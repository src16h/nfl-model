"""
Daily NBA model run (Oct 30 2026), built the same way as the NHL model.

  python run_nba.py          writes docs/nba/data/latest.json (+ history, results)

Steps: add last night's finished games to the history (ESPN box scores), fit team ratings, read the
injury report, find today's and tomorrow's games, simulate each game and its players, price spreads,
totals, moneylines, player props, alt lines and alt-line parlays, then grade everything already played.
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

from nbamodel import config as C
from nbamodel import data as D
from nbamodel import gamemodel as G
from nbamodel import odds as O
from nbamodel import props as P
from nbamodel import ratings as R
from nbamodel.util import clean, norm_name, r

sys.path.insert(0, str(Path(__file__).resolve().parent))
import betrules as BR  # noqa: E402
import clv as CLV  # noqa: E402
import altlines as AL  # noqa: E402
import gates as GT  # noqa: E402
import crossgame as XG  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("nbamodel")
ROOT = Path(__file__).resolve().parent
OUT = ROOT / "docs" / "nba" / "data"
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
    """Moneyline, spread, total. Edge = model chance minus the book's no-vig chance."""
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
    # spread
    sph = b.get("spread")
    if sph is not None and b.get("spread_home_odds") and b.get("spread_away_odds"):
        dec_ = d + sph != 0
        ph = float((d[dec_] + sph > 0).mean())
        bh = no_vig(b["spread_home_odds"], b["spread_away_odds"])
        eh, ea = ph - bh, (1 - ph) - (1 - bh)
        home = eh >= ea
        out["spread"] = {"side": g["home"] if home else g["away"], "line": sph if home else -sph,
                         "odds": fmt_odds(b["spread_home_odds"] if home else b["spread_away_odds"]),
                         "model": r(100 * (ph if home else 1 - ph)), "book": r(100 * (bh if home else 1 - bh)),
                         "edge": r(100 * (eh if home else ea))}
    else:
        line = -(np.floor(float(np.median(d))) + 0.5)          # the model's own number, as a home handicap
        ph = float((d + line > 0).mean())
        side, line, p = (g["home"], line, ph) if ph >= 0.5 else (g["away"], -line, 1 - ph)
        out["spread"] = {"side": side, "line": float(line), "odds": None, "model": r(100 * p), "book": None, "edge": None,
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
        L = float(np.floor(np.median(t)) + 0.5)
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
        elif k == "spread":
            home = v["side"] == g["home"]
            mine, other = (b["spread_home_odds"], b["spread_away_odds"]) if home else (b["spread_away_odds"], b["spread_home_odds"])
            same = sh.get("spread") is not None and b.get("spread") is not None and abs(sh["spread"] - b["spread"]) < 1e-9
            s1, s2 = ((sh.get("spread_home_odds"), sh.get("spread_away_odds")) if home else (sh.get("spread_away_odds"), sh.get("spread_home_odds"))) if same else (None, None)
        else:
            over = v["side"] == "Over"
            mine, other = (b["over_odds"], b["under_odds"]) if over else (b["under_odds"], b["over_odds"])
            same = sh.get("total") is not None and abs(sh["total"] - b["total"]) < 1e-9
            s1, s2 = ((sh.get("over_odds"), sh.get("under_odds")) if over else (sh.get("under_odds"), sh.get("over_odds"))) if same else (None, None)
        dec = BR.decide_sharp(v["model"] / 100, mine, other, s1, s2)
        v["sharp"], v["ev"], v["play"] = dec["sharp"], dec["ev"], dec["play"]
    GT.hold_back(out, getattr(C, "GAME_PAUSED", set()))   # paused bet types (gates.py) become shadow picks
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


def build_results(games_df, pg, ids):
    """Final scores and player stats for every finished game we predicted."""
    out = {}
    ids = {str(x) for x in ids}
    gt = games_df[games_df["game_id"].astype(str).isin(ids) & games_df["hs"].notna()]
    pl = pg[pg["game_id"].astype(str).isin(ids)]
    by = {str(gid): x for gid, x in pl.groupby("game_id")}
    for g in gt.to_dict("records"):
        st = {}
        for p in by.get(str(g["game_id"]), pd.DataFrame()).to_dict("records"):
            if p.get("dnp") or not p.get("min"):
                continue
            st[str(p["pid"])] = [int(p["pts"]), int(p["reb"]), int(p["ast"]), int(p["fg3m"] or 0)]
        out[str(g["game_id"])] = {"h": int(g["hs"]), "a": int(g["as"]), "p": st}
    return out


SIDX = {"pts": 0, "reb": 1, "ast": 2, "fg3m": 3}


def statv(st, stat):
    return st[0] + st[1] + st[2] if stat == "pra" else st[SIDX[stat]]


def grade_pick(kind, pk, g, res):
    """Returns (result, units) for one pick. units None when no book price."""
    h, a = res["h"], res["a"]
    side_home = pk["side"] == g["home"]
    if kind == "ml":
        win = (h > a) == side_home
        rr = "W" if win else "L"
    elif kind == "spread":
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
    picks = {k: [] for k in ("ml", "spread", "total")}
    plays, prop_plays, calib, alts, daily, edges, alt_plays = [], [], {}, [], {}, [], []
    gate_rows = {"nba_edge": ([], [])}       # (shadow, real) graded rows for gates.py
    gate_rows.update({GT.game_gate("nba", k): ([], []) for k in GT.GAME_KINDS["nba"]})
    gate_rows.update({k: ([], []) for k in GT.prop_names("nba")})
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
                    c, e = CLV.measure(fl["odds"], CLV.close("nba", k, fl, g, g.get("book"), fl.get("line")))
                else:                                            # older plays: from the first line seen (bet early vs wait)
                    c, e, _ = CLV.play_clv("nba", k, fl, g, g.get("open_book"))
                plays.append({"date": dt, "kind": k, "pick": pick_text(k, fl), "game": f"{g['away']} at {g['home']}",
                              "odds": fl.get("odds"), "edge": fl.get("ev", fl.get("edge")), "res": rr, "units": u,
                              "clv": None if c is None else r(c, 1), "legacy": bool(fl.get("legacy"))})
                clv_rows.append({"kind": k, "clv": c, "ev": e, "exact": bool(fl.get("at"))})
                if k in GT.GAME_KINDS["nba"]:
                    gate_rows[GT.game_gate("nba", k)][1].append({"date": dt, "res": rr, "units": u, "clv": c, "ev": e})
                daily[dt] = daily.get(dt, 0) + (u or 0)
                daily_t["game"][dt] = daily_t["game"].get(dt, 0) + (u or 0)
            for k, fl in (g.get("shadow_flags") or {}).items():     # paused bet types: graded, not counted as plays
                if not fl.get("odds") or fl.get("side") is None or (k != "ml" and fl.get("line") is None):
                    continue
                rr, u = grade_pick(k, fl, g, res)
                c, e = CLV.measure(fl["odds"], CLV.close("nba", k, fl, g, g.get("book"), fl.get("line")))
                if k in GT.GAME_KINDS["nba"]:
                    gate_rows[GT.game_gate("nba", k)][0].append({"date": dt, "res": rr, "units": u, "clv": c, "ev": e})
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
                    v = statv(st, L["stat"])
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
                v = statv(st, L["stat"])
                rr = "P" if v == L["line"] else ("W" if (v > L["line"]) == (L["side"] == "Over") else "L")
                rs.append(rr)
                if rr == "W":
                    dec *= 1 + payout(L["odds"])
            if None in rs:
                continue
            res_e = "L" if "L" in rs else ("W" if "W" in rs else "P")
            u = (dec - 1) if res_e == "W" else (-1.0 if res_e == "L" else 0.0)
            gate_rows["nba_edge"][0 if e.get("paused") else 1].append({"date": dt, "res": res_e, "units": u, "p": e["p"]})
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
                v = statv(st, stat)
                c = calib.setdefault(stat, [])
                c.append((m["pf"], v > m["fair"]))
                sf = m.get("shadow_flag")
                if sf and sf.get("line") is not None and sf.get("odds") is not None:
                    L = sf["line"]
                    rr = "P" if v == L else ("W" if (v > L) == (sf["side"] == "Over") else "L")
                    spc, spe, _ = CLV.prop_clv(sf, m.get("close")) if sf.get("at") else (None, None, None)
                    gate_rows.setdefault(sf.get("gate") or GT.prop_gate("nba", stat, sf["side"]), ([], []))[0].append(
                        {"date": dt, "res": rr, "units": payout(sf["odds"]) if rr == "W" else (-1.0 if rr == "L" else 0.0),
                         "clv": spc, "ev": spe})
                bk = m.get("flag") if "flag" in m else (m.get("book") if (m.get("book") or {}).get("play") else None)
                if bk and bk.get("line") is not None and bk.get("odds") is not None:
                    L = bk["line"]
                    rr = "P" if v == L else ("W" if (v > L) == (bk["side"] == "Over") else "L")
                    u = payout(bk["odds"]) if rr == "W" else (-1.0 if rr == "L" else 0.0)
                    pc, pe, pmv = CLV.prop_clv(bk, m.get("close")) if bk.get("at") else (None, None, None)
                    gk = GT.prop_gate("nba", stat, bk["side"])
                    if gk in GT.GATES:
                        gate_rows.setdefault(gk, ([], []))[1].append({"date": dt, "res": rr, "units": u, "clv": pc, "ev": pe})
                    prop_plays.append({"date": dt, "player": p["name"], "pick": f"{bk['side']} {L:g} {stat}", "odds": fmt_odds(bk["odds"]),
                                       "edge": bk["edge"], "res": rr, "units": u, "actual": v,
                                       "stat": stat, "side": bk["side"], "clv": None if pc is None else r(pc, 1), "ev": pe, "move": pmv})
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
    by_kind = {k: rec2([x for x in plays if x["kind"] == k]) for k in ("ml", "spread", "total")}
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
            "prop_clv": CLV.prop_summary(prop_plays),
            "calibration": cal,
            "alt": alt_rec([a for a in alts if a["v"] in (3, 4)]),
            "alt_mix": alt_rec([a for a in alts if a["v"] == 5]),
            "alt_hr": alt_rec([a for a in alts if a["v"] == 2]),
            "alt_old": alt_rec([a for a in alts if a["v"] < 2]),
            "edge": {**rec2(edges), "model": r(np.mean([e["p"] for e in edges])) if edges else None,
                     "recent": sorted(edges, key=lambda x: x["date"], reverse=True)[:20]},
            "series": series, "series_by": series_by, "_gate_rows": gate_rows,
            "by_type": {"game": by_kind, "prop": by_prop}}


