"""
Correlated player simulations.

Each simulated game draws:
  - a team passing script and a running script (they pull against each other)
  - how the yards and touches get split among players that day
  - touchdowns, then who scores them
The QB's passing yards are literally the sum of his receivers' yards, so
"QB over + WR1 over" is correlated exactly like real games.
"""
import logging
from pathlib import Path
import numpy as np
import pandas as pd

from . import config as C
from .util import norm_name, fnum

log = logging.getLogger("nflmodel")


def _norm_factor(x):
    return x / x.mean()


def simulate_team(pool: pd.DataFrame, qb_pid, pass_td, rush_td, int_mean,
                  scr_car, scr_yds, seed=0) -> dict:
    """pool: one row per non-QB-scramble player with mean rec, rec_yds, rec_td,
    carries, rush_yds, rush_td. Returns pid -> {stat: array}."""
    N = C.PLAYER_SIMS
    rng = np.random.default_rng(seed)
    s1 = rng.standard_normal(N)
    s2 = -0.35 * s1 + np.sqrt(1 - 0.35 ** 2) * rng.standard_normal(N)
    Fp = np.exp(0.24 * s1 - 0.24 ** 2 / 2)
    Fr = np.exp(0.30 * s2 - 0.30 ** 2 / 2)
    pids = list(pool["pid"])
    k = len(pids)
    z = np.zeros((N, k))
    rec_yds, rec_n, car_n, rush_yds, rec_td, rush_tdm = z.copy(), z.copy(), z.copy(), z.copy(), z.copy(), z.copy()

    ry = pool["rec_yds"].to_numpy(float)
    if ry.sum() > 0:
        y = ry / ry.sum()
        alpha = np.maximum(y * C.K_REC, 0.02)
        W = rng.dirichlet(alpha, N) if k > 1 else np.ones((N, 1))
        idio = np.exp(0.20 * rng.standard_normal((N, k)) - 0.02)
        rec_yds = ry.sum() * Fp[:, None] * W * idio
        ratio = np.where(y > 0, np.clip(W / np.maximum(y, 1e-9), 0, 4), 0)
        f = Fp[:, None] ** 0.6 * ratio ** 0.7
        f = f / np.maximum(f.mean(axis=0), 1e-9)
        rec_n = rng.poisson(pool["rec"].to_numpy(float) * f)
        tdp = pool["rec_td"].to_numpy(float)
        if tdp.sum() > 0:
            cnt = rng.poisson(pass_td * _norm_factor(Fp ** 1.2))
            rec_td = rng.multinomial(cnt, tdp / tdp.sum())

    rr = pool["rush_yds"].to_numpy(float)
    if rr.sum() > 0:
        r = np.clip(rr, 0, None) / np.clip(rr, 0, None).sum()
        alpha = np.maximum(r * C.K_RUSH, 0.02)
        R = rng.dirichlet(alpha, N) if k > 1 else np.ones((N, 1))
        idio = np.exp(0.25 * rng.standard_normal((N, k)) - 0.03125)
        rush_yds = rr.sum() * Fr[:, None] * R * idio
        ratio = np.where(r > 0, np.clip(R / np.maximum(r, 1e-9), 0, 4), 0)
        f = Fr[:, None] ** 0.5 * ratio ** 0.8
        f = f / np.maximum(f.mean(axis=0), 1e-9)
        car_n = rng.poisson(pool["carries"].to_numpy(float) * f)
        tdr = pool["rush_td"].to_numpy(float)
        if tdr.sum() > 0:
            cnt = rng.poisson(rush_td * _norm_factor(Fr ** 1.2))
            rush_tdm = rng.multinomial(cnt, tdr / tdr.sum())

    out = {}
    for j, pid in enumerate(pids):
        out[pid] = {"rec": rec_n[:, j], "rec_yds": rec_yds[:, j], "rec_td": rec_td[:, j],
                    "carries": car_n[:, j].astype(float), "rush_yds": rush_yds[:, j], "rush_td": rush_tdm[:, j]}

    if qb_pid is not None:
        q = out.setdefault(qb_pid, {s: np.zeros(N) for s in ["rec", "rec_yds", "rec_td", "carries", "rush_yds", "rush_td"]})
        if scr_car > 0:
            sy = rng.gamma(1.5, max(scr_yds, 0.1) / 1.5, N)
            q["rush_yds"] = q["rush_yds"] + sy
            q["carries"] = q["carries"] + rng.poisson(scr_car, N)
        q["pass_yds"] = rec_yds.sum(axis=1)
        q["pass_cmp"] = rec_n.sum(axis=1).astype(float)
        q["pass_td"] = rec_td.sum(axis=1).astype(float)
        q["pass_int"] = rng.poisson(int_mean * _norm_factor(np.exp(-0.2 * s1)), N).astype(float)

    for pid, d in out.items():
        pz = d.get("pass_yds", 0) * 0.04 + d.get("pass_td", 0) * 4 - d.get("pass_int", 0) * 2
        d["fpts"] = pz + d["rush_yds"] * 0.1 + d["rush_td"] * 6 + d["rec"] + d["rec_yds"] * 0.1 + d["rec_td"] * 6
        d["anytime_td"] = ((d["rush_td"] + d["rec_td"]) >= 1).astype(float)
        d["rush_rec_yds"] = d["rush_yds"] + d["rec_yds"]
    return out


