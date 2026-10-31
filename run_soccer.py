"""
Soccer model: Premier League, Championship and La Liga.

Each run: refit team ratings on every league match (xG where free, shots elsewhere), price the next
week of fixtures (1X2, draw no bet, Asian handicap, totals, BTTS), price player props (anytime
goalscorer, shots on target), compare with book lines (The Odds API, its own free key), grade
finished matches, and write docs/soccer/data/latest.json for the site.
"""
import json
import logging
import math
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from soccermodel import backtest as BT
from soccermodel import config as C
from soccermodel import data as D
from soccermodel import fatigue as F
from soccermodel import market as MK
from soccermodel import model as M
from soccermodel import odds as O
from soccermodel import props as P
from soccermodel.util import clean, r

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import betrules as BR  # noqa: E402
import altlines as AL  # noqa: E402
import gates as GT  # noqa: E402
import crossgame as XG  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("soccermodel")
OUT = ROOT / "docs" / "soccer" / "data"
HIST = OUT / "history"
ET = ZoneInfo("America/New_York")
DEFAULT_RHO = {"epl": 0.04, "champ": 0.0, "laliga": 0.07}     # from the backtest when it has not been rerun


def load_json(p, default):
    try:
        return json.loads(Path(p).read_text())
    except Exception:  # noqa: BLE001
        return default


def american(p):
    p = min(max(p, 1e-4), 1 - 1e-4)
    return round(-100 * p / (1 - p)) if p >= 0.5 else round(100 * (1 - p) / p)


def fmt_odds(o):
    if o is None:
        return None
    o = int(round(float(o)))
    return f"+{o}" if o > 0 else str(o)


def imp(o):
    o = float(o)
    return 100 / (o + 100) if o > 0 else -o / (-o + 100)


def nv(*odds):
    ps = [imp(o) for o in odds]
    s = sum(ps)
    return [p / s for p in ps]


# ---------------------------------------------------------------------
# picks and plays for one match
# ---------------------------------------------------------------------
def dec(o):
    o = float(o)
    return 1 + (o / 100 if o > 0 else 100 / -o)


def _side_rows(g, G, b):
    """Every priced side: market, label, who, line, bet odds, model / bet-book / sharp chances (sharp only when Pinnacle has
    the same line)."""
    sh = b.get("sharp") or {}
    ph, pd_, pa = M.p1x2(G)
    rows = []
    if b.get("ml_home") and b.get("ml_draw") and b.get("ml_away"):
        bp = nv(b["ml_home"], b["ml_draw"], b["ml_away"])
        sp = nv(sh["ml_home"], sh["ml_draw"], sh["ml_away"]) if sh.get("ml_home") and sh.get("ml_draw") and sh.get("ml_away") else [None] * 3
        for i, (who, side, pm, o) in enumerate((("home", g["home"], ph, b["ml_home"]), ("draw", "Draw", pd_, b["ml_draw"]),
                                                 ("away", g["away"], pa, b["ml_away"]))):
            rows.append({"mkt": "1x2", "who": who, "side": side, "line": None, "odds": o, "pm": pm, "pb": bp[i], "ps": sp[i]})
    L = b.get("ah_home")
    if L is not None and b.get("ah_home_odds") and b.get("ah_away_odds"):
        mh = M.cover(M.ah(G, L))
        bh = nv(b["ah_home_odds"], b["ah_away_odds"])[0]
        sp = nv(sh["ah_home_odds"], sh["ah_away_odds"])[0] if sh.get("ah_home") == L and sh.get("ah_home_odds") and sh.get("ah_away_odds") else None
        rows.append({"mkt": "ah", "who": "home", "side": g["home"], "line": L, "odds": b["ah_home_odds"], "pm": mh, "pb": bh, "ps": sp})
        rows.append({"mkt": "ah", "who": "away", "side": g["away"], "line": -L, "odds": b["ah_away_odds"], "pm": 1 - mh, "pb": 1 - bh,
                     "ps": None if sp is None else 1 - sp})
    T = b.get("total")
    if T is not None and b.get("over_odds") and b.get("under_odds"):
        mo = M.cover(M.total(G, T))
        bo = nv(b["over_odds"], b["under_odds"])[0]
        sp = nv(sh["over_odds"], sh["under_odds"])[0] if sh.get("total") == T and sh.get("over_odds") and sh.get("under_odds") else None
        rows.append({"mkt": "total", "who": "over", "side": "Over", "line": T, "odds": b["over_odds"], "pm": mo, "pb": bo, "ps": sp})
        rows.append({"mkt": "total", "who": "under", "side": "Under", "line": T, "odds": b["under_odds"], "pm": 1 - mo, "pb": 1 - bo,
                     "ps": None if sp is None else 1 - sp})
    for x in rows:
        x["gap"] = 100 * (x["pm"] - x["pb"])                       # model vs the bet book
        x["sev"] = None if x["ps"] is None else 100 * (x["ps"] * dec(x["odds"]) - 1)   # value by Pinnacle's fair price
        # play rule (Oct 20 2026 backtest): Pinnacle says the price is value AND the model agrees with the side
        x["play"] = bool(x["sev"] is not None and C.SHARP_MIN_EV <= x["sev"] <= C.SHARP_MAX_EV and x["gap"] >= C.MODEL_AGREE)
    return rows


