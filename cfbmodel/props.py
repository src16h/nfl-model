"""
Player props from the game simulation.

Each simulated game has a score for both teams. From the score come team
passing and rushing totals (teams that are ahead run more, teams that are
behind throw more), and those are shared among the players by their recent
roles: the quarterback's share of the passing, each back's share of the
carries, each receiver's share of the catches. Because every player lives in
the same simulated game, a big passing day lifts the quarterback and his
receivers together, which is what the alt-line parlays use.
"""
import logging

import numpy as np
import pandas as pd

from . import config as C
from .util import norm_name, r

log = logging.getLogger("cfbmodel")
STAT_COLS = ["pass_cmp", "pass_att", "pass_yds", "pass_td", "rush_att", "rush_yds", "rush_td", "rec", "rec_yds", "rec_td"]
COUNT_MAX = {"pass_td": 7, "rec": 14, "td": 4}
QS = np.round(np.arange(0.025, 0.99, 0.025), 3)          # stored percentiles for yardage stats
CARRY_CONC, REC_CONC = 22.0, 16.0                        # how steady carry and catch shares are game to game
CARRY_SD, CATCH_SHAPE = 6.0, 1.15                        # yards spread per carry, shape of yards per catch
ALT_LADDER = {"pass_yds": [100, 125, 150, 175, 200, 225, 250, 275, 300, 325, 350],
              "rush_yds": [10, 15, 20, 25, 30, 40, 50, 60, 70, 80, 90, 100, 110, 125, 150],
              "rec_yds": [10, 15, 20, 25, 30, 40, 50, 60, 70, 80, 90, 100, 110, 125, 150],
              "rec": [2, 3, 4, 5, 6, 7, 8]}
LABEL = {"pass_yds": "passing yards", "rush_yds": "rushing yards", "rec_yds": "receiving yards", "rec": "receptions",
         "pass_td": "passing TDs", "td": "touchdown"}