def quantiles(arr):
    return float(np.median(arr)), float(np.percentile(arr, 10)), float(np.percentile(arr, 90))


# ---------------------------------------------------------------------
# Props: compare your sportsbook lines to the simulations
# ---------------------------------------------------------------------
STAT_ALIASES = {
    "pass_yds": "pass_yds", "passing_yards": "pass_yds", "pass_tds": "pass_td", "pass_td": "pass_td",
    "completions": "pass_cmp", "pass_cmp": "pass_cmp", "interceptions": "pass_int", "pass_int": "pass_int",
    "rush_yds": "rush_yds", "rushing_yards": "rush_yds", "carries": "carries", "rush_att": "carries",
    "rec": "rec", "receptions": "rec", "rec_yds": "rec_yds", "receiving_yards": "rec_yds",
    "rush_rec_yds": "rush_rec_yds", "anytime_td": "anytime_td", "fpts": "fpts", "fantasy_points": "fpts",
}


def american_to_prob(o):
    try:
        o = float(o)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(o) or o == 0:
        return None
    return 100 / (o + 100) if o > 0 else -o / (-o + 100)


STAT_LABELS = {
    "pass_yds": "Passing yards", "pass_td": "Passing TDs", "pass_cmp": "Completions", "pass_att": "Pass attempts",
    "pass_int": "Interceptions", "rush_yds": "Rushing yards", "carries": "Rush attempts", "rec": "Receptions",
    "rec_yds": "Receiving yards", "rush_rec_yds": "Rush + rec yards", "anytime_td": "Anytime TD",
    "fpts": "Fantasy points",
}


def stat_label(key) -> str:
    k = STAT_ALIASES.get(str(key).strip().lower(), str(key).strip().lower())
    return STAT_LABELS.get(k, str(key).replace("_", " ").capitalize())


def prop_tier(stat, edge_pct, lean):
    """Play (4-7% gap, allowed prop types), Watch (rest up to 15%), Too big (15%+)."""
    if not lean or edge_pct is None:
        return None
    e = abs(float(edge_pct)) / 100
    if e >= C.PROP_WATCH_MAX:
        return "too_big"
    if C.PROP_PLAY_MIN <= e < C.PROP_PLAY_MAX and stat in C.PROP_PLAY_STATS:
        return "play"
    return "watch"


def load_props(path: Path) -> pd.DataFrame:
    try:
        p = pd.read_csv(path, comment="#", skip_blank_lines=True, dtype=str)
        p.columns = [c.strip().lower() for c in p.columns]
        p = p.dropna(subset=["player", "stat"])
        return p
    except Exception as e:  # noqa: BLE001
        log.info(f"no props file read: {e}")
        return pd.DataFrame()


