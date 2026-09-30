"""
Builds the deep history the ensemble learns from.
Run by the "Train model" workflow (a few times a year is plenty).

For every game since TRAIN_START_SEASON, it rebuilds the team ratings using
only data available before that game, then saves one row of features plus
the final score to data/training_rows.csv.
"""
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from nflmodel import config as C
from nflmodel import data as D
from nflmodel import elo
from nflmodel.features import history_rows

ROOT = Path(__file__).parent
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("nflmodel")


def main():
    now = datetime.now(timezone.utc)
    current = C.SEASON or (now.year if now.month >= 3 else now.year - 1)
    start = C.TRAIN_START_SEASON
    last = current - 1  # completed seasons only; the weekly run adds this season live
    sch = D._pd(D.nfl.load_schedules(list(range(start - 4, current + 1))))
    elo_pre, _ = elo.compute(sch)

    out, prev = [], None
    for s in range(start, last + 1):
        log.info(f"season {s}")
        cur = D.load_pbp_season(s)
        prev = prev if prev is not None else D.load_pbp_season(s - 1)
        pbp = pd.concat([prev, cur], ignore_index=True)
        rows = history_rows(pbp, sch, elo_pre, [s])
        log.info(f"  {len(rows)} games")
        out.append(rows)
        prev = cur

    df = pd.concat(out, ignore_index=True)
    path = ROOT / "data" / "training_rows.csv"
    df.round(4).to_csv(path, index=False)
    log.info(f"saved {len(df)} games to {path}")


if __name__ == "__main__":
    main()
