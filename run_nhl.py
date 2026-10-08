"""
Daily NHL model run.

  python run_nhl.py          writes docs/nhl/data/latest.json (+ history, results)

Steps: team form from MoneyPuck, fit the goal and shot models on every game
since 2012, find today's games and starting goalies, simulate each game,
price game lines and player props, build alt-line parlays, then grade
everything already played.
"""
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
    lim = {"ml": C.ML_PLAY_EDGE, "pl": C.PL_PLAY_EDGE, "total": C.TOTAL_PLAY_EDGE}
    for k, v in out.items():
        v["play"] = v["edge"] is not None and lim[k] <= v["edge"] <= C.PLAY_MAX_EDGE
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


def tracking(history_days, results):
    picks = {k: [] for k in ("ml", "pl", "total")}
    plays, prop_plays, calib, alts, daily = [], [], {}, [], {}
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
                    plays.append({"date": dt, "kind": k, "pick": pick_text(k, pk), "game": f"{g['away']} at {g['home']}",
                                  "odds": pk.get("odds"), "edge": pk.get("edge"), "res": rr, "units": u})
                    daily[dt] = daily.get(dt, 0) + (u or 0)
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
                                 "legs": len(hits), "p": ap["p"]})
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
                                       "edge": bk["edge"], "res": rr, "units": u, "actual": v})
                    daily[dt] = daily.get(dt, 0) + u

    def rec(rows):
        w = sum(1 for x in rows if x[0] == "W"); l = sum(1 for x in rows if x[0] == "L")
        us = [x[1] for x in rows if x[1] is not None]
        return {"w": w, "l": l, "pct": r(100 * w / (w + l)) if w + l else None, "units": r(sum(us), 2) if us else None}

    def rec2(rows):
        w = sum(1 for x in rows if x["res"] == "W"); l = sum(1 for x in rows if x["res"] == "L")
        u = sum(x["units"] or 0 for x in rows)
        return {"w": w, "l": l, "pct": r(100 * w / (w + l)) if w + l else None, "units": r(u, 2),
                "roi": r(100 * u / (w + l)) if w + l else None}
    cal = {}
    for st, rows in calib.items():
        cal[st] = {"n": len(rows), "model": r(100 * np.mean([x[0] for x in rows])), "actual": r(100 * np.mean([x[1] for x in rows]))}
    series, run = [], 0.0
    for dt in sorted(daily):
        run += daily[dt]
        series.append({"date": dt, "units": r(run, 2)})
    return {"picks": {k: rec(v) for k, v in picks.items()},
            "plays": rec2(plays), "plays_list": sorted(plays, key=lambda x: x["date"], reverse=True)[:60],
            "prop_plays": rec2(prop_plays), "prop_plays_list": sorted(prop_plays, key=lambda x: x["date"], reverse=True)[:80],
            "calibration": cal,
            "alt": {"n": len(alts), "hits": sum(a["hit"] for a in alts),
                    "model": r(np.mean([a["p"] for a in alts])) if alts else None,
                    "recent": sorted(alts, key=lambda x: x["date"], reverse=True)[:20]},
            "series": series}


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
            sks = P.lineup(t, pg, rates, pos)
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
                             **({"book": {x: m["book"][x] for x in ("line", "side", "odds", "edge", "play")}} if m.get("book") else {})}
        pl_lite.append(lite)
    gdate = {g["game_id"]: g["date"] for g in games}
    for p in pl_lite:
        by_day[gdate[p["game_id"]]]["players"].append(p)
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
            keep.append(lite)
        path.write_text(json.dumps(clean({"date": day, "games": old_games + keep, "players": old_players + v["players"]}),
                                   separators=(",", ":")))
    days = [load_json(p, {}) for p in sorted(HIST.glob("*.json"))]
    days = [d for d in days if d]
    ids = {g["game_id"] for d in days for g in d.get("games", [])}
    results = build_results(games_t, pg, ids)
    (OUT / "results.json").write_text(json.dumps(clean(results), separators=(",", ":")))
    track = tracking(days, results)

    # finished/locked games from today's file so the slate stays complete
    payload = {"generated_at": now.isoformat(), "season": season, "today": today.isoformat(),
               "games": games, "players": players, "odds": odds_status, "tracking": track,
               "model": {"coefs": model.coefs(), "eng": eng, "eng_check": eng_info, "ot_goal_share": r(model.ot_goal_share, 3),
                         "league": {k: r(v, 2) for k, v in lg.items()}, "train_games": int(len(rows) / 2),
                         "backtest": BACKTEST},
               "teams": [{"team": t, **{k: r(v, 2) for k, v in f.items() if k not in ("last",)}} for t, f in sorted(form.items())],
               "rules": {"ml": C.ML_PLAY_EDGE, "pl": C.PL_PLAY_EDGE, "total": C.TOTAL_PLAY_EDGE, "max": C.PLAY_MAX_EDGE,
                         "prop": [100 * C.PROP_PLAY_MIN, 100 * C.PROP_PLAY_MAX]}}
    (OUT / "latest.json").write_text(json.dumps(clean(payload), separators=(",", ":")))
    log.info(f"wrote {len(games)} games, {len(players)} players")


# walk-forward check, refreshed by hand (python -m nhlmodel.backtest); shown on the Record tab
BACKTEST = {"seasons": "2023-24 to 2025-26", "win_logloss": 0.668, "base_logloss": 0.689,
            "note": "Puck-line and overtime rates land within about 1 to 3 points of real results each season. Totals drift with league scoring (off by up to 0.2 goals a game in a season), so total plays need a bigger gap."}

if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        log.exception("NHL run failed")
        sys.exit(1)
