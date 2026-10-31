"""
Team ratings: offense and defense in points per game, from every game's final score, newer games
counting more. Each game says
    home points = league + HCA/2 + home offense + away defense + adjustments
    away points = league - HCA/2 + away offense + home defense + adjustments
and a weighted ridge fit solves for all 30 offenses and defenses at once, so a team's numbers are
already adjusted for who it played. Margin and total both come from the same fit.

Adjustments, fixed from past seasons (fit_adjust): back-to-backs, and lineup strength, the value of
regular rotation players who sat (game score per minute above a replacement level, times their usual
minutes). The same lineup number is built for upcoming games from the injury report.
"""
import numpy as np
import pandas as pd

from . import config as C


def gamescore(p):
    """Hollinger game score from box columns (a DataFrame or row)."""
    return (p["pts"] + 0.4 * p["fgm"] - 0.7 * p["fga"] - 0.4 * (p["fta"] - p["ftm"]) + 0.7 * p["oreb"] + 0.3 * p["dreb"]
            + p["stl"] + 0.7 * p["ast"] + 0.7 * p["blk"] - 0.4 * p["pf"] - p["tov"])


def player_form(pg: pd.DataFrame, games: pd.DataFrame):
    """Per player and team-game, the player's usual minutes and value BEFORE that game (last C.FORM_N team games).
    Returns a frame: game_id, team, pid, exp_min, val_pm, played."""
    g = games[["game_id", "start"]].copy()
    p = pg.merge(g, on="game_id")
    p = p.sort_values("start")
    p["gs"] = gamescore(p.fillna(0))
    p["played"] = (~p["dnp"].astype(bool)) & (p["min"] > 0)
    out = []
    for team, tp in p.groupby("team"):
        gids = list(dict.fromkeys(tp["game_id"]))              # this team's games in order
        idx = {gid: i for i, gid in enumerate(gids)}
        tp = tp.assign(gi=tp["game_id"].map(idx))
        mins = tp.pivot_table(index="gi", columns="pid", values="min", aggfunc="sum").reindex(range(len(gids))).fillna(0.0)
        gsv = tp.pivot_table(index="gi", columns="pid", values="gs", aggfunc="sum").reindex(range(len(gids))).fillna(0.0)
        # rolling over the previous FORM_N team games (shifted: before the game)
        rm = mins.rolling(C.FORM_N, min_periods=1).mean().shift(1)
        apps = (mins > 0).rolling(C.FORM_N, min_periods=1).sum().shift(1)
        rg = gsv.rolling(C.FORM_N, min_periods=1).sum().shift(1)
        rmin = mins.rolling(C.FORM_N, min_periods=1).sum().shift(1)
        vpm = (rg + C.VAL_PRIOR_MIN * C.VAL_REPL) / (rmin + C.VAL_PRIOR_MIN)
        played = mins > 0
        for gi, gid in enumerate(gids):
            if gi == 0:
                continue
            m_, a_, v_ = rm.iloc[gi], apps.iloc[gi], vpm.iloc[gi]
            reg = (m_ >= C.ROT_MIN) & (a_ >= C.ROT_APPS)
            for pid in m_.index[reg.values]:
                out.append((gid, team, pid, float(m_[pid]), float(v_[pid]), bool(played.iloc[gi][pid])))
    return pd.DataFrame(out, columns=["game_id", "team", "pid", "exp_min", "val_pm", "played"])


def lineup_loss(form):
    """Value of regular rotation players who sat, per team-game (points-ish units; scaled by C.LINEUP_K)."""
    f = form[~form["played"]].copy()
    f["loss"] = f["exp_min"] * (f["val_pm"] - C.VAL_REPL).clip(lower=0)
    return f.groupby(["game_id", "team"])["loss"].sum()


def team_frame(games: pd.DataFrame, loss=None):
    """One row per game with rest and lineup features."""
    g = games.copy()
    g["start_dt"] = pd.to_datetime(g["start"], utc=True)
    g["d"] = pd.to_datetime(g["date"])
    last, b2b = {}, {}
    for r in g.sort_values("start_dt").itertuples():
        for t, k in ((r.home, "h"), (r.away, "a")):
            pv = last.get(t)
            b2b[(r.Index, k)] = float(pv is not None and (r.d - pv).days == 1)
            last[t] = r.d
    g["b2b_h"] = [b2b.get((i, "h"), 0.0) for i in g.index]
    g["b2b_a"] = [b2b.get((i, "a"), 0.0) for i in g.index]
    if loss is not None:
        g["loss_h"] = [loss.get((gid, t), 0.0) for gid, t in zip(g["game_id"], g["home"])]
        g["loss_a"] = [loss.get((gid, t), 0.0) for gid, t in zip(g["game_id"], g["away"])]
    else:
        g["loss_h"] = g["loss_a"] = 0.0
    return g