def lock_parlays(g, prev, players, now):
    """Same-game parlay tickets are locked the first time they're posted for the evening (Oct 30 2026). Before,
    every run rebuilt them and only the last version was graded: on Oct 29 the four versions hit 3, 5, 4 and 6 of
    11, and the record showed 6. A locked ticket only changes if one of its players drops out of the lineup."""
    ts = now.isoformat(timespec="minutes")
    try:
        to_start = (datetime.fromisoformat(g["start"].replace("Z", "+00:00")) - now).total_seconds() / 3600
    except (KeyError, ValueError):
        to_start = 99
    evening = now.astimezone(ET).hour >= C.PARLAY_LOCK_HOUR or to_start <= 3
    dressed = {p["pid"] for p in players if p.get("game_id") == g["game_id"]}
    for key in ("alt_parlay", "alt_mix"):
        old = (prev or {}).get(key)
        if old and old.get("locked_at"):
            gone = [L.get("name") for L in old.get("legs", []) if L.get("pid") is not None and L["pid"] not in dressed]
            if not gone:
                g[key] = old                                   # keep the ticket you were shown
                continue
            if g.get(key):                                     # a leg's player is out: post a new ticket, say why
                g[key] = dict(g[key], locked_at=ts, replaced=f"replaced {old['locked_at'][11:16]} ticket: {', '.join(gone)} out")
            continue
        if g.get(key) and evening:
            g[key] = dict(g[key], locked_at=ts)


