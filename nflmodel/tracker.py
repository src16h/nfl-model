"""
The model's memory.

LINES  Every run saves the Vegas line next to our numbers. After a game
       finishes we compare the FIRST line we saw to the FINAL line in the data.
       If lines keep moving toward our side, the model sees something the
       market later agrees with (closing line value). That test needs far
       fewer games than win rate.

PROPS  Every prop you enter in data/props.csv is saved with the model's odds,
       then graded from play-by-play once the game is final. Results are kept
       forever, so you can delete old lines from props.csv without losing your record.

Both logs live in docs/data so the weekly robot saves them automatically.
Nothing here can break the main run: failures are logged and skipped.
"""
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from .util import clean_json, fnum, record_stats
from .propsim import prop_tier, stat_label

log = logging.getLogger("nflmodel")
MAX_SNAPS = 16
MIN_MOVE_SHARE = 0.05   # if fewer games than this ever move, the feed is probably static


def _load(path, default):
    path = Path(path)
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception as e:  # noqa: BLE001
        backup = path.with_suffix(".corrupt.json")
        try:
            backup.write_text(path.read_text())
        except Exception:  # noqa: BLE001
            pass
        log.warning(f"{path.name} could not be read ({str(e)[:60]}). Saved a copy as {backup.name} and starting fresh.")
        return default


def _save(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(clean_json(obj), indent=1, allow_nan=False))


# ---------------------------------------------------------------------
# LINES
# ---------------------------------------------------------------------
def update_line_log(path, games, now):
    """Save this run's line and our numbers for each upcoming game."""
    lg = _load(path, {"games": {}})
    lg.setdefault("games", {})
    ts = now.isoformat(timespec="minutes")
    for g in games:
        sp, to = g.get("market_spread"), g.get("market_total")
        if sp is None and to is None:
            continue
        rec = lg["games"].setdefault(g["game_id"], {
            "game_id": g["game_id"], "season": int(str(g["game_id"])[:4]), "week": g["week"],
            "away": g["away"], "home": g["home"], "kickoff": g.get("kickoff"),
            "snaps": [], "final": None})
        if rec.get("final"):
            continue
        anchored = g.get("lean_engine") == "anchored"
        snap = {"ts": ts, "src": g.get("line_src") or "feed", "spread": sp, "total": to,
                "m": g.get("margin"), "t": g.get("total"),
                "edge_s": g.get("edge_spread"), "edge_t": g.get("edge_total"),
                "engine": g.get("lean_engine"),
                "th_s": C.ANCHOR_LEAN_SPREAD if anchored else C.LEAN_SPREAD_EDGE,
                "th_t": C.ANCHOR_LEAN_TOTAL if anchored else C.LEAN_TOTAL_EDGE}
        rec["last_seen"] = ts
        last = rec["snaps"][-1] if rec["snaps"] else None
        if last and all(last.get(k) == snap[k] for k in ("src", "spread", "total", "m", "t")):
            continue
        snaps = rec["snaps"] + [snap]
        if len(snaps) > MAX_SNAPS:          # always keep the very first one
            snaps = [snaps[0]] + snaps[-(MAX_SNAPS - 1):]
        rec["snaps"] = snaps
    _save(path, lg)


def grade_lines(path, schedules):
    """Attach final lines to finished games, then summarize line movement."""
    lg = _load(path, {"games": {}})
    lg.setdefault("games", {})
    sch = schedules.drop_duplicates("game_id").set_index("game_id")
    changed = False
    for gid, rec in lg["games"].items():
        if rec.get("final") or gid not in sch.index:
            continue
        r = sch.loc[gid]
        if pd.notna(r["home_score"]) and pd.notna(r["away_score"]):
            rec["final"] = {
                "spread": fnum(pd.to_numeric(r.get("spread_line"), errors="coerce"), 2),
                "total": fnum(pd.to_numeric(r.get("total_line"), errors="coerce"), 2),
                "margin": float(r["home_score"] - r["away_score"]),
                "points": float(r["home_score"] + r["away_score"])}
            changed = True
    if changed:
        _save(path, lg)
    return line_summary(lg)


