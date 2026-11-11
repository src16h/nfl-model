"""
Paused bet types and the bar to bring them back (Oct 21 2026).

When a bet type is cut from plays it isn't forgotten: the model keeps finding the bets it WOULD have played
("shadow plays"), locks them at the price it saw, and grades them. Only results from the pause date on count,
so the comeback is judged on fresh bets, not on the history that got it cut.

  paused -> active : at least 40 graded shadow plays since the pause, return of at least MIN_ROI %, and 15+ of
                     them priced at the close with closing value of 0 or better.
  active -> paused : closing value below 0 over 30+ priced plays; or a return of REPAUSE_ROI % or worse that is
                     either too bad to be luck (z of -2 or lower) or has lasted 150 plays.

Nov 11 2026: the bars were MIN_N (25) plays and a return figure, with the closing check skipped whenever fewer
than 15 plays had a closing price (which was nearly always). Simulated at -110: a bet type with a true +3% return
was paused by luck 53% of the time within 150 bets, and a type with no edge came back about a third of the time at
its first look. Win/loss needs hundreds of bets to say anything; the closing price says it in dozens. So closing
value now decides, and the return bar only acts early on a loss too big to be luck. With the same simulation the
+3% type is paused by the return bar 12% of the time (was 53%), a no-edge type 38% (was 77%; the closing bar is what
catches it), and a no-edge type whose plays average -3.5% at the close practically never comes back.

State lives in a small JSON file per sport (docs/.../data/gates.json) and is shown on the Record tab.
"""
import json
import math
from pathlib import Path

