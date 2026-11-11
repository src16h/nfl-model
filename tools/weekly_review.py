"""
Weekly review of every model (Oct 31 2026). Reads each sport's published data and scores every part the same way:

  - every graded record (game plays by type, props by stat and side, alt plays, parlays, teasers, early totals...):
    wins, losses, units, return, and a z-score of the return against break-even
  - every "said vs hit" pair (parlay tickets and legs, prop calibration, alt leg types): the gap in points
  - closing-line value where tracked
  - gates (paused / active bet types), odds credits left, how fresh the data is

and flags what needs a look, with the sample size behind it. Writes docs/review/latest.md and latest.json and appends
a dated copy to docs/review/history/. The weekly review session (a scheduled task) reads this first, digs into the
flagged items, and only then changes anything (see docs/review/RULES.md).

    python tools/weekly_review.py
"""
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import prop_diagnose as PD  # noqa: E402
import records_check as RC  # noqa: E402
OUT = ROOT / "docs" / "review"
SPORTS = {"NFL": "docs/data", "NHL": "docs/nhl/data", "NBA": "docs/nba/data", "CFB": "docs/cfb/data", "Soccer": "docs/soccer/data"}

LOSING_N, LOSING_ROI = 25, -8.0          # records: this many graded and returning this or worse
WINNING_N, WINNING_ROI = 40, 8.0         # worth noting the other way (don't loosen rules on less)
GAP_N, GAP_PTS = 20, 8.0                 # said vs hit: tickets / legs with a gap this big
CAL_N, CAL_PTS = 100, 5.0                # calibration rows
STALE_H = {"NFL": 7 * 24, "CFB": 72}     # hours before data counts as stale (others 36)


def load(p):
    try:
        return json.loads(Path(p).read_text())
    except Exception:  # noqa: BLE001
        return None


