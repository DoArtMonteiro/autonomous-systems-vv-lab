"""Page and script of the Mission Control M10 navigation workbench (/workbench, /workbench.js).

The page asks the server for the landing adapter's description and the committed journeys
(GET /api/workbench), runs up to four policies on one seed and fault set (POST /api/workbench/compare),
replays a stored run (POST /api/workbench/replay) and links its evidence package
(GET /api/workbench/evidence/<run_id>). Every chart is inline SVG drawn by this script from the run's
recorded trace, verification and case; nothing is loaded from the network and no markup is parsed
(no innerHTML). Policies and faults come from the adapter description, so a new policy appears
without a change here.

Truth series are labelled as simulator truth that the controller never sees; estimates and
declarations are labelled as the controller's. `untrusted` is shown as a declaration, not a safe state.
"""

from __future__ import annotations

WORKBENCH_CSS = """
:root{--c1:#2a78d6;--c2:#d4561e;--c3:#0f8a6a;--c4:#8a4fc7;--band:#2a78d633;--fault:#b4231814;--fault-line:#b42318;
--st-good:#3d9a5f;--st-warn:#d39a1d;--st-bad:#c8372d;--st-off:#77746d;--st-none:#c9c6bf}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--c1:#5aa2f0;--c2:#f08350;--c3:#3cc4a0;--c4:#b58af0;
--band:#5aa2f040;--fault:#ff7b6b1c;--fault-line:#ff7b6b;--st-good:#4cb874;--st-warn:#e0b54a;--st-bad:#f0645a;
--st-off:#8f8c84;--st-none:#45433f}}
main{max-width:1400px}
.top{display:flex;flex-wrap:wrap;gap:4px 14px;align-items:baseline}
.top h1{margin:0}
.validity{border-left:4px solid var(--warn);background:var(--panel);padding:8px 12px;margin:12px 0;font-size:13.5px;max-width:none}
.layout{display:grid;grid-template-columns:330px minmax(0,1fr);gap:20px;align-items:start}
@media (max-width:980px){.layout{grid-template-columns:minmax(0,1fr)}}
.setup{position:sticky;top:8px;max-height:calc(100vh - 16px);overflow:auto}
@media (max-width:980px){.setup{position:static;max-height:none;overflow:visible}}
.setup .panel{margin:0 0 12px}
.setup h2,.results h2{border:0;margin:0 0 8px;padding:0;font-size:16px}
button,select,input{font:inherit;font-size:14px;padding:5px 9px;border:1px solid var(--line);border-radius:7px;background:var(--surface);
color:var(--text);min-height:34px;max-width:100%}
button{cursor:pointer}
button:focus-visible,select:focus-visible,input:focus-visible,a:focus-visible,[tabindex]:focus-visible{outline:3px solid var(--s1);outline-offset:2px}
button.primary{background:var(--s1);color:#fff;border-color:var(--s1);font-weight:700}
button:disabled,input:disabled,select:disabled{opacity:.5;cursor:not-allowed}
a.button{display:inline-flex;align-items:center;min-height:34px;padding:5px 12px;border:1px solid var(--line);border-radius:7px;
color:var(--text);text-decoration:none;background:var(--surface)}
label.field{display:grid;gap:2px;font-size:13px;color:var(--text2);margin:6px 0;min-width:0}
label.field select{width:100%}
.row{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px}
.row input{width:100%}
fieldset{border:1px solid var(--line);border-radius:9px;padding:8px 10px;margin:8px 0;min-width:0}
legend{font-weight:600;font-size:13px;padding:0 4px}
.check{display:flex;gap:8px;align-items:flex-start;padding:4px 2px;font-size:13.5px}
.check input{min-height:auto;margin-top:3px}
.check small{display:block;color:var(--muted)}
.journeys{display:grid;gap:8px}
.journey{text-align:left;display:grid;gap:2px;padding:8px 10px;border-radius:9px}
.journey b{font-size:14px}.journey span{font-size:12.5px;color:var(--muted)}
.journey[aria-pressed="true"]{border:2px solid var(--s1)}
.hint{font-size:12px;color:var(--muted);margin:2px 0}
.alert{border:2px solid var(--bad);border-radius:8px;padding:8px 12px;color:var(--text)}
.story{border-left:4px solid var(--s1);padding:6px 12px;background:var(--panel);border-radius:0 10px 10px 0;margin:0 0 12px}
.story p{margin:4px 0}.story ul{margin:4px 0;padding-left:20px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:8px;margin:0 0 10px}
.card{border:1px solid var(--line);border-left:6px solid var(--line);border-radius:9px;padding:8px 10px;text-align:left;display:grid;gap:3px;
background:var(--surface);min-width:0}
.card[aria-pressed="true"]{box-shadow:0 0 0 2px var(--text) inset}
.card .p{font-weight:700;font-family:ui-monospace,Consolas,monospace;font-size:13.5px}
.card .o{font-size:13px;color:var(--text2)}.card .live{font-size:12px;color:var(--muted);font-variant-numeric:tabular-nums}
.cls{display:inline-block;min-width:24px;text-align:center;font-weight:800;border-radius:5px;padding:0 6px;color:#fff;margin-right:6px}
.cls-R{background:var(--st-good)}.cls-T{background:var(--st-warn);color:#1a1a19}.cls-U{background:var(--st-bad)}.cls-x{background:var(--st-off)}
.c1{border-left-color:var(--c1)}.c2{border-left-color:var(--c2)}.c3{border-left-color:var(--c3)}.c4{border-left-color:var(--c4)}
.timebar{position:sticky;top:0;z-index:2;background:var(--surface);border-bottom:1px solid var(--line);padding:6px 0;display:flex;flex-wrap:wrap;
gap:6px 10px;align-items:center}
.timebar input[type=range]{flex:1;min-width:160px}
.timebar output{font-variant-numeric:tabular-nums;font-weight:700;min-width:7ch}
.readout{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:8px;margin:8px 0}
.readout section{background:var(--panel);border-radius:9px;padding:8px 10px;min-width:0}
.readout h3{margin:0 0 4px;font-size:13px}
dl.kv{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:1px 10px;margin:0;font-size:13px;font-variant-numeric:tabular-nums}
dl.kv dt{color:var(--muted)}dl.kv dd{margin:0;overflow-wrap:anywhere}
.charts{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,460px),1fr));gap:12px}
.chart{background:var(--panel);border-radius:10px;padding:10px 10px 6px;margin:0;min-width:0}
.chart.wide{grid-column:1/-1}
.chart h3{margin:0;font-size:14px}.chart figcaption{font-size:12px;color:var(--muted);margin:4px 0 0}
.chart .src{font-size:11.5px;color:var(--muted);margin:0 0 4px}
.chart svg{width:100%;height:auto;display:block;touch-action:none;cursor:crosshair}
.chart svg text{font:11px system-ui,sans-serif;fill:var(--text2)}
.chart svg .lbl{fill:var(--text);font-weight:600}
.ax{stroke:var(--line);stroke-width:1}.gridl{stroke:var(--line);stroke-width:1;stroke-dasharray:2 3}
.ln{fill:none;stroke-width:1.8;stroke-linejoin:round;stroke-linecap:round}
.ln.est{stroke-dasharray:5 3;stroke-width:1.6}.ln.thin{stroke-width:1.2}
.s1{stroke:var(--c1)}.s2{stroke:var(--c2)}.s3{stroke:var(--c3)}.s4{stroke:var(--c4)}
.f1{fill:var(--c1)}.f2{fill:var(--c2)}.f3{fill:var(--c3)}.f4{fill:var(--c4)}
.ln.truth{stroke:var(--text)}.ln.radar{stroke:var(--c2)}.ln.gnss{stroke:var(--c3)}.ln.diff{stroke:var(--c4)}
.ln.lim{stroke:var(--st-bad);stroke-dasharray:1 3;stroke-width:1.4}.ln.h{stroke:var(--st-bad);stroke-width:1.2;stroke-dasharray:6 3}
.band{fill:var(--band);stroke:none}
.fw{fill:var(--fault)}.fwl{stroke:var(--fault-line);stroke-width:1;stroke-dasharray:3 2}
.cursor{stroke:var(--text);stroke-width:1.5}
.mk{stroke:var(--text2);stroke-width:1;stroke-dasharray:2 2}
.pad{stroke:var(--st-good);stroke-width:4}.r5{fill:none;stroke:var(--st-good);stroke-width:1.5}.ko{fill:none;stroke:var(--st-bad);stroke-width:1;stroke-dasharray:5 4}
.dot{stroke:var(--surface);stroke-width:1.5}.hollow{fill:var(--surface);stroke-width:2}
.st-good{fill:var(--st-good)}.st-warn{fill:var(--st-warn)}.st-bad{fill:var(--st-bad)}.st-off{fill:var(--st-off)}.st-none{fill:var(--st-none)}
.iso-correct{fill:var(--st-good)}.iso-before_onset{fill:var(--st-warn)}.iso-wrong{fill:var(--st-bad)}
.lane-text{font-size:10px!important;fill:#fff!important;pointer-events:none}
.legend{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:12px;color:var(--text2);margin:4px 0 0}
.key{display:inline-block;width:18px;height:0;border-top:2px solid currentColor;vertical-align:middle;margin-right:5px}
.key.d{border-top-style:dashed}.key.box{height:10px;border:0;border-radius:2px}
.why{display:grid;grid-template-columns:minmax(0,1fr);gap:10px}
.results,.setup{min-width:0}
.why .panel{margin:0}
.why h3{margin:0 0 6px;font-size:14px}
.why table{font-size:13px}
.ok{color:var(--good)}.bad{color:var(--bad)}.warn{color:var(--warn)}
.note{font-size:12.5px;color:var(--muted)}
.controls{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:6px 0}
.scroll table{min-width:440px}
[hidden]{display:none!important}
@media (max-width:480px){main{padding:16px 16px 48px}.row{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}
.row label:first-child{grid-column:1/-1}h1{font-size:22px}}
@media (prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
"""


