"""
Nov 5 2026: replays this season's graded NFL props with the weather shift in the player sims (players.wx_shift).
For each graded prop in an outdoor game, the stored simulated distribution is scaled by the game's weather
factor and the model's chance re-read at the book line. Compares Brier score and lean record, old vs new.
"""
import json, glob, re, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nflmodel.geo import player_weather
from nflmodel.players import wx_shift
from nflmodel import config as C

L = json.load(open("docs/data/props_log.json"))["props"]
G, PL = {}, {}
for f in sorted(glob.glob("docs/data/history/2026_week*.json")):
    D = json.load(open(f))
    for g in D["games"]:
        G[g["game_id"]] = g
    for p in D.get("players", []):
        PL[(p["game_id"], p["pid"])] = p

def wx_of(s):
    if not s or s == "Indoors":
        return None
    t = re.search(r"(-?\d+)°F", s); w = re.search(r"wind (\d+)", s); r = re.search(r"(\d+)% (rain|snow)", s)
    mm = re.search(r"([\d.]+) mm/hr", s)
    return {"temp": float(t.group(1)) if t else 60, "wind": float(w.group(1)) if w else 0,
            "precip": float(r.group(1)) if r else 0, "rain_mm": float(mm.group(1)) if mm else None}

QL = np.linspace(0.02, 0.98, 25)
def p_over(mk, line):
    """P(X > line) from a stored market: quantiles q, or ge = P(X >= k)."""
    if "q" in mk and mk["q"]:
        q = np.asarray(mk["q"], float)
        if line <= q[0]: return 1 - 0.02 * line / max(q[0], 1e-9)
        if line >= q[-1]: return 0.02 * max(0, 1 - (line - q[-1]) / max(q[-1], 1))
        return 1 - float(np.interp(line, q, QL))
    if "ge" in mk and mk["ge"]:
        ge = np.asarray(mk["ge"], float); ge = ge / 100 if ge.max() > 1.5 else ge
        k = int(np.floor(line)) + 1                       # P(X >= floor(line)+1)
        lo = k - 1
        if lo + 1 >= len(ge): return 0.0
        return float(ge[k]) if k < len(ge) else 0.0
    return None

FACT = {"pass_yds": "py", "rec_yds": "py", "rec": "cmp", "pass_cmp": "cmp", "pass_att": "att",
        "rush_yds": "car", "carries": "car", "rush_rec_yds": "mix"}
rows = []
for k, v in L.items():
    r = v.get("result") or {}
    if r.get("outcome") not in ("Over", "Under") or v.get("stat") not in FACT or v.get("line") in (None, ""):
        continue
    g = G.get(v["game_id"]); p = PL.get((v["game_id"], v["pid"]))
    if not g or not p:
        continue
    s = wx_shift(player_weather(wx_of(g.get("weather")), g.get("weather") == "Indoors"))
    f = {"py": 1 + s["pyds"] / (C.WX_LG_ATT * C.WX_LG_YPA),
         "cmp": (C.WX_LG_ATT + s["att"]) * (C.WX_LG_CMP + s["cmp"]) / (C.WX_LG_ATT * C.WX_LG_CMP),
         "att": (C.WX_LG_ATT + s["att"]) / C.WX_LG_ATT, "car": (24.9 + s["car"]) / 24.9}
    f["mix"] = 0.5 * (f["py"] + f["car"])
    fac = f[FACT[v["stat"]]]
    mk = (p.get("markets") or {}).get(v["stat"])
    line = float(v["line"])
    if mk is None or fac == 1.0:
        new = None
    else:
        po, pn = p_over(mk, line), p_over(mk, line / fac)
        new = None if po is None or pn is None else v["model_over"] / 100 + (pn - po)
    hit = 1.0 if r["outcome"] == "Over" else 0.0
    rows.append(dict(game=v["game_id"], stat=v["stat"], wx=g.get("weather"), pyds=s["pyds"], fac=fac, line=line,
                     old=v["model_over"] / 100, new=new if new is None else min(max(new, 0.01), 0.99),
                     book=v["book_over"] / 100, hit=hit, lean=v.get("lean")))

wxr = [x for x in rows if x["new"] is not None and x["pyds"] <= -3]
print(f"graded yardage/count props: {len(rows)}, in weather games (>=3 pass yds lost per team): {len(wxr)} across {len({x['game'] for x in wxr})} games")
if wxr:
    b = lambda key: np.mean([(x[key] - x["hit"]) ** 2 for x in wxr])
    print(f"Brier (lower is better): book {b('book'):.4f} | model before {b('old'):.4f} | model with weather {b('new'):.4f}")
    gap = min(abs(x["old"] - x["book"]) for x in rows if x["lean"]) if any(x["lean"] for x in rows) else 0.05
    def rec(key):
        w = l = 0
        for x in wxr:
            d = x[key] - x["book"]
            if abs(d) < gap: continue
            win = (d > 0) == (x["hit"] == 1)
            w += win; l += (not win)
        return w, l
    for key, nm in (("old", "before"), ("new", "with weather")):
        w, l = rec(key); print(f"lean record {nm:13s}: {w}-{l}" + (f" ({100*w/(w+l):.0f}%)" if w + l else ""))
    ov = [x for x in wxr if x["stat"] in ("pass_yds", "rec_yds", "rec", "pass_cmp", "pass_att")]
    print(f"passing/receiving Overs hit {sum(x['hit'] for x in ov):.0f} of {len(ov)} ({100*np.mean([x['hit'] for x in ov]):.0f}%) in these games; book expected {100*np.mean([x['book'] for x in ov]):.0f}%, model before {100*np.mean([x['old'] for x in ov]):.0f}%, with weather {100*np.mean([x['new'] for x in ov]):.0f}%")
    by = {}
    for x in wxr: by.setdefault((x["game"], x["wx"], round(x["pyds"])), []).append(x)
    for (gm, w, py), xs in sorted(by.items(), key=lambda t: t[0][2]):
        print(f"  {gm:18s} {w:38s} pass yds {py:+4d}  props {len(xs)}")