def roles(pg, team_id, season_of, season, before=None):
    """Recent roles for one team's players. Returns (players list, team baselines) or (None, None)."""
    t = pg[pg["team_id"] == team_id]
    if before is not None:
        t = t[t["date"] < before]
    if t.empty:
        return None, None
    t = t.copy()
    t[STAT_COLS] = t[STAT_COLS].fillna(0.0)
    gl = t.drop_duplicates("game_id")[["game_id", "date"]].sort_values(["date", "game_id"])
    gl["season"] = gl["game_id"].map(season_of)
    gl = gl[gl["season"] >= season - 1]
    if gl.empty:
        return None, None
    cur = gl[gl["season"] == season]
    age = np.arange(len(gl))[::-1]
    fade = max(0.0, 1.0 - len(cur) / 4.0)              # last season stops counting once 4 games are played
    gl["w"] = C.PLAYER_DECAY ** age * np.where(gl["season"] < season, C.PREV_SEASON_WEIGHT * fade, 1.0)
    gl = gl[gl["w"] > 0]
    t = t.merge(gl[["game_id", "w", "season"]], on="game_id")
    tw = t.groupby("game_id")[STAT_COLS].sum().join(gl.set_index("game_id")["w"])
    tot = {c: float((tw[c] * tw["w"]).sum()) for c in STAT_COLS}
    recent = set(gl["game_id"].tail(2))
    out = []
    for pid, x in t.groupby("pid"):
        if not (set(x["game_id"]) & recent):
            continue                                   # not in either of the last two box scores
        s = {c: float((x[c] * x["w"]).sum()) for c in STAT_COLS}
        xc = x[x["season"] == season]
        gp = len(xc)
        rec = {"pid": int(pid), "name": x.sort_values("date")["name"].iloc[-1], "team_id": int(team_id), "gp": gp,
               "pass_share": s["pass_att"] / max(tot["pass_att"], 1e-9), "carry_share": s["rush_att"] / max(tot["rush_att"], 1e-9),
               "rec_share": s["rec"] / max(tot["rec"], 1e-9),
               "w_car": s["rush_att"], "w_rec": s["rec"], "w_ry": s["rush_yds"], "w_cy": s["rec_yds"],
               "rush_td_share": (s["rush_td"] + 3.0 * s["rush_att"] / max(tot["rush_att"], 1e-9)) / (tot["rush_td"] + 3.0),
               "rec_td_share": (s["rec_td"] + 3.0 * s["rec_yds"] / max(tot["rec_yds"], 1e-9)) / (tot["rec_td"] + 3.0),
               "avg": {k: r(xc[k].mean(), 1) for k in ("pass_yds", "rush_yds", "rec_yds", "rec")} if gp else None,
               "last": {k: r(x.sort_values("date")[k].iloc[-1], 0) for k in ("pass_yds", "rush_yds", "rec_yds", "rec")}}
        out.append(rec)
    if not out:
        return None, None
    qb = max(out, key=lambda p: p["pass_share"])
    last2 = t[t["game_id"].isin(recent)]
    att2 = float(last2["pass_att"].sum())
    for p in out:                                       # share of the passing in the last two games: who the quarterback is now
        p["pass_recent"] = float(last2.loc[last2["pid"] == p["pid"], "pass_att"].sum()) / max(att2, 1.0)
    qb = max(out, key=lambda p: (p["pass_recent"], p["pass_share"]))
    qb["pass_share"] = max(qb["pass_share"], qb["pass_recent"])
    team_ypc_rb = (tot["rush_yds"] - qb["w_ry"]) / max(tot["rush_att"] - qb["w_car"], 1.0)
    team_ypr = tot["rec_yds"] / max(tot["rec"], 1.0)
    for p in out:
        is_qb = p is qb and p["pass_share"] > 0.3
        p["qb"] = is_qb
        prior_ypc = 2.5 if is_qb else float(np.clip(team_ypc_rb, 3.5, 5.5))
        p["ypc"] = (p["w_ry"] + 12.0 * prior_ypc) / (p["w_car"] + 12.0)
        p["ypr"] = (p["w_cy"] + 6.0 * float(np.clip(team_ypr, 10.0, 14.0))) / (p["w_rec"] + 6.0)
        p["pos"] = "QB" if is_qb else ("RB" if p["carry_share"] > 1.5 * p["rec_share"] else "WR")
    base = {"qb": qb if qb["pass_share"] > 0.3 else None, "games": int(len(cur)),
            "ypc": tot["rush_yds"] / max(tot["rush_att"], 1.0), "ypr": team_ypr,
            "cmp_rate": tot["pass_cmp"] / max(tot["pass_att"], 1.0)}
    return out, base


def _skew(rng, shape):
    """Right-skewed noise with mean 0 and sd 1."""
    g = rng.gamma(4.0, 1.0, shape)
    return (g - 4.0) / 2.0


