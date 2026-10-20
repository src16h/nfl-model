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
from soccermodel import model as M
from soccermodel import odds as O
from soccermodel import props as P
from soccermodel.util import clean, r

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import betrules as BR  # noqa: E402

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
def picks(g, G):
    b = g.get("book") or {}
    ph, pd_, pa = M.p1x2(G)
    out = {}
    # 1X2: the side (home or away) with the bigger gap; the draw is shown and only a play if allowed
    if b.get("ml_home") and b.get("ml_draw") and b.get("ml_away"):
        bh, bd, ba = nv(b["ml_home"], b["ml_draw"], b["ml_away"])
        opts = [("home", g["home"], ph, bh, b["ml_home"]), ("away", g["away"], pa, ba, b["ml_away"]), ("draw", "Draw", pd_, bd, b["ml_draw"])]
        if not C.DRAW_PLAYS:
            best = max(opts[:2], key=lambda o: o[2] - o[3])
        else:
            best = max(opts, key=lambda o: o[2] - o[3])
        out["1x2"] = {"side": best[1], "who": best[0], "odds": fmt_odds(best[4]), "model": r(100 * best[2]), "book": r(100 * best[3]),
                      "edge": r(100 * (best[2] - best[3])), "draw": {"model": r(100 * pd_), "book": r(100 * bd), "odds": fmt_odds(b["ml_draw"])}}
    else:
        best = ("home", g["home"], ph) if ph >= pa else ("away", g["away"], pa)
        out["1x2"] = {"side": best[1], "who": best[0], "odds": None, "model": r(100 * best[2]), "book": None, "edge": None,
                      "fair": fmt_odds(american(best[2])), "draw": {"model": r(100 * pd_), "fair": fmt_odds(american(pd_))}}
    # draw no bet: fair line only (books price it per match), from the same grid
    dh = ph / (ph + pa)
    out["dnb"] = {"side": g["home"] if dh >= 0.5 else g["away"], "model": r(100 * max(dh, 1 - dh)),
                  "fair": fmt_odds(american(max(dh, 1 - dh))), "odds": None, "book": None, "edge": None}
    # Asian handicap
    L = b.get("ah_home")
    if L is not None and b.get("ah_home_odds") and b.get("ah_away_odds"):
        mh = M.cover(M.ah(G, L))
        bh = nv(b["ah_home_odds"], b["ah_away_odds"])[0]
        home = (mh - bh) >= ((1 - mh) - (1 - bh))
        out["ah"] = {"side": g["home"] if home else g["away"], "line": L if home else -L,
                     "odds": fmt_odds(b["ah_home_odds"] if home else b["ah_away_odds"]),
                     "model": r(100 * (mh if home else 1 - mh)), "book": r(100 * (bh if home else 1 - bh)),
                     "edge": r(100 * ((mh - bh) if home else (bh - mh)))}
    else:
        best_l, best_d = 0.0, 9
        for l2 in np.arange(-2.5, 2.51, 0.25):                  # the quarter line closest to 50/50
            c = M.cover(M.ah(G, l2))
            if abs(c - 0.5) < best_d:
                best_l, best_d = float(l2), abs(c - 0.5)
        c = M.cover(M.ah(G, best_l))
        home = c >= 0.5
        out["ah"] = {"side": g["home"] if home else g["away"], "line": best_l if home else -best_l, "odds": None,
                     "model": r(100 * max(c, 1 - c)), "book": None, "edge": None, "fair": fmt_odds(american(max(c, 1 - c)))}
    # total
    T = b.get("total")
    if T is not None and b.get("over_odds") and b.get("under_odds"):
        mo = M.cover(M.total(G, T))
        bo = nv(b["over_odds"], b["under_odds"])[0]
        over = (mo - bo) >= ((1 - mo) - (1 - bo))
        out["total"] = {"side": "Over" if over else "Under", "line": T, "odds": fmt_odds(b["over_odds"] if over else b["under_odds"]),
                        "model": r(100 * (mo if over else 1 - mo)), "book": r(100 * (bo if over else 1 - bo)),
                        "edge": r(100 * ((mo - bo) if over else (bo - mo)))}
    else:
        mo = M.cover(M.total(G, 2.5))
        out["total"] = {"side": "Over" if mo >= 0.5 else "Under", "line": 2.5, "odds": None, "model": r(100 * max(mo, 1 - mo)),
                        "book": None, "edge": None, "fair": fmt_odds(american(max(mo, 1 - mo)))}
    # both teams to score: fair line only
    bt = M.btts(G)
    out["btts"] = {"side": "Yes" if bt >= 0.5 else "No", "model": r(100 * max(bt, 1 - bt)), "fair": fmt_odds(american(max(bt, 1 - bt))),
                   "yes": r(100 * bt), "odds": None, "book": None, "edge": None}
    # plays: blend with the book, then demand a real profit at the posted price (shared rules)
    for k, v in out.items():
        if v.get("edge") is None or not v.get("odds"):
            v["play"] = False
            continue
        p = BR.adjust_game(v["model"] / 100, v["book"] / 100)
        ev, need = BR.game_ev(p, int(v["odds"]))
        v["adj"], v["ev"] = r(100 * p), r(ev)
        blocked = k in C.BLOCKED or f"{g['league']}:{k}" in C.BLOCKED
        v["play"] = bool(C.PLAY_EDGE.get(k, 99) <= v["edge"] <= C.PLAY_MAX_EDGE and ev >= need and not blocked)
        v["blocked"] = bool(blocked)
    one, ahp = out.get("1x2"), out.get("ah")
    if one and ahp and one.get("play") and ahp.get("play") and one["side"] == ahp["side"]:   # same team twice: keep the bigger gap
        (ahp if one["edge"] >= ahp["edge"] else one)["play"] = False
    return out


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
def tracking(days, results, boxes):
    picks_all = {k: [] for k in ("1x2", "dnb", "ah", "total", "btts")}
    plays, daily, calib = [], {}, {"goal": [], "sot1": [], "sot2": []}
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
                if pk.get("play"):
                    text = f"{pk['side']} {pk['line']:+g}" if k == "ah" else (f"{pk['side']} {pk['line']:g}" if k == "total" else
                                                                             (f"{pk['side']} to win" if k == "1x2" else pk["side"]))
                    plays.append({"date": dt, "league": g["league"], "kind": k, "pick": text, "game": f"{g['home']} vs {g['away']}",
                                  "odds": pk.get("odds"), "edge": pk.get("edge"), "res": rr, "units": u or 0.0, "score": f"{hg}-{ag}"})
                    daily[dt] = daily.get(dt, 0) + (u or 0)
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
    return {"picks": {k: rec(v) for k, v in picks_all.items()},
            "picks_by_league": {lg: {k: rec([x for x in v if x[2] == lg]) for k, v in picks_all.items()} for lg in C.LEAGUES},
            "plays": rec2(plays), "plays_list": sorted(plays, key=lambda x: x["date"], reverse=True)[:80],
            "by_type": {k: rec2([x for x in plays if x["kind"] == k]) for k in ("1x2", "ah", "total")},
            "by_league": by_league, "series": series, "calibration": cal}


