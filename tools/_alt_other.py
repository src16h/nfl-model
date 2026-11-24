"""NHL / NBA / CFB / Soccer part of tools/alt_parlay_check.py (runs on import). Run from the repo root."""
import json, glob, math, sys, collections
sys.path.insert(0, ".")
import numpy as np
import altlines as AL

sp = sys.argv[1]
recent = sys.argv[2] if len(sys.argv) > 2 else "2026-11-17"
R = json.load(open(f"docs/{sp}/data/results.json"))
NHL = {"sog": 0, "goals": 1, "assists": 2, "points": 3}
NBA = {"pts": 0, "reb": 1, "ast": 2, "fg3m": 3}
CFB = {"pass_yds": 0, "pass_td": 1, "rush_yds": 2, "rec_yds": 3, "rec": 4, "td": 5}


def payout(o):
    o = float(str(o).replace("+", ""))
    return o / 100 if o > 0 else 100 / -o


def leg_hit(L, g, res):
    if L.get("kind") == "team" or L.get("market"):
        if sp == "soccer":
            r_ = AL.grade(L, res["hg"], res["ag"])[0]
        else:
            r_ = AL.grade(L, res["h"], res["a"])[0]
        return None if r_ == "P" else r_ in ("W", "HW")
    st = res["p"].get(str(L["pid"]))
    if st is None:
        return None
    if sp == "nhl":
        v = st[0] if L["stat"] == "saves" else st[NHL[L["stat"]]]
    elif sp == "nba":
        v = st[0] + st[1] + st[2] if L["stat"] == "pra" else st[NBA[L["stat"]]]
    else:
        v = st[CFB[L["stat"]]]
    return v < L["line"] if L.get("side") in ("Under", "under") and not L.get("market") else v > L["line"]


def typ(L):
    if L.get("kind") == "team" or L.get("market"):
        return f"team {L.get('market')} {L.get('side') if L.get('market') in ('total', 'team_total', 'btts') else ''}".strip()
    return f"{L.get('pos', '') or ''} {L['stat']} {L.get('side', 'Over')}".strip()


tickets = []
for f in sorted(glob.glob(f"docs/{sp}/data/history/*.json")):
    d = json.load(open(f))
    day = d.get("date") or f.split("/")[-1][:-5]
    for g in d.get("games", []):
        res = R.get(str(g["game_id"]))
        if not res:
            continue
        for k in ("alt_parlay", "alt_mix", "alt_ladder"):
            ap = g.get(k)
            if not ap or not ap.get("legs"):
                continue
            v = ap.get("v", 1)
            kind = {"alt_parlay": "alt", "alt_mix": "alt_mix", "alt_ladder": "alt_ladder"}[k]
            if sp == "nhl" and k == "alt_parlay":
                kind = "alt" if v in (3, 4) else ("alt_hr" if v == 2 else ("alt_old" if v < 2 else f"alt_v{v}"))
            legs = [{"typ": typ(L), "p": L["p"] / 100, "hit": leg_hit(L, g, res), "line": L.get("line"), "main": L.get("main"),
                     "team": L.get("team"), "stat": L.get("stat")} for L in ap["legs"]]
            tickets.append({"day": day, "kind": kind, "v": v, "p": ap["p"] / 100, "pi": (ap.get("pi") or ap["p"]) / 100,
                            "fair": ap.get("fair"), "legs": legs, "graded": all(l["hit"] is not None for l in legs),
                            "hit": all(l["hit"] for l in legs if l["hit"] is not None)})


def z(h, s, n):
    return (h - s) / math.sqrt(max(s * (1 - s), 1e-9) / n)


def line(name, rows):
    n = len(rows)
    if not n:
        return f"{name}: 0"
    s = np.mean([r["p"] for r in rows]); h = np.mean([bool(r["hit"]) for r in rows])
    return f"{name}: n={n} said {100*s:.1f} hit {100*h:.1f} gap {100*(h-s):+.1f} z {z(h,s,n):+.2f}"


G = [t for t in tickets if t["graded"]]
print(f"#### {sp}: tickets built {len(tickets)}, graded {len(G)} (recent = since {recent})")
for kind in sorted({t["kind"] for t in G}):
    T = [t for t in G if t["kind"] == kind]
    fair = [t for t in T if t["fair"]]
    u = sum((payout(t["fair"]) if t["hit"] else -1) for t in fair)
    print(line(kind, T), f"| units fair {u:+.2f} ({100*u/max(1,len(fair)):+.1f}%) |", line("recent", [t for t in T if t["day"] >= recent]))
