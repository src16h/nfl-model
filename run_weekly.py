"""
Weekly run. GitHub does this automatically on a schedule.
Output: docs/data/latest.json (the dashboard reads it) + a history file per week.
"""
import base64
import json
import logging
import zlib
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
from nflmodel import teasers as TZ
from nflmodel.games import (fit_calibration, backtest_report, apply_cal, simulate, KeyNumbers,
                            fit_win_sigma, win_prob, TeamTotals)
from nflmodel import elo, stack
from nflmodel.features import game_row, history_rows, injury_effects, NO_INJ
from nflmodel.qb import qb_weeks_fast, qb_quality
from nflmodel.geo import forecast, is_indoor
import betrules as BR
import altlines as AL
import gates as GT
from nflmodel.propsim import load_props, evaluate_props, prop_bias, STAT_ALIASES, stat_label, game_shocks, team_points
from nflmodel import oddsapi
from nflmodel.util import norm_name
from nflmodel.util import before, clean_json
from nflmodel import picks as P
from nflmodel import tracker
from nflmodel import usage as U
from nflmodel.availability import current_roster, load_overrides, injury_table, recently_out_ids
from nflmodel.qb import expected_qbs
from nflmodel.adjust import starters_from_snaps, injury_points, Scheme
from nflmodel import dvp as DV
from nflmodel import matchups as MU
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


