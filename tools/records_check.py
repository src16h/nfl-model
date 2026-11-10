"""
Drawdowns, baselines, dropped records and late runs (Nov 10 2026). Part of the weekly scorecard (tools/weekly_review.py).

  1. Every bet record (game plays, prop plays) in the order it was bet: units, return, the worst peak-to-trough
     drawdown in units, and the longest losing streak.
  2. A dumb baseline next to the model, on the same games:
       - moneyline leans and plays vs "always bet the favorite" (soccer: the shortest of home / draw / away)
       - prop plays vs "bet every graded prop of the same stat and side at the book line" (every lean)
     A record only means something if it beats the baseline, not just zero.
  3. Late scheduled runs: how long after its cron time each scheduled workflow actually fired in the last 7 days
     (needs GITHUB_TOKEN or the gh CLI; says "not checked" otherwise).

    python tools/records_check.py
"""
import json
import math
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import prop_diagnose as PD  # noqa: E402

DIRS = {"NFL": "docs/data", "NHL": "docs/nhl/data", "NBA": "docs/nba/data", "CFB": "docs/cfb/data", "Soccer": "docs/soccer/data"}
LATE_MIN = 60          # flag a workflow whose median delay is over this many minutes


def _load(p, default=None):
    try:
        return json.loads(Path(p).read_text())
    except Exception:  # noqa: BLE001
        return default


