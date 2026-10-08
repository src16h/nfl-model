"""
Player projections.

  team volume   (plays, pass rate, game script)  from the game model
x player role   (target share, carry share, red-zone share)
x efficiency    (catch rate, yards per target/carry), pulled toward averages
x opponent      (yards and completion rate the defense allows)
= projection    then ranges from a skewed (gamma) distribution
"""
import zlib
import numpy as np
import pandas as pd
from scipy import stats

from . import config as C
from .util import shrink, fnum
from .propsim import simulate_team, quantiles


def _prior(stat, pos):
    table = C.PRIORS[stat]
    return table.get(pos, table.get("WR"))


def _gamma_range(mean, cv):
    if mean <= 0.5:
        return mean, 0.0, mean * 2
    k = 1.0 / cv ** 2
    th = mean / k
    return (float(stats.gamma.ppf(0.5, k, scale=th)),
            float(stats.gamma.ppf(0.1, k, scale=th)),
            float(stats.gamma.ppf(0.9, k, scale=th)))


def _pos_of(pid, roster, eff_row):
    if roster is not None:
        hit = roster[roster["gsis_id"] == pid]
        if len(hit):
            pg = hit.iloc[0]["pgroup"]
            if pg in ("QB", "RB", "WR", "TE"):
                return pg, hit.iloc[0]["full_name"], hit.iloc[0]["team"]
    # infer from usage if roster is missing
    n_db = eff_row.get("db_n", 0) if eff_row is not None else 0
    n_car = eff_row.get("car_n", 0) if eff_row is not None else 0
    n_rec = eff_row.get("rec_n", 0) if eff_row is not None else 0
    name = eff_row.get("pbp_name", pid) if eff_row is not None else pid
    pos = "QB" if n_db > 30 else ("RB" if n_car > n_rec else "WR")
    return pos, name, None


