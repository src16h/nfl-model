"""NFL part of tools/alt_parlay_check.py (runs on import). Run from the repo root."""
import json, math, sys, collections
from pathlib import Path
sys.path.insert(0, ".")
import numpy as np
from nflmodel import tracker

R = json.load(open("docs/data/results.json"))
cols = R["cols"]; rg = R["games"]; rp = R["players"]

def am(o):
    o = float(str(o).replace("+", ""))
    return 100 / (o + 100) if o > 0 else -o / (-o + 100)

def payout(o):  # profit per unit at American odds
    o = float(str(o).replace("+", ""))
    return o / 100 if o > 0 else 100 / -o

tickets = []
for f in sorted(Path("docs/data/history").glob("2026_week*.json")):
    d = json.load(open(f)); wk = int(d["week"])
    proj = {(p["game_id"], p["pid"]): p for p in d.get("players", [])}
    for hg in d["games"]:
        g = rg.get(hg["game_id"])
        if not g:
            continue
        pl = rp.get(hg["game_id"], {})
        for kind in ("alt_parlay", "alt_mix", "alt_ladder"):
            ap = hg.get(kind)
            if not ap or not ap.get("legs"):
                continue
            legs = []
            for L in ap["legs"]:
                h = tracker._leg_hit(L, g, pl, cols, set(), hg["game_id"])
                pr = proj.get((hg["game_id"], L.get("pid")))
                med = None
                if pr and L.get("stat") in (pr.get("markets") or {}):
                    med = (pr["markets"][L["stat"]] or {}).get("med")
                typ = (f"{L.get('pos')} {L.get('stat')} {L.get('side')}" if L.get("kind") == "player" else f"team {L.get('market', L.get('kind'))}")
                legs.append({"typ": typ, "p": L["p"] / 100, "hit": h, "line": L.get("line"), "main": L.get("main"), "med": med,
                             "team": L.get("team"), "pid": L.get("pid"), "stat": L.get("stat"), "pos": L.get("pos")})
            tickets.append({"wk": wk, "kind": kind, "v": ap.get("v", 1), "p": ap["p"] / 100, "pi": (ap.get("pi") or ap["p"]) / 100,
                            "fair": ap.get("fair"), "bet_at": ap.get("bet_at"), "legs": legs,
                            "graded": all(l["hit"] is not None for l in legs), "hit": all(l["hit"] for l in legs if l["hit"] is not None),
                            "game": hg["game_id"]})

def z(hit, said, n):
    se = math.sqrt(max(said * (1 - said), 1e-9) / n)
    return (hit - said) / se

def line(name, rows, pkey="p", hkey="hit"):
    n = len(rows)
    if not n:
        return f"{name}: 0"
    s = np.mean([r[pkey] for r in rows]); h = np.mean([bool(r[hkey]) for r in rows])
    return f"{name}: n={n} said {100*s:.1f} hit {100*h:.1f} gap {100*(h-s):+.1f} z {z(h,s,n):+.2f}"

G = [t for t in tickets if t["graded"]]
print("tickets built", len(tickets), "graded", len(G))
for kind in ("alt_parlay", "alt_mix", "alt_ladder"):
    T = [t for t in G if t["kind"] == kind]
    print(line(kind, T))
    for v in sorted({t["v"] for t in T}, key=str):
        print("   ", line(f"v{v}", [t for t in T if t["v"] == v]))
    for wk in sorted({t["wk"] for t in T}):
        print("   ", line(f"wk{wk}", [t for t in T if t["wk"] == wk]))
    fair = [t for t in T if t["fair"]]
    u = sum((payout(t["fair"]) if t["hit"] else -1) for t in fair)
    print(f"    units at fair {u:+.2f} over {len(fair)} ({100*u/max(1,len(fair)):+.1f}%)")

AP = [t for t in G if t["kind"] == "alt_parlay"]
ALL = G
print("\n== legs (alt_parlay tickets, every graded leg incl. tickets with ungraded legs)")
legs = [l for t in tickets if t["kind"] == "alt_parlay" for l in t["legs"] if l["hit"] is not None]
print(line("legs", legs))
print(line("legs wk11", [l for t in tickets if t["kind"] == "alt_parlay" and t["wk"] == 11 for l in t["legs"] if l["hit"] is not None]))
print("\n== legs by type, all ticket kinds")
legs_all = [dict(l, wk=t["wk"], kind=t["kind"]) for t in tickets for l in t["legs"] if l["hit"] is not None]
bt = collections.defaultdict(list)
for l in legs_all:
    bt[l["typ"]].append(l)
for k, v in sorted(bt.items(), key=lambda kv: -len(kv[1])):
    print("  ", line(k, v), "| wk11:", line("", [x for x in v if x["wk"] == 11]))
print("\n== legs by said band")
for lo, hi in ((0.6, .75), (.75, .8), (.8, .85), (.85, .9), (.9, 1.01)):
    print("  ", line(f"{lo}-{hi}", [l for l in legs_all if lo <= l["p"] < hi]))
print("\n== legs by line / model median (player legs, Over)")
ov = [l for l in legs_all if l["med"] and l["typ"].endswith("Over") and l["line"] is not None]
for lo, hi in ((0, .5), (.5, .65), (.65, .8), (.8, 2)):
    print("  ", line(f"line/med {lo}-{hi}", [l for l in ov if lo <= l["line"] / l["med"] < hi]))