TEAMS = sorted(["ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DAL", "DEN", "DET", "GSW", "HOU", "IND", "LAC", "LAL", "MEM", "MIA",
                "MIL", "MIN", "NOP", "NYK", "OKC", "ORL", "PHI", "PHX", "POR", "SAC", "SAS", "TOR", "UTA", "WAS"])
TI = {t: i for i, t in enumerate(TEAMS)}


def adj_pts(g, coef):
    """Points adjustment for (home, away) from rest and lineups."""
    ah = -coef["b2b"] * g["b2b_h"] - coef["loss_own"] * g["loss_h"] + coef["loss_opp"] * g["loss_a"]
    aa = -coef["b2b"] * g["b2b_a"] - coef["loss_own"] * g["loss_a"] + coef["loss_opp"] * g["loss_h"]
    return ah, aa


def fit(past: pd.DataFrame, asof, season, coef):
    """Ratings from games before `asof`. Returns dict with league, hca, off, def arrays."""
    w = C.DECAY ** ((asof - past["start_dt"]).dt.total_seconds() / 86400)
    w = w * np.where(past["season"] == season, 1.0, C.PREV_SEASON_WEIGHT)
    if "type" in past:
        w = w * np.where(past["type"] == "post", C.PLAYOFF_WEIGHT, 1.0)
    ah, aa = adj_pts(past, coef)
    n = len(past)
    X = np.zeros((2 * n, 2 + 2 * len(TEAMS)))
    y = np.concatenate([past["hs"].values - ah.values, past["as"].values - aa.values]).astype(float)
    X[:, 0] = 1.0
    X[:n, 1], X[n:, 1] = 0.5, -0.5
    rows, T = np.arange(n), len(TEAMS)
    hi, ai = past["home"].map(TI).values, past["away"].map(TI).values
    X[rows, 2 + hi] = 1.0                                    # home offense
    X[rows, 2 + T + ai] = 1.0                                # away defense
    X[n + rows, 2 + ai] = 1.0                                # away offense
    X[n + rows, 2 + T + hi] = 1.0                            # home defense
    neutral = past["neutral"].astype(bool).values
    X[:n, 1][neutral] = 0.0
    X[n:, 1][neutral] = 0.0
    ww = np.concatenate([w, w])
    lam = np.r_[0.0, 0.0, np.full(2 * len(TEAMS), C.RIDGE)]
    A = (X * ww[:, None]).T @ X + np.diag(lam)
    b = (X * ww[:, None]).T @ y
    beta = np.linalg.solve(A, b)
    return {"league": beta[0], "hca": beta[1], "off": beta[2:2 + len(TEAMS)], "def": beta[2 + len(TEAMS):]}


def predict(rt, home, away, adj_h=0.0, adj_a=0.0, neutral=False):
    h = 0.0 if neutral else rt["hca"] / 2
    ph = rt["league"] + h + rt["off"][TI[home]] + rt["def"][TI[away]] + adj_h
    pa = rt["league"] - h + rt["off"][TI[away]] + rt["def"][TI[home]] + adj_a
    return ph, pa


def walk(g: pd.DataFrame, coef, start_season=None, refit_days=1):
    """Out-of-sample predictions for every game, refitting on each new date with only earlier games."""
    g = g.sort_values("start_dt").reset_index(drop=True)
    preds = np.full((len(g), 2), np.nan)
    ah, aa = adj_pts(g, coef)
    for d, idx in g.groupby(g["d"]).groups.items():
        s = int(g.loc[idx[0], "season"])
        if start_season and s < start_season:
            continue
        past = g[g["d"] < d]
        past = past[past["season"] >= s - 1]
        if (past["season"] == s).sum() < 1 and len(past) < 200:
            continue
        rt = fit(past, g.loc[idx[0], "start_dt"], s, coef)
        for i in idx:
            r = g.loc[i]
            preds[i] = predict(rt, r["home"], r["away"], ah[i], aa[i], bool(r["neutral"]))
    g["p_h"], g["p_a"] = preds[:, 0], preds[:, 1]
    return g
