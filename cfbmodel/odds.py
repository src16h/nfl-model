"""
Odds for college football.

Game lines (spread, total, moneyline, with the opening number) come free from
ESPN's DraftKings feed, so they need no key.

Player prop lines are optional and use The Odds API on its own free key
(ODDS_API_KEY_CFB, 500 credits a month). A game's props cost one credit per
market, so each game is pulled once, inside 30 hours of kickoff, soonest
games first, and only while this week's share of the credits lasts. Without a
key the site shows the model's fair line and you type in your book's line.
"""
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from calendar import monthrange
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config as C
from .util import norm_name

log = logging.getLogger("cfbmodel")
BASE = "https://api.the-odds-api.com"
SPORT = "americanfootball_ncaaf"
PROP_STAT = {"player_pass_yds": "pass_yds", "player_rush_yds": "rush_yds", "player_reception_yds": "rec_yds",
             "player_receptions": "rec", "player_pass_tds": "pass_td", "player_anytime_td": "td"}


BOOK_ORDER = ["hardrockbet", "draftkings", "fanduel", "betmgm", "williamhill_us", "espnbet", "betrivers", "fanatics", "bovada"]


import sys as _sys  # noqa: E402
_sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import standin as SI  # noqa: E402

GAME_BOOKS = ["hardrockbet", "kalshi", "pinnacle"]      # DK Predictions stand-in (Hard Rock + Kalshi), Pinnacle for reference


def _book_lines(ev, b):
    hn, an = ev["home_team"], ev["away_team"]
    rec = {}
    for m in b.get("markets", []):
        out = {o["name"]: o for o in m.get("outcomes", [])}
        if m["key"] == "h2h" and hn in out and an in out:
            rec["ml_home"], rec["ml_away"] = out[hn]["price"], out[an]["price"]
        elif m["key"] == "spreads" and hn in out and an in out and out[hn].get("point") is not None:
            rec["spread"], rec["spread_home_odds"], rec["spread_away_odds"] = float(out[hn]["point"]), out[hn]["price"], out[an]["price"]
        elif m["key"] == "totals" and "Over" in out and "Under" in out and out["Over"].get("point") is not None:
            rec["total"], rec["over_odds"], rec["under_odds"] = float(out["Over"]["point"]), out["Over"]["price"], out["Under"]["price"]
    return rec


def game_lines(cl, games, state, now):
    """Oct 31 2026: game lines at the DK Predictions stand-in price (Hard Rock + Kalshi, standin.py), one call for every
    game (3 credits), at most every GAME_LINES_EVERY_HOURS. Replaces ESPN's DraftKings line on each game it finds
    (ESPN's opening line is kept for the line-move display)."""
    last = state.get("game_lines_at")
    age = (now - datetime.fromisoformat(last)).total_seconds() / 3600 if last else 99
    soon = [g for g in games if 0 < (datetime.fromisoformat(g["start"].replace("Z", "+00:00")) - now).total_seconds() / 3600 <= 24 * 7]
    if soon and (age >= C.GAME_LINES_EVERY_HOURS or not state.get("game_lines")):
        data = cl.get(f"/v4/sports/{SPORT}/odds", markets="h2h,spreads,totals", oddsFormat="american", bookmakers=",".join(GAME_BOOKS))
        lines = {}
        for ev in data:
            bks = {b["key"]: b for b in ev.get("bookmakers", [])}
            hr = _book_lines(ev, bks["hardrockbet"]) if "hardrockbet" in bks else None
            ks = _book_lines(ev, bks[SI.KALSHI]) if SI.KALSHI in bks else None
            if not hr and not ks:
                continue
            rec = SI.apply(hr or None, ks, [(None, "ml_home", "ml_away"), ("spread", "spread_home_odds", "spread_away_odds"),
                                            ("total", "over_odds", "under_odds")])
            rec["book"] = SI.LABEL + (" (Hard Rock + Kalshi)" if hr and ks else " (Kalshi)" if ks else " (Hard Rock only)")
            if "pinnacle" in bks:
                rec["sharp"] = _book_lines(ev, bks["pinnacle"])
            lines[f"{norm_name(ev['home_team'])}|{norm_name(ev['away_team'])}"] = rec
        state["game_lines"], state["game_lines_at"] = lines, now.isoformat()
    lines = state.get("game_lines") or {}
    n = 0
    for g in games:
        rec = lines.get(f"{norm_name(g.get('home_full'))}|{norm_name(g.get('away_full'))}")
        if rec and (rec.get("spread") is not None or rec.get("ml_home") is not None):
            base = g.get("odds") or {}
            g["odds"] = {**base, **{k: rec.get(k) for k in ("spread", "total", "ml_home", "ml_away", "spread_home_odds", "spread_away_odds",
                                                           "over_odds", "under_odds")},
                         "book": rec["book"], "sharp": rec.get("sharp"), "standin": rec.get("standin"), "espn_book": base.get("book")}
            n += 1
    return n


