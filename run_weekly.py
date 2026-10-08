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
from nflmodel.games import (fit_calibration, backtest_report, apply_cal, simulate, KeyNumbers,
                            fit_win_sigma, win_prob, TeamTotals)
from nflmodel import elo, stack
from nflmodel.features import game_row, history_rows, injury_effects, NO_INJ
from nflmodel.qb import qb_weeks_fast, qb_quality
from nflmodel.geo import forecast, is_indoor
from nflmodel.propsim import load_props, evaluate_props, STAT_ALIASES, stat_label
from nflmodel import oddsapi
from nflmodel.util import norm_name
from nflmodel.util import before, clean_json
from nflmodel import picks as P
from nflmodel import tracker
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
    todo = wk[wk["home_score"].isna() & wk["ko"].map(lambda k: k is None or k > now)].copy()

    # optional live odds (only active when the ODDS_API_KEY secret exists; never stops the run)
    try:
        odds = oddsapi.pull(todo, now, OUT / "odds_cache.json")
    except Exception as e:  # noqa: BLE001
        log.warning(f"live odds skipped: {str(e)[:120]}")
        odds = {"game_lines": {}, "props_df": pd.DataFrame(),
                "status": {"enabled": True, "ok": False, "message": "Live odds hit an unexpected problem and were skipped.",
                           "credits_remaining": None, "credits_used": None, "spent_this_run": 0}}
    line_meta = {}
    try:
        for c in ("spread_line", "total_line"):              # whole-number columns can't hold 47.5
            todo[c] = pd.to_numeric(todo[c], errors="coerce").astype(float)
        for gid, L in odds["game_lines"].items():
            m = todo["game_id"] == gid
            if L.get("spread_line") is not None:
                todo.loc[m, "spread_line"] = float(L["spread_line"])
            if L.get("total_line") is not None:
                todo.loc[m, "total_line"] = float(L["total_line"])
            line_meta[gid] = {"src": f"live:{L['book']}", "book": L["book_title"],
                              "ml_home": L.get("ml_home"), "ml_away": L.get("ml_away")}
    except Exception as e:  # noqa: BLE001
        log.warning(f"live lines not applied, using the free feed: {str(e)[:120]}")
        line_meta = {}
    if odds["status"].get("enabled"):
        bundle.status["live_odds"] = {"ok": bool(odds["status"].get("ok")), "rows": int(odds["status"].get("prop_rows") or 0),
                                      "note": odds["status"].get("message", "")}

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
    win_sigma = fit_win_sigma(sch)
    team_tt = TeamTotals(sch)

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
                        weather=wx or {}, inj=(ih, ia), qb_pids=(qbs[h].get("pid"), qbs[a].get("pid")))
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
        # Best plays: stricter than a lean, and only from the market-anchored engine
        play_spread = lean_side if (use_anchor and C.GAME_PLAY_SPREAD is not None and e_sp is not None
                                    and abs(e_sp) >= C.GAME_PLAY_SPREAD) else None
        play_total = lean_total if (use_anchor and C.GAME_PLAY_TOTAL is not None and e_to is not None
                                    and abs(e_to) >= C.GAME_PLAY_TOTAL) else None
        rep = (ens["report_anchored"] if use_anchor else ens["report_independent"]) if ens is not None else None
        hist_s = stack.lookup_bucket(rep, "spread_buckets", e_sp)
        hist_t = stack.lookup_bucket(rep, "total_buckets", e_to)

        notes = []
        for team in (a, h):
            q = qbs[team]
            if abs(q["adj"]) >= 0.5:
                notes.append(f"{team} QB: {q['name']} instead of {q['incumbent']} ({q['adj']:+.1f} pts)")
            try:
                st = inj.loc[inj["pid"] == q.get("pid"), "status"]
                if len(st) and str(st.iloc[0]).upper() == "QUESTIONABLE":
                    notes.append(f"Heads up: {team} QB {q['name']} is questionable. Picks assume he plays.")
            except Exception:  # noqa: BLE001
                pass
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
            "win_prob_home": fnum(win_prob(margin, win_sigma) * 100, 1),
            "margin_range": [fnum(sim["margin_p10"], 0), fnum(sim["margin_p90"], 0)],
            "model_line": line_text(h, ind_m),
            "final_line": line_text(h, margin),
            "lean_engine": "anchored" if use_anchor else "independent",
            "indep_margin": fnum(ind_m), "indep_total": fnum(ind_t),
            "market_line": line_text(h, sl) if np.isfinite(sl) else None,
            "market_spread": fnum(sl), "market_total": fnum(tl),
            "edge_spread": fnum(e_sp), "edge_total": fnum(e_to),
            "lean_side": lean_side, "lean_total": lean_total,
            "play_spread": play_spread, "play_total": play_total,
            "cover_prob_home": fnum(sim.get("cover_home", np.nan) * 100, 0),
            "over_prob": fnum(sim.get("over", np.nan) * 100, 0),
            "qb_home": qbs[h]["name"], "qb_away": qbs[a]["name"],
            "weather": weather,
            "why_margin": [{"factor": f, "pts": fnum(v)} for f, v in why_m],
            "why_total": [{"factor": f, "pts": fnum(v)} for f, v in why_t],
            "why_edge": [{"factor": f, "pts": fnum(v)} for f, v in why_edge],
            "why_edge_total": [{"factor": f, "pts": fnum(v)} for f, v in why_edge_t],
            "hist_spread": hist_s, "hist_total": hist_t,
            "line_src": line_meta.get(g["game_id"], {}).get("src", "feed"),
            "line_book": line_meta.get(g["game_id"], {}).get("book"),
            "injuries_home": ih["list"], "injuries_away": ia["list"],
            "notes": notes,
        }
        lm = line_meta.get(g["game_id"], {})
        ml_h, ml_a = lm.get("ml_home"), lm.get("ml_away")
        if ml_h is None or ml_a is None:                     # free feed fallback
            ml_h = pd.to_numeric(g.get("home_moneyline"), errors="coerce")
            ml_a = pd.to_numeric(g.get("away_moneyline"), errors="coerce")
        game["ml_home"], game["ml_away"] = fnum(ml_h, 0), fnum(ml_a, 0)
        game["win_sigma"] = round(win_sigma, 2)
        h1m = C.H1_MARGIN_SLOPE * margin                        # first half, model only
        h1t = C.H1_TOTAL_SLOPE * total + C.H1_TOTAL_INTERCEPT
        game["team_totals"] = {"home": team_tt.dist(ph), "away": team_tt.dist(pa)}
        game["h1"] = {"margin": fnum(h1m), "total": fnum(h1t), "line": line_text(h, h1m),
                      "sd_margin": C.H1_MARGIN_SD, "sd_total": C.H1_TOTAL_SD}
        game["picks"] = P.build(game, game["ml_home"], game["ml_away"])
        games.append(game)
        gp = dict(game, plays_home=feat["plays_home"], plays_away=feat["plays_away"],
                  proj_home=ph, proj_away=pa, margin=margin)
        for team, opp, side in ((h, a, "home"), (a, h, "away")):
            rws, sm = project_team(team, opp, gp, side, ctx, u, roster, inj, qbs[team])
            players += rws
            sims.update(sm)

    teams_tbl = [{k: (fnum(v, 2) if isinstance(v, (float, np.floating)) else v) for k, v in t.items()}
                 for t in ratings_table(ctx)]
    props_df, stale = tracker.filter_stale(load_props(ROOT / "data" / "props.csv"),
                                           OUT / "props_log.json", week)
    auto = odds["props_df"]
    if len(auto):
        known = {(p["game_id"], norm_name(p["name"])) for p in players}      # only players we project
        auto = auto[[(r["game_id"], norm_name(r["player"])) in known for _, r in auto.iterrows()]]
        manual_keys = {(norm_name(r.get("player")), STAT_ALIASES.get(str(r.get("stat")).strip().lower()))
                       for _, r in props_df.iterrows()} if len(props_df) else set()
        auto = auto[[(norm_name(r["player"]), r["stat"]) not in manual_keys for _, r in auto.iterrows()]]  # your rows win
        props_df = pd.concat([props_df, auto], ignore_index=True) if len(props_df) else auto.reset_index(drop=True)
    props = evaluate_props(props_df, players, sims)
    for r, why in stale:
        props["props"].append({"player": r.get("player"), "stat": r.get("stat"), "line": tracker._s(r.get("line")) or None,
                               "error": f"old line skipped ({why}). Delete it, or put this week's number in the week column"})
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
    lean_rep = (ens["report_anchored"] if (ens is not None and ens.get("anchored") and C.LEAN_ENGINE == "anchored")
                else (ens["report_independent"] if ens is not None else None))
    model_info["reality"] = stack.reality(lean_rep)
    model_info["odds"] = odds["status"]
    return wk, games, players, teams_tbl, model_info, report, scheme.ok, props


