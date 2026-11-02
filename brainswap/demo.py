"""Build site/brainswap_demo.html: a self-contained page for simulated (or real) runs.

    python -m brainswap demo [--runs runs_brainswap_mock] [--out site/brainswap_demo.html]

Each subdirectory of --runs with an analysis.json becomes one selectable scenario.
Directories under runs_brainswap_mock are labeled SIMULATED on the page.
"""

from __future__ import annotations

import json
from pathlib import Path

from .mock import SCENARIOS

SCENARIO_TEXT = {
    "null": ("No effect built in",
             "Strategy notes help both models equally and source style does not matter. "
             "A sound analysis should find no specialization."),
    "presentation": ("Source style drives specialization",
                     "Each mock edits better when its own source uses its own naming style. "
                     "Specialization should appear, and normalizing the names should remove it."),
    "content": ("Learned notes drive specialization",
                "Strategy notes written by a model help that model more than the other one. "
                "Specialization should appear, and normalization should NOT remove it, because notes are strings."),
}


def _slim(an: dict, name: str, simulated: bool) -> dict:
    lines = an.get("lineages", {}).get("lines", {})
    return {
        "name": name, "simulated": simulated,
        "title": SCENARIO_TEXT.get(name, (name, ""))[0], "blurb": SCENARIO_TEXT.get(name, ("", ""))[1],
        "params": SCENARIOS.get(name),
        "rows": an["rows"], "presentations": an["presentations"], "checkpoints": an["checkpoints"],
        "presentation_info": an.get("presentation_info", {}), "verdicts": an.get("verdicts", []),
        "cost": an.get("cost", {}), "comparison": an.get("lineages", {}).get("comparison", {}),
        "lines": {g: [{"name": l["name"], "model": l["model"], "bar": l["bar"], "progress": l["progress"],
                       "proc": l["proc_edits_accepted"]} for l in ls] for g, ls in lines.items()},
    }


SCALES = {"pilot": "Pilot scale (4 lineages per model)", "powered": "Powered scale (16 lineages per model)"}


def build(runs: Path, out: Path) -> Path:
    """runs/<scale>/<scenario>/analysis.json -> one page. Scales other than pilot/powered are skipped."""
    simulated = "mock" in runs.name
    order = ["null", "presentation", "content"]
    data = []
    for scale in SCALES:
        root = runs / scale
        if not root.exists():
            continue
        for d in sorted((d for d in root.iterdir() if (d / "analysis.json").exists()),
                        key=lambda d: order.index(d.name) if d.name in order else 99):
            entry = _slim(json.loads((d / "analysis.json").read_text()), d.name, simulated)
            entry["scale"], entry["scale_label"] = scale, SCALES[scale]
            data.append(entry)
    if not data:
        raise SystemExit(f"No analysis.json under {runs}/<scale>/<scenario>. "
                         "Run `python -m brainswap simulate --scenario all` first.")
    out.parent.mkdir(parents=True, exist_ok=True)
    html = TEMPLATE.replace("__DATA__", json.dumps(data).replace("</", "<\\/"))
    out.write_text(html)
    return out


