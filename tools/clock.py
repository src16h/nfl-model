"""
On-time starter for the model workflows (Nov 10 2026).

GitHub's own cron triggers have fired 2-10 hours late since Nov 1 2026 (median 2.6-4.9 hours by workflow), so pre-game
runs landed after games started. Runs started with workflow_dispatch begin within seconds. This script runs inside the
"Clock" workflow: it reads the cron lines already written in each model workflow and, every minute, dispatches any
workflow whose cron time has come. After about 5h45m it stops and the workflow starts a fresh copy of itself (GitHub
jobs can't run longer than 6 hours).

The workflows keep their own cron lines as a backup: a late scheduled run skips itself when the clock already started
that workflow in the last few hours (the guard job in each workflow).

    GITHUB_TOKEN=... python tools/clock.py [minutes] [since]   # minutes to run (default 345); since = the last minute the
                                                              # previous clock handled (ISO, UTC), so nothing runs twice
"""
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from records_check import _cron_hit  # noqa: E402

WORKFLOWS = ["weekly.yml", "nhl.yml", "nba.yml", "cfb.yml", "soccer.yml", "review.yml"]
REPO = os.environ.get("GITHUB_REPOSITORY", "src16h/nfl-model")
REF = os.environ.get("GITHUB_REF_NAME", "main")


def crons():
    out = {}
    for w in WORKFLOWS:
        p = ROOT / ".github" / "workflows" / w
        if p.exists():
            out[w] = re.findall(r'^\s*-\s*cron:\s*"([^"]+)"', p.read_text(), flags=re.M)
    return out


def dispatch(w):
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/actions/workflows/{w}/dispatches", method="POST",
                                 data=json.dumps({"ref": REF}).encode(),
                                 headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
                                          "Accept": "application/vnd.github+json"})
    for i in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20):
                return True
        except Exception as e:  # noqa: BLE001
            print(f"  dispatch {w} failed ({e}), retry {i + 1}", flush=True)
            time.sleep(10)
    return False


def main(minutes, since=None):
    table = crons()
    print("Schedules:", json.dumps(table), flush=True)
    start = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    end = start + timedelta(minutes=minutes)
    # pick up where the previous clock stopped (nothing twice, nothing missed); with no hand-off, catch up 3 minutes
    last = start - timedelta(minutes=3)
    if since:
        try:
            s_ = datetime.fromisoformat(since.replace("Z", "+00:00"))
            if start - timedelta(minutes=30) <= s_ <= start:
                last = s_
        except ValueError:
            pass
    while True:
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        t = last + timedelta(minutes=1)
        while t <= now:
            for w, cs in table.items():
                if any(_cron_hit(c, t) for c in cs):
                    ok = dispatch(w)
                    print(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} {w} for {t:%H:%M} UTC: {'started' if ok else 'FAILED'}", flush=True)
            t += timedelta(minutes=1)
        last = now
        if now >= end:
            break
        nxt = now + timedelta(minutes=1)
        time.sleep(max(1.0, (nxt - datetime.now(timezone.utc)).total_seconds() + 1))
    Path(os.environ.get("CLOCK_STATE", "/tmp/clock_last")).write_text(last.isoformat(timespec="minutes"))
    print(f"Clock done at {last:%H:%M} UTC; the workflow starts the next one.", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1] else 345, sys.argv[2] if len(sys.argv) > 2 else None)
