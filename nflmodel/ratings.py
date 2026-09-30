"""
Team power ratings.

How it works (plain English):
  Every offensive play gets an EPA value (expected points added).
  We fit one equation across all plays:  EPA = league avg + offense skill + defense weakness
  so a team's rating is automatically adjusted for who they played.
  We fit it three times: all plays, pass plays only, run plays only,
  which lets a good passing offense get credit against a weak pass defense.
"""
from dataclasses import dataclass, field
import numpy as np
import pandas as pd
from scipy import sparse

from . import config as C
from .util import play_weights, before, shrink


def offense_plays(pbp: pd.DataFrame) -> pd.DataFrame:
    p = pbp[((pbp["pass"] == 1) | (pbp["rush"] == 1))
            & pbp["epa"].notna() & pbp["posteam"].notna() & pbp["defteam"].notna()]
    if "two_point_attempt" in p.columns:
        p = p[p["two_point_attempt"] != 1]
    p = p.copy()
    p["is_pass"] = (p["pass"] == 1).astype(int)
    p["is_home"] = (p["posteam"] == p["home_team"]).astype(int)
    return p


def fit_ridge(p: pd.DataFrame, w: np.ndarray, alpha: float, teams: list):
    """Weighted ridge: epa ~ intercept + offense[team] + defense[team] + home."""
    keep = w > 0
    p, w = p[keep], w[keep]
    T = len(teams)
    idx = {t: i for i, t in enumerate(teams)}
    n = len(p)
    if n == 0:
        z = pd.Series(0.0, index=teams)
        return {"intercept": 0.0, "off": z, "def": z.copy(), "home": 0.0, "n": 0}
    oi = p["posteam"].map(idx).to_numpy()
    di = p["defteam"].map(idx).to_numpy() + T
    hi = np.where(p["is_home"].to_numpy() == 1, 2 * T, -1)
    rows = np.concatenate([np.arange(n), np.arange(n), np.arange(n)[hi >= 0]])
    cols = np.concatenate([oi, di, hi[hi >= 0]])
    X = sparse.csr_matrix((np.ones(len(rows)), (rows, cols)), shape=(n, 2 * T + 1))
    y = p["epa"].to_numpy(dtype=float)

    ws = w.sum()
    ybar = (w * y).sum() / ws
    xbar = np.asarray(X.T @ w).ravel() / ws
    G = (X.T @ X.multiply(w[:, None])).toarray() - ws * np.outer(xbar, xbar)
    b = np.asarray(X.T @ (w * y)).ravel() - ws * xbar * ybar
    pen = np.full(2 * T + 1, alpha)
    pen[-1] = alpha * 0.01
    beta = np.linalg.solve(G + np.diag(pen), b)
    intercept = ybar - xbar @ beta

    off = pd.Series(beta[:T], index=teams)
    de = pd.Series(beta[T:2 * T], index=teams)
    intercept += off.mean() + de.mean()
    return {"intercept": float(intercept), "off": off - off.mean(), "def": de - de.mean(),
            "home": float(beta[-1]), "n": int(n)}


@dataclass
class Context:
    season: int
    week: int
    teams: list
    all: dict
    pas: dict
    run: dict
    lg_plays: float
    lg_pts: float
    lg_pass_rate: float
    off_pace: pd.Series
    def_pace: pd.Series
    proe: pd.Series
    sack_off: pd.Series
    sack_def: pd.Series
    lg_sack: float
    def_ypa_mult: pd.Series
    def_cmp_mult: pd.Series
    def_ypc_mult: pd.Series
    pass_td_share: pd.Series
    team_db_epa: pd.Series = field(default=None)
    scheme: dict = field(default=None)
    press_off: pd.Series = field(default=None)   # pressure allowed per dropback
    press_def: pd.Series = field(default=None)   # pressure generated per dropback
    lg_press: float = 0.15


def _wmean_by(df, key, val, w):
    g = pd.DataFrame({"k": df[key].to_numpy(), "v": val * w, "w": w})
    s = g.groupby("k")[["v", "w"]].sum()
    return s["v"], s["w"]