def _team_line(g, team):
    sl = g.get("market_spread")
    if sl is None:
        return None
    return -sl if team == g["home"] else sl


def _fmt_line(v):
    return "PK" if abs(v) < 0.25 else f"{v:+.1f}"


def bucket_record(report, key, lo_min):
    """Backtest record for every bucket at or above a gap size."""
    if not report or lo_min is None:
        return None
    w = l = 0
    for b in report.get(key, []):
        if b.get("lo", 0) >= lo_min - 1e-9 and b.get("record"):
            w, l = w + b["record"][0], l + b["record"][1]
    return {"record": [w, l], **(tracker.record_stats(w, l) or {"n": 0})}


def _pct_side(over_pct, lean):
    return round(over_pct if lean == "Over" else 100 - over_pct)


def build_plays(games, props, model_info):
    """The short list: what the model would actually bet right now."""
    out = []
    for g in games:
        if g.get("state") != "upcoming":
            continue
        matchup = f"{g['away']} at {g['home']}"
        if g.get("play_spread"):
            t = g["play_spread"]
            vl, ml = _team_line(g, t), (-g["margin"] if t == g["home"] else g["margin"])
            out.append({"kind": "spread", "kickoff": g.get("kickoff"), "game_id": g["game_id"], "matchup": matchup,
                        "pick": f"{t} {_fmt_line(vl)}", "detail": f"Model has {t} {_fmt_line(ml)}",
                        "gap": fnum(abs(g["edge_spread"])), "gap_unit": "pts", "book": g.get("line_book"),
                        "cover_prob": None if g.get("cover_prob_home") is None else
                        fnum(g["cover_prob_home"] if t == g["home"] else 100 - g["cover_prob_home"], 0),
                        "bet": {"kind": "spread", "game_id": g["game_id"], "side": t, "line": vl, "odds": "-110",
                                "model_pct": None if g.get("cover_prob_home") is None else
                                fnum(g["cover_prob_home"] if t == g["home"] else 100 - g["cover_prob_home"], 1)}})
        if g.get("play_total"):
            out.append({"kind": "total", "kickoff": g.get("kickoff"), "game_id": g["game_id"], "matchup": matchup,
                        "pick": f"{g['play_total']} {g['market_total']:g}", "detail": f"Model total {g['total']:.1f}",
                        "gap": fnum(abs(g["edge_total"])), "gap_unit": "pts", "book": g.get("line_book"),
                        "bet": {"kind": "total", "game_id": g["game_id"], "side": g["play_total"], "line": g["market_total"],
                                "odds": "-110", "model_pct": None if g.get("over_prob") is None else
                                fnum(g["over_prob"] if g["play_total"] == "Over" else 100 - g["over_prob"], 1)}})
    ko = {g["game_id"]: g.get("kickoff") for g in games}
    st = {g["game_id"]: g.get("state") for g in games}
    for p in props.get("props", []):
        if p.get("tier") != "play" or st.get(p.get("game_id")) != "upcoming":
            continue
        odds = p.get("over_odds") if p["lean"] == "Over" else p.get("under_odds")
        out.append({"kind": "prop", "kickoff": ko.get(p["game_id"]), "game_id": p["game_id"],
                    "matchup": f"{p['team']} vs {p['opp']}", "player": p["player"], "pos": p.get("pos"),
                    "pick": f"{p['lean']} {p['line']}", "label": p.get("label"), "odds": odds,
                    "detail": f"Model {_pct_side(p['model_over'], p['lean'])}% vs book {_pct_side(p['book_over'], p['lean'])}%",
                    "gap": fnum(abs(p["edge"])), "gap_unit": "%", "book": p.get("book"), "median": p.get("median"),
                    "bet": {"kind": "prop", "game_id": p["game_id"], "pid": p.get("pid"), "player": p["player"],
                            "stat": p.get("stat_key") or p.get("stat"), "label": p.get("label"), "side": p["lean"],
                            "line": 0.5 if (p.get("stat_key") or p.get("stat")) == "anytime_td" else float(p["line"]),
                            "odds": odds or "-110", "model_pct": _pct_side(p["model_over"], p["lean"])}})
    out.sort(key=lambda x: (x.get("kickoff") or "", x["kind"] != "spread", -(x.get("gap") or 0)))
    return out


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
    ats_play, ou_play = [], []
    pick_rows, week_rows = [], {}
    for f in sorted(HIST.glob(f"{season}_week*.json")):
        for g in json.loads(f.read_text()).get("games", []):
            if g["game_id"] not in res.index:
                continue
            r = res.loc[g["game_id"]]
            act = r["home_score"] - r["away_score"]
            tot = r["home_score"] + r["away_score"]
            try:
                gr, pk = P.grade_one(g, float(r["home_score"]), float(r["away_score"]))
                for mkt, (res_, u) in gr.items():
                    pick_rows.append((mkt, res_, u, pk[mkt].get("edge")))
                    week_rows.setdefault(int(g.get("week") or 0), []).append((mkt, res_, u, pk[mkt].get("edge")))
            except Exception as e:  # noqa: BLE001
                log.warning(f"pick grade skipped {g['game_id']}: {e}")
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
                    if g.get("play_spread"):
                        ats_play.append(int((act > sl) == (g["play_spread"] == g["home"])))
            tl = g.get("market_total")
            if tl is not None and g.get("lean_total") and tot != tl:
                ou_lean.append(int((tot > tl) == (g["lean_total"] == "Over")))
            if tl is not None and g.get("play_total") and tot != tl:
                ou_play.append(int((tot > tl) == (g["play_total"] == "Over")))
    rec = lambda x: [int(sum(x)), int(len(x) - sum(x))]
    return {"straight_up": rec(su), "ats_all": rec(ats), "ats_leans": rec(ats_lean),
            "totals_leans": rec(ou_lean), "ats_plays": rec(ats_play), "totals_plays": rec(ou_play),
            "picks": P.summarize(pick_rows),
            "picks_by_week": {str(w): P.summarize(r) for w, r in sorted(week_rows.items())},
            "model_mae": fnum(np.mean(err_m)) if err_m else None,
            "vegas_mae": fnum(np.mean(err_v)) if err_v else None}


