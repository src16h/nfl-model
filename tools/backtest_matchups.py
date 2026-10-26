"""
Backtest for the FTN / NGS / PFR matchups (nflmodel/matchups.py).

Every regular-season team-game 2022-2025 from week 4, using only data from before that week:
  target    the offense's EPA per dropback (and per designed run) in that game, blowouts down-weighted
  baseline  offense's usual EPA + defense's usual EPA allowed (both pulled toward average)
  features  the raw matchups; coverage / pass rush use the defenders who actually played (snap counts)
A weighted regression on 2022-24 says how much of each matchup shows up; 2025 checks it out of sample.

python tools/backtest_matchups.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import nflreadpy as nfl  # noqa: E402
from nflmodel import data as D  # noqa: E402
from nflmodel import matchups as MU  # noqa: E402
from nflmodel.util import shrink  # noqa: E402

SEASONS = [2022, 2023, 2024, 2025]
CACHE = Path(__file__).resolve().parent.parent / "data" / "_mu_bt"


def raw():
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / "plays.parquet"
    if f.exists():
        return (pd.read_parquet(f), pd.read_parquet(CACHE / "pfr.parquet"), pd.read_parquet(CACHE / "ngs.parquet"),
                pd.read_parquet(CACHE / "snaps.parquet"))
    pbp = pd.concat([D.load_pbp_season(s) for s in [2021] + SEASONS], ignore_index=True)
    ftn = D._pd(nfl.load_ftn_charting(SEASONS))
    plays = MU.tag_plays(pbp, ftn)
    pfr = D._pd(nfl.load_pfr_advstats(seasons=[2021] + SEASONS, stat_type="def", summary_level="week"))
    ngs = D._pd(nfl.load_nextgen_stats(seasons=[2021] + SEASONS, stat_type="passing"))
    snaps = D._pd(nfl.load_snap_counts(SEASONS))
    snaps = snaps[(snaps["defense_snaps"] > 0)][["game_id", "team", "pfr_player_id"]]
    plays.to_parquet(f)
    pfr.to_parquet(CACHE / "pfr.parquet")
    ngs.to_parquet(CACHE / "ngs.parquet")
    snaps.to_parquet(CACHE / "snaps.parquet")
    return plays, pfr, ngs, snaps


def build():
    f = CACHE / "rows.parquet"
    if f.exists():
        return pd.read_parquet(f), pd.read_parquet(CACHE / "prow.parquet"), pd.read_parquet(CACHE / "drow.parquet")
    plays, pfr, ngs, snaps = raw()
    played = snaps.groupby(["game_id", "team"])["pfr_player_id"].apply(set).to_dict()
    gm = plays[plays["season"].isin(SEASONS)]
    # per team-game results
    g = gm.assign(we=gm["epa"] * gm["gw"]).groupby(["season", "week", "game_id", "posteam", "defteam", "db"]).agg(
        n=("gw", "sum"), e=("we", "sum")).reset_index()
    qbs = (gm[gm["db"] == 1].groupby(["game_id", "posteam", "passer_player_id"]).size()
           .reset_index().sort_values(0).groupby(["game_id", "posteam"])["passer_player_id"].last())
    rows, prows, drows = [], [], []
    for (s, w), grp in g.groupby(["season", "week"]):
        if w < 4:
            continue
        M = MU.Matchups(plays, s, w, pfr=pfr, ngs_pass=ngs)
        t = plays[((plays["season"] == s) & (plays["week"] < w)) | (plays["season"] == s - 1)]
        t = t.assign(ww=np.where(t["season"] == s, 1.0, 0.5) * t["gw"])
        base = {}
        for dbv in (1, 0):
            x = t[t["db"] == dbv]
            lg = np.average(x["epa"], weights=x["ww"])
            o = x.groupby("posteam").apply(lambda y: shrink((y["epa"] * y["ww"]).sum(), y["ww"].sum(), lg, 200))
            d = x.groupby("defteam").apply(lambda y: shrink((y["epa"] * y["ww"]).sum(), y["ww"].sum(), lg, 200))
            base[dbv] = (o, d, lg)
        for _, r in grp.iterrows():
            o, d, lg = base[r["db"]]
            b = float(o.get(r["posteam"], lg) + d.get(r["defteam"], lg) - lg)
            row = {"season": s, "week": w, "game_id": r["game_id"], "off": r["posteam"], "de": r["defteam"],
                   "db": r["db"], "n": r["n"], "y": r["e"] / max(r["n"], 1e-9), "base": b}
            if r["db"] == 1:
                qb = qbs.get((r["game_id"], r["posteam"]))
                row.update(M.pass_feats(r["posteam"], r["defteam"], qb, played.get((r["game_id"], r["defteam"]))))
            else:
                row.update(M.rush_feats(r["posteam"], r["defteam"]))
            rows.append(row)
        # play level: this week's charted plays with each side's split from before the week
        wk = gm[(gm["season"] == s) & (gm["week"] == w)].copy()
        wk["base"] = [float(base[dbv][0].get(o, base[dbv][2]) + base[dbv][1].get(d, base[dbv][2]) - base[dbv][2])
                      for dbv, o, d in zip(wk["db"], wk["posteam"], wk["defteam"])]
        qsp = wk["passer_player_id"].map(M.blitz_qb)
        wk["sp_blitz"] = qsp.fillna(wk["posteam"].map(M.blitz_team)).fillna(0.0)
        for k in ("play_action", "screen", "motion"):
            wk[f"sp_{k}"] = wk["defteam"].map(M.def_split[k]).fillna(0.0)
        wk["sp_box"] = wk["posteam"].map(M.box_split).fillna(0.0)
        wk["r_blitz"] = wk["defteam"].map(M.blitz_rate).fillna(M.lg_blitz)
        for k in ("play_action", "screen", "motion"):
            wk[f"r_{k}"] = wk["posteam"].map(M.off_rate[k]).fillna(M.lg_rate[k])
        wk["r_box"] = wk["defteam"].map(M.box_rate).fillna(M.lg_box)
        prows.append(wk)
        # defender level: this week's coverage and pressures vs each defender's record before the week
        dw = pfr[(pfr["season"] == s) & (pfr["week"] == w) & (pfr["game_type"] == "REG")].copy()
        if M.pfr_ok and len(dw):
            dw["prior_ypt"] = dw["pfr_player_id"].map(M.ypt)
            dw["prior_ppg"] = dw["pfr_player_id"].map(M.ppg)
            dw["lg_ypt"] = M.lg_ypt
            drows.append(dw[["season", "week", "pfr_player_id", "def_targets", "def_yards_allowed", "def_pressures",
                             "prior_ypt", "prior_ppg", "lg_ypt"]])
        print(f"{s} wk {w}", flush=True)
    out = pd.DataFrame(rows).fillna(0.0)
    pr = pd.concat(prows, ignore_index=True)
    dr = pd.concat(drows, ignore_index=True)
    out.to_parquet(f)
    pr.to_parquet(CACHE / "prow.parquet")
    dr.to_parquet(CACHE / "drow.parquet")
    return out, pr, dr


def wls(X, y, w):
    W = np.sqrt(w)
    beta, *_ = np.linalg.lstsq(X * W[:, None], y * W, rcond=None)
    res = y - X @ beta
    s2 = np.sum(w * res ** 2) / max(len(y) - X.shape[1], 1)
    cov = s2 * np.linalg.pinv((X * w[:, None]).T @ X)
    return beta, np.sqrt(np.diag(cov))


def report(df, feats, label):
    tr, te = df[df["season"] < 2025], df[df["season"] == 2025]
    print(f"\n=== {label}: {len(tr)} train team-games, {len(te)} test ===")
    print("raw size of each matchup (middle 80% of games):")
    for f in feats:
        lo, hi = np.percentile(tr[f], [10, 90])
        print(f"  {f:13s} {lo:+.4f} to {hi:+.4f}")
    # one at a time, then all together
    print("one at a time (coef, t, 2025 error change %):")
    single = {}
    for f in feats:
        X = np.column_stack([np.ones(len(tr)), tr[f]])
        b, se = wls(X, (tr["y"] - tr["base"]).to_numpy(), tr["n"].to_numpy())
        pred = te["base"] + b[0] + b[1] * te[f]
        e0 = np.average((te["y"] - te["base"] - b[0]) ** 2, weights=te["n"])
        e1 = np.average((te["y"] - pred) ** 2, weights=te["n"])
        single[f] = (b[1], b[1] / se[1], 100 * (e1 / e0 - 1))
        print(f"  {f:13s} coef {b[1]:+8.3f}  t {b[1] / se[1]:+5.2f}  2025 error {100 * (e1 / e0 - 1):+.3f}%")
    X = np.column_stack([np.ones(len(tr))] + [tr[f] for f in feats])
    b, se = wls(X, (tr["y"] - tr["base"]).to_numpy(), tr["n"].to_numpy())
    Xt = np.column_stack([np.ones(len(te))] + [te[f] for f in feats])
    e0 = np.average((te["y"] - te["base"] - b[0]) ** 2, weights=te["n"])
    e1 = np.average((te["y"] - te["base"] - Xt @ b) ** 2, weights=te["n"])
    print("all together:")
    for f, bb, ss in zip(feats, b[1:], se[1:]):
        print(f"  {f:13s} coef {bb:+8.3f}  t {bb / ss:+5.2f}")
    print(f"  2025 error change {100 * (e1 / e0 - 1):+.3f}%")
    return single, dict(zip(feats, b[1:])), dict(zip(feats, b[1:] / se[1:]))


def persistence(pr, dr):
    """Does each ingredient carry over from past games to the next one? coef 1 = fully, 0 = noise."""
    print("\n=== DO THE SPLITS CARRY OVER? (play level; coef ~1 = real, ~0 = noise) ===")
    out = {}
    tests = [("blitz", "QB vs blitz", 1), ("play_action", "defense vs play action", 1),
             ("screen", "defense vs screens", 1), ("motion", "defense vs motion", 1), ("box", "offense vs 8+ box", 0)]
    for k, label, dbv in tests:
        flag = "heavy_box" if k == "box" else k
        for part, m in (("train", pr["season"] < 2025), ("2025", pr["season"] == 2025)):
            x = pr[m & (pr["db"] == dbv) & pr[flag].notna()]
            X = np.column_stack([np.ones(len(x)), x[flag], x[flag] * x[f"sp_{k}"]])
            b, se = wls(X, (x["epa"] - x["base"]).to_numpy(), x["gw"].to_numpy())
            out[(k, part)] = (b[2], b[2] / se[2])
            print(f"  {label:24s} {part:5s} plays {len(x):6d}  carry-over {b[2]:+.2f}  (t {b[2] / se[2]:+.2f})")
    # rates: does a team's past rate predict this week's?
    print("rates carry over (coef ~1 = real):")
    for k, flag, key in [("blitz", "blitz", "defteam"), ("play_action", "play_action", "posteam"),
                         ("screen", "screen", "posteam"), ("motion", "motion", "posteam"), ("box", "heavy_box", "defteam")]:
        x = pr[pr[flag].notna()]
        g = x.groupby(["game_id", key]).agg(y=(flag, "mean"), r=(f"r_{k}", "first"), n=(flag, "size"))
        X = np.column_stack([np.ones(len(g)), g["r"]])
        b, se = wls(X, g["y"].to_numpy(), g["n"].to_numpy().astype(float))
        print(f"  {k:12s} {b[1]:+.2f} (t {b[1] / se[1]:+.1f})")
    x = dr[(dr["def_targets"] > 0) & dr["prior_ypt"].notna()]
    X = np.column_stack([np.ones(len(x)), x["prior_ypt"] - x["lg_ypt"]])
    b, se = wls(X, (x["def_yards_allowed"] / x["def_targets"] - x["lg_ypt"]).to_numpy(), x["def_targets"].to_numpy().astype(float))
    print(f"  defender yards per target allowed  {b[1]:+.2f} (t {b[1] / se[1]:+.1f}, {len(x)} defender-games)")
    out["coverage"] = b[1]
    x = dr[dr["prior_ppg"].notna()]
    X = np.column_stack([np.ones(len(x)), x["prior_ppg"]])
    b, se = wls(X, x["def_pressures"].to_numpy(float), np.ones(len(x)))
    print(f"  defender pressures per game        {b[1]:+.2f} (t {b[1] / se[1]:+.1f})")
    out["pass_rush"] = b[1]
    return out


def main():
    df, pr, dr = build()
    persistence(pr, dr)
    p = df[df["db"] == 1]
    r = df[df["db"] == 0]
    sp, cp, tp = report(p, list(MU.PASS_FEATS), "PASSING (EPA per dropback)")
    sr, cr, trr = report(r, list(MU.RUSH_FEATS), "RUNNING (EPA per designed run)")
    return sp, cp, tp, sr, cr, trr


if __name__ == "__main__":
    main()
