"""
DraftKings Predictions stand-in price (Oct 31 2026), shared by every model.

DraftKings Predictions has no odds feed, so the price a play is judged at is a blend of two feeds that ride in the
same Odds API call at no extra credit cost:
  - Hard Rock's price, as posted. Its built-in cut (about 4.5% across both sides) is about the size of DK's fee;
  - Kalshi's price plus DK's per-contract fee. Kalshi is an exchange like DK Predictions and posts close to fair
    prices (often -104/+100); DK charges about 1 to 3 cents a contract on top (FEE_TIERS).
Each side's cost per $1 of payout is the average of the two (WEIGHT on Hard Rock), turned back into American odds.
The two are blended only at the same line; when only one posts that line, its price is used alone. Pinnacle stays
the referee of the fair price everywhere (betrules.decide_sharp), the model still has to agree, and every play also
shows the most to pay so it can be checked against the app.
"""

WEIGHT = 0.5                                   # Hard Rock's share of the blend (Kalshi + fee gets the rest)
FEE_TIERS = ((0.20, 0.01), (0.97, 0.02), (1.01, 0.03))   # DK per-contract fee by contract price (reviews, Oct 2026)
KALSHI = "kalshi"
LABEL = "DK stand-in"


def implied(o):
    o = float(o)
    return 100 / (o + 100) if o > 0 else -o / (-o + 100)


def american(c):
    c = min(max(float(c), 0.005), 0.995)
    return round(-100 * c / (1 - c)) if c >= 0.5 else round(100 * (1 - c) / c)


def fee(p):
    for top, f in FEE_TIERS:
        if p < top:
            return f
    return FEE_TIERS[-1][1]


def kalshi_cost(o):
    p = implied(o)
    return min(0.995, p + fee(p))


def price(hr=None, ks=None):
    """(American odds, source) for one side from Hard Rock's and Kalshi's prices at the same line."""
    costs = []
    if hr is not None:
        costs.append((WEIGHT, implied(hr)))
    if ks is not None:
        costs.append((1 - WEIGHT if hr is not None else 1.0, kalshi_cost(ks)))
    if not costs:
        return None, None
    w = sum(x[0] for x in costs)
    c = sum(x[0] * x[1] for x in costs) / w
    src = "blend" if hr is not None and ks is not None else ("hardrock" if hr is not None else "kalshi")
    return american(c), src


def _same(a, b):
    try:
        return a is not None and b is not None and abs(float(a) - float(b)) < 1e-6
    except (TypeError, ValueError):
        return False


def apply(rec, k, groups):
    """Blend a game-lines record in place. rec: the bet book's record (Hard Rock first), or None; k: Kalshi's record
    in the same shape (or None). groups: [(line_key or None, side_a_key, side_b_key, ...more side keys)].
    When rec has no price for a market, Kalshi's line is taken. Returns the record (new if rec was None)."""
    if not k:
        if rec is not None:
            rec.setdefault("standin", {})
        return rec
    rec = dict(rec) if rec is not None else {}
    how, raw = {}, {}
    for line_key, *sides in groups:
        have_hr = all(rec.get(s) is not None for s in sides) and (line_key is None or rec.get(line_key) is not None)
        have_k = all(k.get(s) is not None for s in sides) and (line_key is None or k.get(line_key) is not None)
        if have_hr and have_k and (line_key is None or _same(rec[line_key], k[line_key])):
            for s in sides:
                raw[s] = rec[s]
                rec[s], how[s] = price(rec[s], k[s])
        elif have_hr:
            for s in sides:
                how[s] = "hardrock"
        elif have_k:
            if line_key:
                rec[line_key] = k[line_key]
            for s in sides:
                rec[s], how[s] = price(None, k[s])
    rec["standin"] = how
    rec["hr_prices"] = raw
    rec["kalshi_prices"] = {s: k.get(s) for _, *ss in groups for s in ss if k.get(s) is not None}
    return rec


def rows(hr_rows, k_rows):
    """Alt-line rows (altlines.py form) blended the same way: one row per (market, team, side, line, period)."""
    key = lambda b: (b.get("market"), b.get("team"), b.get("side"), round(float(b.get("line") or 0), 2), b.get("period"))
    kmap = {key(b): b for b in (k_rows or []) if b.get("odds") is not None}
    out, seen = [], set()
    for b in hr_rows or []:
        if b.get("odds") is None:
            continue
        kb = kmap.get(key(b))
        o, src = price(b["odds"], kb["odds"] if kb else None)
        out.append({**b, "odds": o, "src": src, "hr_odds": b["odds"], "k_odds": kb["odds"] if kb else None})
        seen.add(key(b))
    for kk, kb in kmap.items():
        if kk not in seen:
            o, src = price(None, kb["odds"])
            out.append({**kb, "odds": o, "src": src, "hr_odds": None, "k_odds": kb["odds"]})
    return out


def max_price(p, edge=0.015):
    """Most to pay on DK for a side the fair chance p (0-1) says is worth it at `edge` return: (American, cents).
    cents is the contract price before DK's fee."""
    c = p / (1 + edge)
    cents = c - fee(c)
    return american(c), round(100 * cents)
