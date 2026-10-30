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

import json

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


def lineup(team, pg, rates, pos, n_recent=3, roster=None):
    """Skaters from the team's most recent game, with expected ice time and rates.
    With today's roster: players traded or sent down since then are dropped."""
    t = pg[(pg["team"] == team) & (pg["pos"] != "G")]
    if t.empty:
        return []
    recent_ids = sorted(t["game_id"].unique())[-n_recent:]
    last = t[t["game_id"] == recent_ids[-1]]
    rec = t[t["game_id"].isin(recent_ids)].groupby("pid")["toi"].mean().to_dict()
    if roster and roster.get("S"):
        last = last[last["pid"].astype(int).isin(roster["S"])]
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


def load_goalie_overrides(path):
    """data/nhl/goalie_overrides.csv: date,team,goalie (a confirmed starter; blank date = every game)."""
    try:
        o = pd.read_csv(path, comment="#", dtype=str).dropna(subset=["team", "goalie"])
        o["team"] = o["team"].str.strip().str.upper()
        o["nname"] = o["goalie"].map(norm_name)
        o["date"] = o.get("date", pd.Series("", index=o.index)).fillna("").str.strip()
        return o
    except Exception:  # noqa: BLE001
        return pd.DataFrame(columns=["date", "team", "goalie", "nname"])


def projected_goalie(team, pg, game_date, gskill, roster=None, overrides=None):
    """Most likely starter.
    Candidates: goalies on today's NHL roster (so trades count the same day), else anyone who
    dressed for the team lately. Each candidate is judged on his OWN recent games on any team
    (share of the last 20 games he dressed that he started), so a starter who just arrived by trade
    is the No. 1 right away. Near-ties go to the better goalie. The No. 2 goes on a back-to-back
    when the No. 1 started yesterday. A manual override (confirmed starter) beats all of this."""
    gd = pd.Timestamp(game_date)
    G = pg[pg["pos"] == "G"].sort_values(["date", "game_id"])
    tg = G[G["team"] == team]
    if roster and roster.get("G"):
        cands = set(roster["G"])
    else:
        recent = sorted(tg["game_id"].unique())[-5:]
        cands = set(tg[tg["game_id"].isin(recent)]["pid"].astype(int))
    if overrides is not None and len(overrides):
        o = overrides[(overrides["team"] == team) & overrides["date"].isin(["", gd.date().isoformat()])]
        for nn in o["nname"]:
            pool = {**{p: v.get("name", "") for p, v in gskill.items()}, **((roster or {}).get("G", {}))}
            hit = [p for p, n in pool.items() if norm_name(n) == nn and (not cands or p in cands)]
            if hit:
                return int(hit[0]), "Confirmed (manual)"
    if not cands:
        return None, "Projected"
    score, new = {}, set()
    for pid in cands:
        x = G[G["pid"] == pid]
        if x.empty:
            score[pid] = 0.0
            continue
        last = x.iloc[-1]
        # the team has played 3+ games without him dressing: hurt or out of the rotation
        missed = tg[tg["date"] > last["date"]]["game_id"].nunique()
        if missed >= 3:
            score[pid] = -1.0
            continue
        # share of his own last 20 dressed games (any team) that he started, recent games count more
        st = x.tail(20)["starter"].to_numpy(float)
        w = 0.5 ** (np.arange(len(st))[::-1] / 8.0)
        score[pid] = float((st * w).sum() / w.sum())
        here = x[x["team"] == team]
        if len(here) and (x["team"] != team).any() and (gd - pd.Timestamp(here["date"].iloc[0])).days <= 14:
            new.add(pid)                                    # joined this team in the last two weeks
    ratio = lambda p: gskill.get(p, {}).get("ratio", 1.05)
    order = sorted(cands, key=lambda p: (-score[p], ratio(p)))
    if len(order) > 1 and score[order[0]] - score[order[1]] < 0.10 and ratio(order[1]) < ratio(order[0]):
        order[0], order[1] = order[1], order[0]           # near-even split: lean to the better goalie
    main = order[0]
    tag = "Projected, new arrival" if main in new else "Projected"
    ts = tg[tg["starter"] == 1]
    if len(ts) and len(order) > 1:
        lastg = ts.iloc[-1]
        if (gd - pd.Timestamp(lastg["date"])).days <= 1 and int(lastg["pid"]) == main:
            return int(order[1]), "Projected, back-to-back"
    return int(main), tag


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
                             "src": b.get("book"), "pulled": b.get("pulled"),
                             "play": C.PROP_PLAY_MIN * 100 <= 100 * edge <= C.PROP_PLAY_MAX * 100}
            rec["m"][st] = m
        rows.append(rec)
    return rows


