"""
Match model: team attack and defence ratings, then a full scoreline grid.

Ratings: a Poisson regression on every league match in the window, weighted by recency
(HALF_LIFE_DAYS), with an extra cut on older seasons (rosters turn over each summer). The target
blends xG (Understat, or shot-based xG where there is none) with real goals, because xG settles
faster than goals. Features: attack and defence for each club, home edge, and a newcomer offset
for clubs promoted (or relegated) into the league, so a promoted side starts below average
instead of at it. L2 shrinkage pulls small samples toward league average.

Scorelines: independent Poisson for each side, with the Dixon-Coles correction on 0-0, 1-0, 0-1
and 1-1 (real matches have more low-score draws than plain Poisson says). Every market (1X2, draw
no bet, totals, Asian handicap, BTTS) is read off the same grid, so they always agree.
"""
import math

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.linear_model import PoissonRegressor

from . import config as C

MAXG = 11


def shot_xg(sot, shots, coef=None):
    c = coef or C.SHOT_XG
    return c["sot"] * sot + c["off"] * np.maximum(shots - sot, 0)


def signal(df, coef=None):
    """Per-side attacking signal for each match: blend of xG (or shot-xG) and goals."""
    sx_h = shot_xg(df["hst"], df["hs"], coef)
    sx_a = shot_xg(df["ast"], df["as_"], coef)
    lvl = (df["hg"].sum() + df["ag"].sum()) / max(sx_h.sum() + sx_a.sum(), 1e-9)   # shot-xG on this league's goal scale
    if np.isfinite(lvl) and lvl > 0:
        sx_h, sx_a = sx_h * lvl, sx_a * lvl
    xg_h = df["hxg"].fillna(sx_h) if "hxg" in df else sx_h
    xg_a = df["axg"].fillna(sx_a) if "axg" in df else sx_a
    xg_h, xg_a = xg_h.fillna(df["hg"]), xg_a.fillna(df["ag"])
    w = C.XG_WEIGHT
    return w * xg_h + (1 - w) * df["hg"], w * xg_a + (1 - w) * df["ag"]


class Ratings:
    def __init__(self, teams, coef, intercept, home):
        self.teams, self.coef, self.intercept, self.home = teams, coef, intercept, home

    def att(self, t):
        return self.coef.get(("att", t), 0.0)

    def dfn(self, t):
        return self.coef.get(("def", t), 0.0)

    def lambdas(self, home, away, new=None):
        """Expected goals for home and away. new: {team: 'up'|'down'} newcomer flags for this season."""
        new = new or {}
        nh, na = new.get(home), new.get(away)
        lh = self.intercept + self.home + self.att(home) + self.dfn(away)
        la = self.intercept + self.att(away) + self.dfn(home)
        if nh:
            lh += self.coef.get(("new_att", nh), 0.0)
            la += self.coef.get(("new_def", nh), 0.0)
        if na:
            la += self.coef.get(("new_att", na), 0.0)
            lh += self.coef.get(("new_def", na), 0.0)
        return math.exp(lh), math.exp(la)

    def table(self, new=None):
        """Per team: attack and defence as goals per match vs an average side, neutral venue."""
        new = new or {}
        out = {}
        base = math.exp(self.intercept + self.home / 2)
        for t in self.teams:
            a = self.att(t) + (self.coef.get(("new_att", new[t]), 0.0) if new.get(t) else 0.0)
            d = self.dfn(t) + (self.coef.get(("new_def", new[t]), 0.0) if new.get(t) else 0.0)
            out[t] = {"att": base * math.exp(a), "def": base * math.exp(d)}
        return out


def newcomers(league_teams, league, season, higher=None):
    """{team: 'up'|'down'} for clubs in `season` that were not in the league the season before."""
    now, prev = league_teams.get((league, season), set()), league_teams.get((league, season - 1), set())
    if not prev:
        return {}
    hi_prev = league_teams.get((higher, season - 1), set()) if higher else set()
    return {t: ("down" if t in hi_prev else "up") for t in now - prev}


