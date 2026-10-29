"""
Who is available this week.

Sources, in priority order:
  1. data/overrides.csv (you)
  2. official injury report (Out / Doubtful / Questionable)
  3. roster status (injured reserve, cut, practice squad)
"""
import logging
from pathlib import Path
import pandas as pd

from .util import norm_name, normalize_status, pos_group

log = logging.getLogger("nflmodel")
NOT_AVAILABLE_ROSTER = {"RES", "CUT", "RET", "DEV", "SUS", "NWT", "EXE", "UFA", "TRD", "PUP", "NFI"}


def current_roster(rosters: pd.DataFrame | None, season: int, week: int) -> pd.DataFrame | None:
    if rosters is None or not len(rosters):
        return None
    r = rosters.copy()
    r["week"] = pd.to_numeric(r.get("week"), errors="coerce")
    cur = r[(r["season"] == season) & (r["week"] <= week)]
    if len(cur):
        r = cur[cur["week"] == cur["week"].max()]
    else:
        prev = r[r["season"] == season - 1]
        r = prev[prev["week"] == prev["week"].max()] if len(prev) else r
    keep = [c for c in ["team", "gsis_id", "full_name", "position", "depth_chart_position", "status"] if c in r.columns]
    r = r[keep].dropna(subset=["gsis_id"]).drop_duplicates("gsis_id", keep="last")
    r["nname"] = r["full_name"].map(norm_name)
    r["pgroup"] = r["position"].map(pos_group)
    r["roster_ok"] = ~r.get("status", pd.Series("ACT", index=r.index)).fillna("ACT").str.upper().isin(NOT_AVAILABLE_ROSTER)
    return r


def load_overrides(path: Path) -> pd.DataFrame:
    try:
        o = pd.read_csv(path, comment="#", skip_blank_lines=True, dtype=str)
        o.columns = [c.strip().lower() for c in o.columns]
        o = o.dropna(subset=["team", "player", "status"])
        o["team"] = o["team"].str.strip().str.upper()
        o["nname"] = o["player"].map(norm_name)
        o["status"] = o["status"].map(normalize_status)
        o = o.dropna(subset=["status"])
        log.info(f"overrides: {len(o)} rows")
        return o
    except Exception as e:  # noqa: BLE001
        log.warning(f"overrides not read: {e}")
        return pd.DataFrame(columns=["team", "player", "status", "note", "nname"])


def injury_table(injuries, roster, overrides, season, week) -> pd.DataFrame:
    """One row per listed player: team, pid (if known), name, pgroup, status, source."""
    rows = []
    if injuries is not None and len(injuries):
        inj = injuries[(injuries["season"] == season) & (injuries["week"] == week)]
        for _, r in inj.iterrows():
            st = normalize_status(r.get("report_status"))
            if st in ("OUT", "DOUBTFUL", "QUESTIONABLE"):
                rows.append({"team": r.get("team"), "pid": r.get("gsis_id"),
                             "name": r.get("full_name"), "pgroup": pos_group(r.get("position")),
                             "status": st, "source": "injury report"})
    if roster is not None:
        ir = roster[~roster["roster_ok"]]
        for _, r in ir.iterrows():
            rows.append({"team": r["team"], "pid": r["gsis_id"], "name": r["full_name"],
                         "pgroup": r["pgroup"], "status": "IR", "source": "roster"})
    t = pd.DataFrame(rows, columns=["team", "pid", "name", "pgroup", "status", "source"])
    t["nname"] = t["name"].map(norm_name)
    t = t.drop_duplicates(["team", "nname"], keep="first")

    # overrides win
    for _, o in overrides.iterrows():
        mask = (t["team"] == o["team"]) & (t["nname"] == o["nname"])
        t = t[~mask]
        if o["status"] in ("OUT", "DOUBTFUL", "QUESTIONABLE", "IR"):
            pid, pg = None, "UNK"
            if roster is not None:
                hit = roster[(roster["team"] == o["team"]) & (roster["nname"] == o["nname"])]
                if len(hit):
                    pid, pg = hit.iloc[0]["gsis_id"], hit.iloc[0]["pgroup"]
            t = pd.concat([t, pd.DataFrame([{"team": o["team"], "pid": pid, "name": o["player"],
                                             "pgroup": pg, "status": o["status"],
                                             "source": "manual", "nname": o["nname"]}])],
                          ignore_index=True)
    return t


def recently_out_ids(injuries, season, week, lookback=4) -> set:
    """Players listed OUT in the last few weeks (used to spot QBs returning)."""
    if injuries is None or not len(injuries):
        return set()
    i = injuries[(injuries["season"] == season) & (injuries["week"] < week) &
                 (injuries["week"] >= week - lookback)]
    st = i["report_status"].map(normalize_status)
    return set(i.loc[st.isin(["OUT", "DOUBTFUL"]), "gsis_id"].dropna())


ESPN_ABBR = {"WAS": "wsh", "LA": "lar"}          # nflverse code -> ESPN code when they differ


def live_roster_overlay(roster: pd.DataFrame | None) -> pd.DataFrame | None:
    """Fix the weekly roster file with today's ESPN rosters, so a trade or cut counts the same day
    instead of next week. A player moves team only when his name and position group match exactly
    one player in the weekly file; anyone ESPN lists nowhere stays as he was (name spellings differ)."""
    if roster is None or not len(roster):
        return roster
    import json
    import urllib.request
    live = {}
    for team in sorted(roster["team"].dropna().unique()):
        code = ESPN_ABBR.get(team, team.lower())
        url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{code}/roster"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 nfl-model"})
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            log.warning(f"ESPN roster {team} not read: {e}")
            continue
        for grp in d.get("athletes", []):
            for a in grp.get("items", []):
                pg_ = pos_group((a.get("position") or {}).get("abbreviation"))
                live.setdefault((norm_name(a.get("fullName", "")), pg_), []).append(team)
    if len(live) < 1000:                                   # feed mostly down: keep the weekly file as is
        log.warning(f"ESPN live rosters thin ({len(live)} players): not used")
        return roster
    r = roster.copy()
    r["moved_from"] = None
    key_n = r.groupby(["nname", "pgroup"])["gsis_id"].transform("count")
    moves = []
    for i, row in r.iterrows():
        teams = live.get((row["nname"], row["pgroup"]))
        if key_n[i] != 1 or not teams or len(set(teams)) != 1:
            continue
        new = teams[0]
        if new != row["team"]:
            moves.append(f"{row['full_name']} {row['team']}->{new}")
            r.at[i, "moved_from"], r.at[i, "team"] = row["team"], new
            r.at[i, "roster_ok"] = True
    log.info(f"live rosters: {len(live)} players, {len(moves)} team changes since the weekly file"
             + (f": {', '.join(moves[:25])}" if moves else ""))
    return r
