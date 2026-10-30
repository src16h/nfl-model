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

# defense vs position (dvp.py): moves targets and yards between WR / TE / RB by matchup.
# Set by tools/backtest_dvp.py (Oct 26 2026): 18,203 player-games 2022-25, tuned on 2022-24, checked on 2025.
# Small but real: 2025 target error -0.26%, yards error -0.10% vs no matchup; players it boosted most beat
# their usual targets by about 8%. Position stats are noisy, hence the half / quarter strengths.
DVP_ON = True
DVP_PRIOR_SEASON_W = 0.8     # last season's games count this much vs this season's
DVP_K_TGT = 40.0             # expected targets of "no difference" mixed in (bigger = more cautious)
DVP_K_YDS = 400.0            # same, in receiving yards
DVP_STRENGTH = 0.5           # targets: share of the raw factor used (0 = off, 1 = full)
DVP_STRENGTH_YPT = 0.25      # yards per target: share of the raw factor used
DVP_CAP = 1.5                # largest raw factor either way

# Free charting data (matchups.py). Tested Oct 26 2026 on 2022-25: only these two held up.
COVERAGE_ON = True           # PFR: missing cover players make the pass defense weaker for props
COVERAGE_COEF = 0.6          # yards per dropback per yard-per-target the secondary loses (backtest: 1.15 in 2022-24, 0.2 in 2025)
COVERAGE_MAX = 0.06          # cap: never move passing yards more than 6% either way
INT_WORTHY_BLEND = 0.5       # FTN: share of the QB interception rate taken from interception-worthy throws

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
ODDS_BOOKS = ["hardrockbet", "draftkings", "fanduel", "betmgm", "williamhill_us", "espnbet", "betrivers",
              "fanatics", "bovada"]   # Hard Rock first: the price you actually bet (Oct 20 2026)
SHARP_BOOKS = ["pinnacle"]   # referee price for game plays; rides in the same call (10 books = 1 region of credits)
# Which prop types to load. Each one costs about 1 credit per game. Add more from
# nflmodel/oddsapi.py (MARKETS), for example "player_pass_tds" or "player_rush_attempts".
ODDS_PROP_MARKETS = ["player_pass_yds", "player_rush_yds", "player_reception_yds",
                     "player_receptions", "player_anytime_td", "player_tds_over"]   # tds_over = 2+ TDs
# Oct 26 2026: completions, attempts and carries give the alt parlays their count-stat legs (book main lines).
# About 3 more credits per game, so they start with the Nov 1 credit reset.
ODDS_EXTRA_PROP_MARKETS = ["player_pass_completions", "player_pass_attempts", "player_rush_attempts"]
ODDS_EXTRA_FROM = "2026-11-01"
ODDS_HOURS_AHEAD = 30        # only load props for games starting within this many hours
ODDS_REFRESH_HOURS = 72      # load each game's props once per week (about 5 credits per game)
ODDS_PROPS_CLOSE_HOURS = 3.5 # games with a locked prop play get one more props pull this close to kickoff (closing price)
ODDS_MAX_CREDITS_PER_RUN = 100   # hard stop for one run
ODDS_CREDIT_RESERVE = 25     # never spend the last credits of your month

# ---------------------------------------------------------------
# v6: BEST PLAYS AND FASTER UPDATES
# ---------------------------------------------------------------
# Props are sorted into three groups by the gap between the model and the book:
#   Play: 4 to 15% AND clears betrules.py (blended with the book, profit at the price)
#   Watch: 7 to 15%    shown on the Props tab, not a play, still graded
#   Too big: 15%+      hidden behind a toggle, still graded (usually missing info)
PROP_PLAY_MIN = 0.04
PROP_PLAY_MAX = 0.15         # Oct 2026: a candidate becomes a Play only if it clears betrules.py (blend with the book, profit at the price)
PROP_WATCH_MAX = 0.15
# Prop types allowed to be a Play. Anytime TD stays in Watch until it proves itself.
PROP_PLAY_STATS = ["pass_yds", "rush_yds", "rec_yds"]   # receptions removed Oct 2026: 15-23 as plays, heavy juice
# Sides allowed to be a Play (Oct 21 2026). Yardage plays so far: Unders 41-23 (+13.3u), Overs 26-25 (-1.8u); across every
# graded lean Overs hit 44% (576) vs Unders 56% (641). Books shade Overs, so Overs stay leans until they show an edge.
PROP_PLAY_SIDES = ["Under"]
# A "No TD" pick needs a real No price from the book. Without one it is never flagged.
TD_NO_NEEDS_PRICE = True

