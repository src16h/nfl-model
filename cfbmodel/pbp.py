"""
Turns ESPN game summaries into the model's tables.

  plays        every snap with down, distance and field position
  EP           our own expected-points table (what a down, distance and yard
               line is worth, measured by the next score in the half)
  team games   one row per team per game: expected points added on passes and
               runs (garbage time left out), success rates, pace, box score
  player games passing, rushing and receiving lines for prop projections
"""
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from . import data as D

log = logging.getLogger("cfbmodel")
DIR = D.ROOT / "data" / "cfb"

PASS_TYPES = {"Pass Reception", "Pass Incompletion", "Passing Touchdown", "Sack", "Interception", "Pass Interception Return",
              "Interception Return Touchdown", "Pass Completion", "Pass", "Pass Interception"}
RUSH_TYPES = {"Rush", "Rushing Touchdown"}
FUMBLE_TYPES = {"Fumble Recovery (Own)", "Fumble Recovery (Opponent)", "Fumble Return Touchdown"}
SKIP_NEXT = {"Timeout", "End Period", "End of Half", "End of Game", "End of Regulation", "Coin Toss"}
EPA_CAP = 4.5                      # one play can't swing a rating more than this (turnovers are mostly luck)


def _clock(s):
    try:
        m, sec = str(s).split(":")
        return int(m) * 60 + int(sec)
    except Exception:  # noqa: BLE001
        return 0


def plays_frame(s):
    """Flat play table for one trimmed summary, with the points and side of the next score in the half."""
    home = next(t["id"] for t in s["teams"] if t["side"] == "home")
    away = next(t["id"] for t in s["teams"] if t["side"] == "away")
    rows = []
    for di, d in enumerate(s["drives"]):
        for p in d["plays"]:
            rows.append(p + [di])
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=D.PLAY_COLS + ["drive"])
    for c in ("down", "dist", "yte", "e_down", "e_dist", "e_yte", "period", "yards", "away_score", "home_score"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["team"] = pd.to_numeric(df["team"], errors="coerce")
    df["secs"] = df["clock"].map(_clock)
    df = df[df["period"].notna()].reset_index(drop=True)
    # some feeds list plays out of order inside a period; the running score never goes down, so sort on it
    df["_o"] = np.arange(len(df))
    df = df.sort_values(["period", "_o"], kind="stable").reset_index(drop=True)
    df["half"] = np.where(df["period"] <= 2, 1, np.where(df["period"] <= 4, 2, df["period"]))   # each OT period on its own
    df["home"], df["away"] = home, away
    ph = df["home_score"].shift(1).fillna(0)
    pa = df["away_score"].shift(1).fillna(0)
    df["dh"] = (df["home_score"] - ph).clip(lower=0)
    df["da"] = (df["away_score"] - pa).clip(lower=0)
    df["m_before"] = np.where(df["team"] == home, ph - pa, pa - ph)       # offense's lead before the snap

    def val(d):
        return np.where(d >= 6, 7.0, np.where(d == 3, 3.0, np.where(d == 2, 2.0, np.where(d == 1, 1.0, 0.0))))
    sv = np.where(df["dh"] > 0, val(df["dh"]), np.where(df["da"] > 0, -val(df["da"]), 0.0))      # + home, - away
    df["score_home"] = sv
    # next score in the half, from each play on (in home's terms)
    nxt = np.zeros(len(df))
    cur, cur_half = 0.0, None
    for i in range(len(df) - 1, -1, -1):
        if df["half"].iat[i] != cur_half:
            cur, cur_half = 0.0, df["half"].iat[i]
        if sv[i] != 0 and abs(sv[i]) != 1:        # extra points ride with their touchdown
            cur = sv[i]
        nxt[i] = cur
    df["next_home"] = nxt
    df["next_off"] = np.where(df["team"] == home, nxt, -nxt)
    df["pts_off"] = np.where(df["team"] == home, sv, -sv)
    ty = df["type"].fillna("")
    snap = df["down"].between(1, 4) & df["yte"].between(1, 99) & df["team"].notna() & ~ty.isin(SKIP_NEXT) & ~ty.str.contains("Kickoff")
    df["snap"] = snap
    txt = df["text"].fillna("").str.lower()
    is_pass = ty.isin(PASS_TYPES) | (ty.isin(FUMBLE_TYPES) & txt.str.contains(r"pass|sack"))
    is_rush = ty.isin(RUSH_TYPES) | (ty.isin(FUMBLE_TYPES) & ~txt.str.contains(r"pass|sack|punt|kick"))
    df["kind"] = np.where(snap & is_pass, "P", np.where(snap & is_rush, "R", ""))
    # state after the play: the next real snap in the same half
    real = ~ty.isin(SKIP_NEXT)
    idx = np.where(real)[0]
    nxt_i = np.full(len(df), -1)
    pos = np.searchsorted(idx, np.arange(len(df)), side="right")
    ok = pos < len(idx)
    nxt_i[ok] = idx[pos[ok]]
    df["nxt"] = nxt_i
    return df


# ---------------------------------------------------------------------
# expected points
# ---------------------------------------------------------------------
class EP:
    """Lookup table: expected next-score points for the offense by down, distance and yards to the end zone."""

    def __init__(self, table=None):
        self.t = np.array(table) if table is not None else None      # [down 1-4][dist 1-30][yte 1-99]

    def fit(self, plays):
        from sklearn.ensemble import HistGradientBoostingRegressor
        p = plays[plays["snap"] & (plays["period"] <= 4)]
        X = np.column_stack([p["down"], np.clip(p["dist"], 1, 30), p["yte"]])
        m = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.06, max_leaf_nodes=24, min_samples_leaf=400,
                                          monotonic_cst=[0, -1, -1], l2_regularization=1.0, random_state=0)
        m.fit(X, p["next_off"])
        g = np.array([[d, k, y] for d in range(1, 5) for k in range(1, 31) for y in range(1, 100)])
        self.t = m.predict(g).reshape(4, 30, 99)
        return self

    def __call__(self, down, dist, yte):
        d = np.clip(np.nan_to_num(np.asarray(down, float), nan=1), 1, 4).astype(int) - 1
        k = np.clip(np.nan_to_num(np.asarray(dist, float), nan=10), 1, 30).astype(int) - 1
        y = np.clip(np.nan_to_num(np.asarray(yte, float), nan=75), 1, 99).astype(int) - 1
        return self.t[d, k, y]

    def save(self, path):
        Path(path).write_text(json.dumps({"table": np.round(self.t, 3).tolist()}, separators=(",", ":")))

    @classmethod
    def load(cls, path=None):
        return cls(json.loads(Path(path or DIR / "ep_model.json").read_text())["table"])


