"""
Kalshi vs Hard Rock check (Oct 31 2026): for the next few games in each sport, the game lines Kalshi and Hard Rock
post through The Odds API, side by side, plus which markets Kalshi posts per event (props, alt lines?).
About 3 credits per sport for the lines and 1 per event checked. Run from the "Odds market check" workflow.
"""
import json
import os
import urllib.parse
import urllib.request

BASE = "https://api.the-odds-api.com"
SPORTS = [("basketball_nba", "ODDS_API_KEY_NBA"), ("icehockey_nhl", "ODDS_API_KEY_NHL"), ("americanfootball_nfl", "ODDS_API_KEY"),
          ("americanfootball_ncaaf", "ODDS_API_KEY_CFB"), ("soccer_epl", "ODDS_API_KEY_SOCCER")]


def get(path, key, **p):
    p["apiKey"] = key
    with urllib.request.urlopen(f"{BASE}{path}?{urllib.parse.urlencode(p, safe=',')}", timeout=25) as r:
        return json.loads(r.read().decode()), r.headers.get("x-requests-remaining"), r.headers.get("x-requests-last")


def main(n=3):
    for sport, env in SPORTS:
        key = os.environ.get(env, "").strip()
        if not key:
            print(f"{sport}: no {env}")
            continue
        try:
            data, rem, last = get(f"/v4/sports/{sport}/odds", key, markets="h2h,spreads,totals", oddsFormat="american",
                                  bookmakers="hardrockbet,kalshi,pinnacle,draftkings")
        except Exception as e:  # noqa: BLE001
            print(f"{sport}: {e}")
            continue
        n_k = sum(1 for ev in data if any(b["key"] == "kalshi" for b in ev.get("bookmakers", [])))
        print(f"\n=== {sport}: {len(data)} events, Kalshi on {n_k}; cost {last}, left {rem}")
        shown = 0
        for ev in data:
            bks = {b["key"]: b for b in ev.get("bookmakers", [])}
            if "kalshi" not in bks:
                continue
            print(f"\n{ev['away_team']} at {ev['home_team']} ({ev['commence_time']})")
            for k in ("hardrockbet", "kalshi", "draftkings", "pinnacle"):
                if k not in bks:
                    print(f"  {k:12s} -")
                    continue
                parts = []
                for m in bks[k].get("markets", []):
                    parts.append(m["key"] + " " + " / ".join(f"{o['name'][:12]} {o.get('point', '')} {o['price']}" for o in m["outcomes"]))
                print(f"  {k:12s} " + " | ".join(parts) + f"  (updated {bks[k].get('last_update')})")
            try:
                mk, _, _ = get(f"/v4/sports/{sport}/events/{ev['id']}/markets", key, bookmakers="kalshi,hardrockbet")
                for b in mk.get("bookmakers", []):
                    print(f"  markets {b['key']:12s} {', '.join(sorted(m['key'] for m in b.get('markets', [])))}")
            except Exception as e:  # noqa: BLE001
                print(f"  markets: {e}")
            shown += 1
            if shown >= n:
                break


if __name__ == "__main__":
    main()
