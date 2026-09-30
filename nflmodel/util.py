"""Small shared helpers."""
import re
import numpy as np
import pandas as pd

from . import config as C

_SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")


def norm_name(name) -> str:
    """'Kenneth Walker III' -> 'kennethwalker' so names match across sources."""
    if name is None or (isinstance(name, float) and np.isnan(name)):
        return ""
    s = str(name).lower().replace(".", " ").replace("'", "").replace("-", " ")
    s = _SUFFIX.sub("", s)
    return re.sub(r"[^a-z]", "", s)


POS_GROUP = {
    "QB": "QB", "RB": "RB", "FB": "RB", "HB": "RB", "WR": "WR", "TE": "TE",
    "T": "OT", "OT": "OT", "LT": "OT", "RT": "OT",
    "G": "OG", "OG": "OG", "LG": "OG", "RG": "OG", "C": "C", "OL": "OG",
    "DE": "EDGE", "EDGE": "EDGE", "OLB": "EDGE",
    "DT": "DT", "NT": "DT", "DL": "DT",
    "LB": "LB", "ILB": "LB", "MLB": "LB",
    "CB": "CB", "S": "S", "FS": "S", "SS": "S", "SAF": "S", "DB": "S",
    "K": "ST", "P": "ST", "LS": "ST",
}


def pos_group(pos) -> str:
    if pos is None or (isinstance(pos, float) and np.isnan(pos)):
        return "UNK"
    return POS_GROUP.get(str(pos).upper(), "UNK")


def normalize_status(s) -> str | None:
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return None
    s = str(s).strip().upper()
    if s.startswith("OUT"):
        return "OUT"
    if s.startswith("DOUBT"):
        return "DOUBTFUL"
    if s.startswith("QUEST"):
        return "QUESTIONABLE"
    if s in ("IR", "RES", "PUP", "NFI", "SUS", "RESERVE"):
        return "IR"
    if s.startswith("ACTIVE"):
        return "ACTIVE"
    if s.startswith("STARTING"):
        return "STARTING_QB"
    return None


def shrink(total, n, prior_mean, k):
    """Empirical-Bayes style: blend a player's rate with the league prior."""
    total = np.asarray(total, dtype=float)
    n = np.asarray(n, dtype=float)
    return (total + prior_mean * k) / (n + k)


def play_weights(df: pd.DataFrame, season: int, week: int,
                 decay: float = None, prior_base: float = None,
                 garbage: bool = True) -> np.ndarray:
    """Recency weights. Current season decays by week, last season fades out."""
    decay = C.RECENCY_DECAY if decay is None else decay
    prior_base = C.PRIOR_SEASON_BASE if prior_base is None else prior_base
    s = df["season"].to_numpy()
    wk = df["week"].to_numpy().astype(float)
    w = np.zeros(len(df))

    cur = (s == season) & (wk < week)
    w[cur] = decay ** np.clip(week - wk[cur] - 1, 0, None)

    prev = s == season - 1
    if prev.any():
        last = np.nanmax(wk[prev])
        pbase = prior_base * C.PRIOR_SEASON_FADE ** max(week - 1, 0)
        w[prev] = pbase * 0.97 ** (last - wk[prev])

    if garbage and "wp" in df.columns:
        wp = df["wp"].to_numpy(dtype=float)
        g = (wp < 0.10) | (wp > 0.90)
        w = np.where(g, w * C.GARBAGE_TIME_WEIGHT, w)
    return w


def before(df: pd.DataFrame, season: int, week: int) -> pd.DataFrame:
    """Rows strictly before (season, week), last two seasons only."""
    m = ((df["season"] == season) & (df["week"] < week)) | (df["season"] == season - 1)
    return df[m]


def fnum(x, nd=1):
    """JSON-safe rounding."""
    try:
        if x is None or not np.isfinite(float(x)):
            return None
        return round(float(x), nd)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------
# Honest-stats helpers
# ---------------------------------------------------------------------
BREAK_EVEN = 0.524   # win rate needed at standard -110 odds


def clean_json(o):
    """Browsers can't read NaN in JSON, so turn it into null."""
    if isinstance(o, dict):
        return {k: clean_json(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean_json(v) for v in o]
    if isinstance(o, (float, np.floating)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return o


def wilson(w, n, z=1.96):
    """95% range for a win rate. Wide range = small sample = could be luck."""
    if n <= 0:
        return 0.0, 1.0
    p = w / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return float((c - m) / d), float((c + m) / d)


def record_stats(w, l):
    """Win rate + 95% range + a plain-English verdict. None if no games."""
    n = int(w + l)
    if n == 0:
        return None
    lo, hi = wilson(w, n)
    pct = w / n
    if lo > BREAK_EVEN:
        v, note = "above", "Clear edge, even the low end beats break-even"
    elif hi < BREAK_EVEN:
        v, note = "below", "Below break-even, would lose money"
    elif pct >= BREAK_EVEN:
        v, note = "unclear", "Above break-even, but could be luck"
    else:
        v, note = "unclear", "Can't tell apart from a coin flip"
    return {"n": n, "pct": round(100 * pct, 1), "ci_lo": round(100 * lo, 1),
            "ci_hi": round(100 * hi, 1), "verdict": v, "note": note}
