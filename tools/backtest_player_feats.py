"""
Player-level tests for the free charting data. Each asks: does the new stat predict NEXT week better
than what the model already uses? Tuned on 2022-24, checked on 2025, weeks 4+, prior data only.

  A. QB interceptions    INT rate (now)  vs  blended with FTN interception-worthy throw rate
  B. receiver catches    catch rate (now) vs  QB's catchable-ball rate x receiver's hands on catchable balls
  C. yards per target    yards per target (now) vs  plus NGS separation / YAC over expected / air yards
  D. defender coverage   does a defender's yards per target allowed carry over at all?

python tools/backtest_player_feats.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import nflreadpy as nfl  # noqa: E402
from nflmodel import config as C  # noqa: E402
from nflmodel import data as D  # noqa: E402
from nflmodel.util import shrink, pos_group  # noqa: E402

SEASONS = [2022, 2023, 2024, 2025]
CACHE = Path(__file__).resolve().parent.parent / "data" / "_mu_bt"


def load():
    f = CACHE / "pass_plays.parquet"
    if f.exists():
        return (pd.read_parquet(f), pd.read_parquet(CACHE / "ngs_rec.parquet"), pd.read_parquet(CACHE / "pos.parquet"),
                pd.read_parquet(CACHE / "pfr.parquet"))
    CACHE.mkdir(parents=True, exist_ok=True)
    pbp = pd.concat([D.load_pbp_season(s) for s in [2021] + SEASONS], ignore_index=True)
    p = pbp[(pbp["season_type"] == "REG") & (pbp["pass_attempt"] == 1) & (pbp["two_point_attempt"] != 1)
            & (pbp["sack"] != 1)][["season", "week", "game_id", "play_id", "posteam", "passer_player_id",
                                   "receiver_player_id", "complete_pass", "interception", "yards_gained", "wp"]].copy()
    ftn = D._pd(nfl.load_ftn_charting(SEASONS))
    ftn = ftn.rename(columns={"nflverse_game_id": "game_id", "nflverse_play_id": "play_id"})[
        ["game_id", "play_id", "is_interception_worthy", "is_catchable_ball", "is_drop", "is_throw_away"]]
    ftn["play_id"] = pd.to_numeric(ftn["play_id"], errors="coerce")
    p["play_id"] = pd.to_numeric(p["play_id"], errors="coerce")
    p = p.merge(ftn, on=["game_id", "play_id"], how="left")
    ngs = D._pd(nfl.load_nextgen_stats(seasons=[2021] + SEASONS, stat_type="receiving"))
    ros = D._pd(nfl.load_rosters([2021] + SEASONS))
    pos = ros.dropna(subset=["gsis_id"]).groupby("gsis_id")["position"].last().map(pos_group).rename("pos").reset_index()
    p.to_parquet(f)
    ngs.to_parquet(CACHE / "ngs_rec.parquet")
    pos.to_parquet(CACHE / "pos.parquet")
    return p, ngs, pos, pd.read_parquet(CACHE / "pfr.parquet")


def window(df, s, w, prior=0.6):
    m = ((df["season"] == s) & (df["week"] < w)) | (df["season"] == s - 1)
    x = df[m]
    return x.assign(ww=np.where(x["season"] == s, 1.0, prior))


def poisson_dev(k, mu):
    mu = np.maximum(mu, 1e-9)
    return 2 * np.sum(np.where(k > 0, k * np.log(np.maximum(k, 1e-9) / mu), 0) - (k - mu))


def binom_dev(c, n, p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return -2 * np.sum(c * np.log(p) + (n - c) * np.log(1 - p))


def main():
    p, ngs, pos, pfr = load()
    posmap = dict(zip(pos["gsis_id"], pos["pos"]))
    p["pos"] = p["receiver_player_id"].map(posmap)
    ngs = ngs[(ngs["week"] > 0) & (ngs["season_type"] == "REG")]
    pfr = pfr[pfr["game_type"] == "REG"].copy()
    for c in ["def_targets", "def_yards_allowed"]:
        pfr[c] = pd.to_numeric(pfr[c], errors="coerce").fillna(0.0)

    qa, rb_, yc, dc = [], [], [], []
    m_int, k_int = C.PRIORS["qb_int"]
    for s in SEASONS:
        for w in range(4, 19):
            cur = p[(p["season"] == s) & (p["week"] == w)]
            if not len(cur):
                continue
            t = window(p, s, w)
            # A. interceptions
            tq = t.assign(i=t["interception"] * t["ww"], n=t["ww"], iw=t["is_interception_worthy"].astype(float) * t["ww"],
                          nc=t["is_interception_worthy"].notna() * t["ww"])
            q = tq.groupby("passer_player_id")[["i", "n", "iw", "nc"]].sum()
            lg_iw = tq["iw"].sum() / max(tq["nc"].sum(), 1)
            g = cur.groupby(["game_id", "passer_player_id"]).agg(att=("interception", "size"), ints=("interception", "sum")).reset_index()
            g = g.join(q, on="passer_player_id")
            g["r_int"] = shrink(g["i"].fillna(0), g["n"].fillna(0), m_int, k_int)
            g["r_iw"] = shrink(g["iw"].fillna(0), g["nc"].fillna(0), lg_iw, 150) * (m_int / lg_iw)
            g["season"] = s
            qa.append(g[["season", "att", "ints", "r_int", "r_iw"]])
            # B / C. receivers
            tr = t[t["receiver_player_id"].notna()]
            tr = tr.assign(c=tr["complete_pass"] * tr["ww"], n=tr["ww"], y=tr["yards_gained"].fillna(0) * tr["complete_pass"] * tr["ww"],
                           cb=(tr["is_catchable_ball"] == True) * tr["ww"], nc=tr["is_catchable_ball"].notna() * tr["ww"],  # noqa: E712
                           cc=((tr["is_catchable_ball"] == True) & (tr["complete_pass"] == 1)) * tr["ww"])  # noqa: E712
            rr = tr.groupby("receiver_player_id")[["c", "n", "y", "cb", "nc", "cc"]].sum()
            qq = tr.groupby("passer_player_id")[["cb", "nc"]].sum()
            lg_cat = tr["cb"].sum() / max(tr["nc"].sum(), 1)
            lg_hands = tr["cc"].sum() / max(tr["cb"].sum(), 1)
            cr = cur[cur["receiver_player_id"].notna()]
            pg = cr.groupby(["game_id", "receiver_player_id", "pos"]).agg(
                tg=("complete_pass", "size"), rec=("complete_pass", "sum"),
                yds=("yards_gained", lambda v: float((v.fillna(0) * cr.loc[v.index, "complete_pass"]).sum())),
                qb=("passer_player_id", lambda v: v.mode().iat[0] if len(v.mode()) else None)).reset_index()
            pg = pg[pg["pos"].isin(["WR", "TE", "RB"])].join(rr, on="receiver_player_id")
            pg[["c", "n", "y", "cb", "nc", "cc"]] = pg[["c", "n", "y", "cb", "nc", "cc"]].fillna(0)
            prior_c = pg["pos"].map(lambda x: C.PRIORS["catch_rate"][x][0])
            prior_y = pg["pos"].map(lambda x: C.PRIORS["yds_per_target"][x][0])
            pg["p_now"] = shrink(pg["c"], pg["n"], prior_c, 40)
            pg["ypt_now"] = shrink(pg["y"], pg["n"], prior_y, 60)
            hands = shrink(pg["cc"], pg["cb"], lg_hands * prior_c / prior_c.mean(), 40)
            qcat = pg["qb"].map(lambda x: shrink(qq["cb"].get(x, 0), qq["nc"].get(x, 0), lg_cat, 150))
            pg["p_new"] = np.clip(qcat * hands, 0.05, 0.98)
            pg["season"] = s
            # NGS: target-weighted averages of each receiver's weekly rows before this week
            nw = window(ngs, s, w)
            nw = nw.assign(wt=nw["targets"] * nw["ww"])
            agg = nw.groupby("player_gsis_id").apply(lambda x: pd.Series({
                "sep": np.average(x["avg_separation"], weights=x["wt"]) if x["wt"].sum() > 0 else np.nan,
                "yacoe": np.average(x["avg_yac_above_expectation"].fillna(0), weights=x["wt"]) if x["wt"].sum() > 0 else np.nan,
                "iay": np.average(x["avg_intended_air_yards"], weights=x["wt"]) if x["wt"].sum() > 0 else np.nan,
                "ntg": x["wt"].sum()}))
            pg = pg.join(agg, on="receiver_player_id")
            rb_.append(pg[["season", "pos", "tg", "rec", "p_now", "p_new"]])
            yc.append(pg[["season", "pos", "tg", "yds", "ypt_now", "sep", "yacoe", "iay", "ntg"]])
            # D. defenders
            dw = pfr[(pfr["season"] == s) & (pfr["week"] == w) & (pfr["def_targets"] > 0)]
            pw = window(pfr, s, w)
            pl = pw.assign(t=pw["def_targets"] * pw["ww"], y=pw["def_yards_allowed"] * pw["ww"]).groupby("pfr_player_id")[["t", "y"]].sum()
            lg = pl["y"].sum() / max(pl["t"].sum(), 1)
            dd = dw.join(pl, on="pfr_player_id").dropna(subset=["t"])
            dd = dd.assign(prior=shrink(dd["y"], dd["t"], lg, 50), lg=lg, season=s)
            dc.append(dd[["season", "def_targets", "def_yards_allowed", "prior", "lg", "t"]])
        print("built", s, flush=True)

    qa, rb_, yc, dc = (pd.concat(x, ignore_index=True) for x in (qa, rb_, yc, dc))
    tr, te = (lambda d: d[d["season"] < 2025]), (lambda d: d[d["season"] == 2025])

    print("\nA. QB INTERCEPTIONS (Poisson deviance change vs INT rate only; negative = better)")
    best = (0, 0)
    for lam in [0.0, 0.25, 0.5, 0.75, 1.0]:
        res = []
        for d in (tr(qa), te(qa)):
            mu0 = d["att"] * d["r_int"]
            mu = d["att"] * ((1 - lam) * d["r_int"] + lam * d["r_iw"])
            res.append(100 * (poisson_dev(d["ints"], mu) / poisson_dev(d["ints"], mu0) - 1))
        print(f"  blend {lam:.2f}: train {res[0]:+.3f}%  2025 {res[1]:+.3f}%")
        if res[0] < best[1]:
            best = (lam, res[0])
    print("  best blend", best[0])

    print("\nB. CATCHES (binomial deviance change vs catch rate only)")
    for lam in [0.0, 0.25, 0.5, 0.75, 1.0]:
        res = []
        for d in (tr(rb_), te(rb_)):
            p0 = d["p_now"]
            p1 = (1 - lam) * d["p_now"] + lam * d["p_new"]
            res.append(100 * (binom_dev(d["rec"], d["tg"], p1) / binom_dev(d["rec"], d["tg"], p0) - 1))
        print(f"  blend {lam:.2f}: train {res[0]:+.3f}%  2025 {res[1]:+.3f}%")

    print("\nC. YARDS PER TARGET with NGS (receivers with 15+ prior NGS targets)")
    d = yc[(yc["ntg"] >= 15) & (yc["tg"] > 0)].dropna(subset=["sep", "yacoe", "iay"])
    a, b = tr(d), te(d)
    def fit(cols, A):
        X = np.column_stack([np.ones(len(A))] + [A[c] for c in cols])
        W = np.sqrt(A["tg"].to_numpy(float))
        beta, *_ = np.linalg.lstsq(X * W[:, None], (A["yds"] / A["tg"]).to_numpy() * W, rcond=None)
        return beta
    for cols in (["ypt_now"], ["ypt_now", "sep"], ["ypt_now", "yacoe"], ["ypt_now", "iay"], ["ypt_now", "sep", "yacoe", "iay"]):
        beta = fit(cols, a)
        Xb = np.column_stack([np.ones(len(b))] + [b[c] for c in cols])
        e = np.average((b["yds"] / b["tg"] - Xb @ beta) ** 2, weights=b["tg"])
        if cols == ["ypt_now"]:
            e0 = e
        print(f"  {'+'.join(cols):28s} 2025 error {100 * (e / e0 - 1):+.3f}%  coefs {np.round(beta[1:], 3).tolist()}")
    print(f"  ({len(a)} train / {len(b)} test player-games)")

    print("\nD. DEFENDER COVERAGE: does yards per target allowed carry over?")
    for lab, d in (("train", tr(dc)), ("2025", te(dc))):
        X = np.column_stack([np.ones(len(d)), d["prior"] - d["lg"]])
        W = np.sqrt(d["def_targets"].to_numpy(float))
        y = (d["def_yards_allowed"] / d["def_targets"] - d["lg"]).to_numpy()
        beta, *_ = np.linalg.lstsq(X * W[:, None], y * W, rcond=None)
        print(f"  {lab}: carry-over {beta[1]:+.2f}  ({len(d)} defender-games)")


if __name__ == "__main__":
    main()
