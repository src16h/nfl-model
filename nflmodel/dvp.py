"""
Defense vs position (receiving).

The team-level opponent numbers (yards and completion rate a defense allows) already move every
receiver up or down together. This adds the part they miss: WHERE a defense gives up its targets
and yards. Some defenses are fine vs wide receivers and soft vs tight ends, or leak targets to backs.

For each defense and position group (WR, TE, RB):
  target factor  = targets it gave that position / targets those offenses normally give that position
  yards factor   = same, for receiving yards
Comparing with what each offense NORMALLY does takes care of schedule: a defense that faced three
tight-end-heavy offenses isn't called soft vs tight ends for it. Small samples are pulled toward 1.

The factors only move targets and yards BETWEEN a team's players. Team totals are left alone, so
nothing is counted twice with the team-level pass defense numbers.
"""
import logging

import numpy as np
import pandas as pd

from . import config as C
from .util import pos_group

log = logging.getLogger("nflmodel")

GROUPS = ("WR", "TE", "RB")


def pos_map(rosters) -> dict:
    """gsis id -> WR / TE / RB from any roster table (weekly or season)."""
    if rosters is None or not len(rosters):
        return {}
    r = rosters.dropna(subset=["gsis_id"])
    if "season" in r.columns:
        r = r.sort_values(["season"] + (["week"] if "week" in r.columns else []))
    g = r.groupby("gsis_id")["position"].last().map(pos_group)
    return {k: v for k, v in g.items() if v in GROUPS}


def targets_table(pbp: pd.DataFrame, posmap: dict) -> pd.DataFrame:
    """One row per (game, offense, defense, position group): targets and receiving yards."""
    p = pbp[(pbp.get("pass_attempt", 0) == 1) & pbp["receiver_player_id"].notna()
            & pbp["posteam"].notna() & pbp["defteam"].notna()]
    if "two_point_attempt" in p.columns:
        p = p[p["two_point_attempt"] != 1]
    if "season_type" in p.columns:
        p = p[p["season_type"] == "REG"]
    p = p.assign(pg=p["receiver_player_id"].map(posmap))
    p = p[p["pg"].notna()]
    p = p.assign(yds=np.where(p["complete_pass"] == 1, p["yards_gained"].fillna(0), 0.0))
    if "wp" in p.columns:          # late blowouts change who gets the ball, so they count less
        wp = p["wp"].to_numpy(float)
        p = p.assign(gw=np.where((wp < 0.10) | (wp > 0.90), C.GARBAGE_TIME_WEIGHT, 1.0))
    else:
        p = p.assign(gw=1.0)
    p = p.assign(wy=p["yds"] * p["gw"])
    t = p.groupby(["season", "week", "game_id", "posteam", "defteam", "pg"]).agg(
        tgt=("gw", "sum"), yds=("wy", "sum")).reset_index()
    return t


