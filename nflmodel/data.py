"""
Pulls every dataset from nflverse (free, updated daily in season).
Each source is optional except play-by-play and schedules, so one
broken feed never stops the weekly run. Status is shown on the dashboard.
"""
import logging
import pandas as pd

log = logging.getLogger("nflmodel")

try:
    import nflreadpy as nfl
except ImportError:  # pragma: no cover
    nfl = None

PBP_COLS = [
    "game_id", "play_id", "season", "week", "season_type", "home_team", "away_team",
    "posteam", "defteam", "play_type", "pass", "rush", "qb_dropback", "qb_scramble",
    "sack", "pass_attempt", "complete_pass", "interception", "epa", "success", "wp",
    "down", "qtr", "half_seconds_remaining", "yardline_100", "yards_gained",
    "passer_player_id", "passer_player_name", "rusher_player_id", "rusher_player_name",
    "receiver_player_id", "receiver_player_name", "touchdown", "pass_touchdown",
    "rush_touchdown", "td_team", "xpass", "air_yards", "two_point_attempt", "qb_hit",
    "cpoe", "weather",
]


def _pd(df):
    if df is None:
        return None
    if hasattr(df, "to_pandas"):
        return df.to_pandas()
    return pd.DataFrame(df)


def _select(df, cols):
    have = [c for c in cols if c in df.columns]
    return df.select(have) if hasattr(df, "select") else df[have]


class Bundle:
    def __init__(self):
        self.pbp = None
        self.schedules = None
        self.rosters = None
        self.injuries = None
        self.snaps = None
        self.participation = None
        self.status = {}

    def mark(self, name, ok, rows=0, note=""):
        self.status[name] = {"ok": bool(ok), "rows": int(rows), "note": note[:180]}
        (log.info if ok else log.warning)(f"{name}: {'ok' if ok else 'FAILED'} {rows} rows {note}")


def _per_season(fn, seasons, cols=None):
    """Load season by season so a missing season doesn't kill the rest."""
    frames, errors = [], []
    for s in seasons:
        try:
            df = fn([s])
            if cols:
                df = _select(df, cols)
            df = _pd(df)
            if len(df):
                frames.append(df)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{s}: {str(e)[:80]}")
    out = pd.concat(frames, ignore_index=True) if frames else None
    return out, "; ".join(errors)


FLAG_COLS = ["pass", "rush", "qb_dropback", "qb_scramble", "sack", "pass_attempt",
             "complete_pass", "interception", "touchdown", "pass_touchdown",
             "rush_touchdown", "two_point_attempt", "qb_hit"]


def clean_pbp(df):
    for c in FLAG_COLS:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    if "qb_hit" not in df.columns:
        df["qb_hit"] = 0
    df["season"] = df["season"].astype(int)
    df["week"] = df["week"].astype(int)
    if "weather" in df.columns:                      # one text per game; keep it small
        df["weather"] = df["weather"].astype("category")
    return df


def load_pbp_season(season: int):
    """One season of play-by-play (used by the history builder)."""
    df = _pd(_select(nfl.load_pbp([season]), PBP_COLS))
    return clean_pbp(df)


def load_all(season: int) -> Bundle:
    if nfl is None:
        raise RuntimeError("nflreadpy is not installed")
    b = Bundle()
    seasons = [season - 2, season - 1, season]

    b.pbp, err = _per_season(nfl.load_pbp, seasons, PBP_COLS)
    b.mark("play_by_play", b.pbp is not None, 0 if b.pbp is None else len(b.pbp), err)
    if b.pbp is None:
        raise RuntimeError("Play-by-play data unavailable: " + err)
    b.pbp = clean_pbp(b.pbp)

    try:
        from . import config as C
        b.schedules = _pd(nfl.load_schedules(list(range(C.TRAIN_START_SEASON - 4, season + 1))))
        b.mark("schedules", True, len(b.schedules))
    except Exception as e:  # noqa: BLE001
        b.mark("schedules", False, 0, str(e))
        raise

    b.rosters, err = _per_season(nfl.load_rosters_weekly, [season - 1, season])
    b.mark("rosters", b.rosters is not None, 0 if b.rosters is None else len(b.rosters), err)

    b.injuries, err = _per_season(nfl.load_injuries, [season])
    b.mark("injuries", b.injuries is not None, 0 if b.injuries is None else len(b.injuries),
           err or ("" if b.injuries is not None else "no report yet"))

    b.snaps, err = _per_season(nfl.load_snap_counts, [season - 1, season])
    b.mark("snap_counts", b.snaps is not None, 0 if b.snaps is None else len(b.snaps), err)

    if hasattr(nfl, "load_participation"):
        b.participation, err = _per_season(nfl.load_participation, [season - 1, season])
        ok = b.participation is not None and "defense_man_zone_type" in b.participation.columns
        b.mark("coverage_schemes", ok, 0 if b.participation is None else len(b.participation),
               err or ("" if ok else "man/zone data not published"))
        if not ok:
            b.participation = None
    else:
        b.mark("coverage_schemes", False, 0, "loader not available")
    return b
