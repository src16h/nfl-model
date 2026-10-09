"""
Game model.

1. Stage two: a small regression turns the opponent-adjusted ratings into
   expected points, yards and attempts for each team (ratings.py is stage one).
2. A simulation of final scores around the expected margin and total. The
   spread of results comes from how real games landed around their numbers,
   and the pile-ups on football's common margins (3, 7, 10, 14...) are kept.
"""
import logging

import numpy as np
import pandas as pd

from . import config as C

log = logging.getLogger("cfbmodel")

# target -> rating features used to predict it (x_ = team offense vs opponent defense for that stat)
FEATS = {
    "pts": ["x_pts", "x_epa_p", "x_epa_r", "x_sr", "x_ypa", "x_ypc", "o_epa_p", "o_epa_r", "hfa"],
    "pass_yds": ["x_pass_yds", "x_epa_p", "x_ypa", "x_pass_att", "em", "hfa"],
    "rush_yds": ["x_rush_yds", "x_epa_r", "x_ypc", "x_rush_att", "em", "hfa"],
    "pass_att": ["x_pass_att", "x_rush_att", "em", "et"],
    "rush_att": ["x_rush_att", "x_pass_att", "em", "et"],
    "pass_cmp": ["x_pass_cmp", "x_pass_att", "x_epa_p", "em", "et"],
    "td_p": ["x_td_p", "x_epa_p", "x_pts", "em", "et"],
    "td_r": ["x_td_r", "x_epa_r", "x_pts", "em", "et"],
}
VOLUME = ["pass_yds", "rush_yds", "pass_att", "rush_att", "pass_cmp", "td_p", "td_r"]


def pair(F):
    """Attach the opponent's row to each team-game row (o2_ prefix)."""
    cols = [c for c in F.columns if c.startswith(("x_", "o_", "mu_"))] + ["tid", "pts"]
    o = F[["game_id", "tid"] + [c for c in cols if c != "tid"]].rename(columns={c: "opp_" + c for c in cols})
    m = F.merge(o, on="game_id")
    return m[m["tid"] != m["opp_tid"]].reset_index(drop=True) if "opp_tid" in m else m


class Model:
    def __init__(self):
        self.coef = {}

    @staticmethod
    def _X(F, feats, tgt):
        X = np.column_stack([F[f].to_numpy(float) for f in feats] + [F[f"mu_{tgt}"].to_numpy(float), np.ones(len(F))])
        return X

    def _fit_one(self, F, tgt, feats, ridge=1e-6):
        ok = F[tgt].notna() & F[[f for f in feats]].notna().all(axis=1) & F[f"mu_{tgt}"].notna()
        X, y = self._X(F[ok], feats, tgt), F.loc[ok, tgt].to_numpy(float)
        A = X.T @ X + ridge * np.eye(X.shape[1])
        self.coef[tgt] = np.linalg.solve(A, X.T @ y)

    def fit(self, F):
        """F: features frame (ratings.features) with both teams of every game."""
        self._fit_one(F, "pts", FEATS["pts"])
        F = self.script(F)
        for tgt in VOLUME:
            self._fit_one(F, tgt, FEATS[tgt])
        return self

    def script(self, F):
        """Expected margin and total for each row from the points model (game script for the volume stats)."""
        F = F.copy()
        F["e_pts"] = self._X(F, FEATS["pts"], "pts") @ self.coef["pts"]
        opp = F.groupby("game_id")["e_pts"].transform("sum") - F["e_pts"]
        F["em"], F["et"] = F["e_pts"] - opp, F["e_pts"] + opp
        return F

    def predict(self, F, keep_script=False):
        """keep_script=True uses the em / et already in F (e.g. after anchoring to the book's line)."""
        F = F.copy() if keep_script else self.script(F)
        for tgt in VOLUME:
            ok = F[FEATS[tgt]].notna().all(axis=1) & F[f"mu_{tgt}"].notna()
            F["e_" + tgt] = np.where(ok, self._X(F.fillna(0), FEATS[tgt], tgt) @ self.coef[tgt], np.nan)
        return F

    def coefs(self):
        return {t: dict(zip(FEATS[t] + ["league", "const"], np.round(c, 3))) for t, c in self.coef.items()}


