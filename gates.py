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

# ---------------------------------------------------------------------------------------------------
# Game bet types (Oct 26 2026). Every sport's game plays get a gate. They start active (except NHL puck
# lines) and pause on EITHER bar: the return bar above, or the closing-line bar below.
#
# Closing-line bar: expected return of the plays at the closing fair price ("ev at close", vig included)
# averaged over CLV_PAUSE_N+ priced plays. Below CLV_PAUSE_EV, the market is saying the plays were bad
# bets even if they happened to win. Coming back needs the return bar AND ev at close of 0 or better
# (once CLV_MIN_N shadow plays have a closing price).
# ---------------------------------------------------------------------------------------------------
CLV_PAUSE_N = 30
CLV_PAUSE_EV = 0.0
RULES_SINCE = "2026-10-20"           # current play rules (Pinnacle must agree) started here in every sport

GAME_KINDS = {"nhl": ("ml", "pl", "total"), "cfb": ("spread", "total", "ml"), "soccer": ("1x2", "ah", "total"),
              "nfl": ("spread", "total")}
_KIND_LABEL = {"ml": "moneyline", "pl": "puck line", "total": "totals", "spread": "spreads", "1x2": "match result",
               "ah": "Asian handicap"}


def game_gate(sport, kind):
    return f"{sport}_game_{kind}"


for _sp, _kinds in GAME_KINDS.items():
    for _k in _kinds:
        GATES[game_gate(_sp, _k)] = {
            "label": f"{_sp.upper() if _sp != 'soccer' else 'Soccer'} {_KIND_LABEL[_k]}", "min_n": 25, "min_roi": 3.0,
            "repause_roi": -8.0, "since": RULES_SINCE, "start": "active", "clv_gate": True,
            "why": "Game bet type: pauses if 30+ priced plays lose to the closing line, or the return drops to -8%"}
GATES["nhl_game_pl"].update({
    "start": "paused", "since": "2026-10-26",
    "why": "Paused Oct 26: 1-6 (-5.1u) as plays, and both priced plays lost to the closing line"})


def game_names(sport):
    return tuple(game_gate(sport, k) for k in GAME_KINDS[sport])


def paused_kinds(st, sport):
    """Game bet types to hold back this run (they become shadow picks)."""
    return {k for k in GAME_KINDS[sport] if (st.get(game_gate(sport, k)) or {}).get("status") == "paused"}


def hold_back(picks, paused):
    """Turn plays of paused kinds into shadow picks, in place. Call before the one-play-per-game choice."""
    for k, v in (picks or {}).items():
        if v and k in paused and v.get("play"):
            v["play"], v["shadow"] = False, True
    return picks


def shadow_flags(picks, prev, ts, fields):
    """Lock shadow picks the first time they show up, like real plays."""
    out = dict(prev or {})
    for k, v in (picks or {}).items():
        if v and v.get("shadow") and k not in out:
            out[k] = {x: v.get(x) for x in fields}
            out[k]["at"] = ts
    return out


def load(path, names):
    try:
        st = json.loads(Path(path).read_text())
    except Exception:  # noqa: BLE001
        st = {}
    for n in names:
        st.setdefault(n, {"status": GATES[n].get("start", "paused"), "since": GATES[n]["since"], "history": []})
    return st


def active(st, name):
    return (st.get(name) or {}).get("status") == "active"


def _rec(rows):
    w = sum(1 for x in rows if x["res"] in ("W", "HW"))
    l_ = sum(1 for x in rows if x["res"] in ("L", "HL"))
    u = sum(x.get("units") or 0 for x in rows)
    clv = [x["clv"] for x in rows if x.get("clv") is not None]
    ev = [x["ev"] for x in rows if x.get("ev") is not None]
    out = {"n": w + l_, "w": w, "l": l_, "units": round(u, 2), "roi": round(100 * u / (w + l_), 1) if w + l_ else None,
           "clv_n": len(clv), "clv": round(sum(clv) / len(clv), 2) if clv else None,
           "ev_n": len(ev), "ev_close": round(sum(ev) / len(ev), 2) if ev else None}
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
        if cfg.get("clv_gate"):
            clv_ok = clv_ok and (rec["ev_n"] < CLV_MIN_N or (rec["ev_close"] or 0) >= 0)
        hit_ok = not cfg.get("hit_check") or rec.get("hit") is None or rec["hit"] >= rec.get("model", 0) - 3
        if rec["n"] >= cfg["min_n"] and (rec["roi"] or -99) >= cfg["min_roi"] and clv_ok and hit_ok:
            g["history"].append({"date": today, "to": "active", "record": rec})
            g.update({"status": "active", "since": today})
    else:
        rows = [x for x in play_rows if str(x["date"]) >= since]
        rec = _rec(rows)
        bad_roi = rec["n"] >= cfg["min_n"] and (rec["roi"] or 0) <= cfg["repause_roi"]
        bad_clv = cfg.get("clv_gate") and rec["ev_n"] >= CLV_PAUSE_N and (rec["ev_close"] or 0) < CLV_PAUSE_EV
        if bad_roi or bad_clv:
            g["history"].append({"date": today, "to": "paused", "record": rec,
                                 "reason": "lost to the closing line" if bad_clv and not bad_roi else "return"})
            g.update({"status": "paused", "since": today})
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(st, indent=1))
    return {"name": name, "label": cfg["label"], "why": cfg["why"], "status": g["status"], "since": g["since"],
            "min_n": cfg["min_n"], "min_roi": cfg["min_roi"], "repause_roi": cfg["repause_roi"], "record": rec,
            "clv_gate": bool(cfg.get("clv_gate")), "clv_pause_n": CLV_PAUSE_N,
            "history": g["history"][-4:]}
