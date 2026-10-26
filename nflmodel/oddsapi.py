"""
Live odds from The Odds API (optional, switches on when an API key is present).

What it does each run
  1. Lists upcoming NFL games (free, no credits).
  2. Fetches live spreads and totals for all games (about 2 credits total).
  3. Fetches player props game by game, for games kicking off soon, at most
     once per REFRESH window (about 1 credit per prop market per game).
     Props are cached so later runs reuse them without spending credits.
  4. Turns everything into the same rows you would type into data/props.csv.

Safety rules
  - No key, bad key, no credits, or no internet: the run carries on with the
    free data feed and your manual props.csv. It never stops the model.
  - A per-run credit cap and a monthly reserve stop runaway spending.
  - The key is read from the ODDS_API_KEY secret and never written to any file or log.
"""
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from .util import clean_json, norm_name

log = logging.getLogger("nflmodel")
BASE = "https://api.the-odds-api.com"
SPORT = "americanfootball_nfl"

TEAM_ABBR = {
    "Arizona Cardinals": "ARI", "Atlanta Falcons": "ATL", "Baltimore Ravens": "BAL", "Buffalo Bills": "BUF",
    "Carolina Panthers": "CAR", "Chicago Bears": "CHI", "Cincinnati Bengals": "CIN", "Cleveland Browns": "CLE",
    "Dallas Cowboys": "DAL", "Denver Broncos": "DEN", "Detroit Lions": "DET", "Green Bay Packers": "GB",
    "Houston Texans": "HOU", "Indianapolis Colts": "IND", "Jacksonville Jaguars": "JAX",
    "Kansas City Chiefs": "KC", "Los Angeles Rams": "LA", "Los Angeles Chargers": "LAC",
    "Las Vegas Raiders": "LV", "Miami Dolphins": "MIA", "Minnesota Vikings": "MIN",
    "New England Patriots": "NE", "New Orleans Saints": "NO", "New York Giants": "NYG",
    "New York Jets": "NYJ", "Philadelphia Eagles": "PHI", "Pittsburgh Steelers": "PIT",
    "Seattle Seahawks": "SEA", "San Francisco 49ers": "SF", "Tampa Bay Buccaneers": "TB",
    "Tennessee Titans": "TEN", "Washington Commanders": "WAS",
}
ABBR_TEAM = {v: k for k, v in TEAM_ABBR.items()}

# The Odds API market key -> the stat names the model uses
MARKETS = {
    "player_pass_yds": "pass_yds", "player_pass_tds": "pass_td", "player_pass_completions": "pass_cmp",
    "player_pass_interceptions": "pass_int", "player_pass_attempts": "pass_att",
    "player_rush_yds": "rush_yds", "player_rush_attempts": "carries",
    "player_receptions": "rec", "player_reception_yds": "rec_yds",
    "player_rush_reception_yds": "rush_rec_yds", "player_anytime_td": "anytime_td",
    "player_tds_over": "tds",
}


class OddsError(Exception):
    """Something went wrong talking to the odds service (run carries on)."""


class OddsFatal(OddsError):
    """Bad key or out of credits: stop asking for the rest of this run."""


