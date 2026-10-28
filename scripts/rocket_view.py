"""Mission Control page for the `rocket-rigid-body` model (M8), served at /rocket.

The page keeps three statements apart: whether the stored run is verified evidence
(integrity and replay), what the physics reference verification of this build found,
and what the model can and cannot represent. Charts plot recorded samples only; a
ground crossing is reported as a crossing of 0 m altitude, never as a landing.
"""

from __future__ import annotations


def rocket_page(css: str) -> str:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Mission Control: rocket stage</title>
<style>{css}
:root{{--s3:#1f9e89}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--s3:#22a58c}}}}
:root[data-theme="dark"]{{--s3:#22a58c}}
main{{max-width:1200px}}
.tabs{{display:flex;gap:6px;margin:12px 0}}
.tabs button[aria-selected="true"]{{border:2px solid var(--text);font-weight:700}}
button,select,input{{font:inherit;font-size:14px;padding:6px 10px;border:1px solid var(--line);border-radius:8px;background:var(--surface);color:var(--text);min-height:36px}}
button:focus-visible,select:focus-visible,input:focus-visible,a:focus-visible{{outline:2px solid var(--s1);outline-offset:2px}}
button.primary{{background:var(--s1);color:#fff;border-color:var(--s1);font-weight:700}}
button:disabled{{opacity:.6}}
fieldset{{border:1px solid var(--line);border-radius:10px;padding:12px;margin:12px 0;min-width:0}}
legend{{font-weight:700;padding:0 6px}}
.choices{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:8px}}
.choice{{display:flex;gap:8px;align-items:flex-start;border:1px solid var(--line);border-radius:8px;padding:8px}}
.choice input{{min-height:auto;margin-top:4px}}
.choice:has(input:checked){{border:2px solid var(--s1)}}
input[aria-invalid="true"]{{border:2px solid var(--bad)}}
.physics{{border-left:4px solid var(--s1);padding:4px 10px;background:var(--panel);max-width:80ch}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:8px;margin:12px 0}}
.card{{background:var(--panel);border-radius:10px;padding:10px;min-width:0}}
.card b{{display:block;font-size:18px;overflow-wrap:anywhere}}
.ok{{color:var(--good)}}.bad{{color:var(--bad)}}.warn{{color:var(--warn)}}
.statement{{border-left:4px solid var(--line);padding:4px 10px;margin:6px 0;max-width:90ch}}
.statement.ok{{border-color:var(--good)}}.statement.bad{{border-color:var(--bad)}}.statement.warn{{border-color:var(--warn)}}
.statement b{{color:var(--text)}}
.controls{{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:8px 0}}
input[type=range]{{flex:1;min-width:140px}}
.charts{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}}
.charts .panel{{margin:0;min-width:0}}
.chart-title{{font-weight:600;color:var(--text);font-size:14px;margin:0 0 4px}}
.line{{fill:none;stroke-width:2;stroke-linejoin:round}}.l1{{stroke:var(--s1)}}.l2{{stroke:var(--s2)}}.l3{{stroke:var(--s3)}}
.dot1{{fill:var(--s1)}}.dot2{{fill:var(--s2)}}.dot3{{fill:var(--s3)}}
.sw1{{background:var(--s1)}}.sw2{{background:var(--s2)}}.sw3{{background:var(--s3)}}
.cursor{{stroke:var(--text2);stroke-width:1;stroke-dasharray:3 3}}
.ground{{stroke:var(--text2);stroke-width:1}}
.cur{{fill:var(--surface);stroke:var(--text);stroke-width:2}}
dl.kv{{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:4px 12px;margin:0}}
dl.kv dt{{color:var(--muted)}}dl.kv dd{{margin:0;overflow-wrap:anywhere;font-variant-numeric:tabular-nums}}
@media (max-width:480px){{dl.kv{{grid-template-columns:minmax(0,1fr)}}}}
.grid2{{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px}}
@media (max-width:820px){{.grid2{{grid-template-columns:minmax(0,1fr)}}}}
.scroll table{{min-width:520px}}.scroll table.cases{{min-width:0}}
.unverified{{border:2px dashed var(--bad);border-radius:10px;padding:8px;margin:8px 0;min-width:0;overflow-wrap:anywhere}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.4 ui-monospace,Consolas,monospace}}
.alert{{border:2px solid var(--bad);border-radius:8px;padding:8px 12px}}
[hidden]{{display:none!important}}
</style></head>
<body><main>
<p class="meta">V&amp;V lab · Mission Control · <a href="/">Ground vehicle (2D)</a> · Rocket stage (6-DOF)</p>
<h1>Mission Control: rocket stage</h1>
<p class="physics" id="physics"><b>Rocket stage, 6-DOF rigid body with variable mass.</b> 3D position and velocity,
attitude quaternion, angular velocity and propellant mass, integrated with fixed-step RK4. Idealized thrust, uniform
gravity and drag at the centre of mass only; checked against 12 analytic reference cases (result with each run), not
validated against flight data. There is no contact model: crossing 0 m altitude is not a landing.</p>
<div class="tabs" role="tablist" aria-label="Mode">
<button role="tab" id="tab-run" aria-controls="panel-run" aria-selected="true">Run</button>
<button role="tab" id="tab-research" aria-controls="panel-research" aria-selected="false" tabindex="-1">Research</button>
</div>
<section id="panel-run" role="tabpanel" aria-labelledby="tab-run"></section>
<section id="panel-research" role="tabpanel" aria-labelledby="tab-research" hidden></section>
<p id="status" role="status" aria-live="polite" class="meta"></p>
<div id="error" role="alert"></div>
<section id="result" aria-label="Run result"></section>
<noscript>Mission Control needs JavaScript.</noscript>
<script src="/rocket.js"></script>
</main></body></html>
"""


ROCKET_JS = r"""
'use strict';
const SCHEMA = 'vv-sim-run-request.v2', MODEL = 'rocket-rigid-body';
const $ = id => document.getElementById(id);
function el(tag, attrs, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') n.className = v; else if (k.startsWith('on')) n.addEventListener(k.slice(2), v); else n.setAttribute(k, v === true ? '' : v);
  }
  for (const k of kids.flat()) if (k !== null && k !== undefined) n.append(k instanceof Node ? k : String(k));
  return n;
}
const SVGNS = 'http://www.w3.org/2000/svg';
function sv(tag, attrs, ...kids) {
  const n = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, v);
  for (const k of kids) n.append(k instanceof Node ? k : String(k));
  return n;
}
const f = (x, d = 1) => Number.isFinite(x) ? (Object.is(+x.toFixed(d), -0) ? 0 : x).toFixed(d) : 'n/a';
// Three significant figures for small values (0.004 rad/s is not rounded to zero), one decimal for large ones.
const g3 = x => !Number.isFinite(x) ? 'n/a' : Math.abs(x) >= 100 ? f(x, 1) : String(+x.toPrecision(3));
const vec = (v, d = 1, u = '') => `(${v.map(x => f(x, d)).join(', ')})${u ? ' ' + u : ''}`;
const norm = v => Math.hypot(...v);
// Body x axis in inertial components, R(q) (1, 0, 0), for q = (w, x, y, z).
const noseOf = q => { const [w, x, y, z] = q; return [1 - 2 * (y * y + z * z), 2 * (x * y + w * z), 2 * (x * z - w * y)]; };
const tiltDeg = q => Math.acos(Math.max(-1, Math.min(1, noseOf(q)[2]))) * 180 / Math.PI;