def add_epa(df, ep):
    """Expected points added for every snap."""
    e0 = ep(df["down"], df["dist"], df["yte"])
    n = df["nxt"].to_numpy()
    has = n >= 0
    j = np.where(has, n, 0)
    same_half = has & (df["half"].to_numpy()[j] == df["half"].to_numpy())
    nsnap = same_half & df["snap"].to_numpy()[j]
    e1 = np.where(nsnap, ep(df["down"].to_numpy()[j], df["dist"].to_numpy()[j], df["yte"].to_numpy()[j]), 0.0)
    flip = df["team"].to_numpy()[j] != df["team"].to_numpy()
    e1 = np.where(nsnap & flip, -e1, e1)
    # a kickoff next means this drive ended in a score or the half ended: value is the points
    scored = df["pts_off"].to_numpy()
    scored = np.where(np.abs(scored) == 1, 0, scored)
    epa = np.where(scored != 0, scored - e0, e1 - e0)
    df["ep"], df["epa"] = e0, np.where(df["snap"], epa, np.nan)
    return df


def garbage(df):
    """Blowout snaps that say little about either team."""
    m = df["m_before"].abs()
    return ((df["period"] == 2) & (m > 38)) | ((df["period"] == 3) & (m > 28)) | ((df["period"] == 4) & (m > 22))