def weekly_report(live, clv, props_path, week):
    """Report card for the last finished week plus season takeaways, in plain words."""
    try:
        weeks = sorted(int(w) for w in (live.get("picks_by_week") or {}) if int(w) < (week or 99))
        if not weeks:
            return None
        wk = weeks[-1]
        pw = live["picks_by_week"][str(wk)]
        lg = json.loads(Path(props_path).read_text()) if Path(props_path).exists() else {}
        props = [r for r in (lg.get("props") or {}).values() if r.get("result") and r["result"].get("lean_result") in ("win", "loss")]

        def rec(rows):
            w = sum(1 for r in rows if r["result"]["lean_result"] == "win")
            l = sum(1 for r in rows if r["result"]["lean_result"] == "loss")
            u = sum(float(r["result"].get("profit") or 0) for r in rows)
            return {"w": w, "l": l, "units": round(u, 2), "n": w + l}
        wk_props = [r for r in props if int(r.get("week") or 0) == wk]
        out = {"week": wk,
               "picks": {k: {kk: pw[k][kk] for kk in ("w", "l", "p", "units")} for k in ("spread", "total", "moneyline")},
               "prop_plays": rec([r for r in wk_props if r.get("tier") == "play"]),
               "props_flagged": rec(wk_props),
               "season_prop_plays": rec([r for r in props if r.get("tier") == "play"])}
        # prop types this season, by units (only with a real sample)
        types = {}
        for r in props:
            key = f"{stat_label(r.get('stat'))}, {r.get('lean')}"
            types.setdefault(key, []).append(r)
        ranked = sorted(((k, rec(v)) for k, v in types.items() if len(v) >= 12), key=lambda kv: -kv[1]["units"])
        out["best_type"] = {"name": ranked[0][0], **ranked[0][1]} if ranked and ranked[0][1]["units"] > 0 else None
        out["worst_type"] = {"name": ranked[-1][0], **ranked[-1][1]} if ranked and ranked[-1][1]["units"] < 0 else None
        # closing line value this week
        if clv and clv.get("games"):
            sp = [g.get("clv_spread") for gid, g in clv["games"].items()
                  if g.get("clv_spread") is not None and int(gid.split("_")[1]) == wk]
            out["clv_week"] = {"n": len(sp), "avg": fnum(np.mean(sp), 2) if sp else None,
                               "beat": sum(1 for v in sp if v > 0), "worse": sum(1 for v in sp if v < 0)}
        # takeaways
        t = []
        pp = out["prop_plays"]
        if pp["n"]:
            t.append(f"Prop plays went {pp['w']}-{pp['l']} ({pp['units']:+.2f} units) in week {wk}.")
        sp = out["picks"]["spread"]
        t.append(f"Every-game spread picks went {sp['w']}-{sp['l']}" + (f"-{sp['p']}" if sp["p"] else "") + ". Most are tiny gaps, so about half is expected.")
        if out.get("best_type"):
            b = out["best_type"]
            longshot = "TD" in b["name"] or (b["n"] and b["w"] / b["n"] < 0.4)
            t.append(f"Best prop type this season: {b['name']} ({b['w']}-{b['l']}, {b['units']:+.2f} units)."
                     + (" These are long-shot odds, so a few hits swing the total. Likely luck at this sample." if longshot else ""))
        if out.get("worst_type"):
            b = out["worst_type"]; t.append(f"Weakest: {b['name']} ({b['w']}-{b['l']}, {b['units']:+.2f} units). Worth avoiding until it turns.")
        cw = out.get("clv_week") or {}
        if cw.get("n"):
            moved = cw["beat"] + cw["worse"]
            t.append(f"Closing lines: {cw['beat']} picks beat the close, {cw['worse']} were worse, {cw['n'] - moved} didn't move." if moved
                     else "Closing lines didn't move on any pick, so no read on the model's sharpness yet.")
        sea = out["season_prop_plays"]
        if sea["n"] < 100:
            t.append(f"Season sample is still small ({sea['n']} prop plays). Judge the model after 100+.")
        out["takeaways"] = t
        return clean_json(out)
    except Exception as e:  # noqa: BLE001
        log.warning(f"weekly report skipped: {e}")
        return None