def evaluate_props(props: pd.DataFrame, players: list, sims: dict) -> dict:
    if not len(props):
        return {"props": [], "pairs": []}
    by_name = {}
    for p in players:
        by_name.setdefault(norm_name(p["name"]), []).append(p)
    out, keep = [], []
    for _, r in props.iterrows():
        stat = STAT_ALIASES.get(str(r["stat"]).strip().lower())
        cands = by_name.get(norm_name(r["player"]), [])
        if "team" in r and isinstance(r.get("team"), str) and r["team"].strip():
            cands = [c for c in cands if c["team"] == r["team"].strip().upper()] or cands
        hint = r.get("game_id")
        if isinstance(hint, str) and hint:              # auto-loaded lines know their game
            cands = [c for c in cands if c["game_id"] == hint] or cands
        clean = lambda v: None if v is None or (isinstance(v, float) and np.isnan(v)) or str(v).strip() == "" else str(v).strip()
        row = {"player": r["player"], "stat": r["stat"], "line": clean(r.get("line")),
               "over_odds": clean(r.get("over_odds")), "under_odds": clean(r.get("under_odds")),
               "source": clean(r.get("source")) or "manual", "book": clean(r.get("book"))}
        if stat is None or not cands:
            row["error"] = "stat not recognized" if stat is None else "player not in this week's projections"
            out.append(row)
            continue
        p = cands[0]
        arr = sims.get((p["game_id"], p["pid"]), {}).get(stat)
        if arr is None:
            row["error"] = "no simulation for this stat"
            out.append(row)
            continue
        try:
            line = 0.5 if stat == "anytime_td" else float(r.get("line"))
        except (TypeError, ValueError):
            row["error"] = "line missing"
            out.append(row)
            continue
        dec = arr != line
        p_over = float((arr[dec] > line).mean()) if dec.any() else 0.5
        bo, bu = american_to_prob(r.get("over_odds")), american_to_prob(r.get("under_odds"))
        if bo is not None and bu is not None:
            book_over = bo / (bo + bu)
        elif bo is not None:
            book_over = bo
        else:
            book_over = 0.5
        edge = p_over - book_over
        side = "Over" if edge >= C.PROP_EDGE else ("Under" if edge <= -C.PROP_EDGE else None)
        if side == "Under" and stat == "anytime_td" and bu is None and C.TD_NO_NEEDS_PRICE:
            side = None   # no "No TD" price posted, so there is nothing to bet or grade
        tier = prop_tier(stat, edge * 100, side)
        row.update({"team": p["team"], "opp": p["opp"], "pos": p["pos"], "game_id": p["game_id"],
                    "pid": p["pid"], "stat_key": stat,
                    "median": None if stat == "anytime_td" else fnum(np.median(arr), 1), "model_over": fnum(p_over * 100, 1),
                    "book_over": fnum(book_over * 100, 1), "edge": fnum(edge * 100, 1), "lean": side,
                    "tier": tier, "label": stat_label(stat)})
        out.append(row)
        if tier == "play":
            keep.append((row, (arr > line) if side == "Over" else (arr < line), p["team"]))

    pairs = []
    for i in range(len(keep)):
        for j in range(i + 1, len(keep)):
            (ra, ha, ta), (rb, hb, tb) = keep[i], keep[j]
            if ta != tb or ra["game_id"] != rb["game_id"]:
                continue
            joint = float((ha & hb).mean())
            indep = float(ha.mean() * hb.mean())
            leg = lambda x: (f"{x['player']} {'anytime TD' if x['lean'] == 'Over' else 'no TD'}"
                             if STAT_ALIASES.get(str(x['stat']).lower()) == "anytime_td"
                             else f"{x['player']} {x['lean']} {x['line']} {stat_label(x['stat']).lower()}")
            pairs.append({"legs": [leg(ra), leg(rb)],
                          "joint": fnum(joint * 100, 1), "if_independent": fnum(indep * 100, 1),
                          "lift": fnum((joint / indep - 1) * 100 if indep > 0 else 0, 0)})
    pairs = [x for x in pairs if (x["lift"] or 0) >= 3]
    pairs.sort(key=lambda x: -(x["lift"] or 0))
    return {"props": out, "pairs": pairs[:10]}
