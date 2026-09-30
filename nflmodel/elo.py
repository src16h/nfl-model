"""
Elo ratings: a simple, battle-tested second opinion.

Every team starts at 1500. After each game the winner takes points from
the loser, more for bigger wins and upsets. Each offseason ratings drift
one third of the way back to average. 25 Elo points is about 1 point of spread.
"""
import math
import pandas as pd

from .geo import OLD_CODES

K = 20.0
HFA_ELO = 40.0
REGRESS = 1 / 3
PER_POINT = 25.0


def _code(t):
    return OLD_CODES.get(t, t)


def compute(schedules: pd.DataFrame):
    """Returns (pregame elo diff in points by game_id, current ratings dict)."""
    s = schedules.copy()
    s = s.sort_values(["season", "week", "gameday"] if "gameday" in s.columns else ["season", "week"])
    rating, pre, last_season = {}, {}, None
    for _, g in s.iterrows():
        if g["season"] != last_season:
            rating = {t: 1500 + (r - 1500) * (1 - REGRESS) for t, r in rating.items()}
            last_season = g["season"]
        h, a = _code(g["home_team"]), _code(g["away_team"])
        rh, ra = rating.get(h, 1500.0), rating.get(a, 1500.0)
        pre[g["game_id"]] = (rh - ra) / PER_POINT
        if pd.isna(g.get("home_score")) or pd.isna(g.get("away_score")):
            continue
        neutral = str(g.get("location", "Home")).lower().startswith("neutral")
        diff = rh - ra + (0 if neutral else HFA_ELO)
        exp_h = 1 / (1 + 10 ** (-diff / 400))
        mov = g["home_score"] - g["away_score"]
        res = 1.0 if mov > 0 else (0.0 if mov < 0 else 0.5)
        mult = math.log(abs(mov) + 1) * 2.2 / ((abs(diff) * 0.001) + 2.2) if mov != 0 else 1.0
        delta = K * mult * (res - exp_h)
        rating[h], rating[a] = rh + delta, ra - delta
    return pre, rating
