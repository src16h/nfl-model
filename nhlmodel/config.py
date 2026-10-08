"""NHL model settings."""
import os

SEASON = None                    # season start year (2026 = 2026-27). None = guess from today
TRAIN_SINCE = 2021
N_SIMS = 20000

# team form
FORM_DECAY = 0.975               # each older game counts 2.5% less (half-life about 27 games)
FORM_CARRY = 0.35                # share of last season's weight carried into a new season
FORM_PRIOR = 6.0                 # league-average games mixed in
LEAGUE_DECAY = 0.995             # league scoring level: about the last 100 games

# game sim
SOG_DISPERSION = 60.0            # negative binomial size for team shots on goal
OT_GOAL_SHARE = None             # filled from data: share of OT games decided in 3-on-3 (rest go to a shootout)
OT_STRENGTH = 0.35               # how much the stronger team's edge carries into OT
GOALIE_SHRINK_XG = 40.0          # goalie skill is pulled toward average, worth about this many expected goals
PREV_SEASON_WEIGHT = 0.5         # last season's player stats count half
PLAYER_DECAY = 0.985             # each older game counts 1.5% less

# plays
ML_PLAY_EDGE = 3.0               # model win chance minus book's no-vig chance, in %
PL_PLAY_EDGE = 3.0
TOTAL_PLAY_EDGE = 4.0           # scoring drifts during a season, so totals need a bigger gap
PLAY_MAX_EDGE = 10.0             # bigger gaps usually mean the model is missing news
PROP_PLAY_MIN = 0.07             # after removing the slate-wide gap to the book
PROP_PLAY_MAX = 0.12

# props
PROP_STATS = ["sog", "points", "goals", "assists", "saves"]
ASSIST_SPLIT = (0.08, 0.26)      # share of goals with 0 and 1 assists (rest have 2)
PLAYER_SOG_CONC = 60.0           # Dirichlet concentration: how evenly team shots spread (lower = streakier)
SOG_PLAYER_BLEND = 0.5          # team shots: half team model, half the dressed skaters' own shot rates
TOI_RECENT_WEIGHT = 0.5          # last games' ice time vs season average

# alt-line parlays
ALT_PARLAY_ODDS = (100, 125)
ALT_PARLAY_LEGS = 4
ALT_LEG_RANGE = (0.66, 0.90)
ALT_MAX_DROP = {"sog": 1, "points": 0, "saves": 5}   # how far below the main line a leg may go

# odds (separate free key for hockey)
ODDS_KEY_ENV = "ODDS_API_KEY_NHL"
ODDS_BOOK = "draftkings"
ODDS_REGION = "us"
ODDS_RESERVE = 15                # never spend the last credits of the month
ODDS_PROP_MARKETS = ["player_shots_on_goal", "player_points"]   # in priority order
ODDS_LINES_EVERY_HOURS = 5


def odds_key():
    return os.environ.get(ODDS_KEY_ENV, "").strip()
