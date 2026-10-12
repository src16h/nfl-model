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
    """rows: (stat, book_over 0-1, went_over bool). Returns {stat: {"shift", "n", "book", "actual"}}.

    Shift is how far real results ran from the book on the log-odds scale, shrunk by
    sample size, so a hot week or two can only nudge the numbers."""
    by = {}
    for stat, b, went in rows:
        if b is None or went is None:
            continue
        by.setdefault(stat, []).append((float(b), bool(went)))
    out = {}
    for stat, xs in by.items():
        n = len(xs)
        book = sum(x[0] for x in xs) / n
        act = sum(x[1] for x in xs) / n
        shift = 0.0
        if n >= BIAS_MIN_N:
            shift = (logit(clip(act, 0.02, 0.98)) - logit(book)) * n / (n + BIAS_K)
            shift = max(-BIAS_CAP, min(BIAS_CAP, shift))
        out[stat] = {"shift": round(shift, 3), "n": n, "book": round(100 * book, 1), "actual": round(100 * act, 1)}
    return out


def _side(side, p, odds, kind, over_extra=True):
    ev = 100 * (p * (1 + payout(odds)) - 1)
    need = MIN_EV[kind] + (OVER_EXTRA_EV if (over_extra and side == "Over") else 0.0)
    return {"side": side, "p": p, "odds": odds, "ev": ev, "need": need}


def decide_prop(model_over, book_over, over_odds, under_odds, stat, bias=None, blocked=(), raw_cap=None):
    """Chances are 0-1 for the Over; book_over is the book's no-vig chance.

    Returns side, adjusted chance for that side, book chance for that side, edge (adjusted minus
    book, in %), raw edge (model minus book, in %), expected return in %, and whether it is a play."""
    w = MODEL_WEIGHT["prop"]
    p = book_over + w * (model_over - book_over)
    shift = (bias or {}).get(stat, {}).get("shift", 0.0)
    p = inv_logit(logit(p) + shift)
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
            "odds": best["odds"], "shift": shift, "play": bool(play)}


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
            "bias_k": BIAS_K, "bias_min_n": BIAS_MIN_N}
