"""
What the parlay tickets would have returned in units (Nov 11 2026).

Until now a ticket record only compared the model's chance with how often tickets hit ("said vs hit"). A ticket can
hit exactly as often as the model says and still lose money, because the book pays less than the fair price. So each
graded ticket is also scored in units, 1 unit a ticket:

  at_bet_at : at the ticket's "bet at" price, the shortest odds the page says to accept (fair price plus a 7% cushion).
              This is the most you could have made by following the page: bet only when Hard Rock offered that price
              or better, at exactly that price. If tickets lose even here, they lose at any price you would take.
  at_fair   : at the model's own fair price. Close to 0 when the chances are right; below 0 means they ran too high.
  at_book   : at the book's real price, when it was saved (cross-game tickets with every leg priced at Hard Rock).

Hard Rock's real same-game parlay price is not in the odds feed (it is built when you make the slip), so it is not
known here. A ticket that wins at bet_at still has to be offered at that price.
"""
import math


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


def summary(rows):
    """rows: graded tickets with "hit" (True/False) and any of "bet_at", "fair", "book_odds"."""
    rows = [x for x in rows or [] if x.get("hit") is not None]
    return {"n": len(rows), "hits": sum(bool(x["hit"]) for x in rows),
            "at_bet_at": _score(rows, "bet_at"), "at_fair": _score(rows, "fair"), "at_book": _score(rows, "book_odds")}
