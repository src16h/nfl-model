"""
Our own expected-goals data from the NHL's public play-by-play.

Each unblocked shot gets a goal chance from a small logistic model (distance,
angle, shot type, rebound, strength, period). Games are boiled down to:
  data/nhl/games.csv          one row per game: teams, scores, how it ended, xG and shots
  data/nhl/goalie_games.csv   per goalie per game: expected goals faced vs goals allowed
  data/nhl/player_games.csv   per skater per game (recent seasons): ice time, shots, goals, assists, xG
New games are added each run, so the history grows by itself.
"""
import json
import logging
import math
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger("nhlmodel")
ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "data" / "nhl"
API = "https://api-web.nhle.com/v1"
SHOT_TYPES = ["wrist", "snap", "slap", "backhand", "tip-in", "deflected", "wrap-around", "other"]
SHOTS = ("shot-on-goal", "missed-shot", "goal")


def fetch(path, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(f"{API}/{path}", headers={"User-Agent": "nhl-model/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
        except Exception:  # noqa: BLE001
            pass
    return None


def _secs(period, t):
    m, s = t.split(":")
    return (period - 1) * 1200 + int(m) * 60 + int(s)


def shot_rows(pbp):
    """Unblocked shots with model inputs. Empty-net shots are flagged (no goalie)."""
    home_id = pbp["homeTeam"]["id"]
    rows, last = [], {}
    for p in pbp.get("plays", []):
        k = p.get("typeDescKey")
        if k not in SHOTS:
            continue
        d = p.get("details") or {}
        pd_ = p["periodDescriptor"]
        if pd_.get("periodType") == "SO":
            continue
        x, y = d.get("xCoord"), d.get("yCoord")
        if x is None or y is None:
            continue
        team = d.get("eventOwnerTeamId")
        is_home = team == home_id
        hside = p.get("homeTeamDefendingSide")
        # the net being attacked: home defends 'left' (x=-89) so it shoots at x=+89
        if hside in ("left", "right"):
            net = 89 if (hside == "left") == is_home else -89
        else:
            net = 89 if x >= 0 else -89
        dx, dy = abs(net - x), abs(y)
        dist = math.hypot(dx, dy)
        ang = math.degrees(math.atan2(dy, max(dx, 0.1)))
        sc = p.get("situationCode") or "1551"
        ag, ask, hsk, hg = (int(c) for c in sc) if len(sc) == 4 else (1, 5, 5, 1)
        own_sk, opp_sk = (hsk, ask) if is_home else (ask, hsk)
        opp_goalie = (ag if is_home else hg)
        t = _secs(pd_["number"], p["timeInPeriod"])
        prev = last.get(team)
        reb = prev is not None and 0 <= t - prev <= 3
        last[team] = t
        st = d.get("shotType") or "other"
        rows.append({"team_home": int(is_home), "dist": dist, "ang": ang, "type": st if st in SHOT_TYPES else "other",
                     "reb": int(reb), "pp": int(own_sk > opp_sk), "sh": int(own_sk < opp_sk), "en": int(opp_goalie == 0),
                     "ot": int(pd_.get("periodType") == "OT"), "goal": int(k == "goal"), "sog": int(k in ("shot-on-goal", "goal")),
                     "shooter": d.get("shootingPlayerId") or d.get("scoringPlayerId"), "goalie": d.get("goalieInNetId"),
                     "a1": d.get("assist1PlayerId"), "a2": d.get("assist2PlayerId"), "t": t})
    return rows


def design(df):
    X = pd.DataFrame({"d": df["dist"] / 10, "d2": (df["dist"] / 10) ** 2, "ld": np.log1p(df["dist"]),
                      "ang": df["ang"] / 45, "reb": df["reb"], "pp": df["pp"], "sh": df["sh"], "ot": df["ot"]})
    for st in SHOT_TYPES[1:]:
        X["t_" + st] = (df["type"] == st).astype(int)
    X["reb_ang"] = df["reb"] * df["ang"] / 45
    return X


class XG:
    def __init__(self, coef=None):
        self.coef = coef

    def fit(self, shots):
        from sklearn.linear_model import LogisticRegression
        s = shots[shots["en"] == 0]
        X = design(s)
        m = LogisticRegression(C=1.0, max_iter=2000).fit(X, s["goal"])
        self.coef = {"intercept": float(m.intercept_[0]), **dict(zip(X.columns, map(float, m.coef_[0])))}
        return self

    def predict(self, shots):
        X = design(shots)
        z = self.coef["intercept"] + sum(X[c] * self.coef[c] for c in X.columns)
        p = 1 / (1 + np.exp(-z))
        return np.where(shots["en"] == 1, 0.0, p)            # empty-net shots are counted separately


def game_record(pbp, shots, xg_model, box=None):
    """Team, goalie and (optional) player rows for one finished game."""
    df = pd.DataFrame(shots)
    if len(df):
        df["xg"] = xg_model.predict(df)
    h, a = pbp["homeTeam"], pbp["awayTeam"]
    end = (pbp.get("gameOutcome") or {}).get("lastPeriodType") or "REG"
    hs, as_ = h.get("score", 0), a.get("score", 0)
    if end == "SO":                      # official score gives the shootout winner a goal
        reg_h = reg_a = min(hs, as_)
    elif end == "OT":
        reg_h = reg_a = min(hs, as_)
    else:
        reg_h, reg_a = hs, as_
    g = {"game_id": pbp["id"], "season": int(str(pbp["season"])[:4]), "date": pbp["gameDate"], "home": h["abbrev"], "away": a["abbrev"],
         "hs": hs, "as": as_, "reg_h": reg_h, "reg_a": reg_a, "end": end}
    for side, flag in (("h", 1), ("a", 0)):
        s = df[df["team_home"] == flag] if len(df) else df
        reg = s[s["ot"] == 0] if len(s) else s
        g[f"xg_{side}"] = float(reg["xg"].sum()) if len(reg) else 0.0
        g[f"sog_{side}"] = int(reg["sog"].sum()) if len(reg) else 0
        g[f"ff_{side}"] = int(len(reg))
        g[f"en_{side}"] = int(reg[(reg["en"] == 1) & (reg["goal"] == 1)].shape[0]) if len(reg) else 0
    goalies = []
    if len(df):
        for (home_flag, gid), s in df[(df["en"] == 0) & df["goalie"].notna()].groupby(["team_home", "goalie"]):
            team = a["abbrev"] if home_flag == 1 else h["abbrev"]     # goalie defends against the shooting team
            goalies.append({"game_id": pbp["id"], "date": pbp["gameDate"], "team": team, "goalie": int(gid),
                            "xga": float(s["xg"].sum()), "ga": int(s["goal"].sum()), "sa": int(s["sog"].sum())})
    players = []
    if box is not None:
        ixg = df.groupby("shooter")["xg"].sum().to_dict() if len(df) else {}
        names = {r["playerId"]: f"{r['firstName']['default']} {r['lastName']['default']}" for r in pbp.get("rosterSpots", [])}
        pbg = box.get("playerByGameStats") or {}
        for side in ("homeTeam", "awayTeam"):
            team = box[side]["abbrev"]
            st = pbg.get(side) or {}
            for grp in ("forwards", "defense"):
                for p in st.get(grp, []):
                    m, s_ = (p.get("toi") or "0:00").split(":")
                    players.append({"game_id": pbp["id"], "date": pbp["gameDate"], "team": team, "pid": p["playerId"],
                                    "name": names.get(p["playerId"], p["name"]["default"]), "pos": p.get("position"),
                                    "toi": int(m) + int(s_) / 60, "sog": p.get("sog", 0), "goals": p.get("goals", 0),
                                    "assists": p.get("assists", 0), "ixg": round(float(ixg.get(p["playerId"], 0.0)), 3)})
            for p in st.get("goalies", []):
                m, s_ = (p.get("toi") or "0:00").split(":")
                players.append({"game_id": pbp["id"], "date": pbp["gameDate"], "team": team, "pid": p["playerId"],
                                "name": names.get(p["playerId"], p["name"]["default"]), "pos": "G",
                                "toi": int(m) + int(s_) / 60, "saves": p.get("saves", 0), "sa": p.get("shotsAgainst", 0),
                                "starter": int(bool(p.get("starter")))})
    return g, goalies, players


def season_game_ids(season):
    """Regular-season game ids for a season start year, from the league schedule."""
    ids = set()
    for team in TEAMS:
        js = fetch(f"club-schedule-season/{team}/{season}{season + 1}")
        for g in (js or {}).get("games", []):
            if g.get("gameType") == 2:
                ids.add((g["id"], g.get("gameState"), g["startTimeUTC"]))
    return sorted(ids)


TEAMS = ["ANA", "BOS", "BUF", "CAR", "CBJ", "CGY", "CHI", "COL", "DAL", "DET", "EDM", "FLA", "LAK", "MIN", "MTL", "NJD",
         "NSH", "NYI", "NYR", "OTT", "PHI", "PIT", "SEA", "SJS", "STL", "TBL", "TOR", "UTA", "VAN", "VGK", "WPG", "WSH",
         "ARI"]


def update(seasons, player_seasons, xg_model=None, workers=6, max_new=None):
    """Add every finished game not stored yet. Returns the three tables."""
    DIR.mkdir(parents=True, exist_ok=True)
    gp, gkp, plp = DIR / "games.csv", DIR / "goalie_games.csv", DIR / "player_games.csv"
    games = pd.read_csv(gp) if gp.exists() else pd.DataFrame()
    gks = pd.read_csv(gkp) if gkp.exists() else pd.DataFrame()
    pls = pd.read_csv(plp) if plp.exists() else pd.DataFrame()
    have = set(games["game_id"]) if len(games) else set()
    todo = []
    for s in seasons:
        for gid, state, _ in season_game_ids(s):
            if gid not in have and state in ("OFF", "FINAL"):
                todo.append((gid, s in player_seasons))
    if max_new:
        todo = todo[:max_new]
    log.info(f"play-by-play: {len(todo)} new games")
    if not todo:
        return games, gks, pls
    xg_model = xg_model or load_xg()

    def one(item):
        gid, want_box = item
        pbp = fetch(f"gamecenter/{gid}/play-by-play")
        if not pbp or pbp.get("gameState") not in ("OFF", "FINAL"):
            return None
        box = fetch(f"gamecenter/{gid}/boxscore") if want_box else None
        return game_record(pbp, shot_rows(pbp), xg_model, box)

    with ThreadPoolExecutor(workers) as ex:
        out = [x for x in ex.map(one, todo) if x]
    games = pd.concat([games, pd.DataFrame([o[0] for o in out])], ignore_index=True)
    gks = pd.concat([gks, pd.DataFrame([x for o in out for x in o[1]])], ignore_index=True)
    pls = pd.concat([pls, pd.DataFrame([x for o in out for x in o[2]])], ignore_index=True)
    games = games.drop_duplicates("game_id").sort_values(["date", "game_id"])
    games.to_csv(gp, index=False, float_format="%.3f")
    if len(pls):                          # plain CSV in date order: each run only appends, so git stores small diffs
        pls = pls[(pls["game_id"] // 1000000).isin(player_seasons)].sort_values(["date", "game_id"], kind="stable")
        pls.to_csv(plp, index=False, float_format="%.3f")
    gks.sort_values(["date", "game_id"], kind="stable").to_csv(gkp, index=False, float_format="%.3f")
    return games, gks, pls


def load_xg():
    return XG(json.loads((DIR / "xg_model.json").read_text()))