def build_context(pbp_all: pd.DataFrame, schedules: pd.DataFrame,
                  season: int, week: int) -> Context:
    pbp = before(pbp_all, season, week)
    p = offense_plays(pbp)
    teams = sorted(set(p["posteam"].unique()) | set(p["defteam"].unique()))
    w = play_weights(p, season, week)

    r_all = fit_ridge(p, w, C.RIDGE_ALPHA_ALL, teams)
    mp = p["is_pass"].to_numpy() == 1
    r_pas = fit_ridge(p[mp], w[mp], C.RIDGE_ALPHA_SPLIT, teams)
    r_run = fit_ridge(p[~mp], w[~mp], C.RIDGE_ALPHA_SPLIT, teams)

    # ---- pace: offensive plays per game, weighted by game recency ----
    gw = play_weights(p, season, week, garbage=False)
    games = p.assign(gw=gw).groupby(["game_id", "posteam", "defteam"]).agg(
        plays=("epa", "size"), gw=("gw", "mean")).reset_index()
    games = games[games["gw"] > 0]
    lg_plays = float(np.average(games["plays"], weights=games["gw"])) if len(games) else 62.0

    def pace(key):
        v, ww = _wmean_by(games, key, games["plays"].to_numpy(), games["gw"].to_numpy())
        return pd.Series(shrink(v, ww, lg_plays, 3.0), index=v.index).reindex(teams).fillna(lg_plays)

    off_pace, def_pace = pace("posteam"), pace("defteam")

    # ---- pass rate over expected in neutral situations ----
    lg_pass_rate = float(np.average(p["is_pass"], weights=np.maximum(gw, 1e-9)))
    neutral = (p["wp"].between(0.2, 0.8)) & (p["down"].isin([1, 2, 3])) & \
              (p["half_seconds_remaining"].fillna(900) > 120)
    pn, wn = p[neutral], gw[neutral.to_numpy()]
    if "xpass" in pn.columns and pn["xpass"].notna().mean() > 0.5:
        oe = (pn["is_pass"] - pn["xpass"].fillna(pn["is_pass"].mean())).to_numpy()
    else:
        oe = (pn["is_pass"] - pn["is_pass"].mean()).to_numpy()
    v, ww = _wmean_by(pn, "posteam", oe, wn)
    proe = pd.Series(shrink(v, ww, 0.0, 150), index=v.index).reindex(teams).fillna(0.0)

    # ---- sacks, defensive yards allowed (used by player projections) ----
    db = p[p["qb_dropback"] == 1]
    wdb = gw[(p["qb_dropback"] == 1).to_numpy()]
    lg_sack = float(np.average(db["sack"], weights=np.maximum(wdb, 1e-9))) if len(db) else 0.065
    v, ww = _wmean_by(db, "posteam", db["sack"].to_numpy(), wdb)
    sack_off = pd.Series(shrink(v, ww, lg_sack, 200), index=v.index).reindex(teams).fillna(lg_sack)
    v, ww = _wmean_by(db, "defteam", db["sack"].to_numpy(), wdb)
    sack_def = pd.Series(shrink(v, ww, lg_sack, 200), index=v.index).reindex(teams).fillna(lg_sack)

    att = p[(p["pass_attempt"] == 1) & (p["sack"] == 0)]
    watt = gw[((p["pass_attempt"] == 1) & (p["sack"] == 0)).to_numpy()]
    lg_ypa = float(np.average(att["yards_gained"].fillna(0), weights=np.maximum(watt, 1e-9)))
    lg_cmp = float(np.average(att["complete_pass"], weights=np.maximum(watt, 1e-9)))
    v, ww = _wmean_by(att, "defteam", att["yards_gained"].fillna(0).to_numpy(), watt)
    def_ypa_mult = (pd.Series(shrink(v, ww, lg_ypa, C.DEF_SHRINK_K), index=v.index) / lg_ypa)
    v, ww = _wmean_by(att, "defteam", att["complete_pass"].to_numpy(), watt)
    def_cmp_mult = (pd.Series(shrink(v, ww, lg_cmp, C.DEF_SHRINK_K), index=v.index) / lg_cmp)

    ru = p[(p["is_pass"] == 0)]
    wru = gw[(p["is_pass"] == 0).to_numpy()]
    lg_ypc = float(np.average(ru["yards_gained"].fillna(0), weights=np.maximum(wru, 1e-9)))
    v, ww = _wmean_by(ru, "defteam", ru["yards_gained"].fillna(0).to_numpy(), wru)
    def_ypc_mult = (pd.Series(shrink(v, ww, lg_ypc, C.DEF_SHRINK_K), index=v.index) / lg_ypc)

    # ---- share of TDs through the air ----
    td = p[(p["touchdown"] == 1) & (p.get("td_team", p["posteam"]) == p["posteam"])]
    wtd = gw[((p["touchdown"] == 1) & (p.get("td_team", p["posteam"]) == p["posteam"])).to_numpy()]
    v, ww = _wmean_by(td, "posteam", td["is_pass"].to_numpy(dtype=float), wtd)
    pass_td_share = pd.Series(shrink(v, ww, C.LEAGUE_PASS_TD_SHARE, 12), index=v.index)

    # ---- pass rush vs protection (sack or QB hit per dropback) ----
    pr_flag = ((db["sack"] == 1) | (db.get("qb_hit", 0) == 1)).astype(float).to_numpy()
    lg_press = float(np.average(pr_flag, weights=np.maximum(wdb, 1e-9))) if len(db) else 0.15
    v, ww = _wmean_by(db, "posteam", pr_flag, wdb)
    press_off = pd.Series(shrink(v, ww, lg_press, 250), index=v.index).reindex(teams).fillna(lg_press)
    v, ww = _wmean_by(db, "defteam", pr_flag, wdb)
    press_def = pd.Series(shrink(v, ww, lg_press, 250), index=v.index).reindex(teams).fillna(lg_press)

    # ---- team EPA per dropback (baseline for QB changes) ----
    v, ww = _wmean_by(db, "posteam", db["epa"].to_numpy(dtype=float), wdb)
    team_db_epa = (v / ww.replace(0, np.nan)).reindex(teams)

    # ---- league points per team game ----
    sch = schedules.copy()
    done = sch[sch["home_score"].notna() & (
        ((sch["season"] == season) & (sch["week"] < week)) | (sch["season"] == season - 1))]
    lg_pts = float(pd.concat([done["home_score"], done["away_score"]]).mean()) if len(done) else 22.5

    fill = lambda s, d: s.reindex(teams).fillna(d)
    return Context(season, week, teams, r_all, r_pas, r_run, lg_plays, lg_pts, lg_pass_rate,
                   off_pace, def_pace, proe, sack_off, sack_def, lg_sack,
                   fill(def_ypa_mult, 1.0), fill(def_cmp_mult, 1.0), fill(def_ypc_mult, 1.0),
                   fill(pass_td_share, C.LEAGUE_PASS_TD_SHARE), team_db_epa,
                   press_off=press_off, press_def=press_def, lg_press=lg_press)


