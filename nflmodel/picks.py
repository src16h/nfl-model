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


def moneyline_pick(home, away, win_prob_home, ml_home=None, ml_away=None):
    """win_prob_home is a percent (0-100). With book odds, pick the side where the model's
    win chance beats the book's fair (no-cut) win chance by the most. Without odds,
    pick the team the model expects to win."""
    if not _ok(win_prob_home):
        return None
    p_home = win_prob_home / 100
    if _ok(ml_home) and _ok(ml_away) and ml_home != 0 and ml_away != 0:
        ih, ia = implied(ml_home), implied(ml_away)
        fair_home = ih / (ih + ia)                     # strip the book's cut
        e_home = p_home - fair_home
        take_home = e_home >= 0
        team, odds = (home, ml_home) if take_home else (away, ml_away)
        edge = abs(e_home) * 100
        return {"pick": f"{team} {_fmt_odds(odds)}", "side": team, "odds": _fmt_odds(odds),
                "edge": round(edge, 1), "edge_text": f"{edge:.1f}%",
                "model_pct": round((p_home if take_home else 1 - p_home) * 100),
                "book_pct": round((fair_home if take_home else 1 - fair_home) * 100)}
    take_home = p_home >= 0.5
    team = home if take_home else away
    pct = round((p_home if take_home else 1 - p_home) * 100)
    return {"pick": f"{team} ML", "side": team, "odds": None, "edge": None,
            "edge_text": f"{pct}% to win", "model_pct": pct, "book_pct": None}


def build(g, ml_home=None, ml_away=None):
    """g is a game record as written to latest.json."""
    return {
        "spread": spread_pick(g["home"], g["away"], g.get("edge_spread"), g.get("market_spread"),
                              g.get("cover_prob_home")),
        "total": total_pick(g.get("edge_total"), g.get("market_total"), g.get("over_prob")),
        "moneyline": moneyline_pick(g["home"], g["away"], g.get("win_prob_home"), ml_home, ml_away),
    }