const state = {models: null, mission: null, result: null, idx: 0, timer: null, busy: false, ui: null};

function setStatus(t) { $('status').textContent = t; }
function setError(t) { $('error').replaceChildren(t ? el('p', {class: 'alert', id: 'error-text'}, el('b', {}, 'Could not run: '), t) : ''); }
function markField(message) {
  document.querySelectorAll('[aria-invalid]').forEach(n => { n.removeAttribute('aria-invalid'); n.removeAttribute('aria-describedby'); });
  const old = $('field-error'); if (old) old.remove();
  const m = /^overrides\.(\w+) (.*)$/.exec(message || ''), input = m && $('ov-' + m[1]);
  if (input) {
    const name = input.closest('label').firstChild.textContent.trim();
    input.closest('label').after(el('p', {class: 'alert', id: 'field-error'}, `${name}: ${m[2]}.`));
    input.setAttribute('aria-invalid', 'true'); input.setAttribute('aria-describedby', 'field-error'); input.focus();
  }
  return !!input;
}

async function runRequest(body) {
  if (state.busy) return;
  state.busy = true; setError(''); setStatus('Running vv-rocket: integration, replay and reference verification…');
  document.querySelectorAll('button.primary').forEach(b => { b.disabled = true; b.setAttribute('aria-busy', 'true'); });
  try {
    const resp = await fetch('/api/run', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    const data = await resp.json().catch(() => ({error: `server answered ${resp.status} without JSON`}));
    if (resp.ok && (typeof data.run_id !== 'string' || !data.verdict || !data.physics_reference)) {
      data.error = 'the server answered without a run id, verdict or physics reference; nothing from that answer is shown';
    }
    if (!resp.ok || data.error) {
      const message = data.error || `server answered ${resp.status}`;
      setError(markField(message) ? 'one parameter is not an allowed value; see the highlighted field.' : message);
      setStatus(state.result ? `Nothing was run. The result below is still the previous run ${state.result.run_id}.` : '');
      return;
    }
    stop(); state.result = data; state.idx = 0; markField('');
    setStatus(data.verdict.status === 'verified'
      ? `Run ${data.run_id} finished${data.reused ? ' (stored run regenerated and compared)' : ''}. Evidence verified.`
      : `Run ${data.run_id}: the stored run does not match a fresh regeneration or its replay. Nothing below is verified evidence.`);
    drawResult(); drawResearch(); $('result-heading').focus();
  } catch (e) {
    setError('the local server did not respond. Is mission_control.py still running?');
  } finally {
    state.busy = false;
    document.querySelectorAll('button.primary').forEach(b => { b.disabled = false; b.removeAttribute('aria-busy'); });
  }
}

// ---------------------------------------------------------------- modes
function selectTab(name) {
  for (const t of ['run', 'research']) {
    const on = t === name;
    $('tab-' + t).setAttribute('aria-selected', on ? 'true' : 'false');
    $('tab-' + t).setAttribute('tabindex', on ? '0' : '-1');
    $('panel-' + t).hidden = !on;
  }
  $('result').hidden = name !== 'run';
}
function wireTabs() {
  const names = ['run', 'research'];
  names.forEach((name, i) => {
    $('tab-' + name).addEventListener('click', () => selectTab(name));
    $('tab-' + name).addEventListener('keydown', e => {
      const d = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
      if (!d) return;
      const next = names[(i + d + names.length) % names.length];
      selectTab(next); $('tab-' + next).focus(); e.preventDefault();
    });
  });
}

function missions() { return state.models.models[MODEL].capabilities.missions; }
function drawRun() {
  const ms = missions();
  if (!state.mission) state.mission = ms[1] ? ms[1].id : ms[0].id;
  const pick = el('fieldset', {}, el('legend', {}, '1. Choose an experiment'),
    el('div', {class: 'choices'}, ms.map(m => el('label', {class: 'choice'},
      el('input', {type: 'radio', name: 'mission', value: m.id, checked: m.id === state.mission,
        onchange: () => { state.mission = m.id; drawParams(); }}),
      el('span', {}, el('b', {}, m.id.replaceAll('_', ' ')), el('br'), el('span', {class: 'meta'}, m.description))))));
  const params = el('fieldset', {id: 'params'});
  const run = el('button', {class: 'primary', onclick: () => {
    const m = ms.find(x => x.id === state.mission), overrides = {};
    for (const k of Object.keys(m.overrides)) overrides[k] = Number($('ov-' + k).value);
    runRequest({schema: SCHEMA, model: MODEL, mission: m.id, overrides});
  }}, '3. Run simulation');
  $('panel-run').replaceChildren(pick, params, run);
  drawParams();
}
function drawParams() {
  const m = missions().find(x => x.id === state.mission);
  $('params').replaceChildren(el('legend', {}, '2. Change the parameters'),
    el('div', {class: 'controls'}, Object.entries(m.overrides).map(([k, o]) => el('label', {},
      `${o.description} `, el('input', {type: 'number', id: 'ov-' + k, value: +m.defaults[k].toFixed(6), min: o.min, max: o.max,
        step: o.step || 'any', inputmode: 'decimal'}), el('span', {class: 'meta'}, ` [${o.min}, ${o.max}]`)))),
    el('p', {class: 'meta'}, 'Defaults are the stored experiment. The adapter and the Rust library validate every value and refuse anything outside the range with a message.'));
  markField('');
}

// ---------------------------------------------------------------- charts
function niceTicks(lo, hi, n = 4) {
  if (lo === hi) { lo -= 1; hi += 1; }
  const raw = (hi - lo) / n, p = Math.pow(10, Math.floor(Math.log10(raw))), step = [1, 2, 5, 10].map(s => s * p).find(s => s >= raw);
  const out = []; for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) out.push(+v.toFixed(10));
  return {ticks: out, lo: Math.min(lo, out[0]), hi: Math.max(hi, out[out.length - 1])};
}
// xs: numbers; series: [{name, ys, n (1..3)}]. Returns an SVG with a cursor at sample idx.
function chart({title, unit, xs, xLabel, series, idx, onPick}) {
  const W = 360, H = 190, L = 48, R = series.length > 1 ? 36 : 12, T = 10, B = 30;
  const allY = series.flatMap(s => s.ys).filter(Number.isFinite);
  const xr = niceTicks(Math.min(...xs), Math.max(...xs)), yr = niceTicks(Math.min(...allY), Math.max(...allY));
  const X = x => L + (x - xr.lo) / (xr.hi - xr.lo) * (W - L - R), Y = y => H - B - (y - yr.lo) / (yr.hi - yr.lo) * (H - T - B);
  const svg = sv('svg', {viewBox: `0 0 ${W} ${H}`, role: 'img',
    'aria-label': `${title}: ${series.map(s => `${s.name} from ${g3(s.ys[0])} to ${g3(s.ys[s.ys.length - 1])} ${unit}`).join('; ')}. Use the sample controls for exact values.`});
  for (const t of yr.ticks) { svg.append(sv('line', {class: 'grid', x1: L, x2: W - R, y1: Y(t), y2: Y(t)})); svg.append(sv('text', {class: 'axis', x: L - 6, y: Y(t) + 4, 'text-anchor': 'end'}, String(t))); }
  for (const t of xr.ticks) svg.append(sv('text', {class: 'axis', x: X(t), y: H - B + 16, 'text-anchor': 'middle'}, String(t)));
  svg.append(sv('text', {class: 'axis', x: W - R, y: H - 4, 'text-anchor': 'end'}, xLabel));
  if (yr.lo < 0 && yr.hi > 0) svg.append(sv('line', {class: 'zero', x1: L, x2: W - R, y1: Y(0), y2: Y(0)}));
  for (const s of series) {
    const d = xs.map((x, i) => Number.isFinite(s.ys[i]) ? `${i ? 'L' : 'M'}${X(x).toFixed(1)},${Y(s.ys[i]).toFixed(1)}` : '').join('');
    svg.append(sv('path', {class: `line l${s.n}`, d}));
  }
  // End labels, pushed apart so series that end at the same value stay readable.
  if (series.length > 1) {
    const labels = series.map(s => ({name: s.name, y: Y(s.ys[s.ys.length - 1]) + 4})).sort((a, b) => a.y - b.y);
    labels.forEach((l, k) => { if (k && l.y < labels[k - 1].y + 12) l.y = labels[k - 1].y + 12; });
    // Keep them above the time axis labels, moving the stack up if needed.
    for (let k = labels.length - 1, limit = H - B - 4; k >= 0; k--, limit -= 12) labels[k].y = Math.min(labels[k].y, limit);
    for (const l of labels) svg.append(sv('text', {class: 'axis', x: W - R + 4, y: l.y}, l.name));
  }
  svg.append(sv('line', {class: 'cursor', x1: X(xs[idx]), x2: X(xs[idx]), y1: T, y2: H - B}));
  for (const s of series) if (Number.isFinite(s.ys[idx])) svg.append(sv('circle', {class: `dot${s.n}`, cx: X(xs[idx]), cy: Y(s.ys[idx]), r: 4}));
  const hit = sv('rect', {x: L, y: T, width: W - L - R, height: H - T - B, fill: 'transparent'});
  hit.addEventListener('pointermove', e => {
    const box = svg.getBoundingClientRect(), x = xr.lo + ((e.clientX - box.left) * W / box.width - L) / (W - L - R) * (xr.hi - xr.lo);
    let best = 0; xs.forEach((v, i) => { if (Math.abs(v - x) < Math.abs(xs[best] - x)) best = i; });
    if (best !== state.idx) onPick(best);
  });
  svg.append(hit);
  const legend = series.length > 1 ? el('div', {class: 'legend'}, series.map(s => el('span', {}, el('span', {class: `sw sw${s.n}`}), s.name))) : null;
  return el('div', {class: 'panel'}, el('p', {class: 'chart-title'}, `${title} (${unit})`), legend, svg);
}

