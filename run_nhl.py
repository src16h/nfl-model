"""
Daily NHL model run.

  python run_nhl.py          writes docs/nhl/data/latest.json (+ history, results)

Steps: team form from MoneyPuck, fit the goal and shot models on every game
since 2012, find today's games and starting goalies, simulate each game,
price game lines and player props, build alt-line parlays, then grade
everything already played.
"""
import itertools
import json
import logging
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from nhlmodel import config as C
from nhlmodel import data as D
from nhlmodel import gamemodel as G
from nhlmodel import odds as O
from nhlmodel import pbp as B
from nhlmodel import props as P
from nhlmodel import ratings as R
from nhlmodel.util import clean, norm_name, r

sys.path.insert(0, str(Path(__file__).resolve().parent))
import betrules as BR  # noqa: E402
import clv as CLV  # noqa: E402
import altlines as AL  # noqa: E402
import gates as GT  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("nhlmodel")
ROOT = Path(__file__).resolve().parent
OUT = ROOT / "docs" / "nhl" / "data"
HIST = OUT / "history"
ET = ZoneInfo("America/New_York")


def season_of(d: date):
    return d.year if d.month >= 8 else d.year - 1


def no_vig(a, b):
    return O.no_vig(a, b) if a and b else None


def american(p):
    if not p or p <= 0 or p >= 1:
        return None
    return round(-100 * p / (1 - p)) if p >= 0.5 else round(100 * (1 - p) / p)


def payout(odds):
    o = float(odds)
    return o / 100 if o > 0 else 100 / -o


def fmt_odds(o):
    if o is None:
        return None
    o = int(round(float(o)))
    return f"+{o}" if o > 0 else str(o)


# ---------------------------------------------------------------------
# game lines: picks and plays
# ---------------------------------------------------------------------
def game_picks(g, sim):
    """Moneyline, puck line, total. Edge = model chance minus the book's no-vig chance."""
    b = g.get("book") or {}
    d, t = sim["FH"] - sim["FA"], sim["FH"] + sim["FA"]
    pw = float((d > 0).mean())
    out = {}
    # moneyline
    if b.get("ml_home") and b.get("ml_away"):
        bh = no_vig(b["ml_home"], b["ml_away"])
        eh, ea = pw - bh, (1 - pw) - (1 - bh)
        home = eh >= ea
        out["ml"] = {"side": g["home"] if home else g["away"], "odds": fmt_odds(b["ml_home"] if home else b["ml_away"]),
                     "model": r(100 * (pw if home else 1 - pw)), "book": r(100 * (bh if home else 1 - bh)),
                     "edge": r(100 * (eh if home else ea))}
    else:
        home = pw >= 0.5
        out["ml"] = {"side": g["home"] if home else g["away"], "odds": None, "model": r(100 * (pw if home else 1 - pw)),
                     "book": None, "edge": None, "fair": fmt_odds(american(pw if home else 1 - pw))}
    # puck line
    plh = b.get("pl_home")
    if plh is not None and b.get("pl_home_odds") and b.get("pl_away_odds"):
        ph = float((d + plh > 0).mean())
        bh = no_vig(b["pl_home_odds"], b["pl_away_odds"])
        eh, ea = ph - bh, (1 - ph) - (1 - bh)
        home = eh >= ea
        out["pl"] = {"side": g["home"] if home else g["away"], "line": plh if home else -plh,
                     "odds": fmt_odds(b["pl_home_odds"] if home else b["pl_away_odds"]),
                     "model": r(100 * (ph if home else 1 - ph)), "book": r(100 * (bh if home else 1 - bh)),
                     "edge": r(100 * (eh if home else ea))}
    else:
        line = -1.5 if pw >= 0.5 else 1.5                     # the usual puck line: favorite -1.5
        ph = float((d + line > 0).mean())
        side, line, p = (g["home"], line, ph) if ph >= 0.5 else (g["away"], -line, 1 - ph)
        out["pl"] = {"side": side, "line": line, "odds": None, "model": r(100 * p), "book": None, "edge": None,
                     "fair": fmt_odds(american(p))}
    # total
    L = b.get("total")
    if L is not None and b.get("over_odds") and b.get("under_odds"):
        dec = t != L
        po = float((t[dec] > L).mean())
        bo = no_vig(b["over_odds"], b["under_odds"])
        over = po - bo >= (1 - po) - (1 - bo)
        out["total"] = {"side": "Over" if over else "Under", "line": L, "odds": fmt_odds(b["over_odds"] if over else b["under_odds"]),
                        "model": r(100 * (po if over else 1 - po)), "book": r(100 * (bo if over else 1 - bo)),
                        "edge": r(100 * ((po - bo) if over else (bo - po)))}
    else:
        L = 6.5 if t.mean() >= 6.0 else 5.5
        po = float((t > L).mean())
        out["total"] = {"side": "Over" if po >= 0.5 else "Under", "line": L, "odds": None,
                        "model": r(100 * max(po, 1 - po)), "book": None, "edge": None, "fair": fmt_odds(american(max(po, 1 - po)))}
    # plays (Oct 20 2026): Pinnacle's fair price must call the bet price value at the same line, and the model
    # must agree. Checked on 85 graded games: blending the model into the line made it less accurate at every
    # weight, and the model's side on every game went 36-49 (-17%). betrules.decide_sharp.
    sh = b.get("sharp") or {}
    for k, v in out.items():
        if v["edge"] is None or not v.get("odds"):
            v["play"] = False
            continue
        if k == "ml":
            home = v["side"] == g["home"]
            mine, other = (b["ml_home"], b["ml_away"]) if home else (b["ml_away"], b["ml_home"])
            s1, s2 = ((sh.get("ml_home"), sh.get("ml_away")) if home else (sh.get("ml_away"), sh.get("ml_home")))
        elif k == "pl":
            home = v["side"] == g["home"]
            mine, other = (b["pl_home_odds"], b["pl_away_odds"]) if home else (b["pl_away_odds"], b["pl_home_odds"])
            same = sh.get("pl_home") is not None and b.get("pl_home") is not None and abs(sh["pl_home"] - b["pl_home"]) < 1e-9
            s1, s2 = ((sh.get("pl_home_odds"), sh.get("pl_away_odds")) if home else (sh.get("pl_away_odds"), sh.get("pl_home_odds"))) if same else (None, None)
        else:
            over = v["side"] == "Over"
            mine, other = (b["over_odds"], b["under_odds"]) if over else (b["under_odds"], b["over_odds"])
            same = sh.get("total") is not None and abs(sh["total"] - b["total"]) < 1e-9
            s1, s2 = ((sh.get("over_odds"), sh.get("under_odds")) if over else (sh.get("under_odds"), sh.get("over_odds"))) if same else (None, None)
        dec = BR.decide_sharp(v["model"] / 100, mine, other, s1, s2)
        v["sharp"], v["ev"], v["play"] = dec["sharp"], dec["ev"], dec["play"]
    ml, pl = out.get("ml"), out.get("pl")
    plays = [x for x in out.values() if x.get("play")]
    if len(plays) > 1:                                  # one play per game: the best value
        best = max(plays, key=lambda x: x.get("ev") or 0)
        for x in plays:
            x["play"] = x is best
    return out


