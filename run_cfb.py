"""
College football model run (Power 4 games only on the site).

  python run_cfb.py          writes docs/cfb/data/latest.json (+ history, results)

Steps: add finished games from ESPN's free feed, rebuild opponent-adjusted
team ratings, fit the points and yardage models, find this week's games with
a Power 4 team, simulate each one around a number anchored to the book's line,
price spreads, totals, moneylines, teasers and player props, build alt-line
parlays, then grade everything already played.
"""
import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from cfbmodel import backtest as BT
from cfbmodel import config as C
from cfbmodel import data as D
from cfbmodel import gamemodel as G
from cfbmodel import odds as O
from cfbmodel import pbp as B
from cfbmodel import props as P
from cfbmodel import ratings as R
from cfbmodel import teasers as TZ
from cfbmodel.util import clean, r

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("cfbmodel")
ROOT = Path(__file__).resolve().parent
OUT = ROOT / "docs" / "cfb" / "data"
HIST = OUT / "history"
ET = ZoneInfo("America/New_York")
STAT_IDX = {"pass_yds": 0, "pass_td": 1, "rush_yds": 2, "rec_yds": 3, "rec": 4, "td": 5}
LOOKAHEAD_DAYS = 8
CALIB_MIN = {"rec": 2.5, "rec_yds": 30.5, "rush_yds": 30.5}       # fair line a player needs to count in the props check


def american(p):
    if not p or p <= 0 or p >= 1:
        return None
    return round(-100 * p / (1 - p)) if p >= 0.5 else round(100 * (1 - p) / p)


def payout(odds):
    o = float(odds)
    return o / 100 if o > 0 else 100 / -o


def fmt_odds(o):
    if o is None or o != o:
        return None
    o = int(round(float(o)))
    return f"+{o}" if o > 0 else str(o)


def fmt_line(v):
    return "PK" if abs(v) < 0.25 else f"{v:+g}"


def half(v):
    """Nearest half point."""
    return round(v * 2) / 2


def load_json(p, default):
    try:
        return json.loads(Path(p).read_text())
    except Exception:  # noqa: BLE001
        return default


