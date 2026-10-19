"""
6-point teasers, priced by the model.

Each side and total is moved 6 points in the bettor's favor. The chance each
moved line wins comes from real NFL final scores: games Vegas priced near the
model's number, shifted so their center matches the model (same method as the
key-number cover chances). That keeps the pile-ups on 3 and 7 that make
teasers work or fail.

"Wong" legs are the classic teaser spots: a favorite of 7.5 to 8.5 moved to
1.5 to 2.5, or an underdog of 1.5 to 2.5 moved to 7.5 to 8.5. Those cross
both 3 and 7, the two most common NFL margins.

Pushes are counted as losses in every chance here, so the numbers lean safe.
"""
import itertools
import math

import numpy as np

from . import config as C


def _fmt(v):
    return "PK" if abs(v) < 0.25 else f"{v:+g}"


def crosses_3_and_7(h0, pts):
    """h0 is the team's handicap before teasing (e.g. -7.5). True when the
    margins the tease adds include both 3 and 7 (for that team or against)."""
    lo, hi = -h0 - pts, -h0                      # team margins newly covered: lo < k <= hi
    added = set(range(math.floor(lo) + 1, math.floor(hi) + 1))
    return {3, 7} <= added or {-3, -7} <= added


def _odds_to_dec(a):
    a = float(a)
    return 1 + (a / 100 if a > 0 else 100 / -a)


def _american(p):
    if p <= 0 or p >= 1:
        return None
    return round(100 * (1 - p) / p) if p < 0.5 else round(-100 * p / (1 - p))


def breakeven(legs, price):
    """Per-leg chance needed to break even at a teaser price."""
    return (1 / _odds_to_dec(price)) ** (1 / legs)


def game_legs(game, keynum, pts=None):
    """Every teaser leg for one game: both sides and both totals."""
    pts = pts or C.TEASER_POINTS
    sl, tl = game.get("market_spread"), game.get("market_total")
    if keynum is None or not keynum.ok or sl is None or game.get("margin") is None:
        return []
    m = keynum._near(keynum.L, keynum.M, float(game["margin"]))          # home margins
    t = keynum._near(keynum.TL, keynum.T, float(game["total"])) if tl is not None else None
    if m is None:
        return []
    out = []
    for team, sign in ((game["home"], 1), (game["away"], -1)):
        h0 = -sl if sign == 1 else sl                                   # team's handicap
        h1 = h0 + pts
        tm = sign * m
        out.append({"kind": "spread", "team": team, "side": team, "from": h0, "line": h1,
                    "label": f"{team} {_fmt(h1)}", "was": f"{team} {_fmt(h0)}",
                    "p": round(100 * float((tm + h1 > 0).mean()), 1),
                    "push": round(100 * float((tm + h1 == 0).mean()), 1),
                    "p_before": round(100 * float((tm + h0 > 0).mean()), 1),
                    "wong": crosses_3_and_7(h0, pts)})
    if t is not None:
        for side, L in (("Over", tl - pts), ("Under", tl + pts)):
            win = (t > L) if side == "Over" else (t < L)
            out.append({"kind": "total", "side": side, "from": tl, "line": L,
                        "label": f"{side} {L:g}", "was": f"{side} {tl:g}",
                        "p": round(100 * float(win.mean()), 1),
                        "push": round(100 * float((t == L).mean()), 1),
                        "p_before": round(100 * float(((t > tl) if side == "Over" else (t < tl)).mean()), 1),
                        "wong": False})
    return out


def best_combos(games, size, price, top=3):
    """Best teasers of a given size: one leg per game, highest joint chance."""
    pool = []
    for g in games:
        legs = sorted(g.get("teaser_legs") or [], key=lambda L: -L["p"])[:2]
        for L in legs:
            pool.append((g, L))
    pool.sort(key=lambda x: -x[1]["p"])
    pool = pool[:14]
    dec = _odds_to_dec(price)
    best = []
    for combo in itertools.combinations(pool, size):
        if len({g["game_id"] for g, _ in combo}) < size:
            continue
        p = float(np.prod([L["p"] / 100 for _, L in combo]))
        best.append((p, combo))
    best.sort(key=lambda x: -x[0])
    out = []
    for p, combo in best[:top]:
        out.append({"size": size, "price": price, "p": round(100 * p, 1), "fair": _american(p),
                    "ev": round(100 * (p * dec - 1), 1),
                    "legs": [{"game_id": g["game_id"], "matchup": f"{g['away']} at {g['home']}",
                              "kickoff": g.get("kickoff"), **L} for g, L in combo]})
    return out