def _http_get(url: str, timeout: int = 25):
    """Returns (status, headers with lowercase names, body text). Tests replace this."""
    req = urllib.request.Request(url, headers={"User-Agent": "nfl-model/5"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            pass
        return e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, body


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _num(v):
    try:
        x = float(v)
        return x if np.isfinite(x) else None
    except (TypeError, ValueError):
        return None


class Client:
    def __init__(self, key: str):
        self.key = key
        self.remaining = None
        self.used = None
        self.spent = 0      # credits spent during this run

    def get(self, path: str, est_cost: int = 0, **params):
        q = dict(params)
        q["apiKey"] = self.key
        url = f"{BASE}{path}?{urllib.parse.urlencode(q, safe=',')}"
        try:
            status, headers, body = _http_get(url)
        except Exception as e:  # noqa: BLE001
            raise OddsFatal(f"could not reach The Odds API ({type(e).__name__})")
        rem, used, last = (_int(headers.get(h)) for h in ("x-requests-remaining", "x-requests-used", "x-requests-last"))
        if rem is not None:
            self.remaining = rem
        if used is not None:
            self.used = used
        if status == 401:
            raise OddsFatal("the API key was rejected. Check the ODDS_API_KEY secret in GitHub")
        if status == 429:
            raise OddsFatal("out of credits or rate limited")
        if status >= 400:
            raise OddsError(f"API error {status}: {body[:100].replace(self.key, '***')}")
        self.spent += last if last is not None else est_cost
        try:
            return json.loads(body)
        except ValueError:
            raise OddsError("unreadable response from The Odds API")


# ---------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------
def _rank(book_key) -> int:
    try:
        return C.ODDS_BOOKS.index(book_key)
    except ValueError:
        return len(C.ODDS_BOOKS)


def _far(commence, ko, hours=60) -> bool:
    """True when the feed's kickoff is clearly a different game than ours."""
    if not commence or ko is None:
        return False
    try:
        t = datetime.fromisoformat(str(commence).replace("Z", "+00:00"))
        return abs((t - ko).total_seconds()) > hours * 3600
    except (ValueError, TypeError):
        return False


def _fmt_odds(p) -> str:
    p = int(round(float(p)))
    return f"+{p}" if p > 0 else str(p)


def list_events(client: Client):
    data = client.get(f"/v4/sports/{SPORT}/events", dateFormat="iso")
    if not isinstance(data, list):
        raise OddsError("unexpected events response")
    return data


def match_events(todo: pd.DataFrame, events: list) -> dict:
    """Our game_id -> the feed's event, matched by the two teams."""
    pairs = {}
    for ev in events:
        h, a = TEAM_ABBR.get(ev.get("home_team")), TEAM_ABBR.get(ev.get("away_team"))
        if h and a:
            pairs.setdefault(frozenset((h, a)), []).append(ev)
    out = {}
    for _, g in todo.iterrows():
        cands = [e for e in pairs.get(frozenset((g["home_team"], g["away_team"])), [])
                 if not _far(e.get("commence_time"), g.get("ko"))]
        if cands:
            out[g["game_id"]] = cands[0]
    return out


# ---------------------------------------------------------------------
# game lines (spreads and totals)
# ---------------------------------------------------------------------
def _one_book(b, home_full):
    """Spread (home margin convention), spread prices, total and total prices, moneylines from one book."""
    out = {}
    for m in b.get("markets", []):
        oc = m.get("outcomes", [])
        if m.get("key") == "spreads":
            hm = next((o for o in oc if o.get("name") == home_full), None)
            aw = next((o for o in oc if o.get("name") != home_full), None)
            if hm and aw and _num(hm.get("point")) is not None:
                out.update({"spread_line": -_num(hm["point"]), "spread_home_odds": _num(hm.get("price")),
                            "spread_away_odds": _num(aw.get("price"))})
        elif m.get("key") == "totals":
            ov = next((o for o in oc if str(o.get("name", "")).lower() == "over"), None)
            un = next((o for o in oc if str(o.get("name", "")).lower() == "under"), None)
            if ov and un and _num(ov.get("point")) is not None:
                out.update({"total_line": _num(ov["point"]), "over_odds": _num(ov.get("price")), "under_odds": _num(un.get("price"))})
        elif m.get("key") == "h2h":
            prices = {o.get("name"): _num(o.get("price")) for o in oc}
            hp = prices.get(home_full)
            ap = next((v for k, v in prices.items() if k != home_full and k != "Draw"), None)
            if hp is not None and ap is not None:
                out.update({"ml_home": hp, "ml_away": ap})
    return out


def _parse_lines(ev: dict, home_abbr: str):
    """spread_line follows the data feed's convention: the home team's expected margin."""
    home_full = ABBR_TEAM.get(home_abbr)
    spread = total = ml_home = ml_away = None
    book_s = book_t = None
    updated = None
    prices = {}
    sharp = None
    for b in ev.get("bookmakers", []):                      # the referee: Pinnacle's own lines, kept separately
        if b.get("key") in C.SHARP_BOOKS:
            sharp = _one_book(b, home_full) or None
    for b in sorted([b for b in ev.get("bookmakers", []) if b.get("key") not in C.SHARP_BOOKS], key=lambda b: _rank(b.get("key"))):
        one = _one_book(b, home_full)
        if spread is None and "spread_line" in one:
            prices.update({k: one[k] for k in ("spread_home_odds", "spread_away_odds")})
        if total is None and "total_line" in one:
            prices.update({k: one[k] for k in ("over_odds", "under_odds")})
        for m in b.get("markets", []):
            if m.get("key") == "spreads" and spread is None:
                for o in m.get("outcomes", []):
                    p = _num(o.get("point"))
                    if o.get("name") == home_full and p is not None:
                        spread, book_s, updated = -p, b, b.get("last_update")
            elif m.get("key") == "h2h" and ml_home is None:
                prices = {o.get("name"): _num(o.get("price")) for o in m.get("outcomes", [])}
                hp = prices.get(home_full)
                ap = next((v for k, v in prices.items() if k != home_full and k != "Draw"), None)
                if hp is not None and ap is not None:
                    ml_home, ml_away = hp, ap
            elif m.get("key") == "totals" and total is None:
                for o in m.get("outcomes", []):
                    p = _num(o.get("point"))
                    if str(o.get("name", "")).lower() == "over" and p is not None:
                        total, book_t = p, b
    book = book_s or book_t
    if book is None:
        return None
    return {"spread_line": spread, "total_line": total, "ml_home": ml_home, "ml_away": ml_away,
            "book": book.get("key"), **prices, "sharp": sharp,
            "book_title": book.get("title") or book.get("key"), "updated": updated}


def fetch_game_lines(client: Client, todo: pd.DataFrame) -> dict:
    markets = "spreads,totals" + (",h2h" if getattr(C, "ODDS_MONEYLINE_LIVE", False) else "")
    # up to 10 named books cost the same as one region: the US books in ODDS_BOOKS (Hard Rock first) plus Pinnacle
    data = client.get(f"/v4/sports/{SPORT}/odds", est_cost=markets.count(",") + 1, markets=markets,
                      bookmakers=",".join((C.ODDS_BOOKS + C.SHARP_BOOKS)[:10]), oddsFormat="american", dateFormat="iso")
    if not isinstance(data, list):
        raise OddsError("unexpected game lines response")
    by_pair = {frozenset((g["home_team"], g["away_team"])): g for _, g in todo.iterrows()}
    out = {}
    for ev in data:
        h, a = TEAM_ABBR.get(ev.get("home_team")), TEAM_ABBR.get(ev.get("away_team"))
        g = by_pair.get(frozenset((h, a)))
        if g is None or _far(ev.get("commence_time"), g.get("ko")):
            continue
        res = _parse_lines(ev, g["home_team"])
        if res:
            out[g["game_id"]] = res
    return out


# ---------------------------------------------------------------------
# player props
# ---------------------------------------------------------------------
def parse_props(ev: dict, game_id: str) -> list:
    """Rows shaped like data/props.csv. One row per player per stat, from the
    highest-ranked book that lists that player."""
    rows = {}
    allq = {}          # (stat, player) -> [(book key, line, over, under)] from every book: the consensus price
    for b in ev.get("bookmakers", []):
        for m in b.get("markets", []):
            stat = MARKETS.get(m.get("key"))
            if not stat:
                continue
            g2 = {}
            for o in m.get("outcomes", []):
                player, price = str(o.get("description") or "").strip(), _num(o.get("price"))
                side = str(o.get("name", "")).strip().lower()
                line = 0.5 if stat == "anytime_td" else _num(o.get("point"))
                if not player or price is None or line is None:
                    continue
                side = "over" if side in ("yes", "over") else ("under" if side in ("no", "under") else "")
                if side:
                    g2.setdefault((player, line), {})[side] = price
            for (player, line), sd in g2.items():
                if "over" in sd and "under" in sd:
                    allq.setdefault((stat, norm_name(player)), []).append((b.get("key"), line, sd["over"], sd["under"]))
    for b in sorted(ev.get("bookmakers", []), key=lambda b: _rank(b.get("key"))):
        for m in b.get("markets", []):
            stat = MARKETS.get(m.get("key"))
            if not stat:
                continue
            grouped = {}   # (player, line) -> {"over": price, "under": price}
            for o in m.get("outcomes", []):
                player = str(o.get("description") or "").strip()
                price = _num(o.get("price"))
                if not player or price is None:
                    continue
                side = str(o.get("name", "")).strip().lower()
                if stat == "anytime_td":
                    side = "over" if side in ("yes", "over") else ("under" if side in ("no", "under") else "")
                    line = 0.5
                else:
                    line = _num(o.get("point"))
                    if line is None:
                        continue
                if side in ("over", "under"):
                    grouped.setdefault((player, line), {})[side] = price
            by_player = {}
            for (player, line), sides in grouped.items():
                if "over" in sides:                     # need at least the over price
                    by_player.setdefault(player, []).append((line, sides))
            for player, options in by_player.items():
                if (stat, norm_name(player)) in rows:
                    continue
                def evenness(opt):                      # prefer the line closest to a coin flip
                    s = opt[1]
                    if "under" not in s:
                        return 1.0
                    po = 100 / (s["over"] + 100) if s["over"] > 0 else -s["over"] / (-s["over"] + 100)
                    pu = 100 / (s["under"] + 100) if s["under"] > 0 else -s["under"] / (-s["under"] + 100)
                    return abs(po / (po + pu) - 0.5)
                if stat == "tds":                       # this market is only used for 2+ TDs
                    options = [o for o in options if abs(o[0] - 1.5) < 1e-6]
                    if not options:
                        continue
                line, sides = min(options, key=evenness)
                rows[(stat, norm_name(player))] = {
                    "player": player, "team": "", "stat": stat,
                    "line": "" if stat == "anytime_td" else f"{line:g}",
                    "over_odds": _fmt_odds(sides["over"]),
                    "under_odds": _fmt_odds(sides["under"]) if "under" in sides else "",
                    "game_id": game_id, "source": f"auto:{b.get('key')}", "book": b.get("title") or b.get("key")}
                # consensus: the other books' no-vig Over chance at this same line (median), the referee for props
                imp = lambda x: 100 / (x + 100) if x > 0 else -x / (-x + 100)
                cons = [imp(o) / (imp(o) + imp(u)) for bk, L, o, u in allq.get((stat, norm_name(player)), [])
                        if bk != b.get("key") and abs(L - line) < 1e-9]
                rows[(stat, norm_name(player))]["cons_over"] = round(float(np.median(cons)), 4) if cons else None
                rows[(stat, norm_name(player))]["cons_n"] = len(cons)
    return list(rows.values())


def _load_cache(path):
    try:
        return json.loads(Path(path).read_text())
    except Exception:  # noqa: BLE001
        return {"games": {}}


def _save_cache(path, cache):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(clean_json(cache), indent=1, allow_nan=False))


def _lines_due(ent: dict, todo: pd.DataFrame, now: datetime) -> bool:
    """Spreads and totals: refresh every few hours, faster when a game is close."""
    try:
        age = now - datetime.fromisoformat(ent["fetched_at"])
    except (KeyError, TypeError, ValueError):
        return True
    soon = any(ko is not None and pd.notna(ko) and now < ko <= now + timedelta(hours=12) for ko in todo["ko"])
    gap = C.ODDS_LINES_GAMEDAY_HOURS if soon else C.ODDS_LINES_EVERY_HOURS
    return age >= timedelta(hours=gap)


def fetch_all_props(client: Client, todo: pd.DataFrame, matched: dict, now: datetime, cache_path):
    """Fetch props for games kicking off soon (once per refresh window), reuse the cache otherwise."""
    markets = list(C.ODDS_PROP_MARKETS)
    if now.date().isoformat() >= getattr(C, "ODDS_EXTRA_FROM", "9999"):      # count-stat legs (alt parlays)
        markets += [m for m in getattr(C, "ODDS_EXTRA_PROP_MARKETS", []) if m not in markets]
    cache = _load_cache(cache_path)
    cache["games"] = {k: v for k, v in cache.get("games", {}).items() if k in set(todo["game_id"])}
    fetched = cached = skipped_budget = 0
    budget_note = None
    order = todo.assign(_ko=todo["ko"]).sort_values("_ko", na_position="last")
    try:                                                   # games with a locked prop play: refreshed near kickoff (CLV)
        plg = json.loads((Path(cache_path).parent / "props_log.json").read_text()).get("props", {})
        play_games = {r.get("game_id") for r in plg.values() if r.get("flag") and not r.get("result")}
    except Exception:  # noqa: BLE001
        play_games = set()
    try:
        for _, g in order.iterrows():
            gid, ko, ev = g["game_id"], g.get("ko"), matched.get(g["game_id"])
            if ev is None:
                continue
            ent = cache["games"].get(gid)
            in_window = ko is not None and pd.notna(ko) and now < ko <= now + timedelta(hours=C.ODDS_HOURS_AHEAD)
            stale = True
            if ent:
                try:
                    age = now - datetime.fromisoformat(ent["fetched_at"])
                    stale = age >= timedelta(hours=C.ODDS_REFRESH_HOURS)
                    near = ko is not None and pd.notna(ko) and ko - now <= timedelta(hours=C.ODDS_PROPS_CLOSE_HOURS)
                    if gid in play_games and near and age >= timedelta(hours=6):
                        stale = True                       # one near-closing pull so prop plays get a closing price
                except (ValueError, KeyError):
                    stale = True
            if in_window and stale:
                over_cap = client.spent + len(markets) > C.ODDS_MAX_CREDITS_PER_RUN
                below_reserve = client.remaining is not None and client.remaining - len(markets) < C.ODDS_CREDIT_RESERVE
                if over_cap or below_reserve:
                    skipped_budget += 1
                    budget_note = ("stopped at this run's credit limit" if over_cap
                                   else f"kept a reserve of {C.ODDS_CREDIT_RESERVE} credits")
                    if ent:
                        cached += 1
                    continue
                try:
                    data = client.get(f"/v4/sports/{SPORT}/events/{ev['id']}/odds", est_cost=len(markets),
                                      regions="us", markets=",".join(markets), oddsFormat="american", dateFormat="iso")
                except OddsFatal:
                    raise
                except OddsError as e:
                    log.warning(f"props for {gid} skipped: {e}")
                    if ent:
                        cached += 1
                    continue
                cache["games"][gid] = {"fetched_at": now.isoformat(timespec="minutes"), "event_id": ev["id"],
                                       "rows": parse_props(data if isinstance(data, dict) else {}, gid)}
                fetched += 1
            elif ent:
                cached += 1
    finally:
        Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
        Path(cache_path).write_text(json.dumps(clean_json(cache), indent=1, allow_nan=False))
    rows = [r for ent in cache["games"].values() for r in ent.get("rows", [])]
    return rows, {"fetched": fetched, "cached": cached, "skipped": skipped_budget, "budget_note": budget_note}


# ---------------------------------------------------------------------
# alt lines and team totals (altlines.py)
# ---------------------------------------------------------------------
def _alt_rows(ev, b):
    hn, an = ev.get("home_team"), ev.get("away_team")
    rows = []
    for m in b.get("markets", []):
        for o in m.get("outcomes", []):
            pt, pr = _num(o.get("point")), _num(o.get("price"))
            if pt is None or pr is None:
                continue
            k = m.get("key", "")
            per = "h1" if k.endswith("_h1") else None             # 1st half: spreads_h1, totals_h1, alternate_*_h1
            k = k[:-3] if per else k
            if k in ("spreads", "alternate_spreads") and o.get("name") in (hn, an):
                side = "home" if o["name"] == hn else "away"
                rows.append({"market": "spread", "team": side, "side": side, "line": pt, "odds": pr, "period": per})
            elif k in ("totals", "alternate_totals") and str(o.get("name")).lower() in ("over", "under"):
                rows.append({"market": "total", "team": None, "side": str(o["name"]).lower(), "line": pt, "odds": pr, "period": per})
            elif k in ("team_totals", "alternate_team_totals") and str(o.get("name")).lower() in ("over", "under") and o.get("description") in (hn, an):
                rows.append({"market": "team_total", "team": "home" if o["description"] == hn else "away",
                             "side": str(o["name"]).lower(), "line": pt, "odds": pr, "period": per})
    return rows


def fetch_alts(client: Client, todo: pd.DataFrame, matched: dict, now: datetime, cache_path) -> tuple[dict, int]:
    """Hard Rock's alt lines for games kicking off soon, once per game, within the credit floor."""
    cache = _load_cache(cache_path)
    alt = cache.setdefault("alt", {})
    ids = set(todo["game_id"])
    alt = {k: v for k, v in alt.items() if k in ids}
    spent = 0
    soon = []
    for _, g in todo.iterrows():
        ko, ev = g.get("ko"), matched.get(g["game_id"])
        if ev is not None and ko is not None and pd.notna(ko) and now < ko <= now + timedelta(hours=C.ALT_HOURS):
            soon.append((ko, g["game_id"], ev))
    for mkt in C.ALT_MARKETS:
        for ko, gid, ev in sorted(soon, key=lambda x: x[0]):
            ent = alt.setdefault(gid, {"markets": {}})
            if mkt in ent["markets"]:
                continue
            if spent + 1 > C.ALT_MAX_PER_RUN or (client.remaining is not None and client.remaining - 1 < C.ALT_MIN_LEFT):
                break
            try:
                data = client.get(f"/v4/sports/{SPORT}/events/{ev['id']}/odds", est_cost=1, markets=mkt,
                                  bookmakers=",".join(C.ALT_BOOKS), oddsFormat="american", dateFormat="iso")
            except OddsFatal:
                raise
            except OddsError as e:
                log.warning(f"alt lines {mkt} for {gid} skipped: {e}")
                continue
            spent += 1
            bks = {b.get("key"): b for b in (data or {}).get("bookmakers", [])} if isinstance(data, dict) else {}
            bet = next((k for k in C.ALT_BOOKS if k in bks and k not in C.SHARP_BOOKS), None)
            shp = next((k for k in C.SHARP_BOOKS if k in bks), None)
            ent["markets"][mkt] = {"fetched_at": now.isoformat(timespec="minutes"),
                                   "book": _alt_rows(data, bks[bet]) if bet else [], "sharp": _alt_rows(data, bks[shp]) if shp else [],
                                   "book_name": bks[bet].get("title") if bet else None}
    cache["alt"] = alt
    _save_cache(cache_path, cache)
    out = {}
    for gid, ent in alt.items():
        ms = ent.get("markets") or {}
        if ms:
            out[gid] = {"book": [r for v in ms.values() for r in v.get("book", [])], "sharp": [r for v in ms.values() for r in v.get("sharp", [])],
                        "book_name": next((v.get("book_name") for v in ms.values() if v.get("book_name")), None), "markets": list(ms)}
    return out, spent


# ---------------------------------------------------------------------
# main entry
# ---------------------------------------------------------------------
def pull(todo: pd.DataFrame, now: datetime, cache_path) -> dict:
    status = {"enabled": False, "ok": None, "message": "", "credits_remaining": None, "credits_used": None,
              "spent_this_run": 0, "lines": 0, "games_fetched": 0, "games_cached": 0, "prop_rows": 0,
              "book": None, "note": None, "at": now.isoformat(timespec="minutes")}
    out = {"game_lines": {}, "props_df": pd.DataFrame(), "status": status, "alt": {}}
    key = os.environ.get("ODDS_API_KEY", "").strip()
    if not key:
        status["message"] = "Automatic odds are off. Add an Odds API key to load lines on their own."
        return out
    if not (C.ODDS_GAME_LINES_ON or C.ODDS_PROPS_ON):
        status["message"] = "Automatic odds are switched off in config.py."
        return out
    status["enabled"] = True
    client = Client(key)
    notes, rows = [], []
    try:
        matched = match_events(todo, list_events(client))
        if not matched:
            notes.append("no upcoming games found in the odds feed yet")
        if C.ODDS_GAME_LINES_ON:
            cache = _load_cache(cache_path)
            ent = cache.get("lines") or {}
            ids = set(todo["game_id"])
            cached_lines = {k: v for k, v in (ent.get("data") or {}).items() if k in ids}
            due, why_not = _lines_due(ent, todo, now), None
            if due and client.remaining is not None and client.remaining < getattr(C, "ODDS_LINES_FLOOR", 0):
                due, why_not = False, f"saving credits for props ({client.remaining} left)"
            if due:
                try:
                    fresh = fetch_game_lines(client, todo)
                    cache["lines"] = {"fetched_at": now.isoformat(timespec="minutes"), "data": fresh}
                    _save_cache(cache_path, cache)
                    out["game_lines"] = fresh
                    status["lines_at"] = cache["lines"]["fetched_at"]
                except OddsFatal:
                    raise
                except OddsError as e:
                    notes.append(f"live spreads and totals skipped ({e})")
                    out["game_lines"] = cached_lines
                    status["lines_at"] = ent.get("fetched_at")
            else:
                out["game_lines"] = cached_lines
                status["lines_at"] = ent.get("fetched_at")
                status["lines_reused"] = True
                if why_not:
                    notes.append(f"live lines not refreshed, {why_not}")
            status["lines"] = len(out["game_lines"])
        if C.ODDS_PROPS_ON and matched:
            rows, info = fetch_all_props(client, todo, matched, now, cache_path)
            status.update(games_fetched=info["fetched"], games_cached=info["cached"])
            if info["budget_note"]:
                notes.append(f"{info['skipped']} games not refreshed ({info['budget_note']})")
        if matched and getattr(C, "ALT_MARKETS", None):
            try:
                out["alt"], status["alt_spent"] = fetch_alts(client, todo, matched, now, cache_path)
            except OddsFatal:
                raise
            except Exception as e:  # noqa: BLE001
                notes.append(f"alt lines skipped ({str(e)[:80]})")
        status["ok"] = True
    except OddsError as e:
        status["ok"] = False
        notes.append(str(e))
    status["credits_remaining"], status["credits_used"] = client.remaining, client.used
    status["spent_this_run"] = client.spent
    if rows:
        out["props_df"] = pd.DataFrame(rows)
        status["prop_rows"] = len(rows)
        books = pd.Series([r["book"] for r in rows]).value_counts()
        status["book"] = books.index[0]
    if status["ok"]:
        bits = [f"{status['lines']} games with live lines" + (" (reused from the last pull)" if status.get("lines_reused") else "")] if C.ODDS_GAME_LINES_ON else []
        if C.ODDS_PROPS_ON:
            bits.append(f"{status['prop_rows']} prop lines ({status['games_fetched']} games fetched, "
                        f"{status['games_cached']} reused from earlier)")
        status["message"] = "Live odds on: " + ", ".join(bits) + "."
    else:
        status["message"] = "Live odds failed: " + "; ".join(notes) + ". Using the free data feed and your manual props."
        notes = []
    status["note"] = "; ".join(notes) if notes else None
    return out