def workbench_page(css: str) -> str:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>M10 navigation workbench</title>
<style>{css}{WORKBENCH_CSS}</style></head>
<body><main>
<p class="meta"><a href="/">Mission Control</a> · <a href="/landing">Powered landing</a> · M10 navigation workbench · local simulator runs on this computer</p>
<div class="top"><h1>M10 navigation workbench</h1><span class="meta" id="model-line"></span></div>
<p class="validity" id="validity"><b>Idealized demonstrator, development configuration.</b> The M10 navigation is still being tuned on
development seeds; nothing here is an evaluation result, flight software, certified or validated against flight data or hardware.
Requirements, dispersions and sensor models are assumed values.</p>
<div class="layout">
<aside class="setup" aria-label="Run setup">
<section class="panel" aria-labelledby="journeys-h"><h2 id="journeys-h">Demonstration journeys</h2>
<div class="journeys" id="journeys"><p class="hint">Loading…</p></div></section>
<section class="panel" aria-labelledby="setup-h"><h2 id="setup-h">Run setup</h2><div id="setup"></div></section>
</aside>
<div class="results">
<p id="status" role="status" aria-live="polite" class="meta"></p>
<div id="error" role="alert"></div>
<section id="story" aria-label="Journey" hidden></section>
<section id="result" aria-label="Results"><p class="note">Pick a journey or set up a run. Each run is the Rust simulator on this
computer; its trace, verification and replay are shown as recorded.</p></section>
</div>
</div>
<noscript>The workbench needs JavaScript.</noscript>
<script src="/workbench.js"></script>
</main></body></html>
"""


WORKBENCH_JS = r"""
'use strict';
const SVGNS = 'http://www.w3.org/2000/svg';
const TRUTH = 'simulator truth (verifier only, never seen by the controller)';
const CONTROLLER = 'controller (estimate and declarations)';
const UNTRUSTED_NOTE = 'untrusted is a declaration, not a safe state';
const SAMPLED = 'Trace samples every 0.1 s; the navigation runs at 50 Hz, so short excursions between samples are not drawn.';
const REQUEST_SCHEMA = 'vv-sim-run-request.v3';
const $ = id => document.getElementById(id);
function el(tag, attrs, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') n.className = v; else if (k.startsWith('on')) n.addEventListener(k.slice(2), v); else n.setAttribute(k, v === true ? '' : v);
  }
  for (const k of kids.flat(Infinity)) if (k !== null && k !== undefined && k !== false) n.append(k instanceof Node ? k : String(k));
  return n;
}
function sv(tag, attrs, ...kids) {
  const n = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs || {})) if (v !== null && v !== undefined) n.setAttribute(k, v);
  for (const k of kids.flat(Infinity)) if (k !== null && k !== undefined) n.append(k instanceof Node ? k : String(k));
  return n;
}
const fx = (v, d = 1) => (v === null || v === undefined || !isFinite(v)) ? 'n/a' : Number(v).toFixed(d);
const g3 = v => (v === null || v === undefined) ? 'n/a' : String(Number(Number(v).toPrecision(3)));
const words = s => String(s).replaceAll('_', ' ');
const hyp = (a, b) => Math.hypot(a, b);
const state = {wb: null, caps: null, runs: [], focus: 0, t: 0, tMax: 0, timer: null, busy: false, journey: null, cursors: [], replays: {}};

// ---------------------------------------------------------------- status and errors
function setStatus(text) { $('status').textContent = text; }
function setError(text) { $('error').replaceChildren(text ? el('p', {class: 'alert'}, el('b', {}, 'Not run: '), text) : ''); }

// ---------------------------------------------------------------- setup form
const policyInfo = id => state.caps.policies.find(p => p.id === id);
const faultInfo = kind => state.caps.faults.find(f => f.kind === kind);
function protectedSeed(seed) { return state.caps.seed.protected.find(r => seed >= r.min && seed <= r.max); }

function faultRow(i) {
  const kind = el('select', {id: `f${i}-kind`, 'aria-describedby': `f${i}-hint`},
    el('option', {value: ''}, i === 0 ? 'none (nominal)' : 'none'),
    state.caps.faults.map(f => el('option', {value: f.kind}, f.label)));
  const num = (id, label) => el('label', {class: 'field'}, label, el('input', {type: 'number', id, step: 'any', inputmode: 'decimal'}));
  const hint = el('p', {class: 'hint', id: `f${i}-hint`});
  kind.addEventListener('change', () => { fillFaultDefaults(i); gatePolicies(); });
  return el('fieldset', {}, el('legend', {}, `Fault ${i + 1}`), el('label', {class: 'field'}, 'Kind', kind),
    el('div', {class: 'row'}, num(`f${i}-mag`, 'Magnitude'), num(`f${i}-start`, 'Start (s)'), num(`f${i}-end`, 'End (s)')), hint);
}
function fillFaultDefaults(i, given) {
  const kind = $(`f${i}-kind`).value, info = faultInfo(kind);
  const mag = $(`f${i}-mag`), start = $(`f${i}-start`), end = $(`f${i}-end`), hint = $(`f${i}-hint`);
  for (const n of [mag, start, end]) n.disabled = !info;
  if (!info) { mag.value = start.value = end.value = ''; hint.textContent = ''; return; }
  mag.disabled = !info.magnitude;
  mag.value = given ? (info.magnitude ? given.magnitude : '') : (info.magnitude ? info.magnitude.default : '');
  start.value = given ? given.start_s : info.default_start_s;
  end.value = given ? given.end_s : info.default_end_s;
  const parts = [info.description];
  if (info.magnitude) parts.push(`Magnitude ${g3(info.magnitude.min)} to ${g3(info.magnitude.max)} ${info.magnitude.unit}.`);
  else parts.push('No magnitude.');
  if (info.window_length_s) parts.push(`Window ${g3(info.window_length_s.min)} to ${g3(info.window_length_s.max)} s long.`);
  if (info.policies) parts.push(`Exists only for ${info.policies.join(', ')} (case schema v2).`);
  hint.textContent = parts.join(' ');
}
function selectedFaults() {
  const out = [];
  for (const i of [0, 1]) {
    const kind = $(`f${i}-kind`).value; if (!kind) continue;
    const n = id => { const v = $(id).value.trim(); return v === '' ? null : Number(v); };
    out.push({kind, magnitude: faultInfo(kind).magnitude ? n(`f${i}-mag`) : 0, start_s: n(`f${i}-start`), end_s: n(`f${i}-end`)});
  }
  return out;
}
// A journey keeps its own policy order (the first is the focus); otherwise the adapter's order.
function selectedPolicies() {
  const chosen = [...document.querySelectorAll('input[name=policy]:checked')].map(n => n.value), order = state.order || [];
  const rank = p => (order.indexOf(p) + 1) || order.length + 1 + chosen.indexOf(p);
  return chosen.sort((a, b) => rank(a) - rank(b));
}
// A fault that exists only for some policies disables the others, with the reason; the server refuses them anyway.
function gatePolicies() {
  const limits = selectedFaults().map(f => faultInfo(f.kind).policies).filter(Boolean);
  const allowed = id => limits.every(l => l.includes(id));
  const max = state.wb.compare_max, chosen = selectedPolicies();
  for (const box of document.querySelectorAll('input[name=policy]')) {
    const ok = allowed(box.value);
    if (!ok) box.checked = false;
    box.disabled = !ok || (!box.checked && chosen.length >= max);
    const why = $(`why-${box.value}`);
    why.textContent = !ok ? 'Not available with the selected fault (case schema v2 only).' : '';
  }
  $('policy-count').textContent = `${selectedPolicies().length} of at most ${max} selected; all run on the same seed and faults.`;
}
function checkSeed() {
  const v = $('seed').value.trim(), seed = Number(v), msg = $('seed-msg');
  const range = Number.isInteger(seed) ? protectedSeed(seed) : null;
  $('seed').setAttribute('aria-invalid', range ? 'true' : 'false');
  msg.className = range ? 'hint bad' : 'hint';
  msg.textContent = range ? `Seed ${seed} is an ${range.use} seed (${range.min} to ${range.max}); the server refuses it before anything runs.`
    : `Development seeds ${state.caps.seed.development.min} to ${state.caps.seed.development.max}. ${state.caps.seed.protected.map(r => `${r.min} to ${r.max} (${r.use})`).join(' and ')} are refused.`;
  return !range;
}
function drawSetup() {
  const caps = state.caps, model = state.wb.landing.model;
  const policies = el('fieldset', {}, el('legend', {}, 'Controller policies (compare up to ' + state.wb.compare_max + ')'),
    caps.policies.map(p => el('label', {class: 'check'},
      el('input', {type: 'checkbox', name: 'policy', value: p.id, onchange: gatePolicies}),
      el('span', {}, el('code', {}, p.id), p.navigation_declarations ? ' · declares navigation' : '',
        el('small', {}, p.description), el('small', {class: 'warn', id: `why-${p.id}`}))),
    ), el('p', {class: 'hint', id: 'policy-count'}));
  const seed = el('label', {class: 'field'}, 'Seed', el('input', {type: 'number', id: 'seed', value: caps.seed.development.min, min: caps.seed.min,
    max: caps.seed.max, step: 1, inputmode: 'numeric', 'aria-describedby': 'seed-msg', oninput: checkSeed}));
  $('setup').replaceChildren(
    el('label', {class: 'field'}, 'Vehicle and model', el('select', {id: 'model'}, el('option', {value: model.id}, `${model.id} (6-DOF stage, closed loop)`))),
    el('label', {class: 'field'}, 'Mission', el('select', {id: 'mission'}, el('option', {value: 'nominal'}, 'Powered landing from about 3 km, nominal case'))),
    el('p', {class: 'hint'}, 'Same vehicle, initial state, dispersions, sensors and requirements for every policy. M10 policies run on ',
      el('code', {}, 'm10-nominal.json'), ' (case schema v2, with the navigation block); the M9 policies on their own templates, whose controller gains differ.'),
    policies, faultRow(0), faultRow(1), seed, el('p', {class: 'hint', id: 'seed-msg'}),
    el('button', {class: 'primary', id: 'run', onclick: () => runCompare(null)}, 'Run'));
  for (const id of ['m10_b_plus', 'm10_a']) { const b = document.querySelector(`input[name=policy][value="${id}"]`); if (b) b.checked = true; }
  if (!selectedPolicies().length) document.querySelector('input[name=policy]').checked = true;
  fillFaultDefaults(0); fillFaultDefaults(1); gatePolicies(); checkSeed();
}
function drawJourneys() {
  $('journeys').replaceChildren(...state.wb.journeys.map(j => el('button', {class: 'journey', 'aria-pressed': 'false', 'data-j': j.id,
    onclick: () => loadJourney(j)}, el('b', {}, j.title), el('span', {}, `${j.policies.join(' vs ')} · seed ${j.seed} · ${j.faults.length ? j.faults.map(f => words(f.kind)).join(' + ') : 'no fault'}`))));
}
function loadJourney(j) {
  document.querySelectorAll('.journey').forEach(b => b.setAttribute('aria-pressed', b.getAttribute('data-j') === j.id ? 'true' : 'false'));
  state.order = j.policies.slice();
  for (const box of document.querySelectorAll('input[name=policy]')) { box.checked = j.policies.includes(box.value); box.disabled = false; }
  for (const i of [0, 1]) { const f = j.faults[i]; $(`f${i}-kind`).value = f ? f.kind : ''; fillFaultDefaults(i, f); }
  $('seed').value = j.seed; checkSeed(); gatePolicies();
  runCompare(j);
}

