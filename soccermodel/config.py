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

# plays (same shared rules as the other sports, betrules.py)
PLAY_EDGE = {"1x2": 3.0, "dnb": 3.0, "ah": 3.0, "total": 3.5}   # model minus book no-vig chance, in %
PLAY_MAX_EDGE = 10.0             # bigger gaps usually mean the model is missing news (injuries, rotation)
DRAW_PLAYS = False               # draws are the hardest outcome to price; shown, but not a play until the backtest earns it
# Backtest (Oct 2026, 2023-24 to now, early Bet365 prices, same blend-and-profit rules): only Premier League Asian
# handicap (+9% ROI, 420 bets) and totals (+8%, 187), and Championship Asian handicap (+2%, 513) made money. Every
# La Liga market and every moneyline lost. Picks did not beat the closing line anywhere, so even these are provisional:
# they stay plays only while the live record holds up. Blocked markets still show the model's lean and fair odds.
BLOCKED = {"epl:1x2", "champ:1x2", "champ:total", "laliga:1x2", "laliga:ah", "laliga:total"}

# player props (model fair lines; you type the book's price)
PROP_STATS = ["goal", "sot"]     # anytime goalscorer, shots on target (Over 0.5 / 1.5)
PLAYER_DECAY = 0.97              # each older match counts 3% less
PLAYER_PRIOR_MIN = 450           # minutes of position-average rates mixed in
START_MIN = 76.0                 # average minutes for a starter; subs about 22
SUB_MIN = 22.0
PEN_SHARE = 0.75                 # a team's penalty taker gets this share of its penalty xG

# odds: separate free key for soccer (500 credits a month)
ODDS_KEY_ENV = "ODDS_API_KEY_SOCCER"
ODDS_REGIONS = "us,uk"           # US books first (DraftKings); UK books fill leagues US books skip
ODDS_BOOKS = ["draftkings", "fanduel", "betmgm", "williamhill_us", "pinnacle", "betfair_ex_uk", "williamhill"]
ODDS_MARKETS = "h2h,totals,spreads"
ODDS_RESERVE = 15
ODDS_EVERY_HOURS = 10            # each league's lines refresh at most this often


def odds_key():
    return os.environ.get(ODDS_KEY_ENV, "").strip()