def team_pass_rate(ctx: Context, team: str) -> float:
    return float(np.clip(ctx.lg_pass_rate + ctx.proe.get(team, 0.0), 0.42, 0.72))


def matchup_epa(ctx: Context, off: str, de: str) -> float:
    """Above-average EPA per play for `off` against `de` (no home field)."""
    comb = ctx.all["off"].get(off, 0) + ctx.all["def"].get(de, 0)
    pr = team_pass_rate(ctx, off)
    split = pr * (ctx.pas["off"].get(off, 0) + ctx.pas["def"].get(de, 0)) + \
        (1 - pr) * (ctx.run["off"].get(off, 0) + ctx.run["def"].get(de, 0))
    return C.SPLIT_BLEND * split + (1 - C.SPLIT_BLEND) * comb


def matchup_plays(ctx: Context, off: str, de: str) -> float:
    return ctx.lg_plays * (ctx.off_pace.get(off, ctx.lg_plays) / ctx.lg_plays) * \
        (ctx.def_pace.get(de, ctx.lg_plays) / ctx.lg_plays)


def raw_points(ctx: Context, off: str, de: str) -> tuple[float, float]:
    plays = matchup_plays(ctx, off, de)
    return ctx.lg_pts + matchup_epa(ctx, off, de) * plays, plays


def ratings_table(ctx: Context) -> list[dict]:
    """Ratings converted to points per game vs an average team."""
    k = ctx.lg_plays
    out = []
    for t in ctx.teams:
        off = ctx.all["off"].get(t, 0) * k
        de = -ctx.all["def"].get(t, 0) * k  # positive = good defense
        out.append({
            "team": t, "net": off + de, "off": off, "def": de,
            "off_pass": ctx.pas["off"].get(t, 0) * k * 0.6,
            "off_rush": ctx.run["off"].get(t, 0) * k * 0.4,
            "def_pass": -ctx.pas["def"].get(t, 0) * k * 0.6,
            "def_rush": -ctx.run["def"].get(t, 0) * k * 0.4,
            "pace": ctx.off_pace.get(t, k), "proe": ctx.proe.get(t, 0) * 100,
        })
    out.sort(key=lambda r: -r["net"])
    return out