def charting_extras(bundle, inj, season, week):
    """Free charting data for props: PFR coverage (who is missing from each secondary) and FTN
    interception-worthy throws. Returns ({'cov': {team: mult}, 'int': {qb: rate}}, notes by defense)."""
    mx, notes = {}, {}
    try:
        if C.COVERAGE_ON and bundle.pfr_def is not None:
            cov = MU.Coverage(bundle.pfr_def, season, week)
            if cov.pfr_ok and bundle.rosters is not None:
                r = bundle.rosters.copy()
                r["week"] = pd.to_numeric(r.get("week"), errors="coerce")
                cur = r[(r["season"] == season) & (r["week"] <= week)]
                cur = cur[cur["week"] == cur["week"].max()] if len(cur) else r[r["season"] == season - 1]
                to_pfr = r.dropna(subset=["gsis_id", "pfr_id"]).drop_duplicates("gsis_id", keep="last").set_index("gsis_id")["pfr_id"]
                pfr_team = cur.dropna(subset=["pfr_id"]).drop_duplicates("pfr_id", keep="last").set_index("pfr_id")["team"]
                out = inj[inj["status"].isin(["OUT", "DOUBTFUL", "IR"])] if inj is not None and len(inj) else inj
                mult = {}
                for de in cov.usual.index.get_level_values(0).unique():
                    gone = set(out.loc[out["team"] == de, "pid"].dropna().map(to_pfr).dropna()) if out is not None and len(out) else set()
                    if (cur["team"] == de).sum() >= 40:          # left the team (cut, traded) since his last game
                        gone |= {pid for pid in cov.usual.loc[de].index if pfr_team.get(pid, de) != de}
                    shift, _, names = cov.shift(de, unavailable=gone, detail=True)
                    m = float(np.clip(1 + C.COVERAGE_COEF * shift / C.PRIORS["qb_ypa"][0], 1 - C.COVERAGE_MAX, 1 + C.COVERAGE_MAX))
                    mult[de] = m
                    if abs(m - 1) >= 0.01 and names:
                        notes[de] = {"names": names, "pct": 100 * (m - 1)}
                mx["cov"] = mult
                log.info(f"coverage: {sum(abs(v - 1) >= 0.01 for v in mult.values())} defenses moved 1%+")
    except Exception as e:  # noqa: BLE001
        log.warning(f"coverage skipped: {e}")
    try:
        if C.INT_WORTHY_BLEND > 0 and bundle.ftn is not None:
            iw = MU.qb_int_worthy(bundle.pbp, bundle.ftn, season, week, C.PRIORS["qb_int"][0])
            if len(iw):
                mx["int"] = iw.to_dict()
                log.info(f"interception-worthy rates: {len(iw)} QBs")
    except Exception as e:  # noqa: BLE001
        log.warning(f"interception-worthy skipped: {e}")
    return mx, notes


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
                              "ml_home": L.get("ml_home"), "ml_away": L.get("ml_away"),
                              **{k: L.get(k) for k in ("spread_home_odds", "spread_away_odds", "over_odds", "under_odds")},
                              "sharp": L.get("sharp")}
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
    dvp = None
    if C.DVP_ON:
        try:
            dvp = DV.DvP(DV.targets_table(bundle.pbp, DV.pos_map(bundle.rosters)), season, week)
            dvp = dvp if dvp.ok else None
        except Exception as e:  # noqa: BLE001
            log.warning(f"defense vs position skipped: {e}")
    mx, cov_notes = charting_extras(bundle, inj, season, week)
    qw = qb_weeks_fast(before(bundle.pbp, season, week), season, week)
    qual = qb_quality(qw, season)

    games, players, sims = [], [], {}
    alt_inputs, alt_rows_all, conv_errs = [], [], []
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
        # Plays (Oct 20 2026): Pinnacle must call the bet book's price value at the same line, and the model must
        # agree (betrules.decide_sharp). The old 1.5-point gap rule never fired in the backtest and was priced at -110.
        lm = line_meta.get(g["game_id"], {})
        shp = lm.get("sharp") or {}
        sharp_sp = sharp_to = None
        play_spread = play_total = None
        if e_sp is not None and np.isfinite(sl):
            home_side = e_sp > 0 if abs(e_sp) >= 0.05 else sim.get("cover_home", 0.5) >= 0.5
            mp = sim.get("cover_home") if home_side else (1 - sim["cover_home"] if sim.get("cover_home") is not None else None)
            same = shp.get("spread_line") is not None and abs(shp["spread_line"] - sl) < 1e-9
            sp_conv = None
            if not same and shp.get("spread_line") is not None and shp.get("spread_home_odds") and shp.get("spread_away_odds"):
                hs_, as_ = BR.implied(shp["spread_home_odds"]), BR.implied(shp["spread_away_odds"])
                p_home = hs_ / (hs_ + as_)                      # Pinnacle's fair home cover chance at its own line
                ph_bet = keynum.shift("spread", shp["spread_line"], p_home, sl, True)
                if ph_bet is not None:
                    sp_conv = ph_bet if home_side else 1 - ph_bet
            sharp_sp = BR.decide_sharp(mp, lm.get("spread_home_odds" if home_side else "spread_away_odds"),
                                       lm.get("spread_away_odds" if home_side else "spread_home_odds"),
                                       (shp.get("spread_home_odds" if home_side else "spread_away_odds")) if same else None,
                                       (shp.get("spread_away_odds" if home_side else "spread_home_odds")) if same else None,
                                       sharp_p=sp_conv)
            if sp_conv is not None:
                sharp_sp["converted_from"] = shp["spread_line"]
            sharp_sp["side"] = h if home_side else a
            sharp_sp["odds"] = lm.get("spread_home_odds" if home_side else "spread_away_odds")
            play_spread = sharp_sp["side"] if sharp_sp["play"] else None
        if e_to is not None and np.isfinite(tl):
            over = e_to > 0 if abs(e_to) >= 0.05 else sim.get("over", 0.5) >= 0.5
            mp = sim.get("over") if over else (1 - sim["over"] if sim.get("over") is not None else None)
            same = shp.get("total_line") is not None and abs(shp["total_line"] - tl) < 1e-9
            to_conv = None
            if not same and shp.get("total_line") is not None and shp.get("over_odds") and shp.get("under_odds"):
                os_, us_ = BR.implied(shp["over_odds"]), BR.implied(shp["under_odds"])
                po_bet = keynum.shift("total", shp["total_line"], os_ / (os_ + us_), tl, True)
                if po_bet is not None:
                    to_conv = po_bet if over else 1 - po_bet
            sharp_to = BR.decide_sharp(mp, lm.get("over_odds" if over else "under_odds"), lm.get("under_odds" if over else "over_odds"),
                                       (shp.get("over_odds" if over else "under_odds")) if same else None,
                                       (shp.get("under_odds" if over else "over_odds")) if same else None,
                                       sharp_p=to_conv)
            if to_conv is not None:
                sharp_to["converted_from"] = shp["total_line"]
            sharp_to["side"] = "Over" if over else "Under"
            sharp_to["odds"] = lm.get("over_odds" if over else "under_odds")
            play_total = sharp_to["side"] if sharp_to["play"] else None
        rep = (ens["report_anchored"] if use_anchor else ens["report_independent"]) if ens is not None else None
        hist_s = stack.lookup_bucket(rep, "spread_buckets", e_sp)
        hist_t = stack.lookup_bucket(rep, "total_buckets", e_to)

        notes = []
        for de, opp_team in ((h, a), (a, h)):
            cn = cov_notes.get(de)
            if cn:
                notes.append(f"{de} secondary missing {', '.join(cn['names'][:3])}: {opp_team} passing yards {cn['pct']:+.0f}% in player props")
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
            "play_spread": play_spread, "play_total": play_total, "sharp_spread": sharp_sp, "sharp_total": sharp_to,
            "spread_odds": {"home": lm.get("spread_home_odds"), "away": lm.get("spread_away_odds")},
            "total_odds": {"over": lm.get("over_odds"), "under": lm.get("under_odds")}, "sharp_lines": shp or None,
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
        try:
            game["teaser_legs"] = TZ.game_legs(game, keynum)
        except Exception as e:  # noqa: BLE001
            log.warning(f"teaser legs skipped: {e}")
        games.append(game)
        gp = dict(game, plays_home=feat["plays_home"], plays_away=feat["plays_away"],
                  proj_home=ph, proj_away=pa, margin=margin)
        shocks, pnoise = game_shocks(zlib.crc32(f"sgp{g['game_id']}".encode()))
        side_sims = {}
        for team, opp, side in ((h, a, "home"), (a, h, "away")):
            rws, sm = project_team(team, opp, gp, side, ctx, u, roster, inj, qbs[team], shocks=shocks[side], dvp=dvp, mx=mx)
            players += rws
            sims.update(sm)
            side_sims[side] = ({pid: v for (gid, pid), v in sm.items()}, rws)
        full, tlegs = None, []
        try:
            full = {sd: team_points(side_sims[sd][0], qbs[game[sd]].get("pid"), (game.get("team_totals") or {}).get(sd), pnoise[sd])
                    for sd in ("home", "away")}
            if any(v is None for v in full.values()):
                full = None
        except Exception as e:  # noqa: BLE001
            log.warning(f"team points skipped for {g['game_id']}: {str(e)[:120]}")
        if full is not None:
            try:                                   # alt lines and team totals: the sims re-weighted to Pinnacle (altlines.py)
                mdl = AL.Dist(full["home"], full["away"])
                tg = []
                if shp.get("spread_line") is not None and shp.get("spread_home_odds") and shp.get("spread_away_odds"):
                    tg.append(({"market": "spread", "team": "home", "side": "home", "line": -float(shp["spread_line"])},
                               AL.nv(shp["spread_home_odds"], shp["spread_away_odds"])))
                if shp.get("total_line") is not None and shp.get("over_odds") and shp.get("under_odds"):
                    tg.append(({"market": "total", "team": None, "side": "over", "line": float(shp["total_line"])},
                               AL.nv(shp["over_odds"], shp["under_odds"])))
                ba = (odds.get("alt") or {}).get(g["game_id"], {})
                for k_, sides in AL.pairs([x for x in ba.get("sharp", []) if x["market"] == "team_total" and not x.get("period")]).items():
                    if "over" in sides and "under" in sides and abs(k_[2] % 1 - 0.5) < 1e-9:
                        tg.append(({"market": "team_total", "team": k_[1], "side": "over", "line": k_[2]}, AL.nv(sides["over"], sides["under"])))
                mkt, err = AL.tilt(mdl, tg) if len(tg) >= 2 else (None, None)
                game["ladder"] = AL.ladders(mdl, mkt, C.ALT_SPEC)
                game["mkt_err"] = None if err is None else fnum(100 * err, 2)
                fg = lambda rows: [x for x in rows or [] if not x.get("period")]
                h1 = lambda rows: [x for x in rows or [] if x.get("period") == "h1"]
                rws = []
                if fg(ba.get("book")):
                    rws = AL.evaluate(fg(ba["book"]), fg(ba.get("sharp")), mdl, mkt)
                if h1(ba.get("book")) and game.get("h1"):         # 1st half: the model's half projection, re-weighted to Pinnacle's half lines
                    H = game["h1"]
                    rng = np.random.default_rng(zlib.crc32(f"h1{g['game_id']}".encode()))
                    M_ = rng.normal(H["margin"], H["sd_margin"], 20000)
                    T_ = np.maximum(rng.normal(H["total"], H["sd_total"], 20000), np.abs(M_))
                    m1 = AL.Dist(np.round((T_ + M_) / 2), np.round((T_ - M_) / 2))
                    t1 = []
                    for k_, sides in AL.pairs(h1(ba.get("sharp"))).items():
                        s_ = next((x for x in ("home", "over") if x in sides and AL.OTHER[x] in sides), None)
                        if s_ and k_[0] in ("spread", "total"):
                            t1.append(({"market": k_[0], "team": "home" if k_[0] == "spread" else None, "side": s_, "line": k_[2]},
                                       AL.nv(sides[s_], sides[AL.OTHER[s_]])))
                    k1 = AL.tilt(m1, t1)[0] if t1 else None
                    rws += [{**x, "period": "h1"} for x in AL.evaluate(h1(ba["book"]), h1(ba.get("sharp")), m1, k1)]
                if rws:
                    for x in rws:
                        x.update({"game_id": g["game_id"], "label": AL.label(x, h, a), "book": ba.get("book_name"), "kickoff": game.get("kickoff")})
                    alt_rows_all.extend(rws)
                    game["alt"] = {"book": ba.get("book_name"), "markets": ba.get("markets"), "n": len(rws), "plays": [],
                                   "rows": sorted(rws, key=lambda x: -(x["ev"] if x["ev"] is not None else -99))[:12]}
                conv_errs.extend(AL.conv_check(fg(ba.get("sharp")), mkt))
                tlegs = AL.team_legs(mdl, mkt, h, a, C.ALT_LEG_SPEC, C.ALT_LEG_RANGE_TEAM) if mkt is not None else []
            except Exception as e:  # noqa: BLE001
                log.warning(f"alt lines skipped for {g['game_id']}: {str(e)[:120]}")
        alt_inputs.append((game, side_sims, tlegs))
        try:
            write_sgp(game, side_sims, qbs, pnoise, full)
        except Exception as e:  # noqa: BLE001
            log.warning(f"parlay draws skipped for {g['game_id']}: {str(e)[:120]}")

    teams_tbl = [{k: (fnum(v, 2) if isinstance(v, (float, np.floating)) else v) for k, v in t.items()}
                 for t in ratings_table(ctx)]
    if dvp is not None:
        dv = {r["team"]: r for r in dvp.table()}
        for t in teams_tbl:
            t.update({k: v for k, v in dv.get(t["team"], {}).items() if k != "team"})
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
    prop_bias_tbl, prop_real_tbl = prop_bias(OUT / "props_log.json", with_real=True)
    log.info(f"prop bias from graded results: {prop_bias_tbl}")
    log.info(f"prop calibration from graded results: {prop_real_tbl}")
    props = evaluate_props(props_df, players, sims, prop_bias_tbl, prop_real_tbl)
    # alt-line parlays: anchored to the book's main line (or the model's middle number if not posted)
    main_lines = {}
    for r in props.get("props", []):
        try:
            if r.get("pid") and not r.get("error") and r.get("line") not in (None, ""):
                main_lines[(r["pid"], r.get("stat_key") or r.get("stat"))] = float(r["line"])
        except (TypeError, ValueError):
            pass
    from nflmodel import altcal
    altcal.PLAYED = tracker.played_set(bundle.snaps)
    for game, side_sims, tlegs in alt_inputs:
        try:
            game["alt_parlay"] = build_alt_parlay(game, side_sims, main_lines)
        except Exception as e:  # noqa: BLE001
            log.warning(f"alt parlay skipped for {game['game_id']}: {str(e)[:120]}")
        try:                                       # the same search, but every ticket carries a team leg
            game["alt_mix"] = build_alt_parlay(game, side_sims, main_lines, tlegs, need_team=True) if tlegs else None
        except Exception as e:  # noqa: BLE001
            log.warning(f"team-leg parlay skipped for {game['game_id']}: {str(e)[:120]}")
    # alt-line plays: one per game, best value first, at most ALT_PLAY_CAP per kickoff date
    chosen, per_day, keep_ids = AL.best_plays(alt_rows_all, C.ALT_PER_GAME), {}, set()
    for x in sorted(chosen, key=lambda x: -x["ev"]):
        dd = str(x.get("kickoff") or "")[:10]
        if per_day.get(dd, 0) < C.ALT_PLAY_CAP:
            per_day[dd] = per_day.get(dd, 0) + 1
            keep_ids.add(id(x))
    for x in alt_rows_all:
        x["eligible"], x["play"] = x["play"], id(x) in keep_ids
    for game in games:
        if game.get("alt"):
            game["alt"]["plays"] = [x for x in alt_rows_all if x["game_id"] == game["game_id"] and x["play"]]
            game["alt"]["rows"] = sorted(game["alt"]["plays"] + [x for x in game["alt"]["rows"] if not x["play"]],
                                         key=lambda x: (not x["play"], -(x["ev"] if x["ev"] is not None else -99)))[:12]
    odds["status"]["alt_check"] = {"n": len(conv_errs), "mae": fnum(float(np.mean(np.abs(conv_errs))), 2) if conv_errs else None,
                                   "bias": fnum(float(np.mean(conv_errs)), 2) if conv_errs else None}
    log.info(f"alt lines: {len(alt_rows_all)} priced, {len(keep_ids)} plays, conversion check {odds['status']['alt_check']}")
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


