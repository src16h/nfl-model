"""
Game simulation: the ratings give each team's expected points; each simulated game draws a margin and
a total around them (normal, sizes fit on past seasons), rounds to whole scores, and plays overtime
when tied. Returns arrays of final scores (FH, FA) that price every spread, total, team total and alt
line (altlines.Dist), and drive the player props.
"""
import numpy as np

from . import config as C


def simulate(ph, pa, rng, n=None):
    n = n or C.N_SIMS
    m = rng.normal(ph - pa, C.MARGIN_SD, n)
    t = rng.normal(ph + pa, C.TOTAL_SD, n)
    t = np.maximum(t, np.abs(m) + 120)
    fh = np.round((t + m) / 2).astype(int)
    fa = np.round((t - m) / 2).astype(int)
    reg_h, reg_a = fh.copy(), fa.copy()
    tie = fh == fa
    ot = np.zeros(n, int)
    while tie.any():                                       # overtime: about 11 points between the teams
        k = int(tie.sum())
        edge = 0.5 + np.clip((ph - pa) / 60, -0.15, 0.15)  # the better team has a small edge in OT
        oh = rng.poisson(C.OT_PTS / 2 * (0.9 + 0.2 * edge), k)
        oa = rng.poisson(C.OT_PTS / 2 * (1.1 - 0.2 * edge), k)
        fh[tie] += oh
        fa[tie] += oa
        ot[tie] += 1
        tie = fh == fa
    return {"FH": fh, "FA": fa, "RH": reg_h, "RA": reg_a, "OT": ot, "ph": ph, "pa": pa}
