"""
Does the per-stat prop bias (betrules.bias_table) help on weeks it has not seen?

    python tools/prop_bias_check.py

For each NFL week, the bias is fitted on earlier weeks only and scored on that week: log loss of the book's
no-vig chance with and without the shift, and what betting every Under at the posted price returned.
A shift that only chases a streak makes the log loss worse out of sample.

Nov 11 2026 (weeks 5-9): rushing yards 0.6923 -> 0.6840 over 380 props, every Under 221-159 (+9.9%), ahead in
4 of 5 weeks and flat in week 9. Receiving yards, passing yards and receptions: no gain (shifts near zero).
So the rushing-Under shift is kept as it is; look again if two straight weeks go against it.
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import betrules as BR  # noqa: E402


def _pay(o):
    o = float(o)
    return o / 100 if o > 0 else 100 / -o


def check(log_path=ROOT / "docs" / "data" / "props_log.json"):
    props = json.loads(Path(log_path).read_text()).get("props", {})
    rows = [p for p in props.values() if (p.get("result") or {}).get("outcome") in ("Over", "Under")
            and p.get("book_over") is not None and p.get("stat") not in ("anytime_td", "tds")]
    weeks = sorted({p["week"] for p in rows})
    out = {}
    for stat in sorted({p["stat"] for p in rows}):
        ll_b = ll_s = n = 0
        w_ = l_ = 0
        units = 0.0
        by_week = []
        for wk in weeks[1:]:
            train = [(p["stat"], p["book_over"] / 100, p["result"]["outcome"] == "Over") for p in rows if p["week"] < wk]
            shift = BR.bias_table(train).get(stat, {}).get("shift", 0.0)
            ww = wl = 0
            wu = 0.0
            for p in (p for p in rows if p["week"] == wk and p["stat"] == stat):
                b = BR.clip(p["book_over"] / 100, 0.02, 0.98)
                over = p["result"]["outcome"] == "Over"
                s = BR.inv_logit(BR.logit(b) + shift)
                ll_b -= math.log(b if over else 1 - b)
                ll_s -= math.log(s if over else 1 - s)
                n += 1
                try:
                    pay = _pay(p["under_odds"])
                except (TypeError, ValueError, KeyError):
                    continue
                if over:
                    wl, wu = wl + 1, wu - 1
                else:
                    ww, wu = ww + 1, wu + pay
            w_, l_, units = w_ + ww, l_ + wl, units + wu
            by_week.append({"week": wk, "shift": round(shift, 3), "unders": [ww, wl], "units": round(wu, 1)})
        if n:
            out[stat] = {"n": n, "logloss_book": round(ll_b / n, 4), "logloss_shifted": round(ll_s / n, 4),
                         "unders": [w_, l_], "units": round(units, 1), "roi": round(100 * units / max(w_ + l_, 1), 1), "by_week": by_week}
    return out


if __name__ == "__main__":
    for stat, r in check().items():
        better = "helps" if r["logloss_shifted"] < r["logloss_book"] - 0.0005 else ("hurts" if r["logloss_shifted"] > r["logloss_book"] + 0.0005 else "no difference")
        print(f"{stat}: log loss {r['logloss_book']} -> {r['logloss_shifted']} over {r['n']} ({better}); "
              f"every Under {r['unders'][0]}-{r['unders'][1]}, {r['units']:+}u ({r['roi']:+}%)")
        print("   " + " | ".join(f"w{x['week']} shift {x['shift']:+} {x['unders'][0]}-{x['unders'][1]} ({x['units']:+}u)" for x in r["by_week"]))
