"""
Paused bet types and the bar to bring them back (Oct 21 2026).

When a bet type is cut from plays it isn't forgotten: the model keeps finding the bets it WOULD have played
("shadow plays"), locks them at the price it saw, and grades them. Only results from the pause date on count,
so the comeback is judged on fresh bets, not on the history that got it cut.

  paused -> active : at least MIN_N graded shadow plays since the pause, return of at least MIN_ROI %, and (when
                     15+ of them have a closing price) not losing to the closing line on average.
  active -> paused : at least MIN_N graded real plays since it came back, return of REPAUSE_ROI % or worse.

The bar is deliberately modest so a type can come back within a few weeks; the closing-line check guards against
a lucky run. State lives in a small JSON file per sport (docs/.../data/gates.json) and is shown on the Record tab.
"""
import json
from pathlib import Path

GATES = {
    # NFL
    "nfl_prop_overs": {"label": "NFL prop Overs (yardage)", "min_n": 40, "min_roi": 3.0, "repause_roi": -5.0, "since": "2026-10-21",
                       "why": "Paused Oct 21: 26-25 as plays (-1.8u) while Unders went 41-23 (+13.3u)"},
    "nfl_prop_rec": {"label": "NFL receptions props", "min_n": 40, "min_roi": 3.0, "repause_roi": -5.0, "since": "2026-10-21",
                     "why": "Cut earlier in October: 15-23 as plays, heavy juice"},
    # NHL
    "nhl_points": {"label": "NHL points props (Unders)", "min_n": 40, "min_roi": 3.0, "repause_roi": -5.0, "since": "2026-10-21",
                   "why": "Paused Oct 21: points props went 111-121 (-17u). Book lines are pulled only when the day's credits allow"},
    "nhl_edge": {"label": "NHL edge parlays", "min_n": 20, "min_roi": 5.0, "repause_roi": -10.0, "since": "2026-10-21", "hit_check": True,
                 "why": "Paused Oct 21: 6-12 (-4.9u) when the model expected about 46%"},
}
CLV_MIN_N = 15


def load(path, names):
    try:
        st = json.loads(Path(path).read_text())
    except Exception:  # noqa: BLE001
        st = {}
    for n in names:
        st.setdefault(n, {"status": "paused", "since": GATES[n]["since"], "history": []})
    return st


def active(st, name):
    return (st.get(name) or {}).get("status") == "active"


def _rec(rows):
    w = sum(1 for x in rows if x["res"] in ("W", "HW"))
    l_ = sum(1 for x in rows if x["res"] in ("L", "HL"))
    u = sum(x.get("units") or 0 for x in rows)
    clv = [x["clv"] for x in rows if x.get("clv") is not None]
    out = {"n": w + l_, "w": w, "l": l_, "units": round(u, 2), "roi": round(100 * u / (w + l_), 1) if w + l_ else None,
           "clv_n": len(clv), "clv": round(sum(clv) / len(clv), 2) if clv else None}
    ps = [x["p"] for x in rows if x.get("p") is not None]
    if ps:
        out["model"] = round(sum(ps) / len(ps), 1)
        out["hit"] = round(100 * w / (w + l_), 1) if w + l_ else None
    return out


def update(path, st, name, shadow_rows, play_rows, today):
    """shadow_rows / play_rows: graded rows {date, res, units, clv?, p?}. Moves the gate if the bar is met.
    Returns the summary shown on the page."""
    g, cfg = st[name], GATES[name]
    since = g["since"]
    if g["status"] == "paused":
        rows = [x for x in shadow_rows if str(x["date"]) >= since]
        rec = _rec(rows)
        clv_ok = rec["clv_n"] < CLV_MIN_N or (rec["clv"] or 0) >= 0
        hit_ok = not cfg.get("hit_check") or rec.get("hit") is None or rec["hit"] >= rec.get("model", 0) - 3
        if rec["n"] >= cfg["min_n"] and (rec["roi"] or -99) >= cfg["min_roi"] and clv_ok and hit_ok:
            g["history"].append({"date": today, "to": "active", "record": rec})
            g.update({"status": "active", "since": today})
    else:
        rows = [x for x in play_rows if str(x["date"]) >= since]
        rec = _rec(rows)
        if rec["n"] >= cfg["min_n"] and (rec["roi"] or 0) <= cfg["repause_roi"]:
            g["history"].append({"date": today, "to": "paused", "record": rec})
            g.update({"status": "paused", "since": today})
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(st, indent=1))
    return {"name": name, "label": cfg["label"], "why": cfg["why"], "status": g["status"], "since": g["since"],
            "min_n": cfg["min_n"], "min_roi": cfg["min_roi"], "repause_roi": cfg["repause_roi"], "record": rec,
            "history": g["history"][-4:]}
