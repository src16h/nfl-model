"""
Free NBA data from ESPN's public feeds: schedule, live scores, box scores, injuries, and the
DraftKings / ESPN BET lines ESPN posts (opening and closing, for every game since 2022).

History is kept in data/nba/games.csv and data/nba/player_games.csv; each run only fetches
games that finished since the last run.
"""
import json
import logging
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

log = logging.getLogger("nbamodel")
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "nba"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) nba-model/1.0"}
SITE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
CORE = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba"
TYPES = {2: "reg", 3: "post", 5: "playin"}
FIX = {"GS": "GSW", "NO": "NOP", "NY": "NYK", "SA": "SAS", "UTAH": "UTA", "WSH": "WAS"}   # ESPN -> usual abbreviations
TEAMS = {"ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DAL", "DEN", "DET", "GSW", "HOU", "IND", "LAC", "LAL", "MEM", "MIA",
         "MIL", "MIN", "NOP", "NYK", "OKC", "ORL", "PHI", "PHX", "POR", "SAC", "SAS", "TOR", "UTA", "WAS"}
GCOLS = ["game_id", "season", "type", "date", "start", "home", "away", "hs", "as", "neutral",
         "close_spread", "close_total", "open_spread", "open_total", "ml_home", "ml_away", "line_src"]
PCOLS = ["game_id", "team", "pid", "name", "pos", "starter", "dnp", "min", "pts", "reb", "ast", "fg3m", "fg3a",
         "fgm", "fga", "ftm", "fta", "oreb", "dreb", "tov", "stl", "blk", "pf", "pm"]


def tm(a):
    a = str(a).upper()
    return FIX.get(a, a)


def get_json(url, timeout=30, tries=3):
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return json.loads(r.read().decode())
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (i + 1))
    raise last


def season_of(d: date) -> int:
    """Season start year: Oct 2026 to Jun 2027 is 2026."""
    return d.year if d.month >= 8 else d.year - 1


def scoreboard(d: date):
    """Games on one US date: [{event, start, home, away, hs, as, state, type, neutral, odds}]."""
    js = get_json(f"{SITE}/scoreboard?dates={d:%Y%m%d}&limit=50")
    out = []
    for e in js.get("events", []):
        c = e["competitions"][0]
        typ = (e.get("season") or {}).get("type")
        side = {x["homeAway"]: x for x in c["competitors"]}
        if typ not in TYPES or "home" not in side:
            continue
        h, a = tm(side["home"]["team"]["abbreviation"]), tm(side["away"]["team"]["abbreviation"])
        if h not in TEAMS or a not in TEAMS:
            continue
        st = c.get("status", {}).get("type", {})
        o = (c.get("odds") or [{}])[0] if c.get("odds") else {}
        out.append({"event": str(e["id"]), "start": c["date"], "home": h, "away": a, "type": TYPES[typ],
                    "hs": _int(side["home"].get("score")), "as": _int(side["away"].get("score")),
                    "state": st.get("state"), "completed": bool(st.get("completed")), "detail": st.get("shortDetail"),
                    "neutral": bool(c.get("neutralSite")), "odds": o,
                    "home_name": side["home"]["team"].get("displayName"), "away_name": side["away"]["team"].get("displayName")})
    return out