class Fatal(Exception):
    pass


def no_vig(a, b):
    def imp(x):
        return 100 / (x + 100) if x > 0 else -x / (-x + 100)
    pa, pb = imp(float(a)), imp(float(b))
    return pa / (pa + pb)


class Client:
    def __init__(self, key):
        self.key, self.remaining, self.spent = key, None, 0

    def get(self, path, **params):
        params["apiKey"] = self.key
        url = f"{BASE}{path}?{urllib.parse.urlencode(params, safe=',')}"
        req = urllib.request.Request(url, headers={"User-Agent": "cfb-model/1"})
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                status, headers, body = r.status, {k.lower(): v for k, v in r.headers.items()}, r.read().decode()
        except urllib.error.HTTPError as e:
            status, headers, body = e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, ""
        except Exception as e:  # noqa: BLE001
            raise Fatal(f"could not reach The Odds API ({type(e).__name__})")
        if headers.get("x-requests-remaining") is not None:
            self.remaining = int(float(headers["x-requests-remaining"]))
        if headers.get("x-requests-last") is not None:
            self.spent += int(float(headers["x-requests-last"]))
        if status == 401:
            raise Fatal("the college football odds key was rejected. Check the ODDS_API_KEY_CFB secret")
        if status == 429:
            raise Fatal("out of college football odds credits or rate limited")
        if status >= 400:
            raise Fatal(f"odds API error {status}")
        return json.loads(body)


def _load(p, default):
    try:
        return json.loads(Path(p).read_text())
    except Exception:  # noqa: BLE001
        return default


