"""
Pinnacle-implied scorelines.

Pinnacle posts one 1X2, one Asian handicap line and one total. Fitting a scoreline grid (the same
Dixon-Coles grid the model uses) to those no-vig prices gives a sharp fair price for every other
line: the whole Asian handicap ladder, totals at your book's line when it differs, BTTS, draw no
bet and double chance.

Checked Oct 21 2026 on Pinnacle closing prices (Football-Data, EPL / Championship / La Liga,
2023-24 to now): fitted on 1X2 + total 2.5 only, the grid's Asian handicap chance at Pinnacle's own
AH line lands within about 1 point of Pinnacle's real no-vig AH price on average (see
`python -m soccermodel.market`). Draw no bet and double chance come straight from the 1X2, no fit.
"""
import math

import numpy as np
from scipy.optimize import minimize

from . import model as M


def nv(*odds):
    """No-vig chances from American odds."""
    ps = [100 / (o + 100) if o > 0 else -o / (-o + 100) for o in map(float, odds)]
    s = sum(ps)
    return [p / s for p in ps]


def fit(targets, rho, start=(1.4, 1.1)):
    """targets: list of (kind, line, chance) with kind in 'home' / 'away' (1X2 win), 'over' (at line),
    'ah' (home cover at line, pushes ignored). Returns the grid whose prices match best."""
    def loss(x):
        G = M.grid(math.exp(x[0]), math.exp(x[1]), rho)
        ph, _, pa = M.p1x2(G)
        e = 0.0
        for kind, line, p in targets:
            q = ph if kind == "home" else pa if kind == "away" else M.cover(M.total(G, line)) if kind == "over" else M.cover(M.ah(G, line))
            e += (q - p) ** 2
        return e
    res = minimize(loss, np.log(np.array(start)), method="Nelder-Mead", options={"xatol": 1e-4, "fatol": 1e-10, "maxiter": 400})
    lh, la = math.exp(res.x[0]), math.exp(res.x[1])
    return M.grid(lh, la, rho), lh, la, math.sqrt(res.fun / max(len(targets), 1))


def from_sharp(sh, rho, use_ah=True):
    """sh: the sharp book record (American odds). None when Pinnacle has no 1X2."""
    if not (sh and sh.get("ml_home") and sh.get("ml_draw") and sh.get("ml_away")):
        return None
    ph, _, pa = nv(sh["ml_home"], sh["ml_draw"], sh["ml_away"])
    t = [("home", None, ph), ("away", None, pa)]
    if sh.get("total") is not None and sh.get("over_odds") and sh.get("under_odds"):
        t.append(("over", float(sh["total"]), nv(sh["over_odds"], sh["under_odds"])[0]))
    if use_ah and sh.get("ah_home") is not None and sh.get("ah_home_odds") and sh.get("ah_away_odds"):
        t.append(("ah", float(sh["ah_home"]), nv(sh["ah_home_odds"], sh["ah_away_odds"])[0]))
    G, lh, la, err = fit(t, rho)
    return {"G": G, "lh": lh, "la": la, "err": err, "p_home": ph, "p_away": pa, "p_draw": 1 - ph - pa}


# ---------------------------------------------------------------------
# check against Pinnacle's real closing AH prices
# ---------------------------------------------------------------------
def _check():
    import glob
    import pandas as pd

    def am(d):
        return (d - 1) * 100 if d >= 2 else -100 / (d - 1)
    errs, tot_errs = [], []
    for f in sorted(glob.glob("data/soccer/fd/*_2[3-6]2[4-7].csv")):
        d = pd.read_csv(f, encoding="latin-1")
        need = ["PSCH", "PSCD", "PSCA", "PC>2.5", "PC<2.5", "AHCh", "PCAHH", "PCAHA"]
        if not all(c in d.columns for c in need):
            continue
        d = d.dropna(subset=need)
        rho = {"E0": 0.04, "E1": 0.0, "SP": 0.07}[f.split("/")[-1][:2]]
        for _, m in d.iterrows():
            sh = {"ml_home": am(m.PSCH), "ml_draw": am(m.PSCD), "ml_away": am(m.PSCA),
                  "total": 2.5, "over_odds": am(m["PC>2.5"]), "under_odds": am(m["PC<2.5"])}
            x = from_sharp(sh, rho, use_ah=False)
            real = nv(am(m.PCAHH), am(m.PCAHA))[0]
            errs.append(100 * (M.cover(M.ah(x["G"], float(m.AHCh))) - real))
            sh2 = {k: sh[k] for k in ("ml_home", "ml_draw", "ml_away")}
            sh2.update({"ah_home": float(m.AHCh), "ah_home_odds": am(m.PCAHH), "ah_away_odds": am(m.PCAHA)})
            y = from_sharp(sh2, rho)
            tot_errs.append(100 * (M.cover(M.total(y["G"], 2.5)) - nv(sh["over_odds"], sh["under_odds"])[0]))
    e, t = np.array(errs), np.array(tot_errs)
    print(f"AH from 1X2 + total: {len(e)} matches, mean abs error {np.abs(e).mean():.2f} pts, bias {e.mean():+.2f}, 90th pct {np.percentile(np.abs(e), 90):.2f}")
    print(f"Total 2.5 from 1X2 + AH: mean abs error {np.abs(t).mean():.2f} pts, bias {t.mean():+.2f}, 90th pct {np.percentile(np.abs(t), 90):.2f}")


if __name__ == "__main__":
    _check()
