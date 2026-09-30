"""
Game predictions, calibration, and simulation.

1. raw points from ratings (ratings.py)
2. calibration: every run, the model re-checks itself on past games
   and fits home field advantage + a scale factor (keeps it honest)
3. adjustments: rest, QB changes, injuries, scheme matchups
4. simulation: 20,000 games per matchup for win / cover / over odds
"""
import logging
import numpy as np
import pandas as pd

from . import config as C
from .ratings import build_context, raw_points

log = logging.getLogger("nflmodel")


def home_field(row) -> int:
    loc = str(row.get("location", "Home") or "Home")
    return 0 if loc.lower().startswith("neutral") else 1


def rest_adj(row) -> float:
    try:
        d = float(row.get("home_rest", 7)) - float(row.get("away_rest", 7))
    except (TypeError, ValueError):
        return 0.0
    if not np.isfinite(d):
        return 0.0
    return float(np.clip(d * C.REST_POINTS_PER_DAY, -C.REST_CAP, C.REST_CAP))


def raw_game(ctx, row) -> dict:
    h, a = row["home_team"], row["away_team"]
    ph, plays_h = raw_points(ctx, h, a)
    pa, plays_a = raw_points(ctx, a, h)
    return {"raw_home": ph, "raw_away": pa, "plays_home": plays_h, "plays_away": plays_a,
            "raw_margin": ph - pa, "raw_total": ph + pa}


# ---------------------------------------------------------------------
# Backtest + calibration
# ---------------------------------------------------------------------
def backtest_rows(pbp, schedules, season, week, max_contexts=40) -> pd.DataFrame:
    """Predict every completed game from last season week 3 to now,
    using only data available before each game (walk-forward)."""
    sch = schedules[schedules["home_score"].notna()]
    targets = sch[((sch["season"] == season - 1) & (sch["week"] >= 3)) |
                  ((sch["season"] == season) & (sch["week"] < week) & (sch["week"] >= 2))]
    keys = sorted(set(zip(targets["season"], targets["week"])))[-max_contexts:]
    rows = []
    for s, wk in keys:
        try:
            ctx = build_context(pbp, schedules, int(s), int(wk))
        except Exception as e:  # noqa: BLE001
            log.warning(f"backtest {s} wk{wk} skipped: {e}")
            continue
        for _, g in targets[(targets["season"] == s) & (targets["week"] == wk)].iterrows():
            r = raw_game(ctx, g)
            r.update({"season": int(s), "week": int(wk), "game_id": g["game_id"],
                      "hf": home_field(g), "rest": rest_adj(g),
                      "actual_margin": g["home_score"] - g["away_score"],
                      "actual_total": g["home_score"] + g["away_score"],
                      "spread_line": g.get("spread_line"), "total_line": g.get("total_line")})
            rows.append(r)
    return pd.DataFrame(rows)


def fit_calibration(bt: pd.DataFrame) -> dict:
    """Fit HFA + scale with priors so a few weird weeks can't break it."""
    cal = {"hfa": C.DEFAULT_HFA, "m_scale": 1.0, "t_shift": 0.0, "t_scale": 1.0,
           "t_center": 44.0, "n": 0}
    if bt is None or len(bt) < 30:
        return cal
    x = bt["raw_margin"].to_numpy()
    hf = bt["hf"].to_numpy()
    y = bt["actual_margin"].to_numpy() - x - bt["rest"].to_numpy()
    lam_h, lam_b = 60.0, 80.0
    sx = max(np.std(x), 1.0)
    A = np.vstack([np.column_stack([hf, x]),
                   [np.sqrt(lam_h), 0], [0, np.sqrt(lam_b) * sx]])
    tgt = np.concatenate([y, [np.sqrt(lam_h) * C.DEFAULT_HFA, 0.0]])
    hfa, bm1 = np.linalg.lstsq(A, tgt, rcond=None)[0]

    xt = bt["raw_total"].to_numpy()
    m = float(xt.mean())
    st = max(np.std(xt), 1.0)
    yt = bt["actual_total"].to_numpy() - xt
    A2 = np.vstack([np.column_stack([np.ones_like(xt), xt - m]),
                    [np.sqrt(40.0), 0], [0, np.sqrt(80.0) * st]])
    t2 = np.concatenate([yt, [0.0, 0.0]])
    c, dm1 = np.linalg.lstsq(A2, t2, rcond=None)[0]

    cal.update({"hfa": float(np.clip(hfa, 0.0, 3.5)),
                "m_scale": float(np.clip(1 + bm1, 0.6, 1.4)),
                "t_shift": float(np.clip(c, -6, 6)),
                "t_scale": float(np.clip(1 + dm1, 0.6, 1.4)),
                "t_center": m, "n": int(len(bt))})
    return cal


def apply_cal(raw_margin, raw_total, hf, rest, cal):
    margin = cal["hfa"] * hf + cal["m_scale"] * raw_margin + rest
    total = raw_total + cal["t_shift"] + (cal["t_scale"] - 1) * (raw_total - cal["t_center"])
    return margin, total


def _ats(pred_margin, line, actual):
    """Returns 1 win, 0 loss, None push/no line. line = home expected margin."""
    if line is None or not np.isfinite(line):
        return None
    pick_home = pred_margin > line
    res = actual - line
    if res == 0:
        return None
    return int((res > 0) == pick_home)


