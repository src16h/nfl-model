"""
NBA props check: replay past game nights with only what was known before tip-off (player rates, minutes,
the ratings' expected scores) and the players who actually played, then compare the model's chances with
what happened. Prints calibration by stat at several lines and the mean miss.

    python tools/nba_props_check.py [season] [every_nth_date]
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from nbamodel import config as C  # noqa: E402
from nbamodel import gamemodel as G  # noqa: E402
from nbamodel import props as P  # noqa: E402
from nbamodel import ratings as R  # noqa: E402
from tools.nba_backtest import prep  # noqa: E402


def run(season=2025, every=6, n=4000):
    g, _ = prep()
    games, pg = __import__("nbamodel.data", fromlist=["load"]).load()
    w = R.walk(g, C.ADJ, start_season=season)
    w = w[(w["season"] == season) & w["p_h"].notna() & (w["type"] == "reg")]
    rows = []
    rng = np.random.default_rng(5)
    dates = sorted(w["d"].unique())[10::every]
    for d in dates:
        day = w[w["d"] == d]
        asof = day["start_dt"].min()
        tbl, tavg = P.player_table(pg, games, asof)
        for _, x in day.iterrows():
            sim = G.simulate(x["p_h"], x["p_a"], rng, n)
            box = pg[pg["game_id"] == x["game_id"]]
            act = {str(b.pid): b for b in box.itertuples() if not b.dnp and b.min > 0}
            for team, side in ((x["home"], "H"), (x["away"], "A")):
                pl = [dict(p, avail=1.0) for p in P.roster(tbl, team, asof) if p["pid"] in act]
                pl += [dict(p, avail=0.0) for p in P.roster(tbl, team, asof) if p["pid"] not in act]
                pl = [p for p in pl if p["exp_min"] > 0]
                arr = P.team_players(sim, side, pl, tavg.get(team), rng)
                for p in pl:
                    if p["avail"] < 1 or p["exp_min"] < 12:
                        continue
                    a = act[p["pid"]]
                    for st in C.PROP_STATS:
                        xs = arr[p["pid"]][st]
                        val = a.pts + a.reb + a.ast if st == "pra" else getattr(a, st)
                        fair = P._fair(P._dist(xs, P.MAXK[st]))
                        for off in (-2, 0, 2) if st in ("pts", "pra") else (-1, 0, 1):
                            L = fair + off
                            rows.append((st, off, float((xs > L).mean()), float(val > L)))
                        rows.append((st, "mean", float(xs.mean()), float(val)))
                        if st in ("pts", "pra"):
                            mu = float(xs.mean())
                            tier = "lo" if mu < 10 else "mid" if mu < 18 else "hi"
                            rows.append((st, "mean_" + tier, mu, float(val)))
    df = pd.DataFrame(rows, columns=["stat", "off", "p", "y"])
    out = {}
    for st, x in df.groupby("stat"):
        mm = x[x["off"] == "mean"]
        rec = {"n": int(len(mm)), "mean_model": round(mm["p"].mean(), 2), "mean_real": round(mm["y"].mean(), 2)}
        for tier, xx in x[x["off"].astype(str).str.startswith("mean_")].groupby("off"):
            rec[tier] = [len(xx), round(xx["p"].mean(), 2), round(xx["y"].mean(), 2)]
        for off, xx in x[~x["off"].astype(str).str.startswith("mean")].groupby("off"):
            rec[f"over_at_fair{int(off):+d}"] = [round(100 * xx["p"].mean(), 1), round(100 * xx["y"].mean(), 1)]
        out[st] = rec
    return out


if __name__ == "__main__":
    s = int(sys.argv[1]) if len(sys.argv) > 1 else 2025
    e = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    print(json.dumps(run(s, e), indent=1))
