"""6-point teasers, priced from the same simulated scores as everything else."""
import itertools

import numpy as np

from . import config as C


def _fmt(v):
    return "PK" if abs(v) < 0.25 else f"{v:+g}"


def _dec(a):
    a = float(a)
    return 1 + (a / 100 if a > 0 else 100 / -a)


def _american(p):
    if p <= 0 or p >= 1:
        return None
    return round(100 * (1 - p) / p) if p < 0.5 else round(-100 * p / (1 - p))


def breakeven(legs, price):
    return (1 / _dec(price)) ** (1 / legs)


def game_legs(g, d, t, pts=None):
    """Every teaser leg for one game. d: simulated home margins, t: simulated totals. Pushes count as losses."""
    pts = pts or C.TEASER_POINTS
    b = g.get("book") or {}
    sl, tl = b.get("spread"), b.get("total")
    out = []
    if sl is not None:
        for team, sign in ((g["home"], 1), (g["away"], -1)):
            h0 = sl if sign == 1 else -sl
            h1, tm = h0 + pts, sign * d
            out.append({"kind": "spread", "team": team, "side": team, "from": h0, "line": h1,
                        "label": f"{team} {_fmt(h1)}", "was": f"{team} {_fmt(h0)}",
                        "p": round(100 * float((tm + h1 > 0).mean()), 1), "push": round(100 * float((tm + h1 == 0).mean()), 1),
                        "p_before": round(100 * float((tm + h0 > 0).mean()), 1)})
    if tl is not None:
        for side, L in (("Over", tl - pts), ("Under", tl + pts)):
            win = (t > L) if side == "Over" else (t < L)
            out.append({"kind": "total", "side": side, "from": tl, "line": L, "label": f"{side} {L:g}", "was": f"{side} {tl:g}",
                        "p": round(100 * float(win.mean()), 1), "push": round(100 * float((t == L).mean()), 1),
                        "p_before": round(100 * float(((t > tl) if side == "Over" else (t < tl)).mean()), 1)})
    return out


def best_combos(games, size, price, top=3):
    """Best teasers of a given size: one leg per game, highest joint chance."""
    pool = []
    for g in games:
        for L in sorted(g.get("teaser_legs") or [], key=lambda L: -L["p"])[:2]:
            pool.append((g, L))
    pool.sort(key=lambda x: -x[1]["p"])
    pool = pool[:14]
    dec = _dec(price)
    best = []
    for combo in itertools.combinations(pool, size):
        if len({g["game_id"] for g, _ in combo}) < size:
            continue
        best.append((float(np.prod([L["p"] / 100 for _, L in combo])), combo))
    best.sort(key=lambda x: -x[0])
    return [{"size": size, "price": price, "p": round(100 * p, 1), "fair": _american(p), "ev": round(100 * (p * dec - 1), 1),
             "legs": [{"game_id": g["game_id"], "matchup": f"{g['away']} at {g['home']}", "kickoff": g.get("start"), **L} for g, L in combo]}
            for p, combo in best[:top]]


def board(games, history):
    legs = [{"game_id": g["game_id"], "matchup": f"{g['away']} at {g['home']}", "kickoff": g.get("start"), **L}
            for g in games for L in (g.get("teaser_legs") or [])]
    legs.sort(key=lambda L: -L["p"])
    prices = C.TEASER_PRICES
    return {"points": C.TEASER_POINTS, "prices": {str(k): v for k, v in prices.items()},
            "breakeven": {str(k): round(100 * breakeven(k, v), 1) for k, v in prices.items()},
            "legs": legs, "best": {str(k): best_combos(games, k, v) for k, v in prices.items()}, "history": history}


def leg_hit(L, g, res):
    hm, tot = res["h"] - res["a"], res["h"] + res["a"]
    if L["kind"] == "spread":
        return ((hm if L["team"] == g["home"] else -hm) + L["line"]) > 0
    return (tot - L["line"]) * (1 if L["side"] == "Over" else -1) > 0


def tracking(weeks, results):
    """Grade the legs and the best 2-team teaser the model posted each week. weeks: {week label: [games]}."""
    legs, combos = [], []
    price = C.TEASER_PRICES[2]
    for week, games in sorted(weeks.items()):
        graded = [g for g in games if results.get(str(g["game_id"])) and g.get("teaser_legs")]
        for g in graded:
            for L in g["teaser_legs"]:
                legs.append((L["p"] / 100, leg_hit(L, g, results[str(g["game_id"])])))
        if len(graded) >= 2:
            best = best_combos(graded, 2, price, top=1)
            if best:
                b = best[0]
                hits = [leg_hit(L, next(x for x in graded if x["game_id"] == L["game_id"]), results[str(L["game_id"])]) for L in b["legs"]]
                combos.append({"week": week, "legs": [L["label"] for L in b["legs"]], "p": b["p"], "hit": bool(all(hits))})
    if not legs:
        return None
    units = sum((_dec(price) - 1) if c["hit"] else -1 for c in combos)
    return {"legs_n": len(legs), "legs_model": round(100 * float(np.mean([x[0] for x in legs])), 1),
            "legs_actual": round(100 * float(np.mean([x[1] for x in legs])), 1),
            "best2": {"n": len(combos), "hits": sum(c["hit"] for c in combos), "units": round(units, 2),
                      "recent": sorted(combos, key=lambda c: c["week"], reverse=True)[:10]}}
