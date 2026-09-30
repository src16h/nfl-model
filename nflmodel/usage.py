"""
Player roles (usage) and skill (efficiency), straight from play-by-play.

usage:      recent share of team targets, carries, red-zone looks, dropbacks
efficiency: catch rate, yards per target, yards per carry, QB passing rates
            (longer memory, two seasons, then pulled toward position averages)
"""
import numpy as np
import pandas as pd

from . import config as C
from .util import play_weights, before


def _events(pbp: pd.DataFrame) -> pd.DataFrame:
    """One row per player-involvement: target, carry, dropback."""
    p = pbp[pbp["posteam"].notna()]
    rz = (p["yardline_100"] <= 20).astype(int)
    yds = p["yards_gained"].fillna(0)
    base = ["season", "week", "game_id", "posteam", "wp"]

    tg = p[(p["pass_attempt"] == 1) & (p["sack"] == 0) & p["receiver_player_id"].notna()]
    t = tg[base].copy()
    t["pid"] = tg["receiver_player_id"]
    t["name"] = tg["receiver_player_name"]
    t["kind"] = "tgt"
    t["rz"] = rz[tg.index]
    t["cmp"] = tg["complete_pass"]
    t["yds"] = np.where(tg["complete_pass"] == 1, yds[tg.index], 0.0)
    t["td"] = tg["pass_touchdown"]

    ca = p[(p["rush"] == 1) & (p["pass"] == 0) & (p["qb_scramble"] != 1) & p["rusher_player_id"].notna()]
    c = ca[base].copy()
    c["pid"] = ca["rusher_player_id"]
    c["name"] = ca["rusher_player_name"]
    c["kind"] = "car"
    c["rz"] = rz[ca.index]
    c["cmp"] = 0
    c["yds"] = yds[ca.index]
    c["td"] = ca["rush_touchdown"]

    # dropbacks: passes + sacks (passer) and scrambles (rusher)
    pa = p[((p["pass_attempt"] == 1) | (p["sack"] == 1)) & p["passer_player_id"].notna() & (p["qb_scramble"] != 1)]
    d = pa[base].copy()
    d["pid"] = pa["passer_player_id"]
    d["name"] = pa["passer_player_name"]
    d["kind"] = np.where(pa["sack"] == 1, "sack", "att")
    d["rz"] = 0
    d["cmp"] = pa["complete_pass"]
    d["yds"] = np.where(pa["sack"] == 1, 0.0, np.where(pa["complete_pass"] == 1, yds[pa.index], 0.0))
    d["td"] = pa["pass_touchdown"]
    d["int"] = pa["interception"]
    d["epa"] = pa["epa"]

    sc = p[(p["qb_scramble"] == 1) & p["rusher_player_id"].notna()]
    s = sc[base].copy()
    s["pid"] = sc["rusher_player_id"]
    s["name"] = sc["rusher_player_name"]
    s["kind"] = "scr"
    s["rz"] = 0
    s["cmp"] = 0
    s["yds"] = yds[sc.index]
    s["td"] = sc["rush_touchdown"]
    s["epa"] = sc["epa"]

    ev = pd.concat([t, c, d, s], ignore_index=True)
    for col in ["int", "epa"]:
        if col not in ev.columns:
            ev[col] = 0.0
    ev[["int", "epa"]] = ev[["int", "epa"]].fillna(0.0)
    return ev


def build(pbp_all: pd.DataFrame, season: int, week: int) -> dict:
    ev = _events(before(pbp_all, season, week))
    # usage weights: heavy recency; last season only matters early on
    w = play_weights(ev, season, week, decay=C.USAGE_DECAY, prior_base=0.35, garbage=True)
    ev["w"] = w

    def team_share(kind, rz_only=False):
        e = ev[(ev["kind"] == kind) & (ev["w"] > 0)]
        if rz_only:
            e = e[e["rz"] == 1]
        pl = e.groupby(["posteam", "pid"])["w"].sum()
        tm = e.groupby("posteam")["w"].sum()
        return pl / pl.index.get_level_values(0).map(tm).to_numpy()

    usage = pd.DataFrame({
        "tgt_share": team_share("tgt"),
        "car_share": team_share("car"),
        "rz_tgt_share": team_share("tgt", True),
        "rz_car_share": team_share("car", True),
    }).fillna(0.0)
    usage.index.names = ["team", "pid"]
    usage = usage.reset_index()

    # Efficiency: two seasons, current weighted fully, last season 60%
    ew = np.where(ev["season"] == season, 1.0, np.where(ev["season"] == season - 1, 0.6, 0.0))
    ew = np.where((ev["season"] == season) & (ev["week"] >= week), 0.0, ew)
    ev["ew"] = ew
    e = ev[ev["ew"] > 0]

    def agg(kind, cols):
        x = e[e["kind"].isin(kind if isinstance(kind, list) else [kind])]
        out = pd.DataFrame({"n": x.groupby("pid")["ew"].sum()})
        for c in cols:
            out[c] = (x[c] * x["ew"]).groupby(x["pid"]).sum()
        return out

    rec = agg("tgt", ["cmp", "yds", "td"]).add_prefix("rec_")
    car = agg("car", ["yds", "td"]).add_prefix("car_")
    att = agg("att", ["cmp", "yds", "td", "int"]).add_prefix("qb_")
    db = agg(["att", "sack", "scr"], ["epa"]).add_prefix("db_")
    scr = agg("scr", ["yds"]).add_prefix("scr_")
    eff = pd.concat([rec, car, att, db, scr], axis=1).fillna(0.0)

    names = ev.dropna(subset=["name"]).sort_values(["season", "week"]).groupby("pid")["name"].last()
    eff["pbp_name"] = names.reindex(eff.index)
    eff.index.name = "pid"

    # dropbacks by team-week, for QB starter logic
    dbk = ev[ev["kind"].isin(["att", "sack", "scr"])]
    qb_weeks = dbk.groupby(["season", "week", "posteam", "pid"]).agg(
        dropbacks=("kind", "size"), epa=("epa", "sum")).reset_index()
    qb_weeks["rw"] = play_weights(qb_weeks, season, week, garbage=False)
    return {"usage": usage, "eff": eff, "qb_weeks": qb_weeks, "names": names}
