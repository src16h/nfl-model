"""
Alt-line parlay check for the weekly review (owner flag, Nov 24 2026): tickets and legs said vs hit, by leg type, said
band, line distance (vs the model's median and the book's main line), leg count, ticket price, correlation between legs
on the same ticket (misses per ticket vs independence at the real leg-type rates, same-team pairs both missing), and an
out-of-sample replay (walk-forward: leg types judged on earlier weeks / days only; 3-leg cap vs 4+).

    python tools/alt_parlay_check.py nfl
    python tools/alt_parlay_check.py nhl 2026-11-17      # nhl / nba / cfb / soccer; the date marks "recent"

Grades from the site's own history files and results.json (NFL without the snap file, so a ticket whose leg player
never touched the ball drops out instead of counting as a miss: about 1 ticket in 80).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if __name__ == "__main__":
    sp = sys.argv[1] if len(sys.argv) > 1 else "nfl"
    if sp == "nfl":
        sys.argv = [sys.argv[0]]
        from tools import _alt_nfl  # noqa: F401
    else:
        from tools import _alt_other  # noqa: F401
