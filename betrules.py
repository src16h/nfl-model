"""
Shared betting rules for all three models (NFL, NHL, CFB).

Why this exists: through early October 2026 the plays lost money in all three
sports. Checking every graded pick against the book showed the same things:

  1. The book's price was a better guide than the model's. The model's leaned
     side won about as often as the book said it would, not as often as the
     model said. So the model's number is now blended with the book's
     (MODEL_WEIGHT) before anything is called a play.
  2. Prop Overs lost and Unders held up. Books shade Overs because the public
     bets them, so an Over needs a bigger cushion (OVER_EXTRA_EV).
  3. Some stats ran one way all season (fewer rushing yards and NHL points than
     the books expected). BIAS_* learns that from graded results, per stat, and
     fades as the sample stays small.
  4. A play has to show a real expected profit at the posted price, vig
     included (MIN_EV), not just beat the book's fair price.

  5. Calibration (Oct 19 2026): checked against graded props, the model's own
     share of the edge showed up about as claimed, but the final edge on NHL
     plays (after the bias nudge) claimed about +7 points over the book and
     delivered about +2. realization_table() measures, per sport and stat, how
     much of the final edge over the book has really shown up, and decide_prop
     scales the edge by that factor. It starts near 1 (no change), moves only as
     graded results pile up, and never makes an edge bigger.

Each model calls decide_prop / decide_game; nothing else about the
simulations changes.
"""
import math

MODEL_WEIGHT = {"prop": 0.5, "game": 0.5}   # share of the model in the blended chance (rest is the book)
MIN_EV = {"prop": 2.5, "game": 1.5}          # % expected return at the posted price, vig included
OVER_EXTRA_EV = 1.5                          # extra % an Over needs (books shade Overs)
BIAS_K = 300.0                               # graded props needed before a stat's bias counts half
BIAS_CAP = 0.5                               # largest shift on the log-odds scale (about 12% near 50/50)
BIAS_MIN_N = 40                              # fewer graded props than this: no shift
REAL_K = 40.0        # calibration: "no change" counts like this much claimed edge (sum of edges; about 1,000 NHL props)
REAL_K_STAT = 20.0   # each stat is pulled toward its sport's factor with this much claimed edge
REAL_FLOOR = 0.4     # never keep less than 40% of an edge
REAL_MIN_N = 100     # fewer graded props than this: no change


def clip(p, lo=0.005, hi=0.995):
    return min(max(float(p), lo), hi)


def logit(p):
    p = clip(p)
    return math.log(p / (1 - p))


def inv_logit(x):
    return 1 / (1 + math.exp(-x))


def payout(odds):
    o = float(odds)
    return o / 100 if o > 0 else 100 / -o


def implied(odds):
    o = float(odds)
    return 100 / (o + 100) if o > 0 else -o / (-o + 100)


def no_vig_from_one(odds, hold=0.045):
    """Book's fair chance when only one side's price is known (typical prop hold)."""
    return clip(implied(odds) / (1 + hold))


def bias_table(rows):
    """rows: (stat, book_over 0-1, went_over bool[, weight]). Returns {stat: {"shift", "n", "n_eff", "book", "actual"}}.

    Shift is how far real results ran from the book on the log-odds scale, shrunk by
    sample size, so a hot week or two can only nudge the numbers. An optional weight per row
    (recency; NHL since Oct 20 2026) makes older games count less. The shrink then uses the
    weighted count, so an old, fading sample also pulls the shift back toward zero."""
    by = {}
    for row in rows:
        stat, b, went = row[:3]
        wt = float(row[3]) if len(row) > 3 else 1.0
        if b is None or went is None:
            continue
        by.setdefault(stat, []).append((float(b), bool(went), wt))
    out = {}
    for stat, xs in by.items():
        n = len(xs)
        ws = sum(x[2] for x in xs) or 1e-9
        book = sum(x[0] * x[2] for x in xs) / ws
        act = sum(x[1] * x[2] for x in xs) / ws
        shift = 0.0
        if n >= BIAS_MIN_N:
            shift = (logit(clip(act, 0.02, 0.98)) - logit(book)) * ws / (ws + BIAS_K)
            shift = max(-BIAS_CAP, min(BIAS_CAP, shift))
        out[stat] = {"shift": round(shift, 3), "n": n, "n_eff": round(ws, 1), "book": round(100 * book, 1), "actual": round(100 * act, 1)}
    return out