def run(games, state_path, cache_path, now, close_games=()):
    """Returns ({game_id: {player name key: {stat: {line, over, under, book}}}}, status).
    close_games: games with a locked prop play; their props get one more pull near kickoff, so the play can be
    checked against the closing line (clv.prop_clv)."""
    state, cache = _load(state_path, {}), _load(cache_path, {})
    live = {str(g["game_id"]) for g in games}
    cache = {k: v for k, v in cache.items() if k.split("|")[0] in live and v.get("rows")}   # drop played games and empty pulls
    key = C.odds_key()
    status = {"source": "espn", "props": "model", "spent": 0, "remaining": state.get("remaining")}
    if not key:
        status["note"] = "No college football odds key, so prop lines are the model's own. Type your book's line into any player."
        Path(cache_path).write_text(json.dumps(cache))
        return _props(cache), status
    cl = Client(key)
    try:
        try:
            status["game_lines"] = game_lines(cl, games, state, now)
            if status["game_lines"]:
                status["source"] = "odds_api"
        except Fatal:
            raise
        except Exception as e:  # noqa: BLE001
            log.warning(f"CFB game lines (DK stand-in) skipped: {e}")
        soon = [g for g in games if 0 < (datetime.fromisoformat(g["start"].replace("Z", "+00:00")) - now).total_seconds() / 3600 <= C.ODDS_PROP_HOURS]
        closeset = {str(x) for x in close_games}

        def due(g, m):                                  # never pulled, or one closing pull for a locked play
            ent = cache.get(f"{g['game_id']}|{m}")
            if ent is None:
                return True
            if str(g["game_id"]) not in closeset or ent.get("closed") or not ent.get("at"):
                return False
            to_ko = (datetime.fromisoformat(g["start"].replace("Z", "+00:00")) - now).total_seconds() / 3600
            age = (now - datetime.fromisoformat(ent["at"])).total_seconds() / 3600
            return 0 < to_ko <= C.ODDS_PROP_CLOSE_HOURS and age >= 6

        need = [g for g in soon if any(due(g, m) for m in C.ODDS_PROP_MARKETS)]
        if need:
            events = cl.get(f"/v4/sports/{SPORT}/events")                       # free call: event ids
            by = {}
            for ev in events:
                by[(norm_name(ev["home_team"]), norm_name(ev["away_team"]))] = ev["id"]
            days_left = monthrange(now.year, now.month)[1] - now.day + 1
            rem = cl.remaining if cl.remaining is not None else (state.get("remaining") or 500)
            week_allow = max(0, rem - C.ODDS_RESERVE) / max(1.0, days_left / 7.0)
            wk = now.strftime("%G-%V")
            if state.get("week") != wk:
                state.update({"week": wk, "spent_week": 0})
            allowance = int(week_allow) - state.get("spent_week", 0)
            # both-Power-4 games first, then by kickoff
            need.sort(key=lambda g: (not (g.get("p4_home") and g.get("p4_away")), g["start"]))
            tried = 0
            for g in need:
                eid = by.get((norm_name(g["home_full"]), norm_name(g["away_full"])))
                mk = [m for m in C.ODDS_PROP_MARKETS if due(g, m)]
                closing = {m for m in mk if f"{g['game_id']}|{m}" in cache}
                if not eid or allowance < len(mk):
                    continue
                before = cl.spent
                ev = cl.get(f"/v4/sports/{SPORT}/events/{eid}/odds", regions=C.ODDS_REGION, markets=",".join(mk),
                            oddsFormat="american", bookmakers=C.ODDS_BOOK)
                if not any(m.get("outcomes") for b in ev.get("bookmakers", []) for m in b.get("markets", [])):
                    # the preferred book has nothing up: take any US book (an empty answer costs no credits)
                    ev = cl.get(f"/v4/sports/{SPORT}/events/{eid}/odds", regions=C.ODDS_REGION, markets=",".join(mk), oddsFormat="american")
                books = sorted(ev.get("bookmakers", []), key=lambda b: BOOK_ORDER.index(b.get("key")) if b.get("key") in BOOK_ORDER else 99)
                tried += 1
                for m in mk:
                    for b in books:                              # first book in our order that posted this market
                        mm = next((x for x in b.get("markets", []) if x["key"] == m and x.get("outcomes")), None)
                        if not mm:
                            continue
                        rows = {}
                        for o in mm["outcomes"]:
                            nm = norm_name(o.get("description", ""))
                            rr = rows.setdefault(nm, {"line": 0.5 if m == "player_anytime_td" else o.get("point")})
                            rr["over" if o["name"] in ("Over", "Yes") else "under"] = o["price"]
                        cache[f"{g['game_id']}|{m}"] = {"rows": rows, "book": b.get("title"), "at": now.isoformat(), "closed": m in closing}
                        break
                used = cl.spent - before
                allowance -= used
                state["spent_week"] = state.get("spent_week", 0) + used
            got = len({k.split("|")[0] for k in cache})
            if tried and not got:
                status["note"] = "The odds key works, but no book has posted player props for these games yet. The next run checks again."
        status["props"] = "odds_api"
    except Fatal as e:
        log.warning(f"CFB odds: {e}")
        status["note"] = str(e)
    state["remaining"] = cl.remaining if cl.remaining is not None else state.get("remaining")
    status.update({"spent": cl.spent, "remaining": state.get("remaining")})
    Path(state_path).write_text(json.dumps(state))
    Path(cache_path).write_text(json.dumps(cache))
    return _props(cache), status


def _props(cache):
    props = {}
    for ck, v in cache.items():
        gid, mkt = ck.split("|")
        for nm, rr in v["rows"].items():
            if rr.get("line") is None:
                continue
            props.setdefault(int(gid), {}).setdefault(nm, {})[PROP_STAT[mkt]] = dict(rr, book=v.get("book"))
    return props
