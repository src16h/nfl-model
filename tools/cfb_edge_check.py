"""
CFB edge check (Oct 31 2026): where, if anywhere, the model beats the betting line. Rebuilds the walk-forward
predictions the site uses (cfbmodel/backtest.walk) and prints:
  - how much the model's disagreement with the CLOSING line predicts the result (regression weight; 0 = nothing)
  - spreads and totals against the OPENING line by gap size and season (bias corrected on earlier seasons only)

    python tools/cfb_edge_check.py
"""
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cfbmodel import backtest as BT, config as C, data as D, pbp as B, ratings as R  # noqa: E402


def main():
    now = datetime.now(timezone.utc)
    cal = D.calendar()
    season = cal["season"]
    utc = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))
    weeks = [(2, w["week"]) for w in cal["weeks"] if w["stype"] == 2 and utc(w["start"]) <= now + timedelta(days=8)]
    with ThreadPoolExecutor(6) as ex:
        sched = [g for wk in ex.map(lambda sw: D.scoreboard(season, sw[1], sw[0]), weeks) for g in wk]
    p4 = {g[s]["id"] for g in sched for s in ("home", "away") if g[s]["conf"] in C.P4_CONFS} | set(C.P4_EXTRA)
    games_t, tg, _ = B.update(list({g["game_id"]: g for g in sched}.values()), {season - 1, season})
    t = R.prepare(games_t, tg)
    H = BT.walk(R.features(t, R.build(t)), games_t)
    print("model weight vs the close (0 = adds nothing):", BT.close_weight(H, p4, season + 1))
    for gap in (3, 4, 5, 6):
        print(f"early totals vs open, gap {gap}+:", BT.early_totals(H, p4, gap))
    x = H[(H["team_id"].isin(p4) | H["opp_id"].isin(p4)) & H["open_spread"].notna()]
    d, res = x["em"] + x["open_spread"], x["m"] + x["open_spread"]
    for gap in (3, 5, 7):
        sel = d.abs() >= gap
        print(f"spreads vs open, gap {gap}+:", {int(s): BT._rec(d[sel & (x['season'] == s)], res[sel & (x['season'] == s)]) for s in sorted(x["season"].unique())})


if __name__ == "__main__":
    main()
