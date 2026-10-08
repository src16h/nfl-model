"""
Player props from the game simulation.

Every simulated game has team shots and goals. Shots are shared among the
dressed skaters by their shot rate and ice time (with game-to-game noise),
goals by their scoring rate, assists by their assist rate. The goalie's saves
are the other team's shots on him minus the goals he allows. Because players
live inside the same simulated game, their results move together the way
real ones do, which is what the alt-line parlays use.
"""
import itertools
import logging

import numpy as np
import pandas as pd

from . import config as C
from .util import norm_name, r

log = logging.getLogger("nhlmodel")
MAXK = {"sog": 10, "points": 5, "goals": 4, "assists": 4, "saves": 50}
PRIOR_MIN = 200.0                  # minutes of league-average play mixed into each player's rates


def skater_rates(pg: pd.DataFrame, season: int):
    """playerId -> per-60 rates from recent games (each older game counts a bit less),
    pulled toward the position average, plus ice-time history."""
    sk = pg[pg["pos"] != "G"].copy()
    sk["grp"] = np.where(sk["pos"] == "D", "D", "F")
    sk["season"] = sk["game_id"] // 1000000
    sk["g_mix"] = 0.5 * sk["goals"] + 0.5 * sk["ixg"]
    pos = {}
    for g, x in sk.groupby("grp"):
        m = x["toi"].sum()
        pos[g] = {"sog": 60 * x["sog"].sum() / m, "g": 60 * x["g_mix"].sum() / m, "a": 60 * x["assists"].sum() / m}
    sk = sk.sort_values(["date", "game_id"])
    out = {}
    for pid, x in sk.groupby("pid"):
        x = x[x["toi"] > 0]
        if x.empty:
            continue
        grp = x["grp"].iloc[-1]
        age = np.arange(len(x))[::-1]
        w = C.PLAYER_DECAY ** age * np.where(x["season"] < season, C.PREV_SEASON_WEIGHT, 1.0)
        wm = float((w * x["toi"]).sum())
        rates = {k: 60 * (float((w * x[c]).sum()) + PRIOR_MIN * pos[grp][k] / 60) / (wm + PRIOR_MIN)
                 for k, c in (("sog", "sog"), ("g", "g_mix"), ("a", "assists"))}
        cur = x[x["season"] == season]
        rates["toi"] = float(np.average(x["toi"], weights=w))
        rates["name"], rates["grp"], rates["team"] = x["name"].iloc[-1], grp, x["team"].iloc[-1]
        rates["gp"] = int(len(cur))
        rates["avg"] = {"sog": r(cur["sog"].mean(), 2), "points": r((cur["goals"] + cur["assists"]).mean(), 2)} if len(cur) else None
        out[int(pid)] = rates
    return out, pos


def goalie_skill(gg: pd.DataFrame, pg: pd.DataFrame, season: int):
    """playerId -> goals allowed per expected goal (pulled toward 1.0; below 1 is good) and start history."""
    gg = gg.copy()
    gg["season"] = gg["game_id"] // 1000000
    names = pg[pg["pos"] == "G"].drop_duplicates("pid", keep="last").set_index("pid")["name"].to_dict()
    out = {}
    for pid, x in gg.groupby("goalie"):
        w = np.where(x["season"] < season, C.PREV_SEASON_WEIGHT, 1.0) * (x["season"] >= season - 2)
        xg, g = float((w * x["xga"]).sum()), float((w * x["ga"]).sum())
        out[int(pid)] = {"ratio": (g + C.GOALIE_SHRINK_XG) / (xg + C.GOALIE_SHRINK_XG), "name": names.get(pid, str(pid)),
                         "gsax": xg - g, "gp": int((x["season"] == season).sum())}
    return out