def season_last_week(sch, season):
    w = sch.loc[sch["season"] == season, "week"]
    return int(w.max()) if len(w) else 0


def run_tracking(bundle, games, prop_rows, season, week, now):
    """Save lines + props, grade what finished. Never allowed to break the run."""
    res = {}
    try:
        tracker.update_line_log(OUT / "line_log.json", games, now)
        res["lines"] = tracker.grade_lines(OUT / "line_log.json", bundle.schedules)
        res["clv"] = tracker.clv_report(OUT / "line_log.json", C.GAME_PLAY_SPREAD)
    except Exception as e:  # noqa: BLE001
        log.warning(f"line tracker skipped: {e}")
        res["lines"] = {"error": str(e)[:160]}
    try:
        tracker.update_props_log(OUT / "props_log.json", prop_rows, season, week, now)
        res["prop_record"] = tracker.grade_props(OUT / "props_log.json", bundle.pbp, bundle.schedules, now)
    except Exception as e:  # noqa: BLE001
        log.warning(f"prop tracker skipped: {e}")
        res["prop_record"] = {"error": str(e)[:160]}
    try:                                       # box scores the dashboard uses to grade your bets
        (OUT / "results.json").write_text(json.dumps(clean_json(tracker.build_results(bundle.pbp, bundle.schedules, season)),
                                                     separators=(",", ":"), allow_nan=False))
    except Exception as e:  # noqa: BLE001
        log.warning(f"results file skipped: {e}")
    return res


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
        payload.update(run_tracking(bundle, [], [], season, season_last_week(bundle.schedules, season), now))
        (OUT / "latest.json").write_text(json.dumps(clean_json(payload), indent=1, allow_nan=False))
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
    for g in all_games:                                  # older saved games: add or refresh picks
        if "picks" not in g or "vegas_pct" not in ((g["picks"] or {}).get("moneyline") or {"vegas_pct": 0}):
            g["picks"] = P.build(g, g.get("ml_home"), g.get("ml_away"))
    all_games.sort(key=lambda g: g.get("kickoff") or "")
    hpath.write_text(json.dumps(clean_json({"season": season, "week": week, "games": all_games,
                                            "players": all_players}), indent=1, allow_nan=False))

    payload.update(run_tracking(bundle, games, props["props"], season, week, now))
    live = grade(season, bundle.schedules)
    pr = payload.get("prop_record") or {}
    ab = model_info.get("anchored_backtest")
    payload["plays"] = build_plays(all_games, props, model_info)
    payload["plays_record"] = {"spreads": live["ats_plays"], "totals": live["totals_plays"],
                               "props": pr.get("plays") if isinstance(pr, dict) else None}
    payload["plays_rules"] = {
        "prop_play": [round(100 * C.PROP_PLAY_MIN), round(100 * C.PROP_PLAY_MAX)],
        "prop_watch_max": round(100 * C.PROP_WATCH_MAX),
        "prop_play_stats": [stat_label(x) for x in C.PROP_PLAY_STATS],
        "spread_gap": C.GAME_PLAY_SPREAD, "total_gap": C.GAME_PLAY_TOTAL,
        "spread_backtest": bucket_record(ab, "spread_buckets", C.GAME_PLAY_SPREAD),
        "total_backtest": bucket_record(ab, "total_buckets", C.GAME_PLAY_TOTAL),
    }
    payload.update({
        "model": model_info,
        "props": props,
        "scheme_enabled": scheme_ok,
        "games": all_games, "players": all_players, "teams": teams_tbl,
        "backtest": {k: (fnum(v, 2) if isinstance(v, float) else v) for k, v in report.items()},
        "live_record": live,
        "report": weekly_report(live, payload.get("clv"), OUT / "props_log.json", week),
        "settings": {"lean_engine": model_info["lean_engine"],
                     "lean_spread": C.ANCHOR_LEAN_SPREAD if model_info["lean_engine"] == "anchored" else C.LEAN_SPREAD_EDGE,
                     "lean_total": C.ANCHOR_LEAN_TOTAL if model_info["lean_engine"] == "anchored" else C.LEAN_TOTAL_EDGE},
    })
    (OUT / "latest.json").write_text(json.dumps(clean_json(payload), separators=(",", ":"), default=str, allow_nan=False))
    log.info(f"wrote {len(games)} games, {len(players)} player projections for week {week}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        log.exception("run failed")
        sys.exit(1)
