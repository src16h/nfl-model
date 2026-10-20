"""
Free soccer data.

- Football-Data.co.uk: every match with goals, shots, shots on target and closing odds
  (1X2, over/under 2.5, Asian handicap). Used for ratings history and the backtest.
- Understat: expected goals per match (Premier League and La Liga only).
- ESPN: fixtures, live status, results and player box scores (goals, shots, shots on target,
  starts) for all three leagues. Used for upcoming games, grading and player props.

Finished seasons and finished matches are cached under data/soccer so later runs only fetch
what changed.
"""
import gzip
import io
import json
import logging
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from .teams import canon

log = logging.getLogger("soccermodel")
CACHE = Path(__file__).resolve().parent.parent / "data" / "soccer"
UA = {"User-Agent": "Mozilla/5.0 (soccer-model)", "Accept-Encoding": "identity"}


def fetch(url, tries=3, headers=None, timeout=30):
    h = dict(UA, **(headers or {}))
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
                body = r.read()
            return gzip.decompress(body) if body[:2] == b"\x1f\x8b" else body
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                raise
            log.warning(f"retry {url}: {type(e).__name__}")
            time.sleep(2 + 3 * i)


def season_of(d: date) -> int:
    return d.year if d.month >= 7 else d.year - 1


def season_code(s: int) -> str:
    return f"{s % 100:02d}{(s + 1) % 100:02d}"


# ---------------------------------------------------------------------------
# Football-Data.co.uk
# ---------------------------------------------------------------------------
def _first(df, cols):
    """First column that exists and has data, row by row."""
    out = pd.Series(np.nan, index=df.index, dtype=float)
    for c in cols:
        if c in df.columns:
            v = pd.to_numeric(df[c], errors="coerce")
            out = out.fillna(v)
    return out


def fd_matches(league, seasons, current):
    """All matches for a league, oldest first. Columns: league, season, date, home, away, hg, ag, hs, as_, hst, ast,
    close_h/d/a (closing 1X2 decimal odds), close_o25/u25, ah_line (home handicap), close_ahh/aha."""
    div = C.LEAGUES[league]["fd"]
    frames = []
    for s in seasons:
        path = CACHE / "fd" / f"{div}_{season_code(s)}.csv"
        if s >= current or not path.exists():
            try:
                raw = fetch(f"https://www.football-data.co.uk/mmz4281/{season_code(s)}/{div}.csv")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            except Exception as e:  # noqa: BLE001
                log.warning(f"football-data {div} {s}: {e}")
                if not path.exists():
                    continue
        raw = path.read_bytes().decode("utf-8-sig", errors="ignore")
        if not raw.strip():
            continue
        df = pd.read_csv(io.StringIO(raw), on_bad_lines="skip")
        df = df.dropna(subset=["HomeTeam", "AwayTeam"])
        if df.empty:
            continue
        d = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
        out = pd.DataFrame({
            "league": league, "season": s, "date": d.dt.date,
            "home": df["HomeTeam"].map(canon), "away": df["AwayTeam"].map(canon),
            "hg": pd.to_numeric(df.get("FTHG"), errors="coerce"), "ag": pd.to_numeric(df.get("FTAG"), errors="coerce"),
            "hs": _first(df, ["HS"]), "as_": _first(df, ["AS"]), "hst": _first(df, ["HST"]), "ast": _first(df, ["AST"]),
            "close_h": _first(df, ["PSCH", "AvgCH", "B365CH", "PSH", "AvgH"]),
            "close_d": _first(df, ["PSCD", "AvgCD", "B365CD", "PSD", "AvgD"]),
            "close_a": _first(df, ["PSCA", "AvgCA", "B365CA", "PSA", "AvgA"]),
            "close_o25": _first(df, ["PC>2.5", "AvgC>2.5", "B365C>2.5", "P>2.5", "Avg>2.5"]),
            "close_u25": _first(df, ["PC<2.5", "AvgC<2.5", "B365C<2.5", "P<2.5", "Avg<2.5"]),
            "ah_line": _first(df, ["AHCh", "AHh"]),
            "close_ahh": _first(df, ["PCAHH", "AvgCAHH", "B365CAHH", "PAHH", "AvgAHH"]),
            "close_aha": _first(df, ["PCAHA", "AvgCAHA", "B365CAHA", "PAHA", "AvgAHA"]),
            # early retail prices (collected Tuesday/Friday, Bet365 then market average): what a bettor gets
            "early_h": _first(df, ["B365H", "AvgH", "BWH"]), "early_d": _first(df, ["B365D", "AvgD", "BWD"]),
            "early_a": _first(df, ["B365A", "AvgA", "BWA"]),
            "early_o25": _first(df, ["B365>2.5", "Avg>2.5"]), "early_u25": _first(df, ["B365<2.5", "Avg<2.5"]),
            "early_ah_line": _first(df, ["AHh"]),
            "early_ahh": _first(df, ["B365AHH", "AvgAHH"]), "early_aha": _first(df, ["B365AHA", "AvgAHA"]),
            # Pinnacle's early prices (same collection time): the sharp reference
            "sharp_h": _first(df, ["PSH"]), "sharp_d": _first(df, ["PSD"]), "sharp_a": _first(df, ["PSA"]),
            "sharp_o25": _first(df, ["P>2.5"]), "sharp_u25": _first(df, ["P<2.5"]),
            "sharp_ahh": _first(df, ["PAHH"]), "sharp_aha": _first(df, ["PAHA"]),
            "close_ah_line": _first(df, ["AHCh"]),
        })
        oc = [c for c in out.columns if c.startswith(("close_", "early_", "sharp_")) and "line" not in c]
        out[oc] = out[oc].where(out[oc] > 1.01)          # a few rows carry 0 or 1.0 for missing prices
        frames.append(out.dropna(subset=["date"]))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).sort_values("date", kind="stable").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Understat (xG)
