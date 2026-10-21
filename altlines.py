"""
Alt lines and team totals, shared by the NFL, NHL and soccer models.

Every one of these markets is a function of the final score, so one distribution of final scores
prices all of them:
  - the MODEL's distribution (its simulated games, or soccer's scoreline grid), and
  - a PINNACLE-IMPLIED one: the same simulated games re-weighted so they reproduce Pinnacle's no-vig
    main spread (or moneyline) and total. Re-weighting keeps the shape the sims already have (hockey's
    empty-net goals, football's 3s and 7s) and only moves the middle to where the sharpest book says.

A book's alt price is judged by the same rule as every posted play: worth 1.5% to 8% at Pinnacle's fair
chance, with the model agreeing on the side. When Pinnacle posts that exact alt line its own price is the
referee; otherwise the re-weighted sims convert its main lines to the alt line, and the bet must clear 1
extra point (ALT_CONVERTED_EXTRA), since the conversion is an estimate. Each run measures that estimate
against the alt lines Pinnacle did post (conv_check) so the extra point can be tuned.

Bets are dicts: market ("spread" | "total" | "team_total"), team ("home" | "away" | None), side
("home" | "away" | "over" | "under"), line (from the side's own point of view for spreads).
"""
import math

import numpy as np
from scipy.optimize import minimize

SHARP_MIN_EV = 1.5
SHARP_MAX_EV = 8.0
ALT_CONVERTED_EXTRA = 1.0      # extra % value a converted (not posted by Pinnacle) line needs
LEG_AGREE = 0.0                # parlay legs: model chance must be at least Pinnacle's (points)


def implied(o):
    o = float(o)
    return 100 / (o + 100) if o > 0 else -o / (-o + 100)


def payout(o):
    o = float(o)
    return o / 100 if o > 0 else 100 / -o


def nv(a, b):
    pa, pb = implied(a), implied(b)
    return pa / (pa + pb)


def american(p):
    p = min(max(p, 1e-4), 1 - 1e-4)
    return round(-100 * p / (1 - p)) if p >= 0.5 else round(100 * (1 - p) / p)


def fmt(o):
    if o is None:
        return None
    o = int(round(float(o)))
    return f"+{o}" if o > 0 else str(o)


# ---------------------------------------------------------------------
# distributions of final scores
# ---------------------------------------------------------------------
class Dist:
    """Final scores h, a (arrays) with weights w (None = equal)."""

    def __init__(self, h, a, w=None):
        self.h, self.a = np.asarray(h, float), np.asarray(a, float)
        self.w = None if w is None else np.asarray(w, float) / float(np.sum(w))

    @classmethod
    def from_grid(cls, G):
        """A soccer scoreline grid (G[i, j] = P(home i, away j))."""
        n = G.shape[0]
        i, j = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
        return cls(i.ravel(), j.ravel(), G.ravel())

    def x(self, bet):
        """Positive = the bet wins, 0 = refund, negative = loses (whole and half lines)."""
        m, L, s = bet["market"], float(bet.get("line") or 0.0), bet["side"]
        if m == "btts":
            both = (self.h > 0) & (self.a > 0)
            return np.where(both == (s == "yes"), 1.0, -1.0)
        if m == "spread":
            d = self.h - self.a if s == "home" else self.a - self.h
            return d + L
        if m == "total":
            t = self.h + self.a
            return t - L if s == "over" else L - t
        pts = self.h if bet["team"] == "home" else self.a
        return pts - L if s == "over" else L - pts

    def mean(self, v):
        return float(np.mean(v)) if self.w is None else float(np.sum(v * self.w))

    def p(self, bet):
        """Chance the bet wins with refunds left out (how a book's price is quoted). Quarter lines (soccer) split."""
        L = float(bet.get("line") or 0.0)
        if round(L * 4) % 2 == 1:                                   # quarter line: half on each neighbour
            wa, wb = self._wl({**bet, "line": L - 0.25}), self._wl({**bet, "line": L + 0.25})
            W, Lo = (wa[0] + wb[0]) / 2, (wa[1] + wb[1]) / 2
            return W / (W + Lo) if W + Lo > 0 else 0.5
        W, Lo = self._wl(bet)
        return W / (W + Lo) if W + Lo > 0 else 0.5

    def _wl(self, bet):
        x = self.x(bet)
        return self.mean(x > 1e-9), self.mean(x < -1e-9)