SGP_DIR = OUT / "sgp"
SGP_STATS = {"QB": ["pass_yds", "pass_cmp", "pass_att", "rush_yds", "tds"],
             "RB": ["rush_yds", "carries", "rec", "rec_yds", "rush_rec_yds", "tds"],
             "WR": ["rec", "rec_yds", "rush_rec_yds", "tds"], "TE": ["rec", "rec_yds", "tds"]}


COUNT_SGP = {"pass_cmp", "pass_att", "carries", "rec", "tds"}
SGP_KEEP = {"QB": 1, "RB": 2, "WR": 4, "TE": 2}       # players per team books usually offer


def _b64(arr, small=False):
    """Compact draws: counts as 1 byte, yards and points as 2 bytes."""
    if small:
        a = np.clip(np.round(np.asarray(arr, float)), 0, 255).astype("u1")
        return "u1:" + base64.b64encode(a.tobytes()).decode()
    a = np.clip(np.round(np.asarray(arr, float)), -32768, 32767).astype("<i2")
    return "i2:" + base64.b64encode(a.tobytes()).decode()


def _half(x):
    return float(np.floor(x) + 0.5)


def lock_combos(game, side_sims, qbs, pts):
    """A standard set of correlated 2-leg parlays per team, priced from the full
    simulation and saved with the game, so the tracker can check later whether
    'more likely together' held up in real games."""
    h, a = game["home"], game["away"]
    ph, pa = pts["home"], pts["away"]
    out = []
    gt_line = game.get("market_total") if game.get("market_total") is not None else _half(np.median(ph + pa))

    def leg_hits(L):
        if L["kind"] == "tt":
            v = ph if L["team"] == h else pa
            return v > L["line"]
        if L["kind"] == "ml":
            return (ph > pa) if L["team"] == h else (pa > ph)
        if L["kind"] == "total":
            return (ph + pa) > L["line"]
        if L["kind"] == "spread":
            m = (ph - pa) if L["team"] == h else (pa - ph)
            return m + L["line"] > 0
        sims = side_sims[L["_side"]][0][L["pid"]]
        v = sims["rush_td"] + sims["rec_td"] if L["stat"] == "tds" else sims[L["stat"]]
        return v > L["line"]

    for side, team, opp in (("home", h, a), ("away", a, h)):
        sims, rows = side_sims[side]
        by = lambda pos, stat: sorted([r for r in rows if r["pos"] in pos and r["pid"] in sims and stat in sims[r["pid"]]],
                                      key=lambda r: -float(np.mean(sims[r["pid"]][stat])))
        qb = qbs[team].get("pid")
        wr = by(("WR", "TE"), "rec_yds")
        rb = by(("RB",), "rush_yds")
        P = lambda r, st: {"kind": "player", "pid": r["pid"], "name": r["name"], "stat": st, "side": "Over",
                           "line": _half(np.median(sims[r["pid"]][st])), "_side": side}
        tt = {"kind": "tt", "team": team, "side": "Over", "line": _half(np.median(pts[side]))}
        ott = {"kind": "tt", "team": opp, "side": "Over", "line": _half(np.median(pts["home" if side == "away" else "away"]))}
        win = {"kind": "ml", "team": team}
        combos = []
        if qb in sims and "pass_yds" in sims[qb]:
            qbr = {"pid": qb, "name": qbs[team].get("name")}
            qleg = P(qbr, "pass_yds")
            if wr:
                combos.append(("Team QB + WR1 overs", [qleg, P(wr[0], "rec_yds")]))
            combos.append(("Team QB over + Team team total over", [qleg, tt]))
            combos.append(("Team QB over + Opp team total over", [qleg, ott]))
            if game.get("market_spread") is not None:
                line = -game["market_spread"] if team == h else game["market_spread"]
                combos.append(("Team QB over + Team covers", [qleg, {"kind": "spread", "team": team, "line": float(line)}]))
        if rb:
            combos.append(("Team RB1 rush over + Team wins", [P(rb[0], "rush_yds"), win]))
            combos.append(("Team RB1 anytime TD + Team wins", [{"kind": "player", "pid": rb[0]["pid"], "name": rb[0]["name"],
                                                                   "stat": "tds", "side": "Over", "line": 0.5, "_side": side}, win]))
        if wr:
            combos.append(("Team WR1 over + Team team total over", [P(wr[0], "rec_yds"), tt]))
        combos.append(("Team team total over + game over", [tt, {"kind": "total", "side": "Over", "line": float(gt_line)}]))
        for tp, legs in combos:
            name = tp.replace("Team team", f"{team} team").replace("Opp team", f"{opp} team").replace("Team ", f"{team} ", 1).replace("+ Team", f"+ {team}")
            hits = [leg_hits(L) for L in legs]
            joint = float(np.mean(np.logical_and.reduce(hits)))
            indep = float(np.prod([np.mean(x) for x in hits]))
            out.append({"name": name, "type": tp.replace("Team team", "team").replace("Opp team", "opponent team").replace("Team ", "", 1).replace("+ Team", "+ team"),
                        "legs": [{k: v for k, v in L.items() if k != "_side"} for L in legs],
                        "p": round(joint * 100, 1), "pi": round(indep * 100, 1)})
    game["sgp_combos"] = out


