"""
NHL odds from The Odds API, on its own free key (ODDS_API_KEY_NHL).

Budget: the key has 500 credits a month. Each run works out a daily allowance
from the credits left and the days left in the month, then spends it in this
order: game lines (moneyline, puck line, total for every game in one call,
about 3 credits), then player props game by game (1 credit per market per
game), shots on goal first. Props are cached for the day so later runs reuse
them. Without a key, the league's own free moneylines are used.
"""
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from calendar import monthrange
from datetime import datetime, timezone
from pathlib import Path

from . import config as C
from .util import norm_name

log = logging.getLogger("nhlmodel")
BASE = "https://api.the-odds-api.com"
SPORT = "icehockey_nhl"
PROP_STAT = {"player_shots_on_goal": "sog", "player_points": "points", "player_assists": "assists",
             "player_goals": "goals", "player_total_saves": "saves"}


class Fatal(Exception):
    pass


class Client:
    def __init__(self, key):
        self.key, self.remaining, self.spent = key, None, 0

    def get(self, path, **params):
        params["apiKey"] = self.key
        url = f"{BASE}{path}?{urllib.parse.urlencode(params, safe=',')}"
        req = urllib.request.Request(url, headers={"User-Agent": "nhl-model/1"})
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
            raise Fatal("the NHL odds key was rejected. Check the ODDS_API_KEY_NHL secret")
        if status == 429:
            raise Fatal("out of NHL odds credits or rate limited")
        if status >= 400:
            raise Fatal(f"odds API error {status}")
        return json.loads(body)


def _team(name, games):
    """Odds API full name -> our abbreviation, by the team nickname."""
    n = norm_name(name)
    for g in games:
        for side in ("home", "away"):
            nick = norm_name(g[f"{side}_name"])
            if nick and n.endswith(nick):
                return g[side]
    return None


def _no_vig(a, b):
    def imp(x):
        return 100 / (x + 100) if x > 0 else -x / (-x + 100)
    pa, pb = imp(a), imp(b)
    return pa / (pa + pb)


def _load(p, default):
    try:
        return json.loads(Path(p).read_text())
    except Exception:  # noqa: BLE001
        return default


def run(games, state_path, cache_path, now):
    """Fills game['book'] with lines and returns {(game_id): {pid-name-key: {stat: {...}}}} props."""
    state = _load(state_path, {})
    cache = _load(cache_path, {})
    today = now.astimezone(timezone.utc).strftime("%Y-%m-%d")
    month = today[:7]
    if state.get("month") != month:
        state.update({"month": month, "remaining": state.get("remaining") if state.get("month") else None})
    if state.get("day") != today:
        state.update({"day": today, "spent_today": 0})
    cache = {k: v for k, v in cache.items() if v.get("day") == today}
    key = C.odds_key()
    status = {"source": "league", "spent": 0}
    for g in games:                                       # free fallback: the league's posted moneylines
        if g.get("ml_home") and g.get("ml_away"):
            g["book"] = {"ml_home": g["ml_home"], "ml_away": g["ml_away"], "src": "NHL.com"}
    if not key:
        status["note"] = "no NHL odds key, using the league's free moneylines"
        return {}, status
    cl = Client(key)
    try:
        hours = (now - datetime.fromisoformat(state["lines_at"])).total_seconds() / 3600 if state.get("lines_at") else 99
        lines = state.get("lines") or {}
        if hours >= C.ODDS_LINES_EVERY_HOURS or not lines:
            data = cl.get(f"/v4/sports/{SPORT}/odds", regions=C.ODDS_REGION, markets="h2h,spreads,totals",
                          oddsFormat="american", bookmakers=C.ODDS_BOOK)
            if not data:                                   # preferred book missing: any US book
                data = cl.get(f"/v4/sports/{SPORT}/odds", regions=C.ODDS_REGION, markets="h2h,spreads,totals", oddsFormat="american")
            lines = {}
            for ev in data:
                h, a = _team(ev["home_team"], games), _team(ev["away_team"], games)
                if not h or not a:
                    continue
                for b in ev.get("bookmakers", []):
                    rec = {"event": ev["id"], "book": b.get("title"), "commence": ev.get("commence_time")}
                    for m in b.get("markets", []):
                        out = {o["name"]: o for o in m.get("outcomes", [])}
                        hn, an = ev["home_team"], ev["away_team"]
                        if m["key"] == "h2h" and hn in out and an in out:
                            rec["ml_home"], rec["ml_away"] = out[hn]["price"], out[an]["price"]
                        elif m["key"] == "spreads" and hn in out and an in out:
                            rec["pl_home"], rec["pl_home_odds"] = out[hn].get("point"), out[hn]["price"]
                            rec["pl_away_odds"] = out[an]["price"]
                        elif m["key"] == "totals" and "Over" in out and "Under" in out:
                            rec["total"], rec["over_odds"], rec["under_odds"] = out["Over"].get("point"), out["Over"]["price"], out["Under"]["price"]
                    lines[f"{a}@{h}"] = rec
                    break
            state["lines"], state["lines_at"] = lines, now.isoformat()
        for g in games:
            rec = lines.get(f"{g['away']}@{g['home']}")
            if rec:
                g["book"] = dict(rec, src=rec.get("book"))
        status["source"] = "odds_api"
        # props: today's games that haven't started, within today's allowance
        days_left = monthrange(now.year, now.month)[1] - now.day + 1
        rem = cl.remaining if cl.remaining is not None else state.get("remaining") or 500
        daily = max(0, (rem - C.ODDS_RESERVE)) / days_left
        allowance = int(daily) - 6 - state.get("spent_today", 0)          # keep room for line pulls
        et_hour = (now.astimezone(timezone.utc).hour - 4) % 24
        todo = [g for g in games if g.get("book", {}).get("event") and g["date_et"] == g["today_et"]]
        if et_hour >= 13:                                  # props are posted by early afternoon
            for mkt in C.ODDS_PROP_MARKETS:
                for g in sorted(todo, key=lambda x: x["start"]):
                    ck = f"{g['game_id']}|{mkt}"
                    if ck in cache or allowance < 1:
                        continue
                    ev = cl.get(f"/v4/sports/{SPORT}/events/{g['book']['event']}/odds", regions=C.ODDS_REGION,
                                markets=mkt, oddsFormat="american", bookmakers=C.ODDS_BOOK)
                    rows = {}
                    for b in ev.get("bookmakers", []):
                        for m in b.get("markets", []):
                            for o in m.get("outcomes", []):
                                nm = norm_name(o.get("description", ""))
                                r = rows.setdefault(nm, {"line": o.get("point")})
                                r["over" if o["name"] == "Over" else "under"] = o["price"]
                        break
                    cache[ck] = {"day": today, "rows": rows, "book": (ev.get("bookmakers") or [{}])[0].get("title")}
                    allowance -= 1
                    state["spent_today"] = state.get("spent_today", 0) + 1
    except Fatal as e:
        log.warning(f"NHL odds: {e}")
        status["note"] = str(e)
    state["remaining"] = cl.remaining if cl.remaining is not None else state.get("remaining")
    status.update({"spent": cl.spent, "remaining": state.get("remaining")})
    Path(state_path).write_text(json.dumps(state))
    Path(cache_path).write_text(json.dumps(cache))
    props = {}
    for ck, v in cache.items():
        gid, mkt = ck.split("|")
        for nm, r in v["rows"].items():
            if r.get("line") is None:
                continue
            props.setdefault(int(gid), {}).setdefault(nm, {})[PROP_STAT[mkt]] = dict(r, book=v.get("book"))
    return props, status


no_vig = _no_vig