def tilt(model, targets):
    """Re-weight the model's simulated games so they match Pinnacle. targets: list of (bet, chance) with chance
    the no-vig chance (0-1). Returns (Dist, rms error in points). Weights are exp(u * margin + v * total), the
    smallest change that moves the middle while keeping the shape."""
    h, a = model.h, model.a
    d, t = h - a, h + a
    zd = (d - d.mean()) / max(d.std(), 1e-9)
    zt = (t - t.mean()) / max(t.std(), 1e-9)

    def dist(x):
        e = x[0] * zd + x[1] * zt
        w = np.exp(e - e.max())
        if model.w is not None:
            w = w * model.w
        return Dist(h, a, w)

    def loss(x):
        D = dist(x)
        return sum((D.p(b) - p) ** 2 for b, p in targets) + 1e-6 * (x[0] ** 2 + x[1] ** 2)
    if not targets:
        return model, None
    res = minimize(loss, np.zeros(2), method="Nelder-Mead", options={"xatol": 1e-4, "fatol": 1e-11, "maxiter": 300})
    D = dist(res.x)
    err = math.sqrt(sum((D.p(b) - p) ** 2 for b, p in targets) / len(targets))
    return D, err


# ---------------------------------------------------------------------
# ladders: model vs Pinnacle at every line, for the price check on the page
# ---------------------------------------------------------------------
def ladders(model, mkt, spec, lo=0.03, hi=0.97, nd=1):
    """spec: {"spread": (min, max, step), "total": (...), "team_total": (...)}, lines from the home side for spreads.
    Returns {"spread": [[line, model_home%, pin_home%], ...], "total": [[line, over%, pin_over%]],
    "team_home": [...], "team_away": [...]}; pin is None without a Pinnacle-implied distribution."""
    out = {}

    def rows(key, mk, team, side):
        lo_, hi_, st = spec[mk]
        rr = []
        for L in np.arange(lo_, hi_ + 1e-9, st):
            b = {"market": mk, "team": team, "side": side, "line": round(float(L), 2)}
            pm = model.p(b)
            if lo <= pm <= hi:
                pk = mkt.p(b) if mkt is not None else None
                rr.append([round(float(L), 2), round(100 * pm, nd), None if pk is None else round(100 * pk, nd)])
        out[key] = rr
    if "spread" in spec:
        rows("spread", "spread", "home", "home")
    if "total" in spec:
        rows("total", "total", None, "over")
    if "team_total" in spec:
        rows("team_home", "team_total", "home", "over")
        rows("team_away", "team_total", "away", "over")
    return out


# ---------------------------------------------------------------------
# book alt prices -> plays
# ---------------------------------------------------------------------
def _key(b):
    """Two sides of one line share a key: spreads by the home line, totals and team totals by line."""
    if b["market"] == "spread":
        hl = b["line"] if b["side"] == "home" else -b["line"]
        return ("spread", None, round(hl, 2))
    if b["market"] == "btts":
        return ("btts", None, 0.0)
    return (b["market"], b.get("team"), round(float(b["line"]), 2))


def pairs(rows):
    """{key: {side: odds}} for a list of priced bets."""
    out = {}
    for b in rows:
        out.setdefault(_key(b), {})[b["side"]] = b["odds"]
    return out


OTHER = {"home": "away", "away": "home", "over": "under", "under": "over", "yes": "no", "no": "yes"}


def evaluate(book_rows, pin_rows, model, mkt, min_ev=SHARP_MIN_EV, max_ev=SHARP_MAX_EV):
    """Every bet the bet book posted, judged against Pinnacle. Returns rows with chances in %."""
    bp, pp = pairs(book_rows), pairs(pin_rows or [])
    out = []
    for b in book_rows:
        if b.get("odds") is None:
            continue
        k = _key(b)
        other = bp.get(k, {}).get(OTHER[b["side"]])
        book = nv(b["odds"], other) if other is not None else implied(b["odds"])
        pin = pp.get(k, {})
        if b["side"] in pin and OTHER[b["side"]] in pin:
            sharp, exact = nv(pin[b["side"]], pin[OTHER[b["side"]]]), True
        elif mkt is not None:
            sharp, exact = mkt.p(b), False
        else:
            sharp, exact = None, False
        pm = model.p(b)
        ev = None if sharp is None else 100 * (sharp * (1 + payout(b["odds"])) - 1)
        need = min_ev + (0 if exact else ALT_CONVERTED_EXTRA)
        play = bool(ev is not None and need <= ev <= max_ev and pm >= book)
        out.append({**b, "odds": fmt(b["odds"]), "model": round(100 * pm, 1), "book_p": round(100 * book, 1),
                    "sharp": None if sharp is None else round(100 * sharp, 1), "exact": exact,
                    "ev": None if ev is None else round(ev, 1), "need": need, "play": play})
    return out


