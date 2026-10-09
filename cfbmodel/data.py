"""
Free college football data from ESPN's public feed: weekly schedule with
scores and DraftKings lines, and one summary per game with the box score,
player stats, every play, and the closing line.

Summaries are trimmed to the fields the model uses and cached in
data/cfb_cache so each game is downloaded once.
"""
import gzip
import json
import logging
import time
import urllib.request
from pathlib import Path

log = logging.getLogger("cfbmodel")
ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "cfb_cache"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) cfb-model/1.0"}
SITE = "https://site.api.espn.com/apis/site/v2/sports/football/college-football"


def _get(url, timeout=60, tries=4):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (i + 1))
    raise last


def _num(v):
    try:
        return float(str(v).replace("+", "").replace("o", "").replace("u", ""))
    except (TypeError, ValueError):
        return None


def _odds_block(o):
    """One book's line from a scoreboard or summary odds entry. spread is the home team's line."""
    if not o:
        return None
    ps, tt, ml = o.get("pointSpread") or {}, o.get("total") or {}, o.get("moneyline") or {}
    h, a = o.get("homeTeamOdds") or {}, o.get("awayTeamOdds") or {}

    def side(blk, s, when, key):
        return _num((((blk.get(s) or {}).get(when)) or {}).get(key))
    out = {"book": (o.get("provider") or {}).get("name"), "spread": _num(o.get("spread")), "total": _num(o.get("overUnder")),
           "ml_home": _num(h.get("moneyLine")) or side(ml, "home", "close", "odds"),
           "ml_away": _num(a.get("moneyLine")) or side(ml, "away", "close", "odds"),
           "spread_home_odds": _num(h.get("spreadOdds")) or side(ps, "home", "close", "odds"),
           "spread_away_odds": _num(a.get("spreadOdds")) or side(ps, "away", "close", "odds"),
           "over_odds": side(tt, "over", "close", "odds"), "under_odds": side(tt, "under", "close", "odds"),
           "open_spread": side(ps, "home", "open", "line"), "open_total": side(tt, "over", "open", "line"),
           "open_ml_home": side(ml, "home", "open", "odds"), "open_ml_away": side(ml, "away", "open", "odds")}
    if out["spread"] is None:
        out["spread"] = side(ps, "home", "close", "line")
    if out["total"] is None:
        out["total"] = side(tt, "over", "close", "line")
    return out


def scoreboard(year, week, seasontype=2):
    """Every FBS game in a week (includes games against FCS teams)."""
    js = _get(f"{SITE}/scoreboard?groups=80&limit=400&seasontype={seasontype}&week={week}&dates={year}")
    out = []
    for e in js.get("events", []):
        c = e["competitions"][0]
        g = {"game_id": int(e["id"]), "season": int(e["season"]["year"]), "stype": int(e["season"]["type"]),
             "week": int((e.get("week") or {}).get("number") or week), "start": e["date"],
             "state": e["status"]["type"]["name"], "done": bool(e["status"]["type"].get("completed")),
             "neutral": bool(c.get("neutralSite")), "conf_game": bool(c.get("conferenceCompetition")),
             "venue": ((c.get("venue") or {}).get("fullName")), "indoor": bool((c.get("venue") or {}).get("indoor")),
             "tv": ", ".join(b for x in (c.get("broadcasts") or []) for b in x.get("names", [])),
             "odds": _odds_block((c.get("odds") or [None])[0])}
        for t in c["competitors"]:
            s = "home" if t["homeAway"] == "home" else "away"
            tm = t["team"]
            g[s] = {"id": int(tm["id"]), "abbr": tm.get("abbreviation") or tm.get("shortDisplayName"), "name": tm.get("location") or tm.get("displayName"),
                    "nick": tm.get("name"), "conf": int(tm["conferenceId"]) if tm.get("conferenceId") else None,
                    "color": tm.get("color"), "score": _num(t.get("score")),
                    "rank": (t.get("curatedRank") or {}).get("current"),
                    "record": next((r.get("summary") for r in t.get("records", []) if r.get("type") == "total"), None)}
        out.append(g)
    return out


def calendar():
    """Current season, week, and each week's date range."""
    js = _get(f"{SITE}/scoreboard?groups=80&limit=1")
    weeks = []
    for cal in js["leagues"][0].get("calendar", []):
        if isinstance(cal, dict):
            for c in cal.get("entries", []):
                weeks.append({"stype": int(cal.get("value", 2)), "week": int(c["value"]), "label": c["label"],
                              "start": c["startDate"], "end": c["endDate"]})
    return {"season": int(js["season"]["year"]), "stype": int(js["season"]["type"]), "week": int(js["week"]["number"]), "weeks": weeks}


