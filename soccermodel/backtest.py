"""
Walk-forward backtest: every Monday, refit the ratings on matches before that day and price the
coming week. Compares the model with the closing market (Pinnacle, else market average) and tests
the play rules at the early retail prices a bettor actually gets (Bet365, else market average).

Run:  python -m soccermodel.backtest            (all leagues, writes data/soccer/backtest.json)
"""
import json
import logging
import math
import sys
import time
from datetime import date, timedelta

import numpy as np
import pandas as pd

import betrules as BR
from . import config as C
from . import data as D
from . import model as M

log = logging.getLogger("soccermodel")
HIGHER = {"champ": "epl"}


def load(current):
    seasons = list(range(current - C.HIST_SEASONS + 1, current + 1))
    frames, teams = {}, {}
    for lg in C.LEAGUES:
        fd = D.fd_matches(lg, seasons, current)
        us = D.understat_matches(lg, seasons, current)
        if len(fd) and len(us):
            fd = fd.merge(us, on=["date", "home", "away"], how="left")
        frames[lg] = fd
        for s, g in fd.groupby("season"):
            teams[(lg, int(s))] = set(g["home"]) | set(g["away"])
    new = {lg: {s: M.newcomers(teams, lg, s, HIGHER.get(lg)) for s in seasons} for lg in C.LEAGUES}
    return frames, teams, new


def walk(df, new_by_season, start, end=None, alpha=0.01):
    """Predictions for every match from `start` on: rows of match + lh, la."""
    d0 = start - timedelta(days=start.weekday())
    end = end or df["date"].max()
    out = []
    cut = d0
    while cut <= end:
        wk = df[(df["date"] >= cut) & (df["date"] < cut + timedelta(days=7))]
        if len(wk):
            R = M.fit(df, cut, new_by_season, alpha=alpha)
            if R is not None:
                for _, m in wk.iterrows():
                    lh, la = R.lambdas(m["home"], m["away"], new_by_season.get(int(m["season"]), {}))
                    out.append({**m.to_dict(), "lh": lh, "la": la})
        cut += timedelta(days=7)
    return pd.DataFrame(out)


def nv3(h, d, a):
    ih, id_, ia = 1 / h, 1 / d, 1 / a
    s = ih + id_ + ia
    return ih / s, id_ / s, ia / s


def nv2(a, b):
    ia, ib = 1 / a, 1 / b
    return ia / (ia + ib)


def dec_to_am(x):
    return (x - 1) * 100 if x >= 2 else -100 / (x - 1)


def evaluate(P, rho, w_model=0.5):
    """Log loss and the play rules at early prices, with closing-line value."""
    res = {"n": 0, "ll_model": 0.0, "ll_close": 0.0, "ll_blend": 0.0, "ll_ou_model": 0.0, "ll_ou_close": 0.0, "n_ou": 0,
           "plays": {k: [] for k in ("home", "away", "draw", "over", "under", "ah")}}
    for _, m in P.iterrows():
        if not np.isfinite(m["hg"]):
            continue
        G = M.grid(m["lh"], m["la"], rho)
        ph, pd_, pa = M.p1x2(G)
        hg, ag = int(m["hg"]), int(m["ag"])
        y = 0 if hg > ag else (1 if hg == ag else 2)
        if all(np.isfinite([m["close_h"], m["close_d"], m["close_a"]])):
            ch = nv3(m["close_h"], m["close_d"], m["close_a"])
            pm = (ph, pd_, pa)
            pb = tuple(c + w_model * (p - c) for p, c in zip(pm, ch))
            res["n"] += 1
            res["ll_model"] -= math.log(max(pm[y], 1e-9))
            res["ll_close"] -= math.log(max(ch[y], 1e-9))
            res["ll_blend"] -= math.log(max(pb[y], 1e-9))
            # plays at early prices
            if all(np.isfinite([m["early_h"], m["early_d"], m["early_a"]])):
                eh = nv3(m["early_h"], m["early_d"], m["early_a"])
                for k, i, odds in (("home", 0, m["early_h"]), ("draw", 1, m["early_d"]), ("away", 2, m["early_a"])):
                    edge = pm[i] - eh[i]
                    p = eh[i] + w_model * (pm[i] - eh[i])
                    ev = 100 * (p * odds - 1)
                    res["plays"][k].append({"edge": 100 * edge, "ev": ev, "odds": odds, "win": y == i,
                                            "clv": 100 * (ch[i] * odds - 1), "league": m["league"], "season": m["season"]})
        if np.isfinite(m["close_o25"]) and np.isfinite(m["close_u25"]):
            po = M.cover(M.total(G, 2.5))
            co = nv2(m["close_o25"], m["close_u25"])
            yo = hg + ag > 2.5
            res["n_ou"] += 1
            res["ll_ou_model"] -= math.log(max(po if yo else 1 - po, 1e-9))
            res["ll_ou_close"] -= math.log(max(co if yo else 1 - co, 1e-9))
            if np.isfinite(m["early_o25"]) and np.isfinite(m["early_u25"]):
                eo = nv2(m["early_o25"], m["early_u25"])
                for k, pmk, ek, ck, odds, win in (("over", po, eo, co, m["early_o25"], yo), ("under", 1 - po, 1 - eo, 1 - co, m["early_u25"], not yo)):
                    p = ek + w_model * (pmk - ek)
                    res["plays"][k].append({"edge": 100 * (pmk - ek), "ev": 100 * (p * odds - 1), "odds": odds, "win": win,
                                            "clv": 100 * (ck * odds - 1), "league": m["league"], "season": m["season"]})
        L = m.get("early_ah_line")
        if np.isfinite(L) and np.isfinite(m["early_ahh"]) and np.isfinite(m["early_aha"]):
            wpl = M.ah(G, L)
            mh = M.cover(wpl)
            eh = nv2(m["early_ahh"], m["early_aha"])
            for side, pmk, ek, odds in (("home", mh, eh, m["early_ahh"]), ("away", 1 - mh, 1 - eh, m["early_aha"])):
                p = ek + w_model * (pmk - ek)
                margin = (hg - ag) if side == "home" else (ag - hg)
                line = L if side == "home" else -L
                units = 0.0
                for half in M.split(line):
                    v = margin + half
                    units += (odds - 1 if v > 0 else (0 if v == 0 else -1)) / len(M.split(line))
                res["plays"]["ah"].append({"edge": 100 * (pmk - ek), "ev": 100 * (p * odds - 1), "odds": odds, "units": units,
                                           "league": m["league"], "season": m["season"], "side": side})
    return res