def _int(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


def _num(s):
    try:
        return float(str(s).replace("+", ""))
    except (TypeError, ValueError):
        return None


def lines(event):
    """Opening and closing spread (home view) and total, plus closing moneylines, from ESPN's odds feed."""
    try:
        js = get_json(f"{CORE}/events/{event}/competitions/{event}/odds")
    except Exception:  # noqa: BLE001
        return {}
    items = js.get("items") or []
    items.sort(key=lambda x: int((x.get("provider") or {}).get("priority", 9)))
    for it in items:
        hto, ato = it.get("homeTeamOdds") or {}, it.get("awayTeamOdds") or {}
        hc, ho = hto.get("close") or {}, hto.get("open") or {}
        cs = _num(((hc.get("pointSpread") or {}).get("american")))
        os_ = _num(((ho.get("pointSpread") or {}).get("american")))
        ct = it.get("overUnder")
        tot = it.get("total") or {}
        ot = _num(((tot.get("open") or {}).get("total") or {}).get("american")) if tot else None
        if cs is None and it.get("spread") is not None:
            cs = float(it["spread"]) if hto.get("favorite") else -abs(float(it["spread"])) * (-1)
        out = {"close_spread": cs, "close_total": _num(ct), "open_spread": os_, "open_total": ot,
               "ml_home": _num(((hc.get("moneyLine") or {}).get("american"))) or hto.get("moneyLine"),
               "ml_away": _num((((ato.get("close") or {}).get("moneyLine") or {}).get("american"))) or ato.get("moneyLine"),
               "line_src": (it.get("provider") or {}).get("name")}
        if out["close_spread"] is not None or out["close_total"] is not None:
            return out
    return {}


def box(event):
    """Player lines from one finished game."""
    js = get_json(f"{SITE}/summary?event={event}")
    rows = []
    for t in (js.get("boxscore") or {}).get("players", []):
        team = tm(t["team"]["abbreviation"])
        for st in t.get("statistics", []):
            keys = [k.upper() for k in st.get("labels", [])]
            for a in st.get("athletes", []):
                ath = a.get("athlete") or {}
                r = {"game_id": str(event), "team": team, "pid": str(ath.get("id")), "name": ath.get("displayName"),
                     "pos": (ath.get("position") or {}).get("abbreviation"), "starter": bool(a.get("starter")),
                     "dnp": bool(a.get("didNotPlay")) or not a.get("stats")}
                v = dict(zip(keys, a.get("stats") or []))
                mk = lambda s: (_int(str(s).split("-")[0]), _int(str(s).split("-")[1])) if s and "-" in str(s) else (None, None)
                r["min"] = _num(v.get("MIN")) or 0.0
                for k, col in (("PTS", "pts"), ("REB", "reb"), ("AST", "ast"), ("OREB", "oreb"), ("DREB", "dreb"),
                               ("TO", "tov"), ("STL", "stl"), ("BLK", "blk"), ("PF", "pf"), ("+/-", "pm")):
                    r[col] = _num(v.get(k)) or 0.0
                r["fgm"], r["fga"] = mk(v.get("FG"))
                r["fg3m"], r["fg3a"] = mk(v.get("3PT"))
                r["ftm"], r["fta"] = mk(v.get("FT"))
                rows.append(r)
    return rows


def injuries():
    """{team: [{name, pid, status, detail}]} from ESPN's league injury page."""
    out = {}
    try:
        js = get_json(f"{SITE}/injuries")
    except Exception as e:  # noqa: BLE001
        log.warning(f"injuries not read: {e}")
        return out
    for t in js.get("injuries", []):
        for x in t.get("injuries", []):
            ath = x.get("athlete") or {}
            team = tm(((ath.get("team") or {}).get("abbreviation")) or (t.get("abbreviation") or ""))
            if not team:
                continue
            pid = str(ath.get("id") or "") or str(((ath.get("links") or [{}])[0].get("href") or "").split("/id/")[-1].split("/")[0])
            out.setdefault(team, []).append({"name": ath.get("displayName"), "pid": pid, "status": x.get("status"),
                                            "detail": (x.get("shortComment") or "")[:160]})
    return out


def load():
    g = pd.read_csv(DATA / "games.csv", dtype={"game_id": str}) if (DATA / "games.csv").exists() else pd.DataFrame(columns=GCOLS)
    p = pd.read_csv(DATA / "player_games.csv", dtype={"game_id": str, "pid": str}) if (DATA / "player_games.csv").exists() \
        else pd.DataFrame(columns=PCOLS)
    return g, p


def update(start: date, end: date, workers=8):
    """Add every finished game from start to end (US dates) to the history files."""
    DATA.mkdir(parents=True, exist_ok=True)
    g, p = load()
    have = set(g["game_id"].astype(str))
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    with ThreadPoolExecutor(workers) as ex:
        boards = list(ex.map(lambda d: (d, _safe(scoreboard, d) or []), days))
    todo = [(d, x) for d, b in boards for x in b if x["completed"] and x["event"] not in have and x["hs"] is not None]
    log.info(f"history: {len(todo)} new finished games from {start} to {end}")

    def one(item):
        d, x = item
        try:
            ln = lines(x["event"])
            bx = box(x["event"])
        except Exception as e:  # noqa: BLE001
            log.warning(f"game {x['event']} skipped: {e}")
            return None
        gd = datetime.fromisoformat(x["start"].replace("Z", "+00:00"))
        row = {"game_id": x["event"], "season": season_of(d), "type": x["type"], "date": d.isoformat(), "start": gd.isoformat(),
               "home": x["home"], "away": x["away"], "hs": x["hs"], "as": x["as"], "neutral": x["neutral"], **ln}
        return row, bx
    with ThreadPoolExecutor(workers) as ex:
        res = [r for r in ex.map(one, todo) if r]
    if res:
        g = pd.concat([g, pd.DataFrame([r[0] for r in res], columns=GCOLS)], ignore_index=True)
        p = pd.concat([p, pd.DataFrame([x for r in res for x in r[1]], columns=PCOLS)], ignore_index=True)
        g = g.drop_duplicates("game_id", keep="last").sort_values(["start", "game_id"])
        p = p.drop_duplicates(["game_id", "pid"], keep="last")
        g.to_csv(DATA / "games.csv", index=False)
        p.to_csv(DATA / "player_games.csv", index=False)
    return g, p


def _safe(f, *a):
    try:
        return f(*a)
    except Exception as e:  # noqa: BLE001
        log.warning(f"{f.__name__}{a} failed: {e}")
        return None