def line_summary(lg):
    out = {"tracked": len(lg.get("games", {}))}
    for kind, lk, ek, tk in (("spread", "spread", "edge_s", "th_s"), ("total", "total", "edge_t", "th_t")):
        items = []
        for rec in lg.get("games", {}).values():
            fin = rec.get("final")
            if not fin or not rec.get("snaps"):
                continue
            snaps = rec["snaps"]
            ref = snaps[-1].get("src", "feed")                  # the source we last saw before kickoff
            same = [x for x in snaps if x.get("src", "feed") == ref and x.get(lk) is not None]
            if not same:
                continue
            first = same[0]
            a, gap = first.get(lk), first.get(ek)
            # live lines: our last saved live line is the closing proxy. Free feed: its final line.
            b = same[-1].get(lk) if ref.startswith("live") else fin.get(lk)
            if a is None or b is None:
                continue
            clv = float(np.sign(gap) * (b - a)) if gap else 0.0
            items.append({"moved": bool(b != a), "gap": gap, "clv": clv, "th": first.get(tk) or 99})
        n = len(items)
        moved = sum(i["moved"] for i in items)
        blk = {"n": n, "moved": moved, "pct_moved": fnum(100 * moved / n, 0) if n else None,
               "measurable": bool(n >= 10 and moved / n >= MIN_MOVE_SHARE)}
        gapped = [i for i in items if i["gap"] is not None and abs(i["gap"]) >= 0.5]
        flagged = [i for i in items if i["gap"] is not None and abs(i["gap"]) >= i["th"]]
        for name, grp in (("all", gapped), ("flag", flagged)):
            mv = [i for i in grp if i["clv"] != 0]
            blk[name] = {"n": len(grp),
                         "avg": fnum(np.mean([i["clv"] for i in grp]), 2) if grp else None,
                         "toward": sum(1 for i in mv if i["clv"] > 0),
                         "away": sum(1 for i in mv if i["clv"] < 0)}
        out[kind] = blk
    out["graded"] = out["spread"]["n"]
    return out


def _open_close(rec, lk):
    """Opening line (first snapshot) and closing line (last one before kickoff, same source)."""
    snaps = rec.get("snaps") or []
    if not snaps:
        return None, None, None
    ref = snaps[-1].get("src", "feed")
    same = [x for x in snaps if x.get("src", "feed") == ref and x.get(lk) is not None]
    if not same:
        return None, None, None
    fin = rec.get("final") or {}
    close = same[-1].get(lk) if ref.startswith("live") else (fin.get(lk) if fin.get(lk) is not None else same[-1].get(lk))
    return same[0].get(lk), close, same[0]


def clv_report(path, play_spread=None):
    """Closing line value for every model pick, plus each game's open/close lines
    so the dashboard can score your own bets against the close."""
    lg = _load(path, {"games": {}})
    games, rows = {}, {"spread": [], "total": []}
    for gid, rec in lg.get("games", {}).items():
        g = {}
        for kind, lk, ek in (("spread", "spread", "edge_s"), ("total", "total", "edge_t")):
            a, b, first = _open_close(rec, lk)
            if a is None:
                continue
            g[f"open_{kind}"], g[f"close_{kind}"] = a, b
            gap = first.get(ek)
            if rec.get("final") and gap is not None and b is not None:
                side = 1.0 if gap >= 0 else -1.0                  # home / over
                clv = float(side * (b - a))
                g[f"clv_{kind}"] = fnum(clv, 2)
                rows[kind].append({"clv": clv, "gap": abs(gap), "week": rec.get("week")})
        if g:
            g["home"], g["away"] = rec.get("home"), rec.get("away")
            games[gid] = g

    def summ(items):
        if not items:
            return {"n": 0}
        c = np.array([i["clv"] for i in items])
        return {"n": len(items), "avg": fnum(c.mean(), 2), "beat": int((c > 0).sum()),
                "worse": int((c < 0).sum()), "same": int((c == 0).sum()),
                "beat_pct": fnum(100 * (c > 0).sum() / max((c != 0).sum(), 1), 0)}
    out = {"games": games}
    for kind in ("spread", "total"):
        it = rows[kind]
        out[kind] = {"all": summ(it),
                     "small": summ([i for i in it if i["gap"] < 1]),
                     "big": summ([i for i in it if i["gap"] >= 1]),
                     "plays": summ([i for i in it if play_spread is not None and kind == "spread" and i["gap"] >= play_spread])}
    return out


