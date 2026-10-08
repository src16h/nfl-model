"""
Game model.

1. Expected regulation goals and shots on goal for each team from a Poisson
   regression on team form (expected goals for and against, finishing,
   goaltending, home ice, back-to-backs).
2. A simulation that keeps the hockey details that decide bets:
   shots then goals (so saves and goals stay linked), empty-net goals that
   turn 1-goal leads into 2-goal wins (the puck line), and overtime / shootout.
"""
import logging

import numpy as np
import pandas as pd
from sklearn.linear_model import PoissonRegressor

from . import config as C

log = logging.getLogger("nhlmodel")
GOAL_FEATS = ["x_off", "x_def", "x_fin", "x_gk", "home", "b2b", "opp_b2b", "early"]
SOG_FEATS = ["s_off", "s_def", "home", "b2b", "opp_b2b"]


def _feats(t, o, home, lg_xg, lg_sog, rest_t, rest_o, gp_t, gk_o=None, lg_fin=1.0):
    """t and o: dicts of pre-game per-game rates for the team and its opponent.
    Finishing and goaltending are measured against the league's current goals per expected goal."""
    gk = (np.log(o["gaq"] / o["xga"]) if gk_o is None else gk_o) - np.log(lg_fin)
    return {"x_off": np.log(t["xgf"] / lg_xg), "x_def": np.log(o["xga"] / lg_xg),
            "x_fin": np.log(t["gfq"] / t["xgf"]) - np.log(lg_fin), "x_gk": gk,
            "s_off": np.log(t["sogf"] / lg_sog), "s_def": np.log(o["soga"] / lg_sog),
            "home": float(home), "b2b": float(rest_t <= 1), "opp_b2b": float(rest_o <= 1),
            "early": float(gp_t < 10)}


def training_rows(tg):
    """Pair each team-game with its opponent's pre-game form."""
    cols = ["gameId", "team", "pre_xgf", "pre_xga", "pre_gf", "pre_ga", "pre_gfq", "pre_gaq", "pre_sogf", "pre_soga", "rest", "gp"]
    opp = tg[cols].rename(columns={c: "o_" + c for c in cols if c != "gameId"})
    m = tg.merge(opp, on="gameId")
    m = m[m["team"] != m["o_team"]].reset_index(drop=True)
    rows = []
    for r in m.itertuples(index=False):
        t = {"xgf": r.pre_xgf, "xga": r.pre_xga, "gf": r.pre_gf, "ga": r.pre_ga, "gfq": r.pre_gfq, "gaq": r.pre_gaq, "sogf": r.pre_sogf, "soga": r.pre_soga}
        o = {"xgf": r.o_pre_xgf, "xga": r.o_pre_xga, "gf": r.o_pre_gf, "ga": r.o_pre_ga, "gfq": r.o_pre_gfq, "gaq": r.o_pre_gaq, "sogf": r.o_pre_sogf, "soga": r.o_pre_soga}
        f = _feats(t, o, r.home, r.lg_xg, r.lg_sog, r.rest, r.o_rest, r.gp, lg_fin=r.lg_fin)
        f.update({"lg_g": r.lg_g, "lg_sog": r.lg_sog, "gameId": r.gameId, "season": r.season, "date": r.date, "team": r.team, "opp": r.o_team,
                  "reg_g": r.reg_gf, "reg_ga": r.reg_ga, "g": r.goalsFor, "ga_": r.goalsAgainst,
                  "sog60": r.sogf, "ot": r.ot, "so": r.so})
        rows.append(f)
    return pd.DataFrame(rows)


class Model:
    def fit(self, rows):
        # rates relative to the league's current level (scoring drifts season to season)
        self.g = PoissonRegressor(alpha=1e-4, max_iter=500).fit(rows[GOAL_FEATS], rows["reg_g"] / rows["lg_g"], sample_weight=rows["lg_g"])
        self.s = PoissonRegressor(alpha=1e-4, max_iter=500).fit(rows[SOG_FEATS], rows["sog60"] / rows["lg_sog"], sample_weight=rows["lg_sog"])
        ot = rows[rows["ot"] == 1]
        self.ot_goal_share = float(1 - ot["so"].mean()) if len(ot) else 0.57
        return self

    def predict(self, X):
        return self.g.predict(X[GOAL_FEATS]) * X["lg_g"].to_numpy(float), self.s.predict(X[SOG_FEATS]) * X["lg_sog"].to_numpy(float)

    def coefs(self):
        return {"goals": dict(zip(GOAL_FEATS, np.round(self.g.coef_, 3))) | {"intercept": round(float(self.g.intercept_), 3)},
                "shots": dict(zip(SOG_FEATS, np.round(self.s.coef_, 3))) | {"intercept": round(float(self.s.intercept_), 3)}}


