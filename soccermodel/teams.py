"""One name per club across Football-Data, Understat, ESPN and The Odds API."""
import re
import unicodedata

# canonical name (shown on the site) -> other spellings seen in the sources
NAMES = {
    # England
    "Man City": ["Manchester City", "Man City"],
    "Man United": ["Manchester United", "Man United", "Man Utd", "Manchester Utd"],
    "Newcastle": ["Newcastle United", "Newcastle"],
    "Nottingham Forest": ["Nottm Forest", "Nott'm Forest", "Nottingham Forest", "Nottingham"],
    "Brighton": ["Brighton and Hove Albion", "Brighton & Hove Albion", "Brighton"],
    "Tottenham": ["Tottenham Hotspur", "Tottenham", "Spurs"],
    "West Ham": ["West Ham United", "West Ham"],
    "West Brom": ["West Bromwich Albion", "West Brom", "West Bromwich"],
    "Wolves": ["Wolverhampton Wanderers", "Wolverhampton", "Wolves"],
    "Leeds": ["Leeds United", "Leeds"],
    "Leicester": ["Leicester City", "Leicester"],
    "Coventry": ["Coventry City", "Coventry"],
    "Hull": ["Hull City", "Hull"],
    "Ipswich": ["Ipswich Town", "Ipswich"],
    "Birmingham": ["Birmingham City", "Birmingham"],
    "Blackburn": ["Blackburn Rovers", "Blackburn"],
    "Bolton": ["Bolton Wanderers", "Bolton"],
    "Cardiff": ["Cardiff City", "Cardiff"],
    "Charlton": ["Charlton Athletic", "Charlton"],
    "Derby": ["Derby County", "Derby"],
    "Lincoln": ["Lincoln City", "Lincoln"],
    "Norwich": ["Norwich City", "Norwich"],
    "Preston": ["Preston North End", "Preston"],
    "QPR": ["Queens Park Rangers", "QPR", "Q.P.R."],
    "Stoke": ["Stoke City", "Stoke"],
    "Swansea": ["Swansea City", "Swansea"],
    "Sheffield United": ["Sheffield United", "Sheffield Utd", "Sheff Utd"],
    "Sheffield Wed": ["Sheffield Wednesday", "Sheffield Weds", "Sheff Wed", "Sheffield Wed"],
    "Peterborough": ["Peterborough United", "Peterboro", "Peterborough"],
    "Oxford": ["Oxford United", "Oxford"],
    "Luton": ["Luton Town", "Luton"],
    "Huddersfield": ["Huddersfield Town", "Huddersfield"],
    "Wycombe": ["Wycombe Wanderers", "Wycombe"],
    "Rotherham": ["Rotherham United", "Rotherham"],
    "Plymouth": ["Plymouth Argyle", "Plymouth"],
    "Wigan": ["Wigan Athletic", "Wigan"],
    "Reading": ["Reading"],
    "Barnsley": ["Barnsley"],
    "Blackpool": ["Blackpool"],
    "Bournemouth": ["AFC Bournemouth", "Bournemouth"],
    "Bristol City": ["Bristol City"],
    "Wrexham": ["Wrexham AFC", "Wrexham"],
    "Middlesbrough": ["Middlesbrough"],
    "Millwall": ["Millwall"],
    "Portsmouth": ["Portsmouth"],
    "Southampton": ["Southampton"],
    "Watford": ["Watford"],
    "Sunderland": ["Sunderland"],
    "Burnley": ["Burnley"],
    "Brentford": ["Brentford"],
    "Fulham": ["Fulham"],
    # Spain
    "Athletic Bilbao": ["Athletic Club", "Athletic Bilbao", "Ath Bilbao", "Athletic"],
    "Atletico Madrid": ["Atletico Madrid", "Atlético Madrid", "Ath Madrid", "Atletico de Madrid", "Club Atletico de Madrid"],
    "Betis": ["Real Betis", "Betis", "Real Betis Balompie"],
    "Celta Vigo": ["Celta Vigo", "Celta", "RC Celta", "Celta de Vigo"],
    "Espanyol": ["Espanyol", "Espanol", "RCD Espanyol"],
    "Deportivo": ["Deportivo La Coruna", "La Coruna", "Deportivo", "RC Deportivo"],
    "Oviedo": ["Real Oviedo", "Oviedo"],
    "Racing Santander": ["Racing Santander", "Santander", "Racing"],
    "Real Sociedad": ["Real Sociedad", "Sociedad"],
    "Valladolid": ["Real Valladolid", "Valladolid"],
    "Rayo Vallecano": ["Rayo Vallecano", "Vallecano", "Rayo"],
    "Alaves": ["Alaves", "Deportivo Alaves", "Alavés"],
    "Cadiz": ["Cadiz", "Cádiz"],
    "Almeria": ["Almeria", "UD Almeria"],
    "Las Palmas": ["Las Palmas", "UD Las Palmas"],
    "Leganes": ["Leganes", "CD Leganes"],
    "Granada": ["Granada"],
    "Huesca": ["Huesca", "SD Huesca"],
    "Eibar": ["Eibar", "SD Eibar"],
    "Elche": ["Elche"],
    "Getafe": ["Getafe"],
    "Girona": ["Girona"],
    "Levante": ["Levante"],
    "Malaga": ["Malaga", "Málaga"],
    "Mallorca": ["Mallorca", "RCD Mallorca"],
    "Osasuna": ["Osasuna", "CA Osasuna"],
    "Sevilla": ["Sevilla", "Sevilla FC"],
    "Valencia": ["Valencia"],
    "Villarreal": ["Villarreal"],
    "Barcelona": ["Barcelona", "FC Barcelona"],
    "Real Madrid": ["Real Madrid"],
}


def _key(name):
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower()
    s = s.replace("&", " and ").replace("'", "").replace(".", "")
    s = re.sub(r"\b(fc|afc|cf|sad|cd|ud|rcd|sd|rc|ca|club|de futbol|futbol)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


ALIAS = {}
for _c, _vs in NAMES.items():
    for _v in _vs + [_c]:
        ALIAS[_key(_v)] = _c


def canon(name):
    if name is None or (isinstance(name, float) and name != name):
        return None
    k = _key(name)
    return ALIAS.get(k, k.title())