# ---------------------------------------------------------------------------
def understat_matches(league, seasons, current):
    """date, home, away, hxg, axg for finished matches."""
    us = C.LEAGUES[league]["understat"]
    if not us:
        return pd.DataFrame(columns=["date", "home", "away", "hxg", "axg"])
    rows = []
    for s in seasons:
        path = CACHE / "understat" / f"{us}_{s}.json"
        data = None
        if s >= current or not path.exists():
            try:
                raw = fetch(f"https://understat.com/getLeagueData/{us}/{s}", headers={"X-Requested-With": "XMLHttpRequest",
                                                                                      "Referer": f"https://understat.com/league/{us}/{s}"})
                data = json.loads(raw)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({"dates": data.get("dates", [])}, separators=(",", ":")))
            except Exception as e:  # noqa: BLE001
                log.warning(f"understat {us} {s}: {e}")
        if data is None and path.exists():
            data = json.loads(path.read_text())
        for m in (data or {}).get("dates", []):
            if not m.get("isResult"):
                continue
            rows.append({"date": datetime.strptime(m["datetime"][:10], "%Y-%m-%d").date(),
                         "home": canon(m["h"]["title"]), "away": canon(m["a"]["title"]),
                         "hxg": float(m["xG"]["h"]), "axg": float(m["xG"]["a"])})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# ESPN (fixtures, results, player box scores)
# ---------------------------------------------------------------------------
ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer"