def q1_and_half(pbp: pd.DataFrame, game_ids) -> tuple[dict, dict]:
    """First-quarter receiving and passing yards per player, and halftime scores."""
    p = pbp[pbp["game_id"].isin(set(game_ids))]
    q1, half = {}, {}
    if not len(p):
        return q1, half
    c = p[(p["qtr"] == 1) & (p["complete_pass"] == 1)]
    yd = c["yards_gained"].fillna(0)
    for (gid, pid), v in c.assign(y=yd).groupby(["game_id", "receiver_player_id"])["y"].agg(["size", "sum"]).iterrows():
        q1.setdefault(gid, {}).setdefault(pid, {})
        q1[gid][pid].update({"q1_rec": float(v["size"]), "q1_rec_yds": float(v["sum"])})
    for (gid, pid), v in c.assign(y=yd).groupby(["game_id", "passer_player_id"])["y"].sum().items():
        q1.setdefault(gid, {}).setdefault(pid, {})["q1_pass_yds"] = float(v)
    if "total_home_score" in p.columns:
        h = p[p["qtr"] <= 2].groupby("game_id")[["total_home_score", "total_away_score"]].max()
        for gid, r in h.iterrows():
            half[gid] = {"h": float(r["total_home_score"]), "a": float(r["total_away_score"])}
    return q1, half


RESULT_COLS = ["pass_yds", "pass_cmp", "pass_att", "pass_td", "pass_int", "rec", "rec_yds", "rec_td",
               "carries", "rush_yds", "rush_td", "rush_rec_yds", "tds", "q1_rec", "q1_rec_yds", "q1_pass_yds"]


def build_results(pbp: pd.DataFrame, schedules: pd.DataFrame, season: int) -> dict:
    """Final scores, halftime scores and box scores for this season's finished games.
    The dashboard grades your logged bets from this file."""
    sch = schedules[(schedules["season"] == season) & schedules["home_score"].notna()]
    ids = list(sch["game_id"])
    out = {"cols": RESULT_COLS, "games": {}, "players": {}}
    if not ids:
        return out
    st = player_game_stats(pbp, ids)
    pa = pbp[pbp["game_id"].isin(set(ids)) & (pbp["pass_attempt"] == 1) & (pbp["sack"] != 1)]
    att = pa.groupby(["game_id", "passer_player_id"]).size()
    q1, half = q1_and_half(pbp, ids)
    for _, r in sch.iterrows():
        gid = r["game_id"]
        g = {"home": r["home_team"], "away": r["away_team"], "h": float(r["home_score"]), "a": float(r["away_score"])}
        if gid in half:
            g["h1h"], g["h1a"] = half[gid]["h"], half[gid]["a"]
        out["games"][gid] = g
    if len(st):
        for (gid, pid), r in st.iterrows():
            d = r.to_dict()
            d["pass_att"] = float(att.get((gid, pid), 0))
            d["tds"] = float(d.get("rush_td", 0) + d.get("rec_td", 0))
            d.update(q1.get(gid, {}).get(pid, {}))
            out["players"].setdefault(gid, {})[pid] = [fnum(d.get(c, 0.0) or 0.0, 1) for c in RESULT_COLS]
    return out


# ---------------------------------------------------------------------
# PROPS
# ---------------------------------------------------------------------
def _float(v):
    try:
        x = float(v)
        return x if np.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _s(v):
    return "" if v is None or (isinstance(v, float) and np.isnan(v)) else str(v).strip()


def filter_stale(props: pd.DataFrame, path, week: int):
    """Stop old prop lines from silently attaching to a new week's games.

    A row is skipped when:
      - it has a week number in the `week` column that isn't this week, or
      - it has no week number and the exact same line + odds was first seen in an earlier week.
    Returns (rows to use, list of (row, reason) that were skipped)."""
    if props is None or not len(props):
        return props, []
    lg = _load(path, {"props": {}})
    seen = lg.setdefault("seen_rows", {})
    keep, stale = [], []
    for _, r in props.iterrows():
        wk = _s(r.get("week"))
        if wk:
            try:
                w = int(float(wk))
            except ValueError:
                w = None
            if w is not None and w != week:
                stale.append((r, f"marked for week {w}, this run is week {week}"))
                continue
            keep.append(r)
            continue
        fp = "|".join(_s(r.get(c)).lower() for c in ("player", "team", "stat", "line", "over_odds", "under_odds"))
        first = seen.get(fp)
        if first is not None and first != week:
            stale.append((r, f"this exact line was already entered in week {first}"))
            continue
        seen.setdefault(fp, week)
        keep.append(r)
    _save(path, lg)
    return (pd.DataFrame(keep) if keep else props.iloc[0:0]), stale