def history(schedules, since=None, pts=None):
    """How classic Wong legs did at the closing line, plus every 6-point side. Also the underdog half
    of the Wong legs (the only half that still wins), overall and in games with a low total."""
    pts = pts or C.TEASER_POINTS
    since = since or C.TEASER_HIST_SINCE
    s = schedules[schedules["home_score"].notna() & (schedules["season"] >= since)].dropna(subset=["spread_line"])
    has_total = "total_line" in s.columns
    rows = []
    for r in s.itertuples():
        m = r.home_score - r.away_score
        tot = float(r.total_line) if has_total and r.total_line == r.total_line else None
        for h0, tm in ((-r.spread_line, m), (r.spread_line, -m)):
            rows.append((int(r.season), crosses_3_and_7(h0, pts), tm + h0 + pts > 0, h0 > 0, tot))
    def rec(sel):
        n = len(sel)
        w = sum(x[2] for x in sel)
        return {"n": n, "w": int(w), "pct": round(100 * w / n, 1) if n else None}
    wong = [x for x in rows if x[1]]
    dog = [x for x in wong if x[3]]
    low = [x for x in dog if x[4] is not None and x[4] <= C.WONG_TOTAL_MAX]
    seasons = sorted({x[0] for x in rows})
    recent = (seasons[-1] - 3) if seasons else 0
    return {"since": since, "wong": rec(wong), "all": rec(rows),
            "wong_by_season": {str(y): rec([x for x in wong if x[0] == y]) for y in seasons},
            "wong_dog": rec(dog), "wong_dog_low": rec(low), "wong_fav": rec([x for x in wong if not x[3]]),
            "recent_since": recent,
            "wong_dog_recent": rec([x for x in dog if x[0] >= recent]),
            "wong_dog_low_recent": rec([x for x in low if x[0] >= recent]),
            "wong_dog_high_recent": rec([x for x in dog if x[0] >= recent and not (x[4] is not None and x[4] <= C.WONG_TOTAL_MAX)])}


def wong_rates(hist=None):
    """Historical hit rates for underdog Wong legs since the last few seasons: low-total games and the rest."""
    h = hist or {}
    lo, hi = (h.get("wong_dog_low_recent") or {}).get("pct"), (h.get("wong_dog_high_recent") or {}).get("pct")
    return {"low": lo if lo is not None else C.WONG_HIST_FALLBACK["low"], "other": hi if hi is not None else C.WONG_HIST_FALLBACK["other"]}


def wong_dog(L):
    """An underdog Wong leg: +1.5 to +3 teased past 7 (crosses both 3 and 7)."""
    return L.get("kind") == "spread" and bool(L.get("wong")) and (L.get("from") or 0) > 0


def _game_total(g):
    if g.get("market_total") is not None:
        return float(g["market_total"])
    for L in g.get("teaser_legs") or []:
        if L.get("kind") == "total" and L.get("from") is not None:
            return float(L["from"])
    return None


def wong_plays(games, price=None, rates=None):
    """2-team Wong teaser plays: underdog Wong legs only, the model's chance at least WONG_MIN_P, low-total
    games first, then the model's chance. Paired in that order, each leg used once, one leg per game.
    Each leg's chance blends its historical rate (rates) with the model's; a ticket is a play only if it
    clears WONG_MIN_EV at the price."""
    price = price or C.TEASER_PRICES[2]
    rates = rates or wong_rates()
    w = C.WONG_HIST_WEIGHT
    legs = []
    for g in games:
        tot = _game_total(g)
        for L in g.get("teaser_legs") or []:
            if wong_dog(L) and L["p"] >= C.WONG_MIN_P:
                low = tot is not None and tot <= C.WONG_TOTAL_MAX
                hist = rates["low" if low else "other"]
                legs.append({"game_id": g["game_id"], "matchup": f"{g['away']} at {g['home']}", "kickoff": g.get("kickoff"),
                             "total": tot, "low_total": low, **L, "hist": hist, "p_use": round(w * hist + (1 - w) * L["p"], 1)})
    legs.sort(key=lambda L: (not L["low_total"], -L["p_use"]))
    tickets, used = [], set()
    for i, a in enumerate(legs):
        if a["game_id"] in used:
            continue
        b = next((x for x in legs[i + 1:] if x["game_id"] not in used and x["game_id"] != a["game_id"]), None)
        if b is None:
            break
        used |= {a["game_id"], b["game_id"]}
        p = a["p_use"] / 100 * b["p_use"] / 100
        pm = a["p"] / 100 * b["p"] / 100
        ev = 100 * (p * _odds_to_dec(price) - 1)
        tickets.append({"size": 2, "price": price, "p": round(100 * p, 1), "p_model": round(100 * pm, 1), "fair": _american(p),
                        "ev": round(ev, 1), "play": ev >= C.WONG_MIN_EV, "legs": [a, b]})
        if len(tickets) >= C.WONG_MAX_TICKETS:
            break
    return tickets