// ---------------------------------------------------------------- run
async function runCompare(journey) {
  if (state.busy) return;
  setError('');
  if (!checkSeed()) { setError($('seed-msg').textContent); return; }
  const policies = selectedPolicies();
  if (!policies.length) { setError('choose at least one policy.'); return; }
  const body = {schema: state.wb.compare_schema, policies, seed: Number($('seed').value), faults: selectedFaults()};
  state.busy = true; $('run').disabled = true; $('run').setAttribute('aria-busy', 'true');
  setStatus(`Running ${policies.length} ${policies.length === 1 ? 'policy' : 'policies'} one after the other on seed ${body.seed}…`);
  try {
    const resp = await fetch('/api/workbench/compare', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    const data = await resp.json().catch(() => ({error: `server answered ${resp.status} without JSON`}));
    if (!resp.ok || data.error || !Array.isArray(data.runs)) {
      setError(data.error || `server answered ${resp.status}`);
      setStatus(state.runs.length ? 'Nothing was run; the results below are from the previous run.' : '');
      return;
    }
    stop();
    state.journey = journey; state.runs = data.runs.map(prepare); state.focus = 0; state.replays = {};
    state.tMax = Math.max(...state.runs.map(r => r.tEnd));
    const first = state.runs[0];
    state.t = firstInteresting(first);
    drawStory(); drawResult();
    const bad = state.runs.filter(r => !r.verified).length;
    setStatus(`${state.runs.length} run${state.runs.length > 1 ? 's' : ''} finished on seed ${body.seed}. ` +
      (bad ? `${bad} did not verify (stored files differ from a fresh regeneration or replay); their outcomes are withheld.` : 'Every run verified by replay and integrity checks.'));
    $('result-h').focus();
  } catch (e) {
    setError('the local server did not respond. Is mission_control.py still running?');
  } finally {
    state.busy = false; $('run').disabled = false; $('run').removeAttribute('aria-busy');
  }
}
function firstInteresting(run) {
  const f = run.faults.map(x => x.start_s).filter(s => s > 0.5 && s < run.tEnd);
  return f.length ? Math.min(...f) : Math.min(run.tEnd, 10);
}

// ---------------------------------------------------------------- data model of one run
function deriveClass(v) {
  if (!v || !Array.isArray(v.requirements) || !Array.isArray(v.invariants)) return null;
  if (v.outcome === 'no_contact') return 'U';
  if (v.invariants.some(i => !i.pass)) return 'U';
  const failed = v.requirements.filter(r => !r.pass).map(r => r.id.slice(0, 2));
  if (failed.some(id => id !== 'R5')) return 'U';
  return failed.length ? 'T' : 'R';
}
function prepare(raw, i) {
  const S = raw.states || [], v = raw.verification || {}, nav = v.navigation || null;
  const cnav = raw.case && raw.case.controller && raw.case.controller.nav ? raw.case.controller.nav : null;
  const hasNav = S.length > 0 && S[0].estimate && S[0].estimate.nav !== undefined && S[0].estimate.nav !== null;
  const derived = deriveClass(v);
  const verified = raw.verdict && raw.verdict.status === 'verified';
  return {
    raw, i, id: raw.run_id, policy: raw.request.policy, seed: raw.request.seed, faults: raw.request.faults || [], S, v, nav, cnav, hasNav, verified,
    t: S.map(s => s.t_s), tEnd: S.length ? S[S.length - 1].t_s : 0,
    k: cnav && typeof cnav.k_ff === 'number' ? cnav.k_ff : 3, kSource: cnav && typeof cnav.k_ff === 'number' ? 'k = k_ff from the case' : 'k = 3 (no k_ff in the case)',
    h: cnav && typeof cnav.cusum_h === 'number' ? cnav.cusum_h : null, suspect: cnav && typeof cnav.suspect_cusum_fraction === 'number' ? cnav.suspect_cusum_fraction : null,
    cls: nav && nav.physical_class ? nav.physical_class : derived, clsSource: nav && nav.physical_class ? 'verifier' : 'derived', derived,
    color: `c${(i % 4) + 1}`, n: (i % 4) + 1,
  };
}
function sampleAt(run, t) {
  const T = run.t; if (!T.length) return null;
  let lo = 0, hi = T.length - 1;
  if (t >= T[hi]) return run.S[hi];
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (T[m] <= t) lo = m; else hi = m; }
  return run.S[t - T[lo] <= T[hi] - t ? lo : hi];
}
const N = s => s && s.estimate && s.estimate.nav ? s.estimate.nav : null;
const cut = run => (run.raw.summary || {}).cutoff_t_s;
const groupOf = kind => kind.startsWith('altimeter') ? 'radar' : kind.startsWith('gnss') ? 'gnss' : kind.startsWith('imu') ? 'imu' : null;

