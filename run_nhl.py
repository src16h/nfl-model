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
    # plays: blend the model with the book, then demand a real profit at the posted price
    lim = {"ml": C.ML_PLAY_EDGE, "pl": C.PL_PLAY_EDGE, "total": C.TOTAL_PLAY_EDGE}
    for k, v in out.items():
        if v["edge"] is None or not v.get("odds"):
            v["play"] = False
            continue
        p = BR.adjust_game(v["model"] / 100, v["book"] / 100)
        ev, need = BR.game_ev(p, int(v["odds"]))
        v["adj"], v["ev"] = r(100 * p), r(ev)
        blocked = ((k == "pl" and int(v["odds"]) > 0 and "pl_dog" in C.BLOCKED)      # puck-line long shots lost every time
                   or (k == "total" and "totals" in C.BLOCKED))                   # totals: lean only until proven
        v["play"] = bool(lim[k] <= v["edge"] <= C.PLAY_MAX_EDGE and ev >= need and not blocked)
    ml, pl = out.get("ml"), out.get("pl")
    if ml and pl and ml["play"] and pl["play"] and ml["side"] == pl["side"]:   # same team twice: keep the bigger gap
        (pl if ml["edge"] >= pl["edge"] else ml)["play"] = False
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
    plays, prop_plays, calib, alts, daily, edges = [], [], {}, [], {}, []
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
                if pk.get("play"):
                    c, e, exact = CLV.play_clv("nhl", k, pk, g, g.get("open_book"))
                    plays.append({"date": dt, "kind": k, "pick": pick_text(k, pk), "game": f"{g['away']} at {g['home']}",
                                  "odds": pk.get("odds"), "edge": pk.get("edge"), "res": rr, "units": u,
                                  "clv": None if c is None else r(c, 1)})
                    clv_rows.append({"kind": k, "clv": c, "ev": e, "exact": exact})
                    daily[dt] = daily.get(dt, 0) + (u or 0)
                    daily_t["game"][dt] = daily_t["game"].get(dt, 0) + (u or 0)
            ap = g.get("alt_parlay")
            if ap:
                hits = []
                for L in ap["legs"]:
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
                bk = m.get("book")
                if bk and bk.get("play"):
                    L = bk["line"]
                    rr = "P" if v == L else ("W" if (v > L) == (bk["side"] == "Over") else "L")
                    u = payout(bk["odds"]) if rr == "W" else (-1.0 if rr == "L" else 0.0)
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
    by_prop = {}
    for x in prop_plays:
        by_prop.setdefault(f'{x["stat"]}|{x["side"]}', []).append(x)
    by_prop = {k: rec2(v) for k, v in sorted(by_prop.items())}
    return {"picks": {k: rec(v) for k, v in picks.items()},
            "plays": rec2(plays), "plays_list": sorted(plays, key=lambda x: x["date"], reverse=True)[:60],
            "clv": CLV.summary(clv_rows),
            "prop_plays": rec2(prop_plays), "prop_plays_list": sorted(prop_plays, key=lambda x: x["date"], reverse=True)[:80],
            "calibration": cal,
            "alt": alt_rec([a for a in alts if a["v"] >= 3]),
            "alt_hr": alt_rec([a for a in alts if a["v"] == 2]),
            "alt_old": alt_rec([a for a in alts if a["v"] < 2]),
            "edge": {**rec2(edges), "model": r(np.mean([e["p"] for e in edges])) if edges else None,
                     "recent": sorted(edges, key=lambda x: x["date"], reverse=True)[:20]},
            "series": series, "series_by": series_by,
            "by_type": {"game": by_kind, "prop": by_prop}}