// Side view in the east-up plane, equal scale on both axes, ground line at 0 m.
function sideView(states, idx) {
  const W = 360, H = 240, P = 36;
  // Horizontal axis: distance along the ground direction from the first to the last sample (east if none).
  const p0 = states[0].position_m, pn = states[states.length - 1].position_m, dh = Math.hypot(pn[0] - p0[0], pn[1] - p0[1]);
  const u = dh > 1e-9 ? [(pn[0] - p0[0]) / dh, (pn[1] - p0[1]) / dh] : [1, 0];
  const xs = states.map(s => (s.position_m[0] - p0[0]) * u[0] + (s.position_m[1] - p0[1]) * u[1]), zs = states.map(s => s.position_m[2]);
  // Show the 0 m line only when the path comes near it; a flight at 100 km would otherwise shrink to a dot.
  const zmin = Math.min(...zs), z1 = Math.max(...zs), ground = zmin <= 0.5 * (z1 - zmin);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), z0 = ground ? Math.min(0, zmin) : zmin;
  const span = Math.max(x1 - x0, z1 - z0, 1), k = Math.min((W - 2 * P) / span, (H - 2 * P) / span);
  const cx = (x0 + x1) / 2, X = x => W / 2 + (x - cx) * k, Y = z => H - P - (z - z0) * k;
  const svg = sv('svg', {viewBox: `0 0 ${W} ${H}`, role: 'img',
    'aria-label': `Side view, ground distance against altitude, equal scale: altitude from ${f(zs[0])} m to ${f(zs[zs.length - 1])} m over ${f(xs[xs.length - 1])} m of ground distance.`});
  if (ground) {
    svg.append(sv('line', {class: 'ground', x1: 0, x2: W, y1: Y(0), y2: Y(0)}));
    svg.append(sv('text', {class: 'axis', x: 4, y: Y(0) - 4}, '0 m altitude'));
  } else {
    svg.append(sv('text', {class: 'axis', x: 4, y: 14}, `altitude ${f(zmin, 0)} to ${f(z1, 0)} m; ground not in view`));
  }
  svg.append(sv('path', {class: 'line l1', d: states.map((s, i) => `${i ? 'L' : 'M'}${X(xs[i]).toFixed(1)},${Y(zs[i]).toFixed(1)}`).join('')}));
  const n = noseOf(states[idx].attitude), len = 22, nh = n[0] * u[0] + n[1] * u[1];
  // The body axis is drawn at a fixed screen length, projected on this plane; it shows direction, not size.
  svg.append(sv('line', {class: 'line l2', x1: X(xs[idx]), y1: Y(zs[idx]), x2: X(xs[idx]) + nh * len, y2: Y(zs[idx]) - n[2] * len}));
  svg.append(sv('circle', {class: 'cur', cx: X(xs[idx]), cy: Y(zs[idx]), r: 5}));
  const heading = `${f((Math.atan2(u[0], u[1]) * 180 / Math.PI + 360) % 360, 0)}° from north`;
  svg.append(sv('text', {class: 'axis', x: W - 4, y: H - 6, 'text-anchor': 'end'}, `ground distance towards ${heading}, ${f(span, 0)} m across`));
  return el('div', {class: 'panel'}, el('p', {class: 'chart-title'}, 'Trajectory, side view (ground distance and altitude, m, equal scale)'),
    el('div', {class: 'legend'}, el('span', {}, el('span', {class: 'sw sw1'}), 'recorded centre of mass'), el('span', {}, el('span', {class: 'sw sw2'}), 'body x axis (nose) at the selected sample')), svg);
}