def cap_props(players, games=None):
    """Same-direction props move together (a high-event night lifts every Over, a slow one every Under), so many
    of them in one game, or one night, is one big bet. Oct 19: 38 points Unders, -13u. Oct 29: 33 shots Unders
    (6 in one game), 11-21, -11.4u, after the model leaned Under on 171 of 183 shots props.
    Keep the best by expected return: C.PROP_CAP_GAME per stat and side in each game, C.PROP_CAP_NIGHT per stat
    and side each night, and C.PROP_CAP_ONEWAY a night when the model leans one way on most of a stat's props."""
    gdate = {g["game_id"]: g.get("date") for g in (games or [])}
    def cap_out(bs, n):
        for b in sorted(bs, key=lambda x: -(x.get("ev") or 0))[n:]:
            b["play"] = False
            b["capped"] = True
    plays, leans = {}, {}
    for p in players:
        for stat, m in p["m"].items():
            b = m.get("book")
            if not b or not b.get("side"):
                continue
            day = gdate.get(p["game_id"])
            leans.setdefault((day, stat), []).append(b["side"])
            if b.get("play"):
                plays.setdefault((day, stat, b["side"]), {}).setdefault(p["game_id"], []).append(b)
    for (day, stat, side), by_game in plays.items():
        cap_g = C.PROP_CAP_PER_GAME.get((stat, side), C.PROP_CAP_GAME)
        for bs in by_game.values():
            cap_out(bs, cap_g)
        alive = [b for bs in by_game.values() for b in bs if b.get("play")]
        ls = leans.get((day, stat), [])
        oneway = len(ls) >= 20 and sum(x == side for x in ls) / len(ls) >= C.PROP_ONEWAY_SHARE
        cap_out(alive, C.PROP_CAP_ONEWAY if oneway else C.PROP_CAP_NIGHT)


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
                v = statv(st, stat)
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
    if k == "spread":
        return f"{pk['side']} {pk['line']:+g}"
    return f"{pk['side']} {pk['line']:g}"