# Game plays use the market-anchored engine. Set to None to switch one off.
PROP_MODEL_WEIGHT = 0.4      # NFL props: model's share vs the book (Oct 18 2026: book more accurate; 0.4 took past plays from -1.7% to +5.7%)
# Prop plays (Oct 20 2026): the book was a better forecaster than the model on props, so a play also needs the
# market's consensus (other US books' no-vig price at the same line) to rate your book's price as fair or better,
# and at most PROP_CAP_TEAM plays per team per game.
PROP_CONS_MIN_EV = -2.5          # % expected return at your book's price vs the consensus fair chance. 0 blocked every prop for two weeks (Oct 21-29: best -1.3%); -2.5 means Hard Rock beats a typical book's price (about half the usual margin)
PROP_CONS_MIN_BOOKS = 2          # other books that must post the same line
PROP_CAP_TEAM = 2
ALT_TICKET_K = 30                # alt-parlay record counts half after this many graded tickets
TD_PROB_SCALE = 1.0          # retired Oct 20 2026 (flat boost made likely scorers worse); see TD_CURVE
# TD calibration curve, logit(p') = a + b*logit(p). Fit Oct 20 2026 on 670 graded anytime TDs (weeks 4-7), counting
# players who played without a touch (they were dropped before, which inflated real TD rates). Full fit a=-0.20,
# b=0.72; used at half strength while the sample is small. Beat the raw model and the old flat x1.15 in 2 of 3
# held-out weeks.
TD_CURVE = (-0.10, 0.86)
GAME_PLAY_SPREAD = 1.5       # spread gap (points) that makes a spread Play
GAME_PLAY_TOTAL = None       # totals: off, the backtest shows no edge

# Live game lines are cached between runs so frequent updates don't burn credits.
ODDS_LINES_EVERY_HOURS = 22      # refresh spreads and totals once a day (keeps the month under 500 credits)
ODDS_LINES_GAMEDAY_HOURS = 2.5   # game days: every pre-kickoff run refreshes (near-closing prices for CLV, about 2 credits)
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
CPOE_SHRINK_ATT = 150
Q1_CATCH_SHARE = 0.22            # chance a given catch happens in the 1st quarter (2023-25: 21-22%)
Q1_PASS_SHARE = 0.218           # QB: share of passing yards thrown in the 1st quarter
Q1_PASS_KAPPA = 10.3            # how much that share moves game to game (beta concentration)
Q1_YPC_SHAPE = 1.3               # spread of yards on a single catch (fit to 2023-25 Q1 games)
# first half, from 2022-25 games: halftime margin = 0.63 x full-game margin,
# halftime total = 0.49 x full-game total + 1.0
H1_MARGIN_SLOPE = 0.628
H1_TOTAL_SLOPE = 0.493
H1_TOTAL_INTERCEPT = 0.97
H1_MARGIN_SD = 9.84
H1_TOTAL_SD = 8.62            # QB completion % over expected: attempts before it's fully trusted
# Backtest 2015-2025 (walk-forward). Football-only engine (projected scores without Vegas):
EXTRA_MARGIN_FEATS = ["sr_diff", "cpoe_diff", "surface_switch"]   # better in both 2015-19 and 2020-25
EXTRA_TOTAL_FEATS = ["cpoe_sum", "precip"]                         # better overall, mostly since 2020
# Market-anchored engine (the one that makes picks): only what beat Vegas in both halves
EXTRA_ANCHOR_MARGIN_FEATS = []   # tested sr_diff, cpoe_diff, surface_switch: Vegas already prices them
EXTRA_ANCHOR_TOTAL_FEATS = ["turf"]
# Tested and left out (no gain): heat (both engines), sr_sum (hurt the anchored total)

# ------------------------------------------------------------
# v10: same-game parlays. One simulated game drives both teams' players and the
# final score. Weights tuned so simulated correlations match 2022-25 games
# (e.g. WR1 yds vs his QB 0.46, RB1 rush yds vs team margin 0.30, team TDs vs points 0.80).
# ------------------------------------------------------------
SGP_PACE_PASS = 0.199        # shared game pace -> both passing scripts
SGP_PACE_RUSH = 0.197        # shared game pace -> both rushing scripts
SGP_OWN_PASS = 0.514         # team's own efficiency -> its passing
SGP_OPP_PASS = 0.302         # opponent's efficiency -> more passing (playing from behind)
SGP_OWN_RUSH = 0.297         # own efficiency -> more rushing
SGP_OPP_RUSH = 0.312         # opponent's efficiency -> less rushing
SGP_PASS_RUSH = -0.35        # passing vs rushing for the same team (they share plays)
SGP_PTS_TD = 1.465           # team points blend: touchdowns
SGP_PTS_PASS = 0.484         #                    passing yards
SGP_PTS_RUSH = 0.551         #                    rushing yards
SGP_DRAWS = 1000             # simulated games published per matchup for the parlay helper