def num(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def walk(o, path=(), depth=0):
    """Every dict inside o (up to depth 4) with its path."""
    if isinstance(o, dict) and depth <= 4:
        yield path, o
        for k, v in o.items():
            if k in ("recent", "plays_list", "prop_plays_list", "alt_plays_list", "history", "series", "series_by", "weeks", "games", "players"):
                continue
            yield from walk(v, path + (str(k),), depth + 1)
    elif isinstance(o, list) and depth <= 4:
        for i, v in enumerate(o[:60]):
            if isinstance(v, dict):
                lab = v.get("label") or v.get("group") or v.get("name") or str(i)
                yield from walk(v, path + (str(lab),), depth + 1)


def records(track):
    out = []
    for path, d in walk(track):
        w, l = num(d.get("w")), num(d.get("l"))
        if w is None or l is None or w + l == 0:
            continue
        n = int(w + l)
        u = num(d.get("units"))
        roi = num(d.get("roi"))
        if roi is None and u is not None:
            roi = 100 * u / n
        # z of the return vs 0 at roughly -110 odds (sd of a 1-unit bet about 0.95)
        z = (roi / 100) * math.sqrt(n) / 0.95 if roi is not None else None
        out.append({"what": " / ".join(path) or "all", "w": int(w), "l": int(l), "n": n, "pct": round(100 * w / n, 1),
                    "units": None if u is None else round(u, 2), "roi": None if roi is None else round(roi, 1),
                    "z": None if z is None else round(z, 2)})
    return out


def said_vs_hit(track):
    out = []
    for path, d in walk(track):
        what = " / ".join(path) or "all"
        n, hits, model = num(d.get("n")), num(d.get("hits")), num(d.get("model"))
        if n and hits is not None and model is not None:
            out.append({"what": what + " (tickets)", "n": int(n), "said": round(model, 1), "hit": round(100 * hits / n, 1)})
        ln, lm, la = num(d.get("legs_n")), num(d.get("legs_model")), num(d.get("legs_actual"))
        if ln and lm is not None and la is not None:
            out.append({"what": what + " (legs)", "n": int(ln), "said": round(lm, 1), "hit": round(la, 1)})
        act = num(d.get("actual"))
        if n and model is not None and act is not None and hits is None:
            out.append({"what": what, "n": int(n), "said": round(model, 1), "hit": round(act, 1)})
    for r in out:
        r["gap"] = round(r["hit"] - r["said"], 1)
        se = 100 * math.sqrt(max(r["said"], 1) / 100 * (1 - min(r["said"], 99) / 100) / max(r["n"], 1))
        r["z"] = round(r["gap"] / se, 2) if se else None
    return out


MAX_CHANGES = 3                # docs/review/RULES.md: at most 3 changes per sport per week
_SPORT_NAMES = ("NFL", "NHL", "NBA", "CFB", "Soccer")


def change_counts(text, today, days=7):
    """Changes logged per sport in docs/review/CHANGES.md over the last `days` days. An entry line looks like
    "- NHL / NBA | what changed | ..." under a "## 2026-11-10 (...)" heading. "All" counts for every sport; Tools and
    Tests lines and "undone:" lines (taking a change back) count for none."""
    from datetime import date, timedelta
    start = (today - timedelta(days=days - 1)).isoformat()
    counts, day = {s: 0 for s in _SPORT_NAMES}, None
    for line in text.splitlines():
        if line.startswith("## "):
            head = line[3:13]
            try:
                date.fromisoformat(head)
                day = head
            except ValueError:
                day = None
            continue
        if day is None or day < start or day > today.isoformat() or not line.startswith("- ") or " | " not in line:
            continue
        who, what = line[2:].split(" | ", 1)
        if what.strip().lower().startswith("undone"):
            continue
        names = [w.strip().lower() for w in who.replace(",", "/").split("/")]
        for s in _SPORT_NAMES:
            if s.lower() in names or any(n.startswith("all") for n in names):
                counts[s] += 1
    return counts


CLOSE_SINCE = "2026-11-12"     # closing pulls for prop plays were fixed on Nov 11 2026; coverage is counted from here


def review():
    now = datetime.now(timezone.utc)
    rep = {"generated_at": now.isoformat(timespec="minutes"), "sports": {}, "flags": []}
    for sport, d in SPORTS.items():
        L = load(ROOT / d / "latest.json")
        if not L:
            rep["flags"].append({"sport": sport, "level": "high", "what": "no data", "why": f"{d}/latest.json missing or unreadable"})
            continue
        track = dict(L.get("tracking") or {})
        for k in ("cross_parlays", "plays_record", "live_record"):
            if isinstance(L.get(k), dict):
                track[k] = L[k].get("tracking", L[k]) if k == "cross_parlays" else L[k]
        gates = L.get("gates") or track.pop("gates", None) or []
        age = None
        try:
            age = (now - datetime.fromisoformat(L["generated_at"].replace("Z", "+00:00"))).total_seconds() / 3600
        except Exception:  # noqa: BLE001
            pass
        recs, svh = records(track), said_vs_hit(track)
        odds = L.get("odds") if isinstance(L.get("odds"), dict) else {}
        if not odds and isinstance((L.get("model") or {}).get("odds"), dict):     # NFL keeps it under model.odds (Nov 10 2026)
            mo = L["model"]["odds"]
            odds = {"remaining": mo.get("credits_remaining"), "source": "odds_api" if mo.get("enabled") else None}
        S = {"age_h": None if age is None else round(age, 1), "credits_left": (odds or {}).get("remaining"),
             "odds_source": (odds or {}).get("source"), "records": recs, "said_vs_hit": svh,
             "gates": [{"name": g.get("name"), "label": g.get("label"), "status": g.get("status"), "record": g.get("record")} for g in gates if isinstance(g, dict)],
             "backtest": (L.get("model") or {}).get("backtest") if isinstance(L.get("model"), dict) else L.get("backtest")}
        rep["sports"][sport] = S
        if age is not None and age > STALE_H.get(sport, 36):
            rep["flags"].append({"sport": sport, "level": "high", "what": "stale data", "why": f"last update {age:.0f} hours ago"})
        cl = num(S["credits_left"])
        if cl is not None and cl < 60:
            rep["flags"].append({"sport": sport, "level": "medium", "what": "odds credits low", "why": f"{cl:.0f} left this month"})
        for r in recs:
            if r["n"] >= LOSING_N and r["roi"] is not None and r["roi"] <= LOSING_ROI:
                rep["flags"].append({"sport": sport, "level": "high" if (r["z"] or 0) <= -2 else "medium", "what": f"losing: {r['what']}",
                                     "why": f"{r['w']}-{r['l']}, {r['units']:+}u, {r['roi']:+}% (z {r['z']})"})
            elif r["n"] >= WINNING_N and r["roi"] is not None and r["roi"] >= WINNING_ROI:
                rep["flags"].append({"sport": sport, "level": "info", "what": f"winning: {r['what']}",
                                     "why": f"{r['w']}-{r['l']}, {r['units']:+}u, {r['roi']:+}% (z {r['z']})"})
        for r in svh:
            n_min = CAL_N if "calibration" in r["what"] else GAP_N
            pts = CAL_PTS if "calibration" in r["what"] else GAP_PTS
            if r["n"] >= n_min and abs(r["gap"]) >= pts:
                rep["flags"].append({"sport": sport, "level": "high" if abs(r["z"] or 0) >= 2 else "medium",
                                     "what": f"said vs hit: {r['what']}", "why": f"said {r['said']}%, hit {r['hit']}% over {r['n']} (z {r['z']})"})
        # closing prices on prop plays (Nov 11 2026): how many plays since the fix got a later price to be judged against.
        # Without one the closing-line gates (gates.py) never see a prop type.
        pl = [x for x in (track.get("prop_plays_list") or []) if isinstance(x, dict) and str(x.get("date") or "") >= CLOSE_SINCE]
        priced = [x for x in pl if x.get("clv") is not None or x.get("move") in (1, -1)]
        # parlay tickets in units (parlaymoney.py, Nov 11 2026): every ticket record that carries "money"
        S["parlay_money"] = [{"what": " / ".join(pth) or "tickets", **x["money"]} for pth, x in walk(track)
                             if isinstance(x.get("money"), dict) and x["money"].get("n")]
        for m in S["parlay_money"]:
            b = m.get("at_bet_at") or {}
            if (b.get("n") or 0) >= 20 and (b.get("roi") or 0) <= -8:
                rep["flags"].append({"sport": sport, "level": "high" if (b.get("z") or 0) <= -2 else "medium",
                                     "what": f"parlays losing even at the bet-at price: {m['what']}",
                                     "why": f"{b['hits']}-{b['n'] - b['hits']}, {b['units']:+}u ({b['roi']:+}%) at the shortest price the page says to take"})
        S["prop_close"] = {"since": CLOSE_SINCE, "plays": len(pl), "priced": len(priced),
                           "missed_last_run": (odds or {}).get("close_missed"), "owed": (odds or {}).get("close_debt")}
        if len(pl) >= 10 and len(priced) < 0.6 * len(pl):
            rep["flags"].append({"sport": sport, "level": "high", "what": "prop plays without a closing price",
                                 "why": f"{len(priced)} of {len(pl)} plays since {CLOSE_SINCE} have one; check the odds status (close_pulls, close_missed) and the run times"})
        for g in S["gates"]:
            rc = g.get("record") or {}
            if g.get("status") == "paused" and (rc.get("n") or 0) >= 25 and (num(rc.get("roi")) or 0) > 3:
                rep["flags"].append({"sport": sport, "level": "info", "what": f"paused but winning: {g.get('label')}",
                                     "why": f"{rc.get('w')}-{rc.get('l')} as shadow plays, {rc.get('roi')}%"})
    # the change limit (Nov 11 2026): Nov 10 logged about ten changes, three of them undone the same day
    try:
        cc = change_counts((ROOT.parent / "review" / "CHANGES.md").read_text() if (ROOT.parent / "review" / "CHANGES.md").exists()
                           else (Path(__file__).resolve().parents[1] / "docs" / "review" / "CHANGES.md").read_text(), now.date())
        rep["changes_7d"] = cc
        for sp_, n_ in cc.items():
            if n_ > MAX_CHANGES:
                rep["flags"].append({"sport": sp_, "level": "medium", "what": "over the change limit",
                                     "why": f"{n_} changes logged in the last 7 days (limit {MAX_CHANGES}): no more this week unless something is broken"})
    except Exception:  # noqa: BLE001
        pass
    # prop types that are losing or paused: not just paused, diagnosed (tools/prop_diagnose.py)
    rep["diagnoses"] = []
    for sport, key in (("NFL", "nfl"), ("NHL", "nhl"), ("NBA", "nba"), ("CFB", "cfb")):
        try:
            gst = load(ROOT / SPORTS[sport] / "gates.json") or {}
            for st, sd in PD.candidates(key, gst):
                d = PD.diagnose(key, st, sd)
                rep["diagnoses"].append(d)
                if not d.get("error"):
                    rep["flags"].append({"sport": sport, "level": "medium", "what": f"diagnosed: {st} {sd}s",
                                         "why": f"plays {d['plays']['w']}-{d['plays']['l']} ({d['plays']['roi']}%); top cause: {d['causes'][0][:140]}"})
        except Exception as e:  # noqa: BLE001
            rep["flags"].append({"sport": sport, "level": "medium", "what": "prop diagnosis failed", "why": str(e)[:160]})
    # drawdowns, baselines and late scheduled runs (tools/records_check.py, Nov 10 2026)
    try:
        rep["records"] = RC.report()
        rep["flags"] += RC.flags(rep["records"])
    except Exception as e:  # noqa: BLE001
        rep["flags"].append({"sport": "All", "level": "medium", "what": "records check failed", "why": str(e)[:160]})
    order = {"high": 0, "medium": 1, "info": 2}
    rep["flags"].sort(key=lambda f: (order.get(f["level"], 3), f["sport"]))
    return rep


def markdown(rep):
    lines = [f"# Weekly model review, {rep['generated_at'][:10]}", "",
             "Flags first (high, then medium, then info). Every number is a graded record from the site's own data.", ""]
    if rep["flags"]:
        lines += ["| Level | Sport | What | Why |", "|---|---|---|---|"]
        lines += [f"| {f['level']} | {f['sport']} | {f['what']} | {f['why']} |" for f in rep["flags"]]
    else:
        lines.append("No flags.")
    if rep.get("records"):
        lines += ["", RC.markdown(rep["records"])]
    if rep.get("diagnoses"):
        lines += ["", "## Prop diagnoses", "Every prop type that is losing (20+ plays, -8% or worse) or paused, with what's driving it.", ""]
        lines += [PD.markdown(d) for d in rep["diagnoses"]]
    for sport, S in rep["sports"].items():
        lines += ["", f"## {sport}", f"Updated {S['age_h']} hours ago, odds from {S['odds_source']}, credits left {S['credits_left']}.", ""]
        pc = S.get("prop_close") or {}
        if pc.get("plays"):
            lines += [f"Prop plays with a closing price since {pc['since']}: {pc['priced']} of {pc['plays']}"
                      + (f" (closing pulls owed to alt lines: {pc['owed']})" if pc.get("owed") else "") + ".", ""]
        rs = sorted([r for r in S["records"] if r["n"] >= 5], key=lambda r: -r["n"])[:40]
        if rs:
            lines += ["| Record | W-L | Hit | Units | Return | z |", "|---|---|---|---|---|---|"]
            lines += [f"| {r['what']} | {r['w']}-{r['l']} | {r['pct']}% | {r['units']} | {r['roi']}% | {r['z']} |" for r in rs]
        sv = [r for r in S["said_vs_hit"] if r["n"] >= 5]
        if sv:
            lines += ["", "| Said vs hit | n | Said | Hit | Gap | z |", "|---|---|---|---|---|---|"]
            lines += [f"| {r['what']} | {r['n']} | {r['said']}% | {r['hit']}% | {r['gap']:+} | {r['z']} |" for r in sv]
        pm = S.get("parlay_money") or []
        if pm:
            lines += ["", "Parlay tickets in units (1 unit a ticket). Bet-at = the shortest price the page says to take, so it is the "
                      "best case for following the page. Hard Rock's own same-game price isn't in the odds feed.", "",
                      "| Tickets | W-L | At bet-at price | At fair price | At Hard Rock's price |", "|---|---|---|---|---|"]
            fmt = lambda x: f"{x['units']:+}u ({x['roi']:+}%) over {x['n']}" if x and x.get("n") else "n/a"
            lines += [f"| {m['what']} | {m['hits']}-{m['n'] - m['hits']} | {fmt(m.get('at_bet_at'))} | {fmt(m.get('at_fair'))} | {fmt(m.get('at_book'))} |"
                      for m in pm]
        if S["gates"]:
            lines += ["", "Gates: " + "; ".join(f"{g['label']} {g['status']}" for g in S["gates"])]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    rep = review()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "history").mkdir(exist_ok=True)
    md = markdown(rep)
    (OUT / "latest.json").write_text(json.dumps(rep, indent=1, default=str))
    (OUT / "latest.md").write_text(md)
    (OUT / "history" / f"{rep['generated_at'][:10]}.md").write_text(md)
    print(md[:6000])
    print(f"\n{len(rep['flags'])} flags: " + ", ".join(f"{f['sport']} {f['what']}" for f in rep["flags"][:15]))