GATES = {
    # NFL
    "nfl_prop_overs": {"label": "NFL prop Overs (yardage)", "min_n": 40, "min_roi": 3.0, "repause_roi": -5.0, "since": "2026-10-21",
                       "why": "Paused Oct 21: 26-25 as plays (-1.8u) while Unders went 41-23 (+13.3u)"},
    "nfl_prop_pass_under": {"label": "NFL passing-yard Unders", "min_n": 60, "min_roi": 3.0, "repause_roi": -5.0, "since": "2026-10-29",
                            "why": "Paused Oct 29: 13-20 (-25%) as leans in weeks 4-7 while rushing and receiving Unders won"},
    "nfl_prop_long_under": {"label": "NFL longest completion Unders", "min_n": 30, "min_roi": 3.0, "repause_roi": -5.0,
                            "since": "2026-11-09", "why": "New Nov 9 2026: no graded history yet, so it starts as shadow plays"},
    "nfl_prop_long_over": {"label": "NFL longest completion Overs", "min_n": 30, "min_roi": 3.0, "repause_roi": -5.0,
                           "since": "2026-11-09", "why": "New Nov 9 2026: no graded history yet, and books shade Overs"},
    "nfl_prop_rec": {"label": "NFL receptions props", "min_n": 40, "min_roi": 3.0, "repause_roi": -5.0, "since": "2026-10-21",
                     "why": "Cut earlier in October: 15-23 as plays, heavy juice"},
    # NHL
    "nhl_points": {"label": "NHL points props (Unders)", "min_n": 40, "min_roi": 3.0, "repause_roi": -5.0, "since": "2026-10-21",
                   "why": "Paused Oct 21: points props went 111-121 (-17u). Book lines are pulled only when the day's credits allow"},
    # restore_n (Nov 10 2026 review): coming back needs 40 graded shadow tickets (docs/review/RULES.md: un-pause only
    # with 40+ graded results); min_n still governs re-pausing. Shadow record then: 6-11, +10.5% over 17.
    "nhl_edge": {"label": "NHL edge parlays", "min_n": 20, "restore_n": 40, "min_roi": 5.0, "repause_roi": -10.0, "since": "2026-10-21", "hit_check": True,
                 "why": "Paused Oct 21: 6-12 (-4.9u) when the model expected about 46%"},
    # NBA (Oct 30 2026)
    "nba_edge": {"label": "NBA edge parlays", "min_n": 20, "min_roi": 5.0, "repause_roi": -10.0, "since": "2026-10-30", "hit_check": True,
                 "start": "active", "why": "Edge parlays pause if 20+ tickets return -10% or worse"},
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
ROI_Z = -2.0                 # the return bar acts early only when the loss is this many standard errors below break-even
ROI_BACKSTOP_N = 150         # ... or once the losing return has lasted this many plays
RESTORE_MIN_N = 40           # graded shadow plays needed to come back (docs/review/RULES.md: un-pause only with 40+)
RULES_SINCE = "2026-10-20"           # current play rules (Pinnacle must agree) started here in every sport

GAME_KINDS = {"nhl": ("ml", "pl", "total"), "cfb": ("spread", "total", "ml"), "soccer": ("1x2", "ah", "total"),
              "nfl": ("spread", "total"), "nba": ("ml", "spread", "total")}
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


# ---------------------------------------------------------------------------------------------------
# Prop types (Oct 30 2026): every stat and side gets its own gate, like game bet types, so a type that keeps losing
# is paused automatically instead of waiting for someone to notice (Oct 29: 33 NHL shots Unders, 11-21, -11.4u).
# Same bars as game types: 30+ priced plays losing at the close, or 25+ plays returning -8% or worse.
# ---------------------------------------------------------------------------------------------------
PROP_KINDS = {"nhl": [("sog", "Over"), ("sog", "Under"), ("goals", "Over"), ("assists", "Over"), ("assists", "Under")],
              "nba": [(s, d) for s in ("pts", "reb", "ast", "fg3m", "pra") for d in ("Over", "Under")]}
_STAT_LABEL = {"sog": "shots on goal", "goals": "goals", "assists": "assists", "pass_yds": "passing yards", "pass_long": "longest completion",
               "rush_yds": "rushing yards", "rec_yds": "receiving yards", "rec": "receptions", "anytime_td": "anytime TD",
               "tds": "2+ TDs", "pts": "points", "reb": "rebounds", "ast": "assists", "fg3m": "threes", "pra": "pts+reb+ast"}


def prop_gate(sport, stat, side):
    return f"{sport}_prop_{stat}_{side}"


for _sp, _kinds in PROP_KINDS.items():
    for _st, _sd in _kinds:
        _n = prop_gate(_sp, _st, _sd)
        if _n in GATES:
            continue
        GATES[_n] = {"label": f"{_sp.upper()} {_STAT_LABEL[_st]} {_sd}s", "min_n": 25, "min_roi": 3.0, "repause_roi": -8.0,
                     "since": RULES_SINCE, "start": "active", "clv_gate": True, "auto": True,
                     "why": "Prop type: pauses if 30+ priced plays lose to the closing line, or the return drops to -8%"}


_GAME_GATES = {game_gate(_sp, _k) for _sp, _kinds in GAME_KINDS.items() for _k in _kinds}


def prop_names(sport):
    return tuple(prop_gate(sport, st, sd) for st, sd in PROP_KINDS[sport])


def paused_props(st, sport):
    """(stat, side) prop types to hold back this run (they become shadow plays)."""
    return {(a, b) for a, b in PROP_KINDS[sport] if (st.get(prop_gate(sport, a, b)) or {}).get("status") == "paused"}


def game_names(sport):
    return tuple(game_gate(sport, k) for k in GAME_KINDS[sport])


class Paused(set):
    """Paused game bet types. pool_only: the ones held back only by the pooled check (their own gate is active)."""
    pool_only = frozenset()


def paused_kinds(st, sport, docs=None):
    """Game bet types to hold back this run (they become shadow picks): each type's own gate, plus every type while
    the pooled check across sports has game plays paused (pooled() below)."""
    own = {k for k in GAME_KINDS[sport] if (st.get(game_gate(sport, k)) or {}).get("status") == "paused"}
    out = Paused(own)
    try:
        if pooled(docs=docs)["status"] == "paused":
            out |= set(GAME_KINDS[sport])
            out.pool_only = frozenset(set(GAME_KINDS[sport]) - own)
    except Exception:  # noqa: BLE001
        pass
    return out


def hold_back(picks, paused):
    """Turn plays of paused kinds into shadow picks, in place. Call before the one-play-per-game choice."""
    pool_only = getattr(paused, "pool_only", ())
    for k, v in (picks or {}).items():
        if v and k in paused and v.get("play"):
            if v.get("early") and k in pool_only:      # CFB early totals are not the pooled rule: only their own gate stops them
                continue
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
    sq = sum((x.get("units") or 0) ** 2 for x in rows)
    out = {"n": w + l_, "w": w, "l": l_, "units": round(u, 2), "roi": round(100 * u / (w + l_), 1) if w + l_ else None,
           "z": round(u / math.sqrt(sq), 2) if sq > 0 else None,       # units won over their own spread: about -2 = not luck
           "clv_n": len(clv), "clv": round(sum(clv) / len(clv), 2) if clv else None,
           "ev_n": len(ev), "ev_close": round(sum(ev) / len(ev), 2) if ev else None}
    ps = [x["p"] for x in rows if x.get("p") is not None]
    if ps:
        out["model"] = round(sum(ps) / len(ps), 1)
        out["hit"] = round(100 * w / (w + l_), 1) if w + l_ else None
    return out


def update(path, st, name, shadow_rows, play_rows, today):
    """shadow_rows / play_rows: graded rows {date, res, units, clv?, ev?, p?}. Moves the gate if the bar is met.
    Returns the summary shown on the page."""
    g, cfg = st[name], GATES[name]
    since = g["since"]
    need_n = max(cfg["min_n"], cfg.get("restore_n", 0), RESTORE_MIN_N)
    if g["status"] == "paused":
        rows = [x for x in shadow_rows if str(x["date"]) >= since]
        rec = _rec(rows)
        if cfg.get("hit_check"):                       # parlay tickets: no closing price exists for a ticket
            clv_ok = True
        elif cfg.get("clv_gate"):                      # priced plays are required: no closing data, no comeback
            clv_ok = rec["ev_n"] >= CLV_MIN_N and (rec["ev_close"] or 0) >= 0 and (rec["clv_n"] < CLV_MIN_N or (rec["clv"] or 0) >= 0)
        else:
            clv_ok = rec["clv_n"] >= CLV_MIN_N and (rec["clv"] or 0) >= 0
        hit_ok = not cfg.get("hit_check") or rec.get("hit") is None or rec["hit"] >= rec.get("model", 0) - 3
        if rec["n"] >= need_n and (rec["roi"] or -99) >= cfg["min_roi"] and clv_ok and hit_ok:
            g["history"].append({"date": today, "to": "active", "record": rec})
            g.update({"status": "active", "since": today})
    else:
        rows = [x for x in play_rows if str(x["date"]) >= since]
        rec = _rec(rows)
        losing = rec["n"] >= cfg["min_n"] and (rec["roi"] or 0) <= cfg["repause_roi"]
        bad_roi = losing and ((rec["z"] is not None and rec["z"] <= ROI_Z) or rec["n"] >= ROI_BACKSTOP_N)
        bad_clv = cfg.get("clv_gate") and rec["ev_n"] >= CLV_PAUSE_N and (rec["ev_close"] or 0) < CLV_PAUSE_EV
        if bad_roi or bad_clv:
            g["history"].append({"date": today, "to": "paused", "record": rec,
                                 "reason": "lost to the closing line" if bad_clv and not bad_roi else "return"})
            g.update({"status": "paused", "since": today})
    if name in _GAME_GATES:                            # priced rows saved for the pooled check (pooled() below)
        g["ev_rows"] = sorted([[str(x["date"])[:10], round(float(x["ev"]), 2), kind] for kind, src in (("p", play_rows), ("s", shadow_rows))
                               for x in src if x.get("ev") is not None and str(x["date"]) >= RULES_SINCE and not x.get("early")])
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(st, indent=1))
    out = {"name": name, "label": cfg["label"], "why": cfg["why"], "status": g["status"], "since": g["since"],
           "min_n": need_n if g["status"] == "paused" else cfg["min_n"], "min_roi": cfg["min_roi"], "repause_roi": cfg["repause_roi"], "record": rec,
           "clv_gate": bool(cfg.get("clv_gate")), "clv_pause_n": CLV_PAUSE_N, "roi_z": ROI_Z, "roi_backstop_n": ROI_BACKSTOP_N,
           "history": g["history"][-4:]}
    if name in _GAME_GATES:
        pool = pooled(Path(path))
        out["pooled"] = pool
        if pool["status"] == "paused" and g["status"] == "active":      # held back by the pooled check, not by its own record
            at = next((h for h in reversed(pool["history"]) if h["to"] == "paused"), {})
            out.update({"status": "paused", "own_status": "active", "since": pool["since"],
                        "why": f"All game plays are paused: across every sport they averaged {at.get('ev', 0):+.1f}% at the closing price "
                               f"over {at.get('n', 0)} priced plays. They come back when {POOL_RESTORE_N} priced shadow plays average 0 or "
                               f"better (so far {pool['n']})."})
    return out