def _f(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def payout(odds):
    o = _f(odds)
    if o is None:
        return None
    return o / 100 if o > 0 else 100 / -o


def series_stats(units):
    """units: per-bet results in betting order. n, units, worst drawdown (units below the running peak), longest losing run."""
    cum = peak = dd = 0.0
    run = worst_run = 0
    for u in units:
        cum += u
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
        run = run + 1 if u < 0 else (0 if u > 0 else run)
        worst_run = max(worst_run, run)
    n = len(units)
    return {"n": n, "units": round(cum, 2), "roi": round(100 * cum / n, 1) if n else None,
            "max_drawdown": round(dd, 2), "longest_losing_run": worst_run}


def _res_units(r):
    """A graded play row {res, units} -> units (W/L/P and half results)."""
    u = _f(r.get("units"))
    return 0.0 if u is None else u


# ---------------------------------------------------------------------------------------------------------------------
# 1. bet records in order
# ---------------------------------------------------------------------------------------------------------------------
def bet_records(sport):
    L = _load(ROOT / DIRS[sport] / "latest.json", {}) or {}
    out = {}
    if sport == "NFL":
        gp = ((L.get("live_record") or {}).get("game_plays") or {}).get("list") or []
        gp = [x for x in gp if x.get("res") in ("W", "L", "P", "HW", "HL")]
        out["game plays"] = (sorted(gp, key=lambda x: (x.get("week") or 0)), False)
    else:
        tr = L.get("tracking") or {}
        gp = [x for x in (tr.get("plays_list") or []) if x.get("res") in ("W", "L", "P", "HW", "HL")]
        n_rec = sum(int(((tr.get("plays") or {}).get(k)) or 0) for k in ("w", "l"))
        capped = n_rec > sum(1 for x in gp if x.get("res") in ("W", "L", "HW", "HL")) + 2
        out["game plays"] = (sorted(gp, key=lambda x: str(x.get("date") or "")), capped)
    key = {"NFL": "nfl", "NHL": "nhl", "NBA": "nba", "CFB": "cfb"}.get(sport)
    if key:
        try:
            pr = [r for r in PD.rows(key) if r["play"] and r["win"] is not None]
            rows = [{"date": r["date"], "units": (payout(r["odds"]) or 0.91) if r["win"] else -1.0} for r in pr]
            out["prop plays"] = (sorted(rows, key=lambda x: str(x["date"])), False)
        except Exception as e:  # noqa: BLE001
            out["prop plays"] = ([], f"failed: {str(e)[:80]}")
    return {k: {**series_stats([_res_units(x) for x in v]), "capped": c} for k, (v, c) in out.items()}


# ---------------------------------------------------------------------------------------------------------------------
# 2. baselines
# ---------------------------------------------------------------------------------------------------------------------
def _ml_rows(sport):
    """Every graded game with the model's moneyline pick and the book's prices: (pick_units, fav_units, played)."""
    d = ROOT / DIRS[sport]
    res = _load(d / "results.json", {}) or {}
    if sport == "NFL":
        res = res.get("games") or {}
    rows = []
    for f in sorted((d / "history").glob("*.json")):
        h = _load(f, {}) or {}
        for g in h.get("games") or []:
            r = res.get(str(g.get("game_id")))
            if not r:
                continue
            pk = g.get("picks") or {}
            if sport == "Soccer":
                p, b = pk.get("1x2") or {}, g.get("book") or {}
                hg, ag = _f(r.get("hg")), _f(r.get("ag"))
                prices = {"home": _f(b.get("ml_home")), "draw": _f(b.get("ml_draw")), "away": _f(b.get("ml_away"))}
                if hg is None or ag is None or None in prices.values() or not p.get("who"):
                    continue
                outcome = "home" if hg > ag else "away" if ag > hg else "draw"
                fav = max(prices, key=lambda k: 1 / (1 + payout(prices[k])))      # shortest price
                pu = payout(prices[p["who"]]) if p["who"] == outcome else -1.0
                fu = payout(prices[fav]) if fav == outcome else -1.0
                rows.append((pu, fu, bool(p.get("play"))))
                continue
            if sport == "NFL":
                p = pk.get("moneyline") or {}
                mh, ma = _f(g.get("ml_home")), _f(g.get("ml_away"))
            else:
                p = pk.get("ml") or {}
                b = g.get("book") or {}
                mh, ma = _f(b.get("ml_home")), _f(b.get("ml_away"))
            hs, as_ = _f(r.get("h")), _f(r.get("a"))
            if not p.get("side") or mh is None or ma is None or hs is None or as_ is None or hs == as_:
                continue
            home_won = hs > as_
            pick_home = p["side"] == g.get("home")
            pu = payout(mh if pick_home else ma) if pick_home == home_won else -1.0
            fav_home = mh < ma
            fu = payout(mh if fav_home else ma) if fav_home == home_won else -1.0
            rows.append((pu, fu, bool(p.get("play"))))
    return rows


def baselines(sport):
    out = {}
    rows = _ml_rows(sport)
    if rows:
        def rec(sel, i):
            u = [x[i] for x in sel]
            return {"n": len(u), "units": round(sum(u), 2), "roi": round(100 * sum(u) / len(u), 1) if u else None}
        out["moneyline leans"] = {"model": rec(rows, 0), "always the favorite": rec(rows, 1)}
        pl = [x for x in rows if x[2]]
        if pl:
            out["moneyline plays"] = {"model": rec(pl, 0), "always the favorite": rec(pl, 1)}
    key = {"NFL": "nfl", "NHL": "nhl", "NBA": "nba", "CFB": "cfb"}.get(sport)
    if key:
        try:
            R = [r for r in PD.rows(key) if r["win"] is not None]
            plays = [r for r in R if r["play"]]
            u = lambda r: (payout(r["odds"]) or 0.91) if r["win"] else -1.0
            types = sorted({(r["stat"], r["side"]) for r in plays})
            pm = [u(r) for r in plays]
            base = [u(r) for r in R if (r["stat"], r["side"]) in types]
            if pm:
                out["prop plays"] = {"model": {"n": len(pm), "units": round(sum(pm), 2), "roi": round(100 * sum(pm) / len(pm), 1)},
                                     "every lean of the same types": {"n": len(base), "units": round(sum(base), 2),
                                                                      "roi": round(100 * sum(base) / len(base), 1) if base else None}}
        except Exception as e:  # noqa: BLE001
            out["prop plays"] = {"error": str(e)[:100]}
    return out


# ---------------------------------------------------------------------------------------------------------------------
# 3. late scheduled runs
# ---------------------------------------------------------------------------------------------------------------------
def _field_ok(spec, v):
    for part in spec.split(","):
        if part == "*":
            return True
        if "-" in part:
            a, b = part.split("-")
            if int(a) <= v <= int(b):
                return True
        elif part.isdigit() and int(part) == v:
            return True
    return False


def _cron_hit(cron, t):
    mi, hr, dom, mon, dow = cron.split()[:5]
    return (_field_ok(mi, t.minute) and _field_ok(hr, t.hour) and _field_ok(dom, t.day) and _field_ok(mon, t.month)
            and _field_ok(dow.replace("7", "0"), (t.weekday() + 1) % 7))


def _last_fire(crons, t):
    """Latest cron time at or before t (within 26 hours)."""
    x = t.replace(second=0, microsecond=0)
    for _ in range(26 * 60):
        if any(_cron_hit(c, x) for c in crons):
            return x
        x -= timedelta(minutes=1)
    return None


def _gh_runs(path):
    repo = os.environ.get("GITHUB_REPOSITORY", "src16h/nfl-model")
    url = f"repos/{repo}/actions/workflows/{path}/runs?per_page=60&event=schedule"
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        req = urllib.request.Request("https://api.github.com/" + url, headers={"Authorization": f"Bearer {tok}",
                                                                             "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())["workflow_runs"]
    out = subprocess.run(["gh", "api", url], capture_output=True, text=True, timeout=30)
    if out.returncode:
        raise RuntimeError(out.stderr.strip()[:120])
    return json.loads(out.stdout)["workflow_runs"]


def late_runs(days=7):
    now = datetime.now(timezone.utc)
    out = {}
    for y in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        crons = re.findall(r'cron:\s*"([^"]+)"', y.read_text())
        if not crons or y.name == "train.yml":
            continue
        try:
            runs = _gh_runs(y.name)
        except Exception as e:  # noqa: BLE001
            return {"error": f"not checked ({str(e)[:80]})"}
        delays = []
        for r in runs:
            t = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
            if now - t > timedelta(days=days):
                continue
            f = _last_fire(crons, t)
            if f is not None:
                delays.append(round((t - f).total_seconds() / 60))
        if delays:
            s = sorted(delays)
            out[y.name] = {"runs": len(s), "median_min": s[len(s) // 2], "worst_min": s[-1]}
    return out


# ---------------------------------------------------------------------------------------------------------------------
def report():
    rep = {"sports": {}, "late_runs": late_runs()}
    for sp in DIRS:
        rep["sports"][sp] = {"bets": bet_records(sp), "baselines": baselines(sp)}
    return rep


def markdown(rep):
    L = ["## Drawdowns and baselines", "",
         "Every bet record in betting order (worst drop from a high point, longest losing run), and the model next to a dumb "
         "baseline on the same games. A record only counts as an edge if it beats the baseline.", "",
         "| Sport | Record | Bets | Units | Return | Max drawdown | Longest losing run |", "|---|---|---|---|---|---|---|"]
    for sp, S in rep["sports"].items():
        for k, v in S["bets"].items():
            if v["n"]:
                L.append(f"| {sp} | {k}{' (recent list only)' if v.get('capped') is True else ''} | {v['n']} | {v['units']:+} | {v['roi']}% | "
                         f"-{v['max_drawdown']}u | {v['longest_losing_run']} |")
    L += ["", "| Sport | What | Model | Baseline |", "|---|---|---|---|"]
    for sp, S in rep["sports"].items():
        for k, v in S["baselines"].items():
            if "error" in v:
                L.append(f"| {sp} | {k} | failed: {v['error']} | |")
                continue
            (mn, m), (bn, b) = list(v.items())[0], list(v.items())[1]
            L.append(f"| {sp} | {k} | {m['n']} bets, {m['units']:+}u ({m['roi']}%) | {bn}: {b['n']} bets, {b['units']:+}u ({b['roi']}%) |")
    lr = rep["late_runs"]
    L += ["", "### Scheduled runs: how late they fired (last 7 days)", ""]
    if "error" in lr:
        L.append(lr["error"])
    else:
        L += ["| Workflow | Runs | Median delay | Worst |", "|---|---|---|---|"]
        L += [f"| {k} | {v['runs']} | {v['median_min']} min | {v['worst_min']} min |" for k, v in lr.items()]
    return "\n".join(L) + "\n"


def flags(rep):
    out = []
    lr = rep["late_runs"]
    for k, v in (lr.items() if "error" not in lr else []):
        if v["median_min"] > LATE_MIN:
            out.append({"sport": "All", "level": "high", "what": f"late runs: {k}",
                        "why": f"scheduled runs fired a median {v['median_min']} min late (worst {v['worst_min']}) over {v['runs']} runs; pre-game runs may land after games start"})
    for sp, S in rep["sports"].items():
        for k, v in S["baselines"].items():
            if "error" in v or len(v) < 2:
                continue
            (_, m), (bn, b) = list(v.items())[:2]
            if m["n"] >= 40 and (m["roi"] or 0) > 0 and (b["roi"] or 0) >= (m["roi"] or 0):
                out.append({"sport": sp, "level": "info", "what": f"no better than baseline: {k}",
                            "why": f"model {m['roi']}% over {m['n']}, {bn} {b['roi']}% over {b['n']}"})
    return out


if __name__ == "__main__":
    r = report()
    print(markdown(r))
    for f in flags(r):
        print(f)