def picks(g, G, mk=None):
    """mk: Pinnacle-implied scorelines (soccermodel/market.py) or None. Plays only come from book prices (the Pinnacle
    rule in _side_rows); the market numbers here show how the model's leans compare with the sharp price."""
    b = g.get("book") or {}
    sh = b.get("sharp") or {}
    ph, pd_, pa = M.p1x2(G)
    rows = _side_rows(g, G, b)
    out = {}
    for mkt in ("1x2", "ah", "total"):
        rs = [x for x in rows if x["mkt"] == mkt]
        if not rs:
            continue
        plays = [x for x in rs if x["play"]]
        x = max(plays, key=lambda y: y["sev"]) if plays else max([y for y in rs if y["who"] != "draw"] or rs, key=lambda y: y["gap"])
        out[mkt] = {"side": x["side"], "who": x["who"], "line": x["line"], "odds": fmt_odds(x["odds"]), "model": r(100 * x["pm"]),
                    "book": r(100 * x["pb"]), "sharp": None if x["ps"] is None else r(100 * x["ps"]), "edge": r(x["gap"]),
                    "ev": None if x["sev"] is None else r(x["sev"]), "play": x["play"]}
        if mkt == "total" and x["ps"] is None and mk is not None:
            # Pinnacle posted a different total: convert its price to the bet book's line (approximate, never a play)
            po = M.cover(M.total(mk["G"], x["line"]))
            pc = po if x["who"] == "over" else 1 - po
            out[mkt].update({"conv": r(100 * pc), "ev_conv": r(100 * (pc * dec(x["odds"]) - 1)), "conv_from": sh.get("total")})
    if "1x2" in out:
        d = next(y for y in rows if y["mkt"] == "1x2" and y["who"] == "draw")
        out["1x2"]["draw"] = {"model": r(100 * pd_), "book": r(100 * d["pb"]), "odds": fmt_odds(d["odds"])}
    else:
        best = ("home", g["home"], ph) if ph >= pa else ("away", g["away"], pa)
        out["1x2"] = {"side": best[1], "who": best[0], "odds": None, "model": r(100 * best[2]), "book": None, "edge": None,
                      "fair": fmt_odds(american(best[2])), "draw": {"model": r(100 * pd_), "fair": fmt_odds(american(pd_))}, "play": False}
    if "ah" not in out:
        if sh.get("ah_home") is not None and sh.get("ah_home_odds") and sh.get("ah_away_odds"):
            # no bet-book handicap in the feed: lean at Pinnacle's main line, model vs Pinnacle's no-vig chance
            L = float(sh["ah_home"])
            mh, kh = M.cover(M.ah(G, L)), nv(sh["ah_home_odds"], sh["ah_away_odds"])[0]
            home = mh - kh >= 0
            pm, pk = (mh, kh) if home else (1 - mh, 1 - kh)
            out["ah"] = {"side": g["home"] if home else g["away"], "who": "home" if home else "away", "line": L if home else -L,
                         "odds": None, "pin": fmt_odds(sh["ah_home_odds"] if home else sh["ah_away_odds"]), "model": r(100 * pm),
                         "mkt": r(100 * pk), "book": None, "edge": r(100 * (pm - pk)), "fair": fmt_odds(american(pm)),
                         "mfair": fmt_odds(american(pk)), "play": False}
        else:
            best_l, best_d = 0.0, 9
            for l2 in np.arange(-2.5, 2.51, 0.25):                  # the quarter line closest to 50/50
                c = M.cover(M.ah(G, l2))
                if abs(c - 0.5) < best_d:
                    best_l, best_d = float(l2), abs(c - 0.5)
            c = M.cover(M.ah(G, best_l))
            home = c >= 0.5
            out["ah"] = {"side": g["home"] if home else g["away"], "who": "home" if home else "away", "line": best_l if home else -best_l,
                         "odds": None, "model": r(100 * max(c, 1 - c)), "book": None, "edge": None, "fair": fmt_odds(american(max(c, 1 - c))),
                         "play": False}
    if "total" not in out:
        mo = M.cover(M.total(G, 2.5))
        out["total"] = {"side": "Over" if mo >= 0.5 else "Under", "who": "over" if mo >= 0.5 else "under", "line": 2.5, "odds": None,
                        "model": r(100 * max(mo, 1 - mo)), "book": None, "edge": None, "fair": fmt_odds(american(max(mo, 1 - mo))), "play": False}
    dh = ph / (ph + pa)
    out["dnb"] = {"side": g["home"] if dh >= 0.5 else g["away"], "who": "home" if dh >= 0.5 else "away", "model": r(100 * max(dh, 1 - dh)),
                  "fair": fmt_odds(american(max(dh, 1 - dh))), "odds": None, "book": None, "edge": None, "play": False}
    bt = M.btts(G)
    out["btts"] = {"side": "Yes" if bt >= 0.5 else "No", "model": r(100 * max(bt, 1 - bt)), "fair": fmt_odds(american(max(bt, 1 - bt))),
                   "yes": r(100 * bt), "odds": None, "book": None, "edge": None, "play": False}
    if mk is not None:
        # draw no bet straight from Pinnacle's 1X2 (exact), BTTS from its fitted scorelines
        kdh = mk["p_home"] / (mk["p_home"] + mk["p_away"])
        k = kdh if out["dnb"]["who"] == "home" else 1 - kdh
        out["dnb"].update({"mkt": r(100 * k), "mfair": fmt_odds(american(k)), "edge": r(out["dnb"]["model"] - 100 * k)})
        kb = M.btts(mk["G"])
        k = kb if out["btts"]["side"] == "Yes" else 1 - kb
        out["btts"].update({"mkt": r(100 * k), "myes": r(100 * kb), "mfair": fmt_odds(american(k)), "edge": r(out["btts"]["model"] - 100 * k)})
    return out