def project_team(team, opp, game, side, ctx, u, roster, inj, qb) -> list[dict]:
    """side = 'home' or 'away'. game holds the final projected points and plays."""
    pts = game[f"proj_{side}"]
    margin = game["margin"] if side == "home" else -game["margin"]
    plays = game[f"plays_{side}"]

    pr = float(np.clip(ctx.lg_pass_rate + ctx.proe.get(team, 0) - C.GAME_SCRIPT_PASS_RATE * margin, 0.40, 0.75))
    dropbacks = plays * pr
    sack_rate = ctx.sack_off.get(team, ctx.lg_sack) * ctx.sack_def.get(opp, ctx.lg_sack) / ctx.lg_sack
    eff = u["eff"]
    qb_pid = qb.get("pid")
    qrow = eff.loc[qb_pid] if qb_pid in eff.index else None

    def qrate(num, den, key):
        m, k = C.PRIORS[key]
        if qrow is None:
            return m
        return float(shrink(qrow.get(num, 0), qrow.get(den, 0), m, k))

    scr_rate = qrate("scr_n", "db_n", "qb_scramble_rate")
    pass_att = dropbacks * (1 - sack_rate - scr_rate)
    scrambles = dropbacks * scr_rate
    designed = plays - dropbacks
    team_tgts = pass_att * C.TARGETS_PER_ATTEMPT
    tds = pts * C.TD_PER_POINT
    pass_tds = tds * ctx.pass_td_share.get(team, C.LEAGUE_PASS_TD_SHARE)
    rush_tds = tds - pass_tds

    use = u["usage"]
    use = use[use["team"] == team].copy()
    out_ids = set(inj.loc[inj["status"].isin(["OUT", "DOUBTFUL", "IR"]), "pid"].dropna())
    q_ids = set(inj.loc[inj["status"] == "QUESTIONABLE", "pid"].dropna())
    use = use[~use["pid"].isin(out_ids)]

    # keep only players still on this roster
    info = {}
    for pid in use["pid"]:
        erow = eff.loc[pid] if pid in eff.index else None
        pos, name, rteam = _pos_of(pid, roster, erow)
        info[pid] = (pos, name, rteam)
    if roster is not None and (roster["team"] == team).sum() >= 40:
        # drop players who left: traded, cut, or retired since these plays
        use = use[use["pid"].map(lambda p: info[p][2] == team)]
    # only the expected QB runs designed QB carries
    use = use[~use["pid"].map(lambda p: info[p][0] == "QB" and p != qb_pid)]

    for c in ["tgt_share", "car_share", "rz_tgt_share", "rz_car_share"]:
        tot = use[c].sum()
        use[c] = use[c] / tot if tot > 0 else 0.0

    rows = []
    for _, r in use.iterrows():
        pid = r["pid"]
        pos, name, _ = info[pid]
        erow = eff.loc[pid] if pid in eff.index else {}
        g = (lambda k: float(erow.get(k, 0)) if len(erow) else 0.0)
        tgt = team_tgts * r["tgt_share"]
        cm, ck = _prior("catch_rate", pos if pos in ("WR", "TE", "RB") else "WR")
        ym, yk = _prior("yds_per_target", pos if pos in ("WR", "TE", "RB") else "WR")
        catch = shrink(g("rec_cmp"), g("rec_n"), cm, ck) * ctx.def_cmp_mult.get(opp, 1.0)
        ypt = shrink(g("rec_yds"), g("rec_n"), ym, yk) * ctx.def_ypa_mult.get(opp, 1.0)
        car = designed * r["car_share"]
        pm, pk = _prior("ypc", pos if pos in ("RB", "QB", "WR", "TE") else "RB")
        ypc = shrink(g("car_yds"), g("car_n"), pm, pk) * ctx.def_ypc_mult.get(opp, 1.0)
        rows.append({
            "pid": pid, "name": name, "pos": pos, "team": team, "opp": opp,
            "status": "Q" if pid in q_ids else "",
            "tgt_share": r["tgt_share"], "car_share": r["car_share"],
            "targets": tgt, "rec": tgt * float(catch), "rec_yds": tgt * float(ypt),
            "rec_td": pass_tds * (0.5 * r["tgt_share"] + 0.5 * r["rz_tgt_share"]),
            "carries": car, "rush_yds": car * float(ypc),
            "rush_td": rush_tds * (0.5 * r["car_share"] + 0.5 * r["rz_car_share"]),
        })
    df = pd.DataFrame(rows)

    # Make receiving totals agree with the QB's passing line
    cmp_rate = qrate("qb_cmp", "qb_n", "qb_cmp") * ctx.def_cmp_mult.get(opp, 1.0)
    ypa = qrate("qb_yds", "qb_n", "qb_ypa") * ctx.def_ypa_mult.get(opp, 1.0)
    int_rate = qrate("qb_int", "qb_n", "qb_int")
    if len(df) and df["rec_yds"].sum() > 0:
        team_yds = 0.5 * pass_att * ypa + 0.5 * df["rec_yds"].sum()
        team_cmp = 0.5 * pass_att * cmp_rate + 0.5 * df["rec"].sum()
        df["rec_yds"] *= team_yds / df["rec_yds"].sum()
        df["rec"] *= team_cmp / max(df["rec"].sum(), 1e-9)
    else:
        team_yds, team_cmp = pass_att * ypa, pass_att * cmp_rate

    sm, sk = C.PRIORS["qb_scramble_ypa"]
    scr_ypa = float(shrink(qrow.get("scr_yds", 0), qrow.get("scr_n", 0), sm, sk)) if qrow is not None else sm

    # correlated simulations (before the QB row is merged)
    sims = {}
    if len(df):
        seed = zlib.crc32(f"{game['game_id']}{team}".encode())
        sims = simulate_team(df, qb_pid, pass_tds, rush_tds, pass_att * int_rate,
                             scrambles, scrambles * scr_ypa, seed=seed, pass_att=pass_att)
        # simulated passing volume follows receivers; keep the mean consistent
        team_cmp = float(df["rec"].sum())

    # the QB row
    if qb_pid is not None:
        existing = df[df["pid"] == qb_pid] if len(df) else df
        base = existing.iloc[0].to_dict() if len(existing) else {
            "pid": qb_pid, "name": qb.get("name"), "pos": "QB", "team": team, "opp": opp,
            "status": "Q" if qb_pid in q_ids else "", "tgt_share": 0, "car_share": 0,
            "targets": 0, "rec": 0, "rec_yds": 0, "rec_td": 0, "carries": 0, "rush_yds": 0, "rush_td": 0}
        base.update({"pos": "QB", "name": qb.get("name") or base["name"],
                     "pass_att": pass_att, "pass_cmp": team_cmp, "pass_yds": team_yds,
                     "pass_td": pass_tds, "pass_int": pass_att * int_rate,
                     "carries": base["carries"] + scrambles,
                     "rush_yds": base["rush_yds"] + scrambles * scr_ypa})
        df = df[df["pid"] != qb_pid] if len(df) else df
        df = pd.concat([df, pd.DataFrame([base])], ignore_index=True)

    for c in ["pass_att", "pass_cmp", "pass_yds", "pass_td", "pass_int"]:
        if c not in df.columns:
            df[c] = 0.0
    df = df.fillna({c: 0.0 for c in ["pass_att", "pass_cmp", "pass_yds", "pass_td", "pass_int"]})
    df["fpts_ppr"] = (df["pass_yds"] * 0.04 + df["pass_td"] * 4 - df["pass_int"] * 2 +
                      df["rush_yds"] * 0.1 + df["rush_td"] * 6 +
                      df["rec"] + df["rec_yds"] * 0.1 + df["rec_td"] * 6)
    df["td_prob"] = 1 - np.exp(-(df["rush_td"] + df["rec_td"]))

    keep = (df["pos"] == "QB") | (df["tgt_share"] >= C.MIN_TARGET_SHARE) | (df["car_share"] >= C.MIN_CARRY_SHARE)
    df = df[keep]
    rows = [_finish(r, game["game_id"], sims.get(r["pid"])) for _, r in df.iterrows()]
    return rows, {(game["game_id"], pid): v for pid, v in sims.items()}