def lineup(team, pg, rates, pos, n_recent=3):
    """Skaters from the team's most recent game, with expected ice time and rates."""
    t = pg[(pg["team"] == team) & (pg["pos"] != "G")]
    if t.empty:
        return []
    recent_ids = sorted(t["game_id"].unique())[-n_recent:]
    last = t[t["game_id"] == recent_ids[-1]]
    rec = t[t["game_id"].isin(recent_ids)].groupby("pid")["toi"].mean().to_dict()
    out = []
    for p in last.itertuples(index=False):
        rt = rates.get(int(p.pid))
        grp = "D" if p.pos == "D" else "F"
        base = rt or {"sog": pos[grp]["sog"], "g": pos[grp]["g"], "a": pos[grp]["a"], "toi": p.toi}
        toi = C.TOI_RECENT_WEIGHT * rec.get(p.pid, p.toi) + (1 - C.TOI_RECENT_WEIGHT) * (base.get("toi") or p.toi)
        out.append({"pid": int(p.pid), "name": p.name, "pos": p.pos, "team": team, "toi": toi,
                    "e_sog": base["sog"] * toi / 60, "e_g": base["g"] * toi / 60, "e_a": base["a"] * toi / 60,
                    "avg": (rt or {}).get("avg"), "gp": (rt or {}).get("gp", 0)})
    return out


def projected_goalie(team, pg, game_date, gskill):
    """Most likely starter: the goalie with the most recent starts, but the other one
    when the team played yesterday and the usual starter went then."""
    gl = pg[(pg["team"] == team) & (pg["pos"] == "G") & (pg["starter"] == 1)].sort_values(["date", "game_id"])
    if gl.empty:
        return None, "Projected"
    last10 = gl.tail(10)
    counts = last10["pid"].value_counts()
    main = int(counts.index[0])
    last = gl.iloc[-1]
    b2b = (pd.Timestamp(game_date) - pd.Timestamp(last["date"])).days <= 1
    if b2b and int(last["pid"]) == main:
        others = [int(x) for x in counts.index[1:]]
        if not others:                                  # use any other goalie on the roster lately
            others = [int(x) for x in pg[(pg["team"] == team) & (pg["pos"] == "G")]["pid"].unique() if int(x) != main]
        if others:
            return others[0], "Projected, back-to-back"
    return main, "Projected"


def _dist(x, maxk):
    x = np.minimum(x, maxk + 1)
    ge = [float((x >= k).mean()) for k in range(maxk + 2)]
    return ge


def _fair(ge):
    """Half-point line closest to a coin flip."""
    k = min(range(1, len(ge)), key=lambda k: abs(ge[k] - 0.5))
    return k - 0.5


def team_players(sim, side, skaters, goalie, rng):
    """Simulated stat arrays for one team's players. side: 'H' or 'A'."""
    n = len(sim["FH"])
    out = {}
    if skaters:
        e_s = np.array([p["e_sog"] for p in skaters]); e_g = np.array([p["e_g"] for p in skaters]); e_a = np.array([p["e_a"] for p in skaters])
        shots = sim["SH"] if side == "H" else sim["SA"]
        goals = (sim["RH"] + sim["OTH"]) if side == "H" else (sim["RA"] + sim["OTA"])
        P = rng.dirichlet(C.PLAYER_SOG_CONC * e_s / e_s.sum(), size=n)
        S = rng.multinomial(shots, P)
        G = rng.multinomial(goals, e_g / e_g.sum())
        p0, p1 = C.ASSIST_SPLIT
        cat = rng.multinomial(goals, [p0, p1, 1 - p0 - p1])
        A = rng.multinomial(cat[:, 1] + 2 * cat[:, 2], e_a / e_a.sum())
        for i, p in enumerate(skaters):
            out[p["pid"]] = {"sog": S[:, i], "goals": G[:, i], "assists": A[:, i], "points": G[:, i] + A[:, i]}
    if goalie:
        sv = (sim["SA_g"] - sim["GA_ev"]) if side == "H" else (sim["SH_g"] - sim["GH_ev"])
        out[goalie["pid"]] = {"saves": sv}
    return out


