"""
Cross-game alt-line parlays, shared by the NFL and NHL models (Oct 30 2026).

One 'alt down' leg from each of 3 different games (an alt spread like "NYK +10.5", or an alt total),
the kind of ticket a book sells as an alternate-spread parlay. Legs from different games don't move
together, so the ticket's chance is simply the legs' chances multiplied.

Leg chances come from Pinnacle's lines (altlines.team_legs: the model's simulated games re-weighted to
Pinnacle's no-vig spread and total), and the model must agree on the side. Then every leg gets the same
calibration shift on the log-odds scale:
  - before any results: a small safety haircut (PRIOR_SHIFT, about 1.5 points on an 80% leg). The same-game
    alt parlays ran legs about 4 points too confident (82.6% said, 78.5% hit), and that error compounds
    over 3 legs, so these start cautious;
  - as legs get graded, the shift moves to whatever makes the legs' predicted rate match their real hit
    rate, weighted n / (n + LEG_K).

Two tickets per slate: 'spreads' (alt spreads only, like a DraftKings alternate-spread parlay) and 'mix'
(at least one alt total, the rest spreads or totals). When the bet book posts all 3 legs, the ticket also shows the book's price
(cross-game parlays pay the legs' odds multiplied) and its expected return; it's flagged as a play only
when that return is at least MIN_EV.

Tickets lock the first time they're posted inside the lock window, or as soon as one of their games
starts, so the graded record is what was actually shown. State lives in one JSON file per sport.
"""
import itertools
import json
import math
from datetime import datetime, timezone

PRIOR_SHIFT = -0.10            # log-odds haircut on every leg before graded results take over
LEG_K = 60                     # graded legs at which the learned shift gets half the weight
LEG_RANGE = (0.72, 0.90)       # leg chance window, after the shift
ODDS = (-125, 125)             # fair odds window for the whole ticket
TARGET_P = 0.50                # ties go to the ticket closest to even money
N_LEGS = 3
PER_GAME = 6                   # best candidate legs kept per game and style
MIN_EV = 3.0                   # % return at the book's price to flag a ticket as a play
STYLES = {"spreads": ("spread",), "mix": ("spread", "total")}
RECENT = 12


def _implied(o):
    o = float(o)
    return 100 / (o + 100) if o > 0 else -o / (-o + 100)


def _dec(o):
    o = float(o)
    return 1 + (o / 100 if o > 0 else 100 / -o)


def _american(p):
    p = min(max(p, 1e-4), 1 - 1e-4)
    return round(-100 * p / (1 - p)) if p >= 0.5 else round(100 * (1 - p) / p)


def _amer_from_dec(d):
    return round((d - 1) * 100) if d >= 2 else round(-100 / (d - 1))


def fmt(o):
    if o is None:
        return None
    o = int(round(float(o)))
    return f"+{o}" if o > 0 else str(o)


def _logit(p):
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def _sig(x):
    return 1 / (1 + math.exp(-x))