def _rng(sim, key, mean, cv):
    if sim is not None and key in sim:
        return quantiles(sim[key])
    return _gamma_range(mean, cv)


def _finish(r, game_id, sim=None) -> dict:
    tdp = float(sim["anytime_td"].mean()) if sim is not None else r["td_prob"]
    lam = r["rush_td"] + r["rec_td"]
    td2 = float((sim["tds"] >= 2).mean()) if sim is not None and "tds" in sim else 1 - np.exp(-lam) * (1 + lam)
    d = {"game_id": game_id, "pid": r["pid"], "name": r["name"], "pos": r["pos"],
         "team": r["team"], "opp": r["opp"], "status": r["status"],
         "fpts": fnum(r["fpts_ppr"]), "td_prob": fnum(tdp * 100, 1), "td2_prob": fnum(td2 * 100, 1),
         "td_exp": fnum(lam, 2)}
    if sim is not None:
        med, lo, hi = quantiles(sim["fpts"])
        d.update({"fpts_med": fnum(med), "fpts_range": [fnum(lo), fnum(hi)]})
    if sim is not None:
        d["markets"] = market_dists(sim, r["pos"])
    if r["pos"] == "QB":
        med, lo, hi = _rng(sim, "pass_yds", r["pass_yds"], C.PASS_YDS_CV)
        d.update({"pass_att": fnum(r["pass_att"]), "pass_cmp": fnum(r["pass_cmp"]),
                  "pass_yds": fnum(r["pass_yds"], 0), "pass_yds_med": fnum(med, 0),
                  "pass_yds_range": [fnum(lo, 0), fnum(hi, 0)],
                  "pass_td": fnum(r["pass_td"], 2), "pass_int": fnum(r["pass_int"], 2)})
    if r["carries"] >= 0.5:
        cv = float(np.clip(0.85 - 0.004 * r["rush_yds"], 0.45, 0.95))
        med, lo, hi = _rng(sim, "rush_yds", r["rush_yds"], cv)
        d.update({"carries": fnum(r["carries"]), "rush_yds": fnum(r["rush_yds"], 0),
                  "rush_yds_med": fnum(med, 0), "rush_yds_range": [fnum(lo, 0), fnum(hi, 0)],
                  "rush_td": fnum(r["rush_td"], 2)})
    if r["targets"] >= 0.5:
        cv = float(np.clip(0.95 - 0.004 * r["rec_yds"], 0.55, 0.95))
        med, lo, hi = _rng(sim, "rec_yds", r["rec_yds"], cv)
        d.update({"targets": fnum(r["targets"]), "rec": fnum(r["rec"]),
                  "rec_yds": fnum(r["rec_yds"], 0), "rec_yds_med": fnum(med, 0),
                  "rec_yds_range": [fnum(lo, 0), fnum(hi, 0)], "rec_td": fnum(r["rec_td"], 2)})
    return d


# ---------------------------------------------------------------------
# Extra markets (model only, no book odds): compact distributions so the
# dashboard can show a fair line and the over chance at any line you type.
# ---------------------------------------------------------------------
COUNT_STATS = {"pass_cmp", "pass_att", "carries", "q1_rec"}
MARKET_POS = {
    "rush_rec_yds": ("RB", "WR", "TE"), "pass_cmp": ("QB",), "pass_att": ("QB",),
    "carries": ("RB", "QB"), "q1_pass_yds": ("QB",), "q1_rec_yds": ("WR", "TE", "RB"),
    "q1_rec": ("WR", "TE", "RB"),
}


def market_dists(sim: dict, pos: str) -> dict:
    out = {}
    for stat, poss in MARKET_POS.items():
        if pos not in poss or stat not in sim:
            continue
        a = np.asarray(sim[stat], float)
        if a.mean() < (0.6 if stat in COUNT_STATS else 3.0):      # too small to be offered
            continue
        if stat in COUNT_STATS:
            hi = int(np.percentile(a, 99.5)) + 1
            ge = [fnum(float((a >= k).mean()) * 100, 1) for k in range(0, hi + 1)]
            out[stat] = {"mean": fnum(a.mean(), 1), "med": fnum(np.median(a), 1), "ge": ge}
        else:
            q = np.percentile(a, list(range(2, 100, 2)))               # 2nd..98th percentile
            out[stat] = {"mean": fnum(a.mean(), 1), "med": fnum(np.median(a), 1),
                         "zero": fnum(float((a <= 0).mean()) * 100, 1), "q": [fnum(v, 1) for v in q]}
    return out