def board(games, schedules):
    live = [g for g in games if g.get("state", "upcoming") == "upcoming" and g.get("teaser_legs")]
    legs = []
    for g in live:
        for L in g["teaser_legs"]:
            legs.append({"game_id": g["game_id"], "matchup": f"{g['away']} at {g['home']}",
                         "kickoff": g.get("kickoff"), **L})
    legs.sort(key=lambda L: -L["p"])
    prices = C.TEASER_PRICES
    hist = history(schedules)
    return {"points": C.TEASER_POINTS, "prices": {str(k): v for k, v in prices.items()},
            "breakeven": {str(k): round(100 * breakeven(k, v), 1) for k, v in prices.items()},
            "legs": legs,
            "best": {str(k): best_combos(live, k, v) for k, v in prices.items()},
            "wong_plays": wong_plays(live, rates=wong_rates(hist)),
            "wong_rules": {"total_max": C.WONG_TOTAL_MAX, "min_p": C.WONG_MIN_P, "max_tickets": C.WONG_MAX_TICKETS,
                           "min_ev": C.WONG_MIN_EV, "hist_weight": C.WONG_HIST_WEIGHT, "rates": wong_rates(hist)},
            "history": hist}


def _leg_hit(L, g, r):
    hm, tot = r["h"] - r["a"], r["h"] + r["a"]
    if L["kind"] == "spread":
        v = (hm if L["team"] == g["home"] else -hm) + L["line"]
    else:
        v = (tot - L["line"]) * (1 if L["side"] == "Over" else -1)
    return v > 0                                                     # a push counts as a loss (safe side)


def tracking(hist_games_by_week, results_games):
    """Grade the legs, the best 2-team teaser the model posted each week, and the Wong plays."""
    legs, combos, wongs = [], [], []
    price = C.TEASER_PRICES[2]
    for week, games in sorted(hist_games_by_week.items()):
        graded = []
        for g in games:
            r = results_games.get(g["game_id"])
            if not r or not g.get("teaser_legs"):
                continue
            hm, tot = r["h"] - r["a"], r["h"] + r["a"]
            for L in g["teaser_legs"]:
                if L["kind"] == "spread":
                    v = (hm if L["team"] == g["home"] else -hm) + L["line"]
                else:
                    v = (tot - L["line"]) * (1 if L["side"] == "Over" else -1)
                legs.append((week, L["p"] / 100, v > 0, L.get("wong", False)))
            graded.append(g)
        if len(graded) >= 2:
            best = best_combos([dict(g, state="upcoming") for g in graded], 2, price, top=1)
            if best:
                b = best[0]
                hits = []
                for L in b["legs"]:
                    r = results_games[L["game_id"]]
                    g = next(x for x in graded if x["game_id"] == L["game_id"])
                    hm, tot = r["h"] - r["a"], r["h"] + r["a"]
                    v = ((hm if L["team"] == g["home"] else -hm) + L["line"]) if L["kind"] == "spread" else \
                        (tot - L["line"]) * (1 if L["side"] == "Over" else -1)
                    hits.append(v > 0)
                combos.append({"week": int(week), "legs": [L["label"] for L in b["legs"]], "p": b["p"], "hit": all(hits)})
        for t in [t for t in wong_plays(graded, price) if t["play"]]:
            hits = [_leg_hit(L, next(x for x in graded if x["game_id"] == L["game_id"]), results_games[L["game_id"]]) for L in t["legs"]]
            wongs.append({"week": int(week), "legs": [L["label"] for L in t["legs"]], "p": t["p"], "hit": all(hits),
                          "legs_hit": sum(hits), "low": [bool(L["low_total"]) for L in t["legs"]]})
    if not legs:
        return None
    w = [x for x in legs if x[3]]
    units = sum((_odds_to_dec(price) - 1) if c["hit"] else -1 for c in combos)
    return {"legs_n": len(legs), "legs_model": round(100 * np.mean([x[1] for x in legs]), 1),
            "legs_actual": round(100 * np.mean([x[2] for x in legs]), 1),
            "wong_n": len(w), "wong_actual": round(100 * np.mean([x[2] for x in w]), 1) if w else None,
            "best2": {"n": len(combos), "hits": sum(c["hit"] for c in combos), "units": round(units, 2),
                      "recent": sorted(combos, key=lambda c: -c["week"])[:10]},
            "wong_plays": {"n": len(wongs), "hits": sum(c["hit"] for c in wongs),
                           "units": round(sum((_odds_to_dec(price) - 1) if c["hit"] else -1 for c in wongs), 2),
                           "legs_n": 2 * len(wongs), "legs_hit": sum(c["legs_hit"] for c in wongs),
                           "recent": sorted(wongs, key=lambda c: -c["week"])[:12]}}