def update_props_log(path, rows, season, week, now):
    """Save every prop the model evaluated (pre-kickoff games only reach here).
    One record per player per prop type: if the line moves before kickoff, the record
    follows it, so nothing is counted twice. The first line we saw is remembered."""
    lg = _load(path, {"props": {}})
    lg.setdefault("props", {})
    ts = now.isoformat(timespec="minutes")
    index = {(v.get("game_id"), v.get("pid"), v.get("stat")): k for k, v in lg["props"].items()}
    for r in rows:
        if r.get("error") or r.get("model_over") is None or not r.get("pid"):
            continue
        trio = (r["game_id"], r["pid"], r["stat_key"])
        old = None
        if trio in index:
            old = lg["props"].get(index[trio])
            if old and old.get("result"):
                continue  # graded results are final
            lg["props"].pop(index[trio], None)
        key = f"{r['game_id']}|{r['pid']}|{r['stat_key']}"
        first_line = old.get("first_line", old.get("line")) if old else r.get("line")
        first_lean = (old.get("first_lean", old.get("lean")) if old else r.get("lean"))
        lg["props"][key] = {
            "key": key, "season": season, "week": week, "game_id": r["game_id"], "pid": r["pid"],
            "player": r["player"], "team": r.get("team"), "opp": r.get("opp"), "pos": r.get("pos"),
            "stat": r["stat_key"], "line": r.get("line"),
            "over_odds": r.get("over_odds"), "under_odds": r.get("under_odds"),
            "model_over": r["model_over"], "book_over": r["book_over"], "edge": r["edge"],
            "lean": r.get("lean"), "tier": r.get("tier"), "median": r.get("median"),
            "source": r.get("source") or "manual", "book": r.get("book"),
            "first_line": first_line, "first_lean": first_lean,
            "logged_at": old["logged_at"] if old else ts, "updated_at": ts, "result": None}
        index[trio] = key
    _save(path, lg)


def player_game_stats(pbp: pd.DataFrame, game_ids) -> pd.DataFrame:
    """Actual stats per (game, player), rebuilt from play-by-play.
    Can differ from official box scores by a yard or two."""
    p = pbp[pbp["game_id"].isin(game_ids)]
    if "two_point_attempt" in p.columns:
        p = p[p["two_point_attempt"] != 1]
    yds = p["yards_gained"].fillna(0)

    pa = p[(p["pass_attempt"] == 1) & p["passer_player_id"].notna()]
    passing = pa.assign(py=np.where(pa["complete_pass"] == 1, yds[pa.index], 0.0)).groupby(
        ["game_id", "passer_player_id"]).agg(
        pass_yds=("py", "sum"), pass_cmp=("complete_pass", "sum"),
        pass_td=("pass_touchdown", "sum"), pass_int=("interception", "sum"))
    passing.index.names = ["game_id", "pid"]

    tg = p[(p["pass_attempt"] == 1) & p["receiver_player_id"].notna()]
    receiving = tg.assign(ry=np.where(tg["complete_pass"] == 1, yds[tg.index], 0.0)).groupby(
        ["game_id", "receiver_player_id"]).agg(
        rec=("complete_pass", "sum"), rec_yds=("ry", "sum"), rec_td=("pass_touchdown", "sum"))
    receiving.index.names = ["game_id", "pid"]

    ru = p[(p["rush"] == 1) & p["rusher_player_id"].notna()]
    rushing = ru.assign(ryd=yds[ru.index]).groupby(["game_id", "rusher_player_id"]).agg(
        carries=("rush", "sum"), rush_yds=("ryd", "sum"), rush_td=("rush_touchdown", "sum"))
    rushing.index.names = ["game_id", "pid"]

    st = pd.concat([passing, receiving, rushing], axis=1).fillna(0.0)
    for c in ["pass_yds", "pass_cmp", "pass_td", "pass_int", "rec", "rec_yds", "rec_td",
              "carries", "rush_yds", "rush_td"]:
        if c not in st.columns:
            st[c] = 0.0
    st["rush_rec_yds"] = st["rush_yds"] + st["rec_yds"]
    st["fpts"] = (st["pass_yds"] * 0.04 + st["pass_td"] * 4 - st["pass_int"] * 2 + st["rush_yds"] * 0.1
                  + st["rush_td"] * 6 + st["rec"] + st["rec_yds"] * 0.1 + st["rec_td"] * 6)
    return st


def _payout(odds):
    """Profit on a 1-unit win at American odds. Missing odds count as -110."""
    try:
        o = float(odds)
        if not np.isfinite(o) or o == 0:
            raise ValueError
    except (TypeError, ValueError):
        o = -110.0
    return o / 100 if o > 0 else 100 / abs(o)


