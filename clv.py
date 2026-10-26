"""
Closing line value (CLV) for game-line plays, shared by the NHL and CFB models.

When a pick first becomes a play, its price and line are saved ("play_at").
After the game locks, that price is compared with the closing line on the same
side:

  clv      = closing win chance implied by the price (vig in) minus the chance
             implied by the price you got, in percentage points. A line that
             never moved scores 0; positive means you beat the close.
  ev_close = expected return of your bet if the close's no-vig chance is the
             truth (this one includes the vig, so a flat line scores about -2%).

Beating the close regularly is the best early sign an edge is real, long before
wins and losses settle down. Plays saved before play_at existed are measured
from the first line the model saw for that game.
"""
import betrules as BR

# win chance per point (CFB) or per goal (NHL total) when the line itself moved; NHL is about how often
# a game lands on one exact total
PER_POINT = {"cfb_spread": 0.03, "cfb_total": 0.025, "nhl_total": 0.12}


def price(o):
    if o is None:
        return None
    try:
        return float(str(o).replace("+", ""))
    except ValueError:
        return None


def _pair(book, a_key, b_key, use_a):
    a, b = price(book.get(a_key)), price(book.get(b_key))
    if a is None or b is None:
        return None
    pa, pb = BR.implied(a), BR.implied(b)
    mine = pa if use_a else pb
    return {"novig": mine / (pa + pb), "vig": mine}


def _shift(c, d):
    return None if c is None else {"novig": BR.clip(c["novig"] + d), "vig": BR.clip(c["vig"] + d)}


def close(sport, kind, pk, g, book, line):
    """Closing chances for the play's side at the play's own line. line = the line the bet was made at."""
    if not book:
        return None
    home = pk.get("side") == g["home"]
    over = pk.get("side") == "Over"
    if kind == "ml":
        return _pair(book, "ml_home", "ml_away", home)
    if kind == "pl":
        return _pair(book, "pl_home_odds", "pl_away_odds", home)
    if kind == "total":
        c = _pair(book, "over_odds", "under_odds", over)
        if c is None or book.get("total") is None or line is None:
            return None
        moved = (book["total"] - line) * (1 if over else -1)          # close above our Over line: our line is the easier one
        return _shift(c, moved * PER_POINT[f"{sport}_total"])
    if kind == "spread":
        c = _pair(book, "spread_home_odds", "spread_away_odds", home)
        if c is None or book.get("spread") is None or line is None:
            return None
        close_line = book["spread"] if home else -book["spread"]       # the side's handicap at the close
        return _shift(c, (line - close_line) * PER_POINT["cfb_spread"])
    return None


def measure(snap_odds, c):
    """(clv in points, ev_close in %) for a bet at snap_odds against closing chances c."""
    o = price(snap_odds)
    if o is None or c is None:
        return None, None
    return 100 * (c["vig"] - BR.implied(o)), 100 * (c["novig"] * (1 + BR.payout(o)) - 1)


def snapshot(picks, prev, ts):
    """Keep the first price and line at which each pick became a play (same side). prev is the saved dict."""
    out = dict(prev or {})
    for kind, pk in (picks or {}).items():
        if not pk or not pk.get("play"):
            continue
        old = out.get(kind)
        if old and old.get("side") == pk.get("side"):
            continue
        out[kind] = {"side": pk.get("side"), "odds": pk.get("odds"), "line": pk.get("line"), "ts": ts}
    return out


def first_seen(kind, pk, g, first_book):
    """Fallback for plays saved before play_at existed: the play's side priced at the first line we saw."""
    fb = first_book or {}
    home = pk.get("side") == g["home"]
    if kind == "ml":
        return {"odds": fb.get("ml_home") if home else fb.get("ml_away"), "line": None}
    if kind == "pl":
        return {"odds": fb.get("pl_home_odds") if home else fb.get("pl_away_odds"), "line": pk.get("line")}
    if kind == "spread":
        if fb.get("spread") is None:
            return None
        return {"odds": fb.get("spread_home_odds") if home else fb.get("spread_away_odds"),
                "line": fb["spread"] if home else -fb["spread"]}
    if kind == "total":
        over = pk.get("side") == "Over"
        return {"odds": fb.get("over_odds") if over else fb.get("under_odds"), "line": fb.get("total")}
    return None


def play_clv(sport, kind, pk, g, first_book):
    """(clv, ev_close, exact) for one graded play. exact = measured from when it became a play."""
    snap = (g.get("play_at") or {}).get(kind)
    exact = bool(snap and snap.get("side") == pk.get("side"))
    if not exact:
        snap = first_seen(kind, pk, g, first_book)
    if not snap or snap.get("odds") is None:
        return None, None, exact
    line = snap.get("line") if snap.get("line") is not None else pk.get("line")
    c, e = measure(snap["odds"], close(sport, kind, pk, g, g.get("book"), line))
    return c, e, exact