# ---------------------------------------------------------------------
# per-game records
# ---------------------------------------------------------------------
def _pair(v, sep="-"):
    try:
        a, b = str(v).replace("/", sep).split(sep)[:2]
        return float(a), float(b)
    except Exception:  # noqa: BLE001
        return np.nan, np.nan


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return np.nan


def game_record(s, ep, sg=None, df=None):
    """(game row, [two team rows], [player rows]) for one finished game. sg: the schedule entry (conferences)."""
    T = {t["side"]: t for t in s["teams"]}
    h, a = T["home"], T["away"]
    line = next((x for x in s["lines"] if x.get("spread") is not None or x.get("total") is not None), None) or {}
    g = {"game_id": s["id"], "season": s["season"], "stype": s["stype"], "week": s["week"], "date": s["date"],
         "neutral": int(s["neutral"]), "conf_game": int(s["conf_game"]), "home_id": h["id"], "away_id": a["id"],
         "home": h["abbr"], "away": a["abbr"], "hs": h["score"], "as": a["score"],
         "ot": int(len(h.get("lines") or []) > 4),
         "spread": line.get("spread"), "total": line.get("total"), "ml_home": line.get("ml_home"), "ml_away": line.get("ml_away"),
         "open_spread": line.get("open_spread"), "open_total": line.get("open_total"), "book": line.get("book"),
         "home_conf": ((sg or {}).get("home") or {}).get("conf"), "away_conf": ((sg or {}).get("away") or {}).get("conf")}
    if sg and g["spread"] is None and sg.get("odds"):
        o = sg["odds"]
        g.update({k: o.get(k) for k in ("spread", "total", "ml_home", "ml_away", "open_spread", "open_total", "book")})
    if g["spread"] is None and g["total"] is None:
        try:
            o = D.core_odds(s["id"])
            g.update({k: o.get(k) for k in ("spread", "total", "ml_home", "ml_away", "open_spread", "open_total", "book")})
        except Exception:  # noqa: BLE001
            pass
    if df is None:
        df = plays_frame(s)
    have = len(df) > 40 and df["snap"].sum() > 60
    if have:
        df = add_epa(df, ep)
        df["gt"] = garbage(df)
    teams = []
    for me, opp in ((h, a), (a, h)):
        b = s["box"].get(str(me["id"]), {})
        cmp_, att = _pair(b.get("completionAttempts"))
        t3m, t3a = _pair(b.get("thirdDownEff"))
        pen_n, pen_y = _pair(b.get("totalPenaltiesYards"))
        r = {"game_id": s["id"], "team_id": me["id"], "opp_id": opp["id"], "home": int(me is h), "pts": me["score"], "opp_pts": opp["score"],
             "pass_att": att, "pass_cmp": cmp_, "pass_yds": _f(b.get("netPassingYards")), "rush_att": _f(b.get("rushingAttempts")),
             "rush_yds": _f(b.get("rushingYards")), "to": _f(b.get("turnovers")), "pen_yds": pen_y, "third_m": t3m, "third_a": t3a,
             "first_downs": _f(b.get("firstDowns"))}
        if have:
            o = df[(df["team"] == me["id"]) & (df["kind"] != "") & ~df["gt"] & (df["period"] <= 4)]
            e = o["epa"].clip(-EPA_CAP, EPA_CAP)
            pm, rm = o["kind"] == "P", o["kind"] == "R"
            dr = [d for d in s["drives"] if str(d.get("team")) == str(me["id"])]
            # offensive touchdowns, whatever the feed called the play
            mine = df["team"] == me["id"]
            td = (df["pts_off"] == 7) & ((df["kind"] != "") | df["type"].isin(["Passing Touchdown", "Rushing Touchdown"]))
            ispass = (df["kind"] == "P") | (df["type"] == "Passing Touchdown")
            r.update({"n_p": int(pm.sum()), "n_r": int(rm.sum()), "epa_p": float(e[pm].sum()), "epa_r": float(e[rm].sum()),
                      "suc_p": int((o["epa"][pm] > 0).sum()), "suc_r": int((o["epa"][rm] > 0).sum()),
                      "exp_p": int((o["yards"][pm] >= 20).sum()), "exp_r": int((o["yards"][rm] >= 12).sum()),
                      "plays_all": int(((df["team"] == me["id"]) & (df["kind"] != "")).sum()),
                      "drives": len(dr),
                      "td_p": int((mine & td & ispass).sum()), "td_r": int((mine & td & ~ispass).sum())})
        teams.append(r)
    players = []
    for me in (h, a):
        cats = s["players"].get(str(me["id"]), {})
        acc = {}
        def put(cat, mapping):
            c = cats.get(cat)
            if not c:
                return
            keys = c["keys"]
            for pid, name, st in c["rows"]:
                if not pid or str(pid).startswith("-"):
                    continue
                d = acc.setdefault(pid, {"game_id": s["id"], "date": s["date"], "team_id": me["id"], "pid": int(pid), "name": name})
                for k, v in zip(keys, st):
                    if k in mapping:
                        if "/" in k:
                            x, y = _pair(v)
                            d[mapping[k][0]], d[mapping[k][1]] = x, y
                        else:
                            d[mapping[k]] = _f(v)
        put("passing", {"completions/passingAttempts": ("pass_cmp", "pass_att"), "passingYards": "pass_yds", "passingTouchdowns": "pass_td",
                        "interceptions": "pass_int"})
        put("rushing", {"rushingAttempts": "rush_att", "rushingYards": "rush_yds", "rushingTouchdowns": "rush_td"})
        put("receiving", {"receptions": "rec", "receivingYards": "rec_yds", "receivingTouchdowns": "rec_td"})
        players += list(acc.values())
    return g, teams, players