def summarize(res, edge_min=3.0, edge_max=10.0, min_ev=1.5):
    out = {"n": res["n"], "ll_model": res["ll_model"] / max(res["n"], 1), "ll_close": res["ll_close"] / max(res["n"], 1),
           "ll_blend": res["ll_blend"] / max(res["n"], 1),
           "ll_ou_model": res["ll_ou_model"] / max(res["n_ou"], 1), "ll_ou_close": res["ll_ou_close"] / max(res["n_ou"], 1)}
    for k, rows in res["plays"].items():
        sel = [r_ for r_ in rows if edge_min <= r_["edge"] <= edge_max and r_["ev"] >= min_ev]
        if not sel:
            out[k] = {"n": 0}
            continue
        if k == "ah":
            units = sum(r_["units"] for r_ in sel)
            out[k] = {"n": len(sel), "units": round(units, 1), "roi": round(100 * units / len(sel), 1)}
        else:
            units = sum((r_["odds"] - 1) if r_["win"] else -1 for r_ in sel)
            out[k] = {"n": len(sel), "won": round(100 * np.mean([r_["win"] for r_ in sel]), 1), "units": round(units, 1),
                      "roi": round(100 * units / len(sel), 1), "clv": round(float(np.mean([r_["clv"] for r_ in sel])), 2)}
    return out


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    current = C.SEASON or D.season_of(date.today())
    frames, teams, new = load(current)
    report = {}
    for lg in C.LEAGUES:
        t0 = time.time()
        df = frames[lg]
        cache = D.CACHE / f"bt_pred_{lg}.pkl"
        if "--reuse" in (argv or []) and cache.exists():
            P = pd.read_pickle(cache)
        else:
            P = walk(df, new[lg], date(current - 4, 8, 1))
            P.to_pickle(cache)
        first = P[P["season"] == current - 4]
        rho = M.fit_rho([(r_.lh, r_.la, r_.hg, r_.ag) for r_ in first.itertuples() if np.isfinite(r_.hg)])
        test = P[P["season"] > current - 4]
        res = evaluate(test, rho)
        report[lg] = {"rho": rho, **summarize(res)}
        log.info(f"{lg}: {json.dumps(report[lg])} ({time.time() - t0:.0f}s)")
    report["seasons"] = f"{current - 3}-{str(current - 2)[2:]} to {current}-{str(current + 1)[2:]} so far"
    report["note"] = ("Only Premier League Asian handicap and totals, and Championship Asian handicap, made money at early prices, "
                      "so only those can be plays. Picks did not beat the closing line in any league, so treat even those as "
                      "provisional until the live record confirms them. La Liga and all moneylines show leans only.")
    (D.CACHE / "backtest.json").write_text(json.dumps(report, indent=1))
    return report


if __name__ == "__main__":
    main(sys.argv[1:])