def american(p):
    """Fair American odds for a hit chance (0-1)."""
    return f"-{round(100 * p / (1 - p))}" if p > 0.5 else f"+{round(100 * (1 - p) / p)}"


def alt_parlay(arrs, info, game, book, team_legs=(), need_team=False):
    """Model alt-line SGP at fair odds of +100 to +125 (same target as the NFL): legs rated 70%+ after a
    per-leg-type correction learned from graded games (nhlmodel/altcal.py); picks the ticket most likely to hit. Picks the most likely 3-leg (else 2-leg) ticket
    from both teams whose joint chance lands in ALT_TARGET_P, using the simulated games so legs that
    hit together are priced together."""
    from pathlib import Path
    from . import altcal
    data = Path(__file__).resolve().parents[1] / "docs" / "nhl" / "data"
    cal = altcal.fit(data / "history", data / "results.json")
    cands = []
    for pid, stats in arrs.items():
        p = info[pid]
        for st, x in stats.items():
            if st not in C.ALT_MAX_DROP:
                continue
            b = (book or {}).get(norm_name(p["name"]), {}).get(st)
            main = float(b["line"]) if b and b.get("line") is not None else _fair(_dist(x, MAXK[st]))
            src = "book" if b and b.get("line") is not None else "model"
            if st in C.ALT_MAIN_LINE_ONLY and src != "book":
                continue                                   # main line only, and only the book's real one
            k_main = int(main + 0.5)
            for k in range(max(1, k_main - C.ALT_MAX_DROP[st]), k_main + 1):
                hit = x >= k
                raw = float(hit.mean())
                ph = altcal.adjust(cal, st, k - 0.5, raw) if raw > 0 else 0.0   # corrected by leg type from graded games
                if C.ALT_LEG_RANGE[0] <= ph <= C.ALT_LEG_RANGE[1]:
                    cands.append({"pid": pid, "name": p["name"], "team": p["team"], "stat": st, "line": k - 0.5,
                                  "p": ph, "p_raw": raw, "main": main, "main_src": src, "hit": hit})
    booked = [c for c in cands if c["main_src"] == "book"]
    if len(booked) >= 4:                                   # stick to players the book has posted (their alts exist)
        cands = booked
    # team legs (Oct 21 2026): puck lines, totals and team totals priced from Pinnacle's lines (altlines.team_legs),
    # their hit arrays come from the same simulated games, so they combine with player legs at their real correlation
    home, away = game["home"], game["away"]
    tl_c = [{**t, "pid": "T:" + t["label"], "name": "", "team": t.get("teamname"), "stat": "team:" + t["market"],
             "main": None, "main_src": "pinnacle"} for t in team_legs]
    if need_team:
        if not tl_c:
            return None
        cands = tl_c + cands                               # the mixed ticket starts from a team leg
    else:
        cands = cands + tl_c
    if len(cands) < 2:
        return None
    lo, hi = C.ALT_TARGET_P

    def joint(idx, h):
        pj = float(h.mean())
        for i in idx:                                      # keep how legs move together, apply each leg's correction
            pj *= cands[i]["p"] / cands[i]["p_raw"]
        return min(pj, min(cands[i]["p"] for i in idx))

    def search(size):
        beams = [((i,), cands[i]["hit"], cands[i]["p"]) for i in range(len(cands)) if not need_team or i < len(tl_c)]
        for step in range(size - 1):
            last = step == size - 2
            nxt = []
            for idx, h, _p in beams:
                used = {cands[i]["pid"] for i in idx}
                saves = sum(cands[i]["stat"] == "saves" for i in idx)
                tl = [cands[i] for i in idx if cands[i].get("kind") == "team"]
                for j in range(idx[-1] + 1, len(cands)):
                    c = cands[j]
                    if c["pid"] in used or (saves and c["stat"] == "saves"):
                        continue
                    if c.get("kind") == "team" and (len(tl) >= C.ALT_MAX_TEAM_LEGS or any(x["stat"] == c["stat"] for x in tl)):
                        continue                               # at most 2 team legs, one per market
                    hj = h & c["hit"]
                    pj = joint(idx + (j,), hj)
                    if pj >= lo and (not last or pj <= hi):   # adding legs only lowers the chance
                        nxt.append((idx + (j,), hj, pj))
            nxt.sort(key=lambda t: -t[2])
            beams = nxt if last else nxt[:C.ALT_BEAM]
        best = None
        for idx, h, pj in beams:
            cover = set()
            for i in idx:
                cover |= {home, away} if cands[i].get("team") is None else {cands[i]["team"]}
            if lo <= pj <= hi and cover == {home, away} and (best is None or pj > best[1]):
                best = ([cands[i] for i in idx], pj)
        return best

    best = None
    for size in C.ALT_SIZES:
        best = search(size)
        if best:
            break
    if not best:
        return None
    legs, pj = best
    pi = float(np.prod([c["p"] for c in legs]))
    raw = pj
    # whole-ticket correction (Oct 26 2026, same as the NFL): the chance moves toward this ticket type's own graded
    # record on the log-odds scale, fading in with the sample. Player tickets have hit 54% when the model said 48%.
    try:
        tr = (json.loads((data / "latest.json").read_text()).get("tracking") or {}).get("alt_mix" if need_team else "alt") or {}
        n_, m_ = tr.get("n") or 0, (tr.get("model") or 0) / 100
        a_ = (tr.get("hits") or 0) / n_ if n_ else 0
        if n_ >= 10 and 0 < m_ < 1 and 0 < a_ < 1:
            shift = (np.log(a_ / (1 - a_)) - np.log(m_ / (1 - m_))) * n_ / (n_ + C.ALT_TICKET_K)
            pj = float(1 / (1 + np.exp(-(np.log(pj / (1 - pj)) + shift))))
    except Exception:  # noqa: BLE001
        pass
    label = {"sog": "shots", "points": "points", "saves": "saves"}
    def leg(c):
        if c.get("kind") == "team":
            return {"kind": "team", "market": c["market"], "team": c["team_side"], "side": c["side"], "line": c["line"], "name": "",
                    "label": c["label"], "p": r(100 * c["p"]), "p_model": r(100 * c["p_model"]), "main_src": "pinnacle"}
        return {"pid": c["pid"], "name": c["name"], "team": c["team"], "stat": c["stat"], "line": c["line"],
                "label": f"Over {c['line']:g} {label[c['stat']]}", "p": r(100 * c["p"]), "main": c["main"], "main_src": c["main_src"]}
    dec = (1 + C.ALT_BET_CUSHION) / pj
    bet = f"+{round(100 * (dec - 1))}" if dec >= 2 else str(round(-100 / (dec - 1)))
    return {"v": 5 if need_team else 3, "p": r(100 * pj), "p_sim": r(100 * raw), "pi": r(100 * pi), "fair": american(pj),
            "bet_at": bet, "cushion": C.ALT_BET_CUSHION, "legs": [leg(c) for c in legs]}