def team_players(players, base, tsim, rng, blowout=0.0):
    """Simulated stat arrays for one team's players.
    tsim: dict of team arrays (pass_yds, pass_cmp, rush_att, rush_yds, td_p, td_r). blowout: expected margin size."""
    n = len(tsim["pass_yds"])
    out = {}
    qb = base.get("qb")
    if qb is not None:
        s0 = float(np.clip(qb["pass_share"], 0.5, 0.99))
        q_out = float(np.clip(0.05 + 0.006 * max(abs(blowout) - 14, 0), 0.05, 0.22))     # hurt, benched, or pulled in a blowout
        full = np.minimum(1.0, rng.beta(40 * max(s0, 0.9), 40 * (1 - max(s0, 0.9)) + 0.4, n))
        part = rng.uniform(0.35, 0.9, n)
        share = np.where(rng.random(n) < q_out, part, full)
        out[qb["pid"]] = {"pass_yds": tsim["pass_yds"] * share, "pass_td": rng.binomial(tsim["td_p"], share)}
    # carries
    car = [p for p in players if p["carry_share"] > 0.03]
    if car:
        sh = np.array([p["carry_share"] for p in car])
        other = max(1.0 - sh.sum(), 0.03)
        alpha = CARRY_CONC * np.append(sh, other) / (sh.sum() + other)
        P = rng.dirichlet(alpha, n)
        Cn = _multinomial(rng, tsim["rush_att"], P)
        ypc = np.append([p["ypc"] for p in car], base["ypc"])
        raw = Cn * ypc[None, :] + np.sqrt(Cn) * CARRY_SD * _skew(rng, Cn.shape)
        diff = tsim["rush_yds"] - raw.sum(axis=1)
        raw = raw + diff[:, None] * Cn / np.maximum(Cn.sum(axis=1, keepdims=True), 1)
        tds = np.append([p["rush_td_share"] for p in car], 0.0)
        tds[-1] = max(1.0 - tds[:-1].sum(), 0.02)
        TD = _multinomial(rng, tsim["td_r"], np.tile(tds / tds.sum(), (n, 1)))
        for i, p in enumerate(car):
            out.setdefault(p["pid"], {}).update({"rush_yds": np.rint(raw[:, i]), "_rtd": TD[:, i]})
    # catches
    rc = [p for p in players if p["rec_share"] > 0.03]
    if rc:
        sh = np.array([p["rec_share"] for p in rc])
        other = max(1.0 - sh.sum(), 0.03)
        alpha = REC_CONC * np.append(sh, other) / (sh.sum() + other)
        P = rng.dirichlet(alpha, n)
        Rn = _multinomial(rng, tsim["pass_cmp"], P)
        ypr = np.append([p["ypr"] for p in rc], base["ypr"])
        raw = rng.gamma(np.maximum(Rn, 1e-9) * CATCH_SHAPE, ypr[None, :] / CATCH_SHAPE) * (Rn > 0)
        raw = raw * (tsim["pass_yds"] / np.maximum(raw.sum(axis=1), 1.0))[:, None]
        tds = np.append([p["rec_td_share"] for p in rc], 0.0)
        tds[-1] = max(1.0 - tds[:-1].sum(), 0.02)
        TD = _multinomial(rng, tsim["td_p"], np.tile(tds / tds.sum(), (n, 1)))
        for i, p in enumerate(rc):
            out.setdefault(p["pid"], {}).update({"rec": Rn[:, i], "rec_yds": np.rint(raw[:, i]), "_ctd": TD[:, i]})
    for pid, st in out.items():
        if "_rtd" in st or "_ctd" in st:
            st["td"] = st.pop("_rtd", 0) + st.pop("_ctd", 0)
    return out


def _multinomial(rng, totals, P):
    """Row-wise multinomial with a different total and probability vector per row."""
    totals = np.maximum(np.asarray(totals, int), 0)
    n, k = P.shape
    out = np.zeros((n, k), int)
    left = totals.copy()
    rem = np.ones(n)
    for j in range(k - 1):
        p = np.clip(P[:, j] / np.maximum(rem, 1e-12), 0, 1)
        out[:, j] = rng.binomial(left, p)
        left -= out[:, j]
        rem -= P[:, j]
    out[:, k - 1] = left
    return out


def _fair_count(ge):
    k = min(range(1, len(ge)), key=lambda k: abs(ge[k] - 0.5))
    return k - 0.5


def over(m, x, line):
    return float((x > line).mean())


def summarize(arrs, info, book):
    """Distribution summary per stat plus the call against the book when a line exists."""
    from .odds import no_vig
    rows = []
    for pid, stats in arrs.items():
        p = info[pid]
        rec = {"pid": pid, "name": p["name"], "team": p["team"], "pos": p["pos"], "gp": p.get("gp"), "avg": p.get("avg"), "last": p.get("last"), "m": {}}
        for st, x in stats.items():
            if st in C.MIN_SHOW and float(x.mean()) < C.MIN_SHOW[st]:
                continue
            if st == "rec" and float(x.mean()) < 1.2:
                continue
            if st == "td" and float((x >= 1).mean()) < 0.06:
                continue
            if st in COUNT_MAX:
                xk = np.minimum(x, COUNT_MAX[st] + 1)
                ge = [float((xk >= k).mean()) for k in range(COUNT_MAX[st] + 2)]
                m = {"mean": r(x.mean(), 2), "fair": 0.5 if st == "td" else _fair_count(ge), "ge": [round(v, 3) for v in ge]}
            else:
                q = np.quantile(x, QS)
                m = {"mean": r(x.mean(), 1), "fair": float(np.floor(np.median(x)) + 0.5), "q": [round(float(v), 1) for v in q]}
            b = (book or {}).get(norm_name(p["name"]), {}).get(st)
            if b and b.get("line") is not None and b.get("over") and (b.get("under") or st == "td"):
                L = float(b["line"])
                po = over(m, x, L)
                if b.get("under"):
                    bo = no_vig(b["over"], b["under"])
                else:                                           # anytime TD is posted one-sided: take about 7% of juice off
                    bo = (100 / (b["over"] + 100) if b["over"] > 0 else -b["over"] / (-b["over"] + 100)) / 1.07
                side = "Over" if po - bo >= (1 - po) - (1 - bo) or not b.get("under") else "Under"
                edge = (po - bo) if side == "Over" else (bo - po)
                m["book"] = {"line": L, "over": b["over"], "under": b.get("under"), "book_over": r(100 * bo), "model_over": r(100 * po),
                             "side": side, "edge": r(100 * edge), "odds": b["over"] if side == "Over" else b["under"], "src": b.get("book"),
                             "play": C.PROP_PLAY_MIN * 100 <= 100 * edge <= C.PROP_PLAY_MAX * 100}
            rec["m"][st] = m
        if rec["m"]:
            rows.append(rec)
    return rows


