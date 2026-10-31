"""
Player props from the game simulation.

Each player has per-minute rates (points, rebounds, assists, threes; newer games count more, pulled
toward his position's average) and expected minutes (the last few games lean hardest). In every
simulated game:
  - each listed-injured player plays or sits by his injury status; the minutes of players who sit go
    to the teammates who play (team minutes add to 240, about 42 at most for anyone);
  - minutes wobble a little, and starters lose some in blowouts;
  - points: the team's simulated score is shared by each player's scoring rate times his minutes, so a
    teammate sitting raises everyone else's share (usage), and a high-scoring game lifts everyone;
  - rebounds, assists and threes follow rate x minutes, nudged by the game's scoring (LINK);
  - every stat gets game-to-game noise (gamma-Poisson, sizes in config.DISP).
Players live inside the same simulated game as the final score, so they move together the way real
ones do, which is what the alt-line parlays use. A player's own numbers count only the games he plays
(books void a prop when the player sits).
"""
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from .util import norm_name, r

log = logging.getLogger("nbamodel")
BASE = ["pts", "reb", "ast", "fg3m"]
MAXK = {"pts": 60, "reb": 25, "ast": 20, "fg3m": 12, "pra": 80}
LABEL = {"pts": "points", "reb": "rebounds", "ast": "assists", "fg3m": "threes", "pra": "pts+reb+ast"}
POSG = {"PG": "G", "SG": "G", "G": "G", "SF": "F", "PF": "F", "F": "F", "C": "C", "FC": "C", "GF": "F"}


def player_table(pg: pd.DataFrame, games: pd.DataFrame, asof):
    """Rates and expected minutes from games before `asof` (a UTC timestamp). One row per player,
    on the team he played for most recently."""
    g = games[["game_id", "start", "season"]].copy()
    g["start_dt"] = pd.to_datetime(g["start"], utc=True)
    p = pg.merge(g, on="game_id")
    p = p[p["start_dt"] < asof]
    p = p[p["start_dt"] >= asof - pd.Timedelta(days=420)]
    played = p[(~p["dnp"].astype(bool)) & (p["min"] > 0)].copy()
    played = played.sort_values("start_dt")
    played["k"] = played.groupby("pid").cumcount(ascending=False)       # 0 = most recent game played
    played["w"] = C.RATE_DECAY ** played["k"]
    played["pg"] = played["pos"].map(POSG).fillna("F")
    from .ratings import gamescore
    played["gs"] = gamescore(played.fillna(0))
    pos_rate = {}
    for grp, x in played.groupby("pg"):
        pos_rate[grp] = {s: float(x[s].sum() / max(1.0, x["min"].sum())) for s in BASE}
    agg = played.assign(**{f"w_{s}": played["w"] * played[s] for s in BASE + ["min", "gs"]}).groupby("pid")
    sums = agg[[f"w_{s}" for s in BASE + ["min", "gs"]]].sum()
    last = played.groupby("pid").tail(1).set_index("pid")
    recent = played[played["k"] < 8].copy()
    recent["wm"] = C.MIN_DECAY ** recent["k"]
    em = (recent["wm"] * recent["min"]).groupby(recent["pid"]).sum() / recent["wm"].groupby(recent["pid"]).sum()
    starts = recent[recent["k"] < 5].groupby("pid")["starter"].mean()
    out = []
    for pid, row in sums.iterrows():
        lr = last.loc[pid]
        pr = pos_rate.get(POSG.get(lr["pos"], "F"), pos_rate.get("F"))
        rec = {"pid": str(pid), "name": lr["name"], "team": lr["team"], "pos": lr["pos"], "last": lr["start_dt"],
               "exp_min": float(em.get(pid, 0.0)), "start_rate": float(starts.get(pid, 0.0))}
        for s in BASE:
            rec[f"r_{s}"] = (row[f"w_{s}"] + C.PRIOR_MIN * pr[s]) / (row["w_min"] + C.PRIOR_MIN)
        rec["val_pm"] = (row["w_gs"] + C.VAL_PRIOR_MIN * C.VAL_REPL) / (row["w_min"] + C.VAL_PRIOR_MIN)
        out.append(rec)
    t = pd.DataFrame(out)
    # team scoring level (recent), for the environment factor
    tg = games[pd.to_datetime(games["start"], utc=True) < asof].sort_values("start")
    rows = pd.concat([tg[["home", "hs", "start"]].rename(columns={"home": "team", "hs": "pts"}),
                      tg[["away", "as", "start"]].rename(columns={"away": "team", "as": "pts"})]).sort_values("start")
    team_avg = rows.groupby("team")["pts"].apply(lambda s: float(s.tail(20).mean())).to_dict()
    return t, team_avg