// ---------------------------------------------------------------- scales and chart frame
function ticks(lo, hi, n) {
  const span = hi - lo || 1, step0 = span / n, mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= step0) || mag * 10;
  const out = []; for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) out.push(+v.toFixed(10));
  return out;
}
function domain(values, pad = 0.06, floor = null) {
  const xs = values.filter(v => v !== null && v !== undefined && isFinite(v));
  if (!xs.length) return [0, 1];
  let lo = Math.min(...xs), hi = Math.max(...xs);
  if (floor !== null) { lo = Math.min(lo, -floor); hi = Math.max(hi, floor); }
  if (hi - lo < 1e-9) { lo -= 1; hi += 1; }
  const p = (hi - lo) * pad; return [lo - p, hi + p];
}
let clipSeq = 0;
// A time chart: x is the shared time axis [0, tMax]; the frame registers its cursor line.
function timeFrame(box, {height = 190, y, ylabel, log = false}) {
  const W = Math.max(280, Math.round(box.clientWidth || 600)), H = height, L = 54, R = 12, T = 10, B = 26;
  const [y0, y1] = y;
  const ly = v => Math.log10(Math.max(v, 1e-6));
  const X = t => L + (t / (state.tMax || 1)) * (W - L - R);
  const Y = v => log ? T + (ly(y1) - ly(v)) / (ly(y1) - ly(y0)) * (H - T - B) : T + (y1 - v) / (y1 - y0) * (H - T - B);
  const svg = sv('svg', {viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: 'img'});
  const id = `clip${++clipSeq}`;
  svg.append(sv('defs', {}, sv('clipPath', {id}, sv('rect', {x: L, y: T, width: W - L - R, height: H - T - B}))));
  const plot = sv('g', {'clip-path': `url(#${id})`});
  const yt = log ? logTicks(y0, y1) : ticks(y0, y1, 4);
  for (const v of yt) { svg.append(sv('line', {class: 'gridl', x1: L, x2: W - R, y1: Y(v), y2: Y(v)})); svg.append(sv('text', {x: L - 6, y: Y(v) + 4, 'text-anchor': 'end'}, g3(v))); }
  timeTicks(svg, X, W, L, H);
  const ym = T + (H - T - B) / 2;
  svg.append(sv('text', {x: 11, y: ym, transform: `rotate(-90 11 ${ym})`, 'text-anchor': 'middle'}, ylabel || ''));
  svg.append(sv('line', {class: 'ax', x1: L, x2: L, y1: T, y2: H - B}), sv('line', {class: 'ax', x1: L, x2: W - R, y1: H - B, y2: H - B}));
  svg.append(plot);
  const f = {svg, plot, X, Y, W, H, L, R, T, B, y0, y1};
  faultWindows(f);
  const cur = sv('line', {class: 'cursor', y1: T, y2: H - B});
  svg.append(cur);
  state.cursors.push(t => { cur.setAttribute('x1', X(t)); cur.setAttribute('x2', X(t)); });
  scrubbable(svg, x => (x - L) / (W - L - R) * state.tMax);
  return f;
}
function timeTicks(svg, X, W, L, H) {
  const ts = ticks(0, state.tMax, Math.max(3, Math.floor((W - L) / 70)));
  for (const t of ts.slice(0, -1)) svg.append(sv('text', {x: X(t), y: H - 8, 'text-anchor': 'middle'}, g3(t)));
  svg.append(sv('text', {x: W - 12, y: H - 8, 'text-anchor': 'end', class: 'lbl'}, 't (s)'));
}
function logTicks(lo, hi) {
  const out = [];
  for (let e = Math.floor(Math.log10(lo)); e <= Math.ceil(Math.log10(hi)); e++) for (const m of [1, 2, 5]) { const v = m * Math.pow(10, e); if (v >= lo && v <= hi) out.push(v); }
  return out.length ? out : [lo, hi];
}
function scrubbable(svg, toT) {
  const go = e => { const r = svg.getBoundingClientRect(), vb = svg.viewBox.baseVal; const x = (e.clientX - r.left) / r.width * vb.width; setT(toT(x)); };
  svg.addEventListener('pointerdown', e => { stop(); svg.setPointerCapture && svg.setPointerCapture(e.pointerId); go(e); });
  svg.addEventListener('pointermove', e => { if (e.buttons) go(e); });
}
function faultWindows(f) {
  const run = state.runs[state.focus];
  run.faults.forEach((x, k) => {
    const a = f.X(Math.max(0, x.start_s)), b = f.X(Math.min(state.tMax, x.end_s));
    if (b <= a) return;
    f.plot.append(sv('rect', {class: 'fw', x: a, y: f.T, width: b - a, height: f.H - f.T - f.B}));
    f.plot.append(sv('line', {class: 'fwl', x1: a, x2: a, y1: f.T, y2: f.H - f.B}));
    f.plot.append(sv('text', {x: a + 3, y: f.T + 11 + 12 * k}, words(x.kind)));
  });
}
function path(f, pts) {
  let d = '', pen = false;
  for (const [t, v] of pts) {
    if (v === null || v === undefined || !isFinite(v)) { pen = false; continue; }
    d += `${pen ? 'L' : 'M'}${f.X(t).toFixed(1)} ${f.Y(v).toFixed(1)}`; pen = true;
  }
  return d;
}
function line(f, pts, cls) { f.plot.append(sv('path', {class: 'ln ' + cls, d: path(f, pts)})); }
function hline(f, v, cls, text) {
  if (v < f.y0 || v > f.y1) return;
  f.plot.append(sv('line', {class: 'ln ' + cls, x1: f.L, x2: f.W - f.R, y1: f.Y(v), y2: f.Y(v)}));
  if (text) f.plot.append(sv('text', {x: f.W - f.R - 4, y: f.Y(v) - 4, 'text-anchor': 'end'}, text));
}
function band(f, pts) {
  const ok = pts.filter(p => p[1] !== null && isFinite(p[1]) && isFinite(p[2]));
  if (ok.length < 2) return;
  const up = ok.map(([t, , hi]) => `${f.X(t).toFixed(1)} ${f.Y(hi).toFixed(1)}`), dn = ok.slice().reverse().map(([t, lo]) => `${f.X(t).toFixed(1)} ${f.Y(lo).toFixed(1)}`);
  f.plot.append(sv('path', {class: 'band', d: `M${up.join('L')}L${dn.join('L')}Z`}));
}
function eventMarks(f, run) {
  const s = run.raw.summary || {};
  for (const [t, text] of [[s.ignition_t_s, 'ignition'], [cut(run), 'cut'], [s.touchdown_t_s, 'touchdown']]) {
    if (t === null || t === undefined) continue;
    f.plot.append(sv('line', {class: 'mk', x1: f.X(t), x2: f.X(t), y1: f.T, y2: f.H - f.B}));
    f.plot.append(sv('text', {x: f.X(t) - 3, y: f.H - f.B - 4, 'text-anchor': 'end'}, text));
  }
}
function figure(id, title, src, caption, wide) {
  const box = el('div', {class: 'plot'});
  return {node: el('figure', {class: 'chart' + (wide ? ' wide' : ''), id}, el('h3', {}, title), src ? el('p', {class: 'src'}, src) : null, box,
    caption ? el('figcaption', {}, caption) : null), box};
}

// ---------------------------------------------------------------- charts
const runsForOverlay = () => state.runs.filter(r => r.verified);
function chartAltitude(box) {
  const runs = runsForOverlay(), F = runs[0] ? state.runs[state.focus] : null;
  const vals = runs.flatMap(r => r.S.map(s => s.truth.position_m[2]));
  const f = timeFrame(box, {y: domain(vals.concat([0])), ylabel: 'altitude (m)'});
  for (const r of runs) line(f, r.S.map(s => [s.t_s, s.truth.position_m[2]]), `s${r.n}`);
  if (F && F.verified) line(f, F.S.map(s => [s.t_s, s.estimate.position_m[2]]), `est s${F.n}`);
  eventMarks(f, state.runs[state.focus]);
  f.svg.setAttribute('aria-label', 'Centre-of-mass altitude over time, simulator truth for each policy and the focused controller estimate.');
  box.replaceChildren(f.svg);
}
function chartVz(box) {
  const runs = runsForOverlay(), F = state.runs[state.focus];
  const vals = runs.flatMap(r => r.S.map(s => s.truth.velocity_mps[2]));
  const f = timeFrame(box, {y: domain(vals.concat([0])), ylabel: 'vertical speed (m/s)'});
  hline(f, 0, 'thin truth', '');
  for (const r of runs) line(f, r.S.map(s => [s.t_s, s.truth.velocity_mps[2]]), `s${r.n}`);
  if (F.verified) line(f, F.S.map(s => [s.t_s, s.estimate.velocity_mps[2]]), `est s${F.n}`);
  eventMarks(f, F);
  f.svg.setAttribute('aria-label', 'Vertical speed over time, simulator truth for each policy and the focused controller estimate.');
  box.replaceChildren(f.svg);
}
function chartVerr(box) {
  const runs = runsForOverlay(), F = state.runs[state.focus];
  const err = r => r.S.map(s => [s.t_s, s.estimate.position_m[2] - s.truth.position_m[2]]);
  const errs = runs.flatMap(r => err(r).map(p => p[1]));
  const maxErr = Math.max(1.2, ...errs.map(Math.abs));
  const bandPts = F.verified && F.hasNav ? F.S.map(s => { const n = N(s), e = s.estimate.position_m[2] - s.truth.position_m[2]; return [s.t_s, e - F.k * n.sigma_z_m, e + F.k * n.sigma_z_m]; }) : [];
  // The band is centred on the error: the truth lies inside the declared band when 0 is inside it.
  const bandMax = bandPts.length ? Math.max(...bandPts.map(p => Math.max(Math.abs(p[1]), Math.abs(p[2])))) : 0;
  const lim = Math.min(Math.max(maxErr, Math.min(bandMax, 4 * maxErr + 2)) * 1.1, 60);
  const f = timeFrame(box, {y: [-lim, lim], ylabel: 'estimate − truth (m)'});
  if (bandPts.length) band(f, bandPts);
  hline(f, 0, 'thin truth', '');
  const al = F.S.map(s => [s.t_s, Math.max(1, 0.02 * Math.max(0, s.truth.base_position_m[2]))]);
  line(f, al, 'lim'); line(f, al.map(([t, v]) => [t, -v]), 'lim');
  for (const r of runs) line(f, err(r), `s${r.n}` + (r === F ? '' : ' thin'));
  eventMarks(f, F);
  f.svg.setAttribute('aria-label', `Vertical estimation error of each policy over time; band of plus or minus ${F.k} sigma_z around the focused error; alert limit lines.`);
  box.replaceChildren(f.svg);
  return lim;
}
function chartSensors(box) {
  const F = state.runs[state.focus];
  const radarErr = F.S.map(s => [s.t_s, s.observation.altimeter_m === null ? null : s.observation.altimeter_m - s.truth.base_position_m[2]]);
  const gnssErr = F.S.map(s => [s.t_s, s.observation.gnss_position_m ? s.observation.gnss_position_m[2] - s.truth.position_m[2] : null]);
  const f = timeFrame(box, {y: domain(radarErr.concat(gnssErr).map(p => p[1]).concat([0]), 0.08, 1), ylabel: 'sensor − truth (m)'});
  hline(f, 0, 'thin truth', '');
  line(f, radarErr, 'radar'); line(f, gnssErr, 'gnss');
  f.svg.setAttribute('aria-label', 'Radar altimeter error against the true nozzle-plane altitude, and GNSS altitude error against the true centre of mass, over time.');
  box.replaceChildren(f.svg);
}
function chartDisagree(box) {
  const F = state.runs[state.focus];
  const d = F.S.map(s => [s.t_s, s.observation.altimeter_m !== null && s.observation.gnss_position_m ? s.observation.altimeter_m - s.observation.gnss_position_m[2] : null]);
  const f = timeFrame(box, {height: 160, y: domain(d.map(p => p[1])), ylabel: 'radar − GNSS z (m)'});
  line(f, d, 'diff');
  f.svg.setAttribute('aria-label', 'Radar altitude minus GNSS altitude from the observations alone, over time.');
  box.replaceChildren(f.svg);
}
function chartCusum(box) {
  const F = state.runs[state.focus];
  const r = F.S.map(s => [s.t_s, N(s).cusum_radar]), g = F.S.map(s => [s.t_s, N(s).cusum_gnss]);
  const top = Math.max(F.h || 1, ...r.concat(g).map(p => p[1] || 0)) * 1.12;
  const f = timeFrame(box, {y: [0, top], ylabel: 'CUSUM'});
  if (F.h !== null) hline(f, F.h, 'h', `h = ${g3(F.h)}`);
  if (F.h !== null && F.suspect !== null && F.suspect < 1) hline(f, F.h * F.suspect, 'lim', `suspect ${g3(F.suspect)}·h`);
  line(f, r, 'radar'); line(f, g, 'gnss');
  f.svg.setAttribute('aria-label', `CUSUM statistics of the radar and GNSS against the threshold h = ${F.h}.`);
  box.replaceChildren(f.svg);
}
function chartSigma(box) {
  const F = state.runs[state.focus];
  const z = F.S.map(s => [s.t_s, N(s).sigma_z_m]), h = F.S.map(s => [s.t_s, N(s).sigma_h_m]);
  const vals = z.concat(h).map(p => p[1]).filter(v => v > 0);
  const lo = Math.min(...vals), hi = Math.max(...vals), log = hi / lo > 20;
  const f = timeFrame(box, {y: log ? [lo / 1.3, hi * 1.3] : [0, hi * 1.12], log, ylabel: log ? 'sigma (m, log)' : 'sigma (m)'});
  line(f, z, 'radar'); line(f, h, 'gnss');
  f.svg.setAttribute('aria-label', 'Declared standard deviations sigma_z and sigma_h over time.');
  box.replaceChildren(f.svg);
}
const STATE_CLASS = {nominal: 'st-good', healthy: 'st-good', trusted: 'st-good', degraded_nav: 'st-warn', degraded: 'st-warn', suspect: 'st-warn',
  probation: 'st-warn', excluded: 'st-off', untrusted: 'st-bad'};