# ---------------------------------------------------------------------
# results and grading
# ---------------------------------------------------------------------
def load_json(p, default):
    try:
        return json.loads(Path(p).read_text())
    except Exception:  # noqa: BLE001
        return default


def build_results(games_t, pg, ids):
    """Final scores and player stats for every finished game we predicted."""
    out = {}
    gt = games_t[games_t["game_id"].isin(ids)]
    pl = pg[pg["game_id"].isin(ids)]
    by = {gid: x for gid, x in pl.groupby("game_id")}
    for g in gt.to_dict("records"):
        st = {}
        for p in by.get(g["game_id"], pd.DataFrame()).to_dict("records"):
            st[str(p["pid"])] = [int(p["saves"])] if p["pos"] == "G" else [int(p["sog"]), int(p["goals"]), int(p["assists"]), int(p["goals"] + p["assists"])]
        out[str(g["game_id"])] = {"h": int(g["hs"]), "a": int(g["as"]), "end": g["end"], "p": st}
    return out


def grade_pick(kind, pk, g, res):
    """Returns (result, units) for one pick. units None when no book price."""
    h, a = res["h"], res["a"]
    side_home = pk["side"] == g["home"]
    if kind == "ml":
        win = (h > a) == side_home
        rr = "W" if win else "L"
    elif kind == "pl":
        m = (h - a) if side_home else (a - h)
        v = m + pk["line"]
        rr = "P" if v == 0 else ("W" if v > 0 else "L")
    else:
        v = (h + a) - pk["line"]
        rr = "P" if v == 0 else ("W" if (v > 0) == (pk["side"] == "Over") else "L")
    if not pk.get("odds"):
        return rr, None
    return rr, (payout(pk["odds"]) if rr == "W" else (-1.0 if rr == "L" else 0.0))


def edge_parlays(players, games):
    """Cross-game parlays from the day's prop plays: the best pairs by expected return at the book's
    prices, each play used once. Legs come from different games, so they are priced as unrelated."""
    gdate = {g["game_id"]: g["date"] for g in games}
    gname = {g["game_id"]: f"{g['away']} at {g['home']}" for g in games}
    legs = []
    for p in players:
        for st, m in p["m"].items():
            b = m.get("book")
            if b and b.get("play") and b.get("odds") is not None and b.get("adj") is not None:
                legs.append({"pid": p["pid"], "name": p["name"], "team": p["team"], "game_id": p["game_id"],
                             "game": gname.get(p["game_id"], ""), "date": gdate.get(p["game_id"]), "stat": st,
                             "side": b["side"], "line": b["line"], "odds": b["odds"], "p": b["adj"]})
    out = {}
    for day in sorted({l["date"] for l in legs if l["date"]}):
        pool = [l for l in legs if l["date"] == day]
        combos = []
        for combo in itertools.combinations(pool, C.EDGE_LEGS):
            if len({l["game_id"] for l in combo}) < C.EDGE_LEGS:
                continue
            pj = float(np.prod([l["p"] / 100 for l in combo]))
            dec = float(np.prod([1 + payout(l["odds"]) for l in combo]))
            ev = 100 * (pj * dec - 1)
            if ev >= C.EDGE_MIN_EV:
                combos.append((ev, combo, pj, dec))
        combos.sort(key=lambda t: -t[2])                 # every ticket clears the edge bar; most likely to hit first
        used, picks = set(), []
        for ev, combo, pj, dec in combos:
            keys = {(l["pid"], l["stat"]) for l in combo}
            if keys & used:
                continue
            used |= keys
            picks.append({"p": r(100 * pj), "ev": r(ev), "odds": fmt_odds(dec_to_american(dec)), "fair": P.american(pj),
                          "legs": [dict(l) for l in combo]})
            if len(picks) >= C.EDGE_MAX_PER_DAY:
                break
        out[day] = picks
    return out


def dec_to_american(dec):
    return round(100 * (dec - 1)) if dec >= 2 else round(-100 / (dec - 1))


