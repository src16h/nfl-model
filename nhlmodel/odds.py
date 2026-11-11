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
from zoneinfo import ZoneInfo

from . import config as C
from .util import norm_name

import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import standin as SI  # noqa: E402
import clv as CLV  # noqa: E402

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


def _parse_book(ev, b):
    rec = {"event": ev["id"], "book": b.get("title"), "commence": ev.get("commence_time")}
    hn, an = ev["home_team"], ev["away_team"]
    for m in b.get("markets", []):
        out = {o["name"]: o for o in m.get("outcomes", [])}
        if m["key"] == "h2h" and hn in out and an in out:
            rec["ml_home"], rec["ml_away"] = out[hn]["price"], out[an]["price"]
        elif m["key"] == "spreads" and hn in out and an in out:
            rec["pl_home"], rec["pl_home_odds"] = out[hn].get("point"), out[hn]["price"]
            rec["pl_away_odds"] = out[an]["price"]
        elif m["key"] == "totals" and "Over" in out and "Under" in out:
            rec["total"], rec["over_odds"], rec["under_odds"] = out["Over"].get("point"), out["Over"]["price"], out["Under"]["price"]
    return rec


def _lines_for(ev):
    """Bet book: the first of C.ODDS_BOOKS (Hard Rock first) with a moneyline; a missing puck line or total is filled
    from the next book. Pinnacle's lines ride along as rec['sharp'], the referee price."""
    books = {b["key"]: b for b in ev.get("bookmakers", [])}
    rec = None
    for k in [k for k in C.ODDS_BOOKS if k in books]:
        r = _parse_book(ev, books[k])
        if rec is None:
            if "ml_home" in r:
                rec = r
            continue
        for f in (("pl_home", "pl_home_odds", "pl_away_odds"), ("total", "over_odds", "under_odds")):
            if f[0] not in rec and f[0] in r:
                rec.update({x: r[x] for x in f})
    ks = None                                                    # Hard Rock only (standin.py, Nov 3 2026)
    if rec is None and not (ks and "ml_home" in ks):
        return None
    hr_name = (rec or {}).get("book")
    rec = SI.apply(rec, ks, [(None, "ml_home", "ml_away"), ('pl_home', 'pl_home_odds', 'pl_away_odds'), ("total", "over_odds", "under_odds")])
    rec.update({"event": ev["id"], "commence": ev.get("commence_time"), "hr_book": hr_name,
                "book": hr_name})
    for k in C.SHARP_BOOKS:
        if k in books:
            sh = _parse_book(ev, books[k])
            rec["sharp"] = {x: v for x, v in sh.items() if x not in ("event", "commence")}
            break
    return rec


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


