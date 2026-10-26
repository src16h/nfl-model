"""
Backtest for defense vs position (nflmodel/dvp.py).

For every regular-season game 2022-2025 (weeks 4+), using only plays from before that week:
  base : each player's targets = the team's ACTUAL targets that game x his usual share
         his yards               = those targets x his usual yards per target, scaled to the team's actual yards
  dvp  : the same, then targets and yards shifted between WR / TE / RB by the defense's factors
Using the team's actual totals isolates the one thing dvp changes: who gets the ball.
Score: squared error on targets and receiving yards (lower is better), per position and overall.

python tools/backtest_dvp.py            # grid search on 2022-24, check the winner on 2025
"""
import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import nflreadpy as nfl  # noqa: E402
from nflmodel import config as C  # noqa: E402
from nflmodel import data as D  # noqa: E402
from nflmodel import usage as U  # noqa: E402
from nflmodel import dvp as DV  # noqa: E402
from nflmodel.util import shrink  # noqa: E402

SEASONS = [2022, 2023, 2024, 2025]
CACHE = Path(__file__).resolve().parent.parent / "data" / "_dvp_bt"


def load():
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / "base.parquet"
    if f.exists():
        return pd.read_parquet(f), pd.read_parquet(CACHE / "tt.parquet")
    pbp = pd.concat([D.load_pbp_season(s) for s in [SEASONS[0] - 1] + SEASONS], ignore_index=True)
    ros = D._pd(nfl.load_rosters([SEASONS[0] - 1] + SEASONS))
    posmap = DV.pos_map(ros)
    snaps = D._pd(nfl.load_snap_counts(SEASONS))
    pfr = ros.dropna(subset=["pfr_id", "gsis_id"]).drop_duplicates("pfr_id").set_index("pfr_id")["gsis_id"]
    snaps["pid"] = snaps["pfr_player_id"].map(pfr)
    snaps = snaps[(snaps["game_type"] == "REG") & (snaps["offense_snaps"] > 0) & snaps["pid"].notna()]
    played = snaps[["game_id", "team", "pid"]].drop_duplicates()

    reg = pbp[(pbp["season_type"] == "REG") & (pbp["pass_attempt"] == 1) & pbp["receiver_player_id"].notna()
              & (pbp["two_point_attempt"] != 1)].copy()
    reg["yds"] = np.where(reg["complete_pass"] == 1, reg["yards_gained"].fillna(0), 0.0)
    act = reg.groupby(["game_id", "posteam", "receiver_player_id"]).agg(tgt=("yds", "size"), yds=("yds", "sum"))
    act = act.reset_index().rename(columns={"posteam": "team", "receiver_player_id": "pid"})
    games = reg.groupby(["season", "week", "game_id", "posteam"])["defteam"].first().reset_index()

    rows = []
    for s in SEASONS:
        for w in sorted(games.loc[games["season"] == s, "week"].unique()):
            if w < 4:
                continue
            u = U.build(pbp, s, w)
            use, eff = u["usage"], u["eff"]
            gw = games[(games["season"] == s) & (games["week"] == w)]
            for _, g in gw.iterrows():
                tm, opp, gid = g["posteam"], g["defteam"], g["game_id"]
                on = played[(played["game_id"] == gid) & (played["team"] == tm)]["pid"]
                x = use[(use["team"] == tm) & use["pid"].isin(on)][["pid", "tgt_share"]].copy()
                x["pos"] = x["pid"].map(posmap)
                x = x[x["pos"].isin(DV.GROUPS)]
                if not len(x) or x["tgt_share"].sum() <= 0:
                    continue
                x["tgt_share"] /= x["tgt_share"].sum()
                ypt = []
                for pid, pos in zip(x["pid"], x["pos"]):
                    ym, yk = C.PRIORS["yds_per_target"].get(pos, C.PRIORS["yds_per_target"]["WR"])
                    e = eff.loc[pid] if pid in eff.index else None
                    ypt.append(float(shrink(e["rec_yds"], e["rec_n"], ym, yk)) if e is not None else ym)
                x["ypt"] = ypt
                x["season"], x["week"], x["game_id"], x["team"], x["opp"] = s, w, gid, tm, opp
                rows.append(x)
        print(f"baseline built: {s}", flush=True)
    base = pd.concat(rows, ignore_index=True)
    base = base.merge(act, on=["game_id", "team", "pid"], how="left").fillna({"tgt": 0, "yds": 0})
    # team actual totals over players we model (receivers outside WR/TE/RB, like QBs, are rare)
    tt = act.merge(base[["game_id", "team", "pid"]], on=["game_id", "team", "pid"])
    tt = tt.groupby(["game_id", "team"])[["tgt", "yds"]].sum().rename(columns={"tgt": "T", "yds": "Y"}).reset_index()
    tab = DV.targets_table(pbp, posmap)
    base.to_parquet(f)
    tt.to_parquet(CACHE / "tt.parquet")
    tab.to_parquet(CACHE / "tab.parquet")
    return base, tt