# ---------------------------------------------------------------------------------------------------
# Pooled check on game plays (Nov 11 2026). Every sport's game plays come from the same rule (Pinnacle calls the
# bet price value, the model agrees: betrules.decide_sharp), but each bet type waited for its own 30 priced plays,
# which takes months: on Nov 11 the biggest sample was 19 while all of them together had 50, averaging -3.2% at
# the closing fair price (a bet with no edge scores about -2 to -4.5). The rule is one rule, so it is judged once.
#
# Each sport's gates.json keeps its priced game-play rows; this reads all five and works out the pooled state from
# the rows alone (no shared file to write, so the sports' workflows can't trip over each other):
#   active -> paused : POOL_PAUSE_N+ priced plays since the last change, average closing value below 0 and
#                      z of POOL_Z or lower (the average is below 0 by more than luck explains)
#   paused -> active : POOL_RESTORE_N+ priced shadow plays since the pause, average closing value 0 or better
# While paused, every sport's game plays become shadow plays: still found, locked at the price and graded.
# CFB early totals are a different rule (the model against the opening total) and stay out of this.
# ---------------------------------------------------------------------------------------------------
POOL_PAUSE_N = 30
POOL_RESTORE_N = 40
POOL_Z = -1.5
POOL_FILES = {"nfl": "data/gates.json", "nhl": "nhl/data/gates.json", "nba": "nba/data/gates.json", "cfb": "cfb/data/gates.json",
              "soccer": "soccer/data/gates.json"}