def tracking(history_days, results):
    picks = {k: [] for k in ("ml", "pl", "total")}
    plays, prop_plays, calib, alts, daily, edges, alt_plays = [], [], {}, [], {}, [], []
    gate_rows = {"nhl_points": ([], []), "nhl_edge": ([], [])}       # (shadow, real) graded rows for gates.py
    clv_rows = []
    daily_t = {"game": {}, "prop": {}, "edge": {}}       # units per day by bet type (Home record chart)
    for day in history_days:
        dt = day["date"]
        for g in day.get("games", []):
            res = results.get(str(g["game_id"]))
            if not res:
                continue
            for k, pk in (g.get("picks") or {}).items():
                rr, u = grade_pick(k, pk, g, res)
                picks[k].append((rr, u, pk.get("edge")))
            flags = g.get("flags")
            if flags is None:                                    # saved before flags: the plays as last saved
                flags = {k: pk for k, pk in (g.get("picks") or {}).items() if pk and pk.get("play")}
            for k, fl in flags.items():
                if not fl.get("odds") or fl.get("side") is None:
                    continue
                if k != "ml" and fl.get("line") is None:
                    continue
                rr, u = grade_pick(k, fl, g, res)
                if fl.get("at"):                                 # locked when flagged: CLV from that price
                    c, e = CLV.measure(fl["odds"], CLV.close("nhl", k, fl, g, g.get("book"), fl.get("line")))
                else:                                            # older plays: from the first line seen (bet early vs wait)
                    c, e, _ = CLV.play_clv("nhl", k, fl, g, g.get("open_book"))
                plays.append({"date": dt, "kind": k, "pick": pick_text(k, fl), "game": f"{g['away']} at {g['home']}",
                              "odds": fl.get("odds"), "edge": fl.get("ev", fl.get("edge")), "res": rr, "units": u,
                              "clv": None if c is None else r(c, 1), "legacy": bool(fl.get("legacy"))})
                clv_rows.append({"kind": k, "clv": c, "ev": e, "exact": bool(fl.get("at"))})
                daily[dt] = daily.get(dt, 0) + (u or 0)
                daily_t["game"][dt] = daily_t["game"].get(dt, 0) + (u or 0)
            for fl in (g.get("alt_flags") or {}).values():
                rr, u = AL.grade(fl, res["h"], res["a"])
                alt_plays.append({"date": dt, "kind": "alt", "market": fl["market"], "pick": fl.get("label"), "game": f"{g['away']} at {g['home']}",
                                  "odds": fl.get("odds"), "edge": fl.get("ev"), "res": rr, "units": u or 0.0, "exact": fl.get("exact")})
                daily[dt] = daily.get(dt, 0) + (u or 0)
                daily_t["game"][dt] = daily_t["game"].get(dt, 0) + (u or 0)
            for ap in (g.get("alt_parlay"), g.get("alt_mix")):
                if not ap:
                    continue
                hits = []
                for L in ap["legs"]:
                    if L.get("kind") == "team":
                        hits.append(AL.grade(L, res["h"], res["a"])[0] == "W")
                        continue
                    st = res["p"].get(str(L["pid"]))
                    if st is None:
                        hits.append(None)
                        continue
                    v = st[0] if L["stat"] == "saves" else st[{"sog": 0, "goals": 1, "assists": 2, "points": 3}[L["stat"]]]
                    hits.append(v > L["line"])
                if None not in hits:
                    alts.append({"date": dt, "game": f"{g['away']} at {g['home']}", "hit": all(hits), "legs_hit": sum(hits),
                                 "legs": len(hits), "p": ap["p"], "v": ap.get("v", 1), "fair": ap.get("fair")})
        for e in day.get("edge", []):
            rs, dec = [], 1.0
            for L in e["legs"]:
                res = results.get(str(L["game_id"]))
                st = res and res["p"].get(str(L["pid"]))
                if not st:
                    rs.append(None)
                    continue
                v = st[0] if L["stat"] == "saves" else st[{"sog": 0, "goals": 1, "assists": 2, "points": 3}[L["stat"]]]
                rr = "P" if v == L["line"] else ("W" if (v > L["line"]) == (L["side"] == "Over") else "L")
                rs.append(rr)
                if rr == "W":
                    dec *= 1 + payout(L["odds"])
            if None in rs:
                continue
            res_e = "L" if "L" in rs else ("W" if "W" in rs else "P")
            u = (dec - 1) if res_e == "W" else (-1.0 if res_e == "L" else 0.0)
            gate_rows["nhl_edge"][0 if e.get("paused") else 1].append({"date": dt, "res": res_e, "units": u, "p": e["p"]})
            if e.get("paused"):
                continue                                     # paused tickets: graded for the gate, not counted as plays
            edges.append({"date": dt, "res": res_e, "units": u, "p": e["p"], "odds": e["odds"],
                          "legs": " + ".join(f"{L['name']} {L['side']} {L['line']:g} {L['stat']}" for L in e["legs"]),
                          "legs_hit": sum(x == "W" for x in rs), "n": len(rs)})
            daily[dt] = daily.get(dt, 0) + u
            daily_t["edge"][dt] = daily_t["edge"].get(dt, 0) + u
        for p in day.get("players", []):
            res = results.get(str(p["game_id"]))
            if not res:
                continue
            st = res["p"].get(str(p["pid"]))
            if st is None:
                continue
            for stat, m in p["m"].items():
                v = st[0] if stat == "saves" else st[{"sog": 0, "goals": 1, "assists": 2, "points": 3}[stat]]
                c = calib.setdefault(stat, [])
                c.append((m["pf"], v > m["fair"]))
                sf = m.get("shadow_flag")
                if sf and sf.get("line") is not None and sf.get("odds") is not None:
                    L = sf["line"]
                    rr = "P" if v == L else ("W" if (v > L) == (sf["side"] == "Over") else "L")
                    gate_rows.setdefault(sf.get("gate") or "nhl_points", ([], []))[0].append(
                        {"date": dt, "res": rr, "units": payout(sf["odds"]) if rr == "W" else (-1.0 if rr == "L" else 0.0)})
                bk = m.get("flag") if "flag" in m else (m.get("book") if (m.get("book") or {}).get("play") else None)
                if bk and bk.get("line") is not None and bk.get("odds") is not None:
                    L = bk["line"]
                    rr = "P" if v == L else ("W" if (v > L) == (bk["side"] == "Over") else "L")
                    u = payout(bk["odds"]) if rr == "W" else (-1.0 if rr == "L" else 0.0)
                    if stat == "points":
                        gate_rows["nhl_points"][1].append({"date": dt, "res": rr, "units": u})
                    prop_plays.append({"date": dt, "player": p["name"], "pick": f"{bk['side']} {L:g} {stat}", "odds": fmt_odds(bk["odds"]),
                                       "edge": bk["edge"], "res": rr, "units": u, "actual": v,
                                       "stat": stat, "side": bk["side"]})
                    daily[dt] = daily.get(dt, 0) + u
                    daily_t["prop"][dt] = daily_t["prop"].get(dt, 0) + u

    def rec(rows):
        w = sum(1 for x in rows if x[0] == "W"); l = sum(1 for x in rows if x[0] == "L")
        us = [x[1] for x in rows if x[1] is not None]
        return {"w": w, "l": l, "pct": r(100 * w / (w + l)) if w + l else None, "units": r(sum(us), 2) if us else None}

    def rec2(rows):
        w = sum(1 for x in rows if x["res"] == "W"); l = sum(1 for x in rows if x["res"] == "L")
        u = sum(x["units"] or 0 for x in rows)
        return {"w": w, "l": l, "pct": r(100 * w / (w + l)) if w + l else None, "units": r(u, 2),
                "roi": r(100 * u / (w + l)) if w + l else None}
    def alt_rec(rows):
        return {"n": len(rows), "hits": sum(a["hit"] for a in rows),
                "model": r(np.mean([a["p"] for a in rows])) if rows else None,
                "recent": sorted(rows, key=lambda x: x["date"], reverse=True)[:20]}
    cal = {}
    for st, rows in calib.items():
        cal[st] = {"n": len(rows), "model": r(100 * np.mean([x[0] for x in rows])), "actual": r(100 * np.mean([x[1] for x in rows]))}
    series, run = [], 0.0
    for dt in sorted(daily):
        run += daily[dt]
        series.append({"date": dt, "units": r(run, 2)})
    series_by = {}
    for t, dd in daily_t.items():                        # same dates as `series`, so the lines line up
        run_t, out = 0.0, []
        for dt in sorted(daily):
            run_t += dd.get(dt, 0)
            out.append({"date": dt, "units": r(run_t, 2)})
        series_by[t] = out
    # record by bet type: game plays by market, prop plays by stat and side
    by_kind = {k: rec2([x for x in plays if x["kind"] == k]) for k in ("ml", "pl", "total")}
    by_kind["alt"] = rec2(alt_plays)
    by_prop = {}
    for x in prop_plays:
        by_prop.setdefault(f'{x["stat"]}|{x["side"]}', []).append(x)
    by_prop = {k: rec2(v) for k, v in sorted(by_prop.items())}
    return {"picks": {k: rec(v) for k, v in picks.items()},
            "plays": rec2(plays), "plays_list": sorted(plays, key=lambda x: x["date"], reverse=True)[:60],
            "clv": CLV.summary(clv_rows),
            "alt_plays": rec2(alt_plays), "alt_plays_list": sorted(alt_plays, key=lambda x: x["date"], reverse=True)[:60],
            "alt_by_market": {m: rec2([x for x in alt_plays if x["market"] == m]) for m in ("spread", "total", "team_total")},
            "prop_plays": rec2(prop_plays), "prop_plays_list": sorted(prop_plays, key=lambda x: x["date"], reverse=True)[:80],
            "calibration": cal,
            "alt": alt_rec([a for a in alts if a["v"] in (3, 4)]),
            "alt_mix": alt_rec([a for a in alts if a["v"] == 5]),
            "alt_hr": alt_rec([a for a in alts if a["v"] == 2]),
            "alt_old": alt_rec([a for a in alts if a["v"] < 2]),
            "edge": {**rec2(edges), "model": r(np.mean([e["p"] for e in edges])) if edges else None,
                     "recent": sorted(edges, key=lambda x: x["date"], reverse=True)[:20]},
            "series": series, "series_by": series_by, "_gate_rows": gate_rows,
            "by_type": {"game": by_kind, "prop": by_prop}}


