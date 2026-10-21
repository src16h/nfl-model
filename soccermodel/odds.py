"""
Soccer odds from The Odds API, on its own free key (ODDS_API_KEY_SOCCER).

Budget: 500 credits a month. One league pull (1X2, totals and spreads from up to 10 named books)
costs 3 credits. Each run works out a daily allowance from the credits left and the days left in
the month, then refreshes leagues with matches in the next 3 days, soonest kickoff first, each at
most every ODDS_EVERY_HOURS. BTTS, draw no bet and player props cost a credit per match, so the
model prices those itself and you type the book's price.
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
from .teams import canon

log = logging.getLogger("soccermodel")
BASE = "https://api.the-odds-api.com"


class Fatal(Exception):
    pass


class Client:
    def __init__(self, key):
        self.key, self.remaining, self.spent = key, None, 0

    def get(self, path, **params):
        params["apiKey"] = self.key
        url = f"{BASE}{path}?{urllib.parse.urlencode(params, safe=',')}"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "soccer-model/1"}), timeout=25) as r:
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
            raise Fatal("the soccer odds key was rejected. Check the ODDS_API_KEY_SOCCER secret")
        if status == 429:
            raise Fatal("out of soccer odds credits or rate limited")
        if status >= 400:
            raise Fatal(f"odds API error {status}")
        return json.loads(body)


def _load(p, default):
    try:
        return json.loads(Path(p).read_text())
    except Exception:  # noqa: BLE001
        return default


def _parse(ev, book):
    hn, an = ev["home_team"], ev["away_team"]
    rec = {"event": ev["id"], "book": book.get("title"), "commence": ev.get("commence_time"),
           "home": canon(hn), "away": canon(an)}
    for m in book.get("markets", []):
        out = {o["name"]: o for o in m.get("outcomes", [])}
        if m["key"] == "h2h" and hn in out and an in out and "Draw" in out:
            rec["ml_home"], rec["ml_draw"], rec["ml_away"] = out[hn]["price"], out["Draw"]["price"], out[an]["price"]
        elif m["key"] == "spreads" and hn in out and an in out:
            rec["ah_home"], rec["ah_home_odds"], rec["ah_away_odds"] = out[hn].get("point"), out[hn]["price"], out[an]["price"]
        elif m["key"] == "totals" and "Over" in out and "Under" in out:
            rec["total"], rec["over_odds"], rec["under_odds"] = out["Over"].get("point"), out["Over"]["price"], out["Under"]["price"]
    return rec


def _alt_rows(ev, b):
    """Bets in altlines.py form (team names canonical home/away; DNB = handicap 0)."""
    hn, an = ev.get("home_team"), ev.get("away_team")
    rows = []
    for m in b.get("markets", []):
        k = m.get("key", "")
        for o in m.get("outcomes", []):
            pt, pr, nm = o.get("point"), o.get("price"), o.get("name")
            if pr is None:
                continue
            if k == "btts" and nm in ("Yes", "No"):
                rows.append({"market": "btts", "team": None, "side": nm.lower(), "line": 0.0, "odds": pr})
            elif k == "draw_no_bet" and nm in (hn, an):
                sd = "home" if nm == hn else "away"
                rows.append({"market": "spread", "team": sd, "side": sd, "line": 0.0, "odds": pr})
            elif k in ("spreads", "alternate_spreads") and nm in (hn, an) and pt is not None:
                sd = "home" if nm == hn else "away"
                rows.append({"market": "spread", "team": sd, "side": sd, "line": float(pt), "odds": pr})
            elif k in ("totals", "alternate_totals") and nm in ("Over", "Under") and pt is not None:
                rows.append({"market": "total", "team": None, "side": nm.lower(), "line": float(pt), "odds": pr})
            elif k in ("team_totals", "alternate_team_totals") and nm in ("Over", "Under") and pt is not None and o.get("description") in (hn, an):
                rows.append({"market": "team_total", "team": "home" if o["description"] == hn else "away", "side": nm.lower(),
                             "line": float(pt), "odds": pr})
    return rows


def _best_book(ev):
    """Bet book: first book in our preference list (Hard Rock first) that has the 1X2; spreads/totals filled from the
    next books if missing. Pinnacle (else the Betfair exchange) is kept separately as the sharp reference."""
    books = {b["key"]: b for b in ev.get("bookmakers", [])}
    sharp = None
    for k in C.SHARP_BOOKS:
        if k in books:
            r = _parse(ev, books[k])
            sharp = {x: r[x] for x in r if x not in ("event", "commence", "home", "away")}
            break
    bet_books = [k for k in C.ODDS_BOOKS if k not in C.SHARP_BOOKS]
    order = [k for k in bet_books if k in books] + [k for k in books if k not in C.ODDS_BOOKS]
    if not order:                                     # only sharp books posted: bet off them
        order = [k for k in C.SHARP_BOOKS if k in books]
    rec = None
    for k in order:
        r = _parse(ev, books[k])
        if rec is None:
            if "ml_home" in r:
                rec = r
            continue
        for f in (("ah_home", "ah_home_odds", "ah_away_odds"), ("total", "over_odds", "under_odds")):
            if f[0] not in rec and f[0] in r:
                rec.update({x: r[x] for x in f})
                rec.setdefault("book_extra", r["book"])
    if rec is not None and sharp:
        rec["sharp"] = sharp
    return rec


def run(games, state_path, now):
    """games: list of fixture dicts (league, home, away, start). Fills g['book'] in place. Returns a status dict."""
    state = _load(state_path, {})
    month, today = now.strftime("%Y-%m"), now.strftime("%Y-%m-%d")
    if state.get("month") != month:
        state.update({"month": month, "remaining": None})
    if state.get("day") != today:
        state.update({"day": today, "spent_today": 0})
    lines = state.setdefault("lines", {})              # "league|away@home" -> record
    pulled = state.setdefault("pulled", {})            # league -> iso time
    key = C.odds_key()
    status = {"source": "none", "spent": 0}
    cl = Client(key)
    if key:
        try:
            soon = {}
            for g in games:
                st = datetime.fromisoformat(g["start"].replace("Z", "+00:00"))
                if now <= st <= now + timedelta(days=3):
                    soon[g["league"]] = min(soon.get(g["league"], st), st)
            days_left = monthrange(now.year, now.month)[1] - now.day + 1
            rem = state.get("remaining") if state.get("remaining") is not None else 500
            allowance = int(max(0, rem - C.ODDS_RESERVE) / days_left * 1.5) - state.get("spent_today", 0)
            for lg, _ in sorted(soon.items(), key=lambda x: x[1]):
                last = pulled.get(lg)
                hours = (now - datetime.fromisoformat(last)).total_seconds() / 3600 if last else 99
                to_ko = (soon[lg] - now).total_seconds() / 3600
                due = hours >= C.ODDS_EVERY_HOURS or (to_ko <= C.ODDS_PREKO_HOURS and hours >= 1.5)   # closing prices for CLV
                if not due or allowance < 3:
                    continue
                data = cl.get(f"/v4/sports/{C.LEAGUES[lg]['odds']}/odds", markets=C.ODDS_MARKETS,
                              oddsFormat="american", bookmakers=",".join(C.ODDS_BOOKS))
                spent = 3
                allowance -= spent
                state["spent_today"] = state.get("spent_today", 0) + spent
                lines = {k: v for k, v in lines.items() if not k.startswith(lg + "|")}
                for ev in data:
                    rec = _best_book(ev)
                    if rec:
                        lines[f"{lg}|{rec['away']}@{rec['home']}"] = rec
                pulled[lg] = now.isoformat()
            state["lines"] = lines
            status["source"] = "odds_api"
            # more markets (BTTS, draw no bet, alt handicaps and totals, team totals): what the allowance has left
            alt = {k: v for k, v in (state.get("alt") or {}).items() if k in lines or "|" in k}
            soon_m = []
            for g in games:
                st = datetime.fromisoformat(g["start"].replace("Z", "+00:00"))
                rec = lines.get(f"{g['league']}|{g['away']}@{g['home']}")
                if rec and rec.get("event") and now <= st <= now + timedelta(hours=C.ALT_HOURS):
                    soon_m.append((st, g, rec["event"]))
            for mkt in C.ALT_MARKETS:
                for st, g, evid in sorted(soon_m, key=lambda x: x[0]):
                    key = f"{g['league']}|{g['away']}@{g['home']}"
                    ent = alt.setdefault(key, {"day": today, "markets": {}})
                    if mkt in ent["markets"] or allowance - 1 < C.ALT_KEEP:
                        continue
                    ev = cl.get(f"/v4/sports/{C.LEAGUES[g['league']]['odds']}/events/{evid}/odds", markets=mkt,
                                oddsFormat="american", bookmakers=",".join(C.ODDS_BOOKS))
                    allowance -= 1
                    state["spent_today"] = state.get("spent_today", 0) + 1
                    bks = {b["key"]: b for b in (ev or {}).get("bookmakers", [])}
                    bet = next((k for k in C.ODDS_BOOKS if k in bks and k not in C.SHARP_BOOKS), None)
                    shp = next((k for k in C.SHARP_BOOKS if k in bks), None)
                    ent["markets"][mkt] = {"book": _alt_rows(ev, bks[bet]) if bet else [], "sharp": _alt_rows(ev, bks[shp]) if shp else [],
                                           "book_name": bks[bet].get("title") if bet else None, "at": now.isoformat(timespec="minutes")}
                    status["alt_pulls"] = status.get("alt_pulls", 0) + 1
            state["alt"] = {k: v for k, v in alt.items() if v.get("day", today) >= (now - timedelta(days=2)).strftime("%Y-%m-%d")}
        except Fatal as e:
            log.warning(f"soccer odds: {e}")
            status["note"] = str(e)
    else:
        status["note"] = "no soccer odds key yet: model lines only, type in your book's price"
    for g in games:
        rec = lines.get(f"{g['league']}|{g['away']}@{g['home']}")
        if rec:
            g["book"] = dict(rec)
        ent = (state.get("alt") or {}).get(f"{g['league']}|{g['away']}@{g['home']}")
        if ent and ent.get("markets"):
            ms = ent["markets"]
            g["alt_book"] = {"book": [r for v in ms.values() for r in v.get("book", [])], "sharp": [r for v in ms.values() for r in v.get("sharp", [])],
                             "book_name": next((v.get("book_name") for v in ms.values() if v.get("book_name")), None), "markets": list(ms)}
            if status["source"] == "none":
                status["source"] = "saved"
    state["remaining"] = cl.remaining if cl.remaining is not None else state.get("remaining")
    status.update({"spent": cl.spent, "remaining": state.get("remaining")})
    Path(state_path).parent.mkdir(parents=True, exist_ok=True)
    Path(state_path).write_text(json.dumps(state))
    return status
