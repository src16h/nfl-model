"""
Fatigue and fixture congestion.

ESPN keeps each club's schedule per competition. We add every non-league game (Champions League,
Europa League, Conference League, domestic cups) to the league fixtures, then for each match work
out each side's rest: days since its last game, and whether that game was a midweek cup or
European tie. The effect on goals is fitted from history (backtest.fit_fatigue) and applied to
expected goals.
"""
import json
import logging
import time
from datetime import date, datetime, timedelta

from . import config as C
from . import data as D
from .teams import canon

log = logging.getLogger("soccermodel")
TEAM_LISTS = ["eng.1", "eng.2", "eng.3", "eng.4", "esp.1", "esp.2"]
EURO = ["uefa.champions", "uefa.europa", "uefa.europa.conf"]
CUPS = {"epl": ["eng.fa", "eng.league_cup"], "champ": ["eng.fa", "eng.league_cup"], "laliga": ["esp.copa_del_rey"]}


def team_ids():
    path = D.CACHE / "espn_team_ids.json"
    ids = json.loads(path.read_text()) if path.exists() else {}
    if len(ids) < 60:
        for slug in TEAM_LISTS:
            try:
                js = json.loads(D.fetch(f"{D.ESPN}/{slug}/teams"))
                for t in js["sports"][0]["leagues"][0]["teams"]:
                    ids.setdefault(canon(t["team"]["displayName"]), t["team"]["id"])
            except Exception as e:  # noqa: BLE001
                log.warning(f"espn teams {slug}: {e}")
        path.write_text(json.dumps(ids, indent=0, sort_keys=True))
    return ids


def other_games(team_id, league, season, current):
    """Dates (UTC date of kickoff) of a club's non-league games in a season. Past seasons are cached."""
    comps = (EURO if league in ("epl", "laliga") else []) + CUPS.get(league, [])
    out = []
    for comp in comps:
        path = D.CACHE / "espn_sched" / f"{team_id}_{comp}_{season}.json"
        fresh = path.exists() and (time.time() - path.stat().st_mtime) < 20 * 3600
        if path.exists() and (season < current or fresh):
            dates = json.loads(path.read_text())
        else:
            dates = []
            try:
                js = json.loads(D.fetch(f"{D.ESPN}/{comp}/teams/{team_id}/schedule?season={season}"))
                dates = sorted({e["date"][:10] for e in js.get("events", [])})
            except Exception as e:  # noqa: BLE001
                log.warning(f"espn schedule {team_id} {comp} {season}: {type(e).__name__}")
                if path.exists():
                    dates = json.loads(path.read_text())
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(dates))
        out += [date.fromisoformat(d) for d in dates]
    return sorted(set(out))


def schedules(frames, current, seasons):
    """{(team, season): sorted list of (date, kind)} with kind 'L' league or 'X' other competition."""
    ids = team_ids()
    sched = {}
    for lg, df in frames.items():
        for s in seasons:
            d = df[df["season"] == s]
            for t in set(d["home"]) | set(d["away"]):
                games = [(x, "L") for x in d.loc[(d["home"] == t) | (d["away"] == t), "date"]]
                tid = ids.get(t)
                if tid:
                    games += [(x, "X") for x in other_games(tid, lg, s, current)]
                sched[(t, s)] = sorted(set(games))
    return sched


def rest(sched, team, season, when: date):
    """(days since last game capped at 10, 1 if that game was a cup/European tie within 4 days, games in last 14 days)."""
    games = sched.get((team, season), [])
    prev = [(d, k) for d, k in games if d < when]
    if not prev:
        return 10, 0, 0
    last_d, last_k = prev[-1]
    days = min((when - last_d).days, 10)
    mid = 1 if (last_k == "X" and days <= 4) else 0
    busy = sum(1 for d, _ in prev if (when - d).days <= 14)
    return days, mid, busy


def adjust(coef, days_h, mid_h, days_a, mid_a):
    """Multipliers for home and away expected goals from the fitted effects (attack of each side, defence of the other)."""
    import math
    sh = 1 if days_h <= 3 else 0
    sa = 1 if days_a <= 3 else 0
    lh = coef.get("short_att", 0) * sh + coef.get("mid_att", 0) * mid_h + coef.get("short_def", 0) * sa + coef.get("mid_def", 0) * mid_a
    la = coef.get("short_att", 0) * sa + coef.get("mid_att", 0) * mid_a + coef.get("short_def", 0) * sh + coef.get("mid_def", 0) * mid_h
    cap = C.FATIGUE_CAP
    return math.exp(max(-cap, min(cap, lh))), math.exp(max(-cap, min(cap, la)))


def live_schedules(frames, upcoming, season):
    """Schedules for clubs with an upcoming match: this season's league games (played and upcoming) plus cup and
    European games (refreshed about daily)."""
    ids = team_ids()
    sched = {}
    for f in upcoming:
        lg = f["league"]
        df = frames[lg]
        d = df[df["season"] == season]
        for t in (f["home"], f["away"]):
            if (t, season) in sched:
                continue
            games = [(x, "L") for x in d.loc[(d["home"] == t) | (d["away"] == t), "date"]]
            games += [(datetime.fromisoformat(u["start"].replace("Z", "+00:00")).date(), "L") for u in upcoming
                      if t in (u["home"], u["away"])]
            if ids.get(t):
                games += [(x, "X") for x in other_games(ids[t], lg, season, season)]
            sched[(t, season)] = sorted(set(games))
    return sched
