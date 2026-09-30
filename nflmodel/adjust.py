"""
Two game adjustments:

1. Non-QB injuries: each missing regular starter costs points.
   Receivers and backs are valued by their actual share of the offense.
   Linemen and defenders are valued by position if they play 60%+ of snaps.

2. Scheme matchups (only if man/zone coverage data is published):
   an offense that struggles vs man coverage loses points against a
   defense that plays a lot of man, and vice versa.
"""
import logging
import numpy as np
import pandas as pd

from . import config as C
from .util import norm_name, pos_group, shrink

log = logging.getLogger("nflmodel")


def starters_from_snaps(snaps, season, week) -> pd.DataFrame | None:
    if snaps is None or not len(snaps):
        return None
    s = snaps.copy()
    cur = s[(s["season"] == season) & (s["week"] < week) & (s["week"] >= week - 4)]
    if not len(cur):
        prev = s[s["season"] == season - 1]
        cur = prev[prev["week"] >= prev["week"].max() - 3]
    cur = cur.copy()
    for c in ["offense_pct", "defense_pct"]:
        cur[c] = pd.to_numeric(cur[c], errors="coerce").fillna(0)
        if cur[c].max() > 1.5:
            cur[c] = cur[c] / 100.0
    cur["pct"] = cur[["offense_pct", "defense_pct"]].max(axis=1)
    cur["nname"] = cur["player"].map(norm_name)
    g = cur.groupby(["team", "nname"]).agg(pct=("pct", "mean"), position=("position", "last")).reset_index()
    return g


def injury_points(inj: pd.DataFrame, usage: pd.DataFrame, starters) -> dict:
    """team -> {'off': pts lost, 'def': pts given up extra, 'list': notable players}"""
    out = {}
    use = usage.set_index(["team", "pid"])
    for team, grp in inj.groupby("team"):
        off = de = 0.0
        notable = []
        for _, r in grp.iterrows():
            wgt = C.STATUS_WEIGHT.get(r["status"], 0.0)
            pg = r["pgroup"]
            if wgt == 0 or pg in ("QB", "ST"):
                continue
            val, side = 0.0, None
            key = (team, r["pid"])
            if pg in ("WR", "TE", "RB") and r["pid"] is not None and key in use.index:
                u = use.loc[key]
                if pg == "RB":
                    val = C.RB_VALUE_CARRY * u["car_share"] + C.RB_VALUE_TARGET * u["tgt_share"]
                else:
                    val = C.WR_TE_VALUE_PER_TARGET_SHARE * u["tgt_share"]
                val, side = min(val, C.SKILL_VALUE_CAP), "off"
            elif pg in C.POSITION_VALUE and starters is not None:
                hit = starters[(starters["team"] == team) & (starters["nname"] == r["nname"])]
                if len(hit) and hit.iloc[0]["pct"] >= C.STARTER_SNAP_PCT:
                    val = C.POSITION_VALUE[pg]
                    side = "off" if pg in ("OT", "OG", "C") else "def"
            if side is None or val < 0.05:
                continue
            pts = val * wgt
            if side == "off":
                off += pts
            else:
                de += pts
            if val >= 0.25:
                notable.append({"name": r["name"], "pos": pg, "status": r["status"], "pts": round(pts, 2)})
        out[team] = {"off": min(off, C.INJURY_CAP_PER_SIDE), "def": min(de, C.INJURY_CAP_PER_SIDE),
                     "list": sorted(notable, key=lambda x: -x["pts"])[:5]}
    return out


class Scheme:
    """Man vs zone matchup. Disabled automatically when data is missing."""

    def __init__(self, participation, pbp, season, week):
        self.ok = False
        if participation is None:
            return
        try:
            pa = participation.rename(columns={"nflverse_game_id": "game_id"})
            if "old_game_id" in pa.columns and "game_id" not in pa.columns:
                return
            pa = pa[["game_id", "play_id", "defense_man_zone_type"]].dropna()
            pa["man"] = pa["defense_man_zone_type"].astype(str).str.upper().str.contains("MAN").astype(int)
            db = pbp[(pbp["qb_dropback"] == 1) & pbp["epa"].notna()]
            db = db[((db["season"] == season) & (db["week"] < week)) | (db["season"] == season - 1)]
            m = db.merge(pa[["game_id", "play_id", "man"]], on=["game_id", "play_id"], how="inner")
            if len(m) < 3000:
                return
            m["w"] = np.where(m["season"] == season, 1.0, 0.5)
            lg_man = np.average(m["man"], weights=m["w"])
            d = m.groupby("defteam").apply(lambda x: pd.Series({"n": x["w"].sum(), "man": (x["man"] * x["w"]).sum()}))
            self.man_rate = pd.Series(shrink(d["man"], d["n"], lg_man, 200), index=d.index)
            self.lg_man = lg_man

            def epa_split(flag):
                x = m[m["man"] == flag]
                lg = np.average(x["epa"], weights=x["w"])
                g = x.groupby("posteam").apply(lambda y: pd.Series({"n": y["w"].sum(), "e": (y["epa"] * y["w"]).sum()}))
                return pd.Series(shrink(g["e"], g["n"], lg, C.SCHEME_SHRINK_K), index=g.index), lg

            vm, lm = epa_split(1)
            vz, lz = epa_split(0)
            self.man_minus_zone = (vm - vz) - (lm - lz)
            self.ok = True
            log.info(f"scheme: enabled on {len(m)} dropbacks, league man rate {lg_man:.2f}")
        except Exception as e:  # noqa: BLE001
            log.warning(f"scheme disabled: {e}")

    def points(self, off, de, dropbacks) -> float:
        if not self.ok:
            return 0.0
        delta = (self.man_rate.get(de, self.lg_man) - self.lg_man) * self.man_minus_zone.get(off, 0.0)
        return float(np.clip(delta * dropbacks, -C.SCHEME_CAP, C.SCHEME_CAP))