# ---------------------------------------------------------------------
# main
# ---------------------------------------------------------------------
def main():
    now = datetime.now(timezone.utc)
    today = now.astimezone(ET).date()
    season = C.SEASON or D.season_of(today)
    OUT.mkdir(parents=True, exist_ok=True)
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

    log.info("player rates")
    rates = {}
    for lg in C.LEAGUES:
        bx = P.recent_boxes(lg, today - timedelta(days=C.PROP_DAYS), today)
        rates[lg] = P.player_rates(bx)

    games, players = [], []
    for f in sorted(upcoming, key=lambda x: x["start"]):
        lg, R = f["league"], ratings.get(f["league"])
        if R is None:
            continue
        nb = new[lg].get(season, {})
        if f["home"] not in R.teams and f["home"] not in nb:
            log.warning(f"no rating for {f['home']} ({lg})")
        lh, la = R.lambdas(f["home"], f["away"], nb)
        G = M.grid(lh, la, rho[lg])
        ph, pd_, pa = M.p1x2(G)
        gd = datetime.fromisoformat(f["start"].replace("Z", "+00:00")).astimezone(ET).date()
        g = {"game_id": f["event_id"], "league": lg, "date": gd.isoformat(), "start": f["start"], "home": f["home"], "away": f["away"],
             "xg_home": r(lh, 2), "xg_away": r(la, 2), "p_home": r(100 * ph), "p_draw": r(100 * pd_), "p_away": r(100 * pa),
             "book": f.get("book"),
             "scores": sorted(({"s": f"{i}-{j}", "p": r(100 * float(G[i, j]))} for i in range(6) for j in range(6)), key=lambda x: -x["p"])[:6]}
        g["picks"] = picks({**g, "book": f.get("book")}, G)
        games.append(g)
        pr, tm = rates[lg]
        for side, lam, opp in (("home", lh, f["away"]), ("away", la, f["home"])):
            for p in P.match_props(f[side], lam, pr, tm, f["event_id"], opp):
                p["league"] = lg
                players.append(p)

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
        keep = [{k: g[k] for k in ("game_id", "league", "date", "start", "home", "away", "picks", "book", "p_home", "p_draw", "p_away",
                                   "xg_home", "xg_away")} for g in v["games"]]
        for x in keep:                                          # first price seen, for closing-line value later
            prev = next((o for o in old["games"] if o["game_id"] == x["game_id"]), None)
            x["open_book"] = (prev or {}).get("open_book") or x.get("book")
        path.write_text(json.dumps(clean({"date": day, "games": [g for g in old["games"] if g["game_id"] not in live] + keep,
                                          "players": [p for p in old["players"] if p["game_id"] not in live] + v["players"]}),
                                   separators=(",", ":")))

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
    track = tracking(days, results, boxes)

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
               "teams": team_rows, "backtest": bt,
               "model": {lg: {"home": r(ratings[lg].home, 3) if ratings[lg] else None, "rho": rho[lg],
                              "base": r(math.exp(ratings[lg].intercept), 2) if ratings[lg] else None} for lg in C.LEAGUES},
               "rules": {"edge": C.PLAY_EDGE, "max": C.PLAY_MAX_EDGE, "draw_plays": C.DRAW_PLAYS, **BR.summary(),
                         "blocked": sorted(C.BLOCKED)}}
    (OUT / "latest.json").write_text(json.dumps(clean(payload), separators=(",", ":")))
    log.info(f"wrote {len(games)} matches, {len(players)} players")


if __name__ == "__main__":
    main()