def alt_parlay(g, G, mk):
    """Alt-line parlay from the scoreline grids: handicaps, totals, team totals and BTTS. Each leg is priced at Pinnacle's
    implied chance (the model must rate it at least as high); the ticket's chance comes straight from the grid, so legs
    that move together (a team total and that team's handicap) are priced together. Most likely ticket at fair +100 to +125."""
    if mk is None:
        return None
    md, kd = AL.Dist.from_grid(G), AL.Dist.from_grid(mk["G"])
    bets = [{"market": "btts", "team": None, "side": s_, "line": 0.0} for s_ in ("yes", "no")]
    for L in (-1.5, -0.5, 0.5, 1.5, 2.5):
        for sd in ("home", "away"):
            bets.append({"market": "spread", "team": sd, "side": sd, "line": L})
    for L in (0.5, 1.5, 2.5, 3.5, 4.5):
        for sd in ("over", "under"):
            bets.append({"market": "total", "team": None, "side": sd, "line": L})
    for L in (0.5, 1.5, 2.5):
        for t in ("home", "away"):
            for sd in ("over", "under"):
                bets.append({"market": "team_total", "team": t, "side": sd, "line": L})
    lo, hi = C.ALT_PARLAY_LEG
    cands = []
    for b in bets:
        pk, pm = kd.p(b), md.p(b)
        if lo <= pk <= hi and pm >= pk:
            cands.append((b, md.x(b) > 0, pk, pm))
    best = None
    plo, phi = C.ALT_PARLAY_P
    import itertools
    for n in (3, 2):
        for combo in itertools.combinations(range(len(cands)), n):
            if len({cands[i][0]["market"] + (str(cands[i][0].get("team")) if cands[i][0]["market"] == "team_total" else "") for i in combo}) < n:
                continue                                    # one handicap, one total, one BTTS, one team total per team
            hit = np.logical_and.reduce([cands[i][1] for i in combo])
            pk = float(np.sum(kd.w[hit])); pm = float(np.sum(md.w[hit]))
            if plo <= pk <= phi and pm >= pk and (best is None or pk > best[1] + 1e-9 or (abs(pk - best[1]) < 1e-9 and pm > best[2])):
                best = (combo, pk, pm)
        if best:
            break
    if not best:
        return None
    combo, pk, pm = best
    dec = (1 + C.ALT_BET_CUSHION) / pk                       # "bet at": room for the estimate being a little off (as NHL/NBA)
    return {"p": r(100 * pk), "p_model": r(100 * pm), "pi": r(100 * float(np.prod([cands[i][2] for i in combo]))), "fair": fmt_odds(american(pk)),
            "bet_at": fmt_odds(round((dec - 1) * 100) if dec >= 2 else round(-100 / (dec - 1))), "cushion": C.ALT_BET_CUSHION,
            "legs": [{**cands[i][0], "label": AL.label(cands[i][0], g["home"], g["away"]), "p": r(100 * cands[i][2]), "p_model": r(100 * cands[i][3])}
                     for i in combo]}


def cross_legs(g, G, mk):
    """Legs for the cross-game parlays (crossgame.py): alt handicaps and totals, each priced at Pinnacle's implied chance
    (its 1X2, handicap and total re-weighted onto the scoreline grid), the model rating it at least as high."""
    if mk is None:
        return []
    md, kd = AL.Dist.from_grid(G), AL.Dist.from_grid(mk["G"])
    bets = [{"market": "spread", "team": sd, "side": sd, "line": L} for L in (-1.5, -0.5, 0.5, 1.5, 2.5) for sd in ("home", "away")]
    bets += [{"market": "total", "team": None, "side": sd, "line": L} for L in (0.5, 1.5, 2.5, 3.5, 4.5) for sd in ("over", "under")]
    out = []
    for b in bets:
        pk, pm = kd.p(b), md.p(b)
        if 0.70 <= pk <= 0.92 and pm >= pk:
            out.append({**b, "team_side": b["team"], "label": AL.label(b, g["home"], g["away"]), "p": pk, "p_model": pm})
    return out


def form(df, team, before, n=6):
    """Last n league matches: results oldest to newest, goals and xG per match (xG only where Understat has it)."""
    m = df[((df["home"] == team) | (df["away"] == team)) & (df["date"] < before) & df["hg"].notna()].tail(n)
    if m.empty:
        return None
    res, gf, ga, xf, xa = [], [], [], [], []
    for _, x in m.iterrows():
        home = x["home"] == team
        f, a = (x["hg"], x["ag"]) if home else (x["ag"], x["hg"])
        res.append("W" if f > a else "D" if f == a else "L")
        gf.append(f); ga.append(a)
        hx, ax = x.get("hxg"), x.get("axg")
        if hx is not None and ax is not None and np.isfinite(hx) and np.isfinite(ax):
            xf.append(hx if home else ax); xa.append(ax if home else hx)
    return {"res": "".join(res), "pts": sum(3 if c == "W" else 1 if c == "D" else 0 for c in res), "gf": r(np.mean(gf), 2),
            "ga": r(np.mean(ga), 2), "xgf": r(np.mean(xf), 2) if xf else None, "xga": r(np.mean(xa), 2) if xa else None}


def limit_plays(games):
    """One play per match (the best by Pinnacle value), then at most DAILY_CAP per league per day."""
    cand = []
    for g in games:
        GT.hold_back(g["picks"], getattr(C, "GAME_PAUSED", set()))   # paused bet types (gates.py) become shadow picks
        ps = [(k, p) for k, p in g["picks"].items() if p.get("play")]
        for k, p in ps:
            p["play"] = False
        if ps:
            k, p = max(ps, key=lambda kp: kp[1]["ev"])
            cand.append((g, k, p))
    taken = {}
    for g, k, p in sorted(cand, key=lambda c: -c[2]["ev"]):
        key = (g["league"], g["date"])
        if taken.get(key, 0) < C.DAILY_CAP:
            p["play"] = True
            taken[key] = taken.get(key, 0) + 1