def simulate(lam_h, lam_a, mus_h, mus_a, eng=(0.0, 0.0, 0.0), ot_goal_share=0.57, n=None, seed=0, detail=False):
    """Returns sims of final scores plus regulation detail.
    lam: expected regulation goals including empty-netters. mus: expected shots (not counting empty-net shots)."""
    n = n or C.N_SIMS
    rng = np.random.default_rng(seed)
    qt, q1, q2 = eng
    k = C.SOG_DISPERSION

    def draw(lh, la):
        Sh = rng.negative_binomial(k, k / (k + mus_h), n)
        Sa = rng.negative_binomial(k, k / (k + mus_a), n)
        Gh = rng.binomial(Sh, min(lh / mus_h, 0.5))
        Ga = rng.binomial(Sa, min(la / mus_a, 0.5))
        m = Gh - Ga
        u = rng.random(n)
        # late-game hockey: a team down one pulls its goalie. Sometimes it ties it (6-on-5),
        # sometimes the leader hits the empty net. Leads of two get empty-netters too.
        tie_h = (m == -1) & (u < qt)
        tie_a = (m == 1) & (u < qt)
        enh = ((m == 1) & (u >= qt) & (u < qt + q1)) | ((m == 2) & (u < q2))
        ena = ((m == -1) & (u >= qt) & (u < qt + q1)) | ((m == -2) & (u < q2))
        return Sh + tie_h, Sa + tie_a, Gh + tie_h, Ga + tie_a, enh.astype(int), ena.astype(int)

    # first pass: how many late goals each side gets, then take them out of the base rate
    _, _, G1h, G1a, eh, ea = draw(lam_h, lam_a)
    lh = max(lam_h - (G1h.mean() + eh.mean() - lam_h), 0.2)
    la = max(lam_a - (G1a.mean() + ea.mean() - lam_a), 0.2)
    Sh, Sa, Gh, Ga, eh, ea = draw(lh, la)
    RH, RA = Gh + eh, Ga + ea                                   # regulation score
    tie = RH == RA
    p_ot_home = 0.5 + C.OT_STRENGTH * (lam_h - lam_a) / (lam_h + lam_a)
    oth = rng.random(n) < p_ot_home
    in_ot = rng.random(n) < ot_goal_share
    FH = RH + (tie & oth).astype(int)
    FA = RA + (tie & ~oth).astype(int)
    out = {"FH": FH, "FA": FA, "RH": RH, "RA": RA, "tie": tie, "ot_goal": tie & in_ot}
    if detail:
        out.update({"SH": Sh + eh + (tie & in_ot & oth), "SA": Sa + ea + (tie & in_ot & ~oth),
                    "GH_ev": Gh, "GA_ev": Ga, "SH_g": Sh, "SA_g": Sa,          # shots and goals against the goalie
                    "ENH": eh, "ENA": ea, "OTH": tie & in_ot & oth, "OTA": tie & in_ot & ~oth})
    return out


def probs(sim, spread_home=-1.5, total=6.0):
    FH, FA = sim["FH"], sim["FA"]
    d, t = FH - FA, FH + FA
    out = {"win_home": float((d > 0).mean()), "reg_tie": float(sim["tie"].mean()),
           "home_by2": float((d >= 2).mean()), "away_by2": float((d <= -2).mean()),
           "mean_total": float(t.mean())}
    return out


def market_probs(sim, spread_home, total):
    """spread_home: home handicap (e.g. -1.5). total: book total."""
    d, t = sim["FH"] - sim["FA"], sim["FH"] + sim["FA"]
    r = d + spread_home
    dec = r != 0
    cover = float((r[dec] > 0).mean()) if dec.any() else 0.5
    td = t != total
    over = float((t[td] > total).mean()) if td.any() else 0.5
    return {"cover_home": cover, "over": over, "total_push": float((~td).mean())}


def fit_eng(model, rows, grid=None):
    """Pick the empty-net rates so simulated regulation margins match real ones."""
    grid = grid or [(t, a, b) for t in (0.14, 0.20, 0.26) for a in (0.25, 0.35, 0.45) for b in (0.25, 0.40, 0.55)]
    sub = rows[rows["home"] == 1].sample(min(800, int((rows["home"] == 1).sum())), random_state=1)
    away = rows[rows["home"] == 0].set_index("gameId")
    sub = sub[sub["gameId"].isin(away.index)]
    lh, sh = model.predict(sub)
    la, sa = model.predict(away.loc[sub["gameId"]].reset_index())
    pair = sub
    real = np.abs(pair["reg_g"] - pair["reg_ga"]).clip(upper=4).value_counts(normalize=True).sort_index()
    best = None
    for q in grid:
        acc = np.zeros(5)
        for i in range(len(pair)):
            s = simulate(lh[i], la[i], sh[i], sa[i], eng=q, n=400, seed=i)
            m = np.abs(s["RH"] - s["RA"]).clip(max=4)
            acc += np.bincount(m, minlength=5)[:5] / 400
        acc /= len(pair)
        err = float(np.sum((acc - real.reindex(range(5), fill_value=0).to_numpy()) ** 2))
        if best is None or err < best[0]:
            best = (err, q, acc)
    log.info(f"empty-net rates {best[1]}, sim margins {np.round(best[2], 3)} vs real {np.round(real.to_numpy(), 3)}")
    return best[1], {"sim": [round(float(x), 3) for x in best[2]], "real": [round(float(x), 3) for x in real.to_numpy()]}
