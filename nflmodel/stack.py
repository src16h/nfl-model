"""
Two engines, graded the same honest way.

INDEPENDENT: predicts the final margin/total from football data only.
             Good for projected scores. Never sees the Vegas line.
ANCHORED:    starts at the Vegas line and predicts only how far the real
             result lands from it. This is what a betting model needs:
             "where is Vegas likely wrong?" Picks this week's leans.

Each engine = ridge regression (explainable) + optional gradient boosting,
blend chosen by walk-forward backtest: to grade 2019, train only on seasons
before 2019. Results are also broken down by edge size, so we can see
whether bigger disagreements with Vegas actually win more often.
"""
import logging
import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.preprocessing import StandardScaler

from . import config as C
from .features import (MARGIN_FEATS, TOTAL_FEATS, ANCHOR_MARGIN_FEATS, ANCHOR_TOTAL_FEATS,
                       LABELS, label)

log = logging.getLogger("nflmodel")
ALPHAS = [0.3, 1, 3, 10, 30, 100, 300, 1000, 3000]

# name: (features, target, line column used as the anchor or None)
SPECS = {
    "ind_margin": (MARGIN_FEATS, "actual_margin", None),
    "ind_total": (TOTAL_FEATS, "actual_total", None),
    "anc_margin": (ANCHOR_MARGIN_FEATS, "actual_margin", "spread_line"),
    "anc_total": (ANCHOR_TOTAL_FEATS, "actual_total", "total_line"),
}
BUCKETS = {
    "independent": {"spread": [0, 1, 2, 3, 4, 6, 99], "total": [0, 1.5, 3, 4.5, 6, 99]},
    "anchored": {"spread": [0, 0.5, 1, 1.5, 2, 3, 99], "total": [0, 0.5, 1, 1.5, 2, 3, 99]},
}


class Learner:
    def __init__(self, feats, target, anchor=None, gbm_w=0.0):
        self.feats, self.target, self.anchor, self.gbm_w = feats, target, anchor, gbm_w

    def _xy(self, df):
        d = df.dropna(subset=[self.target] + ([self.anchor] if self.anchor else []))
        y = d[self.target].to_numpy(float)
        if self.anchor:
            y = y - d[self.anchor].to_numpy(float)
        return d, d[self.feats].fillna(0).to_numpy(float), y

    def fit(self, df):
        d, X, y = self._xy(df)
        w = C.TRAIN_RECENCY ** (d["season"].max() - d["season"]).to_numpy(float)
        self.sc = StandardScaler().fit(X)
        self.ridge = RidgeCV(alphas=ALPHAS).fit(self.sc.transform(X), y, sample_weight=w)
        self.gbm = None
        if self.gbm_w > 0:
            self.gbm = HistGradientBoostingRegressor(
                max_depth=3, learning_rate=0.04, max_iter=250, min_samples_leaf=60,
                l2_regularization=2.0, random_state=0).fit(X, y, sample_weight=w)
        self.n = len(d)
        return self

    def raw_parts(self, df):
        X = df[self.feats].fillna(0).to_numpy(float)
        lin = self.ridge.predict(self.sc.transform(X))
        g = self.gbm.predict(X) if self.gbm is not None else lin
        base = df[self.anchor].to_numpy(float) if self.anchor else 0.0
        return lin, g, base

    def predict(self, df):
        lin, g, base = self.raw_parts(df)
        fin = (1 - self.gbm_w) * lin + self.gbm_w * g
        return fin + base, lin + base

    def drivers(self, row: dict, final: float, lin: float, top=4):
        """Top reasons in points vs an average game (anchored: vs the Vegas line)."""
        x = np.array([[row.get(f, 0) or 0 for f in self.feats]], float)
        z = self.sc.transform(x)[0]
        contrib = self.ridge.coef_ * z * (1 - self.gbm_w)
        out = [(label(f, row.get(f, 0)), float(c)) for f, c in zip(self.feats, contrib)
               if f not in ("spread_line", "total_line")]
        if self.gbm is not None:
            out.append(("Machine-learning patterns", float(final - lin)))
        out = [o for o in out if abs(o[1]) >= (0.15 if self.anchor else 0.3)]
        return sorted(out, key=lambda t: -abs(t[1]))[:top]

    def weights(self):
        return [{"factor": LABELS.get(f, f), "pts": round(float(c), 2)}
                for f, c in sorted(zip(self.feats, self.ridge.coef_), key=lambda t: -abs(t[1]))]


# ---------------------------------------------------------------------
# Grading helpers
# ---------------------------------------------------------------------
def _hit(pred, line, act):
    if not np.isfinite(line) or not np.isfinite(pred) or act == line or pred == line:
        return None
    return int((act > line) == (pred > line))


def _rec(x):
    x = [v for v in x if v is not None]
    return [int(sum(x)), int(len(x) - sum(x))]


def edge_buckets(pred, line, act, edges):
    out = []
    e = np.abs(pred - line)
    for lo, hi in zip(edges[:-1], edges[1:]):
        sel = (e >= lo) & (e < hi) & np.isfinite(line)
        r = _rec([_hit(p, l, a) for p, l, a in zip(pred[sel], line[sel], act[sel])])
        out.append({"range": f"{lo:g}+" if hi >= 99 else f"{lo:g} to {hi:g}", "record": r})
    return out


