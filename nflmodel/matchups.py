"""
Play-style matchups from three free charting sources (all through nflverse).

FTN charting (every play tagged since 2022)
  blitz        defense blitzes a lot  x  this QB does better / worse when blitzed
  play action  offense uses it a lot  x  this defense gets hurt by it more / less than most
  screens      offense throws a lot   x  this defense handles them better / worse
  motion       offense uses a lot     x  this defense handles it better / worse
  box count    defense stacks 8+      x  this offense runs better / worse into stacked boxes

Next Gen Stats
  time to throw  a QB who holds the ball  x  a defense that gets pressure

Pro Football Reference (per defender, per game)
  coverage     yards per target allowed by the defenders who will actually play,
               vs the defense's usual group (a top corner out matters)
  pass rush    pressures per game from the rushers who will play, vs usual

Each matchup is "how unusual is side A" x "how much side B cares", the same shape as the man / zone
matchup in adjust.py. Every rate and split is pulled toward league average until the sample is big.

What the backtests found (Oct 26 2026, 2022-25; tools/backtest_matchups.py, tools/backtest_player_feats.py):
  - The "how much side B cares" splits (QB vs blitz, defense vs play action / screens / motion, offense
    vs 8+ boxes) do NOT carry over from past games to the next: play-level carry-over bounced around zero
    and flipped sign between 2022-24 and 2025. The rates are steady but already show up in team EPA.
    So none of the FTN matchups or time-to-throw x pressure are used. The code stays for re-testing.
  - Coverage (Coverage class): defenders' yards per target allowed DOES carry over (about 0.6), and
    defenses missing their usual cover players gave up more yards per dropback (strong in 2022-24, same
    direction but weak in 2025). Used for player props at half strength (config COVERAGE_*).
  - Pass rush availability: pressures carry over, but no effect on yards showed up. Not used.
  - FTN interception-worthy throws predict next week's interceptions better than INT rate alone
    (qb_int_worthy below). Used 50/50 in the QB interception rate.
  - FTN catchable balls / drops and NGS separation / YAC over expected / air yards added nothing to
    catch rate or yards per target beyond what the model already uses. Not used.
"""
import logging

import numpy as np
import pandas as pd

from .util import shrink

log = logging.getLogger("nflmodel")

K_RATE = 150.0      # plays of "league average" mixed into a team's rate
K_SPLIT = 120.0     # plays per side mixed into an EPA split
K_TTT = 150.0       # attempts mixed into a QB's time to throw
K_COV = 50.0        # targets mixed into a defender's yards per target
K_PRES = 4.0        # games mixed into a defender's pressures per game

PASS_FEATS = ("blitz", "play_action", "screen", "motion", "ttt_pressure", "coverage", "pass_rush")
RUSH_FEATS = ("box",)


# ---------------------------------------------------------------------------------------------------
# data prep
# ---------------------------------------------------------------------------------------------------
def tag_plays(pbp: pd.DataFrame, ftn: pd.DataFrame | None) -> pd.DataFrame:
    """Regular-season dropbacks and designed runs with FTN tags (NaN where a play isn't charted)."""
    p = pbp[(pbp["season_type"] == "REG") & pbp["epa"].notna() & pbp["posteam"].notna() & pbp["defteam"].notna()]
    p = p[(p["qb_dropback"] == 1) | ((p["rush"] == 1) & (p["qb_scramble"] != 1))]
    cols = ["season", "week", "game_id", "play_id", "posteam", "defteam", "passer_player_id", "qb_dropback",
            "epa", "wp", "yards_gained", "pass_attempt"]
    p = p[[c for c in cols if c in p.columns]].copy()
    p["db"] = (p["qb_dropback"] == 1).astype(int)
    wp = p["wp"].to_numpy(float) if "wp" in p.columns else np.full(len(p), 0.5)
    p["gw"] = np.where((wp < 0.10) | (wp > 0.90), 0.35, 1.0)
    for c in ["blitz", "play_action", "screen", "motion", "heavy_box"]:
        p[c] = np.nan
    if ftn is not None and len(ftn):
        f = ftn.rename(columns={"nflverse_game_id": "game_id", "nflverse_play_id": "play_id"})
        f = f[["game_id", "play_id", "n_blitzers", "n_pass_rushers", "is_play_action", "is_screen_pass",
               "is_motion", "n_defense_box"]].copy()
        f["play_id"] = pd.to_numeric(f["play_id"], errors="coerce")
        p["play_id"] = pd.to_numeric(p["play_id"], errors="coerce")
        p = p.drop(columns=["blitz", "play_action", "screen", "motion", "heavy_box"]).merge(
            f, on=["game_id", "play_id"], how="left")
        ok = p["n_pass_rushers"].notna() | p["n_defense_box"].notna()
        rushers = pd.to_numeric(p["n_pass_rushers"], errors="coerce")
        blitzers = pd.to_numeric(p["n_blitzers"], errors="coerce")
        p["blitz"] = np.where(ok, ((blitzers.fillna(0) > 0) | (rushers.fillna(0) >= 5)).astype(float), np.nan)
        for src, dst in [("is_play_action", "play_action"), ("is_screen_pass", "screen"), ("is_motion", "motion")]:
            p[dst] = np.where(ok, p[src].astype(float).fillna(0.0), np.nan)
        box = pd.to_numeric(p["n_defense_box"], errors="coerce")
        p["heavy_box"] = np.where(box.notna(), (box >= 8).astype(float), np.nan)
        p = p.drop(columns=["n_blitzers", "n_pass_rushers", "is_play_action", "is_screen_pass", "is_motion",
                            "n_defense_box"])
    return p


