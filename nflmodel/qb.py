"""
Quarterback logic. The single biggest injury factor in the NFL.

Expected starter, in order:
  1. STARTING_QB override in data/overrides.csv
  2. season leader coming back from an injury (was listed OUT recently)
  3. whoever took most dropbacks in the team's last 2 games (and is available)
  4. most experienced available QB on the roster

Adjustment = (expected starter quality - quality the ratings already assume)
             x expected dropbacks x scale
"""
import numpy as np
import pandas as pd

from . import config as C
from .util import shrink, play_weights


def qb_weeks_fast(pbp_before: pd.DataFrame, season: int, week: int) -> pd.DataFrame:
    """Dropbacks and EPA per QB per team-week, straight from play-by-play."""
    p = pbp_before[(pbp_before["qb_dropback"] == 1) & pbp_before["posteam"].notna()]
    pid = np.where(p["qb_scramble"] == 1, p["rusher_player_id"], p["passer_player_id"])
    d = pd.DataFrame({"season": p["season"].to_numpy(), "week": p["week"].to_numpy(),
                      "posteam": p["posteam"].to_numpy(), "pid": pid,
                      "epa": p["epa"].fillna(0).to_numpy()}).dropna(subset=["pid"])
    qw = d.groupby(["season", "week", "posteam", "pid"]).agg(
        dropbacks=("epa", "size"), epa=("epa", "sum")).reset_index()
    qw["rw"] = play_weights(qw, season, week, garbage=False)
    return qw


def incumbent(qw: pd.DataFrame, team: str):
    """The QB the team ratings are mostly built on."""
    tw = qw[qw["posteam"] == team]
    s = (tw["dropbacks"] * tw["rw"]).groupby(tw["pid"]).sum()
    return s.idxmax() if len(s) and s.max() > 0 else None


def adj_value(qual: pd.DataFrame, expected, inc, dropbacks: float) -> float:
    if expected is None or expected == inc:
        return 0.0
    q = lambda pid: float(qual.loc[pid, "epa_db"]) if pid is not None and pid in qual.index else C.QB_REPLACEMENT_EPA
    v = (q(expected) - q(inc)) * dropbacks * C.QB_POINTS_SCALE
    return float(np.clip(v, -C.QB_ADJ_CAP, C.QB_ADJ_CAP))


def qb_quality(qb_weeks: pd.DataFrame, season: int) -> pd.DataFrame:
    """Shrunk EPA per dropback per QB (current season full weight, last season 60%)."""
    q = qb_weeks[qb_weeks["season"] >= season - 1].copy()
    q["sw"] = np.where(q["season"] == season, 1.0, 0.6)
    g = q.assign(n=q["dropbacks"] * q["sw"], e=q["epa"] * q["sw"]).groupby("pid")[["n", "e"]].sum()
    g["epa_db"] = shrink(g["e"], g["n"], C.QB_PRIOR_EPA, C.QB_PRIOR_K)
    return g


def expected_qbs(teams, u: dict, roster, inj_table, overrides, recent_out, season, week, ctx) -> dict:
    qw = u["qb_weeks"]
    qual = qb_quality(qw, season)
    names = u["names"]
    unavailable = set(inj_table.loc[inj_table["status"].isin(["OUT", "DOUBTFUL", "IR"]), "pid"].dropna())

    def nm(pid):
        if pid is None:
            return "Unknown QB"
        if roster is not None:
            hit = roster[roster["gsis_id"] == pid]
            if len(hit):
                return hit.iloc[0]["full_name"]
        return names.get(pid, pid)

    def quality(pid):
        if pid is None or pid not in qual.index:
            return C.QB_REPLACEMENT_EPA
        return float(qual.loc[pid, "epa_db"])

    out = {}
    for team in teams:
        tw = qw[qw["posteam"] == team]
        cur = tw[tw["season"] == season]

        # candidates: roster QBs + anyone who threw for this team this season
        cands = set(cur["pid"])
        if roster is not None:
            rq = roster[(roster["team"] == team) & (roster["pgroup"] == "QB") & roster["roster_ok"]]
            cands |= set(rq["gsis_id"])
            on_team = set(roster.loc[roster["team"] == team, "gsis_id"])
            cands = {c for c in cands if c in on_team} or cands
        avail = [c for c in cands if c not in unavailable]

        expected, why = None, ""
        ov = overrides[(overrides["team"] == team) & (overrides["status"] == "STARTING_QB")]
        if len(ov):
            target = ov.iloc[-1]["nname"]
            if roster is not None:
                hit = roster[(roster["team"] == team) & (roster["nname"] == target)]
                expected = hit.iloc[0]["gsis_id"] if len(hit) else None
            why = "manual override"
            if expected is None:
                why = "manual override (no stats found, using backup-level value)"

        if not why and avail:
            # established starter: this season + half of last season, with this team
            est_w = tw[tw["season"] >= season - 1]
            est = (est_w["dropbacks"] * np.where(est_w["season"] == season, 1.0, 0.5)).groupby(est_w["pid"]).sum()
            recent_wks = sorted(cur["week"].unique())[-2:]
            recent = cur[cur["week"].isin(recent_wks)].groupby("pid")["dropbacks"].sum()
            e_lead = est.reindex(avail).dropna()
            r_lead = recent.reindex(avail).dropna()
            if len(e_lead) and e_lead.idxmax() in recent_out and \
                    (not len(r_lead) or r_lead.idxmax() != e_lead.idxmax()):
                expected, why = e_lead.idxmax(), "returning from injury"
            elif len(r_lead):
                expected, why = r_lead.idxmax(), "recent starter"
            elif len(e_lead):
                expected, why = e_lead.idxmax(), "established starter"
            else:
                exp = qual["n"].reindex(avail).dropna()
                if len(exp):
                    expected, why = exp.idxmax(), "most experienced available"
                else:
                    expected, why = sorted(avail)[0], "backup with no NFL stats"
        if expected is None and not why:
            why = "no known QB available"

        inc = incumbent(qw, team)
        inc = expected if inc is None else inc
        dropbacks = ctx.lg_plays * ctx.lg_pass_rate if ctx is not None else 36.0
        adj = adj_value(qual, expected, inc, dropbacks)
        out[team] = {"pid": expected, "name": nm(expected), "why": why,
                     "incumbent": nm(inc), "adj": adj,
                     "epa_db": quality(expected)}
    return out
