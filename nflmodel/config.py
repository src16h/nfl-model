"""
Every tunable number in the model lives here.
Safe to edit. Each setting has a plain-English note.
"""
import os

# Force a season/week (leave blank for automatic detection)
SEASON = int(os.environ["SEASON"]) if os.environ.get("SEASON") else None
WEEK = int(os.environ["WEEK"]) if os.environ.get("WEEK") else None

# ---------------------------------------------------------------
# TEAM RATINGS (built from every offensive play, EPA based)
# ---------------------------------------------------------------
RIDGE_ALPHA_ALL = 300.0      # higher = ratings pulled harder toward average
RIDGE_ALPHA_SPLIT = 220.0    # same, for the separate pass and rush ratings
RECENCY_DECAY = 0.92         # each week back counts 92% as much as the next
PRIOR_SEASON_BASE = 0.60     # weight of last season's plays in week 1
PRIOR_SEASON_FADE = 0.85     # that weight shrinks by 15% each new week
GARBAGE_TIME_WEIGHT = 0.35   # plays when win prob is under 10% or over 90%
SPLIT_BLEND = 0.5            # 0.5 = half pass/rush matchup model, half overall model

# ---------------------------------------------------------------
# GAME MODEL
# ---------------------------------------------------------------
DEFAULT_HFA = 1.5            # home field advantage in points (auto-calibrated)
REST_POINTS_PER_DAY = 0.12   # extra rest vs opponent, points per day
REST_CAP = 1.2
TEAM_SCORE_SD = 9.6          # randomness of one team's score in simulations
N_SIMS = 20000               # simulated games per matchup
MARKET_WEIGHT = 0.0          # 0 = pure model. 0.5 = half model, half Vegas line
LEAN_SPREAD_EDGE = 2.0       # flag a spread lean when model differs by this many points
LEAN_TOTAL_EDGE = 3.0        # flag a total lean at this many points
TD_PER_POINT = 0.105         # offensive touchdowns per point scored (league norm)
LEAGUE_PASS_TD_SHARE = 0.60  # share of offensive TDs that are passing TDs

# ---------------------------------------------------------------
# QUARTERBACKS
# ---------------------------------------------------------------
QB_PRIOR_EPA = -0.05         # typical QB EPA per dropback before we have data
QB_PRIOR_K = 200             # dropbacks before a QB's own numbers dominate
QB_REPLACEMENT_EPA = -0.14   # unknown / emergency QB
QB_POINTS_SCALE = 0.80       # how much of the QB EPA gap turns into points
QB_ADJ_CAP = 10.0            # biggest QB swing allowed, in points

# ---------------------------------------------------------------
# NON-QB INJURIES (points lost when a regular starter is out)
# ---------------------------------------------------------------
STATUS_WEIGHT = {"OUT": 1.0, "IR": 1.0, "DOUBTFUL": 0.85, "QUESTIONABLE": 0.25}
POSITION_VALUE = {
    "OT": 0.50, "OG": 0.35, "C": 0.35,
    "EDGE": 0.55, "DT": 0.35, "LB": 0.30, "CB": 0.50, "S": 0.35,
}
WR_TE_VALUE_PER_TARGET_SHARE = 3.5   # 25% target share WR = about 0.9 points
RB_VALUE_CARRY = 1.0
RB_VALUE_TARGET = 2.0
SKILL_VALUE_CAP = 1.3
INJURY_CAP_PER_SIDE = 4.0    # max combined non-QB injury hit, offense or defense
STARTER_SNAP_PCT = 0.60      # snap share that counts as a regular starter

# ---------------------------------------------------------------
# SCHEME MATCHUPS (man vs zone, used only if data is available)
# ---------------------------------------------------------------
SCHEME_SHRINK_K = 150        # dropbacks before a team's man/zone split is trusted
SCHEME_CAP = 1.5             # max points from scheme matchup

# ---------------------------------------------------------------
# PLAYER PROJECTIONS
# ---------------------------------------------------------------
USAGE_DECAY = 0.85           # recent games matter more for roles
GAME_SCRIPT_PASS_RATE = 0.006  # pass rate drops 0.6% per point a team is favored
TARGETS_PER_ATTEMPT = 0.93
MIN_TARGET_SHARE = 0.05      # show receivers above this share
MIN_CARRY_SHARE = 0.08       # show runners above this share

# Shrinkage priors: (league average, sample size needed to trust player)
PRIORS = {
    "catch_rate": {"WR": (0.63, 40), "TE": (0.70, 40), "RB": (0.77, 40)},
    "yds_per_target": {"WR": (8.2, 60), "TE": (7.3, 60), "RB": (5.8, 60)},
    "ypc": {"RB": (4.3, 80), "QB": (4.8, 40), "WR": (6.5, 20), "TE": (4.0, 20)},
    "qb_cmp": (0.65, 150),
    "qb_ypa": (7.0, 200),
    "qb_int": (0.024, 300),
    "qb_scramble_rate": (0.035, 150),
    "qb_scramble_ypa": (7.0, 30),
}
DEF_SHRINK_K = 250           # plays before a defense's allowed stats are trusted

# Spread of outcomes for yardage ranges (coefficient of variation)
PASS_YDS_CV = 0.27