def _grade_one(r, s, ts):
    if s is None:
        return {"actual": None, "outcome": "Void", "lean_result": "void" if r.get("lean") else None,
                "profit": 0.0, "graded_at": ts}
    key = r["stat"]
    if key == "anytime_td":
        actual, line = (1.0 if (s["rush_td"] + s["rec_td"]) >= 1 else 0.0), 0.5
    elif key == "tds":
        actual, line = float(s["rush_td"] + s["rec_td"]), float(r["line"])
    else:
        actual, line = float(s[key]), float(r["line"])
    outcome = "Over" if actual > line else ("Under" if actual < line else "Push")
    lean_result, profit = None, 0.0
    if r.get("lean"):
        lean_result = "push" if outcome == "Push" else ("win" if outcome == r["lean"] else "loss")
        pay = _payout(r.get("over_odds") if r["lean"] == "Over" else r.get("under_odds"))
        profit = pay if lean_result == "win" else (-1.0 if lean_result == "loss" else 0.0)
    return {"actual": fnum(actual, 1), "outcome": outcome, "lean_result": lean_result,
            "profit": fnum(profit, 3), "graded_at": ts}


def _est_no_td_payout(book_over_pct, hold=0.04):
    """Older 'No TD' picks were saved without a No price. Estimate a realistic one
    from the Yes price plus a normal sportsbook margin, instead of assuming -110."""
    p_no = min(0.985, max(0.05, 1 - float(book_over_pct) / 100 + hold))
    return 1 / p_no - 1


def backfill(lg) -> bool:
    """One-time fixes for records saved by older versions. Returns True if anything changed."""
    changed = False
    for r in lg.get("props", {}).values():
        if "tier" not in r:
            r["tier"] = prop_tier(r.get("stat"), r.get("edge"), r.get("lean"))
            changed = True
        res = r.get("result")
        if (res and r.get("stat") == "anytime_td" and r.get("lean") == "Under" and not r.get("under_odds")
                and not res.get("est_price") and res.get("lean_result") == "win" and r.get("book_over") is not None):
            res["profit"] = fnum(_est_no_td_payout(r["book_over"]), 3)
            res["est_price"] = True
            changed = True
    return changed


def grade_props(path, pbp, schedules, now):
    lg = _load(path, {"props": {}})
    props = lg.setdefault("props", {})
    if backfill(lg):
        _save(path, lg)
    final_ids = set(schedules.loc[schedules["home_score"].notna(), "game_id"])
    in_pbp = set(pbp["game_id"].unique())
    pending = [r for r in props.values()
               if not r.get("result") and r["game_id"] in final_ids and r["game_id"] in in_pbp]
    if pending:
        stats = player_game_stats(pbp, {r["game_id"] for r in pending})
        ts = now.isoformat(timespec="minutes")
        for r in pending:
            idx = (r["game_id"], r["pid"])
            try:
                r["result"] = _grade_one(r, stats.loc[idx] if idx in stats.index else None, ts)
            except Exception as e:  # noqa: BLE001
                log.warning(f"could not grade {r.get('player')} {r.get('stat')}: {e}")
        _save(path, lg)
    return prop_summary(lg)


def _rec_block(items):
    w = sum(1 for r in items if r["result"]["lean_result"] == "win")
    l = sum(1 for r in items if r["result"]["lean_result"] == "loss")
    p = sum(1 for r in items if r["result"]["lean_result"] == "push")
    units = sum(r["result"]["profit"] or 0 for r in items)
    return {"w": w, "l": l, "push": p, "units": fnum(units, 2),
            "roi": fnum(100 * units / (w + l), 1) if (w + l) else None,
            **(record_stats(w, l) or {"n": 0})}