def cap_props(players):
    """Keep only the best N plays of a stat and side in each game (C.PROP_CAP_PER_GAME).
    Same-game Unders win and lose together, so 10 of them in one game is one big bet, not 10."""
    for (stat, side), cap in C.PROP_CAP_PER_GAME.items():
        by_game = {}
        for p in players:
            b = p["m"].get(stat, {}).get("book")
            if b and b.get("play") and b.get("side") == side:
                by_game.setdefault(p["game_id"], []).append(b)
        for bs in by_game.values():
            for b in sorted(bs, key=lambda x: -(x.get("ev") or 0))[cap:]:
                b["play"] = False
                b["capped"] = True


def prop_bias(hist_dir, results):
    """How each prop stat has run against the book in graded games (fades in with sample size),
    and how much of the final edge over the book has really shown up (calibration, betrules.realization_table)."""
    rows, real, real_plays = [], [], []
    for f in sorted(Path(hist_dir).glob("*.json")):
        day = load_json(f, {})
        dt = date.fromisoformat(f.stem)
        for p in day.get("players", []):
            res = results.get(str(p["game_id"]))
            st = res and res["p"].get(str(p["pid"]))
            if not st:
                continue
            for stat, m in p["m"].items():
                bk = m.get("book")
                if not bk or bk.get("odds") is None:
                    continue
                v = st[0] if stat == "saves" else st[{"sog": 0, "goals": 1, "assists": 2, "points": 3}[stat]]
                if v == bk["line"]:
                    continue
                bo = bk.get("book_over")
                if bo is not None:
                    bo = bo / 100
                else:       # older files kept only the bet side's price
                    q = BR.no_vig_from_one(bk["odds"])
                    bo = q if bk["side"] == "Over" else 1 - q
                rows.append((stat, bo, v > bk["line"], dt))
                fo = BR.final_over_from(bk)
                if fo is not None and bk.get("book_over") is not None:
                    real.append((stat, fo, bk["book_over"] / 100, v > bk["line"]))
                    if bk.get("play"):
                        real_plays.append((stat, fo, bk["book_over"] / 100, v > bk["line"]))
    last = max((x[3] for x in rows), default=None)          # last graded night
    rows = [(s_, b_, y_, C.PROP_BIAS_DECAY ** (last - d_).days) for s_, b_, y_, d_ in rows]   # recent nights count more
    real_t = BR.realization_table(real)
    # per side, judged on the plays themselves (the biggest leans, the ones actually bet). Never raises an edge.
    for key, v in BR.realization_table(real_plays).items():
        stat = key.split("|")[0]
        if "|" in key and stat in C.PROP_SIDE_K_STATS and v["n"] >= C.PROP_SIDE_K_MIN:
            base = (real_t.get(key) or real_t.get(stat) or {}).get("k", 1.0)
            real_t[key] = {**v, "k": round(min(v["k"], base), 3), "from": "plays"}
    return BR.bias_table(rows), real_t


