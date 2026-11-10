"""
Prop diagnosis (Oct 31 2026): when a prop type (sport + stat + side) is losing, find out WHY, not just pause it.

For one prop type it reads every graded prop the model priced against a book line (plays, and all the other leans as
a comparison) and checks the usual causes, each with its numbers:

  1. Projection bias     the model's middle number vs what happened (too high / too low), and the book's line vs
                         what happened (is the market itself off, or just the model?)
  2. Calibration         the model's chance on the bet side vs how often it hit, raw and after the site's adjustments
  3. Edge size           do bigger edges do better (real signal) or worse (the model is missing information)?
  4. Plays vs all leans  is the model wrong on this stat in general, or only on the ones it picks to bet?
  5. Price               average price paid and the hit rate needed to break even (heavy juice on Unders?)
  6. Line movement       did the line move with the play or against it before the game (information the model lacks)?
  7. Line size / role    low lines (bench / low-volume players) vs high lines (starters)
  8. Zeros               Overs lost to a 0 (didn't play, left early, role cut)
  9. Clustering          many plays on one night / one game (one bet on the game environment)
 10. Trend               early weeks vs recent weeks

Then it ranks the likely causes and suggests a fix. Used by tools/weekly_review.py for every flagged or paused prop type.

    python tools/prop_diagnose.py nhl sog Under
    python tools/prop_diagnose.py nfl rush_yds Over
"""
import glob
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = {"nfl": ROOT / "docs/data", "nhl": ROOT / "docs/nhl/data", "nba": ROOT / "docs/nba/data", "cfb": ROOT / "docs/cfb/data"}
IDX = {"nhl": {"sog": 0, "goals": 1, "assists": 2, "points": 3, "saves": 0},
       "nba": {"pts": 0, "reb": 1, "ast": 2, "fg3m": 3},
       "cfb": {"pass_yds": 0, "pass_td": 1, "rush_yds": 2, "rec_yds": 3, "rec": 4, "td": 5}}


def _load(p, d=None):
    try:
        return json.loads(Path(p).read_text())
    except Exception:  # noqa: BLE001
        return d


