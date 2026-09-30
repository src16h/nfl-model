"""
Turns each game into a row of numbers (features) the ensemble learns from.
The exact same function is used for past games (training) and this week's
games (predicting), so the model is always judged on what it will actually see.
"""
import logging
import numpy as np
import pandas as pd

from .ratings import build_context
from .games import raw_game, home_field, rest_adj
from .qb import qb_weeks_fast, qb_quality, incumbent, adj_value
from .geo import travel, kickoff_hour_et, is_indoor, weather_features
from .util import before

log = logging.getLogger("nflmodel")

MARGIN_FEATS = ["raw_margin", "hf", "elo_diff", "qb_diff", "rest", "tz_shift",
                "west_early", "dist", "div_x_margin", "prime_hf", "pressure_diff"]
TOTAL_FEATS = ["raw_total", "plays_total", "dome", "wind10", "cold", "prime", "div", "qb_sum"]
LABELS = {
    "raw_margin": "Team strength (EPA ratings)", "hf": "Home field", "elo_diff": "Elo history",
    "qb_diff": "QB situation", "rest": "Rest", "tz_shift": "Travel east/west",
    "west_early": "Body clock (early kickoff)", "dist": "Travel distance",
    "div_x_margin": "Division familiarity", "prime_hf": "Primetime home edge",
    "pressure_diff": "Pass rush vs protection",
    "raw_total": "Offense/defense quality", "plays_total": "Pace", "dome": "Indoors",
    "wind10": "Wind", "cold": "Cold", "prime": "Primetime", "div": "Division game",
    "qb_sum": "QB changes",
}


BINARY_LABELS = {
    "dome": ("Outdoors", "Indoors"), "div": ("Non-division game", "Division game"),
    "prime": ("Daytime kickoff", "Primetime"), "prime_hf": ("Daytime kickoff", "Primetime home edge"),
    "west_early": ("Normal body clock", "Body clock (early kickoff)"),
}


def label(feat, value):
    if feat in BINARY_LABELS:
        return BINARY_LABELS[feat][1 if value else 0]
    return LABELS.get(feat, feat)


def game_row(ctx, g, elo_pre: dict, qual, qw, starters=None, weather=None) -> dict:
    """starters: (home_qb_pid, away_qb_pid) or None to use schedule / incumbent.
    weather: dict with temp/wind or None to use schedule columns."""
    h, a = g["home_team"], g["away_team"]
    r = raw_game(ctx, g)
    hf, rest = home_field(g), rest_adj(g)
    ko = kickoff_hour_et(g)
    dropbacks = ctx.lg_plays * ctx.lg_pass_rate

    if starters is None:
        sh = g.get("home_qb_id") if pd.notna(g.get("home_qb_id", np.nan)) else None
        sa = g.get("away_qb_id") if pd.notna(g.get("away_qb_id", np.nan)) else None
        ih, ia = incumbent(qw, h), incumbent(qw, a)
        qb_h = adj_value(qual, sh or ih, ih, dropbacks)
        qb_a = adj_value(qual, sa or ia, ia, dropbacks)
    else:
        qb_h, qb_a = starters

    lp = ctx.lg_press
    po, pd_ = ctx.press_off, ctx.press_def
    home_rush = (pd_.get(h, lp) - lp) + (po.get(a, lp) - lp)
    away_rush = (pd_.get(a, lp) - lp) + (po.get(h, lp) - lp)

    tr = travel(h, a, hf == 0, ko)
    indoor = is_indoor(g)
    if weather is None:
        wf = weather_features(g.get("temp"), g.get("wind"), indoor)
    else:
        wf = weather_features(weather.get("temp"), weather.get("wind"), indoor)
    div = float(g.get("div_game") == 1 or g.get("div_game") is True)
    prime = float(ko >= 19)

    row = {
        "game_id": g["game_id"], "season": int(g["season"]), "week": int(g["week"]),
        "home": h, "away": a,
        "raw_margin": r["raw_margin"], "raw_total": r["raw_total"],
        "plays_home": r["plays_home"], "plays_away": r["plays_away"],
        "plays_total": r["plays_home"] + r["plays_away"],
        "hf": float(hf), "rest": rest, "elo_diff": elo_pre.get(g["game_id"], 0.0),
        "qb_home": qb_h, "qb_away": qb_a, "qb_diff": qb_h - qb_a, "qb_sum": qb_h + qb_a,
        "pressure_diff": (home_rush - away_rush) * 100,
        "div": div, "prime": prime, "prime_hf": prime * hf, "div_x_margin": div * r["raw_margin"],
        **tr, **wf,
        "spread_line": pd.to_numeric(g.get("spread_line"), errors="coerce"),
        "total_line": pd.to_numeric(g.get("total_line"), errors="coerce"),
    }
    if pd.notna(g.get("home_score")):
        row["actual_margin"] = float(g["home_score"] - g["away_score"])
        row["actual_total"] = float(g["home_score"] + g["away_score"])
    return row


def history_rows(pbp, schedules, elo_pre, seasons, max_week_in_last=None) -> pd.DataFrame:
    """Walk-forward rows: each game built only from data before it."""
    sch = schedules[schedules["home_score"].notna() & schedules["season"].isin(seasons)]
    rows = []
    for (s, wk), games in sch.groupby(["season", "week"]):
        if max_week_in_last is not None and s == max(seasons) and wk >= max_week_in_last:
            continue
        pb = before(pbp, int(s), int(wk))
        if not len(pb) or pb["season"].min() > s - 1 and wk <= 1:
            continue
        try:
            ctx = build_context(pbp, schedules, int(s), int(wk))
            qw = qb_weeks_fast(pb, int(s), int(wk))
            qual = qb_quality(qw, int(s))
        except Exception as e:  # noqa: BLE001
            log.warning(f"history {s} wk{wk} skipped: {str(e)[:100]}")
            continue
        for _, g in games.iterrows():
            rows.append(game_row(ctx, g, elo_pre, qual, qw))
    return pd.DataFrame(rows)