// ---------------------------------------------------------------- result
function crossing(r) { return r.events.find(e => e.kind === 'ground_crossing'); }
function describeRun(r) {
  return `${r.request.mission.replaceAll('_', ' ')} · ${Object.entries(r.request.overrides).map(([k, v]) => `${k} ${+v.toFixed(4)}`).join(' · ')} · run ${r.run_id}`;
}
function drawResult() {
  const r = state.result;
  if (!r || !r.states.length) { $('result').replaceChildren(r ? el('p', {class: 'bad'}, 'The run produced no recorded samples.') : ''); return; }
  const verified = r.verdict.status === 'verified', pr = r.physics_reference, sum = r.summary, gc = crossing(r);
  const withheld = 'withheld: stored files differ from regeneration';
  const card = (label, value, cls) => el('div', {class: 'card'}, el('span', {class: 'meta'}, label), el('b', {class: cls}, value));
  const label = el('b', {id: 'sample-label', role: 'status', 'aria-live': 'polite'});
  const slider = el('input', {type: 'range', min: 0, max: r.states.length - 1, value: 0, 'aria-label': 'Sample', 'aria-describedby': 'sample-label', oninput: e => setIdx(+e.target.value)});
  const playBtn = el('button', {'aria-pressed': 'false', onclick: () => (state.timer ? stop() : play())}, 'play');
  const view = el('div', {id: 'sample-view'});
  state.ui = {r, label, slider, playBtn, view};
  const details = [
    el('h3', {}, 'Events'),
    el('ol', {}, r.events.map(e => el('li', {}, eventText(e)))),
    el('div', {class: 'controls'}, el('button', {'aria-label': 'Previous sample', onclick: () => stepBy(-1)}, '◀ step'), playBtn,
      el('button', {'aria-label': 'Next sample', onclick: () => stepBy(1)}, 'step ▶'), slider, label),
    view,
    el('p', {class: 'meta'}, 'Every chart plots recorded samples of this run, joined by straight lines. The side view projects the path onto the vertical plane through the first and last positions; motion out of that plane is in the sample values above. The body axis drawing shows direction only. Pointing at a chart selects the nearest sample.')];
  $('result').replaceChildren(
    el('h2', {id: 'result-heading', tabindex: '-1'}, verified ? 'Result' : 'Result: REJECTED evidence'),
    el('p', {class: 'meta'}, describeRun(r)),
    el('p', {class: 'statement ' + (verified ? 'ok' : 'bad')}, el('b', {}, 'Evidence (integrity and replay). '), verified
      ? `Verified: vv-rocket replay recomputed this run with the build named in Research and every byte of the trace matched${r.reused ? '; every stored file also matches a fresh regeneration' : ''}. This confirms the record, not the physics.`
      : `Not verified: ${r.verdict.reasons.join('; ')}.`),
    el('p', {class: 'statement ' + (pr.all_pass ? 'ok' : 'warn')}, el('b', {}, 'Physics reference verification of this build. '), pr.summary + '. Details in Research.'),
    el('p', {class: 'statement'}, el('b', {}, 'Model validity. '), r.model_validity, ' ', jetText(sum, verified, withheld)),
    el('div', {class: 'cards'},
      card('Simulated time', verified ? `${f(sum.final_time_s, 2)} s, ended by ${sum.end_reason === 'ground' ? '0 m crossing' : 'duration'}` : withheld),
      card('Highest altitude', verified ? `${f(sum.max_altitude_m)} m` : withheld),
      card('Highest speed', verified ? `${f(sum.max_speed_mps)} m/s` : withheld),
      card('Propellant used', verified ? `${f(sum.propellant_used_kg)} kg` : withheld),
      card('Centre of mass crossing 0 m', !verified ? withheld : gc
        ? `at ${f(gc.detail.estimated_time_s, 2)} s, vertical ${f(gc.detail.estimated_velocity_mps[2])} m/s, horizontal ${f(Math.hypot(gc.detail.estimated_velocity_mps[0], gc.detail.estimated_velocity_mps[1]))} m/s (estimate; no contact model)`
        : 'none in this run')),
    ...(verified ? details : [el('section', {class: 'unverified', 'aria-label': 'Unverified stored data'},
      el('b', {class: 'bad'}, 'UNVERIFIED stored data, shown for diagnosis only'), details)]));
  renderSample();
}
// Measured by vv-rocket at both ends of every burning step; see docs/m8-rocket-dynamics.md.
function jetText(sum, verified, withheld) {
  const eps = sum.max_neglected_jet_ratio;
  if (!verified) return `Neglected jet term: ${withheld}.`;
  if (!Number.isFinite(eps)) return 'Neglected jet term: not reported by this trace.';
  if (eps === 0) return 'The translational jet term the model neglects is zero in this run.';
  return `The model neglects a translational jet term; the largest value sampled at the ends of the burning steps of this run is ε = ${eps.toExponential(2)} of the thrust, at t = ${f(sum.max_neglected_jet_ratio_t_s, 2)} s (a diagnostic, not a pass or fail criterion). By the model's own estimate, not by measurement, the translational acceleration error is of that order; the model is adequate only while ε ≪ 1.`;
}
function eventText(e) {
  const t = `t = ${f(e.t_s, 2)} s: `, d = e.detail;
  if (e.kind === 'burn_start') return t + `burn ${d.burn} starts, ${f(d.thrust_n / 1000, 1)} kN along body ${vec(d.direction_body, 3)}.`;
  if (e.kind === 'burn_end') return t + `burn ${d.burn} ends, ${f(d.propellant_kg)} kg of propellant left.`;
  if (e.kind === 'ground_crossing') return t + `the centre of mass crossed 0 m altitude (estimated at ${f(d.estimated_time_s, 3)} s, velocity ${vec(d.estimated_velocity_mps, 1, 'm/s')}). No contact model: this is not a landing.`;
  if (e.kind === 'end') return t + `run ends (${d.reason === 'ground' ? 'stopped at the 0 m crossing' : 'end of the stored duration'}).`;
  return t + e.kind;
}
function renderSample() {
  const ui = state.ui; if (!ui) return;
  const r = ui.r, i = state.idx, s = r.states[i], ts = r.states.map(x => x.t_s), pick = j => setIdx(j);
  ui.slider.value = i;
  ui.label.setAttribute('aria-live', state.timer ? 'off' : 'polite');
  ui.label.textContent = `t = ${f(s.t_s, 2)} s (sample ${i + 1} of ${r.states.length})`;
  ui.slider.setAttribute('aria-valuetext', `t = ${f(s.t_s, 2)} s, altitude ${f(s.position_m[2])} m, speed ${f(norm(s.velocity_mps))} m/s`);
  ui.playBtn.textContent = state.timer ? 'pause' : 'play';
  ui.playBtn.setAttribute('aria-pressed', state.timer ? 'true' : 'false');
  const col = k => r.states.map(k);
  const charts = el('div', {class: 'charts'},
    sideView(r.states, i),
    chart({title: 'Altitude', unit: 'm', xs: ts, xLabel: 'time (s)', idx: i, onPick: pick, series: [{name: 'z', n: 1, ys: col(x => x.position_m[2])}]}),
    chart({title: 'Speed', unit: 'm/s', xs: ts, xLabel: 'time (s)', idx: i, onPick: pick, series: [{name: '|v|', n: 1, ys: col(x => norm(x.velocity_mps))}]}),
    chart({title: 'Mass', unit: 'kg', xs: ts, xLabel: 'time (s)', idx: i, onPick: pick, series: [{name: 'm', n: 1, ys: col(x => x.mass_kg)}]}),
    chart({title: 'Thrust and drag', unit: 'kN', xs: ts, xLabel: 'time (s)', idx: i, onPick: pick,
      series: [{name: 'thrust', n: 1, ys: col(x => x.thrust_n / 1000)}, {name: 'drag', n: 2, ys: col(x => norm(x.drag_inertial_n) / 1000)}]}),
    chart({title: 'Body axis tilt from vertical', unit: 'degrees', xs: ts, xLabel: 'time (s)', idx: i, onPick: pick, series: [{name: 'tilt', n: 1, ys: col(x => tiltDeg(x.attitude))}]}),
    chart({title: 'Angular velocity, body axes', unit: 'rad/s', xs: ts, xLabel: 'time (s)', idx: i, onPick: pick,
      series: [0, 1, 2].map(k => ({name: 'ω' + 'xyz'[k], n: k + 1, ys: col(x => x.angular_velocity_radps[k])}))}));
  const card = el('div', {class: 'panel'}, el('h3', {}, `Recorded sample at t = ${f(s.t_s, 2)} s (step ${s.step})`), el('dl', {class: 'kv'},
    el('dt', {}, 'position (east, north, up)'), el('dd', {}, vec(s.position_m, 2, 'm')),
    el('dt', {}, 'velocity'), el('dd', {}, vec(s.velocity_mps, 2, 'm/s')),
    el('dt', {}, 'attitude quaternion (w, x, y, z)'), el('dd', {}, vec(s.attitude, 5)),
    el('dt', {}, 'body x axis (east, north, up)'), el('dd', {}, `${vec(noseOf(s.attitude), 4)}, tilt ${f(tiltDeg(s.attitude), 2)}°`),
    el('dt', {}, 'angular velocity (body)'), el('dd', {}, vec(s.angular_velocity_radps, 4, 'rad/s')),
    el('dt', {}, 'mass / propellant'), el('dd', {}, `${f(s.mass_kg, 2)} kg / ${f(s.propellant_kg, 2)} kg`),
    el('dt', {}, 'centre of mass station'), el('dd', {}, `${f(s.cm_station_m, 3)} m from the nozzle exit`),
    el('dt', {}, 'inertia about the centre of mass'), el('dd', {}, vec(s.inertia_kgm2, 1, 'kg m²')),
    el('dt', {}, 'thrust from this sample'), el('dd', {}, `${f(s.thrust_n / 1000, 2)} kN, inertial ${vec(s.thrust_inertial_n.map(x => x / 1000), 2, 'kN')}`),
    el('dt', {}, 'drag'), el('dd', {}, vec(s.drag_inertial_n.map(x => x / 1000), 2, 'kN'))));
  ui.view.replaceChildren(card, charts);
}
function setIdx(i) { state.idx = Math.max(0, Math.min(state.ui.r.states.length - 1, i)); renderSample(); }
function stepBy(d) { setIdx(state.idx + d); }
function stop() { if (state.timer) clearInterval(state.timer); state.timer = null; if (state.ui) renderSample(); }
function play() {
  const n = state.ui.r.states.length, stride = Math.max(1, Math.round(n / 120));
  if (state.idx >= n - 1) state.idx = 0;
  state.timer = setInterval(() => { if (state.idx >= n - 1) { stop(); return; } setIdx(state.idx + stride); }, 100);
  renderSample();
}