def prop_summary(lg):
    props = list(lg.get("props", {}).values())
    done = [r for r in props if r.get("result")]
    graded = [r for r in done if r["result"]["outcome"] != "Void"]
    out = {"logged": len(props), "graded": len(graded),
           "pending": len(props) - len(done), "voided": len(done) - len(graded)}

    bets = [r for r in graded if r.get("lean") and r["result"]["lean_result"] in ("win", "loss", "push")]
    out["leans"] = _rec_block(bets)
    out["by_stat"] = [{"stat": st, "label": stat_label(st), **_rec_block([r for r in bets if r["stat"] == st])}
                      for st in sorted({r["stat"] for r in bets})]
    out["by_side"] = [{"side": sd, **_rec_block([r for r in bets if r["lean"] == sd])} for sd in ("Over", "Under")]
    lo_p, hi_p, top = (round(100 * x) for x in (C.PROP_PLAY_MIN, C.PROP_PLAY_MAX, C.PROP_WATCH_MAX))
    out["by_edge"] = [{"range": nm, **_rec_block([r for r in bets if lo <= abs(r["edge"] or 0) < hi])}
                      for nm, lo, hi in ((f"{lo_p} to {hi_p}%", lo_p, hi_p), (f"{hi_p} to {top}%", hi_p, top),
                                         (f"{top}%+", top, 999))]
    out["by_tier"] = [{"tier": t, **_rec_block([r for r in bets if r.get("tier") == t])}
                      for t in ("play", "watch", "too_big")]
    out["by_type_side"] = [{"stat": st, "label": stat_label(st), "side": sd,
                            **_rec_block([r for r in bets if r["stat"] == st and r["lean"] == sd])}
                           for st in sorted({r["stat"] for r in bets}) for sd in ("Over", "Under")]
    out["plays"] = _rec_block([r for r in bets if r.get("tier") == "play"])
    out["est_priced"] = sum(1 for r in bets if r["result"].get("est_price"))
    out["weeks"] = sorted({int(r["week"]) for r in bets if r.get("week") is not None})

    # every prop with a result: did the model's favored side hit?
    sided = [r for r in graded if r["result"]["outcome"] in ("Over", "Under") and r.get("model_over") is not None]
    hit = [int((r["model_over"] >= 50) == (r["result"]["outcome"] == "Over")) for r in sided]
    out["model_side"] = {"w": int(sum(hit)), "l": int(len(hit) - sum(hit)),
                         **(record_stats(sum(hit), len(hit) - sum(hit)) or {"n": 0})}

    # probability quality: lower Brier = better forecaster
    both = [r for r in sided if r.get("book_over") is not None]
    if both:
        y = np.array([1.0 if r["result"]["outcome"] == "Over" else 0.0 for r in both])
        m = np.array([r["model_over"] / 100 for r in both])
        b = np.array([r["book_over"] / 100 for r in both])
        out["brier"] = {"n": len(both), "model": fnum(np.mean((m - y) ** 2), 4), "book": fnum(np.mean((b - y) ** 2), 4)}
    else:
        out["brier"] = None

    # touchdown props only: is the model's TD chance more accurate than the book's?
    out["td_accuracy"] = {}
    for stat in ("anytime_td", "tds"):
        tb = [r for r in both if r.get("stat") == stat]
        if tb:
            y = np.array([1.0 if r["result"]["outcome"] == "Over" else 0.0 for r in tb])
            m = np.array([r["model_over"] / 100 for r in tb])
            b = np.array([r["book_over"] / 100 for r in tb])
            out["td_accuracy"][stat] = {"n": len(tb), "model": fnum(np.mean((m - y) ** 2), 4),
                                        "book": fnum(np.mean((b - y) ** 2), 4),
                                        "model_avg": fnum(m.mean() * 100, 1), "book_avg": fnum(b.mean() * 100, 1),
                                        "actual": fnum(y.mean() * 100, 1)}

    # did prop lines move after our first look? (only possible when lines get refreshed)
    mv = {"n": 0, "moved": 0, "toward": 0, "away": 0}
    for r in props:
        a, b = _float(r.get("first_line")), _float(r.get("line"))
        if a is None or b is None or r.get("stat") in ("anytime_td", "tds"):
            continue
        mv["n"] += 1
        if b != a:
            mv["moved"] += 1
            fl = r.get("first_lean")
            if fl in ("Over", "Under"):
                good = (b > a) if fl == "Over" else (b < a)
                mv["toward" if good else "away"] += 1
    out["line_moves"] = mv
    out["sources"] = {"auto": sum(1 for r in graded if str(r.get("source", "")).startswith("auto")),
                      "manual": sum(1 for r in graded if not str(r.get("source", "")).startswith("auto"))}

    recent = sorted(graded, key=lambda r: r["result"]["graded_at"], reverse=True)[:40]
    out["recent"] = [{"player": r["player"], "team": r["team"], "week": r["week"], "stat": r["stat"],
                      "label": stat_label(r["stat"]), "tier": r.get("tier"),
                      "line": r["line"], "lean": r.get("lean"), "model_over": r["model_over"],
                      "book_over": r["book_over"], "edge": r["edge"], "actual": r["result"]["actual"],
                      "outcome": r["result"]["outcome"], "result": r["result"]["lean_result"],
                      "profit": r["result"]["profit"]} for r in recent]
    return out
