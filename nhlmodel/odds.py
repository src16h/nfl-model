"""
NHL odds from The Odds API, on its own free key (ODDS_API_KEY_NHL). The pulls and the credit budget are shared with
the NBA in dailyodds.py (Nov 11 2026); this file only says what is different for hockey: shots on goal first, the
puck line fields, the league's free moneylines when there is no key, and props posted by early afternoon.
"""
import sys as _sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo  # noqa: F401

from . import config as C
from .util import norm_name

_sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dailyodds  # noqa: E402
from dailyodds import Fatal, no_vig  # noqa: E402,F401

SPORT = "icehockey_nhl"
PROP_STAT = {"player_shots_on_goal": "sog", "player_points": "points", "player_assists": "assists",
             "player_goals": "goals", "player_total_saves": "saves"}


def _fallback(games):
    """Free fallback: the league's posted moneylines."""
    for g in games:
        if g.get("ml_home") and g.get("ml_away"):
            g["book"] = {"ml_home": g["ml_home"], "ml_away": g["ml_away"], "src": "NHL.com"}


def _props_ok(et_hour, todo, now):
    """Props are posted by early afternoon; matinees need them sooner (Oct 31 2026)."""
    soon = any(0 <= (datetime.fromisoformat(g["start"].replace("Z", "+00:00")) - now).total_seconds() / 3600 <= 4 for g in todo)
    return et_hour >= 13 or soon


API = dailyodds.make(C, norm_name, SPORT, PROP_STAT, label="NHL", key_env=C.ODDS_KEY_ENV,
                     line_keys=("pl_home", "pl_home_odds", "pl_away_odds"), gid_type=int, fallback=_fallback, free_source="league",
                     no_key_note="no NHL odds key, using the league's free moneylines", props_ok=_props_ok)
run, alt_lines = API.run, API.alt_lines