def backtest_report(bt: pd.DataFrame) -> dict:
    """Walk-forward: each week graded with calibration fitted only on earlier weeks."""
    if bt is None or len(bt) < 20:
        return {"games": 0}
    bt = bt.sort_values(["season", "week"]).reset_index(drop=True)
    preds_m, preds_t = [], []
    for i, r in bt.iterrows():
        prior = bt[(bt["season"] < r["season"]) |
                   ((bt["season"] == r["season"]) & (bt["week"] < r["week"]))]
        cal = fit_calibration(prior)
        m, t = apply_cal(r["raw_margin"], r["raw_total"], r["hf"], r["rest"], cal)
        preds_m.append(m)
        preds_t.append(t)
    bt["pm"], bt["pt"] = preds_m, preds_t
    sl = pd.to_numeric(bt["spread_line"], errors="coerce")
    tl = pd.to_numeric(bt["total_line"], errors="coerce")
    has = sl.notna()

    ats_all = [_ats(m, l, a) for m, l, a in zip(bt["pm"], sl, bt["actual_margin"])]
    edge = (bt["pm"] - sl).abs()
    ats_lean = [x for x, e in zip(ats_all, edge) if e >= C.LEAN_SPREAD_EDGE and x is not None]
    ou = []
    for pt, line, act in zip(bt["pt"], tl, bt["actual_total"]):
        if np.isfinite(line) and abs(pt - line) >= C.LEAN_TOTAL_EDGE and act != line:
            ou.append(int((act > line) == (pt > line)))
    ats_valid = [x for x in ats_all if x is not None]
    return {
        "games": int(len(bt)),
        "seasons": sorted({int(s) for s in bt["season"]}),
        "model_mae_margin": float((bt["pm"] - bt["actual_margin"]).abs().mean()),
        "vegas_mae_margin": float((sl[has] - bt.loc[has, "actual_margin"]).abs().mean()) if has.any() else None,
        "model_mae_total": float((bt["pt"] - bt["actual_total"]).abs().mean()),
        "vegas_mae_total": float((tl[tl.notna()] - bt.loc[tl.notna(), "actual_total"]).abs().mean()) if tl.notna().any() else None,
        "straight_up_pct": float(((bt["pm"] > 0) == (bt["actual_margin"] > 0))[bt["actual_margin"] != 0].mean()),
        "ats_all": [sum(ats_valid), len(ats_valid) - sum(ats_valid)],
        "ats_leans": [sum(ats_lean), len(ats_lean) - sum(ats_lean)],
        "totals_leans": [sum(ou), len(ou) - sum(ou)],
    }


# ---------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------
def simulate(mu_home, mu_away, spread_line=None, total_line=None, seed=0):
    rng = np.random.default_rng(seed)
    h = np.clip(np.round(rng.normal(mu_home, C.TEAM_SCORE_SD, C.N_SIMS)), 0, None)
    a = np.clip(np.round(rng.normal(mu_away, C.TEAM_SCORE_SD, C.N_SIMS)), 0, None)
    d = h - a
    out = {"win_home": float((d > 0).mean() + 0.5 * (d == 0).mean()),
           "margin_p10": float(np.percentile(d, 10)), "margin_p90": float(np.percentile(d, 90))}
    if spread_line is not None and np.isfinite(spread_line):
        res = d - spread_line
        dec = res != 0
        out["cover_home"] = float((res[dec] > 0).mean()) if dec.any() else 0.5
    if total_line is not None and np.isfinite(total_line):
        t = h + a
        dec = t != total_line
        out["over"] = float((t[dec] > total_line).mean()) if dec.any() else 0.5
    return out


# ---------------------------------------------------------------------
# Key numbers: probabilities from real NFL final scores
# ---------------------------------------------------------------------
class KeyNumbers:
    """NFL margins pile up on 3 and 7. Instead of a smooth curve, we look at
    real games that Vegas priced close to our projection and count outcomes."""

    def __init__(self, schedules):
        s = schedules[schedules["home_score"].notna() & (schedules["season"] >= C.KEYNUM_SINCE)]
        s = s.dropna(subset=["spread_line", "total_line"])
        self.L = s["spread_line"].to_numpy(float)
        self.M = (s["home_score"] - s["away_score"]).to_numpy(float)
        self.TL = s["total_line"].to_numpy(float)
        self.T = (s["home_score"] + s["away_score"]).to_numpy(float)
        self.ok = len(s) >= 500
        log.info(f"key numbers: {len(s)} games, {'on' if self.ok else 'off'}")

    def _near(self, arr_line, arr_out, x):
        for win in (1.0, 1.5, 2.5, 3.5):
            sel = np.abs(arr_line - x) <= win
            if sel.sum() >= C.KEYNUM_MIN_GAMES:
                # shift by the small gap so the center matches our number exactly
                return np.round(arr_out[sel] + (x - arr_line[sel]))
        return None

    def probs(self, margin, total, spread_line=None, total_line=None):
        if not self.ok:
            return None
        m = self._near(self.L, self.M, margin)
        t = self._near(self.TL, self.T, total)
        if m is None or t is None:
            return None
        out = {"win_home": float((m > 0).mean() + 0.5 * (m == 0).mean()),
               "margin_p10": float(np.percentile(m, 10)), "margin_p90": float(np.percentile(m, 90))}
        if spread_line is not None and np.isfinite(spread_line):
            dec = m != spread_line
            out["cover_home"] = float((m[dec] > spread_line).mean())
            out["push"] = float((~dec).mean())
        if total_line is not None and np.isfinite(total_line):
            dec = t != total_line
            out["over"] = float((t[dec] > total_line).mean())
        return out