class DvP:
    """Factors per (defense, position). f_tgt / f_ypt default to 1 for anything unknown."""

    def __init__(self, table: pd.DataFrame, season: int, week: int, prior_w=None, k_tgt=None, k_yds=None,
                 strength=None, cap=None, strength_ypt=None):
        self.ok = False
        self.f_tgt, self.f_ypt, self.n = {}, {}, {}
        prior_w = C.DVP_PRIOR_SEASON_W if prior_w is None else prior_w
        k_tgt = C.DVP_K_TGT if k_tgt is None else k_tgt
        k_yds = C.DVP_K_YDS if k_yds is None else k_yds
        self.strength = C.DVP_STRENGTH if strength is None else strength
        self.strength_ypt = C.DVP_STRENGTH_YPT if strength_ypt is None else strength_ypt
        self.cap = C.DVP_CAP if cap is None else cap
        if table is None or not len(table):
            return
        t = table[((table["season"] == season) & (table["week"] < week)) | (table["season"] == season - 1)].copy()
        if not len(t):
            return
        t["w"] = np.where(t["season"] == season, 1.0, prior_w)
        t = t[t["w"] > 0]

        # what each offense normally does: its share of targets and yards by position, in the same window
        # (season by season, so last year's offense isn't mixed up with this year's)
        off = t.groupby(["season", "posteam", "pg"])[["tgt", "yds"]].sum()
        tot = off.groupby(level=[0, 1]).transform("sum")
        share = (off / tot.replace(0, np.nan)).fillna(0.0)
        share.columns = ["s_tgt", "s_yds"]

        g = t.groupby(["season", "game_id", "posteam", "defteam"])[["tgt", "yds"]].transform("sum")
        t["g_tgt"], t["g_yds"] = g["tgt"], g["yds"]
        t = t.join(share, on=["season", "posteam", "pg"])
        # every position the offense uses, even ones with zero targets in this game, carries an expectation
        full = (t[["season", "game_id", "posteam", "defteam", "g_tgt", "g_yds", "w"]].drop_duplicates()
                .merge(share.reset_index(), on=["season", "posteam"]))
        full = full.merge(t[["game_id", "posteam", "pg", "tgt", "yds"]], on=["game_id", "posteam", "pg"], how="left")
        full[["tgt", "yds"]] = full[["tgt", "yds"]].fillna(0.0)
        full["e_tgt"] = full["g_tgt"] * full["s_tgt"]
        full["e_yds"] = full["g_yds"] * full["s_yds"]
        for c in ["tgt", "yds", "e_tgt", "e_yds"]:
            full[c] = full[c] * full["w"]
        d = full.groupby(["defteam", "pg"])[["tgt", "yds", "e_tgt", "e_yds"]].sum()
        ft = (d["tgt"] + k_tgt) / (d["e_tgt"] + k_tgt)
        fy = (d["yds"] + k_yds) / (d["e_yds"] + k_yds)
        fp = fy / ft                                   # yards per target, beyond the target change
        lo, hi = 1 / self.cap, self.cap
        self.f_tgt = ft.clip(lo, hi).to_dict()
        self.f_ypt = fp.clip(lo, hi).to_dict()
        self.n = d["e_tgt"].to_dict()
        self.ok = True
        log.info(f"defense vs position: {len(d)} defense-position cells, strength {self.strength}")

    def factors(self, defense, pg) -> tuple[float, float]:
        if not self.ok or pg not in GROUPS:
            return 1.0, 1.0
        return (float(self.f_tgt.get((defense, pg), 1.0)) ** self.strength,
                float(self.f_ypt.get((defense, pg), 1.0)) ** self.strength_ypt)

    def adjust(self, df: pd.DataFrame, defense) -> pd.DataFrame:
        """Shift targets, catches and yards between a team's players. Team totals stay the same.
        df needs pos, targets, rec, rec_yds, tgt_share. Adds dvp_tgt / dvp_yds columns (1 = no change)."""
        df = df.copy()
        df["dvp_tgt"], df["dvp_yds"] = 1.0, 1.0
        if not self.ok or not len(df) or df["targets"].sum() <= 0:
            return df
        f = np.array([self.factors(defense, p) for p in df["pos"]])
        ft, fp = f[:, 0], f[:, 1]
        t0, r0, y0, s0 = (df[c].sum() for c in ["targets", "rec", "rec_yds", "tgt_share"])
        y_before = df["rec_yds"].to_numpy(float).copy()
        tg = df["targets"].to_numpy(float) * ft
        tg *= t0 / max(tg.sum(), 1e-9)
        rel = tg / np.maximum(df["targets"].to_numpy(float), 1e-9)      # renormalized target change per player
        rec = df["rec"].to_numpy(float) * rel
        yd = df["rec_yds"].to_numpy(float) * rel * fp
        df["targets"] = tg
        df["rec"] = rec * (r0 / max(rec.sum(), 1e-9))
        df["rec_yds"] = yd * (y0 / max(yd.sum(), 1e-9))
        df["tgt_share"] = df["tgt_share"].to_numpy(float) * rel
        if df["tgt_share"].sum() > 0:
            df["tgt_share"] *= s0 / df["tgt_share"].sum()
        if "rec_td" in df.columns and df["rec_td"].sum() > 0:      # red-zone looks follow the same matchup
            td0 = df["rec_td"].sum()
            td = df["rec_td"].to_numpy(float) * rel
            df["rec_td"] = td * (td0 / max(td.sum(), 1e-9))
        df["dvp_tgt"] = rel
        df["dvp_yds"] = df["rec_yds"].to_numpy(float) / np.maximum(y_before, 1e-9)
        return df

    def table(self) -> list[dict]:
        """For the dashboard: each defense's factors, as % above or below normal."""
        out = []
        teams = sorted({k[0] for k in self.f_tgt})
        for tm in teams:
            row = {"team": tm}
            for pg in GROUPS:
                a, b = self.factors(tm, pg)
                row[f"{pg.lower()}_tgt"] = round(100 * (a - 1), 1)
                row[f"{pg.lower()}_yds"] = round(100 * (a * b - 1), 1)
            out.append(row)
        return out
