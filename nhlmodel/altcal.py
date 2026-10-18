"""
Alt-line leg calibration for the NHL same-game parlays (same idea as nflmodel/altcal.py).

Checked Oct 18 2026 on graded games: shots Over 0.5 legs held up (model 81.7%, real 80.2%,
187 legs), shots Over 1.5 legs ran high (71.5% vs 63.0%), and top scorers got a point more
often than the model said (54% vs 68% at the fair line, 198 player-games).

Each run refits, per leg type (stat + line), a curve from the model's chance to the real
hit rate using every graded player in history (their fair-line chance) plus every graded
parlay leg. The correction fades in with the sample: weight = n / (n + ALT_CAL_K).
"""
import json
import logging
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

from . import config as C

log = logging.getLogger("nhlmodel")
IDX = {"sog": 0, "goals": 1, "assists": 2, "points": 3}
_CACHE = {}


def group(stat, line):
    if stat == "sog":
        return f"sog_{min(float(line), 2.5):g}"
    return f"{stat}_{float(line):g}"


def _logit(p):
    p = np.clip(np.asarray(p, float), 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def fit(hist_dir, results_path):
    key = (str(hist_dir), str(results_path))
    if key in _CACHE:
        return _CACHE[key]
    out = {}
    try:
        res = json.loads(Path(results_path).read_text())
        rows, seen = {}, set()
        for f in sorted(Path(hist_dir).glob("*.json")):
            d = json.loads(f.read_text())
            for p in d.get("players", []):
                r = res.get(str(p.get("game_id")))
                box = r and r["p"].get(str(p["pid"]))
                if box is None:
                    continue                                   # did not play: books void the leg
                for st, m in (p.get("m") or {}).items():
                    if st in ("sog", "points") and m.get("pf") is not None and m.get("fair") is not None:
                        rows.setdefault(group(st, m["fair"]), []).append((m["pf"], box[IDX[st]] > m["fair"]))
            for g in d.get("games", []):
                r = res.get(str(g.get("game_id")))
                for L in ((g.get("alt_parlay") or {}).get("legs") or []):
                    if not r or L.get("stat") not in ("sog", "points"):
                        continue
                    k = (g["game_id"], L["pid"], L["stat"], L["line"])
                    box = r["p"].get(str(L["pid"]))
                    if k in seen or box is None:
                        continue
                    seen.add(k)
                    rows.setdefault(group(L["stat"], L["line"]), []).append((L["p"] / 100, box[IDX[L["stat"]]] > L["line"]))
        for g, v in rows.items():
            v = np.asarray(v, float)
            if len(v) < 30:
                continue
            x, y = _logit(v[:, 0]), v[:, 1]

            def nll(w):
                p = np.clip(1 / (1 + np.exp(-(w[0] + w[1] * x))), 1e-6, 1 - 1e-6)
                return -np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)) + 0.002 * (w[0] ** 2 + (w[1] - 1) ** 2)
            a, b = minimize(nll, [0.0, 1.0]).x
            out[g] = (float(a), float(b), len(v) / (len(v) + C.ALT_CAL_K), len(v))
        log.info("alt leg calibration: " + ", ".join(f"{g} a={a:.2f} b={b:.2f} w={w:.2f} n={n}" for g, (a, b, w, n) in sorted(out.items())))
    except Exception as e:  # noqa: BLE001
        log.warning(f"alt leg calibration skipped: {e}")
        out = {}
    _CACHE[key] = out
    return out


def adjust(cal, stat, line, p):
    c = cal.get(group(stat, line))
    if not c:
        return float(p)
    a, b, w, _ = c
    x = float(_logit(p))
    return float(1 / (1 + np.exp(-((1 - w) * x + w * (a + b * x)))))