# ---------------------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------------------
def _rate(df, key, flag, k=K_RATE):
    """Shrunk weighted rate of `flag` by `key`. Returns (Series, league rate)."""
    d = df[df[flag].notna()]
    if not len(d):
        return pd.Series(dtype=float), np.nan
    lg = np.average(d[flag], weights=d["w"])
    g = d.groupby(key).apply(lambda x: pd.Series({"n": x["w"].sum(), "y": (x[flag] * x["w"]).sum()}))
    return pd.Series(shrink(g["y"], g["n"], lg, k), index=g.index), lg


def _split(df, key, flag, k=K_SPLIT):
    """Shrunk EPA when flag=1 minus EPA when flag=0, by key, minus the league's same gap."""
    d = df[df[flag].notna()]
    if not len(d) or d[flag].sum() == 0:
        return pd.Series(dtype=float)
    out = {}
    lgs = {}
    for v in (1, 0):
        x = d[d[flag] == v]
        lg = np.average(x["epa"], weights=x["w"])
        g = x.groupby(key).apply(lambda y: pd.Series({"n": y["w"].sum(), "e": (y["epa"] * y["w"]).sum()}))
        out[v] = pd.Series(shrink(g["e"], g["n"], lg, k), index=g.index)
        lgs[v] = lg
    idx = out[1].index.union(out[0].index)
    a = out[1].reindex(idx).fillna(lgs[1])
    b = out[0].reindex(idx).fillna(lgs[0])
    return (a - b) - (lgs[1] - lgs[0])


