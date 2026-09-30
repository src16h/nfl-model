"""
The ensemble.

Two learners look at every past game's features:
  1. Ridge regression: a careful weighted average of every factor (explainable)
  2. Gradient boosting: finds non-obvious patterns (e.g. wind only matters when it's cold)
The backtest picks how much to trust #2. Recent seasons count more.

Deep backtest = walk-forward: to grade 2019, train only on seasons before 2019.
"""
import logging
import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.preprocessing import StandardScaler

from . import config as C
from .features import MARGIN_FEATS, TOTAL_FEATS, LABELS, label

log = logging.getLogger("nflmodel")
ALPHAS = [0.3, 1, 3, 10, 30, 100, 300]


class Learner:
    def __init__(self, feats, target, gbm_w=0.0):
        self.feats, self.target, self.gbm_w = feats, target, gbm_w

    def fit(self, df):
        d = df.dropna(subset=[self.target])
        X = d[self.feats].fillna(0).to_numpy(float)
        y = d[self.target].to_numpy(float)
        w = C.TRAIN_RECENCY ** (d["season"].max() - d["season"]).to_numpy(float)
        self.sc = StandardScaler().fit(X)
        Z = self.sc.transform(X)
        self.ridge = RidgeCV(alphas=ALPHAS).fit(Z, y, sample_weight=w)
        self.gbm = None
        if self.gbm_w > 0:
            self.gbm = HistGradientBoostingRegressor(
                max_depth=3, learning_rate=0.04, max_iter=250, min_samples_leaf=50,
                l2_regularization=1.0, random_state=0).fit(X, y, sample_weight=w)
        self.n = len(d)
        return self

    def predict(self, df):
        X = df[self.feats].fillna(0).to_numpy(float)
        lin = self.ridge.predict(self.sc.transform(X))
        if self.gbm is None:
            return lin, lin
        return (1 - self.gbm_w) * lin + self.gbm_w * self.gbm.predict(X), lin

    def drivers(self, row: dict, final: float, lin: float, top=4):
        """Top reasons, in points, vs an average game."""
        x = np.array([[row.get(f, 0) or 0 for f in self.feats]], float)
        z = self.sc.transform(x)[0]
        contrib = self.ridge.coef_ * z * (1 - self.gbm_w)
        out = [(label(f, row.get(f, 0)), float(c)) for f, c in zip(self.feats, contrib)]
        if self.gbm is not None:
            out.append(("Machine-learning patterns", float(final - lin)))
        out = [o for o in out if abs(o[1]) >= 0.3]
        return sorted(out, key=lambda t: -abs(t[1]))[:top]

    def weights(self):
        """Points per 1 standard deviation of each factor (for the dashboard)."""
        return [{"factor": LABELS.get(f, f), "pts": round(float(c), 2)}
                for f, c in sorted(zip(self.feats, self.ridge.coef_), key=lambda t: -abs(t[1]))]


def _ats(pred, line, act):
    if not np.isfinite(line) or act == line:
        return None
    return int((act > line) == (pred > line))


