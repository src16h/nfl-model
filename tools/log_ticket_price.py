"""
Save the price Hard Rock paid on a parlay ticket you bet (Nov 11 2026). Run by the "Log ticket price" workflow
(.github/workflows/ticket_price.yml); the inputs arrive as environment variables, never on a command line.

    SPORT   NFL / NHL / NBA / Soccer
    TICKET  one of the ticket names on the Parlays tab (see parlaymoney.KINDS)
    TEAM    any team in the ticket, as the site shows it (TOR, KC, "Man City")
    PRICE   the ticket's price at Hard Rock, American odds (+135, -110)
    DATE    the game date, YYYY-MM-DD (blank = today, Eastern time)

Appends one row to data/ticket_prices.csv. Every model run then grades that ticket at this price
(parlaymoney.attach_prices): the first ticket of that type with that team on or after the date, within 7 days.
"""
import csv
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import parlaymoney as PM  # noqa: E402

SPORTS = {"nfl", "nhl", "nba", "soccer"}
BY_LABEL = {v.lower(): k for k, v in PM.KINDS.items()}


def fail(msg):
    print(f"Not saved: {msg}")
    sys.exit(1)


def main(env=os.environ, path=PM.PRICES):
    sport = env.get("SPORT", "").strip().lower()
    kind = BY_LABEL.get(env.get("TICKET", "").strip().lower(), env.get("TICKET", "").strip())
    team = env.get("TEAM", "").strip()
    price = env.get("PRICE", "").strip().replace(" ", "")
    day = env.get("DATE", "").strip()
    if sport not in SPORTS:
        fail(f"sport must be one of {', '.join(sorted(SPORTS))} (CFB parlays are off)")
    if kind not in PM.KINDS:
        fail(f"ticket must be one of: {', '.join(PM.KINDS.values())}")
    if not re.fullmatch(r"[A-Za-z][A-Za-z .'&-]{1,29}", team):
        fail("team should be a team name or abbreviation as the site shows it, like TOR or Man City")
    if not re.fullmatch(r"[+-]?\d{3,5}", price) or PM.dec(price) is None:
        fail("price should be American odds like +135 or -110")
    if not price.startswith(("+", "-")):
        price = "+" + price
    today = datetime.now(ZoneInfo("America/New_York")).date()
    if day:
        try:
            d = date.fromisoformat(day)
        except ValueError:
            fail("date should look like 2026-11-15")
        if abs((d - today).days) > 14:
            fail("date is more than two weeks away from today")
    else:
        d = today
    new = not Path(path).exists() or Path(path).stat().st_size == 0
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["logged_at", "sport", "ticket", "team", "date", "price"])
        w.writerow([datetime.now(timezone.utc).isoformat(timespec="minutes"), sport, kind, team, d.isoformat(), price])
    print(f"Saved: {sport.upper()} {PM.KINDS[kind]} with {team}, {d.isoformat()}, {price}. "
          "It counts at that price from the next model run.")


if __name__ == "__main__":
    main()