# ---------------------------------------------------------------------
# score simulation
# ---------------------------------------------------------------------
class Scores:
    """Final-score simulator fit on how real games landed around their expected margin and total.

    Residuals are taken from past games with a similar-sized favorite, in the favorite's terms, because
    a 3-point favorite and a 30-point favorite miss their numbers in different ways."""

    def fit(self, margin_exp, total_exp, margin, total):
        """All arrays for past games: expected and actual home margin and total."""
        me, te = np.asarray(margin_exp, float), np.asarray(total_exp, float)
        mg, tt = np.asarray(margin, float), np.asarray(total, float)
        sgn = np.where(me >= 0, 1.0, -1.0)
        a = np.abs(me)
        o = np.argsort(a)
        self.a = a[o]
        self.rf = (sgn * (mg - me))[o]                               # favorite's miss
        self.t0 = float(np.mean(te))
        self.rt = ((tt - te) / np.sqrt(np.clip(te, 30, 90) / self.t0))[o]   # higher totals swing more
        # the expected numbers are treated as 50/50 points (how books set lines), so center misses on their median
        self.rf = self.rf - np.median(self.rf)
        self.rt = self.rt - np.median(self.rt)
        m = np.abs(mg.astype(int))
        # key numbers: how much more often each margin happens than a smooth curve says
        cnt = np.bincount(np.clip(m, 0, 60), minlength=61).astype(float)
        sm = np.convolve(np.pad(cnt, 4, mode="edge"), np.ones(9) / 9, mode="valid")
        kf = np.where(sm > 0, cnt / np.maximum(sm, 1e-9), 1.0)
        kf[0] = 0.0                                                   # no ties: overtime decides
        kf[36:] = 1.0                                                 # thin data out there
        self.kf = np.clip(kf, 0.0, 3.0)
        self.sd_m, self.sd_t = float(np.std(self.rf)), float(np.std(tt - te))
        return self

    def _pool(self, a, need=1200):
        """Index range of past games whose favorite was about this big."""
        c = int(np.searchsorted(self.a, a))
        lo, hi = max(0, c - need // 2), min(len(self.a), c + need // 2)
        lo, hi = max(0, min(lo, hi - need)), min(len(self.a), max(hi, lo + need))
        return lo, hi

    def _raw(self, m, t, k, rng, like=None, orient=None):
        """Unrounded margins and totals around (m, t), plus the random numbers used to finish them."""
        lo, hi = self._pool(abs(m if like is None else like))
        i = rng.integers(lo, hi, k)
        sgn = (1.0 if m >= 0 else -1.0) if orient is None else orient
        # residual pairs come from the same real game, plus a little jitter so sims don't repeat exactly
        Mr = m + sgn * self.rf[i] + rng.normal(0, 1.0, k)
        Tr = t + self.rt[i] * np.sqrt(np.clip(t, 30, 90) / self.t0) + rng.normal(0, 1.0, k)
        return Mr, Tr, rng.choice([-1, 1], k), rng.random(k)

    def _final(self, Mr, Tr, par, u, dm=0.0, dt=0.0):
        """Whole-number scores: round, make both teams' points whole, keep key numbers more often."""
        M, T = np.rint(Mr + dm).astype(int), np.rint(Tr + dt).astype(int)
        T = np.maximum(T, np.abs(M))
        T = np.where((T - M) % 2 != 0, T + par, T)
        T = np.where(T < np.abs(M), T + 2, T)
        keep = u * float(self.kf.max()) < self.kf[np.clip(np.abs(M), 0, 60)]
        return M[keep], T[keep]

    def sim(self, m, t, n=None, seed=0, like=None, orient=None, fit=None, offset=None):
        """n simulated (home points, away points) around home margin m and total t. Returns (home, away, offset).

        Rounding to whole scores and the key numbers shift the middle a little, so the draw is nudged until
        it agrees with a target: by default a 50/50 split at m and t, or with fit=(spread, chance home covers,
        total, chance of the over) the book's own no-vig prices. Passing that offset, the same seed, `like`
        (size of favorite to draw past games from) and `orient` to a second sim makes it use the very same
        past games, so the two differ only by the shift in m and t."""
        n = n or C.N_SIMS
        Mr, Tr, par, u = self._raw(m, t, 7 * n, np.random.default_rng(seed), like, orient)
        if offset is None:
            s, ps, L, po = fit if fit is not None else (-m, 0.5, t, 0.5)

            def solve(f, target):
                lo, hi = -5.0, 5.0
                for _ in range(14):
                    mid = (lo + hi) / 2
                    lo, hi = (mid, hi) if f(mid) < target else (lo, mid)
                return (lo + hi) / 2

            def cover(dm):
                M, _ = self._final(Mr, Tr, par, u, dm, 0.0)
                v = M + s
                return float((v > 0).sum()) / max(int((v != 0).sum()), 1)
            dm = solve(cover, ps)

            def over(dt):
                _, T = self._final(Mr, Tr, par, u, dm, dt)
                return float((T > L).sum()) / max(int((T != L).sum()), 1)
            offset = (dm, solve(over, po))
        M, T = self._final(Mr, Tr, par, u, *offset)
        if len(M) >= n:
            M, T = M[:n], T[:n]
        else:
            j = np.random.default_rng(seed + 2).integers(0, len(M), n)
            M, T = M[j], T[j]
        return (T + M) // 2, (T - M) // 2, offset


# ---------------------------------------------------------------------
# team passing and rushing inside a simulated game
# ---------------------------------------------------------------------
YARDS = ["pass_yds", "rush_yds", "pass_att", "rush_att", "pass_cmp"]


class Volume:
    """How a team's passing and rushing move with the score.

    A team that scores more than expected usually gained more yards; a team that is ahead runs more and
    a team that is behind throws more. Those links are measured on past games, and what is left over is
    drawn from real games so the stats keep their natural spread and stay tied to each other."""

    def fit(self, P):
        """P: predicted frame (Model.predict) with actual stats, pts, opp_pts for past games."""
        ok = P[YARDS + ["e_" + y for y in YARDS] + ["pts", "opp_pts", "e_pts", "em", "td_p", "td_r"]].notna().all(axis=1)
        P = P[ok]
        Z = np.column_stack([P["pts"] - P["e_pts"], (P["pts"] - P["opp_pts"]) - P["em"]])
        R = np.column_stack([P[y] - P["e_" + y] for y in YARDS])
        self.B = np.linalg.lstsq(Z, R, rcond=None)[0]                   # 2 x 5
        self.E = R - Z @ self.B
        # touchdowns given points: real (passing TDs, rushing TDs) pairs for every score
        pts = P["pts"].to_numpy(int)
        self.td_by_pts = {}
        tdn = (P["td_p"] + P["td_r"]).to_numpy(int)
        for v in range(0, 85):
            m = np.abs(pts - v) <= (1 if v < 50 else 4)
            self.td_by_pts[v] = tdn[m] if m.sum() >= 15 else np.array([min(v // 7, 11)])
        self.pass_share = float(P["td_p"].sum() / max((P["td_p"] + P["td_r"]).sum(), 1))
        return self

    def sim(self, e, pts, opp, rng):
        """e: this team's expected values (e_pts, em, e_<stat>). pts, opp: simulated scores. Returns stat arrays."""
        n = len(pts)
        Z = np.column_stack([pts - e["e_pts"], (pts - opp) - e["em"]])
        i = rng.integers(0, len(self.E), n)
        V = np.array([e["e_" + y] for y in YARDS])[None, :] + Z @ self.B + self.E[i]
        out = {y: V[:, k] for k, y in enumerate(YARDS)}
        out["pass_att"] = np.clip(np.rint(out["pass_att"]), 5, 80).astype(int)
        out["rush_att"] = np.clip(np.rint(out["rush_att"]), 8, 80).astype(int)
        out["pass_cmp"] = np.clip(np.rint(out["pass_cmp"]), 1, out["pass_att"]).astype(int)
        out["pass_yds"] = np.clip(out["pass_yds"], 10, None)
        tds = np.zeros(n, int)
        pc = np.clip(pts, 0, 84)
        for v in np.unique(pc):
            m = pc == v
            tds[m] = rng.choice(self.td_by_pts[int(v)], int(m.sum()))
        mix = e["e_td_p"] / max(e["e_td_p"] + e["e_td_r"], 0.2) if e.get("e_td_p") == e.get("e_td_p") else self.pass_share
        mix = float(np.clip(mix, 0.2, 0.8))
        theta = rng.beta(8 * mix, 8 * (1 - mix), n)
        out["td_p"] = rng.binomial(tds, theta)
        out["td_r"] = tds - out["td_p"]
        return out