const LANES = [['mode', 'nav mode'], ['radar', 'radar group'], ['gnss', 'GNSS group'], ['vertical', 'vertical channel'],
  ['horizontal_velocity', 'horiz. velocity'], ['horizontal_position', 'horiz. position']];
function chartLanes(box) {
  const W = Math.max(300, Math.round(box.clientWidth || 600)), L = 112, R = 12, lane = 17, gap = 3, head = 16;
  const runs = state.runs.filter(r => r.verified);
  const blocks = runs.map(r => r.hasNav ? LANES.length : 1);
  const H = head + blocks.reduce((a, b) => a + b * (lane + gap) + 14, 0) + 36;
  const X = t => L + (t / (state.tMax || 1)) * (W - L - R);
  const svg = sv('svg', {viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: 'img',
    'aria-label': 'Swimlane timeline of the navigation mode, group health and channel status of each policy, with fault windows, isolation and transition markers.'});
  const F = state.runs[state.focus];
  for (const x of F.faults) {
    const a = X(Math.max(0, x.start_s)), b = X(Math.min(state.tMax, x.end_s));
    if (b > a) svg.append(sv('rect', {class: 'fw', x: a, y: head - 2, width: b - a, height: H - head - 32}));
  }
  svg.append(sv('text', {x: L, y: 11}, F.faults.length ? 'shaded: ' + F.faults.map(x => `${words(x.kind)} ${fx(x.start_s, 1)} to ${fx(x.end_s, 1)} s`).join(' + ') : 'no fault injected'));
  let y = head;
  for (const r of runs) {
    svg.append(sv('text', {x: 4, y: y + 9, class: 'lbl'}, r.policy));
    svg.append(sv('rect', {x: 0, y: y + 1, width: 3, height: 10, class: `f${r.n}`}));
    y += 12;
    if (!r.hasNav) {
      svg.append(sv('text', {x: L, y: y + 12}, 'no navigation declarations (M9 policy)'));
      y += lane + gap + 2;
      continue;
    }
    for (const [key, label] of LANES) {
      svg.append(sv('text', {x: L - 6, y: y + 12, 'text-anchor': 'end'}, label));
      let k = 0;
      while (k < r.S.length) {
        const v = N(r.S[k])[key]; let j = k + 1;
        while (j < r.S.length && N(r.S[j])[key] === v) j++;
        const t0 = r.S[k].t_s, t1 = j < r.S.length ? r.S[j].t_s : r.tEnd;
        const x0 = X(t0), x1 = X(Math.max(t1, t0 + 0.1));
        svg.append(sv('rect', {x: x0, y, width: Math.max(1, x1 - x0), height: lane, class: STATE_CLASS[v] || 'st-none'}, sv('title', {}, `${label}: ${v} from ${fx(t0, 1)} s to ${fx(t1, 1)} s`)));
        if (x1 - x0 > 8 * String(v).length) svg.append(sv('text', {x: x0 + 4, y: y + 12, class: 'lane-text'}, words(v)));
        k = j;
      }
      y += lane + gap;
    }
    const nav = r.nav || {};
    const top = y - LANES.length * (lane + gap);
    for (const tr of nav.transitions || []) svg.append(sv('line', {class: 'mk', x1: X(tr.t_s), x2: X(tr.t_s), y1: top, y2: top + lane}, sv('title', {}, `${tr.from} → ${tr.to} at ${fx(tr.t_s, 2)} s`)));
    for (const e of nav.isolation_events || []) {
      const row = LANES.findIndex(l => l[0] === e.group), cy = top + (row < 0 ? 0 : row) * (lane + gap) + lane / 2, cx = X(e.t_s);
      svg.append(sv('path', {d: `M${cx} ${cy - 7}L${cx + 7} ${cy}L${cx} ${cy + 7}L${cx - 7} ${cy}Z`, class: `iso-${e.verdict}`, stroke: 'var(--text)', 'stroke-width': 1},
        sv('title', {}, `isolation of ${e.group} at ${fx(e.t_s, 2)} s: ${e.verdict}`)));
    }
    y += 2;
  }
  const s = F.raw.summary || {};
  for (const [t, text] of [[s.ignition_t_s, 'ignition'], [cut(F), 'cut'], [s.touchdown_t_s, 'touchdown']]) {
    if (t === null || t === undefined) continue;
    svg.append(sv('line', {class: 'mk', x1: X(t), x2: X(t), y1: head - 2, y2: H - 32}));
    svg.append(sv('text', {x: X(t) - 3, y: H - 22, 'text-anchor': 'end'}, text));
  }
  timeTicks(svg, X, W, L, H);
  const cur = sv('line', {class: 'cursor', y1: head - 2, y2: H - 32});
  svg.append(cur);
  state.cursors.push(t => { cur.setAttribute('x1', X(t)); cur.setAttribute('x2', X(t)); });
  scrubbable(svg, x => (x - L) / (W - L - R) * state.tMax);
  box.replaceChildren(svg);
}
// Side view: x east (downrange) against altitude, unequal scales; top view: equal scales around the pad.
function chartSide(box) {
  const runs = runsForOverlay(), F = state.runs[state.focus];
  const W = Math.max(280, Math.round(box.clientWidth || 600)), H = 300, L = 54, R = 12, T = 10, B = 28;
  const xs = runs.flatMap(r => r.S.flatMap(s => [s.truth.position_m[0], s.estimate.position_m[0]])).concat([-12, 12]);
  const zs = runs.flatMap(r => r.S.map(s => s.truth.position_m[2])).concat([0]);
  const [x0, x1] = domain(xs, 0.05), [z0, z1] = [0, Math.max(...zs) * 1.04];
  const X = v => L + (v - x0) / (x1 - x0) * (W - L - R), Y = v => T + (z1 - v) / (z1 - z0) * (H - T - B);
  const svg = sv('svg', {viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: 'img', 'aria-label': 'Side view: east position against altitude, simulator truth for each policy and the focused estimate.'});
  for (const v of ticks(z0, z1, 5)) { svg.append(sv('line', {class: 'gridl', x1: L, x2: W - R, y1: Y(v), y2: Y(v)})); svg.append(sv('text', {x: L - 6, y: Y(v) + 4, 'text-anchor': 'end'}, g3(v))); }
  for (const v of ticks(x0, x1, Math.max(3, Math.floor(W / 90)))) if (X(v) < W - R - 60) svg.append(sv('text', {x: X(v), y: H - 10, 'text-anchor': 'middle'}, g3(v)));
  svg.append(sv('text', {x: W - R, y: H - 10, 'text-anchor': 'end', class: 'lbl'}, 'x east (m)'));
  svg.append(sv('text', {x: L + 4, y: T + 12, class: 'lbl'}, 'altitude (m)'));
  svg.append(sv('line', {class: 'ax', x1: L, x2: W - R, y1: Y(0), y2: Y(0)}));
  svg.append(sv('line', {class: 'pad', x1: X(-10), x2: X(10), y1: Y(0), y2: Y(0)}));
  const pts = (r, k) => r.S.map(s => `${X(s[k].position_m[0]).toFixed(1)} ${Y(s[k].position_m[2]).toFixed(1)}`).join('L');
  for (const r of runs) svg.append(sv('path', {class: `ln s${r.n}`, d: 'M' + pts(r, 'truth')}));
  if (F.verified) svg.append(sv('path', {class: `ln est s${F.n}`, d: 'M' + pts(F, 'estimate')}));
  const dots = runs.map(r => { const c = sv('circle', {r: 5, class: `dot f${r.n}`}); svg.append(c); return [r, c]; });
  const est = sv('circle', {r: 5, class: `hollow s${F.n}`}); if (F.verified) svg.append(est);
  state.cursors.push(t => {
    for (const [r, c] of dots) { const s = sampleAt(r, t); c.setAttribute('cx', X(s.truth.position_m[0])); c.setAttribute('cy', Y(s.truth.position_m[2])); }
    const s = sampleAt(F, t); if (s) { est.setAttribute('cx', X(s.estimate.position_m[0])); est.setAttribute('cy', Y(s.estimate.position_m[2])); }
  });
  box.replaceChildren(svg);
}
function chartTop(box) {
  const runs = runsForOverlay(), F = state.runs[state.focus];
  const pad = state.caps.requirements.pad_radius_m, keep = state.caps.requirements.keep_out_radius_m;
  const W = Math.max(280, Math.round(box.clientWidth || 600)), H = Math.min(360, Math.max(260, Math.round(W * 0.7)));
  const all = runs.flatMap(r => r.S.flatMap(s => [s.truth.position_m, s.estimate.position_m]));
  const xs = all.map(p => p[0]).concat([-keep, keep]), ys = all.map(p => p[1]).concat([-keep, keep]);
  let [x0, x1] = domain(xs, 0.04), [y0, y1] = domain(ys, 0.04);
  const s = Math.min((W - 20) / (x1 - x0), (H - 30) / (y1 - y0));
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
  x0 = cx - (W - 20) / s / 2; x1 = cx + (W - 20) / s / 2; y0 = cy - (H - 30) / s / 2; y1 = cy + (H - 30) / s / 2;
  const X = v => 10 + (v - x0) * s, Y = v => 10 + (y1 - v) * s;
  const svg = sv('svg', {viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: 'img', 'aria-label': `Top view: east and north position with the ${pad} m pad circle and the ${keep} m keep-out circle.`});
  for (const v of ticks(x0, x1, Math.max(3, Math.floor(W / 90)))) { svg.append(sv('line', {class: 'gridl', x1: X(v), x2: X(v), y1: 10, y2: H - 20})); svg.append(sv('text', {x: X(v), y: H - 6, 'text-anchor': 'middle'}, g3(v))); }
  svg.append(sv('circle', {class: 'ko', cx: X(0), cy: Y(0), r: keep * s}), sv('circle', {class: 'r5', cx: X(0), cy: Y(0), r: pad * s}));
  svg.append(sv('text', {x: X(0) + pad * s + 3, y: Y(0) - 3}, `R5 ${pad} m`), sv('text', {x: X(0) + keep * s * 0.72 + 3, y: Y(0) - keep * s * 0.72}, `keep-out ${keep} m`));
  svg.append(sv('text', {x: W - 14, y: 22, 'text-anchor': 'end', class: 'lbl'}, 'north ↑ · x east (m) · equal scales'));
  const pts = (r, k) => r.S.map(q => `${X(q[k].position_m[0]).toFixed(1)} ${Y(q[k].position_m[1]).toFixed(1)}`).join('L');
  for (const r of runs) svg.append(sv('path', {class: `ln s${r.n}`, d: 'M' + pts(r, 'truth')}));
  if (F.verified) svg.append(sv('path', {class: `ln est s${F.n}`, d: 'M' + pts(F, 'estimate')}));
  for (const r of runs) {
    const td = r.v.touchdown && r.v.touchdown.truth ? r.v.touchdown.truth.base_position_m : null;
    if (!td) continue;
    const a = X(td[0]), b = Y(td[1]);
    svg.append(sv('path', {d: `M${a - 6} ${b - 6}L${a + 6} ${b + 6}M${a - 6} ${b + 6}L${a + 6} ${b - 6}`, class: `ln s${r.n}`, 'stroke-width': 3},
      sv('title', {}, `${r.policy} touchdown (nozzle plane, truth) ${fx(hyp(td[0], td[1]), 1)} m from the pad centre`)));
  }
  const dots = runs.map(r => { const c = sv('circle', {r: 5, class: `dot f${r.n}`}); svg.append(c); return [r, c]; });
  state.cursors.push(t => { for (const [r, c] of dots) { const q = sampleAt(r, t); c.setAttribute('cx', X(q.truth.position_m[0])); c.setAttribute('cy', Y(q.truth.position_m[1])); } });
  box.replaceChildren(svg);
}

