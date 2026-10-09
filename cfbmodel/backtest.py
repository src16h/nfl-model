"""
Walk-forward check against the betting market, rebuilt on every run and shown on the Record tab.

For each past season the points model is fit only on earlier seasons, and the ratings going into each
game only use games played before it. Then the model's number is compared with the closing line (and
the opening line where ESPN kept it) for games with a Power 4 team.
"""
import numpy as np
import pandas as pd

from . import config as C
from . import gamemodel as G


def walk(F, games, first=2021):
    out = []
    lines = games[["game_id", "hs", "as", "spread", "total", "open_spread", "open_total"]]
    for S in sorted(F["season"].unique()):
        if S < first:
            continue
        tr = F[(F["season"] < S) & (F["season"] >= C.FIRST_SEASON + 1)]
        te = F[F["season"] == S]
        if len(tr) < 500 or te.empty:
            continue
        m = G.Model()
        m._fit_one(tr, "pts", G.FEATS["pts"])
        te = m.script(te)
        out.append(te[te["home"] == 1].merge(lines, on="game_id"))
    H = pd.concat(out)
    H["m"], H["tt"] = H["hs"] - H["as"], H["hs"] + H["as"]
    return H[H["hs"].notna()]


def _rec(pick, res):
    ok = (res != 0) & (pick != 0)
    w = int(((np.sign(pick) == np.sign(res)) & ok).sum())
    l = int(((np.sign(pick) != np.sign(res)) & ok).sum())
    return {"w": w, "l": l, "pct": round(100 * w / (w + l), 1) if w + l else None}


def summary(H, p4_ids, season_now):
    """Numbers for the site. H from walk(); only games with a Power 4 team and a posted line, finished seasons only."""
    x = H[(H["team_id"].isin(p4_ids) | H["opp_id"].isin(p4_ids)) & H["spread"].notna() & H["total"].notna()]
    x = x[x["season"] < season_now]
    if x.empty:
        return None
    dm, rm = x["em"] + x["spread"], x["m"] + x["spread"]            # model minus market, result minus market
    dt, rt = (x["et"] - x["total"]) - (x["et"] - x["total"]).mean(), x["tt"] - x["total"]
    late = x["key"] > 4
    buckets = []
    for lo, hi in ((0, 3), (3, 6), (6, 9), (9, 99)):
        ms, ts = (dm.abs() >= lo) & (dm.abs() < hi), (dt.abs() >= lo) & (dt.abs() < hi)
        buckets.append({"lo": lo, "hi": hi, "spread": _rec(dm[ms], rm[ms]), "total": _rec(dt[ts], rt[ts])})
    o = x[x["open_spread"].notna()]
    dmo, rmo = o["em"] + o["open_spread"], o["m"] + o["open_spread"]
    move = o["open_spread"] - o["spread"]                             # + = line moved toward the home team
    big = dmo.abs() >= 3
    toward = (np.sign(dmo[big]) == np.sign(move[big])) & (move[big] != 0)
    away = (np.sign(dmo[big]) != np.sign(move[big])) & (move[big] != 0)
    return {"seasons": f"{int(x['season'].min())} to {int(x['season'].max())}", "n": int(len(x)),
            "mae_model": round(float((x["m"] - x["em"]).abs().mean()), 2), "mae_line": round(float(rm.abs().mean()), 2),
            "mae_model_late": round(float((x["m"] - x["em"])[late].abs().mean()), 2), "mae_line_late": round(float(rm[late].abs().mean()), 2),
            "tot_model": round(float((x["tt"] - x["et"] + (x["et"] - x["total"]).mean()).abs().mean()), 2), "tot_line": round(float(rt.abs().mean()), 2),
            "spread_all": _rec(dm, rm), "total_all": _rec(dt, rt), "buckets": buckets,
            "open": {"n": int(len(o)), "spread": _rec(dmo[big], rmo[big]),
                     "moved_toward": int(toward.sum()), "moved_away": int(away.sum()),
                     "pct_toward": round(100 * toward.sum() / max(toward.sum() + away.sum(), 1), 1)}}


def teaser_history(games, pts=6, since=2021):
    """How every teased side and total did at the closing line."""
    g = games[(games["season"] >= since) & games["spread"].notna() & games["total"].notna() & games["hs"].notna()]
    m, t = g["hs"] - g["as"], g["hs"] + g["as"]
    side = np.concatenate([(m + g["spread"] + pts > 0), (-m - g["spread"] + pts > 0)])
    tot = np.concatenate([(t > g["total"] - pts), (t < g["total"] + pts)])
    return {"since": since, "sides": {"n": int(len(side)), "w": int(side.sum()), "pct": round(100 * float(side.mean()), 1)},
            "totals": {"n": int(len(tot)), "w": int(tot.sum()), "pct": round(100 * float(tot.mean()), 1)}}
