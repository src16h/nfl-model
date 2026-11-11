"""
NBA odds from The Odds API, on its own free key (ODDS_API_KEY_NBA). The pulls and the credit budget are shared with
the NHL in dailyodds.py (Nov 11 2026); this file only says what is different for basketball: points first, the
spread fields, ESPN's free DraftKings lines when there is no key, and props posted by late morning.
"""
import sys as _sys
from pathlib import Path
from zoneinfo import ZoneInfo  # noqa: F401

from . import config as C
from .util import norm_name

_sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dailyodds  # noqa: E402
from dailyodds import Fatal, no_vig  # noqa: E402,F401

SPORT = "basketball_nba"
PROP_STAT = {"player_points": "pts", "player_rebounds": "reb", "player_assists": "ast", "player_threes": "fg3m",
             "player_points_rebounds_assists": "pra"}


def _fallback(games):
    """Free fallback: ESPN's DraftKings lines."""
    for g in games:
        if g.get("espn"):
            g["book"] = dict(g["espn"])


API = dailyodds.make(C, norm_name, SPORT, PROP_STAT, label="NBA", key_env="ODDS_API_KEY_NBA",
                     line_keys=("spread", "spread_home_odds", "spread_away_odds"), gid_type=str, fallback=_fallback, free_source="espn",
                     no_key_note="no NBA odds key yet: ESPN's free DraftKings lines (no Pinnacle referee, props or alt lines)",
                     props_ok=lambda et_hour, todo, now: et_hour >= 11)      # props are posted by late morning
run, alt_lines = API.run, API.alt_lines
