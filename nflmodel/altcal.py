"""
Alt-line leg calibration for the alt-line parlays.

Checked Oct 18 2026 on every graded player (week 5): the sims' lower tails are too
thin for yardage. Players clear "alt down" yardage lines less often than the model
says (RB rushing: model 83%, real 70%; TE yards 83% vs 69%; WR yards 83% vs 78%;
QB yards 83% vs 78%), while catches hold up (82% vs 83%). Duds, early exits and
game script happen more than the sims allow.

Each run refits, per leg type, a curve from the model's chance to the real hit rate,
using every graded week in history. The correction fades in with the sample:
weight = player-games / (player-games + ALT_CAL_K), so it starts weak and grows.
"""
import json
import logging
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

from . import config as C

log = logging.getLogger("nflmodel")
STATS = {"QB": ["pass_yds"], "RB": ["rush_yds", "rec"], "WR": ["rec_yds", "rec"], "TE": ["rec_yds", "rec"]}
_CACHE = {}


def group(pos, stat):
    return "rec" if stat == "rec" else f"{pos}_{stat}"


def _logit(p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def fit(hist_dir, results_path, season):
    """Returns {group: (a, b, weight, player_games)}."""
    key = (str(hist_dir), str(results_path), season)
    if key in _CACHE:
        return _CACHE[key]
    out = {}
    try:
        res = json.loads(Path(results_path).read_text())
        cols = res["cols"]
        rows, pgs = {}, {}
        for f in sorted(Path(hist_dir).glob(f"{season}_week*.json")):
            for p in json.loads(f.read_text()).get("players", []):
                mk = p.get("markets")
                pl = (res.get("players") or {}).get(p.get("game_id"))
                if not mk or not pl or p.get("pid") not in pl:
                    continue                                  # did not play: books void the leg
                act = dict(zip(cols, pl[p["pid"]]))
                for st in STATS.get(p.get("pos"), []):
                    m = mk.get(st)
                    if not m or (m.get("med") or 0) < C.ALT_MIN_MAIN[st]:
                        continue
                    g = group(p["pos"], st)
                    pgs[g] = pgs.get(g, 0) + 1
                    if "q" in m:
                        q = np.asarray(m["q"], float)
                        lv = 1 - np.arange(1, len(q) + 1) / (len(q) + 1)
                        pts = [(lv[i], act[st] > q[i]) for i in range(len(q))]
                    else:
                        ge = m.get("ge") or []
                        pts = [(ge[k] / 100, act[st] >= k) for k in range(1, len(ge))]
                    rows.setdefault(g, []).extend((pp, hh) for pp, hh in pts if 0.55 <= pp <= 0.97)
        for g, v in rows.items():
            v = np.asarray(v, float)
            x, y = _logit(v[:, 0]), v[:, 1]

            def nll(w):
                p = np.clip(1 / (1 + np.exp(-(w[0] + w[1] * x))), 1e-6, 1 - 1e-6)
                return -np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)) + 0.002 * (w[0] ** 2 + (w[1] - 1) ** 2)
            a, b = minimize(nll, [0.0, 1.0]).x
            n = pgs.get(g, 0)
            out[g] = (float(a), float(b), n / (n + C.ALT_CAL_K), n)
        log.info("alt leg calibration: " + ", ".join(f"{g} a={a:.2f} b={b:.2f} w={w:.2f} n={n}" for g, (a, b, w, n) in sorted(out.items())))
    except Exception as e:  # noqa: BLE001
        log.warning(f"alt leg calibration skipped: {e}")
        out = {}
    _CACHE[key] = out
    return out


def adjust(cal, pos, stat, p):
    """Model chance -> calibrated chance for one alt leg."""
    c = cal.get(group(pos, stat))
    if not c:
        return p
    a, b, w, _ = c
    x = float(_logit(p))
    return float(1 / (1 + np.exp(-((1 - w) * x + w * (a + b * x)))))
