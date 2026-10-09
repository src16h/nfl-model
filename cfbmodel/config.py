"""College football model settings (Power 4 only on the site)."""
import os

SEASON = None                    # None = the season ESPN says is live
FIRST_SEASON = 2018              # history the model learns from
N_SIMS = 20000

# who is shown
P4_CONFS = {1: "ACC", 4: "Big 12", 5: "Big Ten", 8: "SEC"}
P4_EXTRA = {87: "Ind"}           # Notre Dame plays a Power 4 schedule
FBS_CONFS = {1, 4, 5, 8, 9, 12, 15, 17, 18, 37, 151}
FCS_ID = 0                       # every FCS opponent is treated as one average FCS team

# team ratings (opponent-adjusted, see ratings.py)
PRIOR_GAMES = {"pts": 7.0, "*": 2.5}   # last season's rating counts like this many games (points are noisier than per-play stats)
PRIOR_CARRY = 0.6                # share of last season's rating kept (rest goes to the team's tier average)
PRIOR_OLDER = 0.0                # share of that prior taken from the season before last (tested: no help)
WEEK_DECAY = 1.0                 # 1.0 = every game this season counts the same (tested: fading old weeks did not help)

# plays
PLAY_MIN_EV = 0.5                # a play needs at least this expected return (%) at the book's posted price, vig included
ML_MAX_DOG = 350                 # no moneyline plays on longer shots than this
PROP_PLAY_MIN = 0.06
PROP_PLAY_MAX = 0.12

# props
PROP_STATS = ["pass_yds", "pass_td", "rush_yds", "rec_yds", "rec", "td"]
PLAYER_DECAY = 0.85              # each older game counts 15% less (roles change fast in college)
PREV_SEASON_WEIGHT = 0.35
MIN_SHOW = {"pass_yds": 60.0, "rush_yds": 12.0, "rec_yds": 12.0}      # projection needed to list a player

# alt-line parlays
ALT_PARLAY_ODDS = (100, 125)
ALT_PARLAY_LEGS = 4
ALT_LEG_RANGE = (0.66, 0.90)
ALT_STATS = {"pass_yds": 0.82, "rush_yds": 0.70, "rec_yds": 0.70, "rec": None}   # alt line = this share of the main line (rec: 1 lower)

# teasers
TEASER_POINTS = 6
TEASER_PRICES = {2: -120, 3: 160}

# odds: ESPN's free DraftKings lines for games; optional Odds API key for prop lines
ODDS_KEY_ENV = "ODDS_API_KEY_CFB"
ODDS_BOOK = "draftkings"
ODDS_REGION = "us"
ODDS_RESERVE = 15
ODDS_PROP_MARKETS = ["player_pass_yds", "player_rush_yds", "player_reception_yds"]   # in priority order
ODDS_PROP_HOURS = 30             # pull a game's props once, inside this many hours of kickoff


def odds_key():
    return os.environ.get(ODDS_KEY_ENV, "").strip()

# how far the model is allowed to pull the number off the book's line
# (tested 2021-2025: against closing lines the model adds nothing on spreads and a little on totals;
#  against opening lines it adds a little on both, and lines tend to move toward it)
ANCHOR_SPREAD = 0.12             # model spread counts 12%, the book's 88%
ANCHOR_TOTAL = 0.20
ANCHOR_EARLY = (0.18, 0.25)      # 3+ days before kickoff the line is softer, so the model counts a bit more
ANCHOR_EARLY_DAYS = 3.0
ANCHOR_EARLY_WEEKS = 3           # through this week the model leans on last season, so its weight is halved
MAX_GAP_SPREAD = 8.0             # raw model-vs-book gaps bigger than this lost money in testing
MAX_GAP_TOTAL = 10.0
