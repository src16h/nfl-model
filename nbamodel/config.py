"""NBA model settings."""
import os

SEASON = None                    # season start year (2026 = 2026-27). None = guess from today
N_SIMS = 20000

# team ratings (ratings.py)
DECAY = 0.99                     # each older day counts 1% less (half-life about 69 days); tuned Oct 30 2026
PREV_SEASON_WEIGHT = 0.3         # last season's games count half on top of the decay
PLAYOFF_WEIGHT = 0.7
RIDGE = 3.0                      # pulls each team's offense and defense toward average (in game-weights)
FORM_N = 10                      # team games that set a player's usual minutes and value
ROT_MIN = 14.0                   # regular rotation: at least this many minutes a game...
ROT_APPS = 4                     # ...and at least this many of the last FORM_N games
VAL_REPL = 0.22                  # replacement-level game score per minute
VAL_PRIOR_MIN = 60.0             # minutes of replacement-level play mixed into each player's value
ADJ = {"b2b": 0.972, "loss_own": 0.1883, "loss_opp": 0.1104}   # filled from past seasons by tools/nba_backtest.py

# game sim (gamemodel.py)
MARGIN_SD = 13.5                 # around the model's number; the market's misses run 14.1 (some of that is its own error)
TOTAL_SD = 17.8
MT_CORR = 0.0
OT_PTS = 11.0                    # both teams in an overtime period
# Odds API (props, alt lines, Pinnacle). Without a key: ESPN's free DraftKings lines
ODDS_BOOKS = ["hardrockbet", "draftkings", "fanduel", "betmgm", "williamhill_us"]
SHARP_BOOKS = ["pinnacle"]
PROP_BOOKS = ["hardrockbet", "draftkings"]
ODDS_RESERVE = 20
ODDS_LINES_EVERY_HOURS = 6
ODDS_PREKO_HOURS = 1.5
ODDS_PROP_MARKETS = ["player_points", "player_rebounds", "player_assists", "player_threes", "player_points_rebounds_assists"]
ALT_MARKETS = ["team_totals", "alternate_spreads", "alternate_totals"]
ALT_BOOKS = ["hardrockbet", "pinnacle"]
ALT_HOURS = 6.0


def odds_key():
    return os.environ.get("ODDS_API_KEY_NBA", "").strip()

# props (props.py)
PROP_STATS = ["pts", "reb", "ast", "fg3m", "pra"]
RATE_DECAY = 0.95                # per game: a player's per-minute rates (half-life about 14 games)
MIN_DECAY = 0.80                 # per game: expected minutes lean on the last few games
PRIOR_MIN = 60.0                 # minutes of position-average play mixed into each player's rates
MIN_SD = 0.18                    # game-to-game minutes noise (share of expected minutes)
BLOWOUT_START = 14               # margin where starters start losing minutes
BLOWOUT_PER_PT = 0.012           # share of minutes lost per point beyond that (starters)
TEAM_MIN = 240.0
USAGE_POW = 1.15
PTS_VAR_A = 1.6                  # points spread: variance = A x mean + mean^2 / DISP (fit Oct 30 2026)
LINK = {"pts": 1.0, "ast": 0.7, "fg3m": 0.8, "reb": 0.5}   # how much each stat follows the simulated team score
DISP = {"pts": 5.0, "reb": 8.0, "ast": 6.0, "fg3m": 4.0}   # gamma-Poisson size; fit Oct 30 2026 by tools/nba_props_check.py (2025-26 nights)
INJ_PLAY = {"out": 0.0, "doubtful": 0.15, "questionable": 0.55, "probable": 0.95, "day-to-day": 0.75}
PROP_PLAY_MIN = 0.07
PROP_PLAY_MAX = 0.12
BLOCKED = set()
PROP_CAP_GAME = 2
PROP_CAP_NIGHT = 8
PARLAY_LOCK_HOUR = 17

# alt-line parlays (same targets as NHL)
ALT_LEG_RANGE = (0.70, 0.95)
ALT_LEG_RANGE_TEAM = (0.70, 0.92)
ALT_TARGET_P = (0.444, 0.50)
ALT_SIZES = (4, 3)
ALT_BEAM = 400
ALT_TICKET_K = 30
ALT_BET_CUSHION = 0.07
ALT_DROP = {"pts": 4, "reb": 2, "ast": 2, "fg3m": 1}     # points below the main line a leg may go
ALT_MAX_TEAM_LEGS = 2
ALT_SPEC = {"spread": (-15.5, 15.5, 1.0), "total": (200.5, 250.5, 1.0), "team_total": (95.5, 130.5, 1.0)}
ALT_LEG_SPEC = {"spread": (-12.5, 20.5, 1.0), "total": (195.5, 255.5, 1.0), "team_total": (95.5, 130.5, 1.0)}
ALT_DAILY_CAP = 4

# prop play guards (same as NHL)
PROP_CAP_PER_GAME = {}
PROP_ONEWAY_SHARE = 0.80
PROP_CAP_ONEWAY = 4
PROP_BIAS_DECAY = 0.90
PROP_SIDE_K_STATS = set()
PROP_SIDE_K_MIN = 50

# edge parlays: 2 prop plays from 2 different games
EDGE_LEGS = 2
EDGE_MAX_PER_DAY = 3
EDGE_PAUSED = False
EDGE_MIN_EV = 5.0
