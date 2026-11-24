"""
NFL alt legs, walk-forward (Nov 24 2026): QB passing / RB rushing / WR+TE receiving Over alt-down lines, anchor 0.5 vs 0.75 vs 1.0 and a
blowout/early-exit tail. Calibration refit on earlier weeks only (same form as altcal.fit). 

    python tools/alt_anchor_check.py

Nov 24 2026, weeks 6-11: QB passing log loss 0.6501 (anchor 0.5) -> 0.6400 (0.75, better in 6 of 6 weeks) -> 0.6336 (1.0);
RB rushing 0.6620 -> 0.6446 (0.75, 5 of 6) -> 0.6800 (1.0); WR / TE receiving no gain from more anchor.
"""
import json, sys, glob, math
sys.path.insert(0, ".")
import numpy as np
from scipy.optimize import minimize
from nflmodel import altcal, config as C
from nflmodel.tracker import _p_over

res = json.load(open("docs/data/results.json")); cols = res["cols"]
mains = {}
for v in json.load(open("docs/data/props_log.json"))["props"].values():
    if v.get("line") not in (None, ""):
        mains[(v["game_id"], v["pid"], v["stat"])] = float(v["line"])
POS = {"QB": "pass_yds", "RB": "rush_yds", "WR": "rec_yds", "TE": "rec_yds"}
lg = lambda p: np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6)))

pgames = []   # (week, pos, stat, m, act, bm)
for f in sorted(glob.glob("docs/data/history/2026_week*.json")):
    d = json.load(open(f)); wk = int(d["week"])
    for p in d["players"]:
        st = POS.get(p.get("pos"))
        m = (p.get("markets") or {}).get(st) if st else None
        pl = res["players"].get(p["game_id"])
        if not m or not pl or p["pid"] not in pl:
            continue
        act = dict(zip(cols, pl[p["pid"]]))
        pgames.append((wk, p["pos"], st, m, act[st], mains.get((p["game_id"], p["pid"], st))))


def fit(weeks_before):
    out = {}
    for pos in POS:
        st = POS[pos]
        xs, ys = [], []
        for wk, ps, s, m, a, bm in pgames:
            if wk >= weeks_before or ps != pos or (m.get("med") or 0) < C.ALT_MIN_MAIN[st] or "q" not in m:
                continue
            q = np.asarray(m["q"], float); lv = 1 - np.arange(1, len(q) + 1) / (len(q) + 1)
            for i in range(len(q)):
                if 0.55 <= lv[i] <= 0.97:
                    xs.append(lv[i]); ys.append(a > q[i])
        if len(xs) < 50:
            continue
        x, y = lg(np.array(xs)), np.array(ys, float)
        nll = lambda w: -np.mean(y * np.log(np.clip(1 / (1 + np.exp(-(w[0] + w[1] * x))), 1e-6, 1 - 1e-6)) + (1 - y) * np.log(np.clip(1 - 1 / (1 + np.exp(-(w[0] + w[1] * x))), 1e-6, 1 - 1e-6))) + 0.002 * (w[0] ** 2 + (w[1] - 1) ** 2)
        a_, b_ = minimize(nll, [0.0, 1.0]).x
        npg = len({id(m) for wk, ps, s, m, a, bm in pgames if wk < weeks_before and ps == pos})
        out[pos] = (a_, b_, npg / (npg + C.ALT_CAL_K))
    return out


def adj(cal, pos, p):
    c = cal.get(pos)
    if not c:
        return p
    a, b, w = c
    x = float(lg(p))
    return float(1 / (1 + np.exp(-((1 - w) * x + w * (a + b * x)))))


VARIANTS = {"anchor 0.5 (now)": (0.5, 0.0), "anchor 0.75": (0.75, 0.0), "anchor 1.0": (1.0, 0.0),
            "anchor 0.5 + tail 6%": (0.5, 0.06), "anchor 0.75 + tail 6%": (0.75, 0.06), "anchor 1.0 + tail 6%": (1.0, 0.06)}
weeks = sorted({g[0] for g in pgames if g[5] is not None})
out = {k: {p: [] for p in ("QB", "RB", "WR", "TE")} for k in VARIANTS}
for wk in weeks:
    if wk < 6:
        continue
    cal = fit(wk)
    for w_, pos, st, m, a, bm in pgames:
        if w_ != wk or bm is None or bm < C.ALT_MIN_MAIN[st]:
            continue
        med = float(m.get("med") or bm)
        for L in altcal.ladder(st, bm, "Over", posted=False):
            for k, (anc, tail) in VARIANTS.items():
                po = _p_over(m, L - anc * (bm - med))
                po = po * (1 - tail)                     # tail: a share of games end early / in a blowout and miss
                pc = adj(cal, pos, po)
                out[k][pos].append((wk, pc, float(a > L), C.ALT_LEG_RANGE[0] <= pc <= C.ALT_LEG_RANGE[1]))

print("Every alt-down step (5/10 yds) below Hard Rock's main, weeks 6-11, calibration fit on earlier weeks only")
for pos in ("QB", "RB", "WR", "TE"):
    print(f"== {pos}")
    for k in VARIANTS:
        v = np.array(out[k][pos])
        if not len(v):
            continue
        ll = -np.mean(v[:, 2] * np.log(np.clip(v[:, 1], 1e-6, 1)) + (1 - v[:, 2]) * np.log(np.clip(1 - v[:, 1], 1e-6, 1)))
        e = v[v[:, 3] == 1]
        e10 = e[e[:, 0] >= 10]
        wins = sum(1 for wk in sorted(set(v[:, 0])) if True)
        print(f"  {k:24s} all steps n={len(v)} logloss {ll:.4f} | eligible (70-92%) n={len(e)} said {100*e[:,1].mean():.1f} hit {100*e[:,2].mean():.1f}"
              f" | wk10-11 n={len(e10)} said {100*e10[:,1].mean() if len(e10) else 0:.1f} hit {100*e10[:,2].mean() if len(e10) else 0:.1f}")
    # by-week log loss: now vs anchor 1.0 + tail
    for k in ("anchor 0.75", "anchor 1.0", "anchor 0.75 + tail 6%", "anchor 1.0 + tail 6%"):
        b_ = np.array(out["anchor 0.5 (now)"][pos]); c_ = np.array(out[k][pos])
        better = 0; tot = 0
        for wk in sorted(set(b_[:, 0])):
            bb = b_[b_[:, 0] == wk]; cc = c_[c_[:, 0] == wk]
            lb = -np.mean(bb[:, 2] * np.log(bb[:, 1]) + (1 - bb[:, 2]) * np.log(1 - bb[:, 1]))
            lc = -np.mean(cc[:, 2] * np.log(cc[:, 1]) + (1 - cc[:, 2]) * np.log(1 - cc[:, 1]))
            better += lc < lb; tot += 1
        print(f"     {k}: better than now in {better} of {tot} weeks")