# ---------------------------------------------------------------
# v2: HISTORY, ML ENSEMBLE, WEATHER, PROPS
# ---------------------------------------------------------------
TRAIN_START_SEASON = int(os.environ.get("TRAIN_START", 2012))  # first season in the deep backtest
TRAIN_RECENCY = 0.88         # each older season counts 88% as much when training
MIN_TRAIN_ROWS = 300         # below this, fall back to simple calibration
GBM_BLEND_OPTIONS = [0.0, 0.25, 0.5]   # share of the machine-learning model, picked by backtest
WALK_FORWARD_SEASONS = 8     # seasons graded in the deep backtest report

KEYNUM_SINCE = 2015          # games used for real score patterns (after the extra-point rule change)
KEYNUM_MIN_GAMES = 80

PLAYER_SIMS = 10000          # simulated games per team for player stats
K_REC = 8.0                  # lower = more week-to-week swing in who gets the yards
K_RUSH = 10.0
PROP_EDGE = 0.04             # flag a prop when the model differs from the book by 4%+

# ---------------------------------------------------------------
# v3: MARKET-ANCHORED ENGINE
# ---------------------------------------------------------------
LEAN_ENGINE = "anchored"     # "anchored" (starts from Vegas) or "independent" (football data only)
ANCHOR_LEAN_SPREAD = 1.0     # anchored engine: flag a spread lean at this many points from Vegas
ANCHOR_LEAN_TOTAL = 1.5      # anchored engine: same, for totals

# ---------------------------------------------------------------
# v5: LIVE ODDS (The Odds API). Turns on when the ODDS_API_KEY secret exists.
# ---------------------------------------------------------------
ODDS_GAME_LINES_ON = True    # live spreads/totals on every run (about 2 credits)
ODDS_PROPS_ON = True         # live player props (about 1 credit per market per game)
# Which sportsbook to trust first. Each line uses the first book on this list that has it.
ODDS_BOOKS = ["draftkings", "fanduel", "betmgm", "williamhill_us", "espnbet", "betrivers",
              "fanatics", "hardrockbet", "bovada"]
# Which prop types to load. Each one costs about 1 credit per game. Add more from
# nflmodel/oddsapi.py (MARKETS), for example "player_pass_tds" or "player_rush_attempts".
ODDS_PROP_MARKETS = ["player_pass_yds", "player_rush_yds", "player_reception_yds",
                     "player_receptions", "player_anytime_td"]
ODDS_HOURS_AHEAD = 30        # only load props for games starting within this many hours
ODDS_REFRESH_HOURS = 72      # load each game's props once per week (about 5 credits per game)
ODDS_MAX_CREDITS_PER_RUN = 100   # hard stop for one run
ODDS_CREDIT_RESERVE = 25     # never spend the last credits of your month

# ---------------------------------------------------------------
# v6: BEST PLAYS AND FASTER UPDATES
# ---------------------------------------------------------------
# Props are sorted into three groups by the gap between the model and the book:
#   Play: 4 to 7%      shown on the Games tab and graded as a play
#   Watch: 7 to 15%    shown on the Props tab, not a play, still graded
#   Too big: 15%+      hidden behind a toggle, still graded (usually missing info)
PROP_PLAY_MIN = 0.04
PROP_PLAY_MAX = 0.07
PROP_WATCH_MAX = 0.15
# Prop types allowed to be a Play. Anytime TD stays in Watch until it proves itself.
PROP_PLAY_STATS = ["pass_yds", "rush_yds", "rec_yds", "rec"]
# A "No TD" pick needs a real No price from the book. Without one it is never flagged.
TD_NO_NEEDS_PRICE = True

# Game plays use the market-anchored engine. Set to None to switch one off.
GAME_PLAY_SPREAD = 1.5       # spread gap (points) that makes a spread Play
GAME_PLAY_TOTAL = None       # totals: off, the backtest shows no edge

# Live game lines are cached between runs so frequent updates don't burn credits.
ODDS_LINES_EVERY_HOURS = 8       # refresh spreads and totals at most this often (both daily runs)
ODDS_LINES_GAMEDAY_HOURS = 3     # when a game kicks off within 12 hours
ODDS_LINES_FLOOR = 120           # below this many credits, stop live line pulls to save credits for props

# ------------------------------------------------------------
# v7: MODEL PICKS (every game gets a spread, total and moneyline pick)
# ------------------------------------------------------------
ODDS_MONEYLINE_LIVE = False      # True: also pull live moneylines with each line refresh (+1 credit each time).
                                 # False: moneylines come from the free data feed (no credits, can lag a bit).
WIN_SIGMA_DEFAULT = 11.4         # win chance curve spread (refit every run from real results)

# ------------------------------------------------------------
# v8: extra context features (each kept only if the backtest says it helps)
# ------------------------------------------------------------
CPOE_SHRINK_ATT = 150            # QB completion % over expected: attempts before it's fully trusted
# Backtest 2015-2025 (walk-forward). Football-only engine (projected scores without Vegas):
EXTRA_MARGIN_FEATS = ["sr_diff", "cpoe_diff", "surface_switch"]   # better in both 2015-19 and 2020-25
EXTRA_TOTAL_FEATS = ["cpoe_sum", "precip"]                         # better overall, mostly since 2020
# Market-anchored engine (the one that makes picks): only what beat Vegas in both halves
EXTRA_ANCHOR_MARGIN_FEATS = []   # tested sr_diff, cpoe_diff, surface_switch: Vegas already prices them
EXTRA_ANCHOR_TOTAL_FEATS = ["turf"]
# Tested and left out (no gain): heat (both engines), sr_sum (hurt the anchored total)
