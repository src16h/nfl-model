"""
Opponent-adjusted team ratings.

For each stat (points, expected points added per pass and per run, success
rate, yards, attempts, pace) every team gets an offense and a defense number,
fit on all games at once so a big day against a weak defense counts for less.
Last season's rating is the starting point and fades as games pile up.
Ratings are rebuilt for every week using only games played before it, so the
history used for training and testing never peeks ahead.
"""
import numpy as np
import pandas as pd

from . import config as C

# stat -> (numerator columns, weight columns). Rate = sum(num) / sum(weight); per-game stats have weight 1.
STATS = {
    "epa_p": (["epa_p"], ["n_p"]), "epa_r": (["epa_r"], ["n_r"]),
    "sr": (["suc_p", "suc_r"], ["n_p", "n_r"]),
    "pts": (["pts"], None), "pass_yds": (["pass_yds"], None), "rush_yds": (["rush_yds"], None),
    "pass_att": (["pass_att"], None), "rush_att": (["rush_att"], None), "pass_cmp": (["pass_cmp"], None),
    "ypa": (["pass_yds"], ["pass_att"]), "ypc": (["rush_yds"], ["rush_att"]),
    "td_p": (["td_p"], None), "td_r": (["td_r"], None),
}


def tkey(stype, week):
    """Order of weeks inside a season: regular season 1-16, then the postseason."""
    return np.where(np.asarray(stype) == 2, np.asarray(week), 30)


def prepare(games, tg):
    """Team-game rows with season, week key, team ids (FCS pooled) and each stat's value and weight."""
    g = games[["game_id", "season", "stype", "week", "date", "neutral", "home_conf", "away_conf"]].copy()
    g["key"] = tkey(g["stype"], g["week"])
    t = tg.merge(g, on="game_id")
    conf = np.where(t["home"] == 1, t["home_conf"], t["away_conf"])
    oconf = np.where(t["home"] == 1, t["away_conf"], t["home_conf"])
    fbs = pd.Series(conf).isin(C.FBS_CONFS).to_numpy()
    ofbs = pd.Series(oconf).isin(C.FBS_CONFS).to_numpy()
    t["conf"], t["opp_conf"] = conf, oconf
    t["tid"] = np.where(fbs, t["team_id"], C.FCS_ID)
    t["oid"] = np.where(ofbs, t["opp_id"], C.FCS_ID)
    t["hfa"] = np.where(t["neutral"] == 1, 0.0, np.where(t["home"] == 1, 1.0, -1.0))
    for st, (num, wt) in STATS.items():
        nv = t[num].sum(axis=1, min_count=len(num))
        if wt is None:
            t["y_" + st], t["w_" + st] = nv, np.where(nv.notna(), 1.0, 0.0)
        else:
            w = t[wt].sum(axis=1, min_count=len(wt))
            t["y_" + st] = nv / w.where(w > 0)
            t["w_" + st] = np.where(t["y_" + st].notna(), w, 0.0)
    return t.sort_values(["season", "key", "date", "game_id"]).reset_index(drop=True)


def tier(conf):
    c = int(conf) if conf == conf and conf is not None else -1
    return "P4" if c in C.P4_CONFS or c == 18 else ("G5" if c in C.FBS_CONFS else "FCS")


def _solve(rows, st, teams, prior, mu0, hfa0, lam, mu_lam):
    """Ridge fit of one stat. Returns (mu, hfa, off dict, def dict)."""
    idx = {t: i for i, t in enumerate(teams)}
    T = len(teams)
    r = rows[rows["w_" + st] > 0]
    off0 = np.array([prior["off"].get(t, 0.0) for t in teams])
    def0 = np.array([prior["def"].get(t, 0.0) for t in teams])
    if len(r) == 0:
        return mu0, hfa0, dict(zip(teams, off0)), dict(zip(teams, def0))
    n = len(r)
    X = np.zeros((n, 2 * T + 1))
    ti = r["tid"].map(idx).to_numpy()
    oi = r["oid"].map(idx).to_numpy()
    ar = np.arange(n)
    X[ar, ti] = 1.0
    X[ar, T + oi] -= 1.0
    X[:, 2 * T] = 1.0
    w = (r["w_" + st] * r["rw"]).to_numpy(float)
    y = r["y_" + st].to_numpy(float) - hfa0 * r["hfa"].to_numpy(float)
    b0 = np.concatenate([off0, def0, [mu0]])
    L = np.concatenate([np.full(2 * T, lam), [mu_lam]])
    Xw = X * w[:, None]
    A = X.T @ Xw + np.diag(L)
    b = b0 + np.linalg.solve(A, Xw.T @ (y - X @ b0))
    return float(b[2 * T]), hfa0, dict(zip(teams, b[:T])), dict(zip(teams, b[T:2 * T]))


def _hfa(rows, st):
    """Home edge for a stat from every non-neutral game: half the home minus away gap."""
    r = rows[(rows["w_" + st] > 0) & (rows["hfa"] != 0)]
    if len(r) < 200:
        return 0.0
    h = np.average(r.loc[r["hfa"] > 0, "y_" + st], weights=r.loc[r["hfa"] > 0, "w_" + st])
    a = np.average(r.loc[r["hfa"] < 0, "y_" + st], weights=r.loc[r["hfa"] < 0, "w_" + st])
    return float(h - a) / 2