legs = [dict(l, day=t["day"], kind=t["kind"]) for t in tickets for l in t["legs"] if l["hit"] is not None]
print(line("legs all", legs), "|", line("recent", [l for l in legs if l["day"] >= recent]))
bt = collections.defaultdict(list)
for l in legs:
    bt[l["typ"]].append(l)
print("-- legs by type")
for k, v in sorted(bt.items(), key=lambda kv: -len(kv[1])):
    print("  ", line(k, v), "|", line("recent", [x for x in v if x["day"] >= recent]))
print("-- legs by said band")
for lo, hi in ((0, .7), (.7, .75), (.75, .8), (.8, .85), (.85, .9), (.9, 1.01)):
    print("  ", line(f"{lo}-{hi}", [l for l in legs if lo <= l["p"] < hi]))
pl = [l for l in legs if l.get("main") and l.get("line") is not None and not l["typ"].startswith("team")]
if pl:
    print("-- player legs by rungs below the book main (main - line)")
    for lo, hi in ((0, 1.01), (1.01, 2.01), (2.01, 5.01), (5.01, 15.01), (15.01, 999)):
        print("  ", line(f"{lo}-{hi}", [l for l in pl if lo <= l["main"] - l["line"] < hi]))
print("-- tickets by leg count")
for n in sorted({len(t["legs"]) for t in G}):
    print("  ", line(f"{n} legs", [t for t in G if len(t["legs"]) == n]))
print("-- tickets by fair price")
for lo, hi in ((-999, -120), (-120, 100), (100, 125), (125, 999)):
    print("  ", line(f"{lo}..{hi}", [t for t in G if t["fair"] and lo <= float(str(t["fair"]).replace("+", "")) < hi]))
print("-- correlation (real leg-type rates)")
rate = {k: np.mean([bool(x["hit"]) for x in v]) for k, v in bt.items()}
for kind in sorted({t["kind"] for t in G}):
    T = [t for t in G if t["kind"] == kind]
    prod_real = np.mean([np.prod([rate[l["typ"]] for l in t["legs"]]) for t in T])
    miss = collections.Counter(sum(1 for l in t["legs"] if not l["hit"]) for t in T)
    exp = collections.Counter()
    for t in T:
        dist = np.array([1.0])
        for l in t["legs"]:
            dist = np.convolve(dist, [rate[l["typ"]], 1 - rate[l["typ"]]])
        for k_, pr in enumerate(dist):
            exp[k_] += pr
    print(f"  {kind}: n={len(T)} said {100*np.mean([t['p'] for t in T]):.1f} model-indep {100*np.mean([t['pi'] for t in T]):.1f} "
          f"real-type product {100*prod_real:.1f} hit {100*np.mean([t['hit'] for t in T]):.1f}; misses {dict(sorted(miss.items()))} "
          f"vs indep {({k_: round(v_, 1) for k_, v_ in sorted(exp.items()) if v_ >= 0.05})}")
pairs = both = 0; eb = 0.0
for t in G:
    L = t["legs"]
    for i in range(len(L)):
        for j in range(i + 1, len(L)):
            if L[i]["team"] and L[i]["team"] == L[j]["team"]:
                pairs += 1; both += (not L[i]["hit"]) and (not L[j]["hit"]); eb += (1 - rate[L[i]["typ"]]) * (1 - rate[L[j]["typ"]])
print(f"  same-team pairs {pairs}: both missed {both}, independent {eb:.1f}")
print("-- out of sample (days walk-forward; types judged on earlier days, 15+ legs, gap >= -3)")
res = collections.defaultdict(list)
days = sorted({t["day"] for t in G})
for dday in days:
    prior = [l for l in legs if l["day"] < dday]
    pt = collections.defaultdict(list)
    for l in prior:
        pt[l["typ"]].append(l)
    ok = {k for k, v in pt.items() if len(v) >= 15 and np.mean([bool(x["hit"]) for x in v]) - np.mean([x["p"] for x in v]) >= -0.03}
    for t in [t for t in G if t["day"] == dday]:
        if len(prior) < 40:
            continue
        u = (payout(t["fair"]) if t["hit"] else -1) if t["fair"] else None
        res["on-target types only" if all(l["typ"] in ok for l in t["legs"]) else "has weak/new type"].append((t["hit"], u, t["p"]))
        res["<=3 legs" if len(t["legs"]) <= 3 else "4+ legs"].append((t["hit"], u, t["p"]))
for k, v in sorted(res.items()):
    us = [x[1] for x in v if x[1] is not None]
    print(f"  {k}: n={len(v)} said {100*np.mean([x[2] for x in v]):.1f} hit {100*np.mean([x[0] for x in v]):.1f} "
          f"units fair {sum(us):+.2f} ({100*sum(us)/max(1,len(us)):+.1f}%)")
