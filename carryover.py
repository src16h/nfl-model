"""Keep started games on the page until they're final (Nov 1 2026).

Each daily model only prices games that haven't started, so a game used to vanish from the
page at the first run after puck drop / tip / kickoff, taking its plays, props and parlays with
it. carry_started() puts those games back from the previous page data (latest.json), exactly as
they were at the last pre-start run, tagged "started": True, until the final score is in.

A game is dropped when its result is in (finals), or MAX_HOURS after its start as a safety net
in case a final never comes through (postponed, suspended, missing box score).
"""
import json
from datetime import datetime, timezone
from pathlib import Path

MAX_HOURS = 8


def _start(g):
    s = g.get("start")
    if not s:
        return None
    try:
        t = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def carry_started(latest_path, games, players, finals, now, max_hours=MAX_HOURS):
    """Return (games, players) with started, unfinished games from the last page added back.

    latest_path: the sport's latest.json (read before it's overwritten)
    finals: game ids with a final score
    """
    try:
        old = json.loads(Path(latest_path).read_text())
    except Exception:  # noqa: BLE001  first run, or unreadable file: nothing to carry
        return games, players
    live = {str(g.get("game_id")) for g in games}
    finals = {str(x) for x in (finals or ())}
    kept = []
    for g in old.get("games") or []:
        gid = str(g.get("game_id"))
        t = _start(g)
        if gid in live or gid in finals or t is None or t > now:
            continue
        if (now - t).total_seconds() > max_hours * 3600:
            continue
        kept.append({**g, "started": True})
    if not kept:
        return games, players
    ids = {str(g["game_id"]) for g in kept}
    have = {(str(p.get("game_id")), str(p.get("pid"))) for p in players}
    kept_p = [p for p in old.get("players") or []
              if str(p.get("game_id")) in ids and (str(p.get("game_id")), str(p.get("pid"))) not in have]
    out = sorted(list(games) + kept, key=lambda g: str(g.get("start") or ""))
    return out, list(players) + kept_p
