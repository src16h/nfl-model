"""
Which markets each book posts for a sport's next events (The Odds API event-markets endpoint).

Costs about 1 credit per event checked. Run from the "Odds market check" workflow (manual only).
"""
import json
import os
import sys
import urllib.parse
import urllib.request

BASE = "https://api.the-odds-api.com"
BOOKS = "hardrockbet,draftkings,fanduel,betmgm,pinnacle,betfair_ex_uk,williamhill"
SPORTS = [("americanfootball_nfl", "ODDS_API_KEY"), ("icehockey_nhl", "ODDS_API_KEY_NHL"), ("soccer_epl", "ODDS_API_KEY_SOCCER")]


def get(path, key, **p):
    p["apiKey"] = key
    with urllib.request.urlopen(f"{BASE}{path}?{urllib.parse.urlencode(p, safe=',')}", timeout=25) as r:
        return json.loads(r.read().decode()), r.headers.get("x-requests-remaining"), r.headers.get("x-requests-last")


def main(n=2):
    for sport, env in SPORTS:
        key = os.environ.get(env, "").strip()
        if not key:
            print(f"{sport}: no {env}")
            continue
        evs, _, _ = get(f"/v4/sports/{sport}/events", key)          # free
        for ev in evs[:n]:
            try:
                data, rem, last = get(f"/v4/sports/{sport}/events/{ev['id']}/markets", key, bookmakers=BOOKS)
            except Exception as e:  # noqa: BLE001
                print(f"{sport} {ev.get('away_team')} at {ev.get('home_team')}: {e}")
                continue
            print(f"\n{sport}: {ev['away_team']} at {ev['home_team']} ({ev['commence_time']}), cost {last}, left {rem}")
            for b in data.get("bookmakers", []):
                print(f"  {b['key']:15s} {', '.join(sorted(m['key'] for m in b.get('markets', [])))}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 2)