# ---------------------------------------------------------------------
# main
# ---------------------------------------------------------------------
def espn_lines(o):
    """ESPN's DraftKings lines in the same shape as the Odds API book record."""
    if not o:
        return None
    num = lambda x: None if x in (None, "", "OFF") else float(str(x).lstrip("ou").replace("+", ""))
    try:
        ml, ps, tt = o.get("moneyline") or {}, o.get("pointSpread") or {}, o.get("total") or {}
        g = lambda d, side, k: ((d.get(side) or {}).get("close") or (d.get(side) or {}).get("open") or {}).get(k)
        rec = {"ml_home": num(g(ml, "home", "odds")), "ml_away": num(g(ml, "away", "odds")),
               "spread": num(g(ps, "home", "line")), "spread_home_odds": num(g(ps, "home", "odds")),
               "spread_away_odds": num(g(ps, "away", "odds")),
               "total": num(g(tt, "over", "line")), "over_odds": num(g(tt, "over", "odds")), "under_odds": num(g(tt, "under", "odds")),
               "book": ((o.get("provider") or {}).get("name") or "DraftKings") + " (ESPN)", "src": "ESPN"}
        if rec["spread"] is None and o.get("spread") is not None:
            rec["spread"] = float(o["spread"]) * (-1 if (o.get("homeTeamOdds") or {}).get("favorite") else 1)
        if rec["total"] is None and o.get("overUnder") is not None:
            rec["total"] = float(o["overUnder"])
        return {k: v for k, v in rec.items() if v is not None}
    except (TypeError, ValueError):
        return None


