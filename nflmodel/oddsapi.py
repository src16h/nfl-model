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
    "player_pass_interceptions": "pass_int", "player_rush_yds": "rush_yds", "player_rush_attempts": "carries",
    "player_receptions": "rec", "player_reception_yds": "rec_yds",
    "player_rush_reception_yds": "rush_rec_yds", "player_anytime_td": "anytime_td",
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
def _parse_lines(ev: dict, home_abbr: str):
    """spread_line follows the data feed's convention: the home team's expected margin."""
    home_full = ABBR_TEAM.get(home_abbr)
    spread = total = None
    book_s = book_t = None
    updated = None
    for b in sorted(ev.get("bookmakers", []), key=lambda b: _rank(b.get("key"))):
        for m in b.get("markets", []):
            if m.get("key") == "spreads" and spread is None:
                for o in m.get("outcomes", []):
                    p = _num(o.get("point"))
                    if o.get("name") == home_full and p is not None:
                        spread, book_s, updated = -p, b, b.get("last_update")
            elif m.get("key") == "totals" and total is None:
                for o in m.get("outcomes", []):
                    p = _num(o.get("point"))
                    if str(o.get("name", "")).lower() == "over" and p is not None:
                        total, book_t = p, b
    book = book_s or book_t
    if book is None:
        return None
    return {"spread_line": spread, "total_line": total, "book": book.get("key"),
            "book_title": book.get("title") or book.get("key"), "updated": updated}


def fetch_game_lines(client: Client, todo: pd.DataFrame) -> dict:
    data = client.get(f"/v4/sports/{SPORT}/odds", est_cost=2, regions="us", markets="spreads,totals",
                      oddsFormat="american", dateFormat="iso")
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
                line, sides = min(options, key=evenness)
                rows[(stat, norm_name(player))] = {
                    "player": player, "team": "", "stat": stat,
                    "line": "" if stat == "anytime_td" else f"{line:g}",
                    "over_odds": _fmt_odds(sides["over"]),
                    "under_odds": _fmt_odds(sides["under"]) if "under" in sides else "",
                    "game_id": game_id, "source": f"auto:{b.get('key')}", "book": b.get("title") or b.get("key")}
    return list(rows.values())


def _load_cache(path):
    try:
        return json.loads(Path(path).read_text())
    except Exception:  # noqa: BLE001
        return {"games": {}}


def fetch_all_props(client: Client, todo: pd.DataFrame, matched: dict, now: datetime, cache_path):
    """Fetch props for games kicking off soon (once per refresh window), reuse the cache otherwise."""
    markets = list(C.ODDS_PROP_MARKETS)
    cache = _load_cache(cache_path)
    cache["games"] = {k: v for k, v in cache.get("games", {}).items() if k in set(todo["game_id"])}
    fetched = cached = skipped_budget = 0
    budget_note = None
    order = todo.assign(_ko=todo["ko"]).sort_values("_ko", na_position="last")
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
                    stale = (now - datetime.fromisoformat(ent["fetched_at"])) >= timedelta(hours=C.ODDS_REFRESH_HOURS)
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
# main entry
# ---------------------------------------------------------------------
def pull(todo: pd.DataFrame, now: datetime, cache_path) -> dict:
    status = {"enabled": False, "ok": None, "message": "", "credits_remaining": None, "credits_used": None,
              "spent_this_run": 0, "lines": 0, "games_fetched": 0, "games_cached": 0, "prop_rows": 0,
              "book": None, "note": None, "at": now.isoformat(timespec="minutes")}
    out = {"game_lines": {}, "props_df": pd.DataFrame(), "status": status}
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
            try:
                out["game_lines"] = fetch_game_lines(client, todo)
                status["lines"] = len(out["game_lines"])
            except OddsFatal:
                raise
            except OddsError as e:
                notes.append(f"live spreads and totals skipped ({e})")
        if C.ODDS_PROPS_ON and matched:
            rows, info = fetch_all_props(client, todo, matched, now, cache_path)
            status.update(games_fetched=info["fetched"], games_cached=info["cached"])
            if info["budget_note"]:
                notes.append(f"{info['skipped']} games not refreshed ({info['budget_note']})")
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
        bits = [f"{status['lines']} games with live lines"] if C.ODDS_GAME_LINES_ON else []
        if C.ODDS_PROPS_ON:
            bits.append(f"{status['prop_rows']} prop lines ({status['games_fetched']} games fetched, "
                        f"{status['games_cached']} reused from earlier)")
        status["message"] = "Live odds on: " + ", ".join(bits) + "."
    else:
        status["message"] = "Live odds failed: " + "; ".join(notes) + ". Using the free data feed and your manual props."
        notes = []
    status["note"] = "; ".join(notes) if notes else None
    return out