def utc(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


# ---------------------------------------------------------------------
# game lines: picks and plays
# ---------------------------------------------------------------------
def game_picks(g, star, mkt, pure):
    """Spread, total, moneyline. With a book line, the model's chance is the book's no-vig chance plus
    how much the simulation moves when centered on the model's anchored number instead of the book's.
    Without one, only fair prices from the model's own number."""
    b = g.get("book") or {}
    out = {}
    d, t = star["d"], star["t"]
    if b.get("spread") is not None:
        s = b["spread"]
        ps, pm = _cover(star["d"], s), _cover(mkt["d"], s)
        bh = O.no_vig(b.get("spread_home_odds") or -110, b.get("spread_away_odds") or -110)
        delta = ps - pm
        home = delta >= 0
        out["spread"] = {"side": g["home"] if home else g["away"], "line": s if home else -s,
                         "odds": fmt_odds((b.get("spread_home_odds") if home else b.get("spread_away_odds")) or -110),
                         "model": r(100 * ((bh + delta) if home else (1 - bh - delta))), "book": r(100 * (bh if home else 1 - bh)),
                         "edge": r(100 * abs(delta)), "gap": r(abs(g["gap_spread"]))}
        _play(out["spread"], abs(g["gap_spread"]) <= C.MAX_GAP_SPREAD)
    else:
        s = half(-float(pure["d"].mean()))
        ph = _cover(pure["d"], s)
        home = ph >= 0.5
        out["spread"] = {"side": g["home"] if home else g["away"], "line": s if home else -s, "odds": None,
                         "model": r(100 * max(ph, 1 - ph)), "book": None, "edge": None, "fair": fmt_odds(american(max(ph, 1 - ph))), "play": False}
    if b.get("total") is not None:
        L = b["total"]
        ps, pm = _over(star["t"], L), _over(mkt["t"], L)
        bo = O.no_vig(b.get("over_odds") or -110, b.get("under_odds") or -110)
        delta = ps - pm
        over = delta >= 0
        out["total"] = {"side": "Over" if over else "Under", "line": L,
                        "odds": fmt_odds((b.get("over_odds") if over else b.get("under_odds")) or -110),
                        "model": r(100 * ((bo + delta) if over else (1 - bo - delta))), "book": r(100 * (bo if over else 1 - bo)),
                        "edge": r(100 * abs(delta)), "gap": r(abs(g["gap_total"]))}
        _play(out["total"], abs(g["gap_total"]) <= C.MAX_GAP_TOTAL)
    else:
        L = half(float(pure["t"].mean()))
        po = _over(pure["t"], L)
        out["total"] = {"side": "Over" if po >= 0.5 else "Under", "line": L, "odds": None, "model": r(100 * max(po, 1 - po)),
                        "book": None, "edge": None, "fair": fmt_odds(american(max(po, 1 - po))), "play": False}
    if b.get("ml_home") and b.get("ml_away"):
        ps, pm = float((star["d"] > 0).mean()), float((mkt["d"] > 0).mean())
        bh = O.no_vig(b["ml_home"], b["ml_away"])
        delta = ps - pm
        home = delta >= 0
        price = b["ml_home"] if home else b["ml_away"]
        out["ml"] = {"side": g["home"] if home else g["away"], "odds": fmt_odds(price),
                     "model": r(100 * float(np.clip((bh + delta) if home else (1 - bh - delta), 0.01, 0.99))), "book": r(100 * (bh if home else 1 - bh)),
                     "edge": r(100 * abs(delta))}
        _play(out["ml"], abs(g["gap_spread"]) <= C.MAX_GAP_SPREAD and -1500 <= price <= C.ML_MAX_DOG)
    else:
        pw = float(((star if b.get("spread") is not None else pure)["d"] > 0).mean())
        home = pw >= 0.5
        out["ml"] = {"side": g["home"] if home else g["away"], "odds": None, "model": r(100 * max(pw, 1 - pw)), "book": None, "edge": None,
                     "fair": fmt_odds(american(max(pw, 1 - pw))), "play": False}
    sp, ml = out.get("spread"), out.get("ml")
    if sp and ml and sp["play"] and ml["play"] and sp["side"] == ml["side"]:     # same team twice: keep the spread
        ml["play"] = False
    return out


def _play(pk, allowed):
    """A play has to make money at the book's posted price, vig included, not just beat the fair price."""
    pk["ev"] = r(100 * (pk["model"] / 100 * (payout(pk["odds"]) + 1) - 1))
    pk["play"] = bool(allowed and pk["ev"] >= C.PLAY_MIN_EV)


def _cover(d, s):
    v = d + s
    dec = v != 0
    return float((v[dec] > 0).mean()) if dec.any() else 0.5


def _over(t, L):
    dec = t != L
    return float((t[dec] > L).mean()) if dec.any() else 0.5


def pick_text(k, pk):
    if k == "ml":
        return f"{pk['side']} ML"
    if k == "spread":
        return f"{pk['side']} {fmt_line(pk['line'])}"
    return f"{pk['side']} {pk['line']:g}"


# ---------------------------------------------------------------------
# results and grading
# ---------------------------------------------------------------------
def build_results(games_t, pg, ids):
    """Final scores, closing lines and player stats for every finished game we predicted."""
    out = {}
    gt = games_t[games_t["game_id"].isin(ids)]
    by = {gid: x for gid, x in pg[pg["game_id"].isin(ids)].groupby("game_id")}
    for g in gt.to_dict("records"):
        st = {}
        for p in by.get(g["game_id"], pd.DataFrame()).fillna(0).to_dict("records"):
            st[str(int(p["pid"]))] = [int(p["pass_yds"]), int(p["pass_td"]), int(p["rush_yds"]), int(p["rec_yds"]), int(p["rec"]),
                                      int(p["rush_td"] + p["rec_td"])]
        out[str(int(g["game_id"]))] = {"h": int(g["hs"]), "a": int(g["as"]), "cs": r(g["spread"]), "ct": r(g["total"]), "p": st}
    return out


def grade_pick(kind, pk, g, res):
    h, a = res["h"], res["a"]
    side_home = pk["side"] == g["home"]
    if kind == "ml":
        rr = "W" if (h > a) == side_home else "L"
    elif kind == "spread":
        v = ((h - a) if side_home else (a - h)) + pk["line"]
        rr = "P" if v == 0 else ("W" if v > 0 else "L")
    else:
        v = (h + a) - pk["line"]
        rr = "P" if v == 0 else ("W" if (v > 0) == (pk["side"] == "Over") else "L")
    if not pk.get("odds"):
        return rr, None
    return rr, (payout(pk["odds"]) if rr == "W" else (-1.0 if rr == "L" else 0.0))


def tracking(weeks, results):
    picks = {k: [] for k in ("spread", "total", "ml")}
    plays, prop_plays, calib, alts, daily = [], [], {}, [], {}
    clv = {"spread": [], "total": []}
    for wk in weeks:
        for g in wk.get("games", []):
            res = results.get(str(g["game_id"]))
            if not res:
                continue
            dt = g["date"]
            for k, pk in (g.get("picks") or {}).items():
                if pk.get("edge") is None:
                    continue
                rr, u = grade_pick(k, pk, g, res)
                picks[k].append((rr, u, pk.get("edge")))
                if pk.get("play"):
                    plays.append({"date": dt, "kind": k, "pick": pick_text(k, pk), "game": f"{g['away']} at {g['home']}",
                                  "odds": pk.get("odds"), "edge": pk.get("edge"), "res": rr, "units": u})
                    daily[dt] = daily.get(dt, 0) + (u or 0)
            # did the line move our way after we first saw it? (first line vs close, in points)
            fb, P_ = g.get("first_book") or {}, g.get("first_picks") or {}
            sp, tp = P_.get("spread"), P_.get("total")
            if sp and fb.get("spread") is not None and res.get("cs") is not None and (sp.get("gap") or 0) >= 3:
                first = fb["spread"] if sp["side"] == g["home"] else -fb["spread"]
                close = res["cs"] if sp["side"] == g["home"] else -res["cs"]
                clv["spread"].append(first - close)
            if tp and fb.get("total") is not None and res.get("ct") is not None and (tp.get("gap") or 0) >= 3:
                clv["total"].append((res["ct"] - fb["total"]) * (1 if tp["side"] == "Over" else -1))
            ap = g.get("alt_parlay")
            if ap:
                hits = []
                for L in ap["legs"]:
                    st = res["p"].get(str(L["pid"]))
                    hits.append(None if st is None else st[STAT_IDX[L["stat"]]] > L["line"])
                if None not in hits:
                    alts.append({"date": dt, "game": f"{g['away']} at {g['home']}", "hit": all(hits), "legs_hit": sum(hits),
                                 "legs": len(hits), "p": ap["p"]})
        for p in wk.get("players", []):
            res = results.get(str(p["game_id"]))
            if not res:
                continue
            st = res["p"].get(str(p["pid"]))
            if st is None:
                continue                                  # did not play: no action
            for stat, m in p["m"].items():
                v = st[STAT_IDX[stat]]
                # regulars only: a low-usage player with no catches or carries isn't in the box score at all,
                # so counting only the ones who are would make every over look too good
                if m["fair"] >= CALIB_MIN.get(stat, 0) and (stat != "td" or m["pf"] >= 0.2):
                    calib.setdefault(stat, []).append((m["pf"], v > m["fair"]))
                bk = m.get("book")
                if bk and bk.get("play"):
                    L = bk["line"]
                    rr = "P" if v == L else ("W" if (v > L) == (bk["side"] == "Over") else "L")
                    u = payout(bk["odds"]) if rr == "W" else (-1.0 if rr == "L" else 0.0)
                    prop_plays.append({"date": p["date"], "player": p["name"], "pick": f"{bk['side']} {L:g} {P.LABEL[stat]}", "odds": fmt_odds(bk["odds"]),
                                       "edge": bk["edge"], "res": rr, "units": u, "actual": v})
                    daily[p["date"]] = daily.get(p["date"], 0) + u

    def rec(rows):
        w = sum(1 for x in rows if x[0] == "W"); l = sum(1 for x in rows if x[0] == "L")
        us = [x[1] for x in rows if x[1] is not None]
        return {"w": w, "l": l, "pct": r(100 * w / (w + l)) if w + l else None, "units": r(sum(us), 2) if us else None}

    def rec2(rows):
        w = sum(1 for x in rows if x["res"] == "W"); l = sum(1 for x in rows if x["res"] == "L")
        u = sum(x["units"] or 0 for x in rows)
        return {"w": w, "l": l, "pct": r(100 * w / (w + l)) if w + l else None, "units": r(u, 2),
                "roi": r(100 * u / (w + l)) if w + l else None}
    cal = {st: {"n": len(rows), "model": r(100 * np.mean([x[0] for x in rows])), "actual": r(100 * np.mean([x[1] for x in rows]))}
           for st, rows in calib.items()}
    series, run = [], 0.0
    for dt in sorted(daily):
        run += daily[dt]
        series.append({"date": dt, "units": r(run, 2)})
    move = {k: {"n": len(v), "avg": r(np.mean(v), 2) if v else None, "our_way": int(sum(x > 0 for x in v)), "against": int(sum(x < 0 for x in v))}
            for k, v in clv.items()}
    return {"picks": {k: rec(v) for k, v in picks.items()},
            "plays": rec2(plays), "plays_list": sorted(plays, key=lambda x: x["date"], reverse=True)[:60],
            "prop_plays": rec2(prop_plays), "prop_plays_list": sorted(prop_plays, key=lambda x: x["date"], reverse=True)[:80],
            "calibration": cal, "line_move": move,
            "alt": {"n": len(alts), "hits": sum(a["hit"] for a in alts),
                    "model": r(np.mean([a["p"] for a in alts])) if alts else None,
                    "recent": sorted(alts, key=lambda x: x["date"], reverse=True)[:20]},
            "teasers": TZ.tracking({w["week"]: w.get("games", []) for w in weeks}, results),
            "series": series}


# ---------------------------------------------------------------------
# main
# ---------------------------------------------------------------------
def main():
    now = datetime.now(timezone.utc)
    today = now.astimezone(ET).date()
    OUT.mkdir(parents=True, exist_ok=True)
    HIST.mkdir(parents=True, exist_ok=True)

    cal = D.calendar()
    season = C.SEASON or cal["season"]
    reg = [w for w in cal["weeks"] if w["stype"] == 2]
    weeks = [(2, w["week"]) for w in reg if utc(w["start"]) <= now + timedelta(days=LOOKAHEAD_DAYS)]
    if any(w["stype"] == 3 and utc(w["start"]) <= now + timedelta(days=LOOKAHEAD_DAYS) for w in cal["weeks"]):
        weeks.append((3, 1))
    with ThreadPoolExecutor(6) as ex:
        sched = [g for wk in ex.map(lambda sw: D.scoreboard(season, sw[1], sw[0]), weeks) for g in wk]
    sched = list({g["game_id"]: g for g in sched}.values())
    p4 = {g[s]["id"] for g in sched for s in ("home", "away") if g[s]["conf"] in C.P4_CONFS} | set(C.P4_EXTRA)
    meta = {}
    for g in sched:
        for s in ("home", "away"):
            t = g[s]
            meta[t["id"]] = {"abbr": t["abbr"], "name": t["name"], "nick": t["nick"], "color": t["color"], "conf": t["conf"]}
    log.info(f"season {season}, week {cal['week']}, {len(sched)} games on the schedule, {len(p4)} Power 4 teams")

    games_t, tg, pg = B.update(sched, {season - 1, season})
    if set(pg["team_id"]) - p4:                               # keep the player table to Power 4 teams
        pg = pg[pg["team_id"].isin(p4)]
        pg.to_csv(B.DIR / "player_games.csv", index=False, float_format="%.1f")
    season_of = dict(zip(games_t["game_id"], games_t["season"]))

    # ratings, points model, simulators
    t = R.prepare(games_t, tg)
    Rt = R.build(t)
    F = R.features(t, Rt)
    Ftrain = F[F["season"] > C.FIRST_SEASON]
    model = G.Model().fit(Ftrain)
    Pn = model.predict(Ftrain)
    lines = games_t[games_t["spread"].notna() & games_t["total"].notna() & games_t["hs"].notna()]
    scores = G.Scores().fit(-lines["spread"], lines["total"], lines["hs"] - lines["as"], lines["hs"] + lines["as"])
    vol = G.Volume().fit(Pn[Pn["season"] >= season - 4])
    Hh = Pn[Pn["home"] == 1].merge(games_t[["game_id", "spread", "total"]], on="game_id").dropna(subset=["spread", "total"])
    recent = Hh[Hh["season"] >= season - 2]
    bias_m, bias_t = float((recent["em"] + recent["spread"]).mean()), float((recent["et"] - recent["total"]).mean())
    walk = BT.walk(F, games_t)
    backtest = BT.summary(walk, p4, season)
    cur = Rt[(int(season), 99)]
    log.info(f"points model {model.coefs()['pts']}")
    log.info(f"model vs book, last 2 seasons: spread {bias_m:+.2f}, total {bias_t:+.2f}; backtest {backtest and {k: backtest[k] for k in ('mae_model', 'mae_line', 'spread_all', 'total_all')}}")

    # this week's games with a Power 4 team
    def tid(team):
        return team["id"] if team["conf"] in C.FBS_CONFS else C.FCS_ID
    upcoming = [g for g in sched if not g["done"] and g["state"] == "STATUS_SCHEDULED" and utc(g["start"]) > now
                and utc(g["start"]) <= now + timedelta(days=LOOKAHEAD_DAYS) and (g["home"]["id"] in p4 or g["away"]["id"] in p4)
                and g["home"]["abbr"] != "TBD" and g["away"]["abbr"] != "TBD"]
    if upcoming:                                              # one week at a time: the earliest week that still has games to play
        first = min((g["stype"], g["week"]) for g in upcoming)
        upcoming = [g for g in upcoming if (g["stype"], g["week"]) == first]
    upcoming.sort(key=lambda g: (g["start"], g["game_id"]))
    log.info(f"{len(upcoming)} upcoming Power 4 games")
    for g in upcoming:
        g["home_full"] = f"{g['home']['name']} {g['home']['nick']}"
        g["away_full"] = f"{g['away']['name']} {g['away']['nick']}"
        g["p4_home"], g["p4_away"] = g["home"]["id"] in p4, g["away"]["id"] in p4
    book_props, odds_status = O.run(upcoming, OUT / "odds_state.json", OUT / "props_cache.json", now)
    with ThreadPoolExecutor(6) as ex:
        ids = sorted({g[s]["id"] for g in upcoming for s in ("home", "away") if g[s]["id"] in p4})
        rosters = dict(zip(ids, ex.map(D.roster, ids)))

    wk_now = min([g["week"] for g in upcoming if g["stype"] == 2] or [cal["week"]])
    damp = 0.5 if wk_now <= C.ANCHOR_EARLY_WEEKS else 1.0
    games, players = [], []
    for i, g in enumerate(upcoming):
        h, a = g["home"], g["away"]
        hf = 0.0 if g["neutral"] else 1.0
        X = pd.DataFrame([dict(R.matchup(cur, tid(h), tid(a), hf), game_id=g["game_id"], side="H"),
                          dict(R.matchup(cur, tid(a), tid(h), -hf), game_id=g["game_id"], side="A")])
        Xp = model.script(X)
        em, et = float(Xp["em"].iat[0]), float(Xp["et"].iat[0])
        b = g.get("odds") or {}
        book = {k: b.get(k) for k in ("spread", "total", "ml_home", "ml_away", "spread_home_odds", "spread_away_odds", "over_odds", "under_odds",
                                      "open_spread", "open_total")}
        book["src"] = b.get("book")
        has_s, has_t = book["spread"] is not None, book["total"] is not None
        gap_s = (em - bias_m + book["spread"]) if has_s else 0.0          # + = model likes the home team more than the book
        gap_t = (et - bias_t - book["total"]) if has_t else 0.0
        early = (utc(g["start"]) - now).total_seconds() / 86400 >= C.ANCHOR_EARLY_DAYS
        ws, wt = (C.ANCHOR_EARLY if early else (C.ANCHOR_SPREAD, C.ANCHOR_TOTAL))
        m_star = (-book["spread"] + damp * ws * gap_s) if has_s else em
        t_star = (book["total"] + damp * wt * gap_t) if has_t else et
        seed = 5000 + i
        if has_s and has_t:
            # the book's own prices set the baseline; the model only moves the middle
            like, orient = abs(book["spread"]), (1.0 if book["spread"] <= 0 else -1.0)
            fit = (book["spread"], O.no_vig(book["spread_home_odds"] or -110, book["spread_away_odds"] or -110),
                   book["total"], O.no_vig(book["over_odds"] or -110, book["under_odds"] or -110))
            mh, ma, off = scores.sim(-book["spread"], book["total"], seed=seed, like=like, orient=orient, fit=fit)
            mkt = {"d": mh - ma, "t": mh + ma}
            sh, sa, _ = scores.sim(m_star, t_star, seed=seed, like=like, orient=orient, offset=off)
            star = {"d": sh - sa, "t": sh + sa}
        else:
            has_s = has_t = False
            book.update({"spread": None, "total": None})
            m_star, t_star, gap_s, gap_t = em, et, 0.0, 0.0
            sh, sa, _ = scores.sim(em, et, seed=seed)
            star = mkt = {"d": sh - sa, "t": sh + sa}
        ph, pa, _ = scores.sim(em, et, n=6000, seed=seed)
        pure = {"d": ph - pa, "t": ph + pa}
        game = {"game_id": g["game_id"], "date": utc(g["start"]).astimezone(ET).date().isoformat(), "start": g["start"],
                "tbd": g["start"][11:16] in ("04:00", "05:00"),       # ESPN's placeholder for a kickoff time not set yet
                "week": g["week"], "wk": f"{season}-w{g['week']:02d}" if g["stype"] == 2 else f"{season}-post",
                "home": h["abbr"], "away": a["abbr"], "home_name": h["name"], "away_name": a["name"],
                "home_rank": h["rank"] if h["rank"] and h["rank"] <= 25 else None, "away_rank": a["rank"] if a["rank"] and a["rank"] <= 25 else None,
                "home_rec": h["record"], "away_rec": a["record"], "neutral": g["neutral"], "venue": g["venue"], "tv": g["tv"],
                "p4_home": g["p4_home"], "p4_away": g["p4_away"],
                "pts_home": r((et + em) / 2), "pts_away": r((et - em) / 2), "model_spread": r(-em), "model_total": r(et),
                "fin_home": r((t_star + m_star) / 2), "fin_away": r((t_star - m_star) / 2),
                "gap_spread": r(gap_s), "gap_total": r(gap_t), "book": book}
        game["picks"] = game_picks(game, star, mkt, pure)
        ml = game["picks"]["ml"]
        game["win_home"] = ml["model"] if ml["side"] == game["home"] else r(100 - ml["model"])
        game["fair_ml_home"] = fmt_odds(american(game["win_home"] / 100))
        game["teaser_legs"] = TZ.game_legs(game, star["d"], star["t"])
        # ratings shown in the game card
        form = {}
        for team, me in ((h, tid(h)), (a, tid(a))):
            form[team["abbr"]] = {k: r(cur[k][2].get(me, 0.0), 3) for k in ("epa_p", "epa_r", "pts")} | \
                                 {"d_" + k: r(cur[k][3].get(me, 0.0), 3) for k in ("epa_p", "epa_r", "pts")}
        game["form"] = form

        # players: team passing and rushing inside the same simulated scores
        Xa = X.copy()
        Xa["e_pts"] = [(t_star + m_star) / 2, (t_star - m_star) / 2]
        Xa["em"], Xa["et"] = [m_star, -m_star], t_star
        Xv = model.predict(Xa, keep_script=True)
        rng = np.random.default_rng(900 + i)
        info, arrs, qbs = {}, {}, {}
        for row, team, pts, opp in ((0, h, sh, sa), (1, a, sa, sh)):
            if team["id"] not in p4:
                continue
            ps, base = P.roles(pg, team["id"], season_of, season)
            if not ps:
                continue
            ros = rosters.get(team["id"]) or {}
            ps = [p for p in ps if not (ros.get(p["pid"]) or {}).get("out")]
            e = {k: float(Xv[k].iat[row]) for k in Xv.columns if k.startswith("e_")} | {"em": float(Xv["em"].iat[row])}
            tsim = vol.sim(e, pts, opp, rng)
            for p in ps:
                pos = (ros.get(p["pid"]) or {}).get("pos")
                info[p["pid"]] = {"name": p["name"], "team": team["abbr"], "pos": pos if pos in ("QB", "RB", "WR", "TE", "FB", "ATH") else p["pos"],
                                  "gp": p["gp"], "avg": p["avg"], "last": p["last"]}
            if base["qb"] is not None and not any(p is base["qb"] for p in ps):
                base["qb"] = None
            if base["qb"] is not None:
                info[base["qb"]["pid"]]["pos"] = "QB"
                qbs[team["abbr"]] = base["qb"]["name"]
            arrs.update(P.team_players(ps, base, tsim, rng, blowout=m_star))
            game.setdefault("team_proj", {})[team["abbr"]] = {k: r(float(np.mean(tsim[k]))) for k in ("pass_yds", "rush_yds", "pass_att", "rush_att")}
        game["qbs"] = qbs
        bp = book_props.get(g["game_id"], {})
        prows = P.summarize(arrs, info, bp)
        for p in prows:
            p["game_id"], p["date"] = g["game_id"], game["date"]
            p["opp"] = a["abbr"] if p["team"] == h["abbr"] else h["abbr"]
        players += prows
        game["alt_parlay"] = P.alt_parlay(arrs, info, bp, need_teams=2 if (g["p4_home"] and g["p4_away"]) else 1) if arrs else None
        games.append(game)
        log.info(f"{a['abbr']}@{h['abbr']}: model {(et - em) / 2:.1f}-{(et + em) / 2:.1f}, book {book['spread']} / {book['total']}, "
                 f"gap {gap_s:+.1f} / {gap_t:+.1f}")

    # if the model sits above or below the book on almost every prop of a stat, that is a level problem,
    # not 40 separate edges. Remove the slate-wide gap so plays come from players it rates differently.
    level = {}
    lg_ = lambda x: np.log(np.clip(x, 0.5, 99.5) / (100 - np.clip(x, 0.5, 99.5)))
    for st in C.PROP_STATS:
        diffs = [lg_(p["m"][st]["book"]["model_over"]) - lg_(p["m"][st]["book"]["book_over"]) for p in players if p["m"].get(st, {}).get("book")]
        if len(diffs) >= 6:
            level[st] = float(np.median(diffs))
    for p in players:
        for st, m in p["m"].items():
            bk = m.get("book")
            if not bk or st not in level:
                continue
            adj = 100 / (1 + np.exp(-(lg_(bk["model_over"]) - level[st])))
            side = "Over" if adj >= bk["book_over"] or not bk.get("under") else "Under"
            edge = (adj - bk["book_over"]) if side == "Over" else (bk["book_over"] - adj)
            bk.update({"model_over_raw": bk["model_over"], "model_over": r(adj), "side": side, "edge": r(edge),
                       "odds": bk["over"] if side == "Over" else bk["under"],
                       "play": 100 * C.PROP_PLAY_MIN <= edge <= 100 * C.PROP_PLAY_MAX})
    level = {k: r(v, 3) for k, v in level.items()}

    # history: one file per week, each game locked at kickoff
    by_wk = {}
    for g in games:
        by_wk.setdefault(g["wk"], {"games": [], "players": []})["games"].append(g)
    gwk = {g["game_id"]: g["wk"] for g in games}
    for p in players:
        lite = {k: p[k] for k in ("pid", "name", "team", "game_id", "date")}
        lite["m"] = {}
        for st, m in p["m"].items():
            if "ge" in m:
                k = int(m["fair"] + 0.5)
                pf = m["ge"][k] if k < len(m["ge"]) else 0.0
            else:
                pf = float(np.interp(m["fair"], m["q"], 1 - P.QS)) if m["q"][-1] > m["q"][0] else 0.5
            lite["m"][st] = {"fair": m["fair"], "pf": round(float(pf), 3),
                             **({"book": {x: m["book"][x] for x in ("line", "side", "odds", "edge", "play")}} if m.get("book") else {})}
        by_wk[gwk[p["game_id"]]]["players"].append(lite)
    for wk, v in by_wk.items():
        path = HIST / f"{wk}.json"
        old = load_json(path, {"week": wk, "games": [], "players": []})
        live = {g["game_id"] for g in v["games"]}
        keep = []
        for g in v["games"]:
            lite = {k: g[k] for k in ("game_id", "date", "start", "home", "away", "picks", "alt_parlay", "teaser_legs", "win_home", "book",
                                      "model_spread", "model_total", "gap_spread", "gap_total")}
            prev = next((x for x in old["games"] if x["game_id"] == g["game_id"]), None)
            lite["first_book"] = (prev or {}).get("first_book") or (g["book"] if g["book"].get("spread") is not None else None)
            lite["first_picks"] = (prev or {}).get("first_picks") or ({k: g["picks"][k] for k in ("spread", "total")} if g["book"].get("spread") is not None else None)
            keep.append(lite)
        path.write_text(json.dumps(clean({"week": wk, "games": [x for x in old["games"] if x["game_id"] not in live] + keep,
                                          "players": [x for x in old["players"] if x["game_id"] not in live] + v["players"]}), separators=(",", ":")))
    wks = [w for w in (load_json(p, {}) for p in sorted(HIST.glob("*.json"))) if w]
    ids = {g["game_id"] for w in wks for g in w.get("games", [])}
    results = build_results(games_t, pg, ids)
    (OUT / "results.json").write_text(json.dumps(clean(results), separators=(",", ":")))
    track = tracking(wks, results)

    # team table: Power 4 teams, ranked among every FBS team
    fbs = sorted({x for x in cur["pts"][2] if x != C.FCS_ID})
    Xavg = pd.DataFrame([dict(R.matchup(cur, x, -1, 0.0), game_id=x, side="T") for x in fbs] +
                        [dict(R.matchup(cur, -1, x, 0.0), game_id=x, side="O") for x in fbs])
    Xs = model.script(Xavg)
    power = {int(x): float(v) for x, v in zip(Xs.loc[Xs["side"] == "T", "game_id"], Xs.loc[Xs["side"] == "T", "em"])}
    rank = {x: i + 1 for i, x in enumerate(sorted(power, key=lambda k: -power[k]))}
    rec = {}
    for g in sched:
        for s in ("home", "away"):
            if g[s]["record"]:
                rec[g[s]["id"]] = g[s]["record"]
    cs = games_t[games_t["season"] == season]
    gp = pd.concat([cs["home_id"], cs["away_id"]]).value_counts().to_dict()
    teams = []
    for x in sorted(p4, key=lambda k: -power.get(k, -99)):
        if x not in power or x not in meta:
            continue
        teams.append({"team": meta[x]["abbr"], "name": meta[x]["name"], "conf": C.P4_CONFS.get(meta[x]["conf"], C.P4_EXTRA.get(x, "")),
                      "power": r(power[x]), "rank": rank[x], "record": rec.get(x), "gp": int(gp.get(x, 0)),
                      "off": r(cur["pts"][2].get(x, 0.0)), "def": r(cur["pts"][3].get(x, 0.0)),
                      "epa_p": r(cur["epa_p"][2].get(x, 0.0), 3), "epa_r": r(cur["epa_r"][2].get(x, 0.0), 3),
                      "d_epa_p": r(cur["epa_p"][3].get(x, 0.0), 3), "d_epa_r": r(cur["epa_r"][3].get(x, 0.0), 3),
                      "sr": r(100 * (cur["sr"][0] + cur["sr"][2].get(x, 0.0))), "d_sr": r(100 * (cur["sr"][0] - cur["sr"][3].get(x, 0.0)))})
    colors = {m["abbr"]: "#" + (m["color"] or "555555") for m in meta.values()}
    for g in games:                                            # make sure every shown team has its own color
        for s, team in (("home", g["home"]), ("away", g["away"])):
            colors.setdefault(team, "#555555")
    shown = {t["team"] for t in teams} | {g[s] for g in games for s in ("home", "away")}
    post = bool(upcoming) and upcoming[0]["stype"] == 3
    wk_label = "Bowl season" if post else next((w["label"] for w in reg if w["week"] == wk_now), f"Week {wk_now}")
    payload = {"generated_at": now.isoformat(), "season": season, "week": wk_now, "week_label": wk_label, "today": today.isoformat(),
               "games": games, "players": players, "odds": odds_status, "tracking": track, "prop_level": level,
               "teasers": TZ.board(games, BT.teaser_history(games_t, C.TEASER_POINTS)),
               "teams": teams, "colors": {k: v for k, v in colors.items() if k in shown},
               "model": {"coefs": model.coefs()["pts"], "backtest": backtest,
                         "anchor": {"spread": C.ANCHOR_SPREAD * damp, "total": C.ANCHOR_TOTAL * damp, "early": [x * damp for x in C.ANCHOR_EARLY], "early_days": C.ANCHOR_EARLY_DAYS},
                         "sd": {"margin": r(scores.sd_m), "total": r(scores.sd_t)}, "train_games": int(len(Ftrain) / 2),
                         "league": {"pts": r(cur["pts"][0]), "epa_p": r(cur["epa_p"][0], 3), "epa_r": r(cur["epa_r"][0], 3)}},
               "rules": {"min_ev": C.PLAY_MIN_EV,
                         "max_gap": [C.MAX_GAP_SPREAD, C.MAX_GAP_TOTAL], "prop": [100 * C.PROP_PLAY_MIN, 100 * C.PROP_PLAY_MAX]}}
    (OUT / "latest.json").write_text(json.dumps(clean(payload), separators=(",", ":")))
    log.info(f"wrote {len(games)} games, {len(players)} players")


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        log.exception("CFB run failed")
        sys.exit(1)
