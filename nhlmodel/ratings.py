"""
Team form going into every game: exponentially weighted per-60 rates with a
pull toward league average, carried across seasons at reduced weight.
"""
import numpy as np
import pandas as pd

from . import config as C

STATS = {k: k for k in ("xgf", "xga", "gf", "ga", "gfq", "gaq", "sogf", "soga")}   # regulation, per game


def pregame(tg: pd.DataFrame):
    """tg from data.team_games. Returns tg with pre_<stat> columns (per 60) and rest days."""
    tg = tg.sort_values(["date", "gameId"]).reset_index(drop=True)
    per60 = {k: tg[v].to_numpy(float) for k, v in STATS.items()}
    league = {}
    for s, grp in tg.groupby("season"):
        league[s] = {k: float(np.mean(per60[k][grp.index])) for k in STATS}
    state = {}
    pre = {k: np.zeros(len(tg)) for k in STATS}
    rest = np.zeros(len(tg))
    gp = np.zeros(len(tg))
    d = C.FORM_DECAY
    lgS = {k: 0.0 for k in STATS}; lgW = 0.0               # league level going into each game
    lgpre = {k: np.zeros(len(tg)) for k in ("gf", "xgf", "sogf", "gfq")}
    first = tg["season"].min()
    for k in STATS:
        lgS[k] = 50 * league[first][k]
    lgW = 50.0
    for i, r in enumerate(tg.itertuples(index=False)):
        t, s = r.team, r.season
        L = league.get(s) or league[max(league)]
        st = state.get(t)
        if st is None or st["season"] != s:
            L = {k: lgS[k] / lgW for k in STATS}             # league level as of now, no peeking ahead
            carry = C.FORM_CARRY if st is not None else 0.0
            old = st
            st = {"season": s, "last": old["last"] if old else None, "n": 0}
            for k in STATS:
                prevS, prevW = (old[k + "_S"], old[k + "_W"]) if old else (0.0, 0.0)
                # pull last season toward this season's league level, keep only part of its weight
                ratio = prevS / prevW / (league.get(old["season"], L)[k]) if old and prevW else 1.0
                st[k + "_S"] = carry * prevW * ratio * L[k] + C.FORM_PRIOR * L[k]
                st[k + "_W"] = carry * prevW + C.FORM_PRIOR
            state[t] = st
        for k in STATS:
            pre[k][i] = st[k + "_S"] / st[k + "_W"]
        rest[i] = (r.date - st["last"]).days if st["last"] is not None else 7
        gp[i] = st["n"]
        for k in lgpre:
            lgpre[k][i] = lgS[k] / lgW
        for k in STATS:
            lgS[k] = C.LEAGUE_DECAY * lgS[k] + per60[k][i]
        lgW = C.LEAGUE_DECAY * lgW + 1.0
        for k in STATS:
            st[k + "_S"] = d * st[k + "_S"] + per60[k][i]
            st[k + "_W"] = d * st[k + "_W"] + 1.0
        st["last"], st["n"] = r.date, st["n"] + 1
    for k in STATS:
        tg["pre_" + k] = pre[k]
    tg["rest"] = rest
    tg["gp"] = gp
    tg["lg_g"], tg["lg_xg"], tg["lg_sog"] = lgpre["gf"], lgpre["xgf"], lgpre["sogf"]
    tg["lg_fin"] = lgpre["gfq"] / lgpre["xgf"]               # league goals per expected goal right now
    state["_league"] = {k: lgS[k] / lgW for k in STATS}
    return tg, league, state


def current(state, league, season):
    """Latest form for every team, for upcoming games."""
    L = league.get(season) or league[max(league)]
    out = {}
    for t, st in state.items():
        if t == "_league":
            continue
        if st["season"] == season:
            out[t] = {k: st[k + "_S"] / st[k + "_W"] for k in STATS}
        else:                                             # no game yet this season
            out[t] = {k: (C.FORM_CARRY * st[k + "_S"] + C.FORM_PRIOR * L[k]) / (C.FORM_CARRY * st[k + "_W"] + C.FORM_PRIOR) for k in STATS}
        out[t]["last"] = st["last"]
        out[t]["gp"] = st["n"] if st["season"] == season else 0
    return out, state["_league"]
