"""
Model picks: one explicit bet per market for every game.

Spread     "KC +3 (2.0)"        gap in points between the model and Vegas
Total      "Over 47.5 (1.8)"    gap in points
Moneyline  "KC +150 (3.1%)"     model win chance minus the book's fair win chance

Every game always gets a side (no passing). The gap tells you how strongly
the model disagrees with the book; the Play rules in config.py still decide
which picks make the "This week's plays" list.
"""
import math


def _ok(v):
    return v is not None and isinstance(v, (int, float)) and math.isfinite(v)


def _fmt_line(v):
    return "PK" if abs(v) < 0.25 else f"{v:+g}"


def _fmt_odds(p):
    p = int(round(float(p)))
    return f"+{p}" if p > 0 else str(p)


def implied(american):
    """American odds -> win chance with the book's cut still in."""
    a = float(american)
    return 100 / (a + 100) if a > 0 else -a / (-a + 100)


def spread_pick(home, away, edge, market_spread, cover_home=None):
    """edge = model home margin - Vegas home margin. Positive means the model likes the home side."""
    if not (_ok(edge) and _ok(market_spread)):
        return None
    if abs(edge) < 0.05 and _ok(cover_home):          # dead even: break the tie with cover chance
        take_home = cover_home >= 50
    else:
        take_home = edge >= 0
    team = home if take_home else away
    line = -market_spread if take_home else market_spread
    return {"pick": f"{team} {_fmt_line(line)}", "side": team, "line": line,
            "edge": round(abs(edge), 1), "edge_text": f"{abs(edge):.1f}"}


def total_pick(edge, market_total, over_prob=None):
    if not (_ok(edge) and _ok(market_total)):
        return None
    if abs(edge) < 0.05 and _ok(over_prob):
        side = "Over" if over_prob >= 50 else "Under"
    else:
        side = "Over" if edge >= 0 else "Under"
    return {"pick": f"{side} {market_total:g}", "side": side, "line": market_total,
            "edge": round(abs(edge), 1), "edge_text": f"{abs(edge):.1f}"}


def _curve(margin, sigma):
    """Win chance from a home margin (same curve the model uses for win chance)."""
    return 0.5 * (1 + math.erf(margin / (sigma * math.sqrt(2))))


def moneyline_pick(home, away, win_prob_home, ml_home=None, ml_away=None,
                   edge_spread=None, market_spread=None, sigma=11.4, spread_side=None):
    """Model-only moneyline. The edge is the model's own disagreement with Vegas:
    win chance from the model's margin minus win chance the Vegas spread implies.
    Always the same team as the spread pick. Book odds are shown as the price only."""
    if _ok(edge_spread) and _ok(market_spread):
        p_model = _curve(market_spread + edge_spread, sigma)      # home win chance, model
        p_vegas = _curve(market_spread, sigma)                    # home win chance, Vegas spread
        take_home = (spread_side == home) if spread_side else (p_model >= p_vegas)
        team = home if take_home else away
        mp = p_model if take_home else 1 - p_model
        vp = p_vegas if take_home else 1 - p_vegas
        edge = max(mp - vp, 0.0) * 100
        odds = (ml_home if take_home else ml_away) if _ok(ml_home) and _ok(ml_away) else None
        return {"pick": f"{team} {_fmt_odds(odds)}" if odds else f"{team} ML", "side": team,
                "odds": _fmt_odds(odds) if odds else None,
                "edge": round(edge, 1), "edge_text": f"{edge:.1f}%",
                "model_pct": round(mp * 100), "vegas_pct": round(vp * 100)}
    if not _ok(win_prob_home):
        return None
    p_home = win_prob_home / 100                                   # no Vegas line yet
    take_home = p_home >= 0.5
    team = home if take_home else away
    pct = round((p_home if take_home else 1 - p_home) * 100)
    return {"pick": f"{team} ML", "side": team, "odds": None, "edge": None,
            "edge_text": f"{pct}% to win", "model_pct": pct, "vegas_pct": None}


def build(g, ml_home=None, ml_away=None):
    """g is a game record as written to latest.json."""
    sp = spread_pick(g["home"], g["away"], g.get("edge_spread"), g.get("market_spread"),
                     g.get("cover_prob_home"))
    return {
        "spread": sp,
        "total": total_pick(g.get("edge_total"), g.get("market_total"), g.get("over_prob")),
        "moneyline": moneyline_pick(g["home"], g["away"], g.get("win_prob_home"), ml_home, ml_away,
                                    g.get("edge_spread"), g.get("market_spread"),
                                    g.get("win_sigma") or 11.4, sp["side"] if sp else None),
    }



# ---------------------------------------------------------------------
# Grading every pick
# ---------------------------------------------------------------------
STD_WIN = 100 / 110                                   # spread and total payout at -110


def _payout(odds):
    o = float(str(odds).replace("+", ""))
    return o / 100 if o > 0 else 100 / -o


def grade_one(g, home_score, away_score):
    """Returns {market: (result, units)} with result 'W', 'L' or 'P'."""
    pk = g.get("picks") or build(g, g.get("ml_home"), g.get("ml_away"))
    act = home_score - away_score
    tot = home_score + away_score
    out = {}
    s = pk.get("spread")
    if s:
        r = (act if s["side"] == g["home"] else -act) + s["line"]
        out["spread"] = ("P", 0.0) if r == 0 else (("W", STD_WIN) if r > 0 else ("L", -1.0))
    t = pk.get("total")
    if t:
        r = tot - t["line"]
        if r == 0:
            out["total"] = ("P", 0.0)
        else:
            win = (r > 0) == (t["side"] == "Over")
            out["total"] = ("W", STD_WIN) if win else ("L", -1.0)
    m = pk.get("moneyline")
    if m:
        if act == 0:
            out["moneyline"] = ("P", 0.0)
        else:
            win = (act > 0) == (m["side"] == g["home"])
            u = None if not m.get("odds") else (_payout(m["odds"]) if win else -1.0)
            out["moneyline"] = ("W" if win else "L", u)
    return out, pk


EDGE_BINS = {"spread": [(0, 1, "Under 1 pt"), (1, 2, "1 to 2 pts"), (2, 99, "2+ pts")],
             "total": [(0, 1, "Under 1 pt"), (1, 2, "1 to 2 pts"), (2, 99, "2+ pts")],
             "moneyline": [(0, 1, "Under 1%"), (1, 3, "1 to 3%"), (3, 999, "3%+")]}


def summarize(graded):
    """graded: list of (market, result, units, edge). Records per market and by edge size."""
    def rec(rows):
        w = sum(1 for r in rows if r[1] == "W")
        l = sum(1 for r in rows if r[1] == "L")
        p = sum(1 for r in rows if r[1] == "P")
        priced = [r[2] for r in rows if r[2] is not None]
        return {"w": w, "l": l, "p": p, "n": w + l,
                "pct": round(100 * w / (w + l), 1) if w + l else None,
                "units": round(sum(priced), 2) if priced else None,
                "priced": len(priced)}
    out = {}
    for mkt, bins in EDGE_BINS.items():
        rows = [r for r in graded if r[0] == mkt]
        out[mkt] = rec(rows)
        out[mkt]["by_edge"] = []
        for lo, hi, name in bins:
            sub = [r for r in rows if r[3] is not None and lo <= r[3] < hi]
            out[mkt]["by_edge"].append({"range": name, **rec(sub)})
    return out