# ------------------------------------------------------------
# v11: model-built alt-line parlay for every game
# ------------------------------------------------------------
ALT_PARLAY_ODDS = (-120, 125)      # target fair odds range for the whole parlay (Oct 26 2026: was +100 to +125, with 4 legs)
# Alt lines and team totals (altlines.py, Oct 21 2026): Hard Rock's alt prices, Pinnacle's ride along in the same call.
# 1 credit per market per game, pulled once per game on the last run before kickoff (after inactives), team totals
# for every game first, then alt spreads, then alt totals, and never below ALT_MIN_LEFT credits (props come first).
# Oct 21 2026: Pinnacle's own team totals (exact referee for team totals) and Hard Rock's 1st-half spread and total added.
ALT_MARKETS = ["alternate_team_totals", "team_totals", "spreads_h1", "totals_h1", "alternate_spreads", "alternate_totals"]
ALT_BOOKS = ["hardrockbet", "pinnacle"]
ALT_HOURS = 3.5                    # pull for games kicking off within this many hours
ALT_MIN_LEFT = 90                  # credits always left for next week's props and lines
ALT_MAX_PER_RUN = 30
ALT_SPEC = {"spread": (-24.5, 24.5, 0.5), "total": (28.0, 64.0, 0.5), "team_total": (6.5, 40.5, 0.5)}    # price-check ladders
ALT_LEG_SPEC = {"spread": (-10.5, 17.5, 1.0), "total": (33.5, 57.5, 1.0), "team_total": (10.5, 31.5, 1.0)}  # parlay legs
ALT_LEG_RANGE_TEAM = (0.70, 0.92)
ALT_PLAY_CAP = 8                   # alt-line plays per kickoff date, best value first
ALT_PER_GAME = {"full": 1, "h1": 1}  # per game: one full-game alt line or team total, one 1st-half bet
ALT_MAX_TEAM_LEGS = 2
ALT_PARLAY_LEGS = 3                # preferred number of legs (Oct 26 2026: was 4; falls back to ALT_PARLAY_SIZES)
ALT_PARLAY_SIZES = (3, 4)          # tried in this order
ALT_TYPE_WEEKS = 4                 # leg-type gate (altcal.type_table): recent graded weeks it looks at
ALT_TYPE_MIN_N = 80                # alt lines graded before a type can be shut off
ALT_TYPE_MAX_MISS = 3.0            # shut off a leg type hitting more than this many points below the model
ALT_NO_QUESTIONABLE = True         # Questionable players: 56% real vs 80% model on alt legs, weeks 5-7
ALT_BOOK_MAIN_ONLY = True          # legs only for players with a posted book line (model-only lines: 65% vs 77%)
ALT_BET_CUSHION = 0.07             # "bet at": the book must pay enough for +7% at the model's chance (estimation error)
ALT_LEG_RANGE = (0.70, 0.92)       # single-leg chance window ("alt down" lines), after calibration
ALT_CAL_K = 60                     # leg calibration counts half after this many graded player-games per leg type
ALT_MAX_YARD_LEGS = 3              # at most 3 yardage legs (pass/rush/rec yds); catches fill the rest
ALT_MAX_RUSH_LEGS = 1              # at most 1 RB rushing leg while the leg calibration is still learning
ALT_STEP = {"pass_yds": 10, "rush_yds": 5, "rec_yds": 5, "rec": 1, "pass_cmp": 1, "pass_att": 1, "carries": 1}   # alt line steps (.5 lines)
ALT_MAX_DROP = {"pass_yds": 50, "rush_yds": 25, "rec_yds": 25, "rec": 2, "pass_cmp": 5, "pass_att": 5, "carries": 4}   # how far below the main line books go
ALT_MAX_RISE = {"rec": 3, "pass_cmp": 5, "pass_att": 5, "carries": 4}      # Under legs: how far ABOVE the main line (alt up)
ALT_MIN_MAIN = {"pass_yds": 149.5, "rush_yds": 29.5, "rec_yds": 24.5, "rec": 3.5, "pass_cmp": 14.5, "pass_att": 22.5, "carries": 9.5}  # skip players books rarely post
ALT_MIN_LINE = {"pass_yds": 149.5, "rush_yds": 14.5, "rec_yds": 14.5, "rec": 1.5, "pass_cmp": 10.5, "pass_att": 15.5, "carries": 4.5}  # lowest alt line books offer

# 6-point teasers (model only, no extra odds calls)
TEASER_POINTS = 6
TEASER_PRICES = {2: -120, 3: 160}          # common book prices; the dashboard lets you enter yours
TEASER_HIST_SINCE = 2018
# Wong teaser plays (Oct 19 2026). Checked on every NFL game since 2018 at the closing line:
#   underdogs of +1.5 to +3 teased past 7 won 75.2% (74.0% since 2023); with a game total of 44 or less, 77.8% (74.9%)
#   favorites of -7.5 to -8.5 teased under 3 won only 70.7% (64.3% since 2023), so they are never plays
# A 2-team teaser at -120 needs about 73.9% a leg.
WONG_TOTAL_MAX = 44.0       # low-total games go first (a 6-point move is worth more when fewer points are scored)
WONG_MIN_P = 70.0           # the model's own chance for the leg must agree it is a good spot
WONG_MAX_TICKETS = 3        # 2-team tickets a week, each leg used once
WONG_MIN_EV = 2.0           # a ticket is a play only if it shows this much expected profit at the price
WONG_HIST_WEIGHT = 0.5      # each leg's chance = this share of its historical rate + the rest from the model
WONG_HIST_FALLBACK = {"low": 74.9, "other": 73.1}   # underdog Wong legs since 2023 (low total / higher total), used if history can't load

# New arrivals (trade or signing): share of a player's old-team targets/carries he keeps
# until he has ARRIVAL_WEEKS weeks of his own with the new team.
ARRIVAL_SHARE = 0.80
ARRIVAL_WEEKS = 3