// ---------------------------------------------------------------- readout at the cursor
function kv(pairs) { return el('dl', {class: 'kv'}, pairs.flatMap(([k, v, cls]) => [el('dt', {}, k), el('dd', {class: cls || null}, v)])); }
function drawReadout() {
  const F = state.runs[state.focus], s = sampleAt(F, state.t); if (!s) return;
  const tr = s.truth, o = s.observation, e = s.estimate, n = N(s);
  const tilt = Math.acos(Math.min(1, tr.tilt_cos)) * 180 / Math.PI;
  const truth = kv([['nozzle altitude', `${fx(tr.base_position_m[2], 1)} m`], ['vertical speed', `${fx(tr.velocity_mps[2], 2)} m/s`],
    ['from pad (nozzle)', `${fx(hyp(tr.base_position_m[0], tr.base_position_m[1]), 1)} m`], ['horizontal speed', `${fx(hyp(tr.base_velocity_mps[0], tr.base_velocity_mps[1]), 2)} m/s`],
    ['tilt', `${fx(tilt, 1)}°`], ['propellant', `${fx(tr.propellant_kg, 0)} kg`],
    ['faults acting', s.active_faults && s.active_faults.length ? s.active_faults.map(words).join(', ') : 'none']]);
  const ctrl = kv([['CG altitude estimate', `${fx(e.position_m[2], 1)} m (error ${fx(e.position_m[2] - tr.position_m[2], 2)} m)`],
    ['vertical speed est.', `${fx(e.velocity_mps[2], 2)} m/s`],
    ...(n ? [['nav mode', words(n.mode), n.mode === 'untrusted' ? 'bad' : ''], ['radar / GNSS group', `${n.radar} / ${n.gnss}`],
      ['vertical channel', n.vertical + (n.vertical === 'untrusted' ? ` (${UNTRUSTED_NOTE})` : ''), n.vertical === 'untrusted' ? 'bad' : ''],
      ['sigma_z / sigma_h', `${fx(n.sigma_z_m, 2)} / ${fx(n.sigma_h_m, 2)} m`], ['CUSUM radar / GNSS', `${fx(n.cusum_radar, 2)} / ${fx(n.cusum_gnss, 2)}`]]
      : [['navigation', 'this policy declares no navigation mode (M9)']]),
    ['throttle', s.applied ? `${fx(s.applied.throttle, 2)} (${s.applied.engine})` : 'n/a']]);
  const obs = kv([['radar altitude', o.altimeter_m === null ? 'no measurement' : `${fx(o.altimeter_m, 1)} m`],
    ['GNSS z', o.gnss_position_m ? `${fx(o.gnss_position_m[2], 1)} m` : 'no fix'],
    ['GNSS horizontal', o.gnss_position_m ? `${fx(o.gnss_position_m[0], 1)}, ${fx(o.gnss_position_m[1], 1)} m` : 'no fix']]);
  $('readout').replaceChildren(
    el('section', {}, el('h3', {}, `${F.policy} at t = ${fx(s.t_s, 1)} s · ${TRUTH}`), truth),
    el('section', {}, el('h3', {}, `Sensor observations (what the controller receives)`), obs),
    el('section', {}, el('h3', {}, `${CONTROLLER}`), ctrl));
  for (const r of state.runs) {
    const q = sampleAt(r, state.t), live = $(`live-${r.i}`); if (!q || !live) continue;
    const m = N(q);
    live.textContent = `t ${fx(q.t_s, 1)} s · h ${fx(q.truth.base_position_m[2], 0)} m · vz ${fx(q.truth.velocity_mps[2], 1)} m/s${m ? ' · ' + words(m.mode) : ''}`;
  }
}

// ---------------------------------------------------------------- time cursor
function setT(t) {
  state.t = Math.max(0, Math.min(state.tMax, t));
  const slider = $('time'); if (slider) { slider.value = state.t.toFixed(1); slider.setAttribute('aria-valuetext', `${fx(state.t, 1)} seconds`); }
  const out = $('time-out'); if (out) out.textContent = `${fx(state.t, 1)} s`;
  for (const c of state.cursors) c(state.t);
  drawReadout();
}
function stop() { if (state.timer) clearInterval(state.timer); state.timer = null; const b = $('play'); if (b) { b.textContent = 'Play'; b.setAttribute('aria-pressed', 'false'); } }
function play() {
  if (state.timer) { stop(); return; }
  if (state.t >= state.tMax - 0.05) setT(0);
  const speed = Number($('speed').value) || 2;
  state.timer = setInterval(() => { if (state.t >= state.tMax) { stop(); return; } setT(state.t + 0.1 * speed); }, 100);
  $('play').textContent = 'Pause'; $('play').setAttribute('aria-pressed', 'true');
}