def alt_parlay(arrs, info, book, need_teams=2):
    """Model alt-line parlay: round-number overs under each player's main line, fair odds +100 to +125."""
    lo_p, hi_p = 1 / (1 + C.ALT_PARLAY_ODDS[1] / 100), 1 / (1 + C.ALT_PARLAY_ODDS[0] / 100)
    cands = []
    for pid, stats in arrs.items():
        p = info[pid]
        for st, x in stats.items():
            if st not in ALT_LADDER:
                continue
            b = (book or {}).get(norm_name(p["name"]), {}).get(st)
            main = float(b["line"]) if b and b.get("line") is not None else (float(np.floor(np.median(x)) + 0.5))
            src = "book" if b and b.get("line") is not None else "model"
            floor_ = main * 0.5 if st != "rec" else main - 2
            opts = [k for k in ALT_LADDER[st] if floor_ <= k <= main]
            for k in opts[-3:]:                                # the rungs just under the main line
                hit = x >= k
                ph = float(hit.mean())
                if C.ALT_LEG_RANGE[0] <= ph <= C.ALT_LEG_RANGE[1]:
                    cands.append({"pid": pid, "name": p["name"], "team": p["team"], "stat": st, "line": k - 0.5, "k": k,
                                  "p": ph, "main": main, "main_src": src, "hit": hit})
    booked = [c for c in cands if c["main_src"] == "book"]
    if len(booked) >= 4:
        cands = booked
    if len(cands) < 3:
        return None
    cands.sort(key=lambda c: -c["p"])
    cands = cands[:36]
    best = None
    for size in (C.ALT_PARLAY_LEGS, 3, 5):
        beam = [((), None)]
        for _ in range(size):
            nxt = []
            for idx, joint in beam:
                used = {cands[i]["pid"] for i in idx}
                for i in range((idx[-1] + 1) if idx else 0, len(cands)):
                    c = cands[i]
                    if c["pid"] in used or sum(cands[x]["stat"] == c["stat"] for x in idx) >= 2:
                        continue
                    j = c["hit"] if joint is None else joint & c["hit"]
                    nxt.append((idx + (i,), j))
            nxt.sort(key=lambda t: -float(t[1].mean()) / np.prod([cands[i]["p"] for i in t[0]]))
            beam = nxt[:60]
        for idx, joint in beam:
            legs = tuple(cands[i] for i in idx)
            pj = float(joint.mean())
            if lo_p <= pj <= hi_p and len({c["team"] for c in legs}) >= need_teams:
                pi = float(np.prod([c["p"] for c in legs]))
                if best is None or pj / pi > best[0]:
                    best = (pj / pi, legs, pj, pi)
        if best:
            break
    if not best:
        return None
    _, legs, pj, pi = best
    return {"p": r(100 * pj), "pi": r(100 * pi), "fair": f"+{round(100 * (1 - pj) / pj)}",
            "legs": [{"pid": c["pid"], "name": c["name"], "team": c["team"], "stat": c["stat"], "line": c["line"],
                      "label": f"{c['k']}+ {LABEL[c['stat']]}", "p": r(100 * c["p"]), "main": c["main"], "main_src": c["main_src"]}
                     for c in legs]}