# ---------------------------------------------------------------------
# tables on disk
# ---------------------------------------------------------------------
def load_tables():
    g = pd.read_csv(DIR / "games.csv")
    t = pd.read_csv(DIR / "team_games.csv")
    p = pd.read_csv(DIR / "player_games.csv")
    return g, t, p


def save_tables(games, tg, pl, player_seasons):
    DIR.mkdir(parents=True, exist_ok=True)
    games = games.drop_duplicates("game_id").sort_values(["date", "game_id"], kind="stable")
    tg = tg.drop_duplicates(["game_id", "team_id"]).merge(games[["game_id", "date"]], on="game_id").sort_values(["date", "game_id", "home"], kind="stable").drop(columns="date")
    games.to_csv(DIR / "games.csv", index=False, float_format="%.3f")
    tg.to_csv(DIR / "team_games.csv", index=False, float_format="%.3f")
    if len(pl):                      # plain CSV in date order: each run only appends, so git stores small diffs
        keep = set(games.loc[games["season"].isin(player_seasons), "game_id"])
        pl = pl[pl["game_id"].isin(keep)].drop_duplicates(["game_id", "pid"]).sort_values(["date", "game_id", "team_id"], kind="stable")
        pl.to_csv(DIR / "player_games.csv", index=False, float_format="%.1f")
    return games, tg, pl


def update(sched, player_seasons, workers=6):
    """Add every finished game in `sched` (schedule entries) that isn't stored yet. Returns the three tables."""
    games, tg, pl = load_tables()
    have = set(games["game_id"])
    todo = [g for g in sched if g["done"] and g["game_id"] not in have and g["home"]["score"] is not None]
    log.info(f"college football: {len(todo)} new finished games")
    if not todo:
        return games, tg, pl
    ep = EP.load()

    def one(sg):
        try:
            s = D.summary(sg["game_id"])
            if s["state"] != "STATUS_FINAL":
                return None
            return game_record(s, ep, sg)
        except Exception as e:  # noqa: BLE001
            log.warning(f"game {sg['game_id']} skipped: {e}")
            return None

    with ThreadPoolExecutor(workers) as ex:
        out = [x for x in ex.map(one, todo) if x]
    if not out:
        return games, tg, pl
    games = pd.concat([games, pd.DataFrame([o[0] for o in out])], ignore_index=True)
    tg = pd.concat([tg, pd.DataFrame([x for o in out for x in o[1]])], ignore_index=True)
    pl = pd.concat([pl, pd.DataFrame([x for o in out for x in o[2]])], ignore_index=True)
    return save_tables(games, tg, pl, player_seasons)