def roster(table, team, asof, injuries=None, last_team_game=None):
    """Players likely to dress for `team`: on the team in its recent games, with their chance to play."""
    t = table[(table["team"] == team)].copy()
    if last_team_game is not None:
        t = t[t["last"] >= last_team_game - pd.Timedelta(days=21)]
    t = t[t["exp_min"] >= 4.0]
    inj = {}
    for x in (injuries or {}).get(team, []):
        st = str(x.get("status") or "").lower()
        a = next((v for k, v in C.INJ_PLAY.items() if k in st), 0.75)
        inj[str(x.get("pid"))] = (a, x.get("status"), x.get("detail"))
        inj[norm_name(x.get("name"))] = inj[str(x.get("pid"))]
    plays = []
    for _, p in t.iterrows():
        a, st, det = inj.get(p["pid"]) or inj.get(norm_name(p["name"])) or (1.0, None, None)
        plays.append({**p.to_dict(), "avail": a, "status": st, "inj": det})
    return sorted(plays, key=lambda x: -x["exp_min"])


def team_players(sim, side, players, team_avg, rng):
    """Simulated stat arrays for one team's players. side 'H' or 'A'. Returns {pid: {stat: array, 'play': mask}}."""
    n = len(sim["FH"])
    if not players:
        return {}
    k = len(players)
    pts_team = sim["FH"] if side == "H" else sim["FA"]
    margin = (sim["FH"] - sim["FA"]) * (1 if side == "H" else -1)
    tot = sim["FH"] + sim["FA"]
    exp_min = np.array([p["exp_min"] for p in players])
    avail = rng.random((n, k)) < np.array([p["avail"] for p in players])
    mins = exp_min * avail * np.clip(rng.normal(1.0, C.MIN_SD, (n, k)), 0.4, 1.6)
    starter = np.array([p["start_rate"] >= 0.5 or p["exp_min"] >= 28 for p in players])
    blow = np.clip(np.abs(margin) - C.BLOWOUT_START, 0, None)[:, None] * C.BLOWOUT_PER_PT
    mins = np.where(starter, mins * np.clip(1 - blow, 0.55, 1.0), mins * (1 + 0.5 * blow))
    # minutes add to 240 among the players who play, about 42 at most each
    for _ in range(3):
        s = mins.sum(1, keepdims=True)
        mins = np.minimum(mins * (C.TEAM_MIN / np.maximum(s, 1.0)), 42.0) * avail
    lvl = team_avg if team_avg else 115.0
    env = pts_team / lvl
    rate = {s: np.array([p[f"r_{s}"] for p in players]) for s in BASE}
    out = {p["pid"]: {"play": avail[:, i]} for i, p in enumerate(players)}
    # points: share of the team's simulated score (usage moves to whoever plays)
    w = rate["pts"] ** C.USAGE_POW * mins                   # scorers keep more of the share than rate x minutes (fit on 2025-26)
    share = w / np.maximum(w.sum(1, keepdims=True), 1e-9)
    mu = {"pts": share * pts_team[:, None] * 0.985}           # a sliver of team points are unassigned (technicals etc.)
    for s in ("reb", "ast", "fg3m"):
        e = (tot / (2 * lvl)) if s == "reb" else env
        mu[s] = rate[s] * mins * (e[:, None] ** C.LINK[s])
    for s in BASE:
        if s == "pts":                                   # points: closer to symmetric than gamma-Poisson (real medians sat higher)
            m_ = np.maximum(mu[s], 1e-6)
            x = np.maximum(0, np.round(rng.normal(m_, np.sqrt(C.PTS_VAR_A * m_ + m_ ** 2 / C.DISP[s])))).astype(int)
        else:
            lam = rng.gamma(C.DISP[s], np.maximum(mu[s], 1e-6) / C.DISP[s])
            x = rng.poisson(lam)
        for i, p in enumerate(players):
            out[p["pid"]][s] = x[:, i]
    for p in players:
        o = out[p["pid"]]
        o["pra"] = o["pts"] + o["reb"] + o["ast"]
        o["min"] = mins[:, players.index(p)]
    return out


