"""
The alt-line page code shared by the NFL and NHL pages (docs/index.html, docs/nhl/index.html), and the
bet-type gate panel (GATES_JS) shared by all four pages (NFL, NHL, CFB, soccer).

Run `python tools/altjs.py` after editing ALT_JS: it rewrites the block between the ALT-JS markers in
both pages, so the two stay identical. Per-page settings come from ALT_CFG, defined on each page.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START, END = "/* ---- ALT-JS start (tools/altjs.py) ---- */", "/* ---- ALT-JS end ---- */"

ALT_CSS = """
/* alt lines and team totals (tools/altjs.py) */
.altbox{display:grid;gap:8px;border:1px solid var(--line-soft);border-radius:var(--r);padding:12px 14px;background:var(--surface)}
.altbox>b{color:var(--ink)}
.altbox table td,.altbox table th{font-size:13.5px;padding:7px 10px}
.altbox tr.on td{background:var(--win-soft)}
.altbox .pcheck{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.altbox select,.altbox input{font:600 14px var(--sans);background:var(--raised);color:var(--ink);border:1px solid var(--line);border-radius:999px;padding:7px 12px}
.altbox select{appearance:none;-webkit-appearance:none;padding-right:14px}
.altbox input{width:92px;font:600 15px var(--num)}
.altbox input:focus,.altbox select:focus{border-color:var(--gold);outline:none;box-shadow:0 0 0 3px var(--gold-soft)}
.mine{display:inline-block;font:600 10.5px var(--sans);color:var(--gold-text);border:1px solid var(--gold-line);border-radius:999px;padding:1px 7px;margin-left:6px;vertical-align:2px}
.vt.thin{border-color:var(--line);color:var(--muted)}
.mchip{display:inline-block;font:600 10.5px var(--sans);color:var(--brown);background:var(--beige);border-radius:999px;padding:2px 8px;margin-right:6px;vertical-align:1px;white-space:nowrap}
.bet.on{border-color:var(--gold-line);background:linear-gradient(90deg,var(--gold-soft),transparent 70%)}
.gbar{height:6px;border-radius:999px;background:var(--line-soft);overflow:hidden}.gbar i{display:block;height:100%;background:var(--gold)}
.legteam{display:inline-block;font:600 10px var(--sans);color:var(--brown);border:1px solid var(--line);border-radius:999px;padding:0 6px;margin-right:5px;vertical-align:1px}
.altbox td:first-child{white-space:normal;min-width:120px}
@media (max-width:640px){.altbox .c-x{display:none}.altbox table td,.altbox table th{padding:7px 6px;font-size:13px}}
/* alt css end */
"""

ALT_JS = r"""
const ALT_MK = {spread: ALT_CFG.spread, total: "Alt total", team_total: "Team total", h1_spread: "1st half spread", h1_total: "1st half total"};
const altMkName = x => x.period === "h1" ? ALT_MK["h1_" + x.market] || "1st half" : ALT_MK[x.market];
const LS_ALTP = `board.${ALT_CFG.sport}.altprices.v1`;
let ALTP = lsGet(LS_ALTP, {});
const ALTSEL = {};
const altKey = (gid, b) => [gid, b.market, b.team || "", b.side, b.line].join("|");
const altSgn = (v, d = 1) => v == null || isNaN(v) ? "–" : (v > 0 ? "+" : "") + Number(v).toFixed(d);
function altLabel(g, b) {
  const L = +b.line, t = b.team === "home" || b.side === "home" ? g.home : g.away;
  if (b.market === "spread") return `${t} ${L > 0 ? "+" : ""}${L}`;
  if (b.market === "total") return `${b.side === "over" ? "Over" : "Under"} ${L}`;
  return `${b.team === "home" ? g.home : g.away} team total ${b.side === "over" ? "Over" : "Under"} ${L}`;
}
function altLad(g, m, team) { const L = g.ladder || {}; return (m === "spread" ? L.spread : m === "total" ? L.total : team === "home" ? L.team_home : L.team_away) || []; }
/* the bet's chance by the model and by Pinnacle (refunds left out). Exact when Pinnacle posted that line. */
function altChance(g, b) {
  let hl = +b.line, flip = false;
  if (b.market === "spread") { if (b.side === "away") { hl = -hl; flip = true; } }
  else if (b.side === "under") flip = true;
  const r = altLad(g, b.market, b.team).find(x => Math.abs(x[0] - hl) < 1e-9);
  if (!r) return null;
  let m = r[1] / 100, k = r[2] == null ? null : r[2] / 100;
  if (flip) { m = 1 - m; k = k == null ? null : 1 - k; }
  const row = (g.alt?.rows || []).find(x => !x.period && x.market === b.market && (x.team || "") === (b.team || "") && x.side === b.side && Math.abs(x.line - b.line) < 1e-9);
  return row && row.exact && row.sharp != null ? {m, k: row.sharp / 100, exact: true} : {m, k, exact: false};
}
/* same rule as the posted plays: worth min% to 8% at Pinnacle's fair chance (1 point more on a converted line), model agrees */
function altVerdict(c, odds) {
  if (!c || c.k == null || !String(odds ?? "").trim()) return null;
  const o = oddsNum(odds); if (!isFinite(o) || Math.abs(o) < 100) return {bad: true};
  const R = D.alt_rules || {}, ev = 100 * (c.k * (payout(odds) + 1) - 1), implied = 100 * impl(odds);
  const lo = (R.min_ev ?? 1.5) + (c.exact ? 0 : (R.converted_extra ?? 1)), hi = R.max_ev ?? 8, agree = 100 * c.m >= implied;
  return {ev, lo, agree, implied, tier: ev > hi ? "big" : ev >= lo && agree ? "play" : ev > 0 ? "thin" : "none"};
}
function altVerdictTxt(v, c) {
  if (!c) return "No ladder for this line.";
  if (!v) return c.k != null ? `Pinnacle's fair ${fair(c.k)} (${n(100 * c.k, 1)}%${c.exact ? "" : ", converted"}), model ${n(100 * c.m, 0)}%. Type your book's price.` : `Model fair ${fair(c.m)} (${n(100 * c.m, 0)}%). Needs Pinnacle's lines to check a price.`;
  if (v.bad) return "Use American odds like -110 or +150.";
  const why = v.tier === "play" ? `Model ${n(100 * c.m, 0)}% agrees.` : v.tier === "big" ? "Gap too big to trust: likely a stale or wrong line." : v.ev > 0 && !v.agree ? `The model disagrees (${n(100 * c.m, 0)}%).` : v.ev > 0 ? `Needs +${n(v.lo)}%${c.exact ? "" : " on a converted line"}.` : "";
  return `<span class="vt ${v.tier === "play" ? "play" : v.tier === "big" ? "big" : "thin"}">${{play: "Play", thin: "Thin edge", big: "Too big to trust", none: "No value"}[v.tier]}</span> Worth ${altSgn(v.ev)}% at Pinnacle's fair ${n(100 * c.k, 1)}%${c.exact ? "" : " (converted)"}; your price implies ${n(v.implied, 1)}%. ${why}`;
}
function altLinesFor(g, m, team, side) {
  return altLad(g, m, team).map(r => m === "spread" && side === "away" ? -r[0] : r[0]).sort((a, b) => a - b);
}
function altSel(g) {
  const s = ALTSEL[g.game_id]; if (s) return s;
  const ls = altLinesFor(g, "team_total", "home", "over"), hs = ls.filter(L => L % 1 !== 0), use = hs.length ? hs : ls;
  return {market: "team_total", team: "home", side: "over", line: use.length ? use[Math.floor(use.length / 2)] : 0};
}
function altBet(g, s, odds) {
  const c = altChance(g, s);
  return {kind: "alt", game_id: g.game_id, market: s.market, team: s.team || null, side: s.side, line: +s.line, home: g.home,
    odds: odds || (c ? fair(c.k ?? c.m) : "-110"), model_pct: c ? 100 * (c.k ?? c.m) : null, desc: altLabel(g, s), sub: `${ALT_MK[s.market]}, ${g.away} at ${g.home}`};
}
function altBox(g) {
  if (!g.ladder) return "";
  const A = g.alt || {}, rows = A.rows || [], s = altSel(g), mk = s.market === "team_total" ? `tt_${s.team}` : s.market;
  const sides = s.market === "spread" ? [["home", g.home], ["away", g.away]] : [["over", "Over"], ["under", "Under"]];
  const lines = altLinesFor(g, s.market, s.team, s.side), key = altKey(g.game_id, s), odds = ALTP[key]?.odds || "";
  const c = altChance(g, s), v = altVerdict(c, odds);
  const tbl = rows.length ? `<div class="tablewrap"><table><thead><tr><th>${esc(A.book || "Book")} price</th><th></th><th class="c-x">Model</th><th>Pinnacle</th><th>Value</th></tr></thead><tbody>
    ${rows.map(x => `<tr class="${x.play ? "on" : ""}"><td style="text-align:left">${esc(x.label)}</td><td>${esc(x.odds)}</td><td class="c-x">${n(x.model, 0)}%</td><td>${x.sharp != null ? `${n(x.sharp, 0)}%${x.exact ? "" : "*"}` : "–"}</td>
      <td>${x.play ? `<span class="tag">Play</span>` : x.ev != null ? `<span class="${x.ev > 0 ? "gold" : "dim"}">${altSgn(x.ev)}%</span>` : "–"}</td></tr>`).join("")}</tbody></table></div>
    <div class="note" style="margin:0">Best ${rows.length} of ${A.n} ${esc(A.book || "")} alt prices by value. * Pinnacle didn't post that line: its main lines converted, so it needs 1 point more value.</div>`
    : `<div class="dim">${esc(ALT_CFG.pending)}</div>`;
  return `<div class="altbox" id="alt-${g.game_id}"><b>Alt lines and team totals</b>${tbl}
    <div><b style="font-size:13.5px">Check a price</b>
      <div class="pcheck" style="margin-top:6px" data-altg="${g.game_id}">
        <select class="altm" aria-label="Market"><option value="team_total|home"${mk === "tt_home" ? " selected" : ""}>${esc(g.home)} team total</option><option value="team_total|away"${mk === "tt_away" ? " selected" : ""}>${esc(g.away)} team total</option><option value="total|"${mk === "total" ? " selected" : ""}>Game total</option><option value="spread|"${mk === "spread" ? " selected" : ""}>${esc(ALT_CFG.spread)}</option></select>
        <select class="alts" aria-label="Side">${sides.map(([k, l]) => `<option value="${k}"${s.side === k ? " selected" : ""}>${esc(l)}</option>`).join("")}</select>
        <select class="altl" aria-label="Line">${lines.map(L => `<option value="${L}"${Math.abs(L - s.line) < 1e-9 ? " selected" : ""}>${s.market === "spread" && L > 0 ? "+" : ""}${L}</option>`).join("")}</select>
        <input class="alto" value="${esc(odds)}" placeholder="${esc(c ? fair(c.k ?? c.m) : "-110")}" inputmode="text" aria-label="Your book's odds">${logBtn(altBet(g, s, odds))}</div>
      <div class="stake" style="margin-top:6px">${altVerdictTxt(v, c)}${v?.tier === "play" ? ` ${altStakeTxt(100 * c.k, odds)}` : ""}</div></div></div>`;
}
function altRedraw(gid) {
  const g = (D.games || []).find(x => String(x.game_id) === String(gid)), el = document.getElementById("alt-" + gid);
  if (g && el) el.outerHTML = altBox(g);
}
document.addEventListener("change", e => {
  const box = e.target.closest("[data-altg]"); if (!box) return;
  const gid = box.dataset.altg, g = (D.games || []).find(x => String(x.game_id) === gid), s = {...altSel(g)};
  if (e.target.matches(".altm")) { const [m, t] = e.target.value.split("|"); s.market = m; s.team = t || null; s.side = m === "spread" ? "home" : "over";
    const ls = altLinesFor(g, s.market, s.team, s.side), hs = ls.filter(L => L % 1 !== 0), use = hs.length ? hs : ls; s.line = use.length ? use[Math.floor(use.length / 2)] : 0; }
  else if (e.target.matches(".alts")) { const old = s.side; s.side = e.target.value; if (s.market === "spread" && old !== s.side) s.line = -s.line; }
  else if (e.target.matches(".altl")) s.line = +e.target.value;
  else if (e.target.matches(".alto")) { const v = e.target.value.trim(), k = altKey(gid, s); if (v) ALTP[k] = {odds: v, at: new Date().toISOString()}; else delete ALTP[k];
    lsSet(LS_ALTP, ALTP); ALTSEL[gid] = s; altRedraw(gid); renderHome(); return; }
  ALTSEL[gid] = s; altRedraw(gid);
});
document.addEventListener("keydown", e => { if (e.key === "Enter" && e.target.matches(".alto")) e.target.blur(); });
/* alt plays: the model's (Hard Rock prices in the feed) plus any price you checked that passes */
function altPlays() {
  const out = [];
  for (const g of D.games || []) {
    if (new Date(g.start) < Date.now()) continue;
    for (const x of g.alt?.plays || []) out.push({type: "alt", kind: "alt", g, p: x, edge: x.ev, model: x.sharp, book: 100 * impl(x.odds), odds: x.odds,
      title: x.label, sub: `${altMkName(x)}, ${g.away} at ${g.home}`});
  }
  for (const [key, v] of Object.entries(ALTP)) {
    if (!v?.odds) continue;
    const [gid, market, team, side, line] = key.split("|"), g = (D.games || []).find(x => String(x.game_id) === gid);
    if (!g || new Date(g.start) < Date.now()) continue;
    const b = {market, team: team || null, side, line: +line}, c = altChance(g, b), vd = altVerdict(c, v.odds);
    if (!vd || vd.tier !== "play") continue;
    const lab = altLabel(g, b);
    if (out.some(x => x.g === g && x.title === lab)) continue;
    out.push({type: "alt", kind: "alt", g, mine: true, p: {...b, odds: v.odds, model: 100 * c.m, sharp: 100 * c.k, exact: c.exact, ev: vd.ev, label: lab},
      edge: vd.ev, model: 100 * c.k, book: vd.implied, odds: fmtO(v.odds), title: lab, sub: `${ALT_MK[market]}, ${g.away} at ${g.home}`});
  }
  return out;
}
const altPlayBet = x => ({kind: "alt", game_id: x.g.game_id, market: x.p.market, period: x.p.period || null, team: x.p.team || null, side: x.p.side, line: +x.p.line, home: x.g.home,
  odds: x.odds, model_pct: x.model, desc: x.title, sub: x.sub});
function altGrade(b, h, a) {
  const L = +b.line, halves = Math.round(L * 4) % 2 ? [L - 0.25, L + 0.25] : [L];
  const xv = x => b.market === "spread" ? (b.side === "home" ? h - a : a - h) + x : b.market === "total" ? (b.side === "over" ? h + a - x : x - h - a)
    : ((b.team === "home" ? h : a) - x) * (b.side === "over" ? 1 : -1);
  const u = halves.map(x => xv(x)).map(v => v > 0 ? payout(b.odds) : v < 0 ? -1 : 0).reduce((s, x) => s + x, 0) / halves.length;
  return {res: u > 0 ? "W" : u < 0 ? "L" : "P", units: (b.units || 1) * u};
}
/* new market: suggested stake capped at 1 unit until alt plays build a graded record */
function altStakeTxt(pPct, odds) {
  const z = sizing(pPct, odds); if (!z) return "";
  if (z.units > 1) { z.units = 1; z.dollars = Math.round(SET.unit); }
  return z.units > 0 ? `Suggested bet <b>${z.units}u</b> ($${z.dollars}) <span class="dim">(1u cap: new market)</span>` : `Suggested bet <b>none</b> at this price`;
}
/* paused bet types (gates.py): shadow record and the bar to come back */
const altLegTxt = L => L.kind === "team" ? `<span class="legteam">${esc(ALT_MK[L.market] || "Team")}</span>${esc(L.label)}` : `<b>${esc(L.name)}</b> ${esc(L.label)}`;
"""

GSTART, GEND = "/* ---- GATES-JS start (tools/altjs.py) ---- */", "/* ---- GATES-JS end ---- */"
GATES_JS = """
/* bet-type gates (gates.py): paused types tracked in the background, and game types watched for closing-line value */
const gSgn = (v, d = 1) => v == null || isNaN(v) ? "–" : (v > 0 ? "+" : "") + Number(v).toFixed(d);
const gList = () => D.gates || D.tracking?.gates || [];
const gWatch = x => x.clv_gate && x.status === "active" && !(x.history || []).some(h => h.to === "active");
function gateCard(x) {
  const R = x.record || {}, back = x.status === "active", watch = gWatch(x);
  const pct = watch ? Math.min(100, 100 * (R.ev_n || 0) / (x.clv_pause_n || 30)) : Math.min(100, 100 * (R.n || 0) / x.min_n);
  const evTxt = R.ev_n ? `${gSgn(R.ev_close, 1)}% at the closing price over ${R.ev_n} priced` : "no closing prices yet";
  const need = watch ? `Closing-line check: ${evTxt}. Pauses at ${x.clv_pause_n || 30}+ priced plays if that stays below 0%, or if the return reaches ${x.repause_roi}%.`
    : back ? `Back since ${esc(String(x.since).slice(5))}. Paused again if it returns ${x.repause_roi}% or worse over its next ${x.min_n}${x.clv_gate ? ", or loses to the closing line" : ""}.`
    : `${R.n || 0} of ${x.min_n} graded. Needs a +${x.min_roi}% return${x.clv_gate ? " and 0% or better at the closing price" : ""} to come back${R.ev_n ? ` (now ${gSgn(R.ev_close, 1)}%)` : R.clv_n >= 15 ? ` (closing value so far ${gSgn(R.clv, 2)})` : ""}.`;
  const tag = watch ? `<span class="vt thin">On watch</span>` : back ? `<span class="tag">Back in plays</span>` : `<span class="vt">Paused</span>`;
  return `<div class="gate"><div class="gh"><b>${esc(x.label)}</b>${tag}</div>
    ${watch ? "" : `<div class="dim" style="font-size:12.5px">${esc(x.why)}</div>`}
    <div class="gs"><span>${R.n ? `${R.w}–${R.l}` : "0–0"} ${back ? "as plays" : "shadow"}</span><span class="${R.n ? (R.units >= 0 ? "up" : "down") : "dim"}">${R.n ? `${gSgn(R.units, 2)}u, ${gSgn(R.roi)}%` : "no results yet"}</span></div>
    <div class="gbar"><i style="width:${pct}%"></i></div><div style="font-size:13px">${need}</div></div>`;
}
function gatesHTML() {
  const G = gList(); if (!G.length) return "";
  const watch = G.filter(gWatch), rest = G.filter(x => !gWatch(x));
  let h = "";
  if (rest.length) {
    const g0 = rest[0];
    h += `<h3>Paused bets, tracked in the background</h3><p class="sub">When a bet type is cut, the model keeps finding the bets it would have played, locks them at the price it saw, and grades them. Only bets from the pause date on count, so a comeback is earned on fresh results. A type comes back into plays on its own after about ${g0.min_n} graded at a +${g0.min_roi}% return or better, without losing to the closing line.</p>
    <div class="gates">${rest.map(gateCard).join("")}</div>
    <p class="note">Record is shadow plays while paused, real plays once back. Shadow plays are never in your units.</p>`;
  }
  if (watch.length) h += `<h3>Bet types on watch</h3><p class="sub">Each game bet type is checked against the closing line: the return its plays would make if the closing price is the true chance. A type that stays below 0% over 30+ priced plays is paused automatically, even if it has been winning, because wins without closing-line value usually don't last.</p>
    <div class="gates">${watch.map(gateCard).join("")}</div>`;
  return h;
}
function propClvHTML() {
  const C = D.tracking?.prop_clv; if (!C || !C.n) return "";
  return `<p class="note"><b>Prop plays vs the closing line:</b> ${C.n} checked, ${C.beat} moved our way, ${C.worse} moved against` +
    (C.ev_close != null ? `, ${gSgn(C.ev_close, 1)}% return at the closing price (same-line plays)` : "") +
    `. A play is locked when first flagged; the closing line is the book's last line before the game.</p>`;
}
/* scorecard (Oct 30 2026): every bet type in one table, sorted by how it's doing since the current rules */
function scStatus(x) {
  const R = x.record || {};
  if (x.status !== "active") return ["Paused", "sc-off", 3];
  if ((R.n || 0) < x.min_n) return ["Proving", "sc-new", 1];
  const clvBad = R.ev_n >= 15 && R.ev_close < 0;
  if ((R.roi || 0) > 0 && !clvBad) return ["Earning", "sc-ok", 0];
  return ["Struggling", "sc-warn", 2];
}
function scorecardHTML() {
  const G = gList(); if (!G.length) return "";
  const all = G.map(x => ({x, s: scStatus(x)})).sort((a, b) => a.s[2] - b.s[2] || ((b.x.record || {}).units || 0) - ((a.x.record || {}).units || 0));
  const rows = all.filter(r => (r.x.record || {}).n || r.s[0] === "Paused"), idle = all.filter(r => !rows.includes(r));
  const cnt = k => all.filter(r => r.s[0] === k).length;
  return `<div class="dash"><div class="panel span-12"><h3>Scorecard</h3><p class="pmuted">Every bet type under the current rules. <b>Earning</b>: past its sample, winning, not losing to the closing line. <b>Proving</b>: too few results yet, stake small. <b>Struggling</b>: losing money or losing to the close; pauses on its own if it keeps up. <b>Paused</b>: not a play, tracked in the background until it earns its way back.</p>
    <div class="sc-sum"><span class="sc-ok">${cnt("Earning")} earning</span><span class="sc-new">${cnt("Proving")} proving</span><span class="sc-warn">${cnt("Struggling")} struggling</span><span class="sc-off">${cnt("Paused")} paused</span></div>
    ${rows.length ? `<div class="tablewrap"><table class="sc"><thead><tr><th>Bet type</th><th>Record</th><th>Close</th></tr></thead><tbody>
    ${rows.map(({x, s}) => { const R = x.record || {};
      return `<tr><td>${esc(x.label)} <span class="sc-tag ${s[1]}">${s[0]}</span><span class="roi">${x.status === "active" ? "since " : "shadow since "}${esc(String(x.since).slice(5))}, ${R.n || 0} of ${x.min_n} graded</span></td>
        <td>${R.n ? `${R.w}–${R.l}` : "0–0"}<span class="roi ${R.n ? (R.units >= 0 ? "up" : "down") : ""}">${R.n ? `${gSgn(R.units, 1)}u, ${gSgn(R.roi, 0)}%` : ""}</span></td>
        <td>${R.ev_n ? `<span class="${R.ev_close >= 0 ? "up" : "down"}">${gSgn(R.ev_close, 1)}%</span><span class="roi">${R.ev_n} priced</span>` : `<span class="dim">–</span>`}</td></tr>`; }).join("")}
    </tbody></table></div>` : ""}
    ${idle.length ? `<p class="note">No plays yet: ${idle.map(r => esc(r.x.label)).join(", ")}.</p>` : ""}</div></div>`;
}
function gatesNote() {
  const G = gList(), back = G.filter(x => x.status === "active" && !gWatch(x)), off = G.filter(x => x.clv_gate && x.status === "paused");
  return (back.length ? ` <b>Back in plays:</b> ${back.map(x => esc(x.label)).join(", ")}.` : "") +
         (off.length ? ` <b>Paused:</b> ${off.map(x => esc(x.label)).join(", ")}.` : "");
}
"""
GATES_CSS = """
/* bet-type gates (tools/altjs.py) */
.gates{display:grid;gap:10px;grid-template-columns:repeat(auto-fill,minmax(min(100%,300px),1fr))}
.gate{border:1px solid var(--line);border-radius:var(--r);padding:12px 14px;background:var(--surface);display:grid;gap:6px}
.gate .gh{display:flex;justify-content:space-between;align-items:center;gap:8px}
.gate .gs{display:flex;justify-content:space-between;gap:8px;font:600 14px var(--num)}
.gbar{height:6px;border-radius:999px;background:var(--line-soft);overflow:hidden}.gbar i{display:block;height:100%;background:var(--gold)}
.vt.thin{border-color:var(--line);color:var(--muted)}
.sc-sum{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 10px}
.sc-sum span,.sc-tag{display:inline-block;font:600 11.5px var(--sans);padding:2px 9px;border-radius:999px;border:1px solid currentColor;white-space:nowrap}
.sc-ok{color:var(--win)}.sc-new{color:var(--muted)}.sc-warn{color:var(--gold-text)}.sc-off{color:var(--loss)}
table.sc td,table.sc th{white-space:normal;padding:9px 10px}table.sc td:first-child{min-width:0}
table.sc .sc-tag{font-size:10.5px;padding:1px 7px;margin-left:4px;vertical-align:1px}
table.sc .roi{display:block;font:400 11.5px var(--sans);color:var(--faint)}
/* gates css end */
"""


def build_gates():
    pages = [ROOT / "docs" / "index.html", ROOT / "docs" / "nhl" / "index.html", ROOT / "docs" / "cfb" / "index.html",
             ROOT / "docs" / "soccer" / "index.html"]
    for page in pages:
        s = page.read_text()
        if GSTART not in s:                      # first run: add the markers just before the page's closing </script>
            i = s.rindex("</script>")
            s = s[:i] + GSTART + GEND + "\n" + s[i:]
        a, b = s.index(GSTART) + len(GSTART), s.index(GEND)
        s = s[:a] + GATES_JS + s[b:]
        c0, c1 = "\n/* bet-type gates (tools/altjs.py) */", "/* gates css end */\n"
        if c0 in s:
            s = s[:s.index(c0)] + s[s.index(c1) + len(c1):]
        s = s.replace("</style>", GATES_CSS + "</style>", 1)
        page.write_text(s)
        print(f"{page}: gates updated")


def build():
    for page, cfg in ((ROOT / "docs" / "nhl" / "index.html", None), (ROOT / "docs" / "index.html", None)):
        s = page.read_text()
        if START not in s:
            print(f"{page}: no ALT-JS markers, skipped")
            continue
        a, b = s.index(START) + len(START), s.index(END)
        s = s[:a] + ALT_JS + s[b:]
        c0, c1 = "\n/* alt lines and team totals (tools/altjs.py) */", "/* alt css end */\n"
        if c0 in s:
            s = s[:s.index(c0)] + s[s.index(c1) + len(c1):]
        s = s.replace("</style>", ALT_CSS + "</style>", 1)
        page.write_text(s)
        print(f"{page}: updated")


if __name__ == "__main__":
    build()
    build_gates()
