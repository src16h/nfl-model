"""
Travel, body clock, and weather.

Weather for upcoming games comes from Open-Meteo (free, no key needed).
Weather for past games comes from the nflverse schedule file.
Domes and retractable roofs are treated as weather-free.
"""
import json
import logging
import math
import urllib.request
from datetime import datetime, timezone

log = logging.getLogger("nflmodel")

# team: (lat, lon, utc offset in standard time, indoor)
STADIUMS = {
    "ARI": (33.5276, -112.2626, -7, True), "ATL": (33.7554, -84.4008, -5, True),
    "BAL": (39.2780, -76.6227, -5, False), "BUF": (42.7738, -78.7870, -5, False),
    "CAR": (35.2258, -80.8528, -5, False), "CHI": (41.8623, -87.6167, -6, False),
    "CIN": (39.0955, -84.5161, -5, False), "CLE": (41.5061, -81.6995, -5, False),
    "DAL": (32.7473, -97.0945, -6, True), "DEN": (39.7439, -105.0201, -7, False),
    "DET": (42.3400, -83.0456, -5, True), "GB": (44.5013, -88.0622, -6, False),
    "HOU": (29.6847, -95.4107, -6, True), "IND": (39.7601, -86.1639, -5, True),
    "JAX": (30.3239, -81.6373, -5, False), "KC": (39.0489, -94.4839, -6, False),
    "LA": (33.9535, -118.3392, -8, True), "LAC": (33.9535, -118.3392, -8, True),
    "LV": (36.0909, -115.1833, -8, True), "MIA": (25.9580, -80.2389, -5, False),
    "MIN": (44.9737, -93.2575, -6, True), "NE": (42.0909, -71.2643, -5, False),
    "NO": (29.9511, -90.0812, -6, True), "NYG": (40.8135, -74.0745, -5, False),
    "NYJ": (40.8135, -74.0745, -5, False), "PHI": (39.9008, -75.1675, -5, False),
    "PIT": (40.4468, -80.0158, -5, False), "SEA": (47.5952, -122.3316, -8, False),
    "SF": (37.4030, -121.9700, -8, False), "TB": (27.9759, -82.5033, -5, False),
    "TEN": (36.1665, -86.7713, -6, False), "WAS": (38.9078, -76.8645, -5, False),
    # old franchise codes that appear in older seasons
    "STL": (38.6328, -90.1885, -6, True), "SD": (32.7831, -117.1196, -8, False),
    "OAK": (37.7516, -122.2005, -8, False),
}
OLD_CODES = {"STL": "LA", "SD": "LAC", "OAK": "LV", "LAR": "LA"}


def miles(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 3959 * 2 * math.asin(math.sqrt(h))


def kickoff_hour_et(row) -> float:
    try:
        hh, mm = str(row.get("gametime") or "13:00").split(":")[:2]
        return int(hh) + int(mm) / 60
    except Exception:  # noqa: BLE001
        return 13.0


def travel(home, away, neutral: bool, ko_hour: float) -> dict:
    h, a = STADIUMS.get(home), STADIUMS.get(away)
    if neutral or h is None or a is None:
        return {"tz_shift": 0.0, "west_early": 0.0, "dist": 0.0}
    tz_shift = float(h[2] - a[2])            # + means away team flew east
    west_early = float(a[2] <= -7 and h[2] == -5 and ko_hour < 14)
    return {"tz_shift": tz_shift, "west_early": west_early, "dist": miles(h, a) / 1000}


def is_indoor(row) -> bool:
    roof = str(row.get("roof") or "").lower()
    if roof in ("dome", "closed"):
        return True
    if roof in ("outdoors", "open"):
        return False
    s = STADIUMS.get(row.get("home_team"))
    return bool(s and s[3])


def weather_features(temp, wind, indoor) -> dict:
    if indoor:
        return {"dome": 1.0, "wind10": 0.0, "cold": 0.0}
    try:
        w = float(wind)
        w = 0.0 if math.isnan(w) else w
    except (TypeError, ValueError):
        w = 0.0
    try:
        t = float(temp)
        t = 60.0 if math.isnan(t) else t
    except (TypeError, ValueError):
        t = 60.0
    return {"dome": 0.0, "wind10": max(w - 10, 0.0), "cold": max(45 - t, 0.0)}


def forecast(home, kickoff_utc: datetime) -> dict | None:
    """Hourly forecast at the home stadium for kickoff + 90 minutes."""
    s = STADIUMS.get(home)
    if s is None or kickoff_utc is None:
        return None
    day = kickoff_utc.strftime("%Y-%m-%d")
    url = ("https://api.open-meteo.com/v1/forecast?"
           f"latitude={s[0]}&longitude={s[1]}"
           "&hourly=temperature_2m,wind_speed_10m,precipitation_probability"
           "&temperature_unit=fahrenheit&wind_speed_unit=mph&timezone=UTC"
           f"&start_date={day}&end_date={day}")
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            d = json.loads(r.read().decode())
        hrs = d["hourly"]["time"]
        target = kickoff_utc.astimezone(timezone.utc).hour + 1
        i = min(range(len(hrs)), key=lambda k: abs(int(hrs[k][11:13]) - target))
        return {"temp": d["hourly"]["temperature_2m"][i],
                "wind": d["hourly"]["wind_speed_10m"][i],
                "precip": d["hourly"].get("precipitation_probability", [None] * len(hrs))[i]}
    except Exception as e:  # noqa: BLE001
        log.info(f"weather unavailable for {home}: {str(e)[:80]}")
        return None