def prop_bias(hist_dir, results):
    """How each prop stat has run against the book in graded games (fades in with sample size),
    and how much of the final edge over the book has really shown up (calibration, betrules.realization_table)."""
    rows, real = [], []
    for f in sorted(Path(hist_dir).glob("*.json")):
        day = load_json(f, {})
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
                rows.append((stat, bo, v > bk["line"]))
                fo = BR.final_over_from(bk)
                if fo is not None and bk.get("book_over") is not None:
                    real.append((stat, fo, bk["book_over"] / 100, v > bk["line"]))
    return BR.bias_table(rows), BR.realization_table(real)


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
        game["alt_parlay"] = P.alt_parlay(arrs, info, game, bp)
        games.append(game)
        log.info(f"{a}@{h}: xG {lam[1]:.2f}-{lam[0]:.2f}, home win {game['win_home']}%, goalies {goalies[a]['name']} / {goalies[h]['name']}")

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
                                 C.BLOCKED, 100 * C.PROP_PLAY_MAX, real=real)
            if not dec:
                continue
            b.update({"model_over_raw": b["model_over"], "model_over": r(adj_over), "side": dec["side"], "edge": dec["raw_edge"],
                      "adj": dec["p"], "ev": dec["ev"], "odds": dec["odds"], "play": dec["play"],
                       "pre": dec["pre"], "k": dec["k"]})
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
                             **({"book": {x: m["book"].get(x) for x in ("line", "side", "odds", "edge", "play", "book_over", "ev", "pre", "k")}} if m.get("book") else {})}
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
        keep = []
        for g in v["games"]:
            lite = {k: g[k] for k in ("game_id", "date", "start", "home", "away", "picks", "alt_parlay", "win_home", "book", "goalies")}
            prev = next((x for x in old["games"] if x["game_id"] == g["game_id"]), None)
            lite["open_book"] = (prev or {}).get("open_book") or g.get("book")
            lite["play_at"] = g["play_at"] = CLV.snapshot(g.get("picks"), (prev or {}).get("play_at"), now.isoformat(timespec="minutes"))
            for k_, pk_ in (g.get("picks") or {}).items():         # live plays: price change since flagged (site shows "bet soon")
                if pk_ and pk_.get("play"):
                    pk_["move"] = CLV.moving("nhl", k_, pk_, g, g["play_at"].get(k_))
            keep.append(lite)
        # edge parlays: keep any ticket with a game already under way (locked), refresh the rest
        locked = [e for e in old.get("edge", []) if any(l["game_id"] not in live for l in e["legs"])]
        taken = {(l["pid"], l["stat"]) for e in locked for l in e["legs"]}
        fresh = [e for e in edge_new.get(day, []) if not ({(l["pid"], l["stat"]) for l in e["legs"]} & taken)]
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

    # finished/locked games from today's file so the slate stays complete
    payload = {"generated_at": now.isoformat(), "season": season, "today": today.isoformat(),
               "games": games, "players": players, "odds": odds_status, "tracking": track, "prop_level": level,
               "edge_parlays": edge_final,
               "model": {"coefs": model.coefs(), "eng": eng, "eng_check": eng_info, "ot_goal_share": r(model.ot_goal_share, 3),
                         "league": {k: r(v, 2) for k, v in lg.items()}, "train_games": int(len(rows) / 2),
                         "backtest": BACKTEST},
               "teams": [{"team": t, **{k: r(v, 2) for k, v in f.items() if k not in ("last",)}, **{k: r(v, 2) for k, v in tpow[t].items()}}
                         for t, f in sorted(form.items()) if t in tpow],          # teams with a game this season (drops moved franchises)
               "rules": {"ml": C.ML_PLAY_EDGE, "pl": C.PL_PLAY_EDGE, "total": C.TOTAL_PLAY_EDGE, "max": C.PLAY_MAX_EDGE,
                         "prop": [100 * C.PROP_PLAY_MIN, 100 * C.PROP_PLAY_MAX], **BR.summary(), "bias": bias, "calibration": real,
                         "blocked": sorted(" ".join(x) if isinstance(x, tuple) else x for x in C.BLOCKED)}}
    (OUT / "latest.json").write_text(json.dumps(clean(payload), separators=(",", ":")))
    log.info(f"wrote {len(games)} games, {len(players)} players")


# walk-forward check, refreshed by hand (python -m nhlmodel.backtest); shown on the Record tab
BACKTEST = {"seasons": "2023-24 to 2025-26", "win_logloss": 0.668, "base_logloss": 0.689,
            "note": "Puck-line and overtime rates land within about 1 to 3 points of real results each season. Totals were recalibrated Oct 18 2026 (scoring catch-up, linked home/away goals, shot-volume effect): this season the model has 45.0% of games over 6.5 vs 44.6% real. Totals show a lean but are not plays until about 150 graded totals show an edge."}

if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        log.exception("NHL run failed")
        sys.exit(1)