def best_plays(rows, per_game=1):
    """The best plays by value (one per game by default). Rows must carry game_id."""
    by = {}
    for r in sorted([r for r in rows if r["play"]], key=lambda r: -r["ev"]):
        if len(by.setdefault(r["game_id"], [])) < per_game:
            by[r["game_id"]].append(r)
    return [r for v in by.values() for r in v]


def conv_check(pin_rows, mkt):
    """Pinnacle-implied (converted) chance vs Pinnacle's own price on every alt line it posted: errors in points."""
    errs = []
    if mkt is None:
        return errs
    for k, sides in pairs(pin_rows or []).items():
        s = next((x for x in ("home", "over", "yes") if x in sides and OTHER[x] in sides), None)
        if s is None:
            continue
        mk, team, L = k
        b = {"market": mk, "team": team, "side": s, "line": L}
        errs.append(100 * (mkt.p(b) - nv(sides[s], sides[OTHER[s]])))
    return errs


def grade(b, hs, as_):
    """'W', 'L', 'P' (or half results on quarter lines) and units won per unit staked at b['odds']."""
    D = Dist([hs], [as_])
    L = float(b.get("line") or 0.0)
    halves = [L - 0.25, L + 0.25] if round(L * 4) % 2 == 1 else [L]
    pay = payout(b["odds"]) if b.get("odds") else None
    res, u = [], 0.0
    for x in halves:
        v = float(D.x({**b, "line": x})[0])
        res.append("W" if v > 1e-9 else "L" if v < -1e-9 else "P")
        if pay is not None:
            u += (pay if v > 1e-9 else -1 if v < -1e-9 else 0) / len(halves)
    r = "W" if all(x == "W" for x in res) else "L" if all(x == "L" for x in res) else "P" if all(x == "P" for x in res) else \
        ("HW" if "W" in res else "HL")
    return r, (u if pay is not None else None)


def label(b, home, away):
    """'BUF -6.5', 'Over 47.5', 'BUF team total Over 23.5'."""
    if b["market"] == "btts":
        return f"BTTS {b['side'].title()}"
    L = float(b["line"])
    if b["market"] == "spread":
        t = home if b["side"] == "home" else away
        return f"{t} {'+' if L > 0 else ''}{L:g}" if L != 0 else f"{t} (draw no bet)"
    if b["market"] == "total":
        return f"{b['side'].title()} {L:g}"
    t = home if b["team"] == "home" else away
    return f"{t} team total {b['side'].title()} {L:g}"


# ---------------------------------------------------------------------
# parlay legs from the simulated games
# ---------------------------------------------------------------------
def team_legs(model, mkt, home, away, spec, p_range=(0.70, 0.92)):
    """'Alt down' team legs for an alt-line parlay: the safer side of alt spreads, totals and team totals.
    Each leg's chance is Pinnacle-implied (sharper than the model on team markets); the model must agree.
    Returns candidates with hit arrays over the model's simulated games (same order as player sims)."""
    out = []
    if mkt is None:
        return out
    bets = []
    lo, hi, st = spec["spread"]
    for L in np.arange(lo, hi + 1e-9, st):
        for side in ("home", "away"):
            bets.append({"market": "spread", "team": side, "side": side, "line": round(float(L), 2)})
    lo, hi, st = spec["total"]
    for L in np.arange(lo, hi + 1e-9, st):
        for side in ("over", "under"):
            bets.append({"market": "total", "team": None, "side": side, "line": round(float(L), 2)})
    lo, hi, st = spec["team_total"]
    for L in np.arange(lo, hi + 1e-9, st):
        for team in ("home", "away"):
            for side in ("over", "under"):
                bets.append({"market": "team_total", "team": team, "side": side, "line": round(float(L), 2)})
    for b in bets:
        if float(b["line"]) % 1 == 0:
            continue                                            # whole lines refund; parlays drop refunded legs
        pk, pm = mkt.p(b), model.p(b)
        if not (p_range[0] <= pk <= p_range[1]) or 100 * (pm - pk) < LEG_AGREE:
            continue
        hit = model.x(b) > 0
        raw = model.mean(hit)
        if raw <= 0:
            continue
        out.append({**b, "kind": "team", "label": label(b, home, away), "p": pk, "p_raw": raw, "p_model": pm, "hit": hit,
                    "team_side": b.get("team"), "teamname": home if b.get("team") == "home" else away if b.get("team") == "away" else None})
    return out
