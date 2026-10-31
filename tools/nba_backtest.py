"""
NBA model backtest: walk forward through past seasons (each date's ratings use only earlier games),
fit the rest and lineup adjustments on the early seasons, then grade later seasons against
DraftKings / ESPN BET closing lines. Writes docs/nba/data/backtest.json and prints the summary.

    python tools/nba_backtest.py
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from nbamodel import config as C  # noqa: E402
from nbamodel import data as D  # noqa: E402
from nbamodel import ratings as R  # noqa: E402

FIT_SEASONS = (2023, 2024)       # adjustments fit here (2022 only warms the ratings up)
TEST_SEASONS = (2025, 2026)


def prep():
    games, pg = D.load()
    games = games[games["hs"].notna()].copy()
    form = R.player_form(pg, games)
    loss = R.lineup_loss(form)
    return R.team_frame(games, loss), form


def fit_adjust(g):
    zero = {"b2b": 0.0, "loss_own": 0.0, "loss_opp": 0.0}
    w = R.walk(g, zero, start_season=min(FIT_SEASONS))
    w = w[w["season"].isin(FIT_SEASONS) & w["p_h"].notna()]
    y = np.r_[w["hs"] - w["p_h"], w["as"] - w["p_a"]]
    X = np.c_[-np.r_[w["b2b_h"], w["b2b_a"]], -np.r_[w["loss_h"], w["loss_a"]], np.r_[w["loss_a"], w["loss_h"]], np.ones(2 * len(w))]
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    return {"b2b": round(float(beta[0]), 3), "loss_own": round(float(beta[1]), 4), "loss_opp": round(float(beta[2]), 4)}


def _pct(gap, res, sel=None):
    sel = np.ones(len(gap), bool) if sel is None else sel
    win = int(((np.sign(gap) == np.sign(res)) & (res != 0) & sel).sum())
    loss = int(((np.sign(gap) != np.sign(res)) & (res != 0) & sel).sum())
    return win, loss


def grade(w):
    out = {}
    w = w[w["p_h"].notna() & w["close_spread"].notna() & w["close_total"].notna()].copy()
    w["m_pred"], w["t_pred"] = w["p_h"] - w["p_a"], w["p_h"] + w["p_a"]
    w["m"], w["t"] = w["hs"] - w["as"], w["hs"] + w["as"]
    w["m_mkt"] = -w["close_spread"]                       # home spread -6.5 -> market margin +6.5
    out["games"] = int(len(w))
    out["margin_mae"] = {"model": round(float((w["m"] - w["m_pred"]).abs().mean()), 2), "market": round(float((w["m"] - w["m_mkt"]).abs().mean()), 2)}
    out["total_mae"] = {"model": round(float((w["t"] - w["t_pred"]).abs().mean()), 2), "market": round(float((w["t"] - w["close_total"]).abs().mean()), 2)}
    out["sd"] = {"margin": round(float((w["m"] - w["m_pred"]).std()), 2), "total": round(float((w["t"] - w["t_pred"]).std()), 2),
                 "margin_vs_close": round(float((w["m"] - w["m_mkt"]).std()), 2), "total_vs_close": round(float((w["t"] - w["close_total"]).std()), 2)}
    for k, a, b, y in (("spread", "m_pred", "m_mkt", "m"), ("total", "t_pred", "close_total", "t")):
        best = min(((float(((w[y] - (x * w[a] + (1 - x) * w[b])) ** 2).mean()), x) for x in np.arange(0, 1.01, 0.05)))
        out[f"{k}_best_model_weight"] = round(float(best[1]), 2)
    for k, gap, res in (("spread", w["m_pred"] - w["m_mkt"], w["m"] - w["m_mkt"]), ("total", w["t_pred"] - w["close_total"], w["t"] - w["close_total"])):
        rows = []
        for lo in (0, 1, 2, 3, 4, 5, 6):
            win, loss = _pct(gap.values, res.values, (gap.abs() >= lo).values)
            rows.append({"gap": lo, "w": win, "l": loss, "pct": round(100 * win / max(1, win + loss), 1)})
        out[f"{k}_ats"] = rows
    out["by_season"] = {}
    for s, x in w.groupby("season"):
        a1, b1 = _pct((x["m_pred"] - x["m_mkt"]).values, (x["m"] - x["m_mkt"]).values)
        a2, b2 = _pct((x["t_pred"] - x["close_total"]).values, (x["t"] - x["close_total"]).values)
        out["by_season"][int(s)] = {"games": int(len(x)), "spread_pct": round(100 * a1 / max(1, a1 + b1), 1),
                                   "total_pct": round(100 * a2 / max(1, a2 + b2), 1),
                                   "margin_mae": round(float((x["m"] - x["m_pred"]).abs().mean()), 2),
                                   "market_mae": round(float((x["m"] - x["m_mkt"]).abs().mean()), 2)}
    return out, w


if __name__ == "__main__":
    g, _ = prep()
    coef = fit_adjust(g)
    print("adjustments", coef, flush=True)
    C.ADJ = coef
    w = R.walk(g, coef, start_season=min(TEST_SEASONS))
    rep, _ = grade(w[w["season"].isin(TEST_SEASONS)])
    rep["adjust"] = coef
    rep["fit_seasons"], rep["test_seasons"] = list(FIT_SEASONS), list(TEST_SEASONS)
    print(json.dumps(rep, indent=1))
    out = ROOT / "docs" / "nba" / "data"
    out.mkdir(parents=True, exist_ok=True)
    (out / "backtest.json").write_text(json.dumps(rep, indent=1))