def _season_report(d, s, lean_s, lean_t):
    sl, tl = d["spread_line"].to_numpy(float), d["total_line"].to_numpy(float)
    am, at = d["actual_margin"].to_numpy(float), d["actual_total"].to_numpy(float)
    pm, pt = d["pm"].to_numpy(float), d["pt"].to_numpy(float)
    hs, ht = np.isfinite(sl), np.isfinite(tl)
    return {
        "season": s, "games": int(len(d)),
        "model_mae": round(float(np.mean(np.abs(pm - am))), 2),
        "vegas_mae": round(float(np.mean(np.abs(sl[hs] - am[hs]))), 2) if hs.any() else None,
        "model_mae_total": round(float(np.mean(np.abs(pt - at))), 2),
        "vegas_mae_total": round(float(np.mean(np.abs(tl[ht] - at[ht]))), 2) if ht.any() else None,
        "ats_all": _rec([_hit(p, l, a) for p, l, a in zip(pm, sl, am)]),
        "ats_leans": _rec([_hit(p, l, a) for p, l, a in zip(pm, sl, am) if abs(p - l) >= lean_s]),
        "totals_leans": _rec([_hit(p, l, a) for p, l, a in zip(pt, tl, at) if abs(p - l) >= lean_t]),
        "straight_up": round(float(((pm > 0) == (am > 0))[am != 0].mean()), 3),
    }


def _wf_predictions(rows, name, test_seasons):
    feats, target, anchor = SPECS[name]
    preds = {w: [] for w in C.GBM_BLEND_OPTIONS}
    for s in test_seasons:
        tr, te = rows[rows["season"] < s], rows[rows["season"] == s]
        m = Learner(feats, target, anchor, 0.5).fit(tr)
        lin, g, base = m.raw_parts(te)
        for w in C.GBM_BLEND_OPTIONS:
            preds[w].append((1 - w) * lin + w * g + base)
    return {w: np.concatenate(v) for w, v in preds.items()}


def lean_thresholds(engine):
    if engine == "anchored":
        return C.ANCHOR_LEAN_SPREAD, C.ANCHOR_LEAN_TOTAL
    return C.LEAN_SPREAD_EDGE, C.LEAN_TOTAL_EDGE


def walk_forward(rows: pd.DataFrame, engine: str):
    """engine: 'independent' or 'anchored'. Returns (report, gbm share margin, total)."""
    seasons = sorted(rows["season"].unique())
    test = [s for s in seasons if sum(x < s for x in seasons) >= 3][-C.WALK_FORWARD_SEASONS:]
    if not test:
        return None, 0.0, 0.0
    te = pd.concat([rows[rows["season"] == s] for s in test])
    am, at = te["actual_margin"].to_numpy(float), te["actual_total"].to_numpy(float)
    pre = "ind" if engine == "independent" else "anc"
    pm_all = _wf_predictions(rows, f"{pre}_margin", test)
    pt_all = _wf_predictions(rows, f"{pre}_total", test)
    wm = min(pm_all, key=lambda w: np.nanmean(np.abs(pm_all[w] - am)))
    wt = min(pt_all, key=lambda w: np.nanmean(np.abs(pt_all[w] - at)))
    te = te.assign(pm=pm_all[wm], pt=pt_all[wt])

    lean_s, lean_t = lean_thresholds(engine)
    b = BUCKETS[engine]
    report = {
        "engine": engine,
        "by_season": [_season_report(d, int(s), lean_s, lean_t) for s, d in te.groupby("season")],
        "overall": _season_report(te, None, lean_s, lean_t),
        "spread_buckets": edge_buckets(te["pm"].to_numpy(float), te["spread_line"].to_numpy(float), am, b["spread"]),
        "total_buckets": edge_buckets(te["pt"].to_numpy(float), te["total_line"].to_numpy(float), at, b["total"]),
        "gbm_share_margin": wm, "gbm_share_total": wt,
        "lean_spread": lean_s, "lean_total": lean_t,
    }
    return report, wm, wt


def build(rows: pd.DataFrame):
    """Train both engines on everything available. None if too little history."""
    rows = rows.dropna(subset=["actual_margin"]).reset_index(drop=True)
    for c in ("inj_margin", "inj_total", "inj_known"):
        if c not in rows.columns:
            rows[c] = 0.0
    rows[["inj_margin", "inj_total", "inj_known"]] = rows[["inj_margin", "inj_total", "inj_known"]].fillna(0.0)
    if len(rows) < C.MIN_TRAIN_ROWS:
        log.info(f"only {len(rows)} history rows: using simple calibration")
        return None
    out = {"seasons": sorted(int(s) for s in rows["season"].unique()), "n": len(rows),
           "injury_coverage": float(rows["inj_known"].mean())}

    rep_i, wm, wt = walk_forward(rows, "independent")
    out["ind_margin"] = Learner(*SPECS["ind_margin"], gbm_w=wm).fit(rows)
    out["ind_total"] = Learner(*SPECS["ind_total"], gbm_w=wt).fit(rows)
    out["report_independent"] = rep_i

    lined = rows.dropna(subset=["spread_line", "total_line"]).reset_index(drop=True)
    out["anchored"] = len(lined) >= C.MIN_TRAIN_ROWS
    out["report_anchored"] = None
    if out["anchored"]:
        rep_a, wm, wt = walk_forward(lined, "anchored")
        out["anc_margin"] = Learner(*SPECS["anc_margin"], gbm_w=wm).fit(lined)
        out["anc_total"] = Learner(*SPECS["anc_total"], gbm_w=wt).fit(lined)
        out["report_anchored"] = rep_a
    log.info(f"engines trained on {len(rows)} games (anchored: {out['anchored']}), "
             f"injury data on {out['injury_coverage']:.0%} of games")
    return out