def main():
    now = datetime.now(timezone.utc)
    import os
    if os.environ.get("NOW"):
        now = datetime.fromisoformat(os.environ["NOW"]).astimezone(timezone.utc)
    now_ts = pd.Timestamp(now)
    today = now.astimezone(ET).date()
    season = C.SEASON or season_of(today)
    OUT.mkdir(parents=True, exist_ok=True)
    HIST.mkdir(parents=True, exist_ok=True)
    # paused bet types (gates.py)
    gst = GT.load(OUT / "gates.json", ("nba_edge",) + GT.game_names("nba") + GT.prop_names("nba"))
    C.GAME_PAUSED = GT.paused_kinds(gst, "nba")
    C.PROP_PAUSED = GT.paused_props(gst, "nba")
    C.EDGE_PAUSED = not GT.active(gst, "nba_edge")
    log.info(f"gates: {({k: v['status'] for k, v in gst.items() if v['status'] != 'active'})} paused")

    # history: last few nights' finished games (ESPN box scores) into data/nba
    games_df, pg = D.update(today - timedelta(days=4), today)
    games_df = games_df[games_df["hs"].notna()].copy()
    form_rows = R.player_form(pg, games_df[games_df["season"] >= season - 1])
    loss_hist = R.lineup_loss(form_rows)
    tf = R.team_frame(games_df[games_df["season"] >= season - 1], loss_hist)
    rt = R.fit(tf, now_ts, season, C.ADJ)
    injuries = D.injuries()
    tbl, team_avg = P.player_table(pg, games_df, now_ts)
    last_game = {}
    for g_ in games_df.itertuples():
        for t in (g_.home, g_.away):
            last_game[t] = max(last_game.get(t, ""), str(g_.date))
    log.info(f"ratings: league {rt['league']:.1f}, home court {rt['hca']:.2f}; injuries for {len(injuries)} teams")

    sched = []
    for d_ in (today, today + timedelta(days=1)):
        try:
            sched += D.scoreboard(d_)
        except Exception as e:  # noqa: BLE001
            log.warning(f"scoreboard {d_} not read: {e}")
    for g in sched:
        g["game_id"] = g["event"]
        g["date_et"] = datetime.fromisoformat(g["start"].replace("Z", "+00:00")).astimezone(ET).date().isoformat()
        g["today_et"] = today.isoformat()
        g["espn"] = espn_lines(g.get("odds"))
    upcoming = [g for g in sched if g["state"] == "pre" and datetime.fromisoformat(g["start"].replace("Z", "+00:00")) > now]
    log.info(f"{len(upcoming)} upcoming games")
    close_games = set()
    for p_ in load_json(HIST / f"{today.isoformat()}.json", {}).get("players", []):
        if any((m_.get("flag") or {}).get("at") for m_ in (p_.get("m") or {}).values()):
            close_games.add(p_["game_id"])
    book_props, odds_status = O.run(upcoming, OUT / "odds_state.json", OUT / "props_cache.json", now, close_games=close_games)
    book_alt = O.alt_lines(load_json(OUT / "props_cache.json", {}))
    alt_rows, conv_errs = [], []
    cross_in, cross_book = [], None
    games, players = [], []
    for i, g in enumerate(upcoming):
        h, a = g["home"], g["away"]
        if h not in R.TI or a not in R.TI:
            continue
        gd = datetime.fromisoformat(g["start"].replace("Z", "+00:00")).astimezone(ET).date()
        rest = {t: (gd - date.fromisoformat(last_game[t])).days if t in last_game else 3 for t in (h, a)}
        lineups, loss = {}, {}
        for t in (h, a):
            lg_ = pd.Timestamp(last_game[t], tz="UTC") if t in last_game else None
            lineups[t] = P.roster(tbl, t, now_ts, injuries, lg_)
            loss[t] = sum((1 - p["avail"]) * p["exp_min"] * max(p.get("val_pm", C.VAL_REPL) - C.VAL_REPL, 0.0)
                          for p in lineups[t] if p["exp_min"] >= C.ROT_MIN)
        feat = {"b2b_h": float(rest[h] == 1), "b2b_a": float(rest[a] == 1), "loss_h": loss[h], "loss_a": loss[a]}
        adj_h, adj_a = R.adj_pts(feat, C.ADJ)
        ph, pa = R.predict(rt, h, a, adj_h, adj_a, g.get("neutral", False))
        rng = np.random.default_rng(1000 + i)
        sim = G.simulate(ph, pa, rng)
        d = sim["FH"] - sim["FA"]
        t_ = sim["FH"] + sim["FA"]
        inj_out = {t: [{"name": p["name"], "status": p["status"], "min": r(p["exp_min"])} for p in lineups[t] if p["avail"] < 1]
                   for t in (h, a)}
        game = {"game_id": g["game_id"], "date": g["date_et"], "start": g["start"], "home": h, "away": a,
                "home_name": g.get("home_name"), "away_name": g.get("away_name"),
                "pts_home": r(ph), "pts_away": r(pa), "margin": r(ph - pa), "total_mean": r(ph + pa),
                "win_home": r(100 * float((d > 0).mean())), "ot": r(100 * float((sim["OT"] > 0).mean())),
                "rest_home": rest[h], "rest_away": rest[a], "loss_home": r(loss[h], 1), "loss_away": r(loss[a], 1),
                "injuries": inj_out,
                "book": {k: v for k, v in (g.get("book") or {}).items() if k != "event"}}
        game["fair_ml_home"] = fmt_odds(american(float((d > 0).mean())))
        game["fair_spread_home"] = r(-(ph - pa), 1)
        game["picks"] = game_picks(game, sim)
        # alt lines and team totals: the sims re-weighted to Pinnacle's spread and total (altlines.py)
        ba = book_alt.get(str(g["game_id"]), {})
        mdl, mkt, mkt_err = AL.Dist(sim["FH"], sim["FA"]), None, None
        try:
            sh = (game.get("book") or {}).get("sharp") or {}
            tg = []
            if sh.get("spread") is not None and sh.get("spread_home_odds") and sh.get("spread_away_odds"):
                tg.append(({"market": "spread", "team": "home", "side": "home", "line": float(sh["spread"])},
                           AL.nv(sh["spread_home_odds"], sh["spread_away_odds"])))
            if sh.get("total") is not None and sh.get("over_odds") and sh.get("under_odds"):
                tg.append(({"market": "total", "team": None, "side": "over", "line": float(sh["total"])}, AL.nv(sh["over_odds"], sh["under_odds"])))
            for k_, sides in AL.pairs([x for x in ba.get("sharp", []) if x["market"] == "team_total"]).items():
                if "over" in sides and "under" in sides:
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
        info, arrs = {}, {}
        for t, side in ((h, "H"), (a, "A")):
            for p in lineups[t]:
                info[p["pid"]] = p
            arrs.update(P.team_players(sim, side, lineups[t], team_avg.get(t), rng))
        bp = book_props.get(str(g["game_id"]), {})
        prows = P.summarize(arrs, info, bp)
        for p in prows:
            p["game_id"] = g["game_id"]
            p["opp"] = a if p["team"] == h else h
        players += prows
        team_legs = AL.team_legs(mdl, mkt, h, a, C.ALT_LEG_SPEC, C.ALT_LEG_RANGE_TEAM) if mkt is not None else []
        try:
            game["alt_parlay"] = P.alt_parlay(arrs, info, game, bp)
            game["alt_mix"] = P.alt_parlay(arrs, info, game, bp, team_legs, need_team=True) if team_legs else None
        except Exception as e:  # noqa: BLE001
            log.warning(f"alt parlay skipped for {a}@{h}: {e}")
        if team_legs:
            cross_in.append({"game_id": g["game_id"], "slate": game["date"], "start": g["start"], "matchup": f"{a} at {h}",
                             "legs": team_legs, "book_rows": ba.get("book")})
            cross_book = cross_book or ba.get("book_name")
        games.append(game)
        log.info(f"{a}@{h}: {pa:.1f}-{ph:.1f}, home win {game['win_home']}%, out: {[x['name'] for x in inj_out[a] + inj_out[h]][:6]}")

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
            if dec["play"] and (st, dec["side"]) in getattr(C, "PROP_PAUSED", set()):   # paused prop type (gates.py): shadow
                b["play"], b["shadow"] = False, GT.prop_gate("nba", st, dec["side"])
    cap_props(players, games)
    edge_new = edge_parlays(players, games)
    level = {k: r(v, 3) for k, v in level.items()}
    log.info(f"prop level vs book (model minus book, over %): {level}")

    # history: one file per day, games locked at tip-off
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
                             **({"book": {x: m["book"].get(x) for x in ("line", "side", "odds", "edge", "play", "book_over", "ev", "pre", "k", "shadow", "pulled")}} if m.get("book") else {})}
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
                    fl = {x: bk.get(x) for x in ("line", "side", "odds", "book_over", "edge", "ev", "pre", "pulled")}
                    fl["at"] = now.isoformat(timespec="minutes")
                m["flag"] = fl
                m["close"] = CLV.close_snap(bk, pm.get("close"), now.isoformat(timespec="minutes"))   # latest pre-game line
                sf = pm.get("shadow_flag")                         # shadow plays (gates.py): locked the same way
                if sf is None and bk.get("shadow") and not bk.get("play"):
                    sf = {x: bk.get(x) for x in ("line", "side", "odds", "edge", "ev", "book_over", "pulled")}
                    sf.update({"at": now.isoformat(timespec="minutes"), "gate": bk["shadow"]})
                if sf:
                    m["shadow_flag"] = sf
        keep = []
        for g in v["games"]:
            lock_parlays(g, next((x for x in old["games"] if x["game_id"] == g["game_id"]), None), players, now)
            lite = {k: g.get(k) for k in ("game_id", "date", "start", "home", "away", "picks", "alt_parlay", "alt_mix", "win_home", "book", "injuries")}
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
                    pk_["move"] = CLV.moving("nba", k_, pk_, g, g["play_at"].get(k_))
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
            lite["shadow_flags"] = g["shadow_flags"] = GT.shadow_flags(
                g.get("picks"), (prev or {}).get("shadow_flags"), now.isoformat(timespec="minutes"),
                ("side", "line", "odds", "model", "book", "sharp", "ev", "edge"))
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
    results = build_results(games_df, pg, ids)
    try:
        lock_x = lambda now_, first: (first - now_).total_seconds() <= 3 * 3600 or (
            first.astimezone(ET).date() == now_.astimezone(ET).date() and now_.astimezone(ET).hour >= C.PARLAY_LOCK_HOUR)
        cross = XG.run(OUT / "cross_parlays.json", cross_in, {k: (v["h"], v["a"]) for k, v in results.items()}, now, lock_x,
                       cross_book, log)
    except Exception as e:  # noqa: BLE001
        cross = None
        log.warning(f"cross-game parlays skipped: {e}")
    (OUT / "results.json").write_text(json.dumps(clean(results), separators=(",", ":")))
    track = tracking(days, results)
    gate_rows = track.pop("_gate_rows", {})
    gst = GT.load(OUT / "gates.json", ("nba_edge",) + GT.game_names("nba") + GT.prop_names("nba"))
    gates_out = [GT.update(OUT / "gates.json", gst, k, sh, pl, today.isoformat()) for k, (sh, pl) in gate_rows.items()]

    payload = {"generated_at": now.isoformat(), "season": season, "today": today.isoformat(),
               "games": games, "players": players, "odds": odds_status, "tracking": track, "prop_level": level,
               "edge_parlays": edge_final, "cross_parlays": cross, "edge_paused": bool(getattr(C, "EDGE_PAUSED", False)), "gates": gates_out,
               "model": {"league": r(rt["league"], 2), "hca": r(rt["hca"], 2), "adjust": C.ADJ, "backtest": load_backtest(),
                         "margin_sd": C.MARGIN_SD, "total_sd": C.TOTAL_SD, "train_games": int(len(tf))},
               "teams": team_table(rt, games_df, season),
               "alt_rules": {"min_ev": AL.SHARP_MIN_EV, "max_ev": AL.SHARP_MAX_EV, "converted_extra": AL.ALT_CONVERTED_EXTRA,
                             "daily_cap": C.ALT_DAILY_CAP},
               "rules": {"prop": [100 * C.PROP_PLAY_MIN, 100 * C.PROP_PLAY_MAX], **BR.summary(), "bias": bias, "calibration": real,
                         "blocked": sorted(" ".join(x) if isinstance(x, tuple) else x for x in C.BLOCKED)}}
    (OUT / "latest.json").write_text(json.dumps(clean(payload), separators=(",", ":")))
    log.info(f"wrote {len(games)} games, {len(players)} players")


def team_table(rt, games_df, season):
    """Ratings per team plus this season's record and points."""
    rows = []
    gs = games_df[(games_df["season"] == season) & (games_df["type"] == "reg")]
    for t in R.TEAMS:
        i = R.TI[t]
        hg, ag = gs[gs["home"] == t], gs[gs["away"] == t]
        w = int((hg["hs"] > hg["as"]).sum() + (ag["as"] > ag["hs"]).sum())
        n = len(hg) + len(ag)
        pf = float(hg["hs"].sum() + ag["as"].sum()) / n if n else None
        pa = float(hg["as"].sum() + ag["hs"].sum()) / n if n else None
        rows.append({"team": t, "off": r(rt["off"][i], 2), "def": r(-rt["def"][i], 2), "net": r(rt["off"][i] - rt["def"][i], 2),
                     "w": w, "l": n - w, "pf": r(pf), "pa": r(pa)})
    return sorted(rows, key=lambda x: -x["net"])


def load_backtest():
    bt = load_json(OUT / "backtest.json", {})
    return bt or None


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        log.exception("NBA run failed")
        sys.exit(1)
