"""
Which NBA alt prop lines the books actually post (Oct 31 2026): for the next 2 games, every rung of the alt ladders
(points, rebounds, assists, threes) at Hard Rock, Kalshi and DraftKings. About 4 credits per game.
"""
import json
import os
import urllib.parse
import urllib.request

BASE = "https://api.the-odds-api.com"
MK = "player_points_alternate,player_rebounds_alternate,player_assists_alternate,player_threes_alternate"


def get(path, **p):
    p["apiKey"] = os.environ["ODDS_API_KEY_NBA"]
    with urllib.request.urlopen(f"{BASE}{path}?{urllib.parse.urlencode(p, safe=',')}", timeout=25) as r:
        return json.loads(r.read().decode()), r.headers.get("x-requests-remaining"), r.headers.get("x-requests-last")


evs, _, _ = get("/v4/sports/basketball_nba/events")
for ev in evs[:2]:
    d, rem, last = get(f"/v4/sports/basketball_nba/events/{ev['id']}/odds", markets=MK, oddsFormat="american",
                       bookmakers="hardrockbet,kalshi,draftkings")
    print(f"\n{ev['away_team']} at {ev['home_team']}: cost {last}, left {rem}")
    for b in d.get("bookmakers", []):
        for m in b.get("markets", []):
            lad = {}
            for o in m["outcomes"]:
                lad.setdefault(o.get("description"), []).append((o["name"][0], o.get("point"), o["price"]))
            mins = sorted({min(p for _, p, _ in v if p is not None) for v in lad.values() if any(p is not None for _, p, _ in v)})
            print(f"  {b['key']:11s} {m['key']:28s} players {len(lad):2d}  lowest rung per player {mins[:12]}")
            for name, v in list(lad.items())[:3]:
                print(f"      {name}: " + ", ".join(f"{s}{p} {pr}" for s, p, pr in sorted(v, key=lambda t: (t[1] or 0))[:12]))