print("== legs by line / book main (player legs, Over)")
ovm = [l for l in legs_all if l["main"] and l["typ"].endswith("Over") and l["line"] is not None]
for lo, hi in ((0, .5), (.5, .65), (.65, .8), (.8, 2)):
    print("  ", line(f"line/main {lo}-{hi}", [l for l in ovm if lo <= l["line"] / l["main"] < hi]))
print("== model median vs book main (Over legs): med above main by")
for lo, hi in ((-99, 0), (0, .05), (.05, .15), (.15, 9)):
    print("  ", line(f"(med-main)/main {lo}-{hi}", [l for l in ov if l["main"] and lo <= (l["med"] - l["main"]) / l["main"] < hi]))

print("\n== tickets by leg count (all kinds)")
for n in sorted({len(t["legs"]) for t in G}):
    T = [t for t in G if len(t["legs"]) == n]
    print("  ", line(f"{n} legs", T), "| alt_parlay:", line("", [t for t in T if t["kind"] == "alt_parlay"]))
T4 = [t for t in G if len(t["legs"]) >= 4]
print("  ", line("4+ legs all kinds", T4)); print("  ", line("4+ legs since wk10", [t for t in T4 if t["wk"] >= 10]))
print("  ", line("4+ legs wk11", [t for t in T4 if t["wk"] == 11]))
print("\n== tickets by fair price")
for lo, hi in ((-999, -120), (-120, 100), (100, 125), (125, 999)):
    T = [t for t in G if t["fair"] and lo <= float(str(t["fair"]).replace("+", "")) < hi]
    print("  ", line(f"fair {lo}..{hi}", T))

print("\n== correlation")
# product of legs' said p, product of legs' real type rate (leave-one-out-ish: full sample), model's own pi
rate = {k: np.mean([bool(x["hit"]) for x in v]) for k, v in bt.items()}
for kind in ("alt_parlay", "alt_mix", "alt_ladder"):
    T = [t for t in G if t["kind"] == kind]
    if not T:
        continue
    prod_said = np.mean([np.prod([l["p"] for l in t["legs"]]) for t in T])
    prod_real = np.mean([np.prod([rate[l["typ"]] for l in t["legs"]]) for t in T])
    print(f"  {kind}: n={len(T)} model joint {100*np.mean([t['p'] for t in T]):.1f}, said-legs product {100*prod_said:.1f}, "
          f"model pi {100*np.mean([t['pi'] for t in T]):.1f}, real-type product {100*prod_real:.1f}, hit {100*np.mean([t['hit'] for t in T]):.1f}")
    miss = collections.Counter(sum(1 for l in t["legs"] if not l["hit"]) for t in T)
    # expected miss distribution if independent at real-type rates (Poisson-binomial)
    exp = collections.Counter()
    for t in T:
        dist = np.array([1.0])
        for l in t["legs"]:
            q = rate[l["typ"]]
            dist = np.convolve(dist, [q, 1 - q])
        for k, pr in enumerate(dist):
            exp[k] += pr
    print("     misses per ticket actual", dict(sorted(miss.items())), "independent", {k: round(v, 1) for k, v in sorted(exp.items())})
# same-team pairs
pairs_n = both = 0; expb = 0.0
for t in G:
    L = t["legs"]
    for i in range(len(L)):
        for j in range(i + 1, len(L)):
            if L[i]["team"] and L[i]["team"] == L[j]["team"]:
                pairs_n += 1; both += (not L[i]["hit"]) and (not L[j]["hit"])
                expb += (1 - rate[L[i]["typ"]]) * (1 - rate[L[j]["typ"]])
print(f"  same-team leg pairs {pairs_n}: both missed {both}, expected if independent {expb:.1f}")
# QB pass yds leg + same-team receiver leg
qb_rec = [(t, a, b) for t in G for a in t["legs"] for b in t["legs"] if a is not b and a["stat"] == "pass_yds" and b["stat"] in ("rec", "rec_yds") and a["team"] == b["team"]]
print(f"  QB yds + same-team receiving leg pairs {len(qb_rec)}: QB miss {sum(not a['hit'] for _,a,_ in qb_rec)}, both miss {sum((not a['hit']) and (not b['hit']) for _,a,b in qb_rec)}")

print("\n== out of sample: walk-forward by week (types judged on earlier weeks only)")
weeks = sorted({t["wk"] for t in G})
res = collections.defaultdict(list)
for wk in weeks:
    prior = [l for l in legs_all if l["wk"] < wk]
    if len(prior) < 40:
        continue
    pt = collections.defaultdict(list)
    for l in prior:
        pt[l["typ"]].append(l)
    ok = {k for k, v in pt.items() if len(v) >= 15 and np.mean([bool(x["hit"]) for x in v]) - np.mean([x["p"] for x in v]) >= -0.03}
    for t in [t for t in G if t["wk"] == wk]:
        on = all(l["typ"] in ok for l in t["legs"])
        u = (payout(t["fair"]) if t["hit"] else -1) if t["fair"] else None
        res["on-target only" if on else "has weak/unknown type"].append((t["hit"], u, t["p"]))
        res["<=3 legs" if len(t["legs"]) <= 3 else "4+ legs"].append((t["hit"], u, t["p"]))
for k, v in res.items():
    us = [x[1] for x in v if x[1] is not None]
    print(f"  {k}: n={len(v)} hit {100*np.mean([x[0] for x in v]):.1f} said {100*np.mean([x[2] for x in v]):.1f} units fair {sum(us):+.2f} ({100*sum(us)/max(1,len(us)):+.1f}%)")

json.dump([{k: v for k, v in t.items()} for t in tickets], open(sys.argv[1] if len(sys.argv) > 1 else "/dev/null", "w"), default=str)