class Coverage:
    """Who is in the secondary this week vs who usually is, from PFR per-defender charting."""

    def __init__(self, pfr: pd.DataFrame | None, season: int, week: int, prior_w: float = 0.5):
        self.season, self.week = season, week
        self.pfr_ok = False
        if pfr is None or not len(pfr):
            return
        d = pfr[(pfr["game_type"] == "REG")] if "game_type" in pfr.columns else pfr
        d = d[((d["season"] == season) & (d["week"] < week)) | (d["season"] == season - 1)].copy()
        if not len(d):
            return
        d["w"] = np.where(d["season"] == season, 1.0, prior_w)
        for c in ["def_targets", "def_yards_allowed", "def_pressures"]:
            d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0.0)    # blank yards = no catches allowed
        self._defenders(d)

    def _defenders(self, d):
        """Per-defender coverage and pass rush, and each team's usual group."""
        lg_ypt = d["def_yards_allowed"].sum() / max(d["def_targets"].sum(), 1)
        pl = d.assign(t=d["def_targets"] * d["w"], y=d["def_yards_allowed"] * d["w"], p=d["def_pressures"] * d["w"]
                      ).groupby("pfr_player_id").agg(t=("t", "sum"), y=("y", "sum"), p=("p", "sum"), g=("w", "sum"))
        self.ypt = pd.Series(shrink(pl["y"], pl["t"], lg_ypt * 1.04, K_COV), index=pl.index)
        self.ppg = pd.Series(shrink(pl["p"], pl["g"], 0.0, K_PRES), index=pl.index)
        self.lg_ypt = lg_ypt
        # usual group for each team: share of its targets (coverage) and of its games (rush), recent weeks
        # count most, so a player out for a month is already baked into how the defense has been playing
        rw = np.where(d["season"] == self.season, 0.8 ** np.clip(self.week - 1 - d["week"], 0, None), 0.02)
        tm = d.assign(w=rw, t=d["def_targets"] * rw, p=d["def_pressures"] * rw)
        tg = tm.groupby(["team", "pfr_player_id"]).agg(t=("t", "sum"), g=("w", "sum"))
        tot_t = tg.groupby(level=0)["t"].transform("sum")
        tot_g = tm.groupby(["team", "game_id"])["w"].first().groupby(level=0).sum()
        tg["share"] = tg["t"] / tot_t.replace(0, np.nan)
        tg["gshare"] = tg["g"] / tg.index.get_level_values(0).map(tot_g).to_numpy()
        self.usual = tg.fillna(0.0)
        self.cur_team = d.sort_values(["season", "week"]).groupby("pfr_player_id")["team"].last()
        self.names = d.sort_values(["season", "week"]).groupby("pfr_player_id")["pfr_player_name"].last() \
            if "pfr_player_name" in d.columns else pd.Series(dtype=str)
        self._pfr_games = tm.groupby(["game_id", "team"]).agg(pres=("def_pressures", "sum"), w=("w", "first"))
        self.pfr_ok = len(tg) > 200

    def shift(self, de, available=None, unavailable=None, detail=False):
        """(coverage yards-per-target shift, pressures-per-game shift) from who plays.
        available: pfr ids who will play (backtest), or unavailable: pfr ids who won't (live).
        Positive coverage shift = the secondary is weaker than usual. detail=True adds the missing names."""
        none = (0.0, 0.0, []) if detail else (0.0, 0.0)
        if not self.pfr_ok or (available is None and unavailable is None) or de not in self.usual.index.get_level_values(0):
            return none
        u = self.usual.loc[de]
        u = u[u.index.map(lambda pid: self.cur_team.get(pid) == de)]
        if not len(u):
            return none
        ypt = self.ypt.reindex(u.index).fillna(self.lg_ypt * 1.04)
        ppg = self.ppg.reindex(u.index).fillna(0.0)
        play = u.index.isin(list(available)) if available is not None else ~u.index.isin(list(unavailable))
        s = u["share"].to_numpy()
        repl = self.lg_ypt * 1.08                              # backups cover worse than average
        normal = float((s * ypt).sum() / max(s.sum(), 1e-9))
        now = float((s * np.where(play, ypt, repl)).sum() / max(s.sum(), 1e-9))
        gs = u["gshare"].to_numpy()
        p_normal = float((gs * ppg).sum())
        p_now = float((gs * np.where(play, ppg, 0.3 * ppg)).sum())   # a backup brings some pressure
        if not detail:
            return now - normal, p_now - p_normal
        miss = [str(self.names.get(pid, pid)) for pid, sh, ok in zip(u.index, s, play) if not ok and sh >= 0.06]
        return now - normal, p_now - p_normal, miss


def qb_int_worthy(pbp: pd.DataFrame, ftn: pd.DataFrame | None, season: int, week: int, lg_int: float,
                  k: float = 150.0, prior_w: float = 0.6) -> pd.Series:
    """Each QB's interception-worthy throw rate (FTN), pulled toward average and put on the interception
    scale (league rate = lg_int). Steadier than real interceptions, which depend on drops and luck."""
    if ftn is None or not len(ftn) or pbp is None:
        return pd.Series(dtype=float)
    p = pbp[(pbp["season_type"] == "REG") & (pbp["pass_attempt"] == 1) & (pbp["sack"] != 1)
            & pbp["passer_player_id"].notna()]
    p = p[((p["season"] == season) & (p["week"] < week)) | (p["season"] == season - 1)][
        ["season", "game_id", "play_id", "passer_player_id"]].copy()
    f = ftn.rename(columns={"nflverse_game_id": "game_id", "nflverse_play_id": "play_id"})[
        ["game_id", "play_id", "is_interception_worthy"]].copy()
    f["play_id"] = pd.to_numeric(f["play_id"], errors="coerce")
    p["play_id"] = pd.to_numeric(p["play_id"], errors="coerce")
    p = p.merge(f, on=["game_id", "play_id"], how="inner").dropna(subset=["is_interception_worthy"])
    if len(p) < 2000:
        return pd.Series(dtype=float)
    w = np.where(p["season"] == season, 1.0, prior_w)
    iw = p["is_interception_worthy"].astype(float).to_numpy()
    lg = float(np.sum(iw * w) / np.sum(w))
    g = pd.DataFrame({"pid": p["passer_player_id"], "n": w, "y": iw * w}).groupby("pid").sum()
    return pd.Series(shrink(g["y"], g["n"], lg, k), index=g.index) * (lg_int / lg)