TEMPLATE = r"""<title>Brain-Swap Test</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Condensed:wght@500;600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
/* Layout: a lab readout -- one column, instrument panels stacked in reading order, numbers in mono. */
:root {
  --bg: #f5f6f8; --panel: #ffffff; --ink: #1c2027; --ink-2: #4a5160; --muted: #737b8b;
  --rule: #dfe3ea; --grid: #e9ecf1; --a: #2a78d6; --b: #eb6834; --zero: #9aa2b1;
  --warn-bg: #fff4d6; --warn-ink: #6b4a00; --warn-rule: #e9c46a;
  --display: "IBM Plex Sans Condensed", "Arial Narrow", system-ui, sans-serif;
  --body: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, "SFMono-Regular", Menlo, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #14171c; --panel: #1b1f26; --ink: #e8ebf0; --ink-2: #b6bdca; --muted: #8b93a3;
  --rule: #2c323c; --grid: #262b34; --a: #3987e5; --b: #d95926; --zero: #6b7383;
  --warn-bg: #3a2f12; --warn-ink: #f3d78a; --warn-rule: #7a6224; color-scheme: dark; } }
:root[data-theme="dark"] {
  --bg: #14171c; --panel: #1b1f26; --ink: #e8ebf0; --ink-2: #b6bdca; --muted: #8b93a3;
  --rule: #2c323c; --grid: #262b34; --a: #3987e5; --b: #d95926; --zero: #6b7383;
  --warn-bg: #3a2f12; --warn-ink: #f3d78a; --warn-rule: #7a6224; color-scheme: dark; }
* { box-sizing: border-box; }
body { background: var(--bg); color: var(--ink); font: 15px/1.55 var(--body); margin: 0; }
.wrap { max-width: 1040px; margin: 0 auto; padding-block: 28px 56px;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px));
  display: grid; gap: 22px; }
h1, h2 { font-family: var(--display); font-weight: 600; text-wrap: balance; margin: 0; }
h1 { font-size: 2.1rem; letter-spacing: -0.01em; }
h2 { font-size: 1.25rem; }
p { margin: 0; max-width: 68ch; }
.lede { color: var(--ink-2); font-size: 1.05rem; }
.eyebrow { font: 500 0.72rem/1 var(--mono); letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); }
.sim { display: flex; gap: 12px; align-items: flex-start; background: var(--warn-bg); color: var(--warn-ink);
  border: 1px solid var(--warn-rule); border-radius: 8px; padding: 12px 14px; }
.sim svg { flex: none; margin-top: 2px; }
.sim strong { letter-spacing: 0.04em; }
.panel { background: var(--panel); border: 1px solid var(--rule); border-radius: 10px; padding: 18px; display: grid; gap: 14px; min-width: 0; }
.tabs { display: flex; flex-wrap: wrap; gap: 8px; }
.tab { font: 500 0.9rem var(--body); color: var(--ink-2); background: transparent; border: 1px solid var(--rule);
  border-radius: 999px; padding: 7px 14px; cursor: pointer; }
.tab[aria-selected="true"] { background: var(--ink); color: var(--panel); border-color: var(--ink); }
.tab:focus-visible, button:focus-visible { outline: 2px solid var(--a); outline-offset: 2px; }
.scen-blurb { color: var(--ink-2); }
.params { font: 0.78rem var(--mono); color: var(--muted); }
.legend { display: flex; flex-wrap: wrap; gap: 16px; font-size: 0.85rem; color: var(--ink-2); }
.key { display: inline-flex; align-items: center; gap: 6px; }
.sw { width: 18px; height: 3px; border-radius: 2px; display: inline-block; }
.sw.a { background: var(--a); } .sw.b { background: var(--b); }
.sw.dash { background: repeating-linear-gradient(90deg, var(--muted) 0 5px, transparent 5px 9px); }
.charts2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 18px; }
.chart { min-width: 0; }
.chart h3 { font: 600 0.92rem var(--body); margin: 0 0 6px; }
svg.plot { width: 100%; height: auto; display: block; overflow: visible; }
svg text { fill: var(--muted); font: 11px var(--mono); }
.matrices { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 16px; }
.mx { display: grid; gap: 6px; min-width: 0; }
.mx h3 { font: 600 0.9rem var(--body); margin: 0; }
.mx table { border-collapse: separate; border-spacing: 4px; width: 100%; font-variant-numeric: tabular-nums; }
.mx th { font: 500 0.72rem var(--mono); color: var(--muted); text-align: center; padding: 2px; }
.mx th.row { text-align: right; padding-right: 6px; white-space: nowrap; }
.mx td { text-align: center; font: 500 0.95rem var(--mono); padding: 10px 4px; border-radius: 6px;
  background: var(--grid); color: var(--ink); }
.mx td.home { box-shadow: inset 0 0 0 2px var(--ink-2); }
.mx .s { font: 0.8rem var(--mono); color: var(--ink-2); }
.verdicts { margin: 0; padding-left: 1.1rem; display: grid; gap: 6px; color: var(--ink-2); }
.foot { color: var(--muted); font-size: 0.85rem; display: grid; gap: 6px; }
.tablewrap { overflow-x: auto; }
table.data { border-collapse: collapse; font: 0.82rem var(--mono); font-variant-numeric: tabular-nums; min-width: 560px; }
table.data th, table.data td { border-bottom: 1px solid var(--rule); padding: 6px 10px; text-align: right; }
table.data th:first-child, table.data td:first-child { text-align: left; }
details summary { cursor: pointer; color: var(--ink-2); font-weight: 500; }
#tip { position: fixed; pointer-events: none; background: var(--ink); color: var(--panel); font: 12px/1.4 var(--mono);
  padding: 6px 8px; border-radius: 6px; z-index: 20; max-width: 260px; }
.note { font-size: 0.85rem; color: var(--muted); }
@media (prefers-reduced-motion: no-preference) { .tab { transition: background .15s, color .15s; } }
</style>

<div class="wrap">
  <header style="display:grid; gap:10px">
    <div class="eyebrow">RSI Brain-Swap Test &middot; prototype readout</div>
    <h1>Does an improvement procedure specialize to the model that grew it?</h1>
    <p class="lede">Two models each evolve their own solver and their own improvement procedure. Then every
      evolved procedure is handed back an untouched seed solver and run by <em>both</em> models. If a procedure
      works better for the model that evolved it, and that home advantage grows over generations, it has specialized.</p>
  </header>

  <div class="sim" id="simbanner" role="note">
    <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 2 1 21h22L12 2zm0 6 1 7h-2l1-7zm0 9a1.3 1.3 0 1 1 0 2.6A1.3 1.3 0 0 1 12 17z"/></svg>
    <div><strong>SIMULATED DATA.</strong> Every number here comes from mock models with effects built in on purpose,
      run through the real harness. It shows what the analysis would report in each scenario. It is not a result
      about any real model.</div>
  </div>

  <section class="panel" aria-labelledby="h-scen">
    <h2 id="h-scen">Scenario and scale</h2>
    <div class="tabs" role="tablist" aria-label="Scenario" id="tabs"></div>
    <div class="tabs" role="tablist" aria-label="Scale" id="scales"></div>
    <p class="note" id="scalenote"></p>
    <p class="scen-blurb" id="blurb"></p>
    <div class="params" id="params"></div>
  </section>

  <section class="panel" aria-labelledby="h-lin">
    <h2 id="h-lin">Lineage progress</h2>
    <p class="note">Development-set bar (tasks solved, mean of two evaluations) after each generation. Solid lines are
      self-modifying lineages; dashed lines are the frozen-improver and one-generation baselines.</p>
    <div class="legend"><span class="key"><span class="sw a"></span>Model A lineages</span>
      <span class="key"><span class="sw b"></span>Model B lineages</span>
      <span class="key"><span class="sw dash"></span>Baselines</span></div>
    <div class="charts2" id="lineage"></div>
  </section>

  <section class="panel" aria-labelledby="h-mx">
    <h2 id="h-mx">The crossed matrix</h2>
    <p class="note">Mean sealed-set gain over the seed solver, in tasks, after a short continuation. Rows: who evolved the
      procedure. Columns: who runs it now. Outlined cells are home games. At generation 0 every procedure is the seed,
      so any home advantage there is noise.</p>
    <div class="matrices" id="matrices"></div>
  </section>

  <section class="panel" aria-labelledby="h-ds">
    <h2 id="h-ds">Specialization growth, by how the source was shown</h2>
    <p class="note">dS = home advantage at the checkpoint minus home advantage at generation 0, with 95% intervals
      over lineages. <b>orig</b>: source as evolved. <b>norm</b>: formatted, locals renamed v0, v1, ...
      <b>neutral</b>: renamed to random names of matched length (token-length control).</p>
    <div class="chart" id="dschart"></div>
  </section>

  <section class="panel" aria-labelledby="h-v">
    <h2 id="h-v">What the analysis concludes</h2>
    <ul class="verdicts" id="verdicts"></ul>
    <div class="foot" id="cost"></div>
    <details><summary>All numbers as a table</summary><div class="tablewrap" id="table"></div></details>
  </section>
</div>
<div id="tip" hidden></div>

<script>
const DATA = __DATA__;
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const tip = document.getElementById("tip");
function showTip(e, html) { tip.innerHTML = html; tip.hidden = false;
  const x = Math.min(e.clientX + 12, innerWidth - tip.offsetWidth - 8), y = e.clientY + 14;
  tip.style.left = x + "px"; tip.style.top = y + "px"; }
function hideTip() { tip.hidden = true; }
const fmt = (v, d = 1) => (v > 0 ? "+" : "") + v.toFixed(d);
const esc = s => String(s).replace(/[&<>]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));

const SCEN = [...new Set(DATA.map(d => d.name))], SCALES = [...new Set(DATA.map(d => d.scale))];
let pick = {name: SCEN.includes("presentation") ? "presentation" : SCEN[0], scale: SCALES[0]};
try { const s = JSON.parse(localStorage.getItem("bs-pick") || "null");
  if (s && DATA.some(d => d.name === s.name && d.scale === s.scale)) pick = s; } catch (e) {}
const current = () => DATA.find(d => d.name === pick.name && d.scale === pick.scale)
  || DATA.find(d => d.name === pick.name) || DATA[0];

function tabRow(id, items, key, label) {
  const el = document.getElementById(id); el.innerHTML = "";
  items.forEach(v => { const b = document.createElement("button"); b.className = "tab"; b.setAttribute("role", "tab");
    b.id = id + "-" + v; b.setAttribute("aria-selected", pick[key] === v); b.textContent = label(v);
    b.onclick = () => { pick[key] = v; try { localStorage.setItem("bs-pick", JSON.stringify(pick)); } catch (e) {} render(); };
    el.appendChild(b); });
}
function tabs() {
  tabRow("tabs", SCEN, "name", v => DATA.find(d => d.name === v).title);
  tabRow("scales", SCALES, "scale", v => DATA.find(d => d.scale === v).scale_label);
  document.getElementById("scales").hidden = SCALES.length < 2;
  document.getElementById("scalenote").textContent = pick.scale === "pilot"
    ? "Pilot scale is what the real pilot would run. Expect wide intervals."
    : "Powered scale is simulated only. It shows whether the same analysis can find the built-in effect with more lineages.";
  document.getElementById("simbanner").hidden = !DATA.some(d => d.simulated);
}

function linePlot(series, title, yLabel) {
  const W = 460, H = 210, L = 34, R = 10, T = 10, B = 28;
  const all = series.flatMap(s => s.y);
  const xs = Math.max(...series.map(s => s.y.length)) - 1;
  const yMin = Math.floor(Math.min(...all) - 1), yMax = Math.ceil(Math.max(...all) + 1);
  const X = i => L + (W - L - R) * i / Math.max(1, xs), Y = v => T + (H - T - B) * (1 - (v - yMin) / (yMax - yMin));
  let g = "";
  const step = Math.max(1, Math.round((yMax - yMin) / 4));
  for (let v = yMin; v <= yMax; v += step) g += `<line x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}" stroke="${css('--grid')}"/><text x="${L - 6}" y="${Y(v) + 4}" text-anchor="end">${v}</text>`;
  for (let i = 0; i <= xs; i += Math.max(1, Math.ceil(xs / 8))) g += `<text x="${X(i)}" y="${H - 10}" text-anchor="middle">${i}</text>`;
  g += `<text x="${W - R}" y="${H}" text-anchor="end">generation</text>`;
  series.forEach(s => {
    const pts = s.y.map((v, i) => `${X(i)},${Y(v)}`).join(" ");
    g += `<polyline points="${pts}" fill="none" stroke="${s.color}" stroke-width="2" ${s.dash ? 'stroke-dasharray="5 4"' : ""} stroke-linejoin="round" opacity="${s.dash ? 0.8 : 1}"/>`;
    s.y.forEach((v, i) => g += `<circle cx="${X(i)}" cy="${Y(v)}" r="7" fill="transparent" data-tip="${esc(s.label)} &middot; gen ${i}: ${v}"/>`);
    const last = s.y.length - 1;
    g += `<circle cx="${X(last)}" cy="${Y(s.y[last])}" r="3.5" fill="${s.color}" stroke="${css('--panel')}" stroke-width="2"/>`;
  });
  return `<div class="chart"><h3>${title}</h3><svg class="plot" viewBox="0 0 ${W} ${H}" role="img" aria-label="${title}">${g}</svg></div>`;
}

function renderLineages(d) {
  const color = m => m === "A" ? css("--a") : css("--b");
  const charts = ["A", "B"].map(m => {
    const s = [];
    (d.lines.evolution || []).filter(l => l.model === m).forEach(l => s.push({y: l.bar, color: color(m), label: `evolution ${l.name} (${l.proc} procedure edits kept)`}));
    ["frozen", "onegen"].forEach(g => (d.lines[g] || []).filter(l => l.model === m).forEach(l => s.push({y: l.bar, color: css("--muted"), dash: true, label: `${g} ${l.name}`})));
    return linePlot(s, `Model ${m}`, "dev bar");
  });
  document.getElementById("lineage").innerHTML = charts.join("");
}

function renderMatrices(d) {
  const last = Math.max(...d.checkpoints);
  const want = [["orig", 0], ["orig", last], ["norm", last], ["neutral", last]];
  const html = want.map(([p, ck]) => {
    const r = d.rows.find(x => x.pres === p && x.checkpoint === ck);
    if (!r) return "";
    const m = r.matrix, cell = (o, x) => `<td class="${o === x ? "home" : ""}" data-tip="evolved by ${o}, run by ${x}: ${m[o + "->" + x].toFixed(2)} tasks">${fmt(m[o + "->" + x])}</td>`;
    return `<div class="mx"><h3>${p === "orig" ? "As evolved" : p === "norm" ? "Normalized" : "Neutral names"} &middot; gen ${ck}</h3>
      <table><tr><th></th><th>run by A</th><th>run by B</th></tr>
      <tr><th class="row">evolved by A</th>${cell("A", "A")}${cell("A", "B")}</tr>
      <tr><th class="row">evolved by B</th>${cell("B", "A")}${cell("B", "B")}</tr></table>
      <div class="s">home advantage S = ${fmt(r.S, 2)} tasks</div></div>`;
  }).join("");
  document.getElementById("matrices").innerHTML = html;
}

function renderDS(d) {
  const rows = d.rows.filter(r => r.checkpoint > 0);
  const W = 560, rowH = 46, L = 92, R = 20, T = 16, H = T + rows.length * rowH + 30;
  const lo = Math.min(-4, ...rows.map(r => r.dS_ci ? r.dS_ci[0] : r.dS)), hi = Math.max(4, ...rows.map(r => r.dS_ci ? r.dS_ci[1] : r.dS));
  const X = v => L + (W - L - R) * (v - lo) / (hi - lo);
  let g = "";
  const step = Math.max(1, Math.round((hi - lo) / 6));
  for (let v = Math.ceil(lo); v <= hi; v += step) g += `<line x1="${X(v)}" x2="${X(v)}" y1="${T}" y2="${H - 26}" stroke="${css('--grid')}"/><text x="${X(v)}" y="${H - 10}" text-anchor="middle">${v}</text>`;
  g += `<line x1="${X(0)}" x2="${X(0)}" y1="${T - 6}" y2="${H - 26}" stroke="${css('--zero')}" stroke-width="1.5"/>`;
  rows.forEach((r, i) => {
    const y = T + i * rowH + rowH / 2, c = r.dS_ci;
    g += `<text x="${L - 10}" y="${y + 4}" text-anchor="end" style="fill:${css('--ink-2')}">${r.pres} &middot; g${r.checkpoint}</text>`;
    if (c) g += `<line x1="${X(c[0])}" x2="${X(c[1])}" y1="${y}" y2="${y}" stroke="${css('--ink-2')}" stroke-width="2" stroke-linecap="round"/>`;
    g += `<circle cx="${X(r.dS)}" cy="${y}" r="5.5" fill="${css('--ink')}" stroke="${css('--panel')}" stroke-width="2"/>`;
    g += `<rect x="${L}" y="${y - rowH / 2}" width="${W - L - R}" height="${rowH}" fill="transparent" data-tip="${r.pres}, checkpoint ${r.checkpoint}: dS ${fmt(r.dS, 2)}${c ? ` (95% CI ${fmt(c[0], 1)} to ${fmt(c[1], 1)})` : ""}"/>`;
  });
  g += `<text x="${W - R}" y="${H}" text-anchor="end">dS, tasks (positive = specialization grew)</text>`;
  document.getElementById("dschart").innerHTML = `<svg class="plot" viewBox="0 0 ${W} ${H + 4}" role="img" aria-label="Specialization growth by presentation">${g}</svg>`;
}

function renderText(d) {
  document.getElementById("blurb").textContent = d.blurb;
  document.getElementById("params").textContent = d.params ? "built-in effects: " + Object.entries(d.params).map(([k, v]) => `${k}=${v}`).join("  ") : "";
  document.getElementById("verdicts").innerHTML = d.verdicts.map(v => `<li>${esc(v)}</li>`).join("");
  const c = d.cost || {};
  const info = Object.entries(d.presentation_info || {}).map(([p, x]) => `${p}: ${Math.round(x.tokens_before)}&rarr;${Math.round(x.tokens_after)} tokens, coverage ${(100 * (x.coverage || 0)).toFixed(0)}%`).join(" &middot; ");
  document.getElementById("cost").innerHTML = `<div>${d.simulated ? "Simulated" : "Actual"} cost: $${(c.total_usd || 0).toFixed(2)} over ${c.calls || 0} model calls${d.simulated ? " (mock token counts at real list prices; real runs use more output tokens)" : ""}.</div><div>Procedure source as shown to the model: ${info}</div>`;
  const head = "<tr><th>presentation</th><th>checkpoint</th><th>S</th><th>dS</th><th>dS 95% CI</th><th>A&rarr;A</th><th>A&rarr;B</th><th>B&rarr;A</th><th>B&rarr;B</th></tr>";
  const body = d.rows.map(r => `<tr><td>${r.pres}</td><td>${r.checkpoint}</td><td>${fmt(r.S, 2)}</td><td>${r.dS !== undefined ? fmt(r.dS, 2) : ""}</td><td>${r.dS_ci ? fmt(r.dS_ci[0], 1) + " .. " + fmt(r.dS_ci[1], 1) : ""}</td>${["A->A", "A->B", "B->A", "B->B"].map(k => `<td>${fmt(r.matrix[k], 2)}</td>`).join("")}</tr>`).join("");
  document.getElementById("table").innerHTML = `<table class="data">${head}${body}</table>`;
}

function render() { const d = current(); pick = {name: d.name, scale: d.scale}; tabs(); renderText(d); renderLineages(d); renderMatrices(d); renderDS(d); }
document.addEventListener("mousemove", e => { const t = e.target.closest && e.target.closest("[data-tip]"); t ? showTip(e, t.getAttribute("data-tip")) : hideTip(); });
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", render);
new MutationObserver(render).observe(document.documentElement, {attributes: true, attributeFilter: ["data-theme"]});
render();
</script>
"""
