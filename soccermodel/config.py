"""Soccer model settings (Premier League, Championship, La Liga)."""
import os

# league key -> sources. fd = Football-Data.co.uk division, espn = ESPN slug,
# understat = Understat league (None = no free xG, the model uses shots instead), odds = The Odds API sport key
LEAGUES = {
    "epl": {"name": "Premier League", "short": "EPL", "fd": "E0", "espn": "eng.1", "understat": "EPL", "odds": "soccer_epl", "teams": 20},
    "champ": {"name": "Championship", "short": "Champ", "fd": "E1", "espn": "eng.2", "understat": None, "odds": "soccer_efl_champ", "teams": 24},
    "laliga": {"name": "La Liga", "short": "La Liga", "fd": "SP1", "espn": "esp.1", "understat": "La_liga", "odds": "soccer_spain_la_liga", "teams": 20},
}

SEASON = None                    # season start year (2026 = 2026-27). None = guess from today (new season from July)
HIST_SEASONS = 7                 # seasons of history for ratings and the backtest

# team ratings (Dixon-Coles style Poisson with time decay)
HALF_LIFE_DAYS = 300             # a match from 10 months ago counts half (tuned Oct 2026: 240-400 best)
SEASON_CARRY = 0.7               # extra weight cut on last season's games at a season change (rosters turn over)
RATING_PRIOR = 4.0               # league-average matches mixed into every team (shrinks small samples)
XG_WEIGHT = 0.7                  # attack/defence signal: share from xG (or shot-based xG), rest from real goals
SHOT_XG = {"sot": 0.222, "off": 0.063}  # shot-based xG where there is no free xG: fit of Understat xG on shots (EPL, La Liga 2020-26);
                                         # tracks real xG at r = 0.75, then rescaled to each league's scoring level
ALPHA = 0.002                    # L2 shrinkage toward league average (tuned Oct 2026: lighter is better)
PROP_DAYS = 240                  # days of ESPN box scores for player rates (covers last spring at a season start)
DC_RHO = None                    # low-score draw correction; None = fit per league from history

# Fatigue (tested Oct 20 2026 on 5,526 matches): after a midweek cup or European game a side scored about 8% fewer
# goals (+-3%) and conceded about 6% more. Adding it did not improve held-out 2025-26 predictions (log loss 1.0292
# without, 1.0294 with), so it is shown on match cards but not applied. data/soccer/fatigue.json holds the effects in
# use (empty = none); fill it to switch it on.
FATIGUE_CAP = 0.12               # largest fatigue change to a side's expected goals (log scale, about 12%)

# plays. Backtest (Oct 20 2026, 2023-24 to now, early Bet365 prices, 29,565 priced sides): the model alone did NOT beat
# the market. Its "edges" lost money in the two latest seasons and beat the closing line only 16-18% of the time, and the
# markets that looked profitable flipped with small setting changes. Blending any of the model into the closing line also
# made it less accurate. What did beat the close: bets where Pinnacle's fair price (the sharpest book) said the bet
# book's price was value. With the model agreeing on the side: 204 bets, beat the close 52%, +0.75% closing value.
# So Pinnacle is the referee and the model is a veto. Any league, any market, draws included.
SHARP_MIN_EV = 1.5               # bet price must be worth this much (%) at Pinnacle's no-vig chance
SHARP_MAX_EV = 8.0               # bigger gaps usually mean a stale or wrong line, not a gift
MODEL_AGREE = 0.0                # the model's chance must be at least the bet book's (gap in % points)
DAILY_CAP = 4                    # plays per league per day, best first; one per match
PROVISIONAL_N = 150              # suggested stakes capped at 1 unit until this many graded plays show positive CLV

# player props (model fair lines; you type the book's price)
PROP_STATS = ["goal", "sot"]     # anytime goalscorer, shots on target (Over 0.5 / 1.5)
PLAYER_DECAY = 0.97              # each older match counts 3% less
PLAYER_PRIOR_MIN = 450           # minutes of position-average rates mixed in
START_MIN = 76.0                 # average minutes for a starter; subs about 22
SUB_MIN = 22.0
LINEUP_HOURS = 3.0               # fetch confirmed lineups for matches starting within this many hours
BENCH_ON = 0.55                  # chance a named substitute gets on the pitch
LINEUP_POWER = 0.35              # how much a weaker (or stronger) named XI moves the team's expected goals
LINEUP_CAP = 0.10                # never more than 10% either way (unvalidated: kept small on purpose)
PEN_SHARE = 0.75                 # a team's penalty taker gets this share of its penalty xG

# odds: separate free key for soccer (500 credits a month)
ODDS_KEY_ENV = "ODDS_API_KEY_SOCCER"
ODDS_REGIONS = "us,uk"           # US books first (DraftKings); UK books fill leagues US books skip
ODDS_BOOKS = ["hardrockbet", "draftkings", "fanduel", "betmgm", "williamhill_us", "pinnacle", "betfair_ex_uk", "williamhill"]
SHARP_BOOKS = ["pinnacle", "betfair_ex_uk"]   # the referee price: sharp books (Betfair exchange if Pinnacle is missing)
ODDS_PREKO_HOURS = 2.5           # a league with a kickoff this close gets fresh lines (closing prices for CLV)
ODDS_MARKETS = "h2h,totals,spreads"
ODDS_RESERVE = 15
ODDS_EVERY_HOURS = 12            # each league's lines refresh at most this often (plus once near kickoff)
# More markets (Oct 21 2026, altlines.py): Hard Rock sends only the 1X2 for soccer, so these come from the first US book
# in ODDS_BOOKS that posts them (DraftKings, FanDuel, BetMGM), labeled on every play, with Pinnacle's own price as the
# referee in the same call. 1 credit per market per match, once per match, for matches within ALT_HOURS, spent only
# from what's left of the day's allowance after line pulls, in this order:
ALT_MARKETS = ["btts", "draw_no_bet", "alternate_spreads", "alternate_totals", "team_totals"]
ALT_HOURS = 12.0
ALT_KEEP = 3                     # credits kept back for the next near-kickoff line pull
ALT_DAILY_CAP = 4                # plays from these markets per day, best first, one per match
ALT_PARLAY_P = (0.444, 0.50)     # alt parlay: fair +100 to +125, like the NFL and NHL
ALT_PARLAY_LEG = (0.62, 0.95)    # each leg's Pinnacle-implied chance
ALT_BET_CUSHION = 0.07           # "bet at": 7% over fair, like NHL and NBA
PARLAY_LOCK_HOURS = 3.0          # parlay tickets lock this close to kickoff (Oct 31 2026)


def odds_key():
    return os.environ.get(ODDS_KEY_ENV, "").strip()