class Matchups:
    def __init__(self, plays: pd.DataFrame, season: int, week: int, pfr: pd.DataFrame | None = None,
                 ngs_pass: pd.DataFrame | None = None, prior_w: float = 0.5):
        self.season, self.week = season, week
        self.ok = False
        t = plays[((plays["season"] == season) & (plays["week"] < week)) | (plays["season"] == season - 1)].copy()
        if not len(t):
            return
        t["w"] = np.where(t["season"] == season, 1.0, prior_w) * t["gw"]
        db, ru = t[t["db"] == 1], t[t["db"] == 0]
        self.lg_db_epa = float(np.average(db["epa"], weights=db["w"]))

        # FTN
        self.blitz_rate, self.lg_blitz = _rate(db, "defteam", "blitz")
        self.blitz_qb = _split(db, "passer_player_id", "blitz")
        self.blitz_team = _split(db, "posteam", "blitz")
        self.off_rate, self.lg_rate, self.def_split = {}, {}, {}
        for f in ("play_action", "screen", "motion"):
            self.off_rate[f], self.lg_rate[f] = _rate(db, "posteam", f)
            self.def_split[f] = _split(db, "defteam", f)
        self.box_rate, self.lg_box = _rate(ru, "defteam", "heavy_box")
        self.box_split = _split(ru, "posteam", "heavy_box")
        self.ftn_ok = db["blitz"].notna().sum() > 2000

        # dropbacks faced per defense-game (for pressure rate)
        self.db_faced = db.groupby(["game_id", "defteam"]).size()

        # NGS time to throw
        self.ttt, self.lg_ttt = pd.Series(dtype=float), np.nan
        if ngs_pass is not None and len(ngs_pass):
            q = ngs_pass[(ngs_pass["week"] > 0) & (ngs_pass["season_type"] == "REG")]
            q = q[((q["season"] == season) & (q["week"] < week)) | (q["season"] == season - 1)]
            if len(q):
                w = np.where(q["season"] == season, 1.0, prior_w) * q["attempts"].astype(float)
                lg = np.average(q["avg_time_to_throw"], weights=w)
                g = pd.DataFrame({"pid": q["player_gsis_id"], "w": w, "y": q["avg_time_to_throw"] * w}).groupby("pid").sum()
                self.ttt = pd.Series(shrink(g["y"], g["w"], lg, K_TTT), index=g.index)
                self.lg_ttt = lg

        # PFR defenders
        self.cov = Coverage(pfr, season, week, prior_w)
        self.pfr_ok = self.cov.pfr_ok
        if self.pfr_ok:
            self.ypt, self.ppg, self.lg_ypt, self._pfr_games = self.cov.ypt, self.cov.ppg, self.cov.lg_ypt, self.cov._pfr_games

        # pressure rate per defense (PFR pressures / dropbacks faced)
        self.press_rate, self.lg_press = pd.Series(dtype=float), np.nan
        if self.pfr_ok:
            pg = self._pfr_games
            pg = pg.join(self.db_faced.rename("dbs"), on=["game_id", "team"]).dropna(subset=["dbs"])
            if len(pg):
                lg = (pg["pres"] * pg["w"]).sum() / (pg["dbs"] * pg["w"]).sum()
                g = pg.assign(y=pg["pres"] * pg["w"], n=pg["dbs"] * pg["w"]).groupby("team")[["y", "n"]].sum()
                self.press_rate = pd.Series(shrink(g["y"], g["n"], lg, 300), index=g.index)
                self.lg_press = lg
        self.ok = True

    def pass_feats(self, off, de, qb_pid=None, available=None) -> dict:
        """Raw matchup values for one offense vs one defense (dropbacks). Zero = nothing unusual."""
        f = dict.fromkeys(PASS_FEATS, 0.0)
        if not self.ok:
            return f
        if self.ftn_ok:
            br = self.blitz_rate.get(de, self.lg_blitz) - self.lg_blitz
            sp = self.blitz_qb.get(qb_pid, np.nan) if qb_pid is not None else np.nan
            sp = self.blitz_team.get(off, 0.0) if not np.isfinite(sp) else sp
            f["blitz"] = float(br * sp)
            for k in ("play_action", "screen", "motion"):
                r = self.off_rate[k].get(off, self.lg_rate[k]) - self.lg_rate[k]
                f[k] = float(r * self.def_split[k].get(de, 0.0))
        if len(self.ttt) and len(self.press_rate) and qb_pid is not None:
            f["ttt_pressure"] = float((self.ttt.get(qb_pid, self.lg_ttt) - self.lg_ttt) *
                                      (self.press_rate.get(de, self.lg_press) - self.lg_press))
        cov, rush = self.cov.shift(de, available=available) if available is not None else (0.0, 0.0)
        f["coverage"], f["pass_rush"] = cov, rush
        return f

    def rush_feats(self, off, de) -> dict:
        f = dict.fromkeys(RUSH_FEATS, 0.0)
        if self.ok and self.ftn_ok:
            f["box"] = float((self.box_rate.get(de, self.lg_box) - self.lg_box) * self.box_split.get(off, 0.0))
        return f
