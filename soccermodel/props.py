"""
Player props: anytime goalscorer and shots on target.

Each player's scoring and shooting rate per 90 minutes comes from ESPN box scores (recent matches
count more), pulled toward his position's league average until he has PLAYER_PRIOR_MIN minutes.
Expected minutes come from how often he started or came off the bench in his team's recent
matches. The match model's expected goals for his team then scale him up or down: a striker
facing a weak defence gets more.

Most books void these bets when the player doesn't play, so chances are given *if he plays*,
mixing a start and a bench appearance by how often each has happened.
"""
import json
import math
from datetime import date, timedelta

import numpy as np

from . import config as C
from . import data as D


def pos_group(abbr):
    a = (abbr or "").upper()
    if a == "G" or a == "GK":
        return "G"
    if a in ("F", "CF", "ST", "LW", "RW", "W", "CF-L", "CF-R", "SS") or a.startswith("CF"):
        return "F"
    if "M" in a:
        return "M"
    if "D" in a or "B" in a:
        return "D"
    return "M"


def pois_ge(lam, k_max=4):
    """[P(X>=0), P(X>=1), ... P(X>=k_max)] for a Poisson mean."""
    p = [math.exp(-lam) * lam ** k / math.factorial(k) for k in range(k_max)]
    out, acc = [1.0], 0.0
    for k in range(k_max):
        acc += p[k]
        out.append(max(0.0, 1 - acc))
    return out


def recent_boxes(league, start: date, end: date):
    """Finished ESPN matches with box scores between two dates, oldest first. Past scoreboard days are cached."""
    games = []
    d = start
    while d <= end:
        path = D.CACHE / "espn_days" / f"{league}_{d:%Y%m%d}.json"
        if path.exists():
            day = json.loads(path.read_text())
        else:
            day = D.espn_day(league, d)
            if d < end - timedelta(days=1) and all(g["completed"] or g["state"] == "post" for g in day):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(day, separators=(",", ":")))
        games += [g for g in day if g["completed"]]
        d += timedelta(days=1)
    seen, out = set(), []
    for g in sorted(games, key=lambda x: x["start"]):
        if g["event_id"] in seen:
            continue
        seen.add(g["event_id"])
        box = D.espn_box(league, g["event_id"])
        if box and box.get("players"):
            out.append({**g, "players": box["players"]})
    return out


def player_rates(boxes):
    """Per team: ordered match list, and per player: weighted per-90 goals and shots on target, start and bench shares."""
    team_games = {}
    for g in boxes:
        for t in (g["home"], g["away"]):
            team_games.setdefault(t, []).append(g)
    # position priors (per 90), league-wide, unweighted
    pri = {}
    for g in boxes:
        for p in g["players"]:
            s = pri.setdefault(pos_group(p["pos"]), [0.0, 0.0, 0.0])
            s[0] += p["min"]; s[1] += p["goals"]; s[2] += p["sot"]
    prior = {k: {"g90": 90 * v[1] / max(v[0], 1), "sot90": 90 * v[2] / max(v[0], 1)} for k, v in pri.items()}
    players, teams = {}, {}
    for t, gl in team_games.items():
        gl = gl[-38:]                                          # about a season of the team's matches
        n = len(gl)
        gf = []
        for i, g in enumerate(gl):
            w = C.PLAYER_DECAY ** (n - 1 - i)
            tp = [p for p in g["players"] if p["team"] == t]
            gf.append((w, sum(p["goals"] for p in tp)))
            for p in tp:
                r_ = players.setdefault(p["pid"], {"pid": p["pid"], "name": p["name"], "team": t, "pos": p["pos"],
                                                   "w_min": 0.0, "w_g": 0.0, "w_sot": 0.0, "apps": []})
                r_["team"], r_["name"] = t, p["name"]
                if p["pos"] and p["pos"] != "SUB":
                    r_["pos"] = p["pos"]
                r_["w_min"] += w * p["min"]; r_["w_g"] += w * p["goals"]; r_["w_sot"] += w * p["sot"]
        recent = gl[-6:]
        for j, g in enumerate(recent):                       # start / bench shares over the last 6, recent first
            w = 0.8 ** (len(recent) - 1 - j)
            ids = {p["pid"]: p for p in g["players"] if p["team"] == t}
            for pid, r_ in players.items():
                if r_["team"] != t:
                    continue
                p = ids.get(pid)
                r_.setdefault("lw", []).append((w, 1 if p and p["start"] else (2 if p else 0)))
        teams[t] = {"gpg": sum(w * x for w, x in gf) / max(sum(w for w, _ in gf), 1e-9),
                    "last": gl[-1]["start"], "n": n}
    for r_ in players.values():
        grp = pos_group(r_["pos"])
        pr = prior.get(grp, {"g90": 0.1, "sot90": 0.4})
        k = C.PLAYER_PRIOR_MIN / 90
        m90 = r_["w_min"] / 90
        r_["g90"] = (r_["w_g"] + pr["g90"] * k) / (m90 + k)
        r_["sot90"] = (r_["w_sot"] + pr["sot90"] * k) / (m90 + k)
        lw = r_.get("lw", [])
        tw = sum(w for w, _ in lw) or 1
        r_["p_start"] = sum(w for w, s in lw if s == 1) / tw
        r_["p_sub"] = sum(w for w, s in lw if s == 2) / tw
        r_["last_app"] = bool(lw and lw[-1][1])
        r_["grp"] = grp
    return players, teams


def match_props(fx, lam_team, players, teams, event_id, opp):
    """Props for one team in one fixture. lam_team: model expected goals for that team."""
    t = fx
    tm = teams.get(t)
    if not tm:
        return []
    factor = lam_team / max(0.5 * tm["gpg"] + 0.5 * lam_team, 0.2)   # this match vs the team's usual output (shrunk)
    out = []
    for r_ in players.values():
        if r_["team"] != t or r_["grp"] == "G":
            continue
        ps, pb = r_["p_start"], r_["p_sub"]
        if ps + pb < 0.25:
            continue
        play = ps + pb
        mix = [(ps / play, C.START_MIN), (pb / play, C.SUB_MIN)]
        res = {}
        for st, rate, fx_pow in (("goal", r_["g90"], 1.0), ("sot", r_["sot90"], 0.7)):
            f = factor ** fx_pow
            ge = np.zeros(5)
            mean = 0.0
            for w, mins in mix:
                lam = rate * mins / 90 * f
                ge += w * np.array(pois_ge(lam))
                mean += w * lam
            ge = [round(float(x), 4) for x in ge]
            fair = 0.5 if st == "goal" or ge[1] < 0.5 or ge[2] < 0.35 else 1.5
            res[st] = {"mean": round(mean, 3), "ge": ge, "fair": fair}
        out.append({"pid": r_["pid"], "name": r_["name"], "team": t, "opp": opp, "pos": r_["pos"], "game_id": event_id,
                    "p_start": round(ps, 2), "p_play": round(play, 2), "m": res})
    out.sort(key=lambda x: -x["m"]["goal"]["ge"][1])
    return out[:14]
