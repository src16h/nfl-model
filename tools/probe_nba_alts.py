"""
Which NBA alt prop lines the books actually post (Oct 31 2026): for the next 2 games, every rung of the alt ladders
(points, rebounds, assists, threes) at Hard Rock, Kalshi and DraftKings. About 4 credits per game.
"""
import json
import os
import urllib.parse
import urllib.request

BASE = "https://api.the-odds-api.com"
import sys as _s
SPORT = os.environ.get("PROBE_SPORT", "basketball_nba")
KEY = "ODDS_API_KEY_NHL" if SPORT == "icehockey_nhl" else "ODDS_API_KEY_NBA"
MK = os.environ.get("PROBE_MARKETS") or "player_points_alternate,player_rebounds_alternate,player_assists_alternate,player_threes_alternate"
N_EV = int(os.environ.get("PROBE_EVENTS", "2"))


def get(path, **p):
    p["apiKey"] = os.environ[KEY]
    with urllib.request.urlopen(f"{BASE}{path}?{urllib.parse.urlencode(p, safe=',')}", timeout=25) as r:
        return json.loads(r.read().decode()), r.headers.get("x-requests-remaining"), r.headers.get("x-requests-last")


evs, _, _ = get(f"/v4/sports/{SPORT}/events")
for ev in evs[:N_EV]:
    d, rem, last = get(f"/v4/sports/{SPORT}/events/{ev['id']}/odds", markets=MK, oddsFormat="american",
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

# Nov 3 2026 (weekly review): Hard Rock's own ladder floor, per player. With PROBE_MAIN set (e.g.
# "player_points,player_rebounds,player_assists,player_threes"), also pulls Hard Rock's main lines and prints, per stat,
# how far below the main line Hard Rock's lowest alt rung sits (main minus lowest rung), so the parlay legs can be held
# to lines Hard Rock really lists. Extra cost: 1 credit per main market per game.
MAIN = os.environ.get("PROBE_MAIN", "")
if MAIN:
    ALT_OF = {m: m + "_alternate" for m in MAIN.split(",")}
    ALT_OF.update({"player_shots_on_goal": "player_shots_alternate"} if "player_shots_on_goal" in ALT_OF else {})
    gaps = {}
    for ev in evs[:N_EV]:
        d, rem, last = get(f"/v4/sports/{SPORT}/events/{ev['id']}/odds", markets=MAIN + "," + ",".join(ALT_OF.values()),
                           oddsFormat="american", bookmakers="hardrockbet")
        print(f"\n[main vs ladder] {ev['away_team']} at {ev['home_team']}: cost {last}, left {rem}")
        mk = {m["key"]: m for b in d.get("bookmakers", []) for m in b.get("markets", [])}
        for main_k, alt_k in ALT_OF.items():
            mains = {o.get("description"): o.get("point") for o in (mk.get(main_k) or {}).get("outcomes", []) if o["name"] == "Over"}
            lows = {}
            for o in (mk.get(alt_k) or {}).get("outcomes", []):
                if o["name"] == "Over" and o.get("point") is not None:
                    lows[o.get("description")] = min(lows.get(o.get("description"), 99), o["point"])
            for nm, m in mains.items():
                if m is not None and nm in lows:
                    gaps.setdefault(main_k, []).append((nm, m, lows[nm]))
            print(f"  {main_k}: {len(mains)} main lines, {len(lows)} alt ladders, missing ladder: "
                  f"{sorted(set(mains) - set(lows))[:8]}")
    for k, v in gaps.items():
        print(f"\n{k}: main - lowest rung, per player (Hard Rock)")
        for nm, m, lo in sorted(v, key=lambda t: t[1]):
            print(f"    {nm}: main {m}, lowest {lo}, gap {m - lo:g}")
