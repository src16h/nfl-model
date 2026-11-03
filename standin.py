"""
Bet price, shared by every model: Hard Rock only (Nov 3 2026).

From Oct 31 to Nov 3 2026 plays were judged at a DraftKings Predictions stand-in (Hard Rock blended with Kalshi plus
DK's per-contract fee). The owner bets on Hard Rock, so that blend is gone: Kalshi is no longer requested and every
play is judged at Hard Rock's own posted price (or the next US book in each model's ODDS_BOOKS when Hard Rock doesn't
post a market). Pinnacle stays the referee of the fair price everywhere (betrules.decide_sharp) and the model still
has to agree. The functions keep their old shapes so callers don't change.
"""

KALSHI = "kalshi"      # never requested any more; kept so older filters that skip it keep working
LABEL = "Hard Rock"


def implied(o):
    o = float(o)
    return 100 / (o + 100) if o > 0 else -o / (-o + 100)


def american(c):
    c = min(max(float(c), 0.005), 0.995)
    return round(-100 * c / (1 - c)) if c >= 0.5 else round(100 * (1 - c) / c)


def price(hr=None, ks=None):
    """(American odds, source) for one side: Hard Rock's price as posted. ks is ignored."""
    return (hr, "hardrock") if hr is not None else (None, None)


def apply(rec, k=None, groups=()):
    """Game-lines record unchanged (Hard Rock's prices). k is ignored."""
    if rec is not None:
        rec.setdefault("standin", {})
    return rec


def rows(hr_rows, k_rows=None):
    """Alt-line rows (altlines.py form) at Hard Rock's prices. k_rows is ignored."""
    return [{**b, "src": "hardrock", "hr_odds": b["odds"]} for b in hr_rows or [] if b.get("odds") is not None]


def max_price(p, edge=0.015):
    """Worst Hard Rock price (American) still worth it for a side the fair chance p (0-1) says wins, at `edge` return."""
    return american(p / (1 + edge))
