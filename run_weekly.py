"""
Weekly run. GitHub does this automatically on a schedule.
Output: docs/data/latest.json (the dashboard reads it) + a history file per week.
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from nflmodel import config as C
from nflmodel import data as D
from nflmodel.ratings import build_context, ratings_table
from nflmodel.games import (fit_calibration, backtest_report, apply_cal, simulate, KeyNumbers)
from nflmodel import elo, stack
from nflmodel.features import game_row, history_rows, injury_effects, NO_INJ
from nflmodel.qb import qb_weeks_fast, qb_quality
from nflmodel.geo import forecast, is_indoor
from nflmodel.propsim import load_props, evaluate_props
from nflmodel.util import before
from nflmodel import usage as U
from nflmodel.availability import current_roster, load_overrides, injury_table, recently_out_ids
from nflmodel.qb import expected_qbs
from nflmodel.adjust import starters_from_snaps, injury_points, Scheme
from nflmodel.players import project_team
from nflmodel.util import fnum

ROOT = Path(__file__).parent
OUT = ROOT / "docs" / "data"
HIST = OUT / "history"
ET = ZoneInfo("America/New_York")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("nflmodel")


def clean_json(o):
    """Browsers can't read NaN in JSON, so turn it into null."""
    if isinstance(o, dict):
        return {k: clean_json(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean_json(v) for v in o]
    if isinstance(o, (float, np.floating)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.integer):
        return int(o)
    return o


def guess_season(now: datetime) -> int:
    return now.year if now.month >= 3 else now.year - 1


def kickoff(row) -> datetime | None:
    try:
        t = str(row.get("gametime") or "13:00")
        return datetime.strptime(f"{row['gameday']} {t}", "%Y-%m-%d %H:%M").replace(tzinfo=ET)
    except Exception:  # noqa: BLE001
        return None


def pick_week(sch: pd.DataFrame, season: int, now: datetime) -> int | None:
    s = sch[sch["season"] == season].copy()
    s["ko"] = s.apply(kickoff, axis=1)
    upcoming = s[s["home_score"].isna() & s["ko"].map(lambda k: k is None or k > now)]
    return int(upcoming["week"].min()) if len(upcoming) else None


def line_text(team, spread_for_team):
    if spread_for_team is None or not np.isfinite(spread_for_team):
        return None
    v = -spread_for_team
    return f"{team} {'PK' if abs(v) < 0.25 else f'{v:+.1f}'}"


def load_history_rows(pbp, sch, elo_pre, season, week, injuries=None, snaps=None):
    """Deep history from the trainer (data/training_rows.csv) + recent games built fresh."""
    path = ROOT / "data" / "training_rows.csv"
    hist = pd.read_csv(path) if path.exists() else pd.DataFrame()
    have = set(hist["season"].unique()) if len(hist) else set()
    fresh_seasons = [s for s in (season - 1, season) if s not in have or s == season]
    hist = hist[~hist["season"].isin(fresh_seasons)] if len(hist) else hist
    log.info(f"history file: {len(hist)} games; building fresh rows for {fresh_seasons}")
    fresh = history_rows(pbp, sch, elo_pre, fresh_seasons, max_week_in_last=week,
                         injuries=injuries, snaps=snaps)
    return pd.concat([hist, fresh], ignore_index=True), len(hist) > 0


def build_games(bundle, season, week, now):
    sch = bundle.schedules
    wk = sch[(sch["season"] == season) & (sch["week"] == week)].copy()
    wk["ko"] = wk.apply(kickoff, axis=1)
    todo = wk[wk["home_score"].isna() & wk["ko"].map(lambda k: k is None or k > now)]

    log.info("building ratings")
    ctx = build_context(bundle.pbp, sch, season, week)
    elo_pre, _ = elo.compute(sch)
    rows, deep = load_history_rows(bundle.pbp, sch, elo_pre, season, week,
                                   bundle.injuries, bundle.snaps)
    ens = stack.build(rows)
    inj_learned = ens is not None and ens["injury_coverage"] >= 0.3
    cal = fit_calibration(rows) if ens is None else None
    report = backtest_report(rows[rows["season"] >= season - 1].copy()) if len(rows) else {"games": 0}
    keynum = KeyNumbers(sch)

    u = U.build(bundle.pbp, season, week)
    roster = current_roster(bundle.rosters, season, week)
    overrides = load_overrides(ROOT / "data" / "overrides.csv")
    inj = injury_table(bundle.injuries, roster, overrides, season, week)
    teams = sorted(set(todo["home_team"]) | set(todo["away_team"]))
    qbs = expected_qbs(teams, u, roster, inj, overrides,
                       recently_out_ids(bundle.injuries, season, week), season, week, ctx)
    starters = starters_from_snaps(bundle.snaps, season, week)
    injpts = injury_points(inj, u["usage"], starters)
    scheme = Scheme(bundle.participation, bundle.pbp, season, week)
    qw = qb_weeks_fast(before(bundle.pbp, season, week), season, week)
    qual = qb_quality(qw, season)

    games, players, sims = [], [], {}
    for i, (_, g) in enumerate(todo.iterrows()):
        h, a = g["home_team"], g["away_team"]
        wx = None if is_indoor(g) else forecast(h, g["ko"])
        ih, ia = injpts.get(h, NO_INJ), injpts.get(a, NO_INJ)
        feat = game_row(ctx, g, elo_pre, qual, qw, starters=(qbs[h]["adj"], qbs[a]["adj"]),
                        weather=wx or {}, inj=(ih, ia))
        fdf = pd.DataFrame([feat])
        sl = pd.to_numeric(g.get("spread_line"), errors="coerce")
        tl = pd.to_numeric(g.get("total_line"), errors="coerce")
        has_lines = bool(np.isfinite(sl) and np.isfinite(tl))

        # --- engine 1: independent (football data only) ---
        why_m, why_t, why_edge, why_edge_t = [], [], [], []
        if ens is not None:
            mfin, mlin = ens["ind_margin"].predict(fdf)
            tfin, tlin = ens["ind_total"].predict(fdf)
            ind_m, ind_t = float(mfin[0]), float(tfin[0])
            why_m = ens["ind_margin"].drivers(feat, ind_m, float(mlin[0]))
            why_t = ens["ind_total"].drivers(feat, ind_t, float(tlin[0]))
        else:
            ind_m, ind_t = apply_cal(feat["raw_margin"], feat["raw_total"], feat["hf"], feat["rest"], cal)
            ind_m += feat["qb_diff"]
            ind_t += feat["qb_sum"]

        # things history can't teach: coverage data always; injuries only if not learned
        dh, da, _ = injury_effects(ih, ia) if not inj_learned else (0.0, 0.0, 0)
        sch_h = scheme.points(h, a, feat["plays_home"] * ctx.lg_pass_rate)
        sch_a = scheme.points(a, h, feat["plays_away"] * ctx.lg_pass_rate)
        extra_m, extra_t = (dh + sch_h) - (da + sch_a), (dh + sch_h) + (da + sch_a)
        ind_m, ind_t = ind_m + extra_m, ind_t + extra_t

        # --- engine 2: anchored (starts from the Vegas line) ---
        anc_m = anc_t = None
        if ens is not None and ens.get("anchored") and has_lines:
            fdf["spread_line"], fdf["total_line"] = sl, tl
            afin, alin = ens["anc_margin"].predict(fdf)
            tfin2, tlin2 = ens["anc_total"].predict(fdf)
            anc_m, anc_t = float(afin[0]) + extra_m, float(tfin2[0]) + extra_t
            why_edge = ens["anc_margin"].drivers(feat, float(afin[0]), float(alin[0]))
            why_edge_t = ens["anc_total"].drivers(feat, float(tfin2[0]), float(tlin2[0]))

        use_anchor = anc_m is not None and C.LEAN_ENGINE == "anchored"
        margin, total = (anc_m, anc_t) if anc_m is not None else (ind_m, ind_t)
        lean_m, lean_t_pred = (anc_m, anc_t) if use_anchor else (ind_m, ind_t)
        th_s, th_t = stack.lean_thresholds("anchored" if use_anchor else "independent")

        ph, pa = (total + margin) / 2, (total - margin) / 2
        slv = sl if np.isfinite(sl) else None
        tlv = tl if np.isfinite(tl) else None
        sim = keynum.probs(margin, total, slv, tlv) or simulate(ph, pa, slv, tlv, seed=i)

        e_sp = lean_m - sl if np.isfinite(sl) else None
        e_to = lean_t_pred - tl if np.isfinite(tl) else None
        lean_side = (h if e_sp > 0 else a) if e_sp is not None and abs(e_sp) >= th_s else None
        lean_total = ("Over" if e_to > 0 else "Under") if e_to is not None and abs(e_to) >= th_t else None

        notes = []
        for team in (a, h):
            q = qbs[team]
            if abs(q["adj"]) >= 0.5:
                notes.append(f"{team} QB: {q['name']} instead of {q['incumbent']} ({q['adj']:+.1f} pts)")
        weather = None
        if is_indoor(g):
            weather = "Indoors"
        elif wx:
            weather = f"{wx['temp']:.0f}°F, wind {wx['wind']:.0f} mph" + (
                f", {wx['precip']:.0f}% rain" if wx.get("precip") is not None else "")
        game = {
            "game_id": g["game_id"], "week": int(week), "state": "upcoming",
            "kickoff": g["ko"].isoformat() if g["ko"] else None,
            "away": a, "home": h, "neutral": feat["hf"] == 0,
            "proj_home": fnum(ph), "proj_away": fnum(pa),
            "margin": fnum(margin), "total": fnum(total),
            "win_prob_home": fnum(sim["win_home"] * 100, 0),
            "margin_range": [fnum(sim["margin_p10"], 0), fnum(sim["margin_p90"], 0)],
            "model_line": line_text(h, ind_m),
            "final_line": line_text(h, margin),
            "lean_engine": "anchored" if use_anchor else "independent",
            "indep_margin": fnum(ind_m), "indep_total": fnum(ind_t),
            "market_line": line_text(h, sl) if np.isfinite(sl) else None,
            "market_spread": fnum(sl), "market_total": fnum(tl),
            "edge_spread": fnum(e_sp), "edge_total": fnum(e_to),
            "lean_side": lean_side, "lean_total": lean_total,
            "cover_prob_home": fnum(sim.get("cover_home", np.nan) * 100, 0),
            "over_prob": fnum(sim.get("over", np.nan) * 100, 0),
            "qb_home": qbs[h]["name"], "qb_away": qbs[a]["name"],
            "weather": weather,
            "why_margin": [{"factor": f, "pts": fnum(v)} for f, v in why_m],
            "why_total": [{"factor": f, "pts": fnum(v)} for f, v in why_t],
            "why_edge": [{"factor": f, "pts": fnum(v)} for f, v in why_edge],
            "why_edge_total": [{"factor": f, "pts": fnum(v)} for f, v in why_edge_t],
            "injuries_home": ih["list"], "injuries_away": ia["list"],
            "notes": notes,
        }
        games.append(game)
        gp = dict(game, plays_home=feat["plays_home"], plays_away=feat["plays_away"],
                  proj_home=ph, proj_away=pa, margin=margin)
        for team, opp, side in ((h, a, "home"), (a, h, "away")):
            rws, sm = project_team(team, opp, gp, side, ctx, u, roster, inj, qbs[team])
            players += rws
            sims.update(sm)

    teams_tbl = [{k: (fnum(v, 2) if isinstance(v, (float, np.floating)) else v) for k, v in t.items()}
                 for t in ratings_table(ctx)]
    props = evaluate_props(load_props(ROOT / "data" / "props.csv"), players, sims)
    model_info = {
        "engine": "two engines" if ens is not None else "simple calibration",
        "lean_engine": C.LEAN_ENGINE if (ens is not None and ens.get("anchored")) else "independent",
        "history_games": int(rows["actual_margin"].notna().sum()) if len(rows) else 0,
        "deep_history": deep,
        "seasons": ens["seasons"] if ens else [],
        "injury_coverage": fnum(ens["injury_coverage"] * 100, 0) if ens else 0,
        "injuries_learned": inj_learned,
        "deep_backtest": ens["report_independent"] if ens else None,
        "anchored_backtest": ens["report_anchored"] if ens else None,
        "weights_margin": ens["ind_margin"].weights() if ens else [],
        "weights_total": ens["ind_total"].weights() if ens else [],
        "weights_edge": ens["anc_margin"].weights() if ens and ens.get("anchored") else [],
        "calibration": {k: fnum(v, 3) for k, v in cal.items()} if cal else None,
    }
    return wk, games, players, teams_tbl, model_info, report, scheme.ok, props


def merge_history(path: Path, games, players):
    """Keep predictions for games that already kicked off (locked picks)."""
    old = json.loads(path.read_text()) if path.exists() else {"games": [], "players": []}
    new_ids = {g["game_id"] for g in games}
    kept_g = [g for g in old.get("games", []) if g["game_id"] not in new_ids]
    kept_p = [p for p in old.get("players", []) if p["game_id"] not in new_ids]
    return kept_g + games, kept_p + players


def grade(season, sch) -> dict:
    """Live record of the picks this model actually published."""
    res = sch[(sch["season"] == season) & sch["home_score"].notna()].set_index("game_id")
    su, ats, ats_lean, ou_lean, err_m, err_v = [], [], [], [], [], []
    for f in sorted(HIST.glob(f"{season}_week*.json")):
        for g in json.loads(f.read_text()).get("games", []):
            if g["game_id"] not in res.index:
                continue
            r = res.loc[g["game_id"]]
            act = r["home_score"] - r["away_score"]
            tot = r["home_score"] + r["away_score"]
            if act != 0:
                su.append(int((g["margin"] > 0) == (act > 0)))
            err_m.append(abs(g["margin"] - act))
            sl = g.get("market_spread")
            if sl is not None:
                err_v.append(abs(sl - act))
                if act != sl:
                    hit = int((act > sl) == (g["margin"] > sl))
                    ats.append(hit)
                    if g.get("lean_side"):
                        ats_lean.append(hit)
            tl = g.get("market_total")
            if tl is not None and g.get("lean_total") and tot != tl:
                ou_lean.append(int((tot > tl) == (g["lean_total"] == "Over")))
    rec = lambda x: [int(sum(x)), int(len(x) - sum(x))]
    return {"straight_up": rec(su), "ats_all": rec(ats), "ats_leans": rec(ats_lean),
            "totals_leans": rec(ou_lean),
            "model_mae": fnum(np.mean(err_m)) if err_m else None,
            "vegas_mae": fnum(np.mean(err_v)) if err_v else None}


def main():
    now = datetime.now(timezone.utc)
    if os.environ.get("NOW"):  # testing / replaying a past week
        now = datetime.fromisoformat(os.environ["NOW"]).astimezone(timezone.utc)
    season = C.SEASON or guess_season(now)
    log.info(f"season {season}")
    bundle = D.load_all(season)
    week = C.WEEK or pick_week(bundle.schedules, season, now)
    OUT.mkdir(parents=True, exist_ok=True)
    HIST.mkdir(parents=True, exist_ok=True)

    payload = {"generated_at": now.isoformat(), "season": season, "week": week,
               "data_status": bundle.status}
    if week is None:
        payload["message"] = "No upcoming games found. The season may be over."
        (OUT / "latest.json").write_text(json.dumps(payload, indent=1))
        log.info("no upcoming games")
        return

    wk, games, players, teams_tbl, model_info, report, scheme_ok, props = build_games(bundle, season, week, now)
    hpath = HIST / f"{season}_week{week:02d}.json"
    all_games, all_players = merge_history(hpath, games, players)

    # attach finals to locked games
    finals = wk.set_index("game_id")
    for g in all_games:
        if g["game_id"] in finals.index and g["game_id"] not in {x["game_id"] for x in games}:
            r = finals.loc[g["game_id"]]
            g["state"] = "final" if pd.notna(r["home_score"]) else "locked"
            if pd.notna(r["home_score"]):
                g["final_home"], g["final_away"] = int(r["home_score"]), int(r["away_score"])
    all_games.sort(key=lambda g: g.get("kickoff") or "")
    hpath.write_text(json.dumps(clean_json({"season": season, "week": week, "games": all_games,
                                            "players": all_players}), indent=1, allow_nan=False))

    payload.update({
        "model": model_info,
        "props": props,
        "scheme_enabled": scheme_ok,
        "games": all_games, "players": all_players, "teams": teams_tbl,
        "backtest": {k: (fnum(v, 2) if isinstance(v, float) else v) for k, v in report.items()},
        "live_record": grade(season, bundle.schedules),
        "settings": {"lean_engine": model_info["lean_engine"],
                     "lean_spread": C.ANCHOR_LEAN_SPREAD if model_info["lean_engine"] == "anchored" else C.LEAN_SPREAD_EDGE,
                     "lean_total": C.ANCHOR_LEAN_TOTAL if model_info["lean_engine"] == "anchored" else C.LEAN_TOTAL_EDGE},
    })
    (OUT / "latest.json").write_text(json.dumps(clean_json(payload), indent=1, default=str, allow_nan=False))
    log.info(f"wrote {len(games)} games, {len(players)} player projections for week {week}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        log.exception("run failed")
        sys.exit(1)