def _dist(x, maxk):
    x = np.minimum(x, maxk + 1)
    return [float((x >= k).mean()) for k in range(maxk + 2)]


def _fair(ge):
    k = min(range(1, len(ge)), key=lambda k: abs(ge[k] - 0.5))
    return k - 0.5


def american(p):
    return f"-{round(100 * p / (1 - p))}" if p > 0.5 else f"+{round(100 * (1 - p) / p)}"


def summarize(arrs, info, book):
    """Distribution summary per stat (in games the player plays) plus the call against the book."""
    from .odds import no_vig
    rows = []
    for pid, stats in arrs.items():
        p = info[pid]
        play = stats["play"]
        if play.mean() < 0.05:
            continue
        rec = {"pid": pid, "name": p["name"], "team": p["team"], "pos": p["pos"], "min": r(float(stats["min"][play].mean())),
               "avail": r(100 * float(play.mean())), "status": p.get("status"), "inj": p.get("inj"), "m": {}}
        for st in C.PROP_STATS:
            x = stats[st][play]
            ge = _dist(x, MAXK[st])
            m = {"mean": r(x.mean(), 1), "fair": _fair(ge), "ge": [round(v, 3) for v in ge]}
            b = (book or {}).get(norm_name(p["name"]), {}).get(st)
            if b and b.get("line") is not None and b.get("over") and b.get("under"):
                L = float(b["line"])
                po = float((x > L).mean()) / max(1e-9, 1 - float((x == L).mean()))
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