// ---------------------------------------------------------------- why this outcome
const CLASS_TEXT = {
  R: 'Recovered: landed with R1 to R6 met and the invariants S1 to S5 held during the whole flight.',
  T: 'Intact touchdown off the pad: everything met except R5 (distance from the pad centre). A failed mission, not a success.',
  U: 'Unsafe: an invariant S1 to S5, or R1 to R4 or R6, failed, or the vehicle never made contact.',
};
function whyPanel(F) {
  const v = F.v, labels = state.caps.labels || {}, nav = F.nav, out = [];
  if (!F.verified) return [el('p', {class: 'alert'}, `Run ${F.id} is not verified evidence (${(F.raw.verdict.reasons || []).join('; ')}). Its outcome is withheld.`)];
  const head = el('div', {class: 'panel'}, el('h3', {}, 'Physical class (simulator truth only)'),
    el('p', {}, el('span', {class: `cls cls-${F.cls || 'x'}`}, F.cls || '?'), CLASS_TEXT[F.cls] || 'No class.',
      F.cls !== 'R' ? ` Here: ${v.requirements.filter(r => !r.pass).concat(v.invariants.filter(i => !i.pass)).map(x => x.id.slice(0, 2)).join(', ') || 'no contact'} failed.` : ''),
    el('p', {class: 'note'}, F.clsSource === 'verifier' ? `Class from the verifier (verification.json navigation.physical_class). Mission outcome: ${words(v.outcome)}.`
      : `This policy has no navigation block; the class is derived here from R1 to R6 and S1 to S5 by the rule of section 9.1. Mission outcome: ${words(v.outcome)}.`),
    F.clsSource === 'verifier' && F.derived && F.derived !== F.cls ? el('p', {class: 'bad'}, `The class derived from R1 to R6 and S1 to S5 here is ${F.derived}, not ${F.cls}: check the verifier.`) : null);
  out.push(head);
  const failedR = v.requirements.filter(r => !r.pass), failedS = v.invariants.filter(i => !i.pass);
  out.push(el('div', {class: 'panel'}, el('h3', {}, `Requirements at contact and invariants: ${failedR.length + failedS.length ? failedR.length + failedS.length + ' failed' : 'all met'}`),
    failedR.length + failedS.length ? el('div', {class: 'scroll'}, el('table', {}, el('thead', {}, el('tr', {}, ['id', 'what', 'expected', 'observed', 'when'].map(h => el('th', {}, h)))),
      el('tbody', {}, failedR.map(r => el('tr', {}, el('td', {}, el('code', {}, r.id.slice(0, 2))), el('td', {}, labels[r.id] || words(r.id)), el('td', {}, r.expected), el('td', {class: 'bad'}, r.observed), el('td', {}, `${fx(r.t_s, 2)} s`))),
        failedS.map(i => el('tr', {}, el('td', {}, el('code', {}, i.id.slice(0, 2))), el('td', {}, labels[i.id] || words(i.id)), el('td', {}, `limit ${g3(i.limit)} ${i.unit}`),
          el('td', {class: 'bad'}, `worst ${g3(i.worst_value)} ${i.unit}, ${i.failure_count} samples`), el('td', {}, i.first_failure ? `${fx(i.first_failure.t_s, 2)} s` : ''))))))
      : el('p', {class: 'ok'}, 'R1 to R6 met at contact and S1 to S5 held, against the assumed demonstrator requirements.')));
  if (!F.hasNav || !nav) {
    out.push(el('div', {class: 'panel'}, el('h3', {}, 'Navigation declarations'), el('p', {}, `${F.policy} is an M9 policy: it declares no navigation mode or channel integrity, so there is nothing to compare with the truth. Only the physical outcome above applies.`)));
    return out;
  }
  const last = F.S[F.S.length - 1], n = N(last);
  out.push(el('div', {class: 'panel'}, el('h3', {}, `What the navigation declared at touchdown (${fx(last.t_s, 2)} s)`),
    kv([['mode', words(n.mode), n.mode === 'untrusted' ? 'bad' : ''], ['vertical channel', n.vertical], ['horizontal velocity / position', `${n.horizontal_velocity} / ${n.horizontal_position}`],
      ['radar / GNSS group', `${n.radar} / ${n.gnss}`]]),
    [n.mode, n.vertical, n.horizontal_velocity, n.horizontal_position].includes('untrusted') ? el('p', {class: 'warn'}, `${UNTRUSTED_NOTE[0].toUpperCase()}${UNTRUSTED_NOTE.slice(1)}: the vehicle keeps braking under the vertical law, without chasing the pad laterally, and is judged by the same R1 to R6 and S1 to S5.`) : null));
  const ch = [['vertical', 'Vertical', 'm'], ['horizontal_velocity', 'Horizontal velocity', 'm/s'], ['horizontal_position', 'Horizontal position', 'm']];
  out.push(el('div', {class: 'panel'}, el('h3', {}, 'Alert failures (error above the limit while declared trusted)'),
    el('div', {class: 'scroll'}, el('table', {}, el('thead', {}, el('tr', {}, ['channel', 'alert limit', 'max true error', 'trusted', 'alert failure'].map(h => el('th', {}, h)))),
      el('tbody', {}, ch.map(([k, label, unit]) => { const c = nav[k] || {}; return el('tr', {}, el('td', {}, label), el('td', {}, c.alert_limit || 'n/a'), el('td', {}, `${g3(c.max_error)} ${unit}`),
        el('td', {}, `${fx(100 * (c.trusted_fraction || 0), 0)}% of cycles`), el('td', {class: c.alert_failure ? 'bad' : 'ok'}, c.alert_failure ? `yes, at ${fx(c.alert_failure_t_s, 2)} s` : (c.declaration_applicable ? 'no' : 'no (error never above the limit)'))); })))),
    el('p', {class: 'note'}, 'Computed by the verifier at every control cycle from the true state; the controller never sees it.')));
  const onset = g => { const fs = F.faults.filter(f => groupOf(f.kind) === g).map(f => f.start_s); return fs.length ? Math.min(...fs) : null; };
  const iso = nav.isolation_events || [];
  const VERDICT = {correct: 'correct: a fault of this group was acting', before_onset: 'before the fault onset', wrong: 'wrong group: no fault of this group'};
  out.push(el('div', {class: 'panel'}, el('h3', {}, 'Isolation and detection'),
    iso.length ? el('ul', {}, iso.map(e => { const o = onset(e.group); return el('li', {class: e.verdict === 'correct' ? 'ok' : 'bad'},
      `${e.group} isolated at ${fx(e.t_s, 2)} s${o === null ? '' : ` (${e.t_s - o >= 0 ? '+' : ''}${fx(e.t_s - o, 2)} s after the onset at ${fx(o, 2)} s)`}: ${VERDICT[e.verdict] || e.verdict}.`); }))
      : el('p', {}, `No isolation (${nav.isolation || 'none'}). Without isolation a suspect source stays declared, and the main solution is kept.`),
    (nav.detections || []).length ? el('ul', {}, nav.detections.map(d => el('li', {}, `${words(d.fault)} from ${fx(d.start_s, 2)} s: ${d.first_declaration_delay_s === null ? 'never declared' : `first declaration ${fx(d.first_declaration_delay_s, 2)} s after onset`}.`))) : null,
    (nav.transitions || []).length ? el('p', {class: 'note'}, 'Mode transitions: ' + nav.transitions.map(x => `${fx(x.t_s, 2)} s ${words(x.from)} → ${words(x.to)}`).join('; ') + '.') : el('p', {class: 'note'}, 'No mode transition.')));
  return out;
}

// ---------------------------------------------------------------- replay and evidence
async function replay(run) {
  const box = $(`replay-${run.i}`);
  box.replaceChildren(el('p', {class: 'note'}, 'Replaying…'));
  try {
    const resp = await fetch('/api/workbench/replay', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({run_id: run.id})});
    const data = await resp.json().catch(() => ({error: `server answered ${resp.status}`}));
    if (!resp.ok || data.error) { box.replaceChildren(el('p', {class: 'alert'}, data.error || `server answered ${resp.status}`)); return; }
    const checks = data.replay.checks || [], passed = checks.filter(c => c.pass).length;
    box.replaceChildren(el('p', {class: data.all_checks_pass ? 'ok' : 'bad'}, data.all_checks_pass
      ? `Replay verified: vv-rocket replay recomputed the trace, the verification and the manifest from the stored case and seed; ${passed} of ${checks.length} checks matched byte for byte.`
      : `Replay ${data.replay.status}: ${passed} of ${checks.length} checks matched. ${data.replay.detail || ''}`),
      el('div', {class: 'scroll'}, el('table', {}, el('thead', {}, el('tr', {}, el('th', {}, 'check'), el('th', {}, 'result'), el('th', {}, 'detail'))),
        el('tbody', {}, checks.map(c => el('tr', {}, el('td', {}, c.name), el('td', {class: c.pass ? 'ok' : 'bad'}, c.pass ? 'match' : 'MISMATCH'), el('td', {}, el('code', {}, c.detail))))))),
      el('p', {class: 'note'}, `Binary SHA-256 ${data.binary_sha256}. Artifacts: ${Object.entries(data.artifacts).map(([k, v]) => `${k} ${v.slice(0, 12)}…`).join(', ')}.`));
  } catch (e) { box.replaceChildren(el('p', {class: 'alert'}, 'the local server did not respond.')); }
}

