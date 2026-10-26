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
from .util import norm_name

log = logging.getLogger("nflmodel")
STATS = {"QB": ["pass_yds"], "RB": ["rush_yds", "rec"], "WR": ["rec_yds", "rec"], "TE": ["rec_yds", "rec"]}
_CACHE = {}
PLAYED = set()     # (game_id, normalized name) with an offensive snap; set by run_weekly from snap counts


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
                if not mk or not pl:
                    continue
                if p.get("pid") in pl:
                    act = dict(zip(cols, pl[p["pid"]]))
                elif (p.get("game_id"), norm_name(p.get("name"))) in PLAYED:
                    act = {c: 0.0 for c in cols}              # played, no touch: books grade the leg a loss
                else:
                    continue                                  # did not play: books void the leg
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


# ---------------------------------------------------------------------------------------------------
# Leg-type gate (Oct 26 2026). Checked on 870 alt-down lines in weeks 5-7 (calibration fit on earlier
# weeks only): catches and WR receiving yards hit about as often as the calibrated model said, while
# RB rushing (63% vs 81%), QB passing (72% vs 79%) and TE receiving yards (70% vs 78%) kept missing,
# every single week, and no ranking could pick out the safe ones. A replay of weeks 5-7: tickets built
# only from the types that hold up hit 60% vs 31% for the old mix.
#
# type_table grades every eligible alt-down line each week (the book's main line minus 1 to N steps,
# calibrated chance 70-92%), whether or not it made a ticket, so an excluded type keeps a record and
# comes back on its own once it holds up again.
# ---------------------------------------------------------------------------------------------------
_TT = {}


def type_table(hist_dir, results_path, props_log_path, season, cal):
    """{group: {"n", "model", "actual", "weeks": {wk: [n, model, actual]}}} over recent graded weeks."""
    key = (str(hist_dir), season)
    if key in _TT:
        return _TT[key]
    from .tracker import _p_over
    out = {}
    try:
        res = json.loads(Path(results_path).read_text())
        cols = res["cols"]
        mains = {}
        try:
            for v in json.loads(Path(props_log_path).read_text()).get("props", {}).values():
                if v.get("line") not in (None, ""):
                    mains[(v.get("game_id"), v.get("pid"), v.get("stat"))] = float(v["line"])
        except Exception:  # noqa: BLE001
            pass
        files = sorted(Path(hist_dir).glob(f"{season}_week*.json"))[-C.ALT_TYPE_WEEKS:]
        rows = {}
        for f in files:
            wk = int(f.stem.split("week")[-1])
            for p in json.loads(f.read_text()).get("players", []):
                mk, pl = p.get("markets"), (res.get("players") or {}).get(p.get("game_id"))
                if not mk or not pl:
                    continue
                if p.get("pid") in pl:
                    act = dict(zip(cols, pl[p["pid"]]))
                elif (p.get("game_id"), norm_name(p.get("name"))) in PLAYED:
                    act = {c: 0.0 for c in cols}
                else:
                    continue
                for st in STATS.get(p.get("pos"), []):
                    m = mk.get(st)
                    bm = mains.get((p.get("game_id"), p.get("pid"), st))
                    if not m or bm is None or bm < C.ALT_MIN_MAIN[st]:
                        continue
                    main = float(np.floor(bm) + 0.5)
                    for k in range(1, int(C.ALT_MAX_DROP[st] // C.ALT_STEP[st]) + 1):
                        L = main - k * C.ALT_STEP[st]
                        if L < C.ALT_MIN_LINE[st]:
                            break
                        pc = adjust(cal, p["pos"], st, _p_over(m, L))
                        if C.ALT_LEG_RANGE[0] <= pc <= C.ALT_LEG_RANGE[1]:
                            rows.setdefault(group(p["pos"], st), []).append((wk, pc, float(act[st] > L)))
        for g, v in rows.items():
            v = np.asarray(v, float)
            weeks = {int(w): [int((v[:, 0] == w).sum()), round(100 * v[v[:, 0] == w, 1].mean(), 1), round(100 * v[v[:, 0] == w, 2].mean(), 1)]
                     for w in sorted(set(v[:, 0]))}
            out[g] = {"n": len(v), "model": round(100 * v[:, 1].mean(), 1), "actual": round(100 * v[:, 2].mean(), 1), "weeks": weeks}
    except Exception as e:  # noqa: BLE001
        log.warning(f"alt leg type table skipped: {e}")
    _TT[key] = out
    return out


def allowed(table, g):
    """A leg type is used unless its recent record clearly misses: enough lines and hitting more than
    ALT_TYPE_MAX_MISS points below the calibrated model."""
    t = table.get(g)
    if not t or t["n"] < C.ALT_TYPE_MIN_N:
        return True
    return t["actual"] >= t["model"] - C.ALT_TYPE_MAX_MISS