ALT_STATS = {"QB": ["pass_yds"], "RB": ["rush_yds", "rec"], "WR": ["rec_yds", "rec"], "TE": ["rec_yds", "rec"]}
ALT_LABEL = {"pass_yds": "pass yds", "rush_yds": "rush yds", "rec_yds": "rec yds", "rec": "receptions"}


def build_alt_parlay(game, side_sims, main_lines=None, team_legs=(), need_team=False):
    """The model's alt-line parlay: 'alt down' legs (70-92% each, after calibration) from both
    teams whose combined chance lands at fair odds of +100 to +125. Leg chances are corrected
    by leg type from graded weeks (nflmodel/altcal.py: yardage tails ran thin, catches held up).
    It picks the ticket most likely to hit; how much the legs move together breaks ties."""
    from nflmodel import altcal
    cal = altcal.fit(HIST, OUT / "results.json", int(str(game["game_id"])[:4]))
    lo_o, hi_o = C.ALT_PARLAY_ODDS
    p_lo, p_hi = 100 / (hi_o + 100), 100 / (lo_o + 100)          # +125 -> 44.4%, +100 -> 50%
    cands = []
    for side in ("home", "away"):
        sims, rows = side_sims[side]
        keep = sorted([r for r in rows if r.get("markets") and r["pid"] in sims], key=lambda r: -(r.get("fpts") or 0))
        taken = {}
        for r in keep:
            if taken.get(r["pos"], 0) >= SGP_KEEP.get(r["pos"], 0):
                continue
            taken[r["pos"]] = taken.get(r["pos"], 0) + 1
            for st in ALT_STATS.get(r["pos"], []):
                arr = sims[r["pid"]].get(st)
                if arr is None:
                    continue
                book = (main_lines or {}).get((r["pid"], st))
                main = float(book) if book is not None else float(np.floor(np.median(arr)) + 0.5)
                main = float(np.floor(main) + 0.5)                      # books use .5 lines
                if main < C.ALT_MIN_MAIN[st]:
                    continue                                            # role too small for a posted prop
                step, drop = C.ALT_STEP[st], C.ALT_MAX_DROP[st]
                for k in range(1, int(drop // step) + 1):               # alt lines below the main, never past the cap
                    L = main - k * step
                    if L < C.ALT_MIN_LINE[st]:
                        break
                    hit = arr > L
                    p_raw = float(hit.mean())
                    p = altcal.adjust(cal, r["pos"], st, p_raw)
                    if C.ALT_LEG_RANGE[0] <= p <= C.ALT_LEG_RANGE[1] and p_raw > 0:
                        cands.append({"pid": r["pid"], "name": r["name"], "team": game[side], "pos": r["pos"], "stat": st,
                                      "line": L, "label": f"Over {L:g} {ALT_LABEL[st]}", "p": p, "p_raw": p_raw, "hit": hit,
                                      "main": main, "main_src": "book" if book is not None else "model"})
    # team legs (Oct 21 2026): alt spreads, totals and team totals priced from Pinnacle's lines (altlines.team_legs);
    # their hits come from the same simulated games as the player legs, so the two combine at their real correlation
    tl_c = [{**t, "pid": "T:" + t["label"], "name": "", "team": t.get("teamname"), "pos": "TEAM", "stat": "team:" + t["market"],
             "main": None, "main_src": "pinnacle"} for t in team_legs]
    n_team = len(tl_c)
    if need_team:
        if not tl_c:
            return None
        cands = tl_c + cands
    if len(cands) < 3:
        return None
    teams = {game["home"], game["away"]}
    is_team = lambda i: cands[i].get("kind") == "team"

    def joint(idx, h):
        """Sim joint chance (keeps how legs move together) with each leg's calibration applied."""
        pj = float(h.mean())
        for i in idx:
            pj *= cands[i]["p"] / cands[i]["p_raw"]
        return min(pj, min(cands[i]["p"] for i in idx))

    def search(n_legs):
        beams = [((i,), cands[i]["hit"]) for i in range(len(cands)) if not need_team or i < n_team]
        for _ in range(n_legs - 1):
            nxt = []
            for idx, h in beams:
                used = {cands[i]["pid"] for i in idx}
                qb_legs = sum(1 for i in idx if cands[i]["stat"] == "pass_yds")
                tl = [cands[i] for i in idx if is_team(i)]
                for j in range(idx[-1] + 1, len(cands)):
                    if cands[j]["pid"] in used:
                        continue
                    if is_team(j) and (len(tl) >= C.ALT_MAX_TEAM_LEGS or any(x["stat"] == cands[j]["stat"] for x in tl)):
                        continue                                    # at most 2 team legs, one per market
                    # one QB yards leg at most: the model overrates how much the two
                    # passing games move together (0.20 vs 0.06 in real games)
                    if qb_legs and cands[j]["stat"] == "pass_yds":
                        continue
                    hj = h & cands[j]["hit"]
                    pj = joint(idx + (j,), hj)
                    if pj >= p_lo:                                  # adding legs only lowers the chance
                        nxt.append((idx + (j,), hj, pj))
            # keep the most promising: most likely to hit, then legs that move together
            nxt.sort(key=lambda t: -(t[2] + 0.01 * t[2] / np.prod([cands[i]["p"] for i in t[0]])))
            beams = [(t[0], t[1]) for t in nxt[:400]]
        best = None
        for idx, h in beams:
            pj = joint(idx, h)
            cover = set()
            for i in idx:
                cover |= teams if cands[i].get("team") is None else {cands[i]["team"]}
            if not (p_lo <= pj <= p_hi) or cover != teams:
                continue
            if sum(1 for i in idx if not is_team(i) and cands[i]["stat"] != "rec") > C.ALT_MAX_YARD_LEGS:
                continue                                            # yardage legs miss more than the sims say
            if sum(1 for i in idx if cands[i]["stat"] == "rush_yds") > C.ALT_MAX_RUSH_LEGS:
                continue                                            # RB rushing misses most (82% real when the sims say 90%)
            pi = float(np.prod([cands[i]["p"] for i in idx]))
            score = pj + 0.01 * pj / pi                             # hit chance first; correlation breaks ties
            if best is None or score > best[0]:
                best = (score, idx, pj, pi)
        return best
    best = None
    for n_legs in (C.ALT_PARLAY_LEGS, C.ALT_PARLAY_LEGS - 1, C.ALT_PARLAY_LEGS + 1):
        best = search(n_legs)
        if best:
            break
    if not best:
        return None
    _, idx, pj, pi = best
    legs = [{"kind": "team", "market": cands[i]["market"], "team": cands[i]["team_side"], "side": cands[i]["side"], "line": cands[i]["line"],
             "name": "", "label": cands[i]["label"], "p": round(cands[i]["p"] * 100, 1), "p_model": round(cands[i]["p_model"] * 100, 1),
             "main_src": "pinnacle"} if is_team(i) else
            {"kind": "player", "pid": cands[i]["pid"], "name": cands[i]["name"], "team": cands[i]["team"], "pos": cands[i]["pos"],
             "stat": cands[i]["stat"], "side": "Over", "line": cands[i]["line"], "label": cands[i]["label"],
             "main": cands[i]["main"], "main_src": cands[i]["main_src"], "p": round(cands[i]["p"] * 100, 1)} for i in idx]
    legs.sort(key=lambda L: (L["kind"] != "team", L.get("team") != game["away"], -L["p"]))
    share = sum(1 for L in legs if L["kind"] != "team") / len(legs)     # the ticket correction learned on player legs
    # whole-ticket correction (Oct 20 2026): graded tickets hit 35% when the model said 47% even after the leg
    # calibration, so the ticket's chance moves toward its record on the log-odds scale, fading in with the sample
    raw = pj
    try:
        ap = (json.loads((OUT / "latest.json").read_text()).get("tracking") or {}).get("alt_parlays") or {}
        n_, m_, a_ = ap.get("n") or 0, (ap.get("model") or 0) / 100, (ap.get("actual") or 0) / 100
        if n_ >= 10 and 0 < m_ < 1 and 0 < a_ < 1:
            shift = (np.log(a_ / (1 - a_)) - np.log(m_ / (1 - m_))) * n_ / (n_ + C.ALT_TICKET_K) * share
            lg = np.log(pj / (1 - pj)) + shift
            pj = float(1 / (1 + np.exp(-lg)))
    except Exception:  # noqa: BLE001
        pass
    fair = (1 - pj) / pj * 100
    return {"legs": legs, "p": round(pj * 100, 1), "p_sim": round(raw * 100, 1), "pi": round(pi * 100, 1),
            "fair": f"+{round(fair)}" if fair >= 100 else str(round(-100 * pj / (1 - pj))),
            "note": "Only bet it if Hard Rock pays more than the fair odds"}


def write_sgp(game, side_sims, qbs, pnoise, full=None):
    """Publish SGP_DRAWS simulated games for one matchup (players + final score)."""
    K = C.SGP_DRAWS
    out = {"game_id": game["game_id"], "home": game["home"], "away": game["away"], "n": K, "players": {}}
    if full is None:
        full = {}
        for side in ("home", "away"):
            team = game[side]
            full[side] = team_points(side_sims[side][0], qbs[team].get("pid"), (game.get("team_totals") or {}).get(side), pnoise[side])
            if full[side] is None:
                return
    try:
        lock_combos(game, side_sims, qbs, full)
    except Exception as e:  # noqa: BLE001
        log.warning(f"parlay combos skipped for {game['game_id']}: {str(e)[:120]}")

    for side in ("home", "away"):
        sims, rows = side_sims[side]
        team = game[side]
        pts = full[side]
        out[f"pts_{side}"] = _b64(pts[:K], small=True)
        ranked = sorted([r for r in rows if r.get("markets") and sims.get(r["pid"]) is not None],
                        key=lambda r: -(r.get("fpts") or 0))
        keep, taken = [], {}
        for r in ranked:
            if taken.get(r["pos"], 0) < SGP_KEEP.get(r["pos"], 0):
                taken[r["pos"]] = taken.get(r["pos"], 0) + 1
                keep.append(r)
        for r in keep:
            sm = sims.get(r["pid"])
            d = dict(sm)
            d["tds"] = d["rush_td"] + d["rec_td"]
            d["rush_rec_yds"] = d["rush_yds"] + d["rec_yds"]
            stats = {s: _b64(d[s][:K], small=s in COUNT_SGP) for s in SGP_STATS.get(r["pos"], []) if s in d}
            if stats:
                out["players"][r["pid"]] = {"name": r["name"], "team": team, "pos": r["pos"], "s": stats}
    # only rewrite when the inputs really changed (keeps the repo from growing every run)
    sig = json.dumps([round(game.get("proj_home") or 0, 0), round(game.get("proj_away") or 0, 0),
                      sorted((pid, v["pos"]) for pid, v in out["players"].items())])
    out["sig"] = zlib.crc32(sig.encode())
    SGP_DIR.mkdir(parents=True, exist_ok=True)
    path = SGP_DIR / f"{game['game_id']}.json"
    if path.exists():
        try:
            if json.loads(path.read_text()).get("sig") == out["sig"]:
                return
        except Exception:  # noqa: BLE001
            pass
    path.write_text(json.dumps(out, separators=(",", ":")))


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


def _fmt_odds_s(o):
    if o is None:
        return None
    o = int(round(float(o)))
    return f"+{o}" if o > 0 else str(o)


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
            sp = g.get("sharp_spread") or {}
            odds_s = _fmt_odds_s(sp.get("odds"))
            out.append({"kind": "spread", "kickoff": g.get("kickoff"), "game_id": g["game_id"], "matchup": matchup,
                        "pick": f"{t} {_fmt_line(vl)}", "odds": odds_s,
                        "detail": f"Pinnacle {sp.get('sharp')}% vs {sp.get('book')}% at {g.get('line_book')}, {sp.get('ev'):+.1f}% value. Model has {t} {_fmt_line(ml)}"
                        if sp.get("ev") is not None else f"Model has {t} {_fmt_line(ml)}",
                        "gap": sp.get("ev"), "gap_unit": "%", "book": g.get("line_book"),
                        "cover_prob": None if g.get("cover_prob_home") is None else
                        fnum(g["cover_prob_home"] if t == g["home"] else 100 - g["cover_prob_home"], 0),
                        "bet": {"kind": "spread", "game_id": g["game_id"], "side": t, "line": vl, "odds": odds_s or "-110",
                                "model_pct": sp.get("sharp") if sp.get("sharp") is not None else (None if g.get("cover_prob_home") is None else
                                fnum(g["cover_prob_home"] if t == g["home"] else 100 - g["cover_prob_home"], 1))}})
        if g.get("play_total"):
            st = g.get("sharp_total") or {}
            odds_t = _fmt_odds_s(st.get("odds"))
            out.append({"kind": "total", "kickoff": g.get("kickoff"), "game_id": g["game_id"], "matchup": matchup,
                        "pick": f"{g['play_total']} {g['market_total']:g}", "odds": odds_t,
                        "detail": f"Pinnacle {st.get('sharp')}% vs {st.get('book')}% at {g.get('line_book')}, {st.get('ev'):+.1f}% value. Model total {g['total']:.1f}"
                        if st.get("ev") is not None else f"Model total {g['total']:.1f}",
                        "gap": st.get("ev"), "gap_unit": "%", "book": g.get("line_book"),
                        "bet": {"kind": "total", "game_id": g["game_id"], "side": g["play_total"], "line": g["market_total"],
                                "odds": odds_t or "-110", "model_pct": st.get("sharp") if st.get("sharp") is not None else (None if g.get("over_prob") is None else
                                fnum(g["over_prob"] if g["play_total"] == "Over" else 100 - g["over_prob"], 1))}})
    for g in games:                                       # alt lines and team totals (altlines.py)
        if g.get("state") != "upcoming":
            continue
        for x in (g.get("alt") or {}).get("plays", []):
            out.append({"kind": "alt", "market": x["market"], "period": x.get("period"), "kickoff": g.get("kickoff"), "game_id": g["game_id"],
                        "matchup": f"{g['away']} at {g['home']}", "pick": x["label"], "odds": x["odds"],
                        "detail": f"Pinnacle {x['sharp']}%{'' if x['exact'] else ' (converted)'} vs {x['book_p']}% at {x.get('book')}, {x['ev']:+.1f}% value. Model {x['model']}%",
                        "gap": x["ev"], "gap_unit": "%", "book": x.get("book"),
                        "bet": {"kind": "alt", "game_id": g["game_id"], "market": x["market"], "period": x.get("period"), "team": x.get("team"), "side": x["side"],
                                "line": x["line"], "home": g["home"], "odds": x["odds"], "model_pct": x["sharp"]}})
    ko = {g["game_id"]: g.get("kickoff") for g in games}
    st = {g["game_id"]: g.get("state") for g in games}
    for p in props.get("props", []):
        if p.get("tier") != "play" or st.get(p.get("game_id")) != "upcoming":
            continue
        odds = p.get("over_odds") if p["lean"] == "Over" else p.get("under_odds")
        out.append({"kind": "prop", "kickoff": ko.get(p["game_id"]), "game_id": p["game_id"],
                    "matchup": f"{p['team']} vs {p['opp']}", "player": p["player"], "pos": p.get("pos"),
                    "pick": f"{p['lean']} {p['line']}", "label": p.get("label"), "odds": odds,
                    "detail": f"Model {_pct_side(p['model_over'], p['lean'])}% vs book {_pct_side(p['book_over'], p['lean'])}%"
                              + (f", other books {_pct_side(p['cons_over'], p['lean'])}% ({p.get('cons_n')} books, {p['cons_ev']:+.1f}% value at this price)"
                                 if p.get("cons_over") is not None and p.get("cons_ev") is not None else ""),
                    "model_pct": _pct_side(p["model_over"], p["lean"]), "book_pct": _pct_side(p["book_over"], p["lean"]),
                    "gap": fnum(abs(p["edge"])), "gap_unit": "%", "book": p.get("book"), "median": p.get("median"),
                    "bet": {"kind": "prop", "game_id": p["game_id"], "pid": p.get("pid"), "player": p["player"],
                            "stat": p.get("stat_key") or p.get("stat"), "label": p.get("label"), "side": p["lean"],
                            "line": 0.5 if (p.get("stat_key") or p.get("stat")) == "anytime_td" else float(p["line"]),
                            "odds": odds or "-110", "model_pct": _pct_side(p["model_over"], p["lean"])}})
    out.sort(key=lambda x: (x.get("kickoff") or "", x["kind"] != "spread", -(x.get("gap") or 0)))
    return out


def lock_flags(old_games, games, now):
    """Plays are locked the first time they are flagged (Oct 20 2026): graded at that line and price, and a play
    that later stops qualifying still counts, since that's when you'd have bet it. Older saved plays without flags
    count at their saved line (marked legacy)."""
    prev = {g["game_id"]: g for g in old_games}
    ts = now.isoformat(timespec="minutes")
    for g in games:
        p = prev.get(g["game_id"]) or {}
        flags = dict(p.get("flags") or {})
        if "flags" not in p:
            if p.get("play_spread") and p.get("market_spread") is not None:
                t = p["play_spread"]
                flags["spread"] = {"side": t, "line": -p["market_spread"] if t == p["home"] else p["market_spread"],
                                   "odds": "-110", "at": None, "legacy": True}
            if p.get("play_total") and p.get("market_total") is not None:
                flags["total"] = {"side": p["play_total"], "line": p["market_total"], "odds": "-110", "at": None, "legacy": True}
        if g.get("play_spread") and "spread" not in flags:
            t, sp = g["play_spread"], g.get("sharp_spread") or {}
            flags["spread"] = {"side": t, "line": -g["market_spread"] if t == g["home"] else g["market_spread"],
                               "odds": _fmt_odds_s(sp.get("odds")) or "-110", "ev": sp.get("ev"), "sharp": sp.get("sharp"),
                               "book_pct": sp.get("book"), "book": g.get("line_book"), "at": ts}
        if g.get("play_total") and "total" not in flags:
            st = g.get("sharp_total") or {}
            flags["total"] = {"side": g["play_total"], "line": g["market_total"], "odds": _fmt_odds_s(st.get("odds")) or "-110",
                              "ev": st.get("ev"), "sharp": st.get("sharp"), "book_pct": st.get("book"), "book": g.get("line_book"), "at": ts}
        g["flags"] = flags
        alt_flags = dict(p.get("alt_flags") or {})        # alt-line plays: locked the same way
        for x in (g.get("alt") or {}).get("plays", []):
            k_ = f"{x.get('period') or ''}{x['market']}|{x.get('team')}|{x['side']}|{x['line']}"
            if k_ not in alt_flags:
                alt_flags[k_] = {f_: x.get(f_) for f_ in ("market", "team", "side", "line", "odds", "model", "sharp", "exact", "ev", "label", "book", "period")}
                alt_flags[k_]["at"] = ts
        g["alt_flags"] = alt_flags


def grade_flag(kind, fl, g, hs, as_):
    """(result, units, line CLV in points) for a locked play. CLV: the play's line vs the last saved line before kickoff."""
    if kind == "spread":
        m = (hs - as_) if fl["side"] == g["home"] else (as_ - hs)
        v = m + fl["line"]
        close = g.get("market_spread")
        clv = None if close is None else fl["line"] - (-close if fl["side"] == g["home"] else close)
    else:
        v = (hs + as_ - fl["line"]) * (1 if fl["side"] == "Over" else -1)
        close = g.get("market_total")
        clv = None if close is None else (close - fl["line"]) * (1 if fl["side"] == "Over" else -1)
    rr = "P" if v == 0 else ("W" if v > 0 else "L")
    o = float(str(fl.get("odds") or "-110").replace("+", ""))
    pay = o / 100 if o > 0 else 100 / -o
    return rr, (pay if rr == "W" else (-1.0 if rr == "L" else 0.0)), clv


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
    flag_rows = []
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
            flags = g.get("flags")
            if flags is None:                          # saved before flags existed: the plays as last saved
                flags = {}
                if g.get("play_spread") and g.get("market_spread") is not None:
                    t = g["play_spread"]
                    flags["spread"] = {"side": t, "line": -g["market_spread"] if t == g["home"] else g["market_spread"], "odds": "-110", "legacy": True}
                if g.get("play_total") and g.get("market_total") is not None:
                    flags["total"] = {"side": g["play_total"], "line": g["market_total"], "odds": "-110", "legacy": True}
            for kind, fl in flags.items():
                rr, u, clv = grade_flag(kind, fl, g, float(r["home_score"]), float(r["away_score"]))
                flag_rows.append({"kind": kind, "week": int(g.get("week") or 0), "game": f"{g['away']} at {g['home']}",
                                  "pick": f"{fl['side']} {fl['line']:+g}" if kind == "spread" else f"{fl['side']} {fl['line']:g}",
                                  "odds": fl.get("odds"), "res": rr, "units": round(u, 3), "clv_pts": None if clv is None else round(clv, 1),
                                  "legacy": bool(fl.get("legacy"))})
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
    frec = lambda k: [sum(1 for x in flag_rows if x["kind"] == k and x["res"] == "W"), sum(1 for x in flag_rows if x["kind"] == k and x["res"] == "L")]
    cl = [x["clv_pts"] for x in flag_rows if x["clv_pts"] is not None]
    return {"straight_up": rec(su), "ats_all": rec(ats), "ats_leans": rec(ats_lean),
            "totals_leans": rec(ou_lean), "ats_plays": frec("spread"), "totals_plays": frec("total"),
            "game_plays": {"list": sorted(flag_rows, key=lambda x: -x["week"])[:40],
                           "units": round(sum(x["units"] for x in flag_rows), 2),
                           "clv_pts": round(float(np.mean(cl)), 2) if cl else None,
                           "beat_close": round(100 * float(np.mean([c > 0 for c in cl])), 1) if cl else None, "n_clv": len(cl)},
            "picks": P.summarize(pick_rows),
            "picks_by_week": {str(w): P.summarize(r) for w, r in sorted(week_rows.items())},
            "model_mae": fnum(np.mean(err_m)) if err_m else None,
            "vegas_mae": fnum(np.mean(err_v)) if err_v else None}


MARKET_NAMES = {"team_total": "Team totals", "h1_spread": "1st half margin", "h1_total": "1st half total",
                "pass_yds": "Passing yards", "pass_cmp": "Completions", "pass_att": "Pass attempts", "rush_yds": "Rushing yards",
                "carries": "Rush attempts", "rec": "Receptions", "rec_yds": "Receiving yards", "rush_rec_yds": "Rush + rec yards",
                "q1_pass_yds": "1st quarter pass yards", "q1_rec_yds": "1st quarter rec yards", "q1_rec": "1st quarter receptions"}


def weekly_report(live, clv, props_path, week, tracking=None):
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
        for key, m in ((tracking or {}).get("markets") or {}).items():
            nm = MARKET_NAMES.get(key, key)
            if m.get("verdict") == "low":
                t.append(f"{nm}: overs hit {m['over']}% at the model's fair line ({m['n']} graded). The model runs low here, so overs have an edge.")
            elif m.get("verdict") == "high":
                t.append(f"{nm}: overs hit only {m['over']}% at the model's fair line ({m['n']} graded). The model runs high here, so unders have an edge.")
        sea = out["season_prop_plays"]
        if sea["n"] < 100:
            t.append(f"Season sample is still small ({sea['n']} prop plays). Judge the model after 100+.")
        out["takeaways"] = t
        # week-by-week series for the dashboard trend charts
        series = []
        for w in sorted(set(weeks) | {int(r.get("week") or 0) for r in props}):
            if not w or w >= (week or 99):
                continue
            pr = rec([r for r in props if int(r.get("week") or 0) == w and r.get("tier") == "play"])
            pk = (live.get("picks_by_week") or {}).get(str(w)) or {}
            series.append({"week": w, "prop_units": pr["units"], "prop_w": pr["w"], "prop_l": pr["l"],
                           "spread_w": (pk.get("spread") or {}).get("w", 0), "spread_l": (pk.get("spread") or {}).get("l", 0)})
        out["series"] = series
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
        res["prop_record"] = tracker.grade_props(OUT / "props_log.json", bundle.pbp, bundle.schedules, now, snaps=bundle.snaps)
        try:                                   # paused bet types: shadow record and the bar to come back (gates.py)
            gst = GT.load(OUT / "gates.json", ("nfl_prop_overs", "nfl_prop_rec"))
            rows = tracker.gate_rows(OUT / "props_log.json")
            res["gates"] = [GT.update(OUT / "gates.json", gst, k, sh, pl, now.date().isoformat()) for k, (sh, pl) in rows.items()]
        except Exception as e:  # noqa: BLE001
            log.warning(f"gates skipped: {e}")
    except Exception as e:  # noqa: BLE001
        log.warning(f"prop tracker skipped: {e}")
        res["prop_record"] = {"error": str(e)[:160]}
    try:                                       # box scores the dashboard uses to grade your bets
        results = tracker.build_results(bundle.pbp, bundle.schedules, season)
        (OUT / "results.json").write_text(json.dumps(clean_json(results), separators=(",", ":"), allow_nan=False))
        res["tracking"] = clean_json(tracker.model_tracking(HIST, season, results, snaps=bundle.snaps))
        by_week, kn = {}, KeyNumbers(bundle.schedules)
        for f in sorted(HIST.glob(f"{season}_week*.json")):
            d = json.loads(f.read_text())
            gs = d.get("games", [])
            for g in gs:                       # weeks saved before teasers existed
                if "teaser_legs" not in g and g.get("margin") is not None:
                    g["teaser_legs"] = TZ.game_legs(g, kn)
            by_week[int(d.get("week") or f.stem.split("week")[-1])] = gs
        res["tracking"]["teasers"] = clean_json(TZ.tracking(by_week, results.get("games") or {}))
    except Exception as e:  # noqa: BLE001
        log.warning(f"results / tracking skipped: {e}")
    return res


def main():
    now = datetime.now(timezone.utc)
    if os.environ.get("NOW"):  # testing / replaying a past week
        now = datetime.fromisoformat(os.environ["NOW"]).astimezone(timezone.utc)
    season = C.SEASON or guess_season(now)
    log.info(f"season {season}")
    bundle = D.load_all(season)
    # paused bet types (gates.py): a type that has earned its way back is a play again from this run on
    gst = GT.load(OUT / "gates.json", ("nfl_prop_overs", "nfl_prop_rec"))
    if GT.active(gst, "nfl_prop_overs"):
        C.PROP_PLAY_SIDES = ["Over", "Under"]
    if GT.active(gst, "nfl_prop_rec") and "rec" not in C.PROP_PLAY_STATS:
        C.PROP_PLAY_STATS = list(C.PROP_PLAY_STATS) + ["rec"]
    log.info(f"gates: {({k: v['status'] for k, v in gst.items()})}")
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
    if SGP_DIR.exists():                      # parlay draws only for games still to be played
        live_ids = {g["game_id"] for g in games}
        for f in SGP_DIR.glob("*.json"):
            if f.stem not in live_ids:
                f.unlink()
    hpath = HIST / f"{season}_week{week:02d}.json"
    lock_flags((json.loads(hpath.read_text()) if hpath.exists() else {}).get("games", []), games, now)
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
    try:
        payload["teasers"] = clean_json(TZ.board(all_games, bundle.schedules))
    except Exception as e:  # noqa: BLE001
        log.warning(f"teaser board skipped: {e}")
    payload["plays_record"] = {"spreads": live["ats_plays"], "totals": live["totals_plays"],
                               "props": pr.get("plays") if isinstance(pr, dict) else None}
    payload["plays_rules"] = {
        "prop_play": [round(100 * C.PROP_PLAY_MIN), round(100 * C.PROP_PLAY_MAX)],
        "prop_watch_max": round(100 * C.PROP_WATCH_MAX),
        "prop_play_stats": [stat_label(x) for x in C.PROP_PLAY_STATS], "prop_play_sides": list(getattr(C, "PROP_PLAY_SIDES", ["Over", "Under"])),
        "spread_gap": None, "total_gap": None, "sharp_rule": {"min_ev": BR.SHARP_MIN_EV, "max_ev": BR.SHARP_MAX_EV},
        "alt_rule": {"min_ev": AL.SHARP_MIN_EV, "max_ev": AL.SHARP_MAX_EV, "converted_extra": AL.ALT_CONVERTED_EXTRA, "cap": C.ALT_PLAY_CAP},
        "game_plays": live.get("game_plays"),
        "spread_backtest": bucket_record(ab, "spread_buckets", C.GAME_PLAY_SPREAD),
        "total_backtest": bucket_record(ab, "total_buckets", C.GAME_PLAY_TOTAL),
        **BR.summary(), **dict(zip(("bias", "calibration"), prop_bias(OUT / "props_log.json", with_real=True))),
        "model_weight": {**BR.MODEL_WEIGHT, "prop": C.PROP_MODEL_WEIGHT}, "td_scale": C.TD_PROB_SCALE, "td_curve": list(C.TD_CURVE),
    }
    payload["alt_rules"] = {"min_ev": AL.SHARP_MIN_EV, "max_ev": AL.SHARP_MAX_EV, "converted_extra": AL.ALT_CONVERTED_EXTRA, "daily_cap": C.ALT_PLAY_CAP}
    payload.update({
        "model": model_info,
        "props": props,
        "scheme_enabled": scheme_ok,
        "games": all_games, "players": all_players, "teams": teams_tbl,
        "backtest": {k: (fnum(v, 2) if isinstance(v, float) else v) for k, v in report.items()},
        "live_record": live,
        "report": weekly_report(live, payload.get("clv"), OUT / "props_log.json", week, payload.get("tracking")),
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
