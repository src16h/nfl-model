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
from .geo import travel, kickoff_hour_et, is_indoor, weather_features, precip_from_text
from .ratings import is_turf
from . import config as C
from .util import before

log = logging.getLogger("nflmodel")

BASE_MARGIN_FEATS = ["raw_margin", "hf", "elo_diff", "qb_diff", "rest", "tz_shift",
                     "west_early", "dist", "div_x_margin", "prime_hf", "pressure_diff", "inj_margin"]
BASE_TOTAL_FEATS = ["raw_total", "plays_total", "dome", "wind10", "cold", "prime", "div", "qb_sum", "inj_total"]
# v8 context features: switched on in config.py only after passing the backtest
MARGIN_FEATS = BASE_MARGIN_FEATS + [f for f in getattr(C, "EXTRA_MARGIN_FEATS", []) if f not in BASE_MARGIN_FEATS]
TOTAL_FEATS = BASE_TOTAL_FEATS + [f for f in getattr(C, "EXTRA_TOTAL_FEATS", []) if f not in BASE_TOTAL_FEATS]
# market-anchored versions also see the Vegas number
ANCHOR_MARGIN_FEATS = BASE_MARGIN_FEATS + list(getattr(C, "EXTRA_ANCHOR_MARGIN_FEATS", [])) + ["spread_line"]
ANCHOR_TOTAL_FEATS = BASE_TOTAL_FEATS + list(getattr(C, "EXTRA_ANCHOR_TOTAL_FEATS", [])) + ["total_line"]
NO_INJ = {"off": 0.0, "def": 0.0, "list": []}
LABELS = {
    "raw_margin": "Team strength (EPA ratings)", "hf": "Home field", "elo_diff": "Elo history",
    "qb_diff": "QB situation", "rest": "Rest", "tz_shift": "Travel east/west",
    "west_early": "Body clock (early kickoff)", "dist": "Travel distance",
    "div_x_margin": "Division familiarity", "prime_hf": "Primetime home edge",
    "pressure_diff": "Pass rush vs protection",
    "raw_total": "Offense/defense quality", "plays_total": "Pace", "dome": "Indoors",
    "wind10": "Wind", "cold": "Cold", "prime": "Primetime", "div": "Division game",
    "qb_sum": "QB changes", "inj_margin": "Injuries (non-QB)", "inj_total": "Injuries (non-QB)",
    "spread_line": "Vegas line", "total_line": "Vegas total",
    "sr_diff": "Success rate matchup", "sr_sum": "Success rate (both offenses)",
    "cpoe_diff": "QB accuracy (CPOE)", "cpoe_sum": "QB accuracy (both QBs)",
    "heat": "Heat", "precip": "Rain or snow", "turf": "Artificial turf",
    "surface_switch": "Road team on unfamiliar surface",
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


def injury_effects(ih: dict, ia: dict) -> tuple[float, float, float]:
    """Points each side loses to non-QB injuries -> (home change, away change)."""
    dh = -ih["off"] + ia["def"]
    da = -ia["off"] + ih["def"]
    return dh, da, 1.0 if (ih["off"] or ih["def"] or ia["off"] or ia["def"]) else 0.0


def game_row(ctx, g, elo_pre: dict, qual, qw, starters=None, weather=None,
             inj=None, qb_pids=None) -> dict:
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
        pid_h, pid_a = sh or ih, sa or ia
    else:
        qb_h, qb_a = starters
        pid_h, pid_a = qb_pids if qb_pids is not None else (incumbent(qw, h), incumbent(qw, a))

    # success rate matchup (opponent-adjusted, in percentage points)
    sr = ctx.sr
    if sr is not None:
        so, sd = sr["off"], sr["def"]
        h_sr = so.get(h, 0.0) + sd.get(a, 0.0)
        a_sr = so.get(a, 0.0) + sd.get(h, 0.0)
        sr_diff, sr_sum = (h_sr - a_sr) * 100, (h_sr + a_sr) * 100
    else:
        sr_diff = sr_sum = 0.0
    # starting QB accuracy (completion % over expected)
    cp = ctx.qb_cpoe if ctx.qb_cpoe is not None else pd.Series(dtype=float)
    c_h, c_a = float(cp.get(pid_h, 0.0) or 0.0), float(cp.get(pid_a, 0.0) or 0.0)
    # playing surface
    th = ctx.turf_home if ctx.turf_home is not None else pd.Series(dtype=float)
    turf = is_turf(g.get("surface"))
    if turf is None:
        turf = th.get(h)
    turf = float(turf) if turf is not None and pd.notna(turf) else 0.0
    away_home = th.get(a)
    switch = float(away_home is not None and pd.notna(away_home) and away_home != turf)

    lp = ctx.lg_press
    po, pd_ = ctx.press_off, ctx.press_def
    home_rush = (pd_.get(h, lp) - lp) + (po.get(a, lp) - lp)
    away_rush = (pd_.get(a, lp) - lp) + (po.get(h, lp) - lp)

    tr = travel(h, a, hf == 0, ko)
    indoor = is_indoor(g)
    if weather is None:
        wf = weather_features(g.get("temp"), g.get("wind"), indoor, g.get("precip"))
    else:
        pp = weather.get("precip")
        wf = weather_features(weather.get("temp"), weather.get("wind"), indoor,
                              None if pp is None else float(pp) / 100)
    ih, ia = inj if inj is not None else (NO_INJ, NO_INJ)
    dh, da, _ = injury_effects(ih, ia)
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
        "inj_margin": dh - da, "inj_total": dh + da, "inj_known": float(inj is not None),
        "div": div, "prime": prime, "prime_hf": prime * hf, "div_x_margin": div * r["raw_margin"],
        "sr_diff": sr_diff, "sr_sum": sr_sum, "cpoe_diff": c_h - c_a, "cpoe_sum": c_h + c_a,
        "turf": turf, "surface_switch": switch,
        **tr, **wf,
        "spread_line": pd.to_numeric(g.get("spread_line"), errors="coerce"),
        "total_line": pd.to_numeric(g.get("total_line"), errors="coerce"),
    }
    if pd.notna(g.get("home_score")):
        row["actual_margin"] = float(g["home_score"] - g["away_score"])
        row["actual_total"] = float(g["home_score"] + g["away_score"])
    return row


