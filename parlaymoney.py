"""
What the parlay tickets would have returned in units (Nov 11 2026).

Until now a ticket record only compared the model's chance with how often tickets hit ("said vs hit"). A ticket can
hit exactly as often as the model says and still lose money, because the book pays less than the fair price. So each
graded ticket is also scored in units, 1 unit a ticket:

  at_bet_at : at the ticket's "bet at" price, the shortest odds the page says to accept (fair price plus a 7% cushion).
              This is the most you could have made by following the page: bet only when Hard Rock offered that price
              or better, at exactly that price. If tickets lose even here, they lose at any price you would take.
  at_fair   : at the model's own fair price. Close to 0 when the chances are right; below 0 means they ran too high.
  at_book   : at the book's real price: a cross-game ticket with every leg priced at Hard Rock, or any ticket whose
              Hard Rock price the owner logged (data/ticket_prices.csv, written by the "Log ticket price" workflow).

Hard Rock's real same-game parlay price is not in the odds feed (it is built when you make the slip), so the only way
to know it is to save it when the ticket is bet. A logged price is matched to a ticket by sport, ticket type and one
team in it: the first such ticket on or after the logged date, within LOG_DAYS days. Each logged price fits one ticket.
"""
import csv
import math
from datetime import date
from pathlib import Path

PRICES = Path(__file__).resolve().parent / "data" / "ticket_prices.csv"
LOG_DAYS = 7
KINDS = {"alt": "Same-game parlay", "alt_mix": "Alt parlay with a team leg", "alt_ladder": "Ladder-style parlay",
         "cross": "Cross-game alt parlay"}
_cache = {}


def load_prices(path=None):
    """Logged Hard Rock ticket prices: [{sport, kind, team, date, price}]."""
    path = Path(path or PRICES)
    key = (str(path), path.stat().st_mtime if path.exists() else None)
    if key in _cache:
        return _cache[key]
    out = []
    try:
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                try:
                    d = date.fromisoformat((r.get("date") or "").strip())
                except ValueError:
                    continue
                if dec(r.get("price")) is None:
                    continue
                out.append({"sport": (r.get("sport") or "").strip().lower(), "kind": (r.get("ticket") or "").strip(),
                            "team": (r.get("team") or "").strip().lower(), "date": d, "price": r["price"].strip()})
    except FileNotFoundError:
        pass
    _cache[key] = out
    return out


def _team_ok(logged, teams):
    for t in teams or []:
        t = str(t or "").strip().lower()
        if t and (t == logged or (len(logged) >= 4 and (logged in t or t in logged))):   # soccer names: "Man City" / "Manchester City"
            return True
    return False


def attach_prices(rows, prices=None):
    """Sets row["logged_price"] on the tickets a logged price belongs to. rows need sport, kind, date, teams."""
    prices = load_prices() if prices is None else prices
    taken = set()
    for lp in sorted(prices, key=lambda x: x["date"]):
        best, gap = None, None
        for i, r in enumerate(rows):
            if i in taken or r.get("sport") != lp["sport"] or r.get("kind") != lp["kind"]:
                continue
            try:
                d = date.fromisoformat(str(r.get("date"))[:10])
            except ValueError:
                continue
            g = (d - lp["date"]).days
            if 0 <= g <= LOG_DAYS and _team_ok(lp["team"], r.get("teams")) and (gap is None or g < gap):
                best, gap = i, g
        if best is not None:
            taken.add(best)
            rows[best]["logged_price"] = lp["price"]
    return rows


def dec(odds):
    """American odds (number or text like "+122") as a decimal price; None when missing or unreadable."""
    try:
        o = float(str(odds).replace("+", ""))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(o) or -100 < o < 100:
        return None
    return 1 + (o / 100 if o > 0 else 100 / -o)


def _score(rows, key):
    xs = [(bool(x["hit"]), dec(x.get(key))) for x in rows]
    xs = [(h, d) for h, d in xs if d is not None]
    if not xs:
        return {"n": 0, "units": None, "roi": None}
    u = sum((d - 1) if h else -1.0 for h, d in xs)
    sq = sum(((d - 1) if h else -1.0) ** 2 for h, d in xs)
    return {"n": len(xs), "hits": sum(h for h, _ in xs), "units": round(u, 2), "roi": round(100 * u / len(xs), 1),
            "z": round(u / math.sqrt(sq), 2) if sq else None,
            "breakeven": round(100 * sum(1 / d for _, d in xs) / len(xs), 1)}     # hit rate needed to break even, average


def summary(rows, prices=None):
    """rows: graded tickets with "hit" (True/False) and any of "bet_at", "fair", "book_odds"; with sport, kind, date and
    teams, a logged Hard Rock price (data/ticket_prices.csv) is used as the book price."""
    rows = [dict(x) for x in rows or [] if x.get("hit") is not None]
    attach_prices(rows, prices)
    for x in rows:
        if x.get("logged_price") and not x.get("book_odds"):
            x["book_odds"] = x["logged_price"]
    return {"n": len(rows), "hits": sum(bool(x["hit"]) for x in rows),
            "at_bet_at": _score(rows, "bet_at"), "at_fair": _score(rows, "fair"), "at_book": _score(rows, "book_odds")}