def _f(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def implied(o):
    o = _f(o)
    if o is None or o == 0:
        return None
    return 100 / (o + 100) if o > 0 else -o / (-o + 100)


def payout(o):
    o = _f(o)
    return None if o is None else (o / 100 if o > 0 else 100 / -o)


# ---------------------------------------------------------------------
# rows: one per graded prop with a book line
# ---------------------------------------------------------------------
def rows(sport):
    """{date, player, stat, side (the model's lean), line, odds, p_raw / p_adj (model chance of the lean side, 0-1),
    book_p (book no-vig chance of the lean side), fair (model middle), actual, win (True/False/None push), play,
    close_book_p (book chance of the lean side at the last pre-game line), pos}"""
    out = []
    if sport == "nfl":
        for v in (_load(DATA["nfl"] / "props_log.json", {}).get("props") or {}).values():
            res = v.get("flag_result") if v.get("flag") else v.get("result")
            fl = v.get("flag") or {}
            if not res or res.get("actual") is None or v.get("line") in (None, ""):
                continue
            side = fl.get("lean") or v.get("lean")
            line = _f(fl.get("line") or v.get("line"))
            bo, mo = _f(fl.get("book_over", v.get("book_over"))), _f(fl.get("model_over", v.get("model_over")))
            if side not in ("Over", "Under") or line is None or bo is None or mo is None:
                continue
            a = _f(res["actual"])
            win = None if a == line else (a > line) == (side == "Over")
            ob = side == "Over"
            out.append({"date": f"w{int(v.get('week') or 0):02d}", "player": v.get("player"), "stat": v["stat"], "side": side, "line": line,
                        "odds": _f(fl.get("odds")) or _f(v.get("over_odds") if ob else v.get("under_odds")),
                        "p_raw": (mo if ob else 100 - mo) / 100, "p_adj": None, "book_p": (bo if ob else 100 - bo) / 100,
                        "fair": _f(v.get("median")), "actual": a, "win": win, "play": v.get("tier") == "play", "close_book_p": None,
                        "pos": v.get("pos"), "game": v.get("game_id")})
        return out
    res = _load(DATA[sport] / "results.json", {})
    for f in sorted(glob.glob(str(DATA[sport] / "history" / "*.json"))):
        day = _load(f, {})
        date = day.get("date") or day.get("week") or Path(f).stem
        for p in day.get("players", []):
            r = res.get(str(p.get("game_id")))
            st = (r or {}).get("p", {}).get(str(p.get("pid")))
            if st is None:
                continue
            for stat, m in (p.get("m") or {}).items():
                bk = m.get("flag") or m.get("book")
                if not bk or bk.get("line") is None or stat not in IDX.get(sport, {}) and sport != "nba":
                    continue
                line, side = _f(bk.get("line")), bk.get("side")
                if side not in ("Over", "Under") or line is None:
                    continue
                if sport == "nba":
                    a = st[0] + st[1] + st[2] if stat == "pra" else st[IDX["nba"].get(stat, 0)]
                else:
                    a = st[0] if (stat == "saves" or len(st) == 1) else st[IDX[sport][stat]]
                bo, edge = _f(bk.get("book_over")), _f(bk.get("edge"))
                ob = side == "Over"
                mo_raw = None if bo is None or edge is None else (bo + edge if ob else bo - edge)
                pre = _f(bk.get("pre"))
                cl = m.get("close") or {}
                cbo = _f(cl.get("book_over")) if _f(cl.get("line")) == line else None
                out.append({"date": str(date), "player": p.get("name"), "stat": stat, "side": side, "line": line, "odds": _f(bk.get("odds")),
                            "p_raw": None if mo_raw is None else (mo_raw if ob else 100 - mo_raw) / 100,
                            "p_adj": None if pre is None else (pre if ob else 100 - pre) / 100,
                            "book_p": None if bo is None else (bo if ob else 100 - bo) / 100,
                            "fair": _f(m.get("fair")), "actual": _f(a), "win": None if a == line else (a > line) == ob,
                            "play": bool(m.get("flag")) or bool(bk.get("play")),
                            "close_book_p": None if cbo is None else (cbo if ob else 100 - cbo) / 100, "pos": None, "game": p.get("game_id")})
    return out


# ---------------------------------------------------------------------
# the checks
# ---------------------------------------------------------------------
def _rec(rs):
    g = [r for r in rs if r["win"] is not None]
    w = sum(r["win"] for r in g)
    u = sum((payout(r["odds"]) or 0.91) if r["win"] else -1.0 for r in g)
    return {"n": len(g), "w": w, "l": len(g) - w, "pct": round(100 * w / len(g), 1) if g else None,
            "units": round(u, 2), "roi": round(100 * u / len(g), 1) if g else None}


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _se_pct(p, n):
    return 100 * math.sqrt(max(p, 0.01) * max(1 - p, 0.01) / max(n, 1))


def diagnose(sport, stat, side):
    R = [r for r in rows(sport) if r["stat"] == stat]
    if not R:
        return {"sport": sport, "stat": stat, "side": side, "error": "no graded props with a book line"}
    plays = [r for r in R if r["play"] and r["side"] == side]
    leans = [r for r in R if r["side"] == side]
    every = R
    d = {"sport": sport, "stat": stat, "side": side, "plays": _rec(plays), "leans_same_side": _rec(leans), "checks": {}, "causes": []}
    base = plays if len(plays) >= 15 else leans
    d["based_on"] = "plays" if base is plays else "every lean on this side (too few plays)"
    sgn = 1 if side == "Over" else -1
    C = d["checks"]
    # 1. projection bias, on every graded prop of this stat (not just this side)
    mb = _mean([r["actual"] - r["fair"] for r in every if r["fair"] is not None])
    lb = _mean([r["actual"] - r["line"] for r in every])
    C["projection"] = {"n": len(every), "actual_minus_model": None if mb is None else round(mb, 2), "actual_minus_line": None if lb is None else round(lb, 2)}
    # Nov 10 2026: a mean-minus-median gap shows up on skewed stats (points, yards) even when the model is right, so the
    # level-bias cause also needs the results to land above / below the model's fair line more often than half the time
    fx = [r["actual"] > r["fair"] for r in every if r["fair"] is not None and r["actual"] != r["fair"]]
    ov = sum(fx) / len(fx) if fx else None
    ovz = None if ov is None else (ov - 0.5) / math.sqrt(0.25 / len(fx))
    C["projection"].update({"over_rate_at_fair": None if ov is None else round(100 * ov, 1), "over_rate_z": None if ovz is None else round(ovz, 2)})
    if mb is not None and lb is not None:
        sd = _mean([abs(r["actual"] - r["line"]) for r in every]) or 1
        if (abs(mb) > 0.15 * sd and abs(mb) > abs(lb) + 0.05 * sd and sgn * mb < 0      # only when it hurts this side
                and ovz is not None and abs(ovz) >= 2 and (ovz > 0) == (mb > 0)):
            d["causes"].append((abs(mb) / sd, f"Projection bias: results ran {abs(mb):.2f} {'above' if mb > 0 else 'below'} the model's middle number "
                                f"on {len(every)} {stat} props, while the book's line missed by only {lb:+.2f}. The model's level for {stat} is off; "
                                f"shift it {'up' if mb > 0 else 'down'} (or let the prop bias correction learn faster)."))
        if abs(lb) > 0.15 * sd and sgn * lb < 0:
            d["causes"].append((abs(lb) / sd * 0.8, f"The market itself has run {'low' if lb > 0 else 'high'}: results beat the book's line by {lb:+.2f} on average. "
                                f"{'Unders' if lb > 0 else 'Overs'} into that are fighting the tide."))
    # 2. calibration on the bet side
    for key in ("p_raw", "p_adj"):
        xs = [r for r in base if r[key] is not None and r["win"] is not None]
        if len(xs) >= 10:
            said = 100 * _mean([r[key] for r in xs]); hit = 100 * _mean([float(r["win"]) for r in xs])
            C["calibration_" + key] = {"n": len(xs), "said": round(said, 1), "hit": round(hit, 1)}
    cal = C.get("calibration_p_adj") or C.get("calibration_p_raw")
    if cal:
        gap = cal["hit"] - cal["said"]; se = _se_pct(cal["said"] / 100, cal["n"])
        if gap < -1.5 * se:
            d["causes"].append((-gap / max(se, 1), f"Overconfidence: the model gave the bet side {cal['said']}% and it hit {cal['hit']}% over {cal['n']}. "
                                f"Shrink this prop type's chance toward the book's (betrules realization k) or raise its edge bar."))
    bk = [r for r in base if r["book_p"] is not None and r["win"] is not None]
    if len(bk) >= 10:
        C["book_said"] = {"n": len(bk), "book": round(100 * _mean([r["book_p"] for r in bk]), 1), "hit": round(100 * _mean([float(r["win"]) for r in bk]), 1)}
    # 3. edge size
    eb = []
    for lo, hi in ((0, 4), (4, 8), (8, 99)):
        xs = [r for r in base if r["p_raw"] is not None and r["book_p"] is not None and lo <= 100 * (r["p_raw"] - r["book_p"]) < hi]
        if xs:
            eb.append({"edge": f"{lo}-{hi if hi < 99 else '+'}", **_rec(xs)})
    C["by_edge"] = eb
    big = [x for x in eb if x["edge"].startswith("8")]
    small = [x for x in eb if x["edge"].startswith("0") or x["edge"].startswith("4")]
    if big and big[0]["n"] >= 8 and small and sum(s["n"] for s in small) >= 8:
        sp = sum(s["w"] for s in small) / max(1, sum(s["n"] for s in small)) * 100
        if big[0]["pct"] is not None and big[0]["pct"] < sp - 8:
            d["causes"].append((1.2, f"Bigger edges did worse ({big[0]['pct']}% at 8+ points vs {sp:.0f}% below): big gaps from the book usually mean news "
                                f"the model can't see (injury, role, lineup). Cap the edge for {stat} lower."))
    # 4. plays vs all leans
    if plays and len(leans) > len(plays) + 10:
        C["plays_vs_leans"] = {"plays": d["plays"], "all_leans": d["leans_same_side"]}
    # 5. price
    od = [r["odds"] for r in base if r["odds"] is not None]
    if od:
        be = 100 * _mean([implied(o) for o in od])
        C["price"] = {"avg_breakeven": round(be, 1), "hit": d["plays"]["pct"] if base is plays else d["leans_same_side"]["pct"],
                      "heavy_juice_share": round(100 * sum(1 for o in od if o <= -150) / len(od), 0)}
        hv = [r for r in base if r["odds"] is not None and r["odds"] <= -150]
        if len(hv) >= 8:
            hr = _rec(hv)
            C["price"]["heavy_juice"] = hr
            if hr["roi"] is not None and hr["roi"] < -10:
                d["causes"].append((1.0, f"Price: {len(hv)} bets at -150 or worse returned {hr['roi']}% (break-even about {round(100 * _mean([implied(r['odds']) for r in hv]))}%). "
                                    f"Skip heavy juice for {stat} {side}s or demand a bigger edge there."))
    # 6. line movement before the game
    mv = [r for r in base if r["close_book_p"] is not None and r["book_p"] is not None]
    if len(mv) >= 10:
        moves = [100 * (r["close_book_p"] - r["book_p"]) for r in mv]
        toward = sum(1 for x in moves if x > 0.5); against = sum(1 for x in moves if x < -0.5)
        C["line_move"] = {"n": len(mv), "avg_pts_toward_play": round(_mean(moves), 2), "toward": toward, "against": against}
        if against > toward * 1.4 and against >= 6:
            d["causes"].append((1.1, f"The market moved against these {against} times vs {toward} with them before the game (average {_mean(moves):+.1f} points): "
                                f"later information (lineups, injuries) went the other way. Bet these later, after news, or not at all."))
    # 7. line size
    if base:
        ls = sorted(r["line"] for r in base)
        cut = ls[len(ls) // 2]
        lo_, hi_ = [r for r in base if r["line"] <= cut], [r for r in base if r["line"] > cut]
        C["line_size"] = {f"<= {cut:g}": _rec(lo_), f"> {cut:g}": _rec(hi_)}
        a_, b_ = _rec(lo_), _rec(hi_)
        if a_["n"] >= 10 and b_["n"] >= 10 and a_["pct"] is not None and b_["pct"] is not None and abs(a_["pct"] - b_["pct"]) >= 12:
            worse = f"lines at or under {cut:g}" if a_["pct"] < b_["pct"] else f"lines over {cut:g}"
            d["causes"].append((0.9, f"Role / volume: {worse} did much worse ({min(a_['pct'], b_['pct'])}% vs {max(a_['pct'], b_['pct'])}%). "
                                f"{'Low lines are bench and low-volume players whose minutes swing; restrict to starters.' if a_['pct'] < b_['pct'] else 'High lines are stars the market prices sharply; the model adds little there.'}"))
    # 8. zeros (Overs)
    if side == "Over":
        zb = [r for r in base if r["line"] >= 1.5]                # a 0 on an Over 0.5 is just the normal way to lose
        z = [r for r in zb if r["actual"] == 0]
        C["zeros"] = {"n": len(z), "of": len(zb), "share": round(100 * len(z) / max(1, len(zb)), 1)}
        if len(zb) >= 15 and len(z) / len(zb) >= 0.12:
            d["causes"].append((1.0, f"Zeros: {len(z)} of {len(zb)} Overs (lines 1.5+) finished at 0 (didn't play, injured early, role cut). "
                                f"Skip questionable players and anyone without a clear role for {stat} Overs."))
    # 9. clustering
    by_night = {}
    for r in base:
        by_night.setdefault(r["date"], []).append(r)
    big_n = sorted(by_night.items(), key=lambda kv: -len(kv[1]))[:3]
    C["clustering"] = [{"date": k, "n": len(v), **_rec(v)} for k, v in big_n]
    weekly = sport in ("nfl", "cfb")                             # a "date" is a whole week there
    if base is plays and big_n and len(big_n[0][1]) >= (20 if weekly else 8):
        worst = _rec(big_n[0][1])
        if worst["roi"] is not None and worst["roi"] < -20:
            d["causes"].append((0.8, f"Clustering: {len(big_n[0][1])} plays on {big_n[0][0]} went {worst['w']}-{worst['l']}. Many same-direction plays in one "
                                f"{'week' if weekly else 'night'} are one bet on the game environment; cap them per {'game' if weekly else 'night'}."))
    # 10. trend
    dates = sorted(by_night)
    if len(dates) >= 4:
        half = len(dates) // 2
        C["trend"] = {"early": _rec([r for d_ in dates[:half] for r in by_night[d_]]), "recent": _rec([r for d_ in dates[half:] for r in by_night[d_]])}
    d["causes"] = [c for _, c in sorted(d["causes"], key=lambda t: -t[0])]
    if not d["causes"] and (d["plays"]["roi"] or 0) >= 0:
        d["causes"] = ["No flaw found, and the plays are at break-even or better. If this type is paused, the gate's shadow record decides "
                       "when it comes back (40+ graded over 3+ weeks, positive return, closing value not negative)."]
    if not d["causes"]:
        d["causes"] = ["No single cause stands out: the losses look like the model having no edge on this prop type rather than one fixable flaw. "
                       "Keep it paused (shadow plays keep grading it) until the gate's evidence says otherwise."]
    return d


def candidates(sport, gate_state=None, min_n=20, roi=-8.0):
    """Prop types worth diagnosing: plays with min_n+ graded returning roi% or worse, plus any paused prop gate."""
    R = rows(sport)
    out = set()
    by = {}
    for r in R:
        if r["play"]:
            by.setdefault((r["stat"], r["side"]), []).append(r)
    for k, rs in by.items():
        rc = _rec(rs)
        if rc["n"] >= min_n and rc["roi"] is not None and rc["roi"] <= roi:
            out.add(k)
    named = {"nfl_prop_overs": [("pass_yds", "Over"), ("rush_yds", "Over"), ("rec_yds", "Over")],      # older gates that cover
             "nfl_prop_rec": [("rec", "Over"), ("rec", "Under")], "nfl_prop_pass_under": [("pass_yds", "Under")],   # several types
             "nhl_points": [("points", "Over"), ("points", "Under")]}
    stats = {r["stat"] for r in R}
    for name, g in (gate_state or {}).items():
        if g.get("status") != "paused":
            continue
        if name in named:
            out.update(k for k in named[name] if k[0] in stats)
        elif name.startswith(f"{sport}_prop_"):
            parts = name[len(f"{sport}_prop_"):].rsplit("_", 1)
            if len(parts) == 2 and parts[1] in ("Over", "Under"):
                out.add(tuple(parts))
    return sorted(out)


def markdown(d):
    if d.get("error"):
        return f"### {d['sport'].upper()} {d['stat']} {d['side']}s: {d['error']}\n"
    P, Lr = d["plays"], d["leans_same_side"]
    out = [f"### {d['sport'].upper()} {d['stat']} {d['side']}s",
           f"Plays {P['w']}-{P['l']} ({P['units']:+}u, {P['roi']}%); every {d['side']} lean {Lr['w']}-{Lr['l']} ({Lr['roi']}%). Checks use {d['based_on']}.", "",
           "**Likely causes, most likely first:**"] + [f"{i + 1}. {c}" for i, c in enumerate(d["causes"])] + ["", "<details><summary>All checks</summary>", "",
           "```", json.dumps(d["checks"], indent=1, default=str)[:4000], "```", "</details>", ""]
    return "\n".join(out)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    print(markdown(diagnose(sys.argv[1].lower(), sys.argv[2], sys.argv[3].title())))
