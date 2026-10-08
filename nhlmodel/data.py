"""
Free NHL data from the league's public API: schedule, live scores, box
scores, play-by-play (pbp.py turns it into our own expected-goals tables),
and the free moneylines the league posts on its schedule.

Responses are cached in data/nhl_cache so a run makes each request once.
"""
import json
import logging
import re
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

log = logging.getLogger("nhlmodel")
ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "nhl_cache"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) nhl-model/1.0"}
API = "https://api-web.nhle.com/v1"

def _get(url, timeout=60, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (i + 1))
    raise last


def _cached(name, url, max_age_h=3, timeout=120):
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / name
    if p.exists() and time.time() - p.stat().st_mtime < max_age_h * 3600:
        return p
    p.write_bytes(_get(url, timeout=timeout))
    return p


def api(path, max_age_h=0.5):
    name = "api_" + re.sub(r"[^A-Za-z0-9]+", "_", path) + ".json"
    return json.loads(_cached(name, f"{API}/{path}", max_age_h).read_text())


def team_games(games: pd.DataFrame, since=2021):
    """One row per team per game from data/nhl/games.csv (regulation stats)."""
    g = games[games["season"] >= since].copy()
    rows = []
    for side, opp, flag in (("h", "a", 1), ("a", "h", 0)):
        t = pd.DataFrame({
            "gameId": g["game_id"], "season": g["season"], "date": pd.to_datetime(g["date"]),
            "team": g["home"] if flag else g["away"], "opp": g["away"] if flag else g["home"], "home": flag,
            "xgf": g[f"xg_{side}"], "xga": g[f"xg_{opp}"], "sogf": g[f"sog_{side}"], "soga": g[f"sog_{opp}"],
            "gf": g[f"reg_{side}"], "ga": g[f"reg_{opp}"],
            "gfq": g[f"reg_{side}"] - g[f"en_{side}"], "gaq": g[f"reg_{opp}"] - g[f"en_{opp}"],
            "reg_gf": g[f"reg_{side}"], "reg_ga": g[f"reg_{opp}"],
            "goalsFor": g["hs"] if flag else g["as"], "goalsAgainst": g["as"] if flag else g["hs"],
            "ot": (g["end"] != "REG").astype(int), "so": (g["end"] == "SO").astype(int)})
        rows.append(t)
    return pd.concat(rows).sort_values(["date", "gameId", "home"]).reset_index(drop=True)


def schedule(start: date, days=2):
    """Games from start for a few days, with state, scores and the league's free moneylines."""
    out, seen = [], set()
    d = start
    while d < start + timedelta(days=days):
        js = api(f"schedule/{d.isoformat()}", max_age_h=0.25)
        for wk in js.get("gameWeek", []):
            for g in wk.get("games", []):
                if g["id"] in seen or g.get("gameType") != 2:
                    continue
                seen.add(g["id"])
                def ml(side):
                    for o in side.get("odds") or []:
                        v = str(o.get("value", ""))
                        if re.fullmatch(r"[+-]?\d{3,4}", v):
                            return int(v)
                    return None
                out.append({"game_id": g["id"], "date": wk["date"], "start": g["startTimeUTC"],
                            "state": g.get("gameState"), "home": g["homeTeam"]["abbrev"], "away": g["awayTeam"]["abbrev"],
                            "home_name": g["homeTeam"].get("commonName", {}).get("default", ""),
                            "away_name": g["awayTeam"].get("commonName", {}).get("default", ""),
                            "home_score": g["homeTeam"].get("score"), "away_score": g["awayTeam"].get("score"),
                            "ml_home": ml(g["homeTeam"]), "ml_away": ml(g["awayTeam"]),
                            "last_period": (g.get("gameOutcome") or {}).get("lastPeriodType")})
        d += timedelta(days=7)
    return [g for g in out if start.isoformat() <= g["date"] < (start + timedelta(days=days)).isoformat()]


def boxscore(game_id, max_age_h=24 * 30):
    return api(f"gamecenter/{game_id}/boxscore", max_age_h=max_age_h)


def club_schedule(team, season_id):
    return api(f"club-schedule-season/{team}/{season_id}", max_age_h=6)


def _toi(s):
    try:
        m, sec = str(s).split(":")
        return int(m) + int(sec) / 60
    except Exception:  # noqa: BLE001
        return 0.0


def box_players(box):
    """Flat rows from a finished box score: skaters and goalies with their stats."""
    rows = []
    pbg = box.get("playerByGameStats") or {}
    for side in ("homeTeam", "awayTeam"):
        team = box[side]["abbrev"]
        st = pbg.get(side) or {}
        for grp in ("forwards", "defense"):
            for p in st.get(grp, []):
                rows.append({"pid": p["playerId"], "name": p["name"]["default"], "team": team, "pos": p.get("position"),
                             "toi": _toi(p.get("toi")), "sog": p.get("sog", 0), "goals": p.get("goals", 0),
                             "assists": p.get("assists", 0), "points": p.get("points", 0), "blocks": p.get("blockedShots", 0),
                             "goalie": False})
        for p in st.get("goalies", []):
            rows.append({"pid": p["playerId"], "name": p["name"]["default"], "team": team, "pos": "G",
                         "toi": _toi(p.get("toi")), "saves": p.get("saves", 0), "shots_against": p.get("shotsAgainst", 0),
                         "starter": bool(p.get("starter")), "goalie": True})
    return rows


def last_game_ids(team, before_utc, season_id, n=3):
    """The team's last n finished regular-season games before a time."""
    js = club_schedule(team, season_id)
    done = [g for g in js.get("games", []) if g.get("gameType") == 2 and g.get("gameState") in ("OFF", "FINAL")
            and g["startTimeUTC"] < before_utc]
    return [g["id"] for g in done[-n:]]