def _ts(x):
    if not x:
        return None
    try:
        t = datetime.fromisoformat(str(x).replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


# ---------------------------------------------------------------------
# calibration
# ---------------------------------------------------------------------
def shift_from(record):
    """Log-odds shift for every leg: the prior haircut, handing over to the graded record as it grows."""
    n = record.get("legs_n") or 0
    m, a = (record.get("legs_model") or 0) / 100, (record.get("legs_actual") or 0) / 100
    w = n / (n + LEG_K)
    learned = (_logit(a) - _logit(m)) if n and 0 < m < 1 and 0 < a < 1 else 0.0
    return round(PRIOR_SHIFT * (1 - w) + learned * w, 4)


# ---------------------------------------------------------------------
# building
# ---------------------------------------------------------------------
def _book_odds(leg, book_rows):
    for b in book_rows or []:
        if (b.get("market") == leg["market"] and b.get("side") == leg["side"] and b.get("odds") is not None
                and abs(float(b.get("line") or 0) - float(leg["line"])) < 1e-6
                and (leg["market"] != "team_total" or b.get("team") == leg.get("team"))):
            return float(b["odds"])
    return None


def candidates(slate_games, shift, style):
    """Per game: legs of the style's markets inside LEG_RANGE after the shift, most model agreement first."""
    out = []
    for g in slate_games:
        rows = []
        for L in g["legs"]:
            if L["market"] not in STYLES[style]:
                continue
            p = _sig(_logit(L["p"]) + shift)
            if not (LEG_RANGE[0] <= p <= LEG_RANGE[1]):
                continue
            bo = _book_odds(L, g.get("book_rows"))
            rows.append({"game_id": g["game_id"], "matchup": g["matchup"], "start": g.get("start"),
                         "market": L["market"], "team": L.get("team_side") or L.get("team"), "side": L["side"],
                         "line": float(L["line"]), "label": L["label"],
                         "p": p, "p_pin": float(L["p"]), "p_model": float(L.get("p_model") or L["p"]),
                         "book_odds": bo})
        rows.sort(key=lambda x: -(x["p_model"] - x["p_pin"]))
        if rows:
            out.append(rows[:PER_GAME])
    return out


def build(slate_games, shift, style, book_name=None):
    """The best 3-leg ticket for one slate: fair odds in ODDS; the best expected return at the book's price
    when every leg is posted, otherwise the most model agreement; even money breaks ties."""
    per_game = candidates(slate_games, shift, style)
    if len(per_game) < N_LEGS:
        return None
    p_lo, p_hi = _implied(ODDS[1]), _implied(ODDS[0])
    best = None
    for games in itertools.combinations(per_game, N_LEGS):
        for legs in itertools.product(*games):
            if style == "mix" and all(L["market"] == "spread" for L in legs):
                continue                                            # the mix carries at least one total (else it's the spreads ticket)
            p = math.prod(L["p"] for L in legs)
            if not (p_lo <= p <= p_hi):
                continue
            agree = sum(L["p_model"] - L["p_pin"] for L in legs)
            priced = all(L["book_odds"] is not None for L in legs)
            ev = 100 * (p * math.prod(_dec(L["book_odds"]) for L in legs) - 1) if priced else None
            score = (1 if priced else 0, ev if priced else agree, -abs(p - TARGET_P))
            if best is None or score > best[0]:
                best = (score, legs, p, ev)
    if not best:
        return None
    _, legs, p, ev = best
    legs = sorted(legs, key=lambda L: L.get("start") or "")
    dec_book = math.prod(_dec(L["book_odds"]) for L in legs) if ev is not None else None
    return {
        "style": style, "legs": [{**{k: L[k] for k in ("game_id", "matchup", "start", "market", "team", "side", "line", "label")},
                                  "p": round(100 * L["p"], 1), "p_pin": round(100 * L["p_pin"], 1),
                                  "p_model": round(100 * L["p_model"], 1), "book_odds": fmt(L["book_odds"])} for L in legs],
        "p": round(100 * p, 1), "fair": fmt(_american(p)),
        "min_odds": fmt(_amer_from_dec((1 + MIN_EV / 100) / p)),     # price needed for a MIN_EV return
        "book": book_name if ev is not None else None, "book_odds": fmt(_amer_from_dec(dec_book)) if dec_book else None,
        "ev": None if ev is None else round(ev, 1), "play": bool(ev is not None and ev >= MIN_EV),
        "shift": shift,
    }


# ---------------------------------------------------------------------
# grading and tracking
# ---------------------------------------------------------------------
def grade_leg(L, hs, as_):
    """True (win), False (loss) or None (push) for a half-point alt line."""
    if L["market"] == "spread":
        m = (hs - as_) if L["side"] == "home" else (as_ - hs)
        v = m + float(L["line"])
    elif L["market"] == "total":
        v = (hs + as_ - float(L["line"])) * (1 if L["side"] == "over" else -1)
    else:
        sc = hs if L.get("team") == "home" else as_
        v = (sc - float(L["line"])) * (1 if L["side"] == "over" else -1)
    return None if abs(v) < 1e-9 else v > 0


def grade(state, finals):
    """Settle locked tickets whose games are all final. finals: {game_id: (home score, away score)}."""
    for t in state["tickets"].values():
        if t.get("result") or not t.get("locked_at"):
            continue
        res = []
        for L in t["legs"]:
            f = finals.get(str(L["game_id"]))
            if f is None:
                break
            L["hit"] = grade_leg(L, float(f[0]), float(f[1]))
            res.append(L["hit"])
        else:
            live = [x for x in res if x is not None]                # a pushed leg drops out, as at the book
            t["result"] = "W" if live and all(live) else "L" if False in live else "P"
            t["legs_hit"] = sum(1 for x in res if x)


def tracking(state):
    rows = [t for t in state["tickets"].values() if t.get("result") in ("W", "L")]
    legs = [L for t in state["tickets"].values() if t.get("result") for L in t["legs"] if L.get("hit") is not None]
    out = {"n": len(rows), "hits": sum(1 for t in rows if t["result"] == "W"),
           "model": round(sum(t["p"] for t in rows) / len(rows), 1) if rows else None,
           "actual": round(100 * sum(1 for t in rows if t["result"] == "W") / len(rows), 1) if rows else None,
           "legs_n": len(legs), "legs_model": round(sum(L["p"] for L in legs) / len(legs), 1) if legs else None,
           "legs_actual": round(100 * sum(1 for L in legs if L["hit"]) / len(legs), 1) if legs else None}
    units, priced = 0.0, 0
    for t in rows:
        if t.get("book_odds"):
            priced += 1
            units += (_dec(t["book_odds"]) - 1) if t["result"] == "W" else -1.0
    out["book_units"], out["book_n"] = round(units, 2), priced
    by = {}
    for t in rows:
        b = by.setdefault(t["style"], {"n": 0, "hits": 0, "model": 0.0})
        b["n"] += 1
        b["hits"] += t["result"] == "W"
        b["model"] += t["p"]
    out["by_style"] = {k: {"n": v["n"], "hits": v["hits"], "model": round(v["model"] / v["n"], 1),
                           "actual": round(100 * v["hits"] / v["n"], 1)} for k, v in by.items()}
    done = sorted([t for t in state["tickets"].values() if t.get("result")], key=lambda t: t.get("slate") or "", reverse=True)
    out["recent"] = [{k: t.get(k) for k in ("slate", "style", "p", "fair", "book_odds", "result", "legs_hit")} |
                     {"legs": [{"label": L["label"], "matchup": L["matchup"], "hit": L.get("hit")} for L in t["legs"]]}
                     for t in done[:RECENT]]
    return out


# ---------------------------------------------------------------------
# one run
# ---------------------------------------------------------------------
def run(path, games, finals, now, lock_fn, book_name=None, log=None):
    """games: [{game_id, slate, start, matchup, legs (altlines.team_legs output), book_rows}] for games not yet
    started; finals: {game_id: (home, away)}; lock_fn(now, first_start) -> True inside the lock window.
    Returns the payload block for the site."""
    try:
        state = json.loads(path.read_text())
    except (OSError, ValueError):
        state = {"tickets": {}}
    ts = now.isoformat(timespec="minutes")
    for t in state["tickets"].values():                     # a ticket whose game has started is the one that was shown
        if not t.get("locked_at") and any((_ts(L.get("start")) or now) <= now for L in t["legs"]):
            t["locked_at"] = ts
    grade(state, finals)
    track = tracking(state)
    shift = shift_from(track)
    slates = {}
    for g in games:
        st = _ts(g.get("start"))
        if st is None or st <= now or not g.get("legs"):
            continue
        slates.setdefault(g["slate"], []).append({**g, "legs": [{k: v for k, v in L.items() if k != "hit"} for L in g["legs"]]})
    current = []
    for slate, sg in sorted(slates.items()):
        first = min(_ts(g["start"]) for g in sg)
        for style in STYLES:
            key = f"{slate}|{style}"
            old = state["tickets"].get(key)
            started = old and any((_ts(L.get("start")) or now) <= now for L in old["legs"])
            if old and (old.get("locked_at") or started):
                if not old.get("locked_at"):
                    old["locked_at"] = ts
                current.append(old)
                continue
            t = build(sg, shift, style, book_name)
            if t is None:
                state["tickets"].pop(key, None)
                continue
            t.update({"slate": slate, "posted_at": ts})
            if lock_fn(now, first):
                t["locked_at"] = ts
            state["tickets"][key] = t
            current.append(t)
    for key, t in state["tickets"].items():                 # slates already under way stay on the board until graded
        if not t.get("result") and t.get("locked_at") and t not in current:
            current.append(t)
    path.write_text(json.dumps(state, separators=(",", ":")))
    if log:
        log.info(f"cross-game parlays: {len(current)} tickets, leg shift {shift}, record {track.get('hits')}/{track.get('n')}")
    return {"tickets": sorted(current, key=lambda t: (t.get("slate") or "", t["style"])), "tracking": track,
            "rules": {"leg_range": [round(100 * x) for x in LEG_RANGE], "odds": [fmt(x) for x in ODDS], "legs": N_LEGS,
                      "min_ev": MIN_EV, "shift": shift, "prior_shift": PRIOR_SHIFT, "leg_k": LEG_K}}