def alt_parlay(arrs, info, game, book, team_legs=(), need_team=False):
    """Model alt-line SGP at fair odds of +100 to +125 (same target as the NHL and NFL): 'alt down' player legs
    (Overs below the main line) rated 70%+, from both teams, plus Pinnacle-priced team legs when asked.
    Uses the simulated games, so legs that hit together are priced together. Questionable players are left out."""
    data = Path(__file__).resolve().parents[1] / "docs" / "nba" / "data"
    cands = []
    for pid, stats in arrs.items():
        p = info[pid]
        if p.get("avail", 1.0) < 0.99:
            continue                                   # anyone on the injury report: a leg could be voided
        for st in ("pts", "reb", "ast", "fg3m"):
            x = stats[st]
            b = (book or {}).get(norm_name(p["name"]), {}).get(st)
            main = float(b["line"]) if b and b.get("line") is not None else _fair(_dist(x, MAXK[st]))
            src = "book" if b and b.get("line") is not None else "model"
            k_main = int(main + 0.5)
            for kk in range(max(1, k_main - C.ALT_DROP[st]), k_main + 1):
                hit = x >= kk
                ph = float(hit.mean())
                if C.ALT_LEG_RANGE[0] <= ph <= C.ALT_LEG_RANGE[1]:
                    cands.append({"pid": pid, "name": p["name"], "team": p["team"], "stat": st, "line": kk - 0.5,
                                  "p": ph, "p_raw": ph, "main": main, "main_src": src, "hit": hit})
    booked = [c for c in cands if c["main_src"] == "book"]
    if len(booked) >= 4:
        cands = booked
    # keep each player's best few legs so the search stays small
    cands.sort(key=lambda c: -c["p"])
    per, keep = {}, []
    for c in cands:
        k_ = (c["pid"], c["stat"])
        if per.get(k_, 0) < 2:
            per[k_] = per.get(k_, 0) + 1
            keep.append(c)
    cands = keep[:80]
    home, away = game["home"], game["away"]
    tl_c = [{**t, "pid": "T:" + t["label"], "name": "", "team": t.get("teamname"), "stat": "team:" + t["market"],
             "main": None, "main_src": "pinnacle"} for t in team_legs]
    if need_team:
        if not tl_c:
            return None
        cands = tl_c + cands
    if len(cands) < 2:
        return None
    lo, hi = C.ALT_TARGET_P

    def joint(idx, h):
        pj = float(h.mean())
        for i in idx:
            pj *= cands[i]["p"] / cands[i]["p_raw"]
        return min(pj, min(cands[i]["p"] for i in idx))

    def search(size):
        beams = [((i,), cands[i]["hit"], cands[i]["p"]) for i in range(len(cands)) if not need_team or i < len(tl_c)]
        for step in range(size - 1):
            last = step == size - 2
            nxt = []
            for idx, h, _p in beams:
                used = {cands[i]["pid"] for i in idx}
                tl = [cands[i] for i in idx if cands[i].get("kind") == "team"]
                for j in range(idx[-1] + 1, len(cands)):
                    c = cands[j]
                    if c["pid"] in used:
                        continue
                    if c.get("kind") == "team" and (len(tl) >= C.ALT_MAX_TEAM_LEGS or any(x["stat"] == c["stat"] for x in tl)):
                        continue
                    hj = h & c["hit"]
                    pj = joint(idx + (j,), hj)
                    if pj >= lo and (not last or pj <= hi):
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
    try:                                                 # ticket chance moves toward its own graded record (as NHL)
        tr = (json.loads((data / "latest.json").read_text()).get("tracking") or {}).get("alt_mix" if need_team else "alt") or {}
        n_, m_ = tr.get("n") or 0, (tr.get("model") or 0) / 100
        a_ = (tr.get("hits") or 0) / n_ if n_ else 0
        if n_ >= 10 and 0 < m_ < 1 and 0 < a_ < 1:
            shift = (np.log(a_ / (1 - a_)) - np.log(m_ / (1 - m_))) * n_ / (n_ + C.ALT_TICKET_K)
            pj = float(1 / (1 + np.exp(-(np.log(pj / (1 - pj)) + shift))))
    except Exception:  # noqa: BLE001
        pass

    def leg(c):
        if c.get("kind") == "team":
            return {"kind": "team", "market": c["market"], "team": c["team_side"], "side": c["side"], "line": c["line"], "name": "",
                    "label": c["label"], "p": r(100 * c["p"]), "p_model": r(100 * c["p_model"]), "main_src": "pinnacle"}
        return {"pid": c["pid"], "name": c["name"], "team": c["team"], "stat": c["stat"], "line": c["line"],
                "label": f"Over {c['line']:g} {LABEL[c['stat']]}", "p": r(100 * c["p"]), "main": c["main"], "main_src": c["main_src"]}
    dec = (1 + C.ALT_BET_CUSHION) / pj
    bet = f"+{round(100 * (dec - 1))}" if dec >= 2 else str(round(-100 / (dec - 1)))
    return {"v": 5 if need_team else 3, "p": r(100 * pj), "p_sim": r(100 * raw), "pi": r(100 * pi), "fair": american(pj),
            "bet_at": bet, "cushion": C.ALT_BET_CUSHION, "legs": [leg(c) for c in legs]}