def grade(kind, pk, g, hg, ag):
    if kind == "1x2":
        y = "home" if hg > ag else ("draw" if hg == ag else "away")
        rr = "W" if pk.get("who") == y else "L"
        units = M_units(rr, pk.get("odds"))
        return rr, units
    if kind in ("ah",):
        margin = (hg - ag) if pk["side"] == g["home"] else (ag - hg)
        parts = M.split(pk["line"])
        tot, res = 0.0, []
        for half in parts:
            v = margin + half
            o = BR.payout(pk["odds"]) if pk.get("odds") else None
            res.append("W" if v > 0 else ("P" if v == 0 else "L"))
            if o is not None:
                tot += (o if v > 0 else (0 if v == 0 else -1)) / len(parts)
        rr = "W" if all(x == "W" for x in res) else ("L" if all(x == "L" for x in res) else
                                                      ("P" if all(x == "P" for x in res) else ("HW" if "W" in res else "HL")))
        return rr, (tot if pk.get("odds") else None)
    if kind == "total":
        parts = M.split(pk["line"])
        tot, res = 0.0, []
        for half in parts:
            v = (hg + ag) - half
            if pk["side"] == "Under":
                v = -v
            res.append("W" if v > 0 else ("P" if v == 0 else "L"))
            if pk.get("odds"):
                o = BR.payout(pk["odds"])
                tot += (o if v > 0 else (0 if v == 0 else -1)) / len(parts)
        rr = "W" if all(x == "W" for x in res) else ("L" if all(x == "L" for x in res) else
                                                      ("P" if all(x == "P" for x in res) else ("HW" if "W" in res else "HL")))
        return rr, (tot if pk.get("odds") else None)
    if kind == "dnb":
        if hg == ag:
            return "P", 0.0
        rr = "W" if (hg > ag) == (pk["side"] == g["home"]) else "L"
        return rr, None
    if kind == "btts":
        yes = hg > 0 and ag > 0
        return ("W" if yes == (pk["side"] == "Yes") else "L"), None
    return None, None


def M_units(rr, odds):
    if not odds:
        return None
    return BR.payout(odds) if rr == "W" else -1.0


# ---------------------------------------------------------------------
# tracking
# ---------------------------------------------------------------------
def close_prob(g, k, fl):
    """Closing fair chance for a flagged side, from the last lines saved before kickoff: Pinnacle when it has the same
    line, else the bet book. None when the line moved (a different handicap or total can't be compared directly)."""
    b = g.get("book") or {}
    for src in (b.get("sharp") or {}, b):
        if k == "1x2" and src.get("ml_home") and src.get("ml_draw") and src.get("ml_away"):
            p3 = nv(src["ml_home"], src["ml_draw"], src["ml_away"])
            return {"home": p3[0], "draw": p3[1], "away": p3[2]}.get(fl.get("who")), src is not b
        if k == "ah" and src.get("ah_home") is not None and src.get("ah_home_odds") and src.get("ah_away_odds"):
            line_home = fl["line"] if fl.get("who") == "home" else -fl["line"]
            if abs(src["ah_home"] - line_home) < 1e-9:
                ph = nv(src["ah_home_odds"], src["ah_away_odds"])[0]
                return (ph if fl.get("who") == "home" else 1 - ph), src is not b
        if k == "total" and src.get("total") is not None and src.get("over_odds") and src.get("under_odds"):
            if abs(src["total"] - fl["line"]) < 1e-9:
                po = nv(src["over_odds"], src["under_odds"])[0]
                return (po if fl.get("side") == "Over" else 1 - po), src is not b
    return None, False