def fit(df, asof, new_by_season, alpha=0.01, coef=None):
    """df: one league's matches (with hxg/axg where known). Uses matches strictly before `asof`."""
    d = df[(df["date"] < asof) & df["hg"].notna()]
    if len(d) < 50:
        return None
    age = np.array([(asof - x).days for x in d["date"]], dtype=float)
    cur_season = int(d["season"].max())
    w = np.exp(-math.log(2) * age / C.HALF_LIFE_DAYS) * (C.SEASON_CARRY ** (cur_season - d["season"].to_numpy()))
    yh, ya = signal(d, coef)
    teams = sorted(set(d["home"]) | set(d["away"]))
    ti = {t: i for i, t in enumerate(teams)}
    nT = len(teams)
    # columns: att teams, def teams, home, new_att_up, new_att_down, new_def_up, new_def_down
    n = len(d)
    rows, cols, vals = [], [], []
    H, A, S = d["home"].map(ti).to_numpy(), d["away"].map(ti).to_numpy(), d["season"].to_numpy()
    newc = {"up": 0, "down": 1}
    for i in range(n):
        for side in (0, 1):                      # row 2i = home attacking, 2i+1 = away attacking
            r_ = 2 * i + side
            at, df_ = (H[i], A[i]) if side == 0 else (A[i], H[i])
            rows += [r_, r_]
            cols += [at, nT + df_]
            vals += [1.0, 1.0]
            if side == 0:
                rows.append(r_); cols.append(2 * nT); vals.append(1.0)
            nm = new_by_season.get(int(S[i]), {})
            fa, fd = nm.get(teams[at]), nm.get(teams[df_])
            if fa:
                rows.append(r_); cols.append(2 * nT + 1 + newc[fa]); vals.append(1.0)
            if fd:
                rows.append(r_); cols.append(2 * nT + 3 + newc[fd]); vals.append(1.0)
    X = sparse.csr_matrix((vals, (rows, cols)), shape=(2 * n, 2 * nT + 5))
    y = np.empty(2 * n)
    y[0::2], y[1::2] = yh.to_numpy(), ya.to_numpy()
    sw = np.repeat(w, 2)
    ok = np.isfinite(y)
    m = PoissonRegressor(alpha=alpha, max_iter=300, tol=1e-6)
    m.fit(X[ok], y[ok], sample_weight=sw[ok])
    c = m.coef_
    coefd = {}
    for t, i in ti.items():
        coefd[("att", t)] = float(c[i])
        coefd[("def", t)] = float(c[nT + i])
    coefd[("new_att", "up")], coefd[("new_att", "down")] = float(c[2 * nT + 1]), float(c[2 * nT + 2])
    coefd[("new_def", "up")], coefd[("new_def", "down")] = float(c[2 * nT + 3]), float(c[2 * nT + 4])
    return Ratings(teams, coefd, float(m.intercept_), float(c[2 * nT]))


# ---------------------------------------------------------------------------
# scoreline grid and markets
# ---------------------------------------------------------------------------
def grid(lh, la, rho):
    g = np.arange(MAXG)
    ph = np.exp(-lh) * lh ** g / np.array([math.factorial(k) for k in g])
    pa = np.exp(-la) * la ** g / np.array([math.factorial(k) for k in g])
    M = np.outer(ph, pa)
    M[0, 0] *= 1 - lh * la * rho
    M[0, 1] *= 1 + lh * rho
    M[1, 0] *= 1 + la * rho
    M[1, 1] *= 1 - rho
    M = np.clip(M, 0, None)
    return M / M.sum()


_I = np.arange(MAXG)
DIFF = _I[:, None] - _I[None, :]
TOT = _I[:, None] + _I[None, :]


def p1x2(M):
    return float(M[DIFF > 0].sum()), float(M[DIFF == 0].sum()), float(M[DIFF < 0].sum())


def btts(M):
    return float(M[1:, 1:].sum())


def _half(M, x, line):
    """x: margin grid (home margin for AH, total for totals). Returns win, push, lose chance for x + line > 0."""
    v = x + line
    return float(M[v > 1e-9].sum()), float(M[np.abs(v) <= 1e-9].sum()), float(M[v < -1e-9].sum())


def split(line):
    """Quarter lines (-0.25, -0.75...) are half on each neighbouring line."""
    q = round(line * 4) % 2
    return [line - 0.25, line + 0.25] if q == 1 else [line]


def ah(M, home_line):
    """Home Asian handicap: (win, push, lose), each averaged over the split halves.
    For quarter lines a 'push' half means half the stake back."""
    parts = [_half(M, DIFF, L) for L in split(home_line)]
    return tuple(sum(p[i] for p in parts) / len(parts) for i in range(3))


def total(M, line):
    """Over chances: (win, push, lose) for the Over at `line` (quarter lines split)."""
    parts = [_half(M, TOT, -L) for L in split(line)]
    return tuple(sum(p[i] for p in parts) / len(parts) for i in range(3))


def cover(wpl):
    """Chance of winning the bet ignoring pushes (how a book's no-vig price is quoted)."""
    w, p, l_ = wpl
    return w / (w + l_) if w + l_ > 0 else 0.5


def fit_rho(rows):
    """rows: (lh, la, hg, ag). Dixon-Coles rho that best fits the low scores (grid search)."""
    best, best_ll = 0.0, -1e18
    for rho in np.arange(-0.20, 0.081, 0.01):
        ll = 0.0
        for lh, la, hg, ag in rows:
            M = grid(lh, la, rho)
            ll += math.log(max(M[min(int(hg), MAXG - 1), min(int(ag), MAXG - 1)], 1e-12))
        if ll > best_ll:
            best, best_ll = float(rho), ll
    return best