def espn_day(league, d: date):
    slug = C.LEAGUES[league]["espn"]
    try:
        js = json.loads(fetch(f"{ESPN}/{slug}/scoreboard?dates={d:%Y%m%d}"))
    except Exception as e:  # noqa: BLE001
        log.warning(f"espn {slug} {d}: {e}")
        return []
    out = []
    for e in js.get("events", []):
        comp = e["competitions"][0]
        cs = {c["homeAway"]: c for c in comp["competitors"]}
        if "home" not in cs or "away" not in cs:
            continue
        st = e["status"]["type"]
        out.append({"league": league, "event_id": e["id"], "start": e["date"],
                    "home": canon(cs["home"]["team"]["displayName"]), "away": canon(cs["away"]["team"]["displayName"]),
                    "home_espn": cs["home"]["team"]["id"], "away_espn": cs["away"]["team"]["id"],
                    "hg": int(cs["home"]["score"]) if st.get("completed") and cs["home"].get("score") not in (None, "") else None,
                    "ag": int(cs["away"]["score"]) if st.get("completed") and cs["away"].get("score") not in (None, "") else None,
                    "state": st.get("state"), "completed": bool(st.get("completed")), "status": st.get("name")})
    return out


def espn_window(league, start: date, end: date):
    out, d = [], start
    while d <= end:
        out += espn_day(league, d)
        d += timedelta(days=1)
    seen, uniq = set(), []
    for g in out:                       # ESPN days are US dates; late games can show twice
        if g["event_id"] not in seen:
            seen.add(g["event_id"])
            uniq.append(g)
    return uniq


def espn_box(league, event_id):
    """Player lines for a finished match: [{pid, name, team, pos, start, sub_in, sub_out, goals, shots, sot, pen_goals}]
    plus team stats. Cached once the match is final."""
    path = CACHE / "espn_box" / f"{event_id}.json"
    if path.exists():
        return json.loads(path.read_text())
    slug = C.LEAGUES[league]["espn"]
    try:
        js = json.loads(fetch(f"{ESPN}/{slug}/summary?event={event_id}"))
    except Exception as e:  # noqa: BLE001
        log.warning(f"espn box {event_id}: {e}")
        return None
    final = js.get("header", {}).get("competitions", [{}])[0].get("status", {}).get("type", {}).get("completed")
    sub_min, pen = {}, {}
    for k in js.get("keyEvents", []):
        t = (k.get("type") or {}).get("text", "")
        clock = (k.get("clock") or {}).get("displayValue", "") or ""
        try:
            minute = int(clock.split("'")[0].split("+")[0]) if clock else None
        except ValueError:
            minute = None
        parts = k.get("participants") or []
        if t.startswith("Substitution") and minute is not None:
            ids = [p.get("athlete", {}).get("id") for p in parts]
            if ids:
                sub_min[ids[0]] = minute                # first participant comes on
            if len(ids) > 1:
                sub_min[ids[1]] = minute                # second goes off
        if "Penalty" in t and "Goal" in t and parts:
            aid = parts[0].get("athlete", {}).get("id")
            pen[aid] = pen.get(aid, 0) + 1
    players = []
    for team in js.get("rosters", []):
        tname = canon(team["team"]["displayName"])
        for p in team.get("roster", []):
            st = {s["name"]: s.get("value") for s in p.get("stats", [])}
            if not st.get("appearances"):
                continue
            aid = p["athlete"]["id"]
            start = bool(p.get("starter"))
            m = sub_min.get(aid)
            if start:
                mins = m if p.get("subbedOut") and m is not None else (C.START_MIN if p.get("subbedOut") else 90)
            else:
                mins = max(90 - m, 1) if m is not None else C.SUB_MIN
            players.append({"pid": aid, "name": p["athlete"]["displayName"], "team": tname,
                            "pos": (p.get("position") or {}).get("abbreviation", ""), "start": start,
                            "min": float(mins), "goals": int(st.get("totalGoals") or 0) - 0,
                            "shots": int(st.get("totalShots") or 0), "sot": int(st.get("shotsOnTarget") or 0),
                            "own_goals": int(st.get("ownGoals") or 0), "pen_goals": pen.get(aid, 0)})
    out = {"event_id": event_id, "final": bool(final), "players": players}
    if final and players:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, separators=(",", ":")))
    return out