def realization_table(rows):
    """rows: (stat, final_over 0-1, book_over 0-1, went_over bool), where final_over is the chance the model
    acted on BEFORE any calibration (so the factor never feeds on itself).

    On the side the model leaned, k = edge over the book that really showed up / edge the model claimed,
    pulled toward 1 (REAL_K, then each stat toward its sport with REAL_K_STAT), kept between REAL_FLOOR and 1."""
    by = {}
    for stat, f, b, went in rows:
        if f is None or b is None or went is None or f == b:
            continue
        by.setdefault(stat, []).append((float(f), float(b), bool(went)))

    def sums(xs):
        claimed = sum(abs(f - b) for f, b, y in xs)
        realized = sum(((y - b) if f > b else (b - y)) for f, b, y in xs)
        return claimed, realized

    allx = [x for xs in by.values() for x in xs]
    if not allx:
        return {}
    on = len(allx) >= REAL_MIN_N
    cl, rl = sums(allx)
    k_all = max(REAL_FLOOR, min(1.0, (rl + REAL_K) / (cl + REAL_K))) if on else 1.0
    out = {"_all": {"k": round(k_all, 3), "n": len(allx), "claimed": round(100 * cl / len(allx), 1),
                    "realized": round(100 * rl / len(allx), 1)}}
    for stat, xs in by.items():
        c, r_ = sums(xs)
        k = max(REAL_FLOOR, min(1.0, (r_ + k_all * REAL_K_STAT) / (c + REAL_K_STAT))) if on else 1.0
        out[stat] = {"k": round(k, 3), "n": len(xs), "claimed": round(100 * c / len(xs), 1), "realized": round(100 * r_ / len(xs), 1)}
        for side in ("Over", "Under"):           # per side, pulled toward the stat's factor (used when decide_prop gets side_k=True)
            ys = [x for x in xs if (x[0] > x[1]) == (side == "Over")]
            if not ys:
                continue
            c2, r2 = sums(ys)
            k2 = max(REAL_FLOOR, min(1.0, (r2 + k * REAL_K_STAT) / (c2 + REAL_K_STAT))) if on else 1.0
            out[f"{stat}|{side}"] = {"k": round(k2, 3), "n": len(ys), "claimed": round(100 * c2 / len(ys), 1),
                                     "realized": round(100 * r2 / len(ys), 1)}
    return out


def real_k(real, stat, side=None):
    """Calibration factor for a stat, or one side of it when side is given (1.0 = keep the whole edge)."""
    if not real:
        return 1.0
    return ((real.get(f"{stat}|{side}") if side else None) or real.get(stat) or real.get("_all") or {}).get("k", 1.0)


def _side(side, p, odds, kind, over_extra=True):
    ev = 100 * (p * (1 + payout(odds)) - 1)
    need = MIN_EV[kind] + (OVER_EXTRA_EV if (over_extra and side == "Over") else 0.0)
    return {"side": side, "p": p, "odds": odds, "ev": ev, "need": need}


def decide_prop(model_over, book_over, over_odds, under_odds, stat, bias=None, blocked=(), raw_cap=None, weight=None, real=None,
                side_k=False):
    """Chances are 0-1 for the Over; book_over is the book's no-vig chance.

    Returns side, adjusted chance for that side, book chance for that side, edge (adjusted minus
    book, in %), raw edge (model minus book, in %), expected return in %, whether it is a play,
    'pre' (the Over chance before calibration, which history keeps so calibration never feeds on
    itself) and 'k' (the calibration factor used). side_k=True scales the edge by the factor for the side
    the model leans (e.g. "points|Under"), not the stat as a whole (NHL, Oct 20 2026)."""
    w = MODEL_WEIGHT["prop"] if weight is None else weight
    p = book_over + w * (model_over - book_over)
    shift = (bias or {}).get(stat, {}).get("shift", 0.0)
    p = inv_logit(logit(p) + shift)
    pre = p
    k = real_k(real, stat, ("Over" if p > book_over else "Under") if side_k else None)
    p = clip(book_over + k * (p - book_over))
    opts = []
    if over_odds is not None:
        opts.append(_side("Over", p, over_odds, "prop"))
    if under_odds is not None:
        opts.append(_side("Under", 1 - p, under_odds, "prop"))
    if not opts:
        return None
    best = max(opts, key=lambda o: o["ev"] - o["need"])
    over = best["side"] == "Over"
    bs = book_over if over else 1 - book_over
    raw = 100 * ((model_over - book_over) if over else (book_over - model_over))
    play = (best["ev"] >= best["need"] and (stat, best["side"]) not in blocked and stat not in blocked
            and (raw_cap is None or raw <= raw_cap))
    return {"side": best["side"], "p": round(100 * best["p"], 1), "book": round(100 * bs, 1),
            "edge": round(100 * (best["p"] - bs), 1), "raw_edge": round(raw, 1), "ev": round(best["ev"], 1),
            "odds": best["odds"], "shift": shift, "play": bool(play), "pre": round(100 * pre, 1), "k": k}


def adjust_game(model_p, book_p):
    """Blended chance for one side of a game line (0-1)."""
    return clip(book_p + MODEL_WEIGHT["game"] * (model_p - book_p))


def game_ev(p, odds, side=None):
    """Expected return (%) and the bar it must clear."""
    s = _side(side or "", p, odds, "game", over_extra=False)
    return s["ev"], s["need"]


def summary():
    """Rules as shown on the Record tab."""
    return {"model_weight": MODEL_WEIGHT, "min_ev": MIN_EV, "over_extra_ev": OVER_EXTRA_EV,
            "bias_k": BIAS_K, "bias_min_n": BIAS_MIN_N, "real_floor": REAL_FLOOR, "real_min_n": REAL_MIN_N}


def final_over_from(bk):
    """Over chance a stored history entry acted on before calibration: 'pre' when saved, otherwise
    rebuilt from the expected return at the posted price (entries saved before calibration existed)."""
    if bk.get("pre") is not None:
        return bk["pre"] / 100
    if bk.get("ev") is None or bk.get("odds") is None or bk.get("side") is None:
        return None
    ps = (1 + bk["ev"] / 100) / (1 + payout(bk["odds"]))
    return ps if bk["side"] == "Over" else 1 - ps