def build(t, prior_games=None, carry=None, decay=None, stats=None, upto=None, older=None):
    """Ratings going into every (season, week key), plus each season's final ratings.

    Returns {(season, key): {stat: (mu, hfa, off, def)}} and the same for the live 'now' state
    under key (season, 99). `upto` limits work to seasons <= upto."""
    prior_games = C.PRIOR_GAMES if prior_games is None else prior_games
    carry = C.PRIOR_CARRY if carry is None else carry
    decay = C.WEEK_DECAY if decay is None else decay
    older = C.PRIOR_OLDER if older is None else older
    stats = stats or list(STATS)
    pgs = prior_games if isinstance(prior_games, dict) else {}
    pg_of = lambda st: pgs.get(st, pgs.get("*", 3.0)) if pgs else prior_games
    final2 = {st: None for st in stats}                # the season before last
    hfa = {st: _hfa(t, st) for st in stats}
    out = {}
    final = {st: None for st in stats}                 # last season's final (mu, off, def)
    tiers_prev = {}
    for season in sorted(t["season"].unique()):
        if upto and season > upto:
            break
        S = t[t["season"] == season]
        teams = sorted(set(S["tid"]) | set(S["oid"]))
        tier_now = {}
        for tid, cf in zip(S["tid"], S["conf"]):
            tier_now.setdefault(tid, tier(cf) if tid != C.FCS_ID else "FCS")
        for tid, cf in zip(S["oid"], S["opp_conf"]):
            tier_now.setdefault(tid, tier(cf) if tid != C.FCS_ID else "FCS")
        priors, mus, lams = {}, {}, {}
        for st in stats:
            f = final[st]
            if f is None:
                priors[st] = {"off": {}, "def": {}}
                mus[st] = float(np.average(S.loc[S["w_" + st] > 0, "y_" + st], weights=S.loc[S["w_" + st] > 0, "w_" + st])) if (S["w_" + st] > 0).any() else 0.0
            else:
                mu_f, off_f, def_f = f
                pr = {"off": {}, "def": {}}
                f2 = final2[st]
                if f2 is not None and older > 0:          # program strength: mix in the season before last
                    off_f = {x: (1 - older) * v + older * f2[1].get(x, v) for x, v in off_f.items()}
                    def_f = {x: (1 - older) * v + older * f2[2].get(x, v) for x, v in def_f.items()}
                for side, src in (("off", off_f), ("def", def_f)):
                    tm = {}
                    for k in ("P4", "G5", "FCS"):
                        v = [src[x] for x in src if tiers_prev.get(x) == k]
                        tm[k] = float(np.mean(v)) if v else 0.0
                    for x in teams:
                        base = tm[tier_now.get(x, "G5")]
                        pr[side][x] = (carry * src[x] + (1 - carry) * base) if x in src else base
                priors[st], mus[st] = pr, mu_f
            wmean = float(S.loc[S["w_" + st] > 0, "w_" + st].mean()) if (S["w_" + st] > 0).any() else 1.0
            lams[st] = pg_of(st) * wmean
        keys = sorted(S["key"].unique())
        for k in keys + [99]:
            past = S[S["key"] < k]
            past = past.assign(rw=decay ** (past["key"].max() - past["key"]) if len(past) else 1.0)
            res = {}
            for st in stats:
                res[st] = _solve(past, st, teams, priors[st], mus[st], hfa[st], lams[st], 40 * lams[st] / max(pg_of(st), 1e-6))
            out[(int(season), int(k))] = res
        for st in stats:
            mu, _, off, deff = out[(int(season), 99)][st]
            final2[st] = final[st]
            final[st] = (mu, off, deff)
        tiers_prev = tier_now
    return out


def features(t, R, stats=None):
    """Pre-game expectation of every stat for each team-game row: mu + offense - opponent defense (+ home edge)."""
    stats = stats or list(STATS)
    cols = {f"x_{st}": np.full(len(t), np.nan) for st in stats}
    cols.update({f"mu_{st}": np.full(len(t), np.nan) for st in stats})
    cols.update({f"o_{st}": np.full(len(t), np.nan) for st in stats})     # what the opponent's offense is expected to do
    for (season, key), idx in t.groupby(["season", "key"]).groups.items():
        res = R.get((int(season), int(key)))
        if res is None:
            continue
        ii = t.index.get_indexer(idx)
        tid, oid = t["tid"].to_numpy()[ii], t["oid"].to_numpy()[ii]
        for st in stats:
            mu, hfa, off, deff = res[st]
            o_t = np.array([off.get(x, 0.0) for x in tid]); d_o = np.array([deff.get(x, 0.0) for x in oid])
            o_o = np.array([off.get(x, 0.0) for x in oid]); d_t = np.array([deff.get(x, 0.0) for x in tid])
            cols[f"x_{st}"][ii] = o_t - d_o
            cols[f"o_{st}"][ii] = o_o - d_t
            cols[f"mu_{st}"][ii] = mu
    return pd.concat([t, pd.DataFrame(cols, index=t.index)], axis=1)


def matchup(res, tid, oid, hfa, stats=None):
    """Feature row for one team in an upcoming game from the current ratings."""
    row = {"tid": tid, "oid": oid, "hfa": hfa}
    for st in (stats or list(STATS)):
        mu, _, off, deff = res[st]
        row[f"x_{st}"] = off.get(tid, 0.0) - deff.get(oid, 0.0)
        row[f"o_{st}"] = off.get(oid, 0.0) - deff.get(tid, 0.0)
        row[f"mu_{st}"] = mu
    return row