def pick_text(k, pk):
    if k == "ml":
        return f"{pk['side']} ML"
    if k == "pl":
        return f"{pk['side']} {pk['line']:+g}"
    return f"{pk['side']} {pk['line']:g}"


# ---------------------------------------------------------------------
# main
# ---------------------------------------------------------------------
def main():
    now = datetime.now(timezone.utc)
    today = now.astimezone(ET).date()
    season = C.SEASON or season_of(today)
    season_id = f"{season}{season + 1}"
    OUT.mkdir(parents=True, exist_ok=True)
    HIST.mkdir(parents=True, exist_ok=True)
    # paused bet types (gates.py): a type that has earned its way back is a play again from this run on
    gst = GT.load(OUT / "gates.json", ("nhl_points", "nhl_edge"))
    if GT.active(gst, "nhl_points"):
        C.BLOCKED = (set(C.BLOCKED) - {"points"}) | {("points", "Over")}
        C.ODDS_PROP_MARKETS = list(C.ODDS_PROP_MARKETS) + ["player_points"]
        C.SHADOW_PROP_MARKETS = []
    if GT.active(gst, "nhl_edge"):
        C.EDGE_PAUSED = False
    log.info(f"gates: {({k: v['status'] for k, v in gst.items()})}")

    log.info("play-by-play tables")
    games_t, gg, pg = B.update([season - 1, season], {season - 1, season})
    tg = D.team_games(games_t, C.TRAIN_SINCE)
    tg, league, state = R.pregame(tg)
    rows = G.training_rows(tg)
    model = G.Model().fit(rows)
    eng, eng_info = G.fit_eng(model, rows[rows["season"] >= season - 3])
    form, lg = R.current(state, league, season)
    tpow = model.team_power(form, lg)
    log.info(f"model coefs {model.coefs()}")
    rates, pos = P.skater_rates(pg, season)
    gskill = P.goalie_skill(gg, pg, season)

    sched = D.schedule(today, days=2)
    upcoming = [g for g in sched if g["state"] in ("FUT", "PRE") and
                datetime.fromisoformat(g["start"].replace("Z", "+00:00")) > now]
    for g in sched:
        g["date_et"] = datetime.fromisoformat(g["start"].replace("Z", "+00:00")).astimezone(ET).date().isoformat()
        g["today_et"] = today.isoformat()
    log.info(f"{len(upcoming)} upcoming games")
    book_props, odds_status = O.run(upcoming, OUT / "odds_state.json", OUT / "props_cache.json", now)
    book_alt = O.alt_lines(load_json(OUT / "props_cache.json", {}))
    alt_rows, conv_errs = [], []

    games, players = [], []
    for i, g in enumerate(upcoming):
        h, a = g["home"], g["away"]
        if h not in form or a not in form:
            continue
        gd = datetime.fromisoformat(g["start"].replace("Z", "+00:00")).astimezone(ET).date()

        def rest(t):
            last = form[t]["last"]
            return (pd.Timestamp(gd) - last).days if last is not None else 7

        # projected starting goalies
        goalies = {}
        for t in (h, a):
            pid, status = P.projected_goalie(t, pg, gd, gskill)
            sk = gskill.get(pid, {"ratio": 1.0, "name": "Unknown", "gsax": 0, "gp": 0})
            goalies[t] = {"pid": pid, "name": sk["name"], "status": status, "ratio": r(sk["ratio"], 3),
                          "gsax": r(sk["gsax"]), "gp": sk.get("gp")}
        X = []
        for t, o, home in ((h, a, 1), (a, h, 0)):
            f = G._feats(form[t], form[o], home, lg["xgf"], lg["sogf"], rest(t), rest(o), form[t]["gp"],
                         gk_o=float(np.clip(np.log(goalies[o]["ratio"]), -0.25, 0.25)) + np.log(lg["gfq"] / lg["xgf"]),
                         lg_fin=lg["gfq"] / lg["xgf"])
            f.update({"lg_g": lg["gf"], "lg_sog": lg["sogf"]})
            X.append(f)
        X = pd.DataFrame(X)
        lam, mus = model.predict(X)
        # shots: blend the team model with what tonight's skaters usually shoot (steadier early in a season)
        lineups = {t: P.lineup(t, pg, rates, pos) for t in (h, a)}
        for j, t in enumerate((h, a)):
            ind = sum(p["e_sog"] for p in lineups[t])
            if ind > 0:
                mus[j] = (1 - C.SOG_PLAYER_BLEND) * mus[j] + C.SOG_PLAYER_BLEND * ind
        sim = G.simulate(lam[0], lam[1], mus[0], mus[1], eng=eng, ot_goal_share=model.ot_goal_share, seed=1000 + i, detail=True)
        d = sim["FH"] - sim["FA"]
        game = {"game_id": g["game_id"], "date": g["date_et"], "start": g["start"], "home": h, "away": a,
                "home_name": g["home_name"], "away_name": g["away_name"],
                "xg_home": r(lam[0], 2), "xg_away": r(lam[1], 2), "sog_home": r(mus[0]), "sog_away": r(mus[1]),
                "win_home": r(100 * float((d > 0).mean())), "ot": r(100 * float(sim["tie"].mean())),
                "total_mean": r(float((sim["FH"] + sim["FA"]).mean()), 2),
                "rest_home": rest(h), "rest_away": rest(a), "goalies": goalies,
                "form": {t: {k: r(form[t][k], 2) for k in ("xgf", "xga", "gf", "ga", "sogf", "soga")} for t in (h, a)},
                "book": {k: v for k, v in (g.get("book") or {}).items() if k != "event"}}
        game["fair_ml_home"] = fmt_odds(american(float((d > 0).mean())))
        game["picks"] = game_picks(game, sim)
        # alt lines and team totals: the sims re-weighted to Pinnacle's lines price every alt line (altlines.py)
        ba = book_alt.get(g["game_id"], {})
        mdl, mkt, mkt_err = AL.Dist(sim["FH"], sim["FA"]), None, None
        try:
            sh = (g.get("book") or {}).get("sharp") or {}
            tg = []
            if sh.get("ml_home") and sh.get("ml_away"):
                tg.append(({"market": "spread", "team": "home", "side": "home", "line": 0.0}, AL.nv(sh["ml_home"], sh["ml_away"])))
            if sh.get("pl_home") is not None and sh.get("pl_home_odds") and sh.get("pl_away_odds"):
                tg.append(({"market": "spread", "team": "home", "side": "home", "line": float(sh["pl_home"])}, AL.nv(sh["pl_home_odds"], sh["pl_away_odds"])))
            if sh.get("total") is not None and sh.get("over_odds") and sh.get("under_odds"):
                tg.append(({"market": "total", "team": None, "side": "over", "line": float(sh["total"])}, AL.nv(sh["over_odds"], sh["under_odds"])))
            for k_, sides in AL.pairs([x for x in ba.get("sharp", []) if x["market"] == "team_total"]).items():
                if "over" in sides and "under" in sides:          # Pinnacle's own team totals pin each side's scoring
                    tg.append(({"market": "team_total", "team": k_[1], "side": "over", "line": k_[2]}, AL.nv(sides["over"], sides["under"])))
            if len(tg) >= 2:
                mkt, mkt_err = AL.tilt(mdl, tg)
            game["ladder"] = AL.ladders(mdl, mkt, C.ALT_SPEC)
            game["mkt_err"] = None if mkt_err is None else r(100 * mkt_err, 2)
            if ba.get("book"):
                ev_rows = AL.evaluate(ba["book"], ba.get("sharp"), mdl, mkt)
                for x in ev_rows:
                    x.update({"game_id": g["game_id"], "label": AL.label(x, h, a), "book": ba.get("book_name")})
                alt_rows += ev_rows
                game["alt"] = {"book": ba.get("book_name"), "markets": ba.get("markets"), "n": len(ev_rows),
                               "rows": sorted(ev_rows, key=lambda x: -(x["ev"] if x["ev"] is not None else -99))[:12], "plays": []}
            conv_errs += AL.conv_check(ba.get("sharp"), mkt)
        except Exception as e:  # noqa: BLE001
            log.warning(f"alt lines skipped for {a}@{h}: {e}")
        # players
        rng = np.random.default_rng(77 + i)
        info, arrs = {}, {}
        for t, side in ((h, "H"), (a, "A")):
            sks = lineups[t]
            for p in sks:
                info[p["pid"]] = p
            gk = goalies[t]
            gk_rec = {"pid": gk["pid"], "name": gk["name"], "pos": "G", "team": t} if gk["pid"] else None
            if gk_rec:
                info[gk["pid"]] = gk_rec
            arrs.update(P.team_players(sim, side, sks, gk_rec, rng))
        bp = book_props.get(g["game_id"], {})
        prows = P.summarize(arrs, info, bp)
        for p in prows:
            p["game_id"] = g["game_id"]
            p["opp"] = a if p["team"] == h else h
        players += prows
        team_legs = AL.team_legs(mdl, mkt, h, a, C.ALT_LEG_SPEC, C.ALT_LEG_RANGE) if mkt is not None else []
        game["alt_parlay"] = P.alt_parlay(arrs, info, game, bp)              # players only (the record so far)
        game["alt_mix"] = P.alt_parlay(arrs, info, game, bp, team_legs, need_team=True)   # must include a team leg
        games.append(game)
        log.info(f"{a}@{h}: xG {lam[1]:.2f}-{lam[0]:.2f}, home win {game['win_home']}%, goalies {goalies[a]['name']} / {goalies[h]['name']}")

    # alt-line plays: one per game, best value first, at most ALT_DAILY_CAP a day
    chosen = AL.best_plays(alt_rows)
    by_day_n, keep_ids = {}, set()
    gday = {g["game_id"]: g["date"] for g in games}
    for x in sorted(chosen, key=lambda x: -x["ev"]):
        dd = gday.get(x["game_id"])
        if by_day_n.get(dd, 0) < C.ALT_DAILY_CAP:
            by_day_n[dd] = by_day_n.get(dd, 0) + 1
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
    log.info(f"alt lines: {len(alt_rows)} priced, {len(keep_ids)} plays, conversion check {odds_status['alt_check']}")

    # market level check: if the model sits above or below the book on almost every prop of a stat,
    # that is a level problem (league trend, early-season noise), not 40 separate edges. Remove the
    # slate-wide gap so plays come from players the model rates differently from the rest.
    level = {}
    lg_ = lambda x: np.log(np.clip(x, 0.5, 99.5) / (100 - np.clip(x, 0.5, 99.5)))
    for st in C.PROP_STATS:
        diffs = [lg_(p["m"][st]["book"]["model_over"]) - lg_(p["m"][st]["book"]["book_over"]) for p in players if p["m"].get(st, {}).get("book")]
        if len(diffs) >= 12:
            level[st] = float(np.median(diffs))
    bias, real = prop_bias(HIST, load_json(OUT / "results.json", {}))
    log.info(f"prop bias from graded results: {bias}")
    log.info(f"prop calibration from graded results: {real}")
    for p in players:
        for st, m in p["m"].items():
            b = m.get("book")
            if not b:
                continue
            adj_over = 100 / (1 + np.exp(-(lg_(b["model_over"]) - level.get(st, 0.0))))      # same shift on the log-odds scale
            dec = BR.decide_prop(adj_over / 100, b["book_over"] / 100, b.get("over"), b.get("under"), st, bias,
                                 C.BLOCKED, 100 * C.PROP_PLAY_MAX, real=real, side_k=st in C.PROP_SIDE_K_STATS)
            if not dec:
                continue
            b.update({"model_over_raw": b["model_over"], "model_over": r(adj_over), "side": dec["side"], "edge": dec["raw_edge"],
                      "adj": dec["p"], "ev": dec["ev"], "odds": dec["odds"], "play": dec["play"],
                       "pre": dec["pre"], "k": dec["k"]})
            if not dec["play"] and st == "points" and "points" in C.BLOCKED:     # shadow play while points are paused (gates.py)
                d2 = BR.decide_prop(adj_over / 100, b["book_over"] / 100, b.get("over"), b.get("under"), st, bias,
                                    (set(C.BLOCKED) - {"points"}) | {("points", "Over")}, 100 * C.PROP_PLAY_MAX, real=real,
                                    side_k=st in C.PROP_SIDE_K_STATS)
                if d2 and d2["play"]:
                    b["shadow"] = "nhl_points"
    cap_props(players)
    edge_new = edge_parlays(players, games)
    level = {k: r(v, 3) for k, v in level.items()}
    log.info(f"prop level vs book (model minus book, over %): {level}")

    # history: one file per day, games locked at puck drop
    by_day = {}
    for g in games:
        by_day.setdefault(g["date"], {"games": [], "players": []})["games"].append(g)
    pl_lite = []
    for p in players:
        lite = {k: p[k] for k in ("pid", "name", "team", "game_id")}
        lite["m"] = {}
        for st, m in p["m"].items():
            k = int(m["fair"] + 0.5)
            lite["m"][st] = {"fair": m["fair"], "pf": m["ge"][k] if k < len(m["ge"]) else 0.0,
                             **({"book": {x: m["book"].get(x) for x in ("line", "side", "odds", "edge", "play", "book_over", "ev", "pre", "k", "shadow")}} if m.get("book") else {})}
        pl_lite.append(lite)
    gdate = {g["game_id"]: g["date"] for g in games}
    for p in pl_lite:
        by_day[gdate[p["game_id"]]]["players"].append(p)
    edge_final = {}
    for day, v in by_day.items():
        path = HIST / f"{day}.json"
        old = load_json(path, {"date": day, "games": [], "players": []})
        live = {g["game_id"] for g in v["games"]}
        old_games = [g for g in old["games"] if g["game_id"] not in live]
        old_players = [p for p in old["players"] if p["game_id"] not in live]
        prev_pl = {(p["game_id"], p["pid"]): p for p in old["players"] if p["game_id"] in live}
        for p in v["players"]:                                   # prop plays: locked at first flag
            pv = prev_pl.get((p["game_id"], p["pid"])) or {}
            for st, m in p["m"].items():
                pm = (pv.get("m") or {}).get(st) or {}
                fl = pm.get("flag")
                if fl is None and pv and "flag" not in pm and (pm.get("book") or {}).get("play"):
                    fl = {x: pm["book"].get(x) for x in ("line", "side", "odds", "book_over", "edge")}
                    fl.update({"at": None, "legacy": True})
                bk = m.get("book") or {}
                if fl is None and bk.get("play"):
                    fl = {x: bk.get(x) for x in ("line", "side", "odds", "book_over", "edge", "ev", "pre")}
                    fl["at"] = now.isoformat(timespec="minutes")
                m["flag"] = fl
                sf = pm.get("shadow_flag")                         # shadow plays (gates.py): locked the same way
                if sf is None and bk.get("shadow") and not bk.get("play"):
                    sf = {x: bk.get(x) for x in ("line", "side", "odds", "edge", "ev")}
                    sf.update({"at": now.isoformat(timespec="minutes"), "gate": bk["shadow"]})
                if sf:
                    m["shadow_flag"] = sf
        keep = []
        for g in v["games"]:
            lite = {k: g.get(k) for k in ("game_id", "date", "start", "home", "away", "picks", "alt_parlay", "alt_mix", "win_home", "book", "goalies")}
            alt_flags = dict((prev or {}).get("alt_flags") or {}) if (prev := next((x for x in old["games"] if x["game_id"] == g["game_id"]), None)) else {}
            for x in (g.get("alt") or {}).get("plays", []):        # alt plays are locked the first time they're flagged
                k_ = f"{x['market']}|{x.get('team')}|{x['side']}|{x['line']}"
                if k_ not in alt_flags:
                    alt_flags[k_] = {f_: x.get(f_) for f_ in ("market", "team", "side", "line", "odds", "model", "sharp", "exact", "ev", "label", "book")}
                    alt_flags[k_]["at"] = now.isoformat(timespec="minutes")
            lite["alt_flags"] = g["alt_flags"] = alt_flags
            prev = next((x for x in old["games"] if x["game_id"] == g["game_id"]), None)
            lite["open_book"] = (prev or {}).get("open_book") or g.get("book")
            lite["play_at"] = g["play_at"] = CLV.snapshot(g.get("picks"), (prev or {}).get("play_at"), now.isoformat(timespec="minutes"))
            for k_, pk_ in (g.get("picks") or {}).items():         # live plays: price change since flagged (site shows "bet soon")
                if pk_ and pk_.get("play"):
                    pk_["move"] = CLV.moving("nhl", k_, pk_, g, g["play_at"].get(k_))
            # plays are locked the first time they're flagged (Oct 20 2026): graded at that price, even if they later drop off
            flags = dict((prev or {}).get("flags") or {})
            if prev is not None and "flags" not in prev:            # saved before flags existed: their last plays count
                for k_, pk_ in (prev.get("picks") or {}).items():
                    if pk_ and pk_.get("play"):
                        flags[k_] = {x: pk_.get(x) for x in ("side", "line", "odds", "model", "book", "edge")}
                        flags[k_].update({"at": None, "legacy": True})
                for k_, snap in ((prev or {}).get("play_at") or {}).items():   # flagged earlier but gone by now: still counts
                    if k_ not in flags and snap.get("odds"):
                        flags[k_] = {"side": snap.get("side"), "line": snap.get("line"), "odds": snap.get("odds"), "at": snap.get("ts"),
                                     "legacy": True}
            for k_, pk_ in (g.get("picks") or {}).items():
                if pk_ and pk_.get("play") and k_ not in flags:
                    flags[k_] = {x: pk_.get(x) for x in ("side", "line", "odds", "model", "book", "sharp", "ev", "edge")}
                    flags[k_]["at"] = now.isoformat(timespec="minutes")
            lite["flags"] = g["flags"] = flags
            keep.append(lite)
        # edge parlays: keep any ticket with a game already under way (locked), refresh the rest
        locked = [e for e in old.get("edge", []) if any(l["game_id"] not in live for l in e["legs"])]
        taken = {(l["pid"], l["stat"]) for e in locked for l in e["legs"]}
        fresh = [e for e in edge_new.get(day, []) if not ({(l["pid"], l["stat"]) for l in e["legs"]} & taken)]
        if getattr(C, "EDGE_PAUSED", False):                     # paused: still built and graded, flagged so they don't count as plays
            for e in fresh:
                e["paused"] = True
        edge_final[day] = (locked + fresh)[:max(C.EDGE_MAX_PER_DAY, len(locked))]
        path.write_text(json.dumps(clean({"date": day, "games": old_games + keep, "players": old_players + v["players"],
                                          "edge": edge_final[day]}),
                                   separators=(",", ":")))
    days = [load_json(p, {}) for p in sorted(HIST.glob("*.json"))]
    days = [d for d in days if d]
    ids = {g["game_id"] for d in days for g in d.get("games", [])}
    results = build_results(games_t, pg, ids)
    (OUT / "results.json").write_text(json.dumps(clean(results), separators=(",", ":")))
    track = tracking(days, results)
    gate_rows = track.pop("_gate_rows", {})
    gst = GT.load(OUT / "gates.json", ("nhl_points", "nhl_edge"))
    gates_out = [GT.update(OUT / "gates.json", gst, k, sh, pl, today.isoformat()) for k, (sh, pl) in gate_rows.items()]

    # finished/locked games from today's file so the slate stays complete
    payload = {"generated_at": now.isoformat(), "season": season, "today": today.isoformat(),
               "games": games, "players": players, "odds": odds_status, "tracking": track, "prop_level": level,
               "edge_parlays": edge_final, "edge_paused": bool(getattr(C, "EDGE_PAUSED", False)), "gates": gates_out,
               "model": {"coefs": model.coefs(), "eng": eng, "eng_check": eng_info, "ot_goal_share": r(model.ot_goal_share, 3),
                         "league": {k: r(v, 2) for k, v in lg.items()}, "train_games": int(len(rows) / 2),
                         "backtest": BACKTEST},
               "teams": [{"team": t, **{k: r(v, 2) for k, v in f.items() if k not in ("last",)}, **{k: r(v, 2) for k, v in tpow[t].items()}}
                         for t, f in sorted(form.items()) if t in tpow],          # teams with a game this season (drops moved franchises)
               "alt_rules": {"min_ev": AL.SHARP_MIN_EV, "max_ev": AL.SHARP_MAX_EV, "converted_extra": AL.ALT_CONVERTED_EXTRA,
                             "daily_cap": C.ALT_DAILY_CAP},
               "rules": {"ml": C.ML_PLAY_EDGE, "pl": C.PL_PLAY_EDGE, "total": C.TOTAL_PLAY_EDGE, "max": C.PLAY_MAX_EDGE,
                         "prop": [100 * C.PROP_PLAY_MIN, 100 * C.PROP_PLAY_MAX], **BR.summary(), "bias": bias, "calibration": real,
                         "blocked": sorted(" ".join(x) if isinstance(x, tuple) else x for x in C.BLOCKED)}}
    (OUT / "latest.json").write_text(json.dumps(clean(payload), separators=(",", ":")))
    log.info(f"wrote {len(games)} games, {len(players)} players")


# walk-forward check, refreshed by hand (python -m nhlmodel.backtest); shown on the Record tab
BACKTEST = {"seasons": "2023-24 to 2025-26", "win_logloss": 0.668, "base_logloss": 0.689,
            # vs the market (Oct 20 2026, 85 graded games with book moneylines): book no-vig 0.6338, model 0.6409,
            # 50/50 blend 0.6365. The model is less accurate than the line, which is why plays now need Pinnacle's price.
            "market_logloss": 0.6338, "model_vs_market_logloss": 0.6409,
            "note": "Puck-line and overtime rates land within about 1 to 3 points of real results each season. Totals were recalibrated Oct 18 2026 (scoring catch-up, linked home/away goals, shot-volume effect): this season the model has 45.0% of games over 6.5 vs 44.6% real. Totals show a lean but are not plays until about 150 graded totals show an edge."}

if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        log.exception("NHL run failed")
        sys.exit(1)