function drawResearch() {
  const r = state.result, m = state.models.models[MODEL];
  const kv = obj => el('dl', {class: 'kv'}, Object.entries(obj).flatMap(([k, v]) => [el('dt', {}, k), el('dd', {}, el('code', {}, String(v)))]));
  const model = [el('h3', {}, 'Model'), kv({id: m.model.id, physics: m.model.physics, ...m.model.frames, units: Object.entries(m.model.units).map(([k, v]) => `${k} ${v}`).join(', ')})];
  if (!r) { $('panel-research').replaceChildren(el('p', {}, 'Run an experiment first; this panel then shows the exact request, provenance hashes, replay checks and the reference verification.'), ...model); return; }
  const pr = r.physics_reference, p = r.provenance;
  $('panel-research').replaceChildren(
    el('h2', {}, `Run ${r.run_id}`),
    el('h3', {}, 'Request (as validated by the adapter)'), el('pre', {}, JSON.stringify(r.request, null, 2)),
    ...model,
    el('h3', {}, 'Provenance'), el('p', {class: 'meta'}, 'run_id: first 16 hex characters of sha256 of the validated request, the case it produces and the vv-rocket binary hash.'), kv({adapter: r.adapter, source_sha256: p.source_sha256, binary_sha256: p.binary_sha256, manifest_sha256: p.manifest_sha256}),
    el('h3', {}, 'Input and artifact sha256'), kv(Object.assign({}, ...Object.entries(r.inputs).map(([k, v]) => ({['inputs/' + k]: v})), p.artifacts)),
    el('h3', {}, 'Replay checks (vv-rocket replay)'),
    el('ul', {}, (r.replay.checks || [{name: r.replay.status, pass: false}]).map(c => el('li', {class: c.pass ? 'ok' : 'bad'}, `${c.pass ? 'pass' : 'FAIL'}: ${c.name}`))),
    el('h3', {}, 'Integrity'), el('p', {class: r.integrity.problems.length ? 'bad' : 'ok'}, r.integrity.problems.length ? r.integrity.problems.join('; ') : r.reused ? 'All files match a fresh regeneration of this request.' : 'No integrity problem found.'),
    el('h3', {}, 'Reference verification (recomputed by this build for this response and compared with the stored verification.json)'),
    el('p', {}, pr.summary + '.'),
    el('div', {class: 'scroll'}, el('table', {class: 'cases'}, el('thead', {}, el('tr', {}, ['case', 'title', 'status of the active criteria'].map(h => el('th', {}, h)))),
      el('tbody', {}, pr.cases.map(c => el('tr', {}, el('td', {}, el('code', {}, c.id)), el('td', {}, c.title), el('td', {class: c.status === 'PASS' ? 'ok' : c.status === 'FAIL' ? 'bad' : 'warn'}, c.status)))))),
    ...pr.failed_criteria.map(x => el('div', {class: 'panel'}, el('b', {class: 'bad'}, `FAIL ${x.case}: ${x.metric}`),
      el('p', {}, `Observed ${x.value.toExponential(3)} ${x.unit}, pre-registered limit ${x.tolerance}. The criterion is kept as registered.`),
      x.diagnosis ? el('p', {}, x.diagnosis) : null)),
    pr.criteria_history.length ? el('h3', {}, 'First-run criteria kept as history (never counted as passes)') : '',
    ...pr.criteria_history.map(x => el('div', {class: 'panel'}, el('b', {class: 'warn'}, `${x.status.toUpperCase()} ${x.case}: ${x.metric}`),
      el('p', {}, `Observed ${x.value.toExponential(3)} ${x.unit}, limit ${x.tolerance}. ` + (x.superseded_by ? `Superseded by '${x.superseded_by}'; the limit is unchanged.` : `Invalid: ${x.note}.`)),
      x.diagnosis ? el('p', {}, x.diagnosis) : null)),
    el('h3', {}, 'Declared gaps'), el('ul', {}, pr.gaps.map(g => el('li', {}, `${g.id} (${g.status}): ${g.reason}`))));
}

async function boot() {
  wireTabs();
  try {
    state.models = await (await fetch('/api/models')).json();
    if (!state.models.models || !state.models.models[MODEL]) throw new Error('model missing');
  } catch (e) { setError('could not load the rocket model description from the local server.'); return; }
  $('physics').append(' ', el('span', {class: 'meta'}, `Model ${MODEL}; adapter contract ${state.models.schema}.`));
  drawRun(); drawResearch();
}
boot();
"""