def history_rows(pbp, schedules, elo_pre, seasons, max_week_in_last=None,
                 injuries=None, snaps=None) -> pd.DataFrame:
    """Walk-forward rows: each game built only from data before it.
    If injury reports are given, each week's non-QB injuries become features too."""
    from . import usage as U
    from .availability import injury_table, load_overrides
    from .adjust import starters_from_snaps, injury_points

    empty_ov = pd.DataFrame(columns=["team", "player", "status", "note", "nname"])
    wet = {}
    if "weather" in pbp.columns:
        wt = pbp.groupby("game_id", observed=True)["weather"].first()
        wet = {k: precip_from_text(v) for k, v in wt.items()}
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
        injpts = None
        if injuries is not None and len(injuries) and (injuries["season"] == s).any():
            try:
                inj = injury_table(injuries, None, empty_ov, int(s), int(wk))
                if len(inj):
                    use = U.build(pbp, int(s), int(wk))["usage"]
                    injpts = injury_points(inj, use, starters_from_snaps(snaps, int(s), int(wk)))
            except Exception as e:  # noqa: BLE001
                log.warning(f"injuries {s} wk{wk} skipped: {str(e)[:100]}")
        for _, g in games.iterrows():
            inj = None
            if injpts is not None:
                inj = (injpts.get(g["home_team"], NO_INJ), injpts.get(g["away_team"], NO_INJ))
            g = g.copy()
            g["precip"] = wet.get(g["game_id"], 0.0)
            rows.append(game_row(ctx, g, elo_pre, qual, qw, inj=inj))
    return pd.DataFrame(rows)