def project(base, tt, ft=None, fp=None):
    b = base.merge(tt, on=["game_id", "team"])
    ft = np.ones(len(b)) if ft is None else ft
    fp = np.ones(len(b)) if fp is None else fp
    key = [b["game_id"], b["team"]]
    w = b["tgt_share"].to_numpy() * ft
    w = w / pd.Series(w).groupby(key).transform("sum").to_numpy()
    tg = b["T"].to_numpy() * w
    y = tg * b["ypt"].to_numpy() * fp
    y = y * b["Y"].to_numpy() / np.maximum(pd.Series(y).groupby(key).transform("sum").to_numpy(), 1e-9)
    return tg, y


def factors(base, tab, prior_w, k_tgt, k_yds, strength, cap):
    ft = np.ones(len(base))
    fp = np.ones(len(base))
    for (s, w), idx in base.groupby(["season", "week"]).groups.items():
        d = DV.DvP(tab, s, w, prior_w=prior_w, k_tgt=k_tgt, k_yds=k_yds, strength=strength, cap=cap, strength_ypt=strength)
        sub = base.loc[idx]
        f = np.array([d.factors(o, p) for o, p in zip(sub["opp"], sub["pos"])])
        ft[base.index.get_indexer(idx)] = f[:, 0]
        fp[base.index.get_indexer(idx)] = f[:, 1]
    return ft, fp


def score(base, tg, y, mask=None):
    m = np.ones(len(base), bool) if mask is None else mask
    return (float(np.mean((base["tgt"].to_numpy()[m] - tg[m]) ** 2)),
            float(np.mean((base["yds"].to_numpy()[m] - y[m]) ** 2)))


def main():
    base, tt = load()
    tab = pd.read_parquet(CACHE / "tab.parquet")
    base = base.reset_index(drop=True)
    train = base["season"] < 2025
    tg0, y0 = project(base, tt)
    b_tr = score(base, tg0, y0, train.to_numpy())
    b_te = score(base, tg0, y0, (~train).to_numpy())
    print(f"\nplayer-games: {len(base)} (train {train.sum()}, test {(~train).sum()})")
    print(f"base  train: targets MSE {b_tr[0]:.4f}  yards MSE {b_tr[1]:.2f} | test {b_te[0]:.4f} {b_te[1]:.2f}")

    results = []
    for pw, k in itertools.product([0.3, 0.6, 0.8, 1.0], [20, 40, 80, 160]):
        ft, fp = factors(base, tab, pw, k, k * 10, 1.0, 1.5)
        for st, sy in itertools.product([0.25, 0.5, 0.75, 1.0], [0.0, 0.25, 0.5]):
            tg, y = project(base, tt, ft ** st, fp ** sy)
            r = score(base, tg, y, train.to_numpy())
            results.append({"prior_w": pw, "k": k, "strength": st, "strength_ypt": sy,
                            "tgt_gain%": 100 * (1 - r[0] / b_tr[0]), "yds_gain%": 100 * (1 - r[1] / b_tr[1])})
    res = pd.DataFrame(results)
    res["score"] = res["tgt_gain%"] + res["yds_gain%"]
    print("\ntop settings on 2022-24 (gain = % lower squared error than base):")
    print(res.sort_values("score", ascending=False).head(8).round(3).to_string(index=False))
    best = res.sort_values("score", ascending=False).iloc[0]

    ft, fp = factors(base, tab, best["prior_w"], best["k"], best["k"] * 10, 1.0, 1.5)
    tg, y = project(base, tt, ft ** best["strength"], fp ** best["strength_ypt"])
    print("\nholdout 2025 with the winner:")
    for pos in [None] + list(DV.GROUPS):
        m = (~train).to_numpy() & (np.ones(len(base), bool) if pos is None else (base["pos"] == pos).to_numpy())
        b = score(base, tg0, y0, m)
        r = score(base, tg, y, m)
        print(f"  {pos or 'ALL':3s} n={m.sum():5d}  targets {100 * (1 - r[0] / b[0]):+.2f}%   yards {100 * (1 - r[1] / b[1]):+.2f}%")
    # does the direction hold? players the matchup boosted most vs cut most
    m = (~train).to_numpy()
    lift = np.log(np.maximum(tg, 1e-6) / np.maximum(tg0, 1e-6))
    df = pd.DataFrame({"lift": lift[m], "act": base["tgt"].to_numpy()[m], "b": tg0[m],
                       "ya": base["yds"].to_numpy()[m], "yb": y0[m], "yl": np.log(np.maximum(y, 1e-6) / np.maximum(y0, 1e-6))[m]})
    df["grp"] = pd.qcut(df["lift"], 5, labels=["biggest cut", "cut", "neutral", "boost", "biggest boost"])
    out = df.groupby("grp", observed=True).agg(n=("act", "size"), model_shift=("lift", lambda v: 100 * (np.exp(v.mean()) - 1)),
                                               actual_vs_base_tgt=("act", "sum"), base_tgt=("b", "sum"),
                                               actual_yds=("ya", "sum"), base_yds=("yb", "sum"))
    out["targets_vs_base%"] = 100 * (out["actual_vs_base_tgt"] / out["base_tgt"] - 1)
    out["yards_vs_base%"] = 100 * (out["actual_yds"] / out["base_yds"] - 1)
    print("\n2025 by matchup group (did players the model boosted really beat their usual numbers?):")
    print(out[["n", "model_shift", "targets_vs_base%", "yards_vs_base%"]].round(1).to_string())
    print("\nBEST", best.to_dict())


if __name__ == "__main__":
    main()
