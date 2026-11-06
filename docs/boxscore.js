/* Projected box scores (Nov 5 2026): every player's average line from the model's simulations, inside each game card.
   One file for all five pages; each page calls BOX.<sport>(game, D.players). */
(function () {
  const st = document.createElement("style");
  st.textContent = `
.bx{margin-top:4px}
.bx>summary{cursor:pointer;color:var(--ink);font-weight:600;list-style:none;display:flex;justify-content:space-between;align-items:center;gap:8px;padding:2px 0}
.bx>summary::-webkit-details-marker{display:none}
.bx>summary::after{content:"Show";font-weight:500;font-size:12.5px;color:var(--gold-text)}
.bx[open]>summary::after{content:"Hide"}
.bx>summary span{color:var(--faint);font-weight:500;font-size:12.5px;margin-left:auto}
.bx h4{margin:14px 0 6px;font-size:12.5px;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.04em}
.bx h4 b{color:var(--ink)}
.bx .tablewrap{border-radius:var(--r);background:var(--surface)}
.bx table{font-size:13px}
.bx th,.bx td{padding:6px 7px;text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums;border-bottom:1px solid var(--line-soft)}
.bx tr:last-child td{border-bottom:0}
.bx th{color:var(--faint);font-weight:600;font-size:11.5px;text-transform:uppercase;letter-spacing:.03em}
.bx th:first-child,.bx td:first-child{text-align:left}
.bx td:first-child{color:var(--ink);font-weight:500;white-space:normal;min-width:110px}
.bx td:first-child span{color:var(--faint);font-weight:400;font-size:11.5px;margin-left:5px}
.bx .bxnote{color:var(--faint);font-size:12px;margin:10px 0 0;line-height:1.45}`;
  document.head.appendChild(st);

  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  const num = v => v == null || !isFinite(v) ? null : Number(v);
  const f0 = v => num(v) == null ? "–" : String(Math.round(v));
  const f1 = v => num(v) == null ? "–" : (Math.round(v * 10) / 10).toFixed(1);
  const f2 = v => num(v) == null ? "–" : (Math.round(v * 100) / 100).toFixed(2);
  const pct = v => num(v) == null ? "–" : Math.round(v * 100) + "%";
  const mean = (p, k) => p.m?.[k]?.mean ?? p.markets?.[k]?.mean ?? null;
  const same = (a, b) => String(a) === String(b);

  function table(rows, cols) {
    if (!rows.length) return "";
    return `<div class="tablewrap"><table><thead><tr>${cols.map(c => `<th>${c[0]}</th>`).join("")}</tr></thead><tbody>${
      rows.map(p => `<tr>${cols.map(c => `<td>${c[1](p)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
  }
  const name = (p, tag) => `${esc(p.name)}${tag ? `<span>${esc(tag)}</span>` : ""}`;

  // sections: [{title, pick(p), sort(p), cols}] drawn per team, teams in the order given
  function box(g, players, teams, sections, note) {
    const mine = (players || []).filter(p => same(p.game_id, g.game_id));
    if (!mine.length) return "";
    let h = "";
    for (const s of sections) {
      for (const t of teams) {
        const rows = mine.filter(p => p.team === t && s.pick(p)).sort((a, b) => s.sort(b) - s.sort(a));
        if (rows.length) h += `<h4><b>${esc(t)}</b> ${esc(s.title)}</h4>${table(rows, s.cols)}`;
      }
    }
    if (!h) return "";
    return `<details class="bx"><summary>Projected box score<span>${mine.length} players</span></summary>${h}
      <p class="bxnote">${note || ""} These are averages across every simulation of this game, so fractions are normal: 0.4 means it happens in a good share of runs, not never. Real games swing a lot more than an average.</p></details>`;
  }

  window.BOX = {
    nfl(g, players) {
      return box(g, players, [g.away, g.home], [
        {title: "Passing", pick: p => p.pos === "QB" && (p.pass_att ?? mean(p, "pass_att") ?? 0) >= 5, sort: p => p.pass_yds ?? 0,
         cols: [["Player", p => name(p, p.status)], ["C/Att", p => `${f0(p.pass_cmp ?? mean(p, "pass_cmp"))}/${f0(p.pass_att ?? mean(p, "pass_att"))}`],
                ["Yds", p => f0(p.pass_yds ?? mean(p, "pass_yds"))], ["TD", p => f1(p.pass_td)], ["Int", p => f1(p.pass_int)]]},
        {title: "Rushing", pick: p => (p.carries ?? mean(p, "carries") ?? 0) >= 1.5, sort: p => p.rush_yds ?? 0,
         cols: [["Player", p => name(p, p.pos)], ["Car", p => f0(p.carries ?? mean(p, "carries"))], ["Yds", p => f0(p.rush_yds ?? mean(p, "rush_yds"))],
                ["TD", p => f1(p.rush_td)]]},
        {title: "Receiving", pick: p => (p.targets ?? 0) >= 1.5 || (p.rec ?? 0) >= 1, sort: p => p.rec_yds ?? 0,
         cols: [["Player", p => name(p, p.pos)], ["Tgt", p => f1(p.targets)], ["Rec", p => f1(p.rec ?? mean(p, "rec"))],
                ["Yds", p => f0(p.rec_yds ?? mean(p, "rec_yds"))], ["TD", p => f1(p.rec_td)]]},
      ], "Players the model expects to get real work. Kickers and defense aren't simulated.");
    },
    cfb(g, players) {
      return box(g, players, [g.away, g.home], [
        {title: "Passing", pick: p => p.pos === "QB" && mean(p, "pass_yds") != null, sort: p => mean(p, "pass_yds") ?? 0,
         cols: [["Player", p => name(p)], ["Yds", p => f0(mean(p, "pass_yds"))], ["TD", p => f1(mean(p, "pass_td"))],
                ["Rush yds", p => f0(mean(p, "rush_yds"))]]},
        {title: "Rushing and receiving", pick: p => p.pos !== "QB" && ((mean(p, "rush_yds") ?? 0) >= 8 || (mean(p, "rec_yds") ?? 0) >= 8),
         sort: p => (mean(p, "rush_yds") ?? 0) + (mean(p, "rec_yds") ?? 0),
         cols: [["Player", p => name(p, p.pos)], ["Rush", p => f0(mean(p, "rush_yds"))], ["Rec", p => f1(mean(p, "rec"))],
                ["Rec yds", p => f0(mean(p, "rec_yds"))], ["TD", p => f1(mean(p, "td"))]]},
      ], "Players with a priced role. The college model doesn't project completions, attempts or interceptions yet.");
    },
    nba(g, players) {
      return box(g, players, [g.away, g.home], [
        {title: "", pick: p => (p.min ?? 0) >= 8 && (p.avail ?? 100) > 0, sort: p => p.min ?? 0,
         cols: [["Player", p => name(p, (p.avail ?? 100) < 100 ? `${p.status || "Questionable"}, ${Math.round(p.avail)}% to play` : p.pos)],
                ["Min", p => f0(p.min)], ["Pts", p => f1(mean(p, "pts"))], ["Reb", p => f1(mean(p, "reb"))], ["Ast", p => f1(mean(p, "ast"))],
                ["3PM", p => f1(mean(p, "fg3m"))], ["PRA", p => f1(mean(p, "pra"))]]},
      ], "Players expected to play 8+ minutes. Questionable players are weighted by their chance to play. Steals, blocks and turnovers aren't simulated yet.");
    },
    nhl(g, players) {
      const ga = t => t === g.home ? g.xg_away : g.xg_home;
      const starter = (p) => !g.goalies?.[p.team] || same(g.goalies[p.team].pid, p.pid);
      return box(g, players, [g.away, g.home], [
        {title: "Skaters", pick: p => p.pos !== "G" && (p.toi ?? 0) > 0, sort: p => mean(p, "points") ?? 0,
         cols: [["Player", p => name(p, p.pos)], ["TOI", p => f1(p.toi)], ["SOG", p => f1(mean(p, "sog"))], ["G", p => f2(mean(p, "goals"))],
                ["A", p => f2(mean(p, "assists"))], ["Pts", p => f2(mean(p, "points"))]]},
        {title: "Goalie", pick: p => p.pos === "G" && starter(p), sort: p => mean(p, "saves") ?? 0,
         cols: [["Player", p => name(p, g.goalies?.[p.team]?.status)], ["Saves", p => f1(mean(p, "saves"))], ["GA", p => f1(ga(p.team))],
                ["Sv%", p => { const s = mean(p, "saves"), a = ga(p.team); return s == null || a == null ? "–" : (s / (s + a)).toFixed(3).replace(/^0/, ""); }]]},
      ], "Skaters sorted by expected points. Goals against is the opponent's expected goals.");
    },
    soccer(g, players) {
      return box(g, players, [g.home, g.away], [
        {title: "", pick: p => (p.p_play ?? 1) >= 0.25, sort: p => mean(p, "goal") ?? 0,
         cols: [["Player", p => name(p, p.pos)], ["Start", p => pct(p.p_start)], ["SOT", p => f2(mean(p, "sot"))],
                ["Goals", p => f2(mean(p, "goal"))], ["Scores", p => pct(p.m?.goal?.ge?.[1])]]},
      ], "Players with a 25%+ chance to play, sorted by expected goals. SOT is shots on target, \"Scores\" is the chance of at least one goal.");
    },
  };
})();