// ---------------------------------------------------------------- page assembly
function drawStory() {
  const j = state.journey, box = $('story');
  if (!j) { box.hidden = true; box.replaceChildren(); return; }
  box.hidden = false;
  box.replaceChildren(el('div', {class: 'story'}, el('h2', {}, j.title), el('p', {}, j.narrative),
    el('p', {}, el('b', {}, 'Observed in development: '), j.expectation),
    el('p', {}, el('b', {}, 'What to look at')), el('ul', {}, j.look_at.map(x => el('li', {}, x)))));
}
function runCard(r) {
  const v = r.v, failed = r.verified ? v.requirements.filter(x => !x.pass).map(x => x.id.slice(0, 2)).concat(v.invariants.filter(x => !x.pass).map(x => x.id.slice(0, 2))) : [];
  return el('button', {class: `card ${r.color}`, 'aria-pressed': r.i === state.focus ? 'true' : 'false', onclick: () => { state.focus = r.i; drawResult(); },
    'aria-label': `Focus ${r.policy}`},
    el('span', {class: 'p'}, r.policy),
    el('span', {class: 'o'}, r.verified ? el('span', {class: `cls cls-${r.cls || 'x'}`}, r.cls || '?') : el('span', {class: 'cls cls-x'}, '!'),
      r.verified ? `${words(v.outcome)}${failed.length ? ' · failed ' + failed.join(', ') : ''}` : 'withheld: not verified evidence'),
    el('span', {class: 'live', id: `live-${r.i}`}),
    el('span', {class: 'live'}, `run ${r.id} · ${r.verified ? 'evidence verified' : 'REJECTED evidence'}`));
}
function drawResult() {
  stop();
  state.cursors = [];
  const F = state.runs[state.focus];
  const req = F.raw.request;
  const faultText = F.faults.length ? F.faults.map(f => `${words(f.kind)}${faultInfo(f.kind) && faultInfo(f.kind).magnitude ? ' ' + g3(f.magnitude) + ' ' + faultInfo(f.kind).magnitude.unit : ''} ${fx(f.start_s, 2)} to ${fx(f.end_s, 2)} s`).join(' + ') : 'no fault';
  const charts = [
    ['side', 'Side view', `Solid: ${TRUTH} (centre of mass), one colour per policy. Dashed: focused ${CONTROLLER}.`, 'Unequal scales. The green bar is the pad (±10 m); the centre of mass is about 15 m above the nozzle plane at contact.', chartSide],
    ['top', 'Top view', `Solid: ${TRUTH} (centre of mass). Dashed: focused estimate. ×: touchdown of the nozzle plane, where R5 is judged.`, 'Equal scales. Green circle: R5 limit; red dashed circle: S2 keep-out.', chartTop],
    ['alt', 'Altitude', `Solid: ${TRUTH}. Dashed: focused estimate.`, null, chartAltitude],
    ['vz', 'Vertical speed', `Solid: ${TRUTH}. Dashed: focused estimate.`, null, chartVz],
    ['verr', 'Vertical estimation error', `Line: estimate minus ${TRUTH}, centre of mass. Band: ± ${F.k}·sigma_z declared by the focused controller (${F.kSource}).`,
      `Dotted red: vertical alert limit max(1 m, 0.02 h) with h the true nozzle-plane altitude (verifier). The truth lies inside the declared band where the band covers 0. Clipped to the plotted range.`, chartVerr, true],
    ['sens', 'Sensors against truth', `Radar altimeter minus the true nozzle-plane altitude (orange) and GNSS altitude minus the true centre of mass (green). Uses ${TRUTH}.`, 'Gaps are missing measurements (dropout or no fix).', chartSensors],
    ['dis', 'Radar against GNSS', 'Radar altitude minus GNSS altitude, from the observations only: what the controller can compare.', 'In nominal flight the difference is the height of the centre of mass above the nozzle plane, about 14 to 15 m, plus the radar lever arm and noise.', chartDisagree],
  ];
  if (F.hasNav && F.verified) {
    charts.push(['cusum', 'CUSUM detectors', `Per-source CUSUM of the ${CONTROLLER}: radar (orange) and GNSS (green); threshold h from the case (dashed red).`, SAMPLED, chartCusum]);
    charts.push(['sigma', 'Declared uncertainty', `sigma_z (orange) and sigma_h (green) declared by the ${CONTROLLER}.`, 'sigma_h excludes the undetectable horizontal bias term B_h, so horizontal position is never trusted.', chartSigma]);
  }
  const lanes = figure('lanes', 'Navigation timeline', `Declarations of the ${CONTROLLER}, sampled every 0.1 s. Green nominal, healthy or trusted; amber degraded, suspect or probation; grey excluded; red untrusted (${UNTRUSTED_NOTE}).`,
    'Shaded: fault windows. Thin dashed ticks: mode transitions from the verifier. Diamonds: isolations, green correct, amber before the onset, red wrong group.', true);
  const figs = charts.map(([id, title, src, cap, fn, wide]) => ({fig: figure(id, title, src, cap, wide), fn}));
  const s = F.raw.summary || {};
  $('result').replaceChildren(
    el('h2', {id: 'result-h', tabindex: '-1'}, `Results · seed ${req.seed} · ${faultText}`),
    el('div', {class: 'cards', role: 'group', 'aria-label': 'Runs; choose the one to focus'}, state.runs.map(runCard)),
    el('div', {class: 'timebar'},
      el('button', {id: 'play', 'aria-pressed': 'false', onclick: play}, 'Play'),
      el('label', {class: 'meta'}, 'speed ', el('select', {id: 'speed'}, [1, 2, 5].map(x => el('option', {value: x, selected: x === 2 ? true : null}, `${x}×`)))),
      el('input', {type: 'range', id: 'time', min: 0, max: state.tMax.toFixed(1), step: 0.1, value: state.t, 'aria-label': 'Time cursor (s)', oninput: e => { stop(); setT(Number(e.target.value)); }}),
      el('output', {id: 'time-out', for: 'time'}),
      el('span', {class: 'meta'}, `focus: ${F.policy} · touchdown ${fx(s.touchdown_t_s, 2)} s`)),
    el('div', {class: 'readout', id: 'readout'}),
    el('div', {class: 'legend'}, state.runs.map(r => el('span', {}, el('span', {class: 'key', style: null}, ''), el('b', {class: null}, r.policy))),
      el('span', {}, 'solid: truth · dashed: estimate')),
    el('h2', {}, 'Trajectory and navigation'),
    el('div', {class: 'charts'}, figs.slice(0, 4).map(x => x.fig.node), figs.slice(4).map(x => x.fig.node), lanes.node),
    el('h2', {}, `Why this outcome · ${F.policy}`),
    el('div', {class: 'why'}, whyPanel(F)),
    el('h2', {}, 'Replay and evidence'),
    el('div', {class: 'why'}, state.runs.map(r => el('div', {class: 'panel'}, el('h3', {}, `${r.policy} · run ${r.id}`),
      el('div', {class: 'controls'}, el('button', {onclick: () => replay(r)}, 'Replay this run'), ' ',
        el('a', {class: 'button', href: `/api/workbench/evidence/${r.id}`, download: `vv-m10-evidence-${r.id}.zip`}, 'Download evidence (zip)')),
      el('div', {id: `replay-${r.i}`}, el('p', {class: 'note'}, r.verified ? 'Verified when it ran (replay and integrity). Replay again to recompute every artifact now.' : `Rejected: ${(r.raw.verdict.reasons || []).join('; ')}`))))),
    el('p', {class: 'note'}, state.wb.landing.model.validity));
  // Colour keys of the legend follow the run order.
  [...$('result').querySelectorAll('.legend .key')].forEach((k, i) => { if (state.runs[i]) k.style.borderTopColor = `var(--c${state.runs[i].n})`; });
  drawCharts(figs, lanes);
  setT(state.t);
}
let lastCharts = null;
function drawCharts(figs, lanes) {
  lastCharts = [figs, lanes];
  state.cursors = [];
  const F = state.runs[state.focus];
  if (!F.verified) {
    for (const x of figs) x.fig.box.replaceChildren(el('p', {class: 'alert'}, 'Not drawn: this run is not verified evidence.'));
    lanes.box.replaceChildren();
    return;
  }
  for (const x of figs) x.fn(x.fig.box);
  chartLanes(lanes.box);
}
let resizeTimer = null;
window.addEventListener('resize', () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => { if (lastCharts && state.runs.length) { drawCharts(...lastCharts); setT(state.t); } }, 150);
});

async function boot() {
  try {
    const resp = await fetch('/api/workbench');
    const data = await resp.json();
    if (!resp.ok || data.error) { setError(data.error || `server answered ${resp.status}`); return; }
    state.wb = data; state.caps = data.landing.capabilities;
  } catch (e) { setError('could not load the workbench description from the local server.'); return; }
  $('model-line').textContent = `${state.wb.landing.model.id} · adapter ${state.wb.landing.schema}`;
  drawJourneys(); drawSetup();
}
boot();
"""