def _trim(s):
    h = s["header"]
    comp = h["competitions"][0]
    out = {"id": int(h["id"]), "season": h["season"]["year"], "stype": h["season"]["type"], "week": h.get("week"),
           "date": comp["date"], "neutral": bool(comp.get("neutralSite")), "conf_game": bool(comp.get("conferenceCompetition")),
           "state": comp["status"]["type"]["name"], "teams": [], "box": {}, "players": {}, "lines": [], "drives": []}
    gi = s.get("gameInfo") or {}
    out["venue"] = {"grass": (gi.get("venue") or {}).get("grass"), "indoor": (gi.get("venue") or {}).get("indoor"),
                    "city": ((gi.get("venue") or {}).get("address") or {}).get("city")}
    for c in comp["competitors"]:
        tm = c["team"]
        out["teams"].append({"side": c["homeAway"], "id": int(tm["id"]), "abbr": tm.get("abbreviation"), "name": tm.get("location"),
                             "score": _num(c.get("score")), "lines": [_num(x.get("displayValue")) for x in c.get("linescores", [])]})
    for t in (s.get("boxscore") or {}).get("teams", []):
        out["box"][str(t["team"]["id"])] = {x["name"]: x.get("displayValue") for x in t.get("statistics", [])}
    for t in (s.get("boxscore") or {}).get("players", []):
        cats = {}
        for cat in t.get("statistics", []):
            cats[cat["name"]] = {"keys": cat.get("keys", []),
                                 "rows": [[a["athlete"].get("id"), a["athlete"].get("displayName"), a.get("stats", [])] for a in cat.get("athletes", [])]}
        out["players"][str(t["team"]["id"])] = cats
    for o in s.get("pickcenter") or []:
        b = _odds_block(o)
        if b:
            out["lines"].append(b)
    for d in (s.get("drives") or {}).get("previous", []):
        plays = []
        for p in d.get("plays", []):
            st, en = p.get("start") or {}, p.get("end") or {}
            plays.append([int((p.get("type") or {}).get("id") or 0), (p.get("type") or {}).get("text"), (p.get("period") or {}).get("number"),
                          (p.get("clock") or {}).get("displayValue"),
                          st.get("down"), st.get("distance"), st.get("yardsToEndzone"), (st.get("team") or {}).get("id"),
                          en.get("down"), en.get("distance"), en.get("yardsToEndzone"), (en.get("team") or {}).get("id"),
                          p.get("statYardage"), bool(p.get("scoringPlay")), p.get("awayScore"), p.get("homeScore"),
                          (p.get("text") or "")[:160]])
        out["drives"].append({"team": (d.get("team") or {}).get("id"), "result": d.get("result"), "yards": d.get("yards"),
                              "n": d.get("offensivePlays"), "score": bool(d.get("isScore")),
                              "start_yl": (d.get("start") or {}).get("yardLine"), "plays": plays})
    return out


PLAY_COLS = ["type_id", "type", "period", "clock", "down", "dist", "yte", "team", "e_down", "e_dist", "e_yte", "e_team",
             "yards", "scoring", "away_score", "home_score", "text"]


def summary(game_id, refresh=False):
    """Trimmed game summary, cached forever once the game is final."""
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / f"g{game_id}.json.gz"
    if p.exists() and not refresh:
        return json.loads(gzip.decompress(p.read_bytes()))
    t = _trim(_get(f"{SITE}/summary?event={game_id}"))
    if t["state"] == "STATUS_FINAL":
        p.write_bytes(gzip.compress(json.dumps(t, separators=(",", ":")).encode()))
    return t


def core_odds(game_id):
    """Closing line from ESPN's core feed (used when a game summary has none): the middle of the posted books."""
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / f"o{game_id}.json"
    if p.exists():
        return json.loads(p.read_text())
    js = _get(f"https://sports.core.api.espn.com/v2/sports/football/leagues/college-football/events/{game_id}/competitions/{game_id}/odds?limit=50")
    items = [i for i in js.get("items", []) if "live" not in ((i.get("provider") or {}).get("name") or "").lower()]

    def med(vals):
        v = sorted(x for x in vals if x is not None)
        return v[len(v) // 2] if v else None
    out = {"book": "consensus" if len(items) > 1 else ((items[0].get("provider") or {}).get("name") if items else None),
           "spread": med([_num(i.get("spread")) for i in items]), "total": med([_num(i.get("overUnder")) for i in items]),
           "ml_home": med([_num((i.get("homeTeamOdds") or {}).get("moneyLine")) for i in items]),
           "ml_away": med([_num((i.get("awayTeamOdds") or {}).get("moneyLine")) for i in items]),
           "open_spread": med([_num(((((i.get("homeTeamOdds") or {}).get("open") or {}).get("pointSpread")) or {}).get("american")) for i in items]),
           "open_total": med([_num((((i.get("open") or {}).get("total")) or {}).get("american")) for i in items])}
    p.write_text(json.dumps(out))
    return out


def roster(team_id):
    """{player id: position} for a team (QB, RB, WR, TE...). Empty if ESPN has nothing."""
    try:
        js = _get(f"{SITE}/teams/{team_id}/roster", tries=2)
    except Exception:  # noqa: BLE001
        return {}
    out = {}
    for grp in js.get("athletes", []):
        for a in grp.get("items", []):
            try:
                out[int(a["id"])] = {"pos": (a.get("position") or {}).get("abbreviation"),
                                     "out": bool(a.get("injuries")) or ((a.get("status") or {}).get("type") not in (None, "active"))}
            except (KeyError, ValueError, TypeError):
                continue
    return out
