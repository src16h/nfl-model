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


BOOK_ORDER = ["draftkings", "fanduel", "betmgm", "williamhill_us", "espnbet", "hardrockbet", "betrivers", "fanatics", "bovada"]


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


def run(games, state_path, cache_path, now):
    """Returns ({game_id: {player name key: {stat: {line, over, under, book}}}}, status)."""
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
        soon = [g for g in games if 0 < (datetime.fromisoformat(g["start"].replace("Z", "+00:00")) - now).total_seconds() / 3600 <= C.ODDS_PROP_HOURS]
        need = [g for g in soon if any(f"{g['game_id']}|{m}" not in cache for m in C.ODDS_PROP_MARKETS)]
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
                mk = [m for m in C.ODDS_PROP_MARKETS if f"{g['game_id']}|{m}" not in cache]
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
                        cache[f"{g['game_id']}|{m}"] = {"rows": rows, "book": b.get("title"), "at": now.isoformat()}
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
