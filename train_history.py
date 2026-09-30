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

    def optional(fn, s, label):
        try:
            df = D._pd(fn([s]))
            return df if len(df) else None
        except Exception as e:  # noqa: BLE001
            log.info(f"  no {label} for {s}: {str(e)[:80]}")
            return None

    out, prev, prev_snaps = [], None, None
    for s in range(start, last + 1):
        log.info(f"season {s}")
        cur = D.load_pbp_season(s)
        prev = prev if prev is not None else D.load_pbp_season(s - 1)
        pbp = pd.concat([prev, cur], ignore_index=True)
        inj = optional(D.nfl.load_injuries, s, "injury reports")
        snaps_cur = optional(D.nfl.load_snap_counts, s, "snap counts")
        if prev_snaps is None:
            prev_snaps = optional(D.nfl.load_snap_counts, s - 1, "snap counts")
        snaps = pd.concat([x for x in (prev_snaps, snaps_cur) if x is not None], ignore_index=True) \
            if (prev_snaps is not None or snaps_cur is not None) else None
        rows = history_rows(pbp, sch, elo_pre, [s], injuries=inj, snaps=snaps)
        cov = rows["inj_known"].mean() if len(rows) else 0
        log.info(f"  {len(rows)} games, injury data on {cov:.0%}")
        out.append(rows)
        prev, prev_snaps = cur, snaps_cur

    df = pd.concat(out, ignore_index=True)
    path = ROOT / "data" / "training_rows.csv"
    df.round(4).to_csv(path, index=False)
    log.info(f"saved {len(df)} games to {path}")


if __name__ == "__main__":
    main()