def tracking(days, results, boxes):
    gate_rows = {GT.game_gate("soccer", k): ([], []) for k in GT.GAME_KINDS["soccer"]}   # (shadow, real) for gates.py
    picks_all = {k: [] for k in ("1x2", "dnb", "ah", "total", "btts")}
    plays, daily, calib = [], {}, {"goal": [], "sot1": [], "sot2": []}
    alt_plays, parlays = [], []
    for day in days:
        dt = day["date"]
        for g in day.get("games", []):
            res = results.get(str(g["game_id"]))
            if not res:
                continue
            hg, ag = res["hg"], res["ag"]
            for k, pk in (g.get("picks") or {}).items():
                rr, u = grade(k, pk, g, hg, ag)
                if rr is None:
                    continue
                picks_all[k].append((rr, u, g["league"]))
            for fl in (g.get("alt_flags") or {}).values():
                rr, u = AL.grade(fl, hg, ag)
                alt_plays.append({"date": dt, "league": g["league"], "kind": "alt", "market": fl["market"], "pick": fl.get("label"),
                                  "game": f"{g['home']} vs {g['away']}", "odds": fl.get("odds"), "edge": fl.get("ev"), "res": rr,
                                  "units": u or 0.0, "score": f"{hg}-{ag}", "book": fl.get("book"), "exact": fl.get("exact")})
                daily[dt] = daily.get(dt, 0) + (u or 0)
            ap = g.get("alt_parlay")
            if ap and ap.get("legs"):
                hits = [AL.grade(L, hg, ag)[0] == "W" for L in ap["legs"]]
                parlays.append({"date": dt, "league": g["league"], "game": f"{g['home']} vs {g['away']}", "hit": all(hits),
                                "legs_hit": sum(hits), "legs": len(hits), "p": ap["p"], "fair": ap.get("fair"), "score": f"{hg}-{ag}",
                                "leg_labels": [L.get("label") for L in ap["legs"]], "leg_p": [L.get("p") for L in ap["legs"]], "leg_hits": hits})
            flags = g.get("flags")
            if flags is None:                                   # files written before flags existed
                flags = {k: pk for k, pk in (g.get("picks") or {}).items() if pk.get("play")}
            for k, fl in flags.items():
                if not fl.get("odds"):
                    continue
                rr, u = grade(k, fl, g, hg, ag)
                if rr is None:
                    continue
                pc, sharp_close = close_prob(g, k, fl)
                clv = None if pc is None else r(100 * (pc * dec(fl["odds"]) - 1), 2)
                text = (f"{fl['side']} {fl['line']:+g}" if k == "ah" else (f"{fl['side']} {fl['line']:g}" if k == "total" else
                        ("Draw" if fl.get("who") == "draw" else f"{fl['side']} to win")))
                plays.append({"date": dt, "league": g["league"], "kind": k, "pick": text, "game": f"{g['home']} vs {g['away']}",
                              "odds": fl.get("odds"), "edge": fl.get("ev", fl.get("edge")), "res": rr, "units": u or 0.0,
                              "score": f"{hg}-{ag}", "clv": clv, "clv_sharp": sharp_close, "legacy": bool(fl.get("legacy"))})
                daily[dt] = daily.get(dt, 0) + (u or 0)
                if k in GT.GAME_KINDS["soccer"]:     # soccer's clv is already expected return at the closing fair price
                    gate_rows[GT.game_gate("soccer", k)][1].append({"date": dt, "res": rr, "units": u or 0.0, "ev": clv})
            for k, fl in (g.get("shadow_flags") or {}).items():     # paused bet types: graded, not counted as plays
                if not fl.get("odds") or k not in GT.GAME_KINDS["soccer"]:
                    continue
                rr, u = grade(k, fl, g, hg, ag)
                if rr is None:
                    continue
                pc, _ = close_prob(g, k, fl)
                gate_rows[GT.game_gate("soccer", k)][0].append(
                    {"date": dt, "res": rr, "units": u or 0.0, "ev": None if pc is None else 100 * (pc * dec(fl["odds"]) - 1)})
        for p in day.get("players", []):
            bx = boxes.get(str(p["game_id"]))
            if not bx:
                continue
            st = bx.get(str(p["pid"]))
            if st is None:                                   # didn't play: void
                continue
            calib["goal"].append((p["m"]["goal"]["pf1"], st["goals"] >= 1))
            calib["sot1"].append((p["m"]["sot"]["pf1"], st["sot"] >= 1))
            calib["sot2"].append((p["m"]["sot"]["pf2"], st["sot"] >= 2))

    def rec(rows):
        w = sum(1 for x in rows if x[0] in ("W", "HW")); l_ = sum(1 for x in rows if x[0] in ("L", "HL"))
        us = [x[1] for x in rows if x[1] is not None]
        return {"w": w, "l": l_, "pct": r(100 * w / (w + l_)) if w + l_ else None, "units": r(sum(us), 2) if us else None}

    def rec2(rows):
        w = sum(1 for x in rows if x["res"] in ("W", "HW")); l_ = sum(1 for x in rows if x["res"] in ("L", "HL"))
        u = sum(x["units"] or 0 for x in rows)
        return {"w": w, "l": l_, "pct": r(100 * w / (w + l_)) if w + l_ else None, "units": r(u, 2), "roi": r(100 * u / (w + l_)) if w + l_ else None}

    series, run = [], 0.0
    for dt in sorted(daily):
        run += daily[dt]
        series.append({"date": dt, "units": r(run, 2)})
    cal = {}
    for k, rows in calib.items():
        if rows:
            cal[k] = {"n": len(rows), "model": r(100 * np.mean([x[0] for x in rows])), "actual": r(100 * np.mean([x[1] for x in rows]))}
    by_league = {lg: rec2([x for x in plays if x["league"] == lg]) for lg in C.LEAGUES}
    cl = [x["clv"] for x in plays if x["clv"] is not None]
    clv = {"n": len(cl), "avg": r(float(np.mean(cl)), 2) if cl else None,
           "beat": r(100 * float(np.mean([c > 0 for c in cl]))) if cl else None,
           "sharp_share": r(100 * float(np.mean([x["clv_sharp"] for x in plays if x["clv"] is not None]))) if cl else None}
    alt_rec = {**rec2(alt_plays), "by_market": {m: rec2([x for x in alt_plays if x["market"] == m]) for m in ("btts", "spread", "total", "team_total")},
               "list": sorted(alt_plays, key=lambda x: x["date"], reverse=True)[:60]}
    lp = [(p_, h_) for x in parlays for p_, h_ in zip(x.get("leg_p") or [], x.get("leg_hits") or []) if p_ is not None]
    par_rec = {"n": len(parlays), "hits": sum(x["hit"] for x in parlays), "model": r(float(np.mean([x["p"] for x in parlays]))) if parlays else None,
               "legs_n": len(lp), "legs_model": r(float(np.mean([a for a, _ in lp]))) if lp else None,
               "legs_actual": r(100 * float(np.mean([b for _, b in lp]))) if lp else None,
               "recent": sorted(parlays, key=lambda x: x["date"], reverse=True)[:20]}
    rule = [x for x in plays if not x["legacy"]]
    rcl = [x["clv"] for x in rule if x["clv"] is not None]
    provisional = len(rule) < C.PROVISIONAL_N or not rcl or float(np.mean(rcl)) <= 0
    return {"picks": {k: rec(v) for k, v in picks_all.items()},
            "picks_by_league": {lg: {k: rec([x for x in v if x[2] == lg]) for k, v in picks_all.items()} for lg in C.LEAGUES},
            "plays": rec2(plays), "plays_list": sorted(plays, key=lambda x: x["date"], reverse=True)[:80],
            "by_type": {k: rec2([x for x in plays if x["kind"] == k]) for k in ("1x2", "ah", "total")},
            "by_league": by_league, "series": series, "calibration": cal, "clv": clv,
            "rule": {**rec2(rule), "n": len(rule)}, "provisional": provisional, "alt_plays": alt_rec, "alt_parlays": par_rec,
            "_gate_rows": gate_rows}


