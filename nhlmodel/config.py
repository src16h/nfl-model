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

# scoring-level catch-up (real vs predicted goals over recent games)
GOAL_BIAS_DECAY = 0.995          # about the last 200 team-games
GOAL_BIAS_PRIOR = 100.0          # goals of "no correction" mixed in so it moves gradually

# game sim
GOAL_LINK = -0.1                 # home and away goals pull against each other a little (real totals bunch up). Locked
SHOT_LINK = 0.7                  # 1 = every shot equally dangerous; lower = big shot totals come with a lower shooting %.
                                 # Locked (fits ran 0.4 / 1.0 / 0.7 by season); keeps totals from shifting night to night
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
PROP_PLAY_MAX = 0.12             # raw gap cap; the bar to be a play is set in betrules.py (blend with the book, profit at the price)
# markets that may not be plays (checked Oct 2026: points Overs 1-17, puck-line underdogs 0-5, saves far off;
# totals lean only after the Oct 18 recalibration, until about 150 graded totals show an edge)
BLOCKED = {("points", "Over"), "saves", "pl_dog", "totals"}
# Oct 20 2026: points Unders fired 38-53 a night (7-12 in one game), claimed +7 points over the book on
# plays and delivered 0. Three guards:
PROP_CAP_PER_GAME = {("points", "Under"): 2}   # best N by expected return in each game; the rest are not plays
PROP_BIAS_DECAY = 0.90           # bias nudge: each older day counts 10% less (half-life about a week)
PROP_SIDE_K_STATS = {"points"}   # these stats scale the edge by how much the PLAYS on that side really delivered
PROP_SIDE_K_MIN = 50             # graded plays on a side before that counts

# props
PROP_STATS = ["sog", "points", "goals", "assists", "saves"]
ASSIST_SPLIT = (0.08, 0.26)      # share of goals with 0 and 1 assists (rest have 2)
PLAYER_SOG_CONC = 300.0          # how evenly team shots spread; fit so 1+ and 2+ shot rates match 2025-26 games
SOG_PLAYER_BLEND = 0.7          # team shots: mostly the dressed skaters' own shot rates, partly the team model
TOI_RECENT_WEIGHT = 0.5          # last games' ice time vs season average

# alt-line parlays
ALT_LEG_RANGE = (0.70, 0.97)     # leg chance window AFTER the per-leg-type correction (Oct 18: was 80%+ before calibration)
ALT_TARGET_P = (0.444, 0.50)     # joint chance = fair odds +100 to +125, same as the NFL (Oct 18; Oct 15-18 was -150 to -260)
ALT_SIZES = (4, 3)               # try 4 legs first, then 3
ALT_BEAM = 400                   # partial tickets kept at each step of the search
ALT_CAL_K = 300                  # leg calibration counts half after this many graded player-games per leg type
ALT_MAX_DROP = {"sog": 1, "points": 0, "saves": 0}   # how far below the main line a leg may go
ALT_MAIN_LINE_ONLY = {"saves"}   # Hard Rock Bet has no alt goalie saves: only the posted main line, never a model line

# odds (separate free key for hockey)
ODDS_KEY_ENV = "ODDS_API_KEY_NHL"
ODDS_BOOK = "draftkings"           # (older setting, kept for reference)
ODDS_BOOKS = ["hardrockbet", "draftkings", "fanduel", "betmgm", "williamhill_us"]   # bet book: Hard Rock first (where you bet)
SHARP_BOOKS = ["pinnacle"]       # referee price for plays (rides along in the same call, no extra credits)
PROP_BOOKS = ["hardrockbet", "draftkings"]
ODDS_PREKO_HOURS = 2.0           # games starting this soon get a fresh line pull (near-closing prices for CLV)
ODDS_REGION = "us"
ODDS_RESERVE = 15                # never spend the last credits of the month
# Oct 21 2026: player points pulls dropped (111-121 and -17 units on 232 plays, Overs 5-17). Their credits now pay for
# Hard Rock's team totals and alt lines below. Points still show the model's fair line with a price check.
ODDS_PROP_MARKETS = ["player_shots_on_goal"]   # in priority order
# Alt lines and team totals (altlines.py): Hard Rock's prices, Pinnacle's ride along in the same call for free.
# 1 credit per market per game, spent only from what's left of the day's allowance after props, soonest games
# first, once per game per day. Busy nights get team totals only; lighter nights add alt totals and puck lines.
ALT_MARKETS = ["team_totals", "alternate_totals", "alternate_spreads"]   # in priority order
ALT_BOOKS = ["hardrockbet", "pinnacle"]
ALT_HOURS = 7.0                  # pull for games starting within this many hours (the 5:12pm ET run)
ALT_SPEC = {"spread": (-3.5, 3.5, 1.0), "total": (3.5, 9.5, 0.5), "team_total": (0.5, 5.5, 0.5)}   # price-check ladders
ALT_LEG_SPEC = {"spread": (-1.5, 2.5, 1.0), "total": (4.5, 7.5, 1.0), "team_total": (0.5, 3.5, 1.0)}  # parlay legs
ALT_DAILY_CAP = 4                # alt-line plays per day, best value first, one per game
ALT_MAX_TEAM_LEGS = 2            # team legs (puck line, total, team total) per alt parlay
ODDS_LINES_EVERY_HOURS = 5


def odds_key():
    return os.environ.get(ODDS_KEY_ENV, "").strip()

# edge parlays: 2 prop plays from 2 different games (each leg already beats the book)
EDGE_LEGS = 2
EDGE_MAX_PER_DAY = 3             # each play is used once, so these are separate tickets
EDGE_MIN_EV = 5.0                # parlay expected return in %, at the book's prices