def walk_forward(rows: pd.DataFrame):
    """Grade the ensemble season by season. Returns report + best GBM blend."""
    seasons = sorted(rows["season"].unique())
    test = [s for s in seasons if sum(x < s for x in seasons) >= 3][-C.WALK_FORWARD_SEASONS:]
    if not test:
        return None, 0.0, 0.0
    preds = {w: {"m": [], "t": []} for w in C.GBM_BLEND_OPTIONS}
    idx = []
    for s in test:
        tr, te = rows[rows["season"] < s], rows[rows["season"] == s]
        mm = Learner(MARGIN_FEATS, "actual_margin", 0.5).fit(tr)
        tm = Learner(TOTAL_FEATS, "actual_total", 0.5).fit(tr)
        Xm, Xt = te[MARGIN_FEATS].fillna(0).to_numpy(float), te[TOTAL_FEATS].fillna(0).to_numpy(float)
        lin_m, g_m = mm.ridge.predict(mm.sc.transform(Xm)), mm.gbm.predict(Xm)
        lin_t, g_t = tm.ridge.predict(tm.sc.transform(Xt)), tm.gbm.predict(Xt)
        for w in C.GBM_BLEND_OPTIONS:
            preds[w]["m"].append((1 - w) * lin_m + w * g_m)
            preds[w]["t"].append((1 - w) * lin_t + w * g_t)
        idx.append(te.index)
    te_all = rows.loc[np.concatenate(idx)]
    am, at = te_all["actual_margin"].to_numpy(), te_all["actual_total"].to_numpy()
    mae = {w: (np.mean(np.abs(np.concatenate(p["m"]) - am)), np.mean(np.abs(np.concatenate(p["t"]) - at)))
           for w, p in preds.items()}
    wm = min(mae, key=lambda w: mae[w][0])
    wt = min(mae, key=lambda w: mae[w][1])
    te_all = te_all.assign(pm=np.concatenate(preds[wm]["m"]), pt=np.concatenate(preds[wt]["t"]))

    per = []
    for s, d in te_all.groupby("season"):
        per.append(_season_report(d, int(s)))
    report = {"by_season": per, "overall": _season_report(te_all, None),
              "gbm_share_margin": wm, "gbm_share_total": wt}
    return report, wm, wt


def _season_report(d, s):
    sl, tl = d["spread_line"].to_numpy(float), d["total_line"].to_numpy(float)
    ats = [_ats(p, l, a) for p, l, a in zip(d["pm"], sl, d["actual_margin"])]
    ats = [x for x in ats if x is not None]
    edge = np.abs(d["pm"].to_numpy() - sl)
    lean = [_ats(p, l, a) for p, l, a, e in zip(d["pm"], sl, d["actual_margin"], edge) if e >= C.LEAN_SPREAD_EDGE]
    lean = [x for x in lean if x is not None]
    ou = [_ats(p, l, a) for p, l, a in zip(d["pt"], tl, d["actual_total"]) if np.isfinite(l) and abs(p - l) >= C.LEAN_TOTAL_EDGE]
    ou = [x for x in ou if x is not None]
    has = np.isfinite(sl)
    hast = np.isfinite(tl)
    r = lambda x: [int(sum(x)), int(len(x) - sum(x))]
    return {
        "season": s, "games": int(len(d)),
        "model_mae": round(float(np.mean(np.abs(d["pm"] - d["actual_margin"]))), 2),
        "vegas_mae": round(float(np.mean(np.abs(sl[has] - d["actual_margin"].to_numpy()[has]))), 2) if has.any() else None,
        "model_mae_total": round(float(np.mean(np.abs(d["pt"] - d["actual_total"]))), 2),
        "vegas_mae_total": round(float(np.mean(np.abs(tl[hast] - d["actual_total"].to_numpy()[hast]))), 2) if hast.any() else None,
        "ats_all": r(ats), "ats_leans": r(lean), "totals_leans": r(ou),
        "straight_up": round(float(((d["pm"] > 0) == (d["actual_margin"] > 0))[d["actual_margin"] != 0].mean()), 3),
    }


def build(rows: pd.DataFrame):
    """Train final models on everything available. None if too little history."""
    rows = rows.dropna(subset=["actual_margin"]).reset_index(drop=True)
    if len(rows) < C.MIN_TRAIN_ROWS:
        log.info(f"only {len(rows)} history rows: using simple calibration")
        return None
    report, wm, wt = walk_forward(rows)
    margin = Learner(MARGIN_FEATS, "actual_margin", wm).fit(rows)
    total = Learner(TOTAL_FEATS, "actual_total", wt).fit(rows)
    log.info(f"ensemble trained on {len(rows)} games, ML share margin {wm} total {wt}")
    return {"margin": margin, "total": total, "report": report,
            "seasons": sorted(int(s) for s in rows["season"].unique())}