def _stats(vals):
    n = len(vals)
    if not n:
        return 0, None, None
    m = sum(vals) / n
    sd = math.sqrt(sum((v - m) ** 2 for v in vals) / (n - 1)) if n > 1 else 0.0
    return n, m, (m / (sd / math.sqrt(n)) if sd > 0 else None)


def pooled_state(rows):
    """rows: [date, ev at close %, "p" (play) or "s" (shadow play)] from every sport. Walks them in date order."""
    status, since = "active", RULES_SINCE
    cur, hist = [], []
    for day in sorted({r[0] for r in rows}):
        want = ("p",) if status == "active" else ("p", "s")     # paused: plays already locked before the pause count too
        cur += [r[1] for r in rows if r[0] == day and r[2] in want and r[0] >= since]
        n, m, z = _stats(cur)
        if status == "active" and n >= POOL_PAUSE_N and m < 0 and z is not None and z <= POOL_Z:
            hist.append({"date": day, "to": "paused", "n": n, "ev": round(m, 2), "z": round(z, 2)})
            status, since, cur = "paused", day, []
            since = _next_day(day)
        elif status == "paused" and n >= POOL_RESTORE_N and m >= 0:
            hist.append({"date": day, "to": "active", "n": n, "ev": round(m, 2)})
            status, cur = "active", []
            since = _next_day(day)
    n, m, z = _stats(cur)
    return {"status": status, "since": since, "n": n, "ev": None if m is None else round(m, 2), "z": None if z is None else round(z, 2),
            "counts": "plays" if status == "active" else "shadow plays", "pause_n": POOL_PAUSE_N, "restore_n": POOL_RESTORE_N,
            "history": hist[-4:]}


def _next_day(day):
    from datetime import date, timedelta
    return (date.fromisoformat(day) + timedelta(days=1)).isoformat()


def pooled(gates_path=None, docs=None):
    """Pooled state of game plays across the five sports. gates_path: any sport's gates.json (used to find docs/)."""
    if docs is None:
        docs = Path(__file__).resolve().parent / "docs"
        if gates_path is not None:                     # walk up from .../docs/<sport>/data/gates.json to .../docs
            for par in Path(gates_path).resolve().parents:
                if par.name == "docs":
                    docs = par
                    break
    rows, by = [], {}
    for sport, rel in POOL_FILES.items():
        try:
            st = json.loads((Path(docs) / rel).read_text())
        except Exception:  # noqa: BLE001
            continue
        for name, g in st.items():
            if name in _GAME_GATES and isinstance(g, dict):
                rs = [r for r in g.get("ev_rows") or [] if len(r) == 3]
                rows += rs
                by[sport] = by.get(sport, 0) + len(rs)
    out = pooled_state(rows)
    out["by_sport"] = by
    return out