def summarize(arrs, info, book):
    """Distribution summary per stat plus the call against the book when a line exists."""
    rows = []
    for pid, stats in arrs.items():
        p = info[pid]
        rec = {"pid": pid, "name": p["name"], "team": p["team"], "pos": p["pos"], "toi": r(p.get("toi")), "m": {}}
        for st, x in stats.items():
            ge = _dist(x, MAXK[st])
            m = {"mean": r(x.mean(), 2), "fair": _fair(ge), "ge": [round(v, 3) for v in ge]}
            b = (book or {}).get(norm_name(p["name"]), {}).get(st)
            if b and b.get("line") is not None and b.get("over") and b.get("under"):
                L = float(b["line"])
                po = float((x > L).mean())
                from .odds import no_vig
                bo = no_vig(b["over"], b["under"])
                side = "Over" if po - bo >= (1 - po) - (1 - bo) else "Under"
                edge = (po - bo) if side == "Over" else (bo - po)
                m["book"] = {"line": L, "over": b["over"], "under": b["under"], "book_over": r(100 * bo), "model_over": r(100 * po),
                             "side": side, "edge": r(100 * edge), "odds": b["over"] if side == "Over" else b["under"],
                             "src": b.get("book"),
                             "play": C.PROP_PLAY_MIN * 100 <= 100 * edge <= C.PROP_PLAY_MAX * 100}
            rec["m"][st] = m
        rows.append(rec)
    return rows


def alt_parlay(arrs, info, game, book):
    """Model alt-line parlay: half-point overs near the main line, fair odds +100 to +125."""
    lo_p, hi_p = 1 / (1 + C.ALT_PARLAY_ODDS[1] / 100), 1 / (1 + C.ALT_PARLAY_ODDS[0] / 100)
    cands = []
    for pid, stats in arrs.items():
        p = info[pid]
        for st, x in stats.items():
            if st not in C.ALT_MAX_DROP:
                continue
            b = (book or {}).get(norm_name(p["name"]), {}).get(st)
            main = float(b["line"]) if b and b.get("line") is not None else _fair(_dist(x, MAXK[st]))
            src = "book" if b and b.get("line") is not None else "model"
            k_main = int(main + 0.5)
            for k in range(max(1, k_main - C.ALT_MAX_DROP[st]), k_main + 1):
                hit = x >= k
                ph = float(hit.mean())
                if C.ALT_LEG_RANGE[0] <= ph <= C.ALT_LEG_RANGE[1]:
                    cands.append({"pid": pid, "name": p["name"], "team": p["team"], "stat": st, "line": k - 0.5,
                                  "p": ph, "main": main, "main_src": src, "hit": hit})
    if len(cands) < 3:
        return None
    cands.sort(key=lambda c: -c["p"])
    cands = cands[:40]
    best = None
    for size in (C.ALT_PARLAY_LEGS, 3, 5):
        beam = [((), None)]
        for _ in range(size):
            nxt = []
            for idx, joint in beam:
                used = {cands[i]["pid"] for i in idx}
                saves = any(cands[i]["stat"] == "saves" for i in idx)
                for i in range((idx[-1] + 1) if idx else 0, len(cands)):
                    c = cands[i]
                    if c["pid"] in used or (saves and c["stat"] == "saves"):
                        continue
                    j = c["hit"] if joint is None else joint & c["hit"]
                    nxt.append((idx + (i,), j))
            nxt.sort(key=lambda t: -float(t[1].mean()) / np.prod([cands[i]["p"] for i in t[0]]))
            beam = nxt[:60]
        beam = [(tuple(cands[i] for i in idx), j) for idx, j in beam]
        for legs, joint in beam:
            pj = float(joint.mean())
            teams = {c["team"] for c in legs}
            if lo_p <= pj <= hi_p and len(teams) == 2:
                pi = float(np.prod([c["p"] for c in legs]))
                score = pj / pi
                if best is None or score > best[0]:
                    best = (score, legs, pj, pi)
        if best:
            break
    if not best:
        return None
    _, legs, pj, pi = best
    fair = round(100 * (1 - pj) / pj)
    label = {"sog": "shots", "points": "points", "saves": "saves"}
    return {"p": r(100 * pj), "pi": r(100 * pi), "fair": f"+{fair}",
            "legs": [{"pid": c["pid"], "name": c["name"], "team": c["team"], "stat": c["stat"], "line": c["line"],
                      "label": f"Over {c['line']:g} {label[c['stat']]}", "p": r(100 * c["p"]), "main": c["main"], "main_src": c["main_src"]}
                     for c in legs]}