def run(games, state_path, cache_path, now, close_games=(), shadow_games=()):
    """Fills game['book'] with lines and returns {(game_id): {pid-name-key: {stat: {...}}}} props.
    close_games: games with a locked prop play; their props get one more pull near puck drop, so the
    play can be checked against the closing line (clv.prop_clv)."""
    state = _load(state_path, {})
    cache = _load(cache_path, {})
    today = now.astimezone(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")   # ET day: a 9pm run must not spend tomorrow's budget (Nov 5 2026)
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
    cl = Client(key)
    if not key:
        status["note"] = "no NHL odds key, using the league's free moneylines"
        Path(cache_path).write_text(json.dumps(cache))
        for g in games:                                   # lines saved by an earlier keyed run still count
            rec = (state.get("lines") or {}).get(f"{g['away']}@{g['home']}")
            if rec:
                g["book"] = dict(rec, src=rec.get("book"))
        return _props(cache), status
    try:
        hours = (now - datetime.fromisoformat(state["lines_at"])).total_seconds() / 3600 if state.get("lines_at") else 99
        lines = state.get("lines") or {}
        soon = [g for g in games if 0 <= (datetime.fromisoformat(g["start"].replace("Z", "+00:00")) - now).total_seconds() / 3600
                <= C.ODDS_PREKO_HOURS]
        due = hours >= C.ODDS_LINES_EVERY_HOURS or not lines or (soon and hours >= 1.0)    # near puck drop: near-closing prices
        if due:
            # one call, up to 10 books = same credits as one book: Hard Rock (where you bet) first, Pinnacle kept as the referee
            data = cl.get(f"/v4/sports/{SPORT}/odds", markets="h2h,spreads,totals", oddsFormat="american",
                          bookmakers=",".join(C.ODDS_BOOKS + C.SHARP_BOOKS))
            lines = {}
            for ev in data:
                h, a = _team(ev["home_team"], games), _team(ev["away_team"], games)
                if not h or not a:
                    continue
                rec = _lines_for(ev)
                try:                                          # only games in the next 2 days: the feed also lists
                    ct = datetime.fromisoformat(str(ev.get("commence_time")).replace("Z", "+00:00"))   # rematches weeks out
                except ValueError:
                    ct = None
                if rec and ct is not None and (ct - now).total_seconds() > 48 * 3600:
                    continue
                k_ = f"{a}@{h}"
                if rec and (k_ not in lines or str(rec.get("commence")) < str(lines[k_].get("commence"))):
                    lines[k_] = rec                           # same pair twice: keep the sooner game
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
        et_hour = now.astimezone(ZoneInfo("America/New_York")).hour
        _st = lambda g: datetime.fromisoformat(g["start"].replace("Z", "+00:00"))
        todo = [g for g in games if g.get("book", {}).get("event") and g["date_et"] == g["today_et"] and _st(g) > now]   # started games: no pulls
        # Closing prices first (Nov 11 2026). A locked prop play gets one more pull of its own market near the start,
        # so it can be checked against the closing line (clv.prop_clv). Before this, a closing pull needed the
        # day's allowance to still have a credit by the evening run, after the afternoon's props and alt lines
        # (NHL: 2 of 102 plays ended up priced, NBA: 6 of 75). Now: paid from the day's allowance when it has room; otherwise taken anyway
        # (down to the month's reserve) and written down as a debt that the alt-line pulls below pay back, one
        # skipped alt pull per closing pull (at most ALT_CUT_SHARE of a run's alt pulls, and no more closing pulls on
        # credit once CLOSE_DEBT_MAX is owed). Shadow plays (paused types) get theirs only from the day's allowance.
        debt = int(state.get("close_debt", 0) or 0)
        left = lambda: (cl.remaining if cl.remaining is not None else rem) - C.ODDS_RESERVE
        for g in sorted(todo, key=lambda x: x["start"]):
            for mkt in list(C.ODDS_PROP_MARKETS) + [m for m in getattr(C, "SHADOW_PROP_MARKETS", []) if m not in C.ODDS_PROP_MARKETS]:
                ck = f"{g['game_id']}|{mkt}"
                if ck not in cache or not _close_due(cache[ck], g, now):
                    continue
                real = CLV.wants_close(close_games, g["game_id"], PROP_STAT[mkt])
                if not real and not CLV.wants_close(shadow_games, g["game_id"], PROP_STAT[mkt]):
                    continue
                owed = allowance < 1
                if owed and (not real or left() < 1 or debt >= getattr(C, "CLOSE_DEBT_MAX", 6)):
                    status["close_missed"] = status.get("close_missed", 0) + 1
                    continue
                rows, used = _pull_props(cl, g, mkt)
                cache[ck] = {"day": today, "rows": rows, "book": used, "at": now.isoformat(), "closed": True}
                state["spent_today"] = state.get("spent_today", 0) + 1
                status["close_pulls"] = status.get("close_pulls", 0) + 1
                if owed:
                    debt += 1
                else:
                    allowance -= 1
        # floor (Nov 5 2026): every game still to play gets its main prop market and its main alt market, even when the
        # daily share is used up, as long as the month's reserve holds. Those two come first; the rest gets what's left.
        # Nov 11 2026: the alt half of the floor shrinks by the closing-pull debt (latest games lose their alt pull first).
        skip = state.get("alt_skip") or {}
        skipped = set(skip.get("ids", [])) if skip.get("day") == today else set()
        need_p = [g for g in todo if f"{g['game_id']}|{C.ODDS_PROP_MARKETS[0]}" not in cache]
        need_a = [g for g in todo if (_st(g) - now).total_seconds() / 3600 <= C.ALT_HOURS and f"alt:{g['game_id']}:{C.ALT_MARKETS[0]}" not in cache and g['game_id'] not in skipped]
        spare = max(0, left() - 6)
        alt_floor = len(need_a) - min(max(debt, 0), int(len(need_a) * getattr(C, "ALT_CUT_SHARE", 0.5) + 0.5))
        floor = min(len(need_p) + alt_floor, spare)
        if allowance < floor:
            status["floor"] = {"allowance": allowance, "raised_to": floor}
            allowance = floor
            cut = sorted(need_a, key=lambda x: x["start"])[alt_floor:]
            if cut:
                debt -= len(cut)
                skipped |= {g["game_id"] for g in cut}
                status["alt_skipped"] = len(cut)
        elif debt:                                         # room to spare: pay the debt out of what the extra alt markets would get
            pay = max(0, min(debt, allowance - len(need_p) - len(need_a)))
            allowance -= pay
            debt -= pay
        state["close_debt"], state["alt_skip"] = debt, {"day": today, "ids": sorted(skipped)}
        status["close_debt"] = debt
        hold = len([g for g in need_a if g["game_id"] not in skipped])   # kept for main alt lines while the other prop markets pull
        soon_start = any(0 <= (datetime.fromisoformat(g["start"].replace("Z", "+00:00")) - now).total_seconds() / 3600 <= 4 for g in todo)
        if et_hour >= 13 or soon_start:                    # props are posted by early afternoon; matinees need them sooner (Oct 31 2026)
            for mkt in C.ODDS_PROP_MARKETS:
                for g in sorted(todo, key=lambda x: x["start"]):
                    ck = f"{g['game_id']}|{mkt}"
                    if ck in cache or allowance - (0 if mkt == C.ODDS_PROP_MARKETS[0] else hold) < 1:
                        continue
                    rows, used = _pull_props(cl, g, mkt)
                    cache[ck] = {"day": today, "rows": rows, "book": used, "at": now.isoformat(), "closed": False}
                    allowance -= 1
                    state["spent_today"] = state.get("spent_today", 0) + 1
            # alt lines and team totals: whatever today's allowance has left, soonest games first (altlines.py)
            alt_todo = [g for g in todo if 0 <= (datetime.fromisoformat(g["start"].replace("Z", "+00:00")) - now).total_seconds() / 3600
                        <= C.ALT_HOURS]
            for mkt in C.ALT_MARKETS:
                for g in sorted(alt_todo, key=lambda x: x["start"]):
                    ck = f"alt:{g['game_id']}:{mkt}"
                    if ck in cache or allowance < 1 or g["game_id"] in skipped:
                        continue
                    ev = cl.get(f"/v4/sports/{SPORT}/events/{g['book']['event']}/odds",
                                markets=mkt, oddsFormat="american", bookmakers=",".join(C.ALT_BOOKS))
                    bks = {b["key"]: b for b in ev.get("bookmakers", [])}
                    bet = next((k for k in C.ALT_BOOKS if k in bks and k not in C.SHARP_BOOKS), None)
                    shp = next((k for k in C.SHARP_BOOKS if k in bks), None)
                    blended = SI.rows(_alt_rows(ev, bks[bet], mkt) if bet else [])
                    cache[ck] = {"day": today, "book": blended,
                                 "sharp": _alt_rows(ev, bks[shp], mkt) if shp else [], "book_name": bks[bet].get("title") if bet else None}
                    allowance -= 1
                    state["spent_today"] = state.get("spent_today", 0) + 1
                    status["alt_pulls"] = status.get("alt_pulls", 0) + 1
                    if mkt == C.ALT_MARKETS[0]:
                        hold = max(0, hold - 1)
            # shadow pulls: paused prop types (gates.py), only with credits left over, so would-be plays can be graded
            for mkt in getattr(C, "SHADOW_PROP_MARKETS", []):
                for g in sorted(todo, key=lambda x: x["start"]):
                    ck = f"{g['game_id']}|{mkt}"
                    if ck in cache or allowance < 1:
                        continue
                    rows, used = _pull_props(cl, g, mkt)
                    cache[ck] = {"day": today, "rows": rows, "book": used, "at": now.isoformat(), "closed": False}
                    allowance -= 1
                    state["spent_today"] = state.get("spent_today", 0) + 1
                    status["shadow_pulls"] = status.get("shadow_pulls", 0) + 1
        if et_hour >= 13 or soon_start:
            dark = [f"{g['away']}@{g['home']}" for g in todo if f"{g['game_id']}|{C.ODDS_PROP_MARKETS[0]}" not in cache]
            if dark:
                status["note"] = f"No props pulled yet for {', '.join(dark)}: out of odds credits ({rem} left this month)"
                log.warning(status["note"])
    except Fatal as e:
        log.warning(f"NHL odds: {e}")
        status["note"] = str(e)
    state["remaining"] = cl.remaining if cl.remaining is not None else state.get("remaining")
    status.update({"spent": cl.spent, "remaining": state.get("remaining")})
    Path(state_path).write_text(json.dumps(state))
    Path(cache_path).write_text(json.dumps(cache))
    return _props(cache), status


def _alt_rows(ev, b, mkt):
    """Bets in altlines.py form from one book's market."""
    hn, an = ev["home_team"], ev["away_team"]
    rows = []
    for m in b.get("markets", []):
        for o in m.get("outcomes", []):
            pt, pr = o.get("point"), o.get("price")
            if pt is None or pr is None:
                continue
            if m["key"] in ("spreads", "alternate_spreads") and o["name"] in (hn, an):
                side = "home" if o["name"] == hn else "away"
                rows.append({"market": "spread", "team": side, "side": side, "line": float(pt), "odds": pr})
            elif m["key"] in ("totals", "alternate_totals") and o["name"] in ("Over", "Under"):
                rows.append({"market": "total", "team": None, "side": o["name"].lower(), "line": float(pt), "odds": pr})
            elif m["key"] in ("team_totals", "alternate_team_totals") and o["name"] in ("Over", "Under") and o.get("description") in (hn, an):
                rows.append({"market": "team_total", "team": "home" if o["description"] == hn else "away", "side": o["name"].lower(),
                             "line": float(pt), "odds": pr})
    return rows


def _pull_props(cl, g, mkt):
    """One prop market for one game: ({player name key: {line, over, under, bk, book}}, first book used).
    Hard Rock first; a player missing there is filled from the next book."""
    ev = cl.get(f"/v4/sports/{SPORT}/events/{g['book']['event']}/odds",
                markets=mkt, oddsFormat="american", bookmakers=",".join(C.PROP_BOOKS))
    rows, used = {}, None
    bks = {b["key"]: b for b in ev.get("bookmakers", [])}
    for k in [k for k in C.PROP_BOOKS if k in bks]:
        for m in bks[k].get("markets", []):
            for o in m.get("outcomes", []):
                nm = norm_name(o.get("description", ""))
                if nm in rows and rows[nm].get("bk") != k:
                    continue
                r = rows.setdefault(nm, {"line": o.get("point"), "bk": k, "book": bks[k].get("title")})
                r["over" if o["name"] == "Over" else "under"] = o["price"]
        used = used or bks[k].get("title")
    return rows, used


def _close_due(ent, g, now):
    """Is this game's saved prop market due its one closing pull? Inside PROP_CLOSE_HOURS of the start, and the saved
    price an hour old or more. (Whether the market holds a locked play is checked by the caller.)"""
    if not getattr(C, "PROP_CLOSE_PULL", True) or ent.get("closed"):
        return False
    try:
        to_start = (datetime.fromisoformat(g["start"].replace("Z", "+00:00")) - now).total_seconds() / 3600
        age = (now - datetime.fromisoformat(ent["at"])).total_seconds() / 3600 if ent.get("at") else 99
    except (ValueError, KeyError):
        return False
    return 0 < to_start <= getattr(C, "PROP_CLOSE_HOURS", C.ODDS_PREKO_HOURS + 0.5) and age >= 1.0


def alt_lines(cache):
    """{game_id: {"book": [...], "sharp": [...], "book_name": str}} from today's alt pulls."""
    out = {}
    for ck, v in cache.items():
        if not ck.startswith("alt:"):
            continue
        gid = int(ck.split(":")[1])
        o = out.setdefault(gid, {"book": [], "sharp": [], "book_name": None, "markets": []})
        o["book"] += v.get("book", [])
        o["sharp"] += v.get("sharp", [])
        o["book_name"] = o["book_name"] or v.get("book_name")
        o["markets"].append(ck.split(":")[2])
    return out


def _props(cache):
    props = {}
    for ck, v in cache.items():
        if ck.startswith("alt:"):
            continue
        gid, mkt = ck.split("|")
        for nm, r in v["rows"].items():
            if r.get("line") is None:
                continue
            props.setdefault(int(gid), {}).setdefault(nm, {})[PROP_STAT[mkt]] = dict(r, book=r.get("book") or v.get("book"),
                                                                                  pulled=v.get("at"))   # when this price was fetched
    return props


no_vig = _no_vig