# ---------------------------------------------------------------------
# main
# ---------------------------------------------------------------------
def main():
    now = datetime.now(timezone.utc)
    today = now.astimezone(ET).date()
    season = C.SEASON or D.season_of(today)
    OUT.mkdir(parents=True, exist_ok=True)
    C.GAME_PAUSED = GT.paused_kinds(GT.load(OUT / "gates.json", GT.game_names("soccer")), "soccer")   # gates.py
    HIST.mkdir(parents=True, exist_ok=True)
    bt = load_json(D.CACHE / "backtest.json", {})

    log.info("history and ratings")
    frames, teams_by, new = BT.load(season)
    ratings, rho = {}, {}
    for lg in C.LEAGUES:
        ratings[lg] = M.fit(frames[lg], today + timedelta(days=1), new[lg], alpha=C.ALPHA)
        rho[lg] = (bt.get(lg) or {}).get("rho", DEFAULT_RHO[lg])

    log.info("fixtures")
    fixtures = []
    for lg in C.LEAGUES:
        fixtures += D.espn_window(lg, today - timedelta(days=3), today + timedelta(days=8))
    upcoming = [f for f in fixtures if f["state"] == "pre" and datetime.fromisoformat(f["start"].replace("Z", "+00:00")) > now]
    log.info(f"{len(upcoming)} upcoming matches")
    odds_status = O.run(upcoming, OUT / "odds_state.json", now)

    log.info("schedules (fatigue)")
    sched = F.live_schedules(frames, upcoming, season)
    fat_coef = load_json(D.CACHE / "fatigue.json", {})

    log.info("player rates")
    rates = {}
    for lg in C.LEAGUES:
        bx = P.recent_boxes(lg, today - timedelta(days=C.PROP_DAYS), today)
        rates[lg] = P.player_rates(bx)

    games, players, alt_rows, conv_errs = [], [], [], []
    cross_in, cross_book = [], None
    for f in sorted(upcoming, key=lambda x: x["start"]):
        lg, R = f["league"], ratings.get(f["league"])
        if R is None:
            continue
        nb = new[lg].get(season, {})
        if f["home"] not in R.teams and f["home"] not in nb:
            log.warning(f"no rating for {f['home']} ({lg})")
        lh, la = R.lambdas(f["home"], f["away"], nb)
        kick = datetime.fromisoformat(f["start"].replace("Z", "+00:00"))
        # fatigue: short rest and midweek cup / European games (effects fitted from history, soccermodel/fatigue.py)
        rh, ra = F.rest(sched, f["home"], season, kick.date()), F.rest(sched, f["away"], season, kick.date())
        fh, fa = F.adjust(fat_coef, rh[0], rh[1], ra[0], ra[1])
        lh, la = lh * fh, la * fa
        # confirmed lineups (about an hour before kickoff): props use the named XI, team attack moves a little
        pr, tm = rates[lg]
        lu, lineups = None, {}
        if (kick - now).total_seconds() / 3600 <= C.LINEUP_HOURS:
            lu = P.lineup(lg, f["event_id"])
        if lu:
            for side in ("home", "away"):
                if f[side] in lu:
                    mult, missing = P.apply_lineup(f[side], lu[f[side]], pr)
                    lineups[side] = {"confirmed": True, "formation": lu[f[side]].get("formation"), "missing": missing, "mult": r(mult, 3)}
                    if side == "home":
                        lh *= mult
                    else:
                        la *= mult
        G = M.grid(lh, la, rho[lg])
        ph, pd_, pa = M.p1x2(G)
        sh = (f.get("book") or {}).get("sharp") or {}
        try:
            mk = MK.from_sharp(sh, rho[lg])
        except Exception as e:  # noqa: BLE001
            log.warning(f"market fit {f['home']} v {f['away']}: {e}")
            mk = None
        gd = datetime.fromisoformat(f["start"].replace("Z", "+00:00")).astimezone(ET).date()
        g = {"game_id": f["event_id"], "league": lg, "date": gd.isoformat(), "start": f["start"], "home": f["home"], "away": f["away"],
             "xg_home": r(lh, 2), "xg_away": r(la, 2), "p_home": r(100 * ph), "p_draw": r(100 * pd_), "p_away": r(100 * pa),
             "book": f.get("book"), "rest": {"home": rh[0], "away": ra[0], "home_mid": rh[1], "away_mid": ra[1]},
             "fatigue": {"home": r(fh, 3), "away": r(fa, 3)}, "lineups": lineups, "lh": r(lh, 4), "la": r(la, 4),
             "mkt": {"lh": r(mk["lh"], 4), "la": r(mk["la"], 4), "err": r(100 * mk["err"], 2), "p_home": r(100 * mk["p_home"]),
                     "p_draw": r(100 * mk["p_draw"]), "p_away": r(100 * mk["p_away"])} if mk else None,
             "ah_main": {"line": sh["ah_home"], "home": fmt_odds(sh["ah_home_odds"]), "away": fmt_odds(sh["ah_away_odds"]),
                         "nv_home": r(100 * nv(sh["ah_home_odds"], sh["ah_away_odds"])[0]), "book": sh.get("book")}
                        if sh.get("ah_home") is not None and sh.get("ah_home_odds") and sh.get("ah_away_odds") else None,
             "form": {"home": form(frames[lg], f["home"], kick.date()), "away": form(frames[lg], f["away"], kick.date())},
             "scores": sorted(({"s": f"{i}-{j}", "p": r(100 * float(G[i, j]))} for i in range(6) for j in range(6)), key=lambda x: -x["p"])[:6]}
        g["picks"] = picks({**g, "book": f.get("book")}, G, mk)
        try:                                             # more markets: BTTS, draw no bet, alt lines, team totals (altlines.py)
            ab = f.get("alt_book") or {}
            if ab.get("book"):
                rws = AL.evaluate(ab["book"], ab.get("sharp"), AL.Dist.from_grid(G), AL.Dist.from_grid(mk["G"]) if mk else None)
                for x in rws:
                    x.update({"game_id": f["event_id"], "label": AL.label(x, f["home"], f["away"]), "book": ab.get("book_name"), "date": gd.isoformat()})
                alt_rows += rws
                g["alt"] = {"book": ab.get("book_name"), "markets": ab.get("markets"), "n": len(rws), "plays": [],
                            "rows": sorted(rws, key=lambda x: -(x["ev"] if x["ev"] is not None else -99))[:12]}
                conv_errs.extend(AL.conv_check(ab.get("sharp"), AL.Dist.from_grid(mk["G"]) if mk else None))
            g["alt_parlay"] = alt_parlay(g, G, mk)
            cl_ = cross_legs(g, G, mk)
            if cl_:
                cross_in.append({"game_id": f["event_id"], "slate": g["date"], "start": g["start"], "matchup": f"{f['home']} vs {f['away']}",
                                 "league": f["league"], "legs": cl_, "book_rows": ab.get("book")})
                cross_book = cross_book or ab.get("book_name")
        except Exception as e:  # noqa: BLE001
            log.warning(f"more markets skipped for {f['home']} v {f['away']}: {e}")
        games.append(g)
        for side, lam, opp in (("home", lh, f["away"]), ("away", la, f["home"])):
            for p in P.match_props(f[side], lam, pr, tm, f["event_id"], opp):
                p["league"] = lg
                players.append(p)
        for r_ in pr.values():                                   # lineup overrides belong to this match only
            r_.pop("lu", None)
    limit_plays(games)
    chosen, per_day, keep_ids = AL.best_plays(alt_rows), {}, set()
    for x in sorted(chosen, key=lambda x: -x["ev"]):
        if per_day.get(x["date"], 0) < C.ALT_DAILY_CAP:
            per_day[x["date"]] = per_day.get(x["date"], 0) + 1
            keep_ids.add(id(x))
    for x in alt_rows:
        x["eligible"], x["play"] = x["play"], id(x) in keep_ids
    for g in games:
        if g.get("alt"):
            g["alt"]["plays"] = [x for x in alt_rows if x["game_id"] == g["game_id"] and x["play"]]
            g["alt"]["rows"] = sorted(g["alt"]["plays"] + [x for x in g["alt"]["rows"] if not x["play"]],
                                      key=lambda x: (not x["play"], -(x["ev"] if x["ev"] is not None else -99)))[:12]
    odds_status["alt_check"] = {"n": len(conv_errs), "mae": r(float(np.mean(np.abs(conv_errs))), 2) if conv_errs else None,
                                "bias": r(float(np.mean(conv_errs)), 2) if conv_errs else None}
    log.info(f"more markets: {len(alt_rows)} priced, {len(keep_ids)} plays, conversion check {odds_status['alt_check']}")

    # history: today's view of each match, so results can be graded later
    by_day = {}
    for g in games:
        by_day.setdefault(g["date"], {"games": [], "players": []})["games"].append(g)
    gdate = {g["game_id"]: g["date"] for g in games}
    for p in players:
        lite = {k: p[k] for k in ("pid", "name", "team", "game_id", "league")}
        lite["m"] = {"goal": {"pf1": p["m"]["goal"]["ge"][1]}, "sot": {"pf1": p["m"]["sot"]["ge"][1], "pf2": p["m"]["sot"]["ge"][2]}}
        by_day[gdate[p["game_id"]]]["players"].append(lite)
    for day, v in by_day.items():
        path = HIST / f"{day}.json"
        old = load_json(path, {"date": day, "games": [], "players": []})
        live = {g["game_id"] for g in v["games"]}
        for g in v["games"]:                                    # alt parlays lock within PARLAY_LOCK_HOURS of kickoff (Oct 31 2026),
            pv = next((o for o in old["games"] if o["game_id"] == g["game_id"]), None) or {}   # so the graded ticket is the one shown
            if (pv.get("alt_parlay") or {}).get("locked_at"):
                g["alt_parlay"] = pv["alt_parlay"]
            elif g.get("alt_parlay"):
                try:
                    to_ko = (datetime.fromisoformat(g["start"].replace("Z", "+00:00")) - now).total_seconds() / 3600
                except (KeyError, ValueError):
                    to_ko = 99
                if to_ko <= C.PARLAY_LOCK_HOURS:
                    g["alt_parlay"] = dict(g["alt_parlay"], locked_at=now.isoformat(timespec="minutes"))
        keep = [{k: g.get(k) for k in ("game_id", "league", "date", "start", "home", "away", "picks", "book", "p_home", "p_draw", "p_away",
                                       "xg_home", "xg_away", "alt_parlay")} for g in v["games"]]
        stamp = now.isoformat(timespec="minutes")
        for x in keep:                                          # first price seen, for closing-line value later
            prev = next((o for o in old["games"] if o["game_id"] == x["game_id"]), None) or {}
            x["open_book"] = prev.get("open_book") or x.get("book")
            # plays are locked the first time they are flagged: graded at that price, CLV measured from it
            flags = dict(prev.get("flags") or {})
            if "flags" not in prev:                            # older files: their posted plays count as flagged
                for k, pk in (prev.get("picks") or {}).items():
                    if pk.get("play") and pk.get("odds"):
                        flags[k] = {x_: pk.get(x_) for x_ in ("side", "who", "line", "odds", "model", "book", "edge")}
                        flags[k].update({"at": None, "legacy": True})
            for k, pk in x["picks"].items():
                if pk.get("play") and k not in flags:
                    flags[k] = {x_: pk.get(x_) for x_ in ("side", "who", "line", "odds", "model", "book", "sharp", "edge", "ev")}
                    flags[k]["at"] = stamp
            x["flags"] = flags
            x["shadow_flags"] = GT.shadow_flags(x["picks"], prev.get("shadow_flags"), stamp,
                                                ("side", "who", "line", "odds", "model", "book", "sharp", "edge", "ev"))
            alt_flags = dict(prev.get("alt_flags") or {})     # more-markets plays: locked at first flag too
            live_g = next((g for g in v["games"] if g["game_id"] == x["game_id"]), {})
            for a_ in (live_g.get("alt") or {}).get("plays", []):
                k_ = f"{a_['market']}|{a_.get('team')}|{a_['side']}|{a_['line']}"
                if k_ not in alt_flags:
                    alt_flags[k_] = {f_: a_.get(f_) for f_ in ("market", "team", "side", "line", "odds", "model", "sharp", "exact", "ev", "label", "book")}
                    alt_flags[k_]["at"] = stamp
            x["alt_flags"] = alt_flags
        path.write_text(json.dumps(clean({"date": day, "games": [g for g in old["games"] if g["game_id"] not in live] + keep,
                                          "players": [p for p in old["players"] if p["game_id"] not in live] + v["players"]}),
                                   separators=(",", ":")))

    flagged = {}
    for day in by_day:
        for x in load_json(HIST / f"{day}.json", {}).get("games", []):
            flagged[x["game_id"]] = x.get("flags") or {}
    for g in games:
        g["flags"] = flagged.get(g["game_id"], {})

    # results and grading
    days = [d for d in (load_json(p, {}) for p in sorted(HIST.glob("*.json"))) if d]
    results = load_json(OUT / "results.json", {})
    for f in fixtures:
        if f["completed"] and f["hg"] is not None:
            results[f["event_id"]] = {"hg": f["hg"], "ag": f["ag"], "league": f["league"]}
    need = {str(g["game_id"]) for d in days for g in d.get("games", []) if str(g["game_id"]) not in results}
    if need:                                                    # older matches that fell out of the fixture window
        for d in days:
            dd = date.fromisoformat(d["date"])
            if dd >= today or not any(str(g["game_id"]) in need for g in d.get("games", [])):
                continue
            for lg in C.LEAGUES:
                for f in D.espn_window(lg, dd - timedelta(days=1), dd + timedelta(days=1)):
                    if f["completed"] and f["hg"] is not None:
                        results[f["event_id"]] = {"hg": f["hg"], "ag": f["ag"], "league": f["league"]}
    boxes = {}
    for d in days:
        for g in d.get("games", []):
            gid = str(g["game_id"])
            if gid in results:
                bx = D.espn_box(g["league"], gid)
                if bx and bx.get("final"):
                    boxes[gid] = {str(p["pid"]): {"goals": p["goals"], "sot": p["sot"]} for p in bx["players"]}
                    results[gid]["p"] = {str(p["pid"]): [p["goals"], p["sot"]] for p in bx["players"]}   # grades "My bets" props
    (OUT / "results.json").write_text(json.dumps(results, separators=(",", ":")))
    try:                                                        # cross-game alt parlays: one leg from each of 3 matches
        cross = XG.run(OUT / "cross_parlays.json", cross_in, {k: (v["hg"], v["ag"]) for k, v in results.items() if v.get("hg") is not None},
                       now, lambda now_, first: (first - now_).total_seconds() <= C.PARLAY_LOCK_HOURS * 3600, cross_book, log)
    except Exception as e:  # noqa: BLE001
        cross = None
        log.warning(f"cross-game parlays skipped: {e}")
    track = tracking(days, results, boxes)
    gate_rows = track.pop("_gate_rows", {})
    gst = GT.load(OUT / "gates.json", GT.game_names("soccer"))
    track["gates"] = [GT.update(OUT / "gates.json", gst, k, sh, pl, today.isoformat()) for k, (sh, pl) in gate_rows.items()]

    # recently finished matches, for the results strip
    recent = sorted([{"league": f["league"], "home": f["home"], "away": f["away"], "hg": f["hg"], "ag": f["ag"], "start": f["start"],
                      "game_id": f["event_id"]} for f in fixtures if f["completed"] and f["hg"] is not None], key=lambda x: x["start"], reverse=True)

    team_rows = []
    for lg, R in ratings.items():
        if R is None:
            continue
        nb = new[lg].get(season, {})
        cur = teams_by.get((lg, season), set())
        tab = R.table(nb)
        for t in sorted(cur):
            if t not in tab and t not in nb:
                continue
            v = tab.get(t) or R.table(nb).get(t)
            if v is None:
                continue
            team_rows.append({"league": lg, "team": t, "att": r(v["att"], 2), "def": r(v["def"], 2), "net": r(v["att"] - v["def"], 2),
                              "new": nb.get(t)})

    payload = {"generated_at": now.isoformat(), "season": season, "today": today.isoformat(),
               "leagues": {k: {"name": v["name"], "short": v["short"], "xg": bool(v["understat"])} for k, v in C.LEAGUES.items()},
               "games": games, "players": players, "recent": recent[:30], "odds": odds_status, "tracking": track,
               "teams": team_rows, "backtest": bt, "cross_parlays": cross,
               "model": {lg: {"home": r(ratings[lg].home, 3) if ratings[lg] else None, "rho": rho[lg],
                              "base": r(math.exp(ratings[lg].intercept), 2) if ratings[lg] else None} for lg in C.LEAGUES},
               "alt_rules": {"min_ev": AL.SHARP_MIN_EV, "max_ev": AL.SHARP_MAX_EV, "converted_extra": AL.ALT_CONVERTED_EXTRA, "daily_cap": C.ALT_DAILY_CAP},
               "rules": {"sharp_min_ev": C.SHARP_MIN_EV, "sharp_max_ev": C.SHARP_MAX_EV, "model_agree": C.MODEL_AGREE,
                         "daily_cap": C.DAILY_CAP, "provisional_n": C.PROVISIONAL_N, "fatigue": fat_coef}}
    (OUT / "latest.json").write_text(json.dumps(clean(payload), separators=(",", ":")))
    log.info(f"wrote {len(games)} matches, {len(players)} players")


if __name__ == "__main__":
    main()