def summary(rows):
    """rows: dicts with 'clv', 'ev' and 'kind'. Averages and how often the close was beaten, overall and by kind."""
    def one(xs):
        xs = [x for x in xs if x.get("clv") is not None]
        if not xs:
            return {"n": 0}
        c = [x["clv"] for x in xs]
        beat, worse = sum(v > 0.05 for v in c), sum(v < -0.05 for v in c)
        evs = [x["ev"] for x in xs if x.get("ev") is not None]
        return {"n": len(c), "avg": round(sum(c) / len(c), 2), "beat": beat, "worse": worse, "same": len(c) - beat - worse,
                "beat_pct": round(100 * beat / max(beat + worse, 1)),
                "ev_close": round(sum(evs) / len(evs), 2) if evs else None}
    ex = [x for x in rows if x.get("exact")]
    fs = [x for x in rows if not x.get("exact")]
    out = {"plays": one(ex),            # measured from when each pick became a play (the real CLV)
           "first_line": one(fs)}       # older plays: the play's side at the first posted line (bet early vs wait)
    for k in sorted({x["kind"] for x in rows}):
        out[k] = {"plays": one([x for x in ex if x["kind"] == k]), "first_line": one([x for x in fs if x["kind"] == k])}
    return out


def moving(sport, kind, pk, g, snap):
    """For a live play: how the price has moved since it became a play, in win-chance points
    (positive = the market moved toward the play, so the price is getting worse)."""
    if not snap or snap.get("side") != pk.get("side") or snap.get("odds") is None or pk.get("odds") is None:
        return None
    now = price(pk.get("odds"))
    then = price(snap.get("odds"))
    if now is None or then is None:
        return None
    d = BR.implied(now) - BR.implied(then)
    if kind in ("total", "spread") and snap.get("line") is not None and pk.get("line") is not None:
        per = PER_POINT["cfb_spread"] if kind == "spread" else PER_POINT[f"{sport}_total"]
        if kind == "spread":
            d += (snap["line"] - pk["line"]) * per                       # handicap shrank since: worse price now
        else:
            d += (pk["line"] - snap["line"]) * per * (1 if pk.get("side") == "Over" else -1)   # Over line went up since: worse price now
    return round(100 * d, 1)


# ---------------------------------------------------------------------------------------------------
# Player props (Oct 26 2026): a prop play is locked at the line and price it was first flagged at
# ("flag"), and every later pre-game run saves the book's latest line for that player ("close"; the
# runners re-pull props once near kickoff for games with a locked play). Both carry book_over, the
# book's no-vig chance of the Over in %.
# ---------------------------------------------------------------------------------------------------
def close_snap(book, prev, ts):
    """Latest pre-game line for a prop, or the previous one when the book has none this run."""
    if book and book.get("line") is not None and book.get("book_over") is not None:
        return {"line": book["line"], "book_over": book["book_over"], "at": ts}
    return prev


def prop_clv(flag, close):
    """(clv in points of no-vig chance, ev at close %, line move) for a locked prop play.
    Same line: compares the no-vig chance of our side at close vs when flagged. Line moved: clv and ev
    are None and move is +1 (toward us: Over line went up / Under line went down) or -1."""
    if not flag or not close or flag.get("book_over") is None or close.get("book_over") is None:
        return None, None, None
    try:
        l0, l1 = float(flag["line"]), float(close["line"])
    except (TypeError, ValueError, KeyError):
        return None, None, None
    over = flag.get("side") == "Over"
    if abs(l1 - l0) > 1e-9:
        return None, None, (1 if (l1 > l0) == over else -1)
    p0 = flag["book_over"] / 100 if over else 1 - flag["book_over"] / 100
    p1 = close["book_over"] / 100 if over else 1 - close["book_over"] / 100
    o = price(flag.get("odds"))
    ev = None if o is None else 100 * (p1 * (1 + BR.payout(o)) - 1)
    return 100 * (p1 - p0), ev, 0


def prop_summary(rows):
    """rows: dicts with clv, ev, move. What the closing line says about the prop plays."""
    same = [x for x in rows if x.get("move") == 0]
    moved = [x for x in rows if x.get("move") in (1, -1)]
    ev = [x["ev"] for x in same if x.get("ev") is not None]
    return {"n": len(same) + len(moved), "same_line": len(same),
            "avg": round(sum(x["clv"] for x in same) / len(same), 2) if same else None,
            "beat": sum(1 for x in same if x["clv"] > 0.05) + sum(1 for x in moved if x["move"] > 0),
            "worse": sum(1 for x in same if x["clv"] < -0.05) + sum(1 for x in moved if x["move"] < 0),
            "ev_close": round(sum(ev) / len(ev), 2) if ev else None}
