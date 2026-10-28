"""Mission Control page for the `rocket-landing` model (M9), served at /landing, and the campaign reader.

The page keeps three statements apart and never merges them: the mission outcome (requirements R1 to
R6 at contact), the flight-safety invariants S1 to S4, and the evidence verdict (integrity and replay).
Verdicts are shown only from a run whose replay verified; anything else is marked unverified. Charts plot
recorded samples only, as inline SVG without libraries. The campaign panel reads
`runs/m9-campaign/summary.json` from disk, labels it as such, and sends a clicked run back through the
adapter so that the per-run views are recomputed, not read from the campaign directory.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

CAMPAIGN_SCHEMA = "vv-m9-campaign.v1"
MAX_CAMPAIGN_BYTES = 8 * 1024 * 1024
MISSING = "no campaign evidence found; run `python scripts/m9_campaign.py`"

_TOP = ("preregistered", "seeds", "boundary_seeds", "total_runs", "command", "machine", "duration_s", "binary_sha256",
        "source_sha256", "determinism_check", "resummarized")
_ROWS = {
    "cells": ("fault", "policy", "runs", "landed", "landed_with_invariant_failure", "hard_landing", "no_contact",
              "invariant_failure_runs", "requirement_failures"),
    "pairs": ("fault", "pairs", "both_land", "only_baseline", "only_robust", "neither"),
    "hypotheses": ("id", "statement", "criterion", "observed", "verdict", "evidence", "complete"),
    "boundaries": ("fault", "policy", "magnitude", "runs", "landed"),
    "boundary_findings": ("fault", "policy", "first_magnitude_with_failures", "finding"),
    # `dir` is a path inside the campaign directory; the page never needs it.
    "runs": ("fault", "policy", "seed", "group", "magnitude", "window", "outcome", "failed", "exit_code", "replay"),
}


def load_campaign(path: Path | None) -> dict[str, Any]:
    """Read the campaign summary defensively. Never raises; anything unusable is `found: false`."""

    def missing(reason: str) -> dict[str, Any]:
        return {"found": False, "message": MISSING, "reason": reason}

    try:
        if path is None or path.is_symlink() or not path.is_file():
            return missing("summary.json not found")
        if path.stat().st_size > MAX_CAMPAIGN_BYTES:
            return missing("summary.json is larger than the limit")
        raw = path.read_bytes()
        data = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError):
        return missing("summary.json cannot be read as JSON")
    if not isinstance(data, dict) or data.get("schema") != CAMPAIGN_SCHEMA:
        return missing(f"summary.json is not a {CAMPAIGN_SCHEMA} document")
    out: dict[str, Any] = {k: data.get(k) for k in _TOP}
    for name, keys in _ROWS.items():
        rows = data.get(name, [])
        if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
            return missing(f"summary.json field {name} is not a list of objects")
        out[name] = [{k: r.get(k) for k in keys} for r in rows]
    limitations = data.get("limitations", [])
    if not isinstance(limitations, list) or not all(isinstance(x, str) for x in limitations):
        return missing("summary.json field limitations is not a list of strings")
    out["limitations"] = limitations
    return {"found": True, "schema": CAMPAIGN_SCHEMA, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
            "summary": out}


def landing_page(css: str) -> str:
    return PAGE.replace("/*CSS*/", css)


PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Mission Control: powered landing</title>
<style>/*CSS*/
:root{--s3:#1f9e89}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--s3:#22a58c}}
:root[data-theme="dark"]{--s3:#22a58c}
main{max-width:1200px}
.tabs{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0}
.tabs button[aria-selected="true"]{border:2px solid var(--text);font-weight:700}
button,select,input{font:inherit;font-size:14px;padding:6px 10px;border:1px solid var(--line);border-radius:8px;background:var(--surface);color:var(--text);min-height:36px}
button{cursor:pointer}
button:focus-visible,select:focus-visible,input:focus-visible,a:focus-visible{outline:2px solid var(--s1);outline-offset:2px}
button.primary{background:var(--s1);color:#fff;border-color:var(--s1);font-weight:700}
button:disabled{opacity:.6;cursor:default}
button[aria-pressed="true"]{border:2px solid var(--text);font-weight:700}
fieldset{border:1px solid var(--line);border-radius:10px;padding:12px;margin:12px 0;min-width:0}
legend{font-weight:700;padding:0 6px}
.choices{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:8px}
.choice{display:flex;gap:8px;align-items:flex-start;border:1px solid var(--line);border-radius:8px;padding:8px;min-width:0}
.choice input{min-height:auto;margin-top:4px}
.choice:has(input:checked){border:2px solid var(--s1)}
.choice:has(input:focus-visible){outline:2px solid var(--s1);outline-offset:2px}
input[aria-invalid="true"]{border:2px solid var(--bad)}
.physics{border-left:4px solid var(--s1);padding:4px 10px;background:var(--panel);max-width:80ch}
.ok{color:var(--good)}.bad{color:var(--bad)}.warn{color:var(--warn)}
.statement{border-left:4px solid var(--line);padding:4px 10px;margin:6px 0;max-width:90ch}
.statement.ok{border-color:var(--good)}.statement.bad{border-color:var(--bad)}.statement.warn{border-color:var(--warn)}
.statement b{color:var(--text)}
.controls{display:flex;flex-wrap:wrap;gap:8px 12px;align-items:center;margin:8px 0}
.controls label{display:flex;flex-wrap:wrap;gap:4px 8px;align-items:center}
input[type=number]{width:9em}
input[type=range]{flex:1;min-width:160px;padding:0}
.charts{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}
.charts .panel{margin:0;min-width:0}
.chart-title{font-weight:600;color:var(--text);font-size:14px;margin:0 0 4px}
.line{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}.l1{stroke:var(--s1)}.l2{stroke:var(--s2)}.l3{stroke:var(--s3)}
.dash{stroke-dasharray:7 4}.dots{stroke-dasharray:2 4}
.dot1{fill:var(--s1)}.dot2{fill:var(--s2)}.dot3{fill:var(--s3)}
.cursor{stroke:var(--text2);stroke-width:1;stroke-dasharray:3 3}
.span{fill:var(--warn);fill-opacity:.16}
.evt{stroke:var(--muted);stroke-width:1;stroke-dasharray:1 3}
.refline{stroke:var(--bad);stroke-width:1.5;stroke-dasharray:5 4}
.padc{fill:var(--good);fill-opacity:.12;stroke:var(--good);stroke-width:1.5}
.keepc{fill:none;stroke:var(--bad);stroke-width:1.5;stroke-dasharray:5 4}
.end{fill:var(--surface);stroke:var(--text);stroke-width:2}
.legend{align-items:center;flex-wrap:wrap;gap:4px 14px}
.legend svg{width:26px;height:10px;display:inline-block;vertical-align:middle;margin-right:4px}
dl.kv{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:4px 12px;margin:0}
dl.kv dt{color:var(--muted)}dl.kv dd{margin:0;overflow-wrap:anywhere;font-variant-numeric:tabular-nums}
@media (max-width:480px){dl.kv{grid-template-columns:minmax(0,1fr)}}
.grid2{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px}
@media (max-width:820px){.grid2{grid-template-columns:minmax(0,1fr)}}
.grid2>*{min-width:0}
.scroll table{min-width:560px}.scroll table.narrow{min-width:0}
tr.differs td{background:var(--panel);font-weight:600}
td.num,th.num{text-align:right;white-space:nowrap}
.unverified{border:2px dashed var(--bad);border-radius:10px;padding:8px;margin:8px 0;min-width:0;overflow-wrap:anywhere}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.4 ui-monospace,Consolas,monospace}
.alert{border:2px solid var(--bad);border-radius:8px;padding:8px 12px}
.note{border:1px solid var(--line);border-radius:8px;padding:8px 12px;margin:8px 0;max-width:90ch}
.matrix button{width:100%;text-align:left;min-height:44px}
.matrix button[aria-pressed="true"]{outline:2px solid var(--text)}
.matrix td{vertical-align:middle}
.sub{display:block;font-size:12px;color:var(--muted);font-weight:400}
.cols3{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}
.cols3>*{min-width:0}
[hidden]{display:none!important}
</style></head>
<body><main>
<p class="meta">V&amp;V lab · Mission Control · <a href="/">Ground vehicle (2D)</a> · <a href="/rocket">Rocket stage (6-DOF)</a> · Powered landing (closed loop)</p>
<h1>Mission Control: powered landing</h1>
<p class="physics" id="physics"><b>Closed-loop landing of a rocket stage.</b> A controller sees only noisy sensor readings
(radar altimeter, GNSS, IMU), commands throttle and thrust vector, and tries to land on a pad. A separate verifier judges the
true state at touchdown against six requirements and the whole flight against four safety invariants. Idealized demonstrator:
not flight software, not validated against flight data, no contact model (touchdown is the nozzle exit plane reaching the
ground). Requirements, noise and fault ranges are assumed values.</p>
<div class="tabs" role="tablist" aria-label="Sections">
<button role="tab" id="tab-run" aria-controls="panel-run" aria-selected="true">Run</button>
<button role="tab" id="tab-campaign" aria-controls="panel-campaign" aria-selected="false" tabindex="-1">Campaign evidence</button>
<button role="tab" id="tab-claims" aria-controls="panel-claims" aria-selected="false" tabindex="-1">What is claimed</button>
<button role="tab" id="tab-research" aria-controls="panel-research" aria-selected="false" tabindex="-1">Research</button>
</div>
<section id="panel-run" role="tabpanel" aria-labelledby="tab-run"></section>
<section id="panel-campaign" role="tabpanel" aria-labelledby="tab-campaign" hidden></section>
<section id="panel-claims" role="tabpanel" aria-labelledby="tab-claims" hidden></section>
<section id="panel-research" role="tabpanel" aria-labelledby="tab-research" hidden></section>
<p id="status" role="status" aria-live="polite" class="meta"></p>
<div id="error" role="alert"></div>
<section id="result" aria-label="Run result"></section>
<noscript>Mission Control needs JavaScript.</noscript>
<script src="/landing.js"></script>
</main></body></html>
"""

LANDING_JS = r"""
'use strict';
const SCHEMA = 'vv-sim-run-request.v3', MODEL = 'rocket-landing', ZOOM_S = 20;
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
// replaceChildren would turn a null child into the text "null".
const fill = (node, ...kids) => node.replaceChildren(...kids.flat().filter(k => k !== null && k !== undefined && k !== false));
const f = (x, d = 1) => Number.isFinite(x) ? (Object.is(+x.toFixed(d), -0) ? 0 : x).toFixed(d) : 'n/a';
const g3 = x => !Number.isFinite(x) ? 'n/a' : Math.abs(x) >= 100 ? f(x, 1) : String(+x.toPrecision(3));
// Cosines sit close to 1, where three significant figures would hide the margin.
const val = (x, unit) => unit === 'cos' ? f(x, 5) : g3(x);
const words = s => String(s).replaceAll('_', ' ');
const POLICY_NAMES = ['baseline', 'robust'];

const state = {models: null, caps: null, kind: 'nominal', policy: 'baseline', mode: null, single: null, pair: null,
  note: null, zoom: 'full', t: 0, busy: false, campaign: null, campaignFilter: null, tab: 'run'};

function setStatus(t) { $('status').textContent = t; }
function setError(t) { fill($('error'), t ? el('p', {class: 'alert', id: 'error-text'}, el('b', {}, 'Could not run: '), t) : ''); }
const FIELD_FOR_ERROR = [['fault.magnitude', 'ln-magnitude'], ['fault.start_s', 'ln-start'], ['fault.end_s', 'ln-end'], ['seed', 'ln-seed']];
function markField(message) {
  document.querySelectorAll('[aria-invalid]').forEach(n => { n.removeAttribute('aria-invalid'); n.removeAttribute('aria-describedby'); });
  const old = $('field-error'); if (old) old.remove();
  const hit = message && FIELD_FOR_ERROR.find(([prefix]) => message.startsWith(prefix)), input = hit && $(hit[1]);
  if (!input || state.tab !== 'run') return false;
  (input.closest('label') || input).after(el('p', {class: 'alert', id: 'field-error'}, message));
  input.setAttribute('aria-invalid', 'true'); input.setAttribute('aria-describedby', 'field-error'); input.focus();
  return true;
}

// ---------------------------------------------------------------- requests
const faultOf = kind => state.caps.faults.find(x => x.kind === kind);
function describeFault(fl) {
  if (!fl) return 'no fault (nominal)';
  const info = faultOf(fl.kind), unit = info && info.magnitude ? ' ' + info.magnitude.unit : '';
  return `${info ? info.label : words(fl.kind)}${info && info.magnitude ? ' ' + g3(fl.magnitude) + unit : ''}, ${f(fl.start_s, 2)} s to ${f(fl.end_s, 2)} s`;
}
function formRequest(policy) {
  const num = id => { const v = $(id).value.trim(); return v === '' ? null : Number(v); };
  const seed = num('ln-seed');
  if (state.kind === 'nominal') return {schema: SCHEMA, model: MODEL, policy, seed, fault: null};
  const info = faultOf(state.kind);
  return {schema: SCHEMA, model: MODEL, policy, seed,
    fault: {kind: state.kind, magnitude: info.magnitude ? num('ln-magnitude') : 0, start_s: num('ln-start'), end_s: num('ln-end')}};
}

async function post(body) {
  const resp = await fetch('/api/run', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  const data = await resp.json().catch(() => ({error: `server answered ${resp.status} without JSON`}));
  if (!resp.ok || data.error) throw new Error(data.error || `server answered ${resp.status}`);
  if (typeof data.run_id !== 'string' || !data.verdict || !data.verification || !Array.isArray(data.states)) {
    throw new Error('the server answered without a run id, verdict or verification; nothing from that answer is shown');
  }
  return data;
}
async function runBodies(bodies, note) {
  if (state.busy) return false;
  state.busy = true; setError('');
  document.querySelectorAll('button.primary').forEach(b => { b.disabled = true; b.setAttribute('aria-busy', 'true'); });
  try {
    const out = [];
    for (let i = 0; i < bodies.length; i++) {
      setStatus(`Running ${bodies[i].policy} policy (${i + 1} of ${bodies.length}): simulation, then replay by the Rust build…`);
      out.push(await post(bodies[i]));
    }
    state.note = note || null;
    if (out.length === 1) { state.mode = 'single'; state.single = out[0]; } else { state.mode = 'compare'; state.pair = {baseline: out[0], robust: out[1]}; }
    state.t = endAll();  // the cursor starts at touchdown, where the requirements are judged
    markField('');
    const bad = out.filter(r => r.verdict.status !== 'verified');
    setStatus(bad.length ? `Run ${bad.map(r => r.run_id).join(', ')}: the stored run does not match a fresh regeneration or its replay. Nothing from it is verified evidence.`
      : `${out.length === 1 ? 'Run ' + out[0].run_id : 'Both runs'} finished and replay verified${out.some(r => r.reused) ? ' (stored runs regenerated and compared)' : ''}.`);
    selectTab('run'); drawResult(); drawResearch(); $('result-heading').focus();
    return true;
  } catch (e) {
    const message = e && e.message && !(e instanceof TypeError) ? e.message : 'the local server did not respond. Is mission_control.py still running?';
    setError(markField(message) ? 'one parameter is not an allowed value; see the highlighted field.' : message);
    setStatus(state.mode ? 'Nothing new was run. The result below is still the previous one.' : '');
    return false;
  } finally {
    state.busy = false;
    document.querySelectorAll('button.primary').forEach(b => { b.disabled = false; b.removeAttribute('aria-busy'); });
  }
}
const runOne = () => runBodies([formRequest(state.policy)]);
const runCompare = () => runBodies(POLICY_NAMES.map(formRequest));

// ---------------------------------------------------------------- tabs
const TABS = ['run', 'campaign', 'claims', 'research'];
function selectTab(name) {
  state.tab = name;
  for (const t of TABS) {
    const on = t === name;
    $('tab-' + t).setAttribute('aria-selected', on ? 'true' : 'false');
    $('tab-' + t).setAttribute('tabindex', on ? '0' : '-1');
    $('panel-' + t).hidden = !on;
  }
  $('result').hidden = name !== 'run';
  if (name === 'campaign' && !state.campaign) loadCampaign();
}
function wireTabs() {
  TABS.forEach((name, i) => {
    $('tab-' + name).addEventListener('click', () => selectTab(name));
    $('tab-' + name).addEventListener('keydown', e => {
      const d = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
      if (!d) return;
      const next = TABS[(i + d + TABS.length) % TABS.length];
      selectTab(next); $('tab-' + next).focus(); e.preventDefault();
    });
  });
}

// ---------------------------------------------------------------- run form
function drawRun() {
  const caps = state.caps;
  const scenarios = [{kind: 'nominal', label: 'Nominal', description: 'No fault. Sensor noise is on; with seed 0 the initial state and the vehicle are exactly nominal.', range: ''}]
    .concat(caps.faults.map(x => ({kind: x.kind, label: x.label, description: x.description, range: rangeText(x)})));
  const pick = el('fieldset', {}, el('legend', {}, '1. Choose a scenario'),
    el('div', {class: 'choices'}, scenarios.map(s => el('label', {class: 'choice'},
      el('input', {type: 'radio', name: 'scenario', value: s.kind, checked: s.kind === state.kind, onchange: () => { state.kind = s.kind; drawParams(); }}),
      el('span', {}, el('b', {}, s.label), el('br'), el('span', {class: 'meta'}, s.description + (s.range ? ' Pre-registered range: ' + s.range : '')))))));
  const params = el('fieldset', {id: 'params'});
  const policy = el('fieldset', {}, el('legend', {}, '3. Choose the controller policy'),
    el('div', {class: 'choices'}, caps.policies.map(p => el('label', {class: 'choice'},
      el('input', {type: 'radio', name: 'policy', value: p.id, checked: p.id === state.policy, onchange: () => { state.policy = p.id; }}),
      el('span', {}, el('b', {}, p.id), el('br'), el('span', {class: 'meta'}, p.description))))));
  const seed = el('fieldset', {}, el('legend', {}, '4. Choose the seed'),
    el('div', {class: 'controls'}, el('label', {}, 'Seed ', el('input', {type: 'number', id: 'ln-seed', value: 0, min: caps.seed.min, max: caps.seed.max, step: 1, inputmode: 'numeric'}),
      el('span', {class: 'meta'}, ` [${caps.seed.min}, ${caps.seed.max}]`))),
    el('p', {class: 'meta'}, caps.seed.note));
  const run = el('button', {class: 'primary', onclick: runOne}, 'Run with the chosen policy');
  const compare = el('button', {class: 'primary', onclick: runCompare}, 'Compare policies on this case');
  fill($('panel-run'), pick, params, policy, seed,
    el('div', {class: 'controls'}, run, compare),
    el('p', {class: 'meta'}, 'Compare policies runs baseline and robust on exactly the same seed and fault, one after the other, and shows the difference in the requirement verdicts. Each run is replayed by the Rust build before any verdict is shown.'));
  drawParams();
}
function rangeText(x) {
  const parts = [];
  if (x.magnitude) parts.push(`magnitude ${x.magnitude.min} to ${x.magnitude.max} ${x.magnitude.unit}`);
  if (x.window_length_s) parts.push(`window of ${x.window_length_s.min} to ${x.window_length_s.max} s`);
  return parts.length ? parts.join(', ') + '.' : 'any window.';
}
function drawParams() {
  const box = $('params'); if (!box) return;
  const legend = el('legend', {}, '2. Set the fault');
  if (state.kind === 'nominal') { fill(box, legend, el('p', {class: 'meta'}, 'Nominal scenario: there is no fault to set.')); markField(''); return; }
  const x = faultOf(state.kind), t = state.caps.time;
  const fields = [];
  if (x.magnitude) fields.push(el('label', {}, `Magnitude (${x.magnitude.unit}) `, el('input', {type: 'number', id: 'ln-magnitude', value: x.magnitude.default,
    min: x.magnitude.min, max: x.magnitude.max, step: 'any', inputmode: 'decimal'}), el('span', {class: 'meta'}, ` [${x.magnitude.min}, ${x.magnitude.max}]`)));
  fields.push(el('label', {}, 'Window start (s) ', el('input', {type: 'number', id: 'ln-start', value: x.default_start_s, min: 0, max: t.duration_s, step: t.step_s, inputmode: 'decimal'})));
  fields.push(el('label', {}, 'Window end (s) ', el('input', {type: 'number', id: 'ln-end', value: x.default_end_s, min: 0, max: t.duration_s, step: t.step_s, inputmode: 'decimal'})));
  const win = x.window_length_s ? `The window must last ${x.window_length_s.min} to ${x.window_length_s.max} s.` : 'The window may be any length up to the end of the run.';
  fill(box, legend, el('div', {class: 'controls'}, fields),
    el('p', {class: 'meta'}, `${x.description} ${win} Times are multiples of ${t.step_s} s, within 0 to ${t.duration_s} s. The adapter and the Rust library refuse any value outside the pre-registered range. Defaults are the demonstration values.`));
  markField('');
}

// ---------------------------------------------------------------- run helpers
const verified = r => r.verdict.status === 'verified';
const endT = r => r.states.length ? r.states[r.states.length - 1].t_s : 0;
const reqOf = (r, prefix) => (r.verification.requirements || []).find(x => x.id.startsWith(prefix));
function nearest(r, t) {
  const s = r.states; let lo = 0, hi = s.length - 1;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (s[mid].t_s < t) lo = mid + 1; else hi = mid; }
  return lo > 0 && Math.abs(s[lo - 1].t_s - t) <= Math.abs(s[lo].t_s - t) ? lo - 1 : lo;
}
// The estimate is of the centre of mass; the altimeter and the contact point are on the nozzle plane. The estimate is
// moved to the nozzle plane with the true offset of that sample, so the gap to the truth is the estimator error alone.
const offset = s => s.truth.position_m[2] - s.truth.base_position_m[2];
const cols = {
  truth: s => s.truth.base_position_m[2],
  altimeter: s => s.observation && s.observation.altimeter_m !== null ? s.observation.altimeter_m : NaN,
  estimate: s => s.estimate.position_m[2] - offset(s),
  estErr: s => s.estimate.position_m[2] - s.truth.position_m[2],
  altErr: s => s.observation && s.observation.altimeter_m !== null ? s.observation.altimeter_m - s.truth.base_position_m[2] : NaN,
  vz: s => s.truth.base_velocity_mps[2],
  vzEst: s => s.estimate.velocity_mps[2],
  cmd: s => s.command.throttle,
  applied: s => s.applied.throttle,
  gy: s => s.applied.gimbal_tan[0],
  gz: s => s.applied.gimbal_tan[1],
};
const col = (r, name) => r.states.map(cols[name]);
const ts = r => r.states.map(s => s.t_s);

function faultSpans(r) {
  const end = endT(r);
  return (r.verification.faults || []).filter(x => x.start_s < end).map(x => ({from: x.start_s, to: Math.min(x.end_s, end), name: words(x.kind)}));
}
function eventMarks(r) {
  return r.events.filter(e => ['ignition', 'cutoff', 'flameout', 'touchdown'].includes(e.kind)).map(e => ({t: e.t_s, name: e.kind}));
}
function eventText(e) {
  const t = `t = ${f(e.t_s, 2)} s: `, d = e.detail || {};
  if (e.kind === 'ignition') return t + `engine ignites${d.command_t_s !== undefined && Math.abs(d.command_t_s - e.t_s) > 1e-9 ? ` (commanded at ${f(d.command_t_s, 2)} s, ${f(e.t_s - d.command_t_s, 2)} s late)` : ' as commanded'}.`;
  if (e.kind === 'fault_start') return t + `fault starts: ${words(d.fault)}${d.magnitude ? ' (magnitude ' + g3(d.magnitude) + ')' : ''}.`;
  if (e.kind === 'fault_end') return t + `fault ends: ${words(d.fault)}.`;
  if (e.kind === 'cutoff') return t + 'the controller cuts the engine off; it cannot relight.';
  if (e.kind === 'flameout') return t + 'propellant exhausted, the engine goes out.';
  if (e.kind === 'touchdown') return t + 'the nozzle exit plane reaches the ground. No contact dynamics: this instant is interpolated within the step.';
  if (e.kind === 'end') return t + `run ends (${d.reason === 'touchdown' ? 'at touchdown' : words(d.reason || 'end of duration')}).`;
  return t + words(e.kind);
}

// ---------------------------------------------------------------- statements and tables
function failedReqs(r) { return (r.verification.requirements || []).filter(x => x.evaluated && !x.pass); }
function failedInvs(r) { return (r.verification.invariants || []).filter(x => x.evaluated && !x.pass); }
const short = id => id.split('_')[0];
const WITHHELD = 'withheld: this run is not verified evidence';
function statements(r) {
  const ok = verified(r), v = r.verification;
  let outcome;
  if (!ok) outcome = el('p', {class: 'statement bad'}, el('b', {}, 'Mission outcome. '), WITHHELD + '.');
  else if (v.outcome === 'landed') outcome = el('p', {class: 'statement ok'}, el('b', {}, 'Mission outcome: landed. '), 'Touchdown happened and all six contact requirements, R1 to R6, are met on the true state.');
  else if (v.outcome === 'hard_landing') outcome = el('p', {class: 'statement bad'}, el('b', {}, 'Mission outcome: hard landing. '),
    `Touchdown happened but ${failedReqs(r).map(x => short(x.id)).join(', ')} ${failedReqs(r).length > 1 ? 'are' : 'is'} not met (see the table).`);
  else outcome = el('p', {class: 'statement bad'}, el('b', {}, 'Mission outcome: no contact. '), 'The run ended without the nozzle plane reaching the ground, so no requirement was evaluated.');
  let inv;
  if (!ok) inv = el('p', {class: 'statement bad'}, el('b', {}, 'Safety invariants. '), WITHHELD + '.');
  else if (failedInvs(r).length) inv = el('p', {class: 'statement bad'}, el('b', {}, 'Safety invariants: violated. '), `${failedInvs(r).map(x => short(x.id)).join(', ')} failed during the flight, whatever the mission outcome.`);
  else inv = el('p', {class: 'statement ok'}, el('b', {}, 'Safety invariants: all hold. '), 'S1 to S4 held at every step of the flight (S2 is checked at contact). This is separate from the mission outcome.');
  const ev = el('p', {class: 'statement ' + (ok ? 'ok' : 'bad')}, el('b', {}, 'Evidence (integrity and replay). '), ok
    ? `Verified: vv-rocket replay recomputed the trace, the requirement and invariant verdicts and the manifest from the stored case and seed, and each matched byte for byte${r.reused ? '; every stored file also matches a fresh regeneration' : ''}. This confirms the record, not the physics.`
    : `Not verified: ${r.verdict.reasons.join('; ')}.`);
  return [outcome, inv, ev];
}
// The verifier marks a fault window that never acted; such a run is effectively fault-free.
function actedNote(r) {
  const idle = verified(r) ? (r.verification.faults || []).filter(x => x.acted === false) : [];
  return idle.length ? el('p', {class: 'statement warn'}, el('b', {}, 'The fault never acted. '),
    `${idle.map(x => words(x.kind)).join(', ')}: the verifier reports that the window never acted on the vehicle or the sensors (for example it closed before the event it affects), so this run behaves like a run without the fault.`) : null;
}
function limitText(x) { return x.expected || `${x.limit} ${x.unit}`; }
function reqTable(r) {
  const ok = verified(r), labels = state.caps.labels;
  const rows = (r.verification.requirements || []).map(x => el('tr', {},
    el('td', {}, el('b', {}, short(x.id)), ' ', labels[x.id] || words(x.id)),
    el('td', {}, el('code', {}, limitText(x))),
    el('td', {class: 'num'}, !ok ? 'withheld' : x.evaluated ? `${val(x.value, x.unit)} ${x.unit}` : 'not evaluated'),
    el('td', {class: !ok ? '' : !x.evaluated ? 'warn' : x.pass ? 'ok' : 'bad'}, !ok ? 'withheld' : !x.evaluated ? 'not evaluated' : x.pass ? 'pass' : 'FAIL',
      ok && x.evaluated && !x.pass && x.cause && x.cause.length ? el('span', {class: 'sub'}, 'active fault: ' + x.cause.map(words).join(', ')) : null)));
  return el('div', {}, el('div', {class: 'scroll'}, el('table', {}, el('thead', {}, el('tr', {}, ['Requirement', 'Limit', 'Observed', 'Result'].map(h => el('th', {}, h)))), el('tbody', {}, rows))),
    el('p', {class: 'meta'}, 'Assumed demonstrator requirements, fixed before any run; not specifications of a real vehicle. They are evaluated on the true state at touchdown, never on sensor readings.'));
}
function invTable(r) {
  const ok = verified(r), labels = state.caps.labels;
  const rows = (r.verification.invariants || []).map(x => el('tr', {},
    el('td', {}, el('b', {}, short(x.id)), ' ', labels[x.id] || words(x.id)),
    el('td', {}, el('code', {}, `${x.limit} ${x.unit}`)),
    el('td', {class: 'num'}, !ok ? 'withheld' : x.worst_value === null || x.worst_value === undefined ? 'n/a' : `${val(x.worst_value, x.unit)} ${x.unit}`),
    el('td', {class: !ok ? '' : x.pass ? 'ok' : 'bad'}, !ok ? 'withheld' : x.pass ? 'holds' : `VIOLATED (${x.failure_count} step${x.failure_count === 1 ? '' : 's'})`),
    el('td', {}, !ok ? 'withheld' : x.first_failure ? `t = ${f(x.first_failure.t_s, 2)} s: expected ${x.first_failure.expected}, observed ${x.first_failure.observed}${x.first_failure.cause && x.first_failure.cause.length ? '; active fault: ' + x.first_failure.cause.map(words).join(', ') : ''}` : 'none')));
  return el('div', {class: 'scroll'}, el('table', {}, el('thead', {}, el('tr', {}, ['Invariant', 'Limit', 'Worst value', 'Result', 'First failure'].map(h => el('th', {}, h)))), el('tbody', {}, rows)));
}
function touchdownCard(r) {
  const td = r.verification.touchdown;
  if (!td) return el('p', {class: 'meta'}, 'No touchdown in this run.');
  const t = td.truth, bv = t.base_velocity_mps, bp = t.base_position_m;
  return el('dl', {class: 'kv'},
    el('dt', {}, 'time'), el('dd', {}, `${f(td.t_s, 2)} s (step ${td.step}, interpolated at ${f(td.fraction * 100, 0)}% of the step)`),
    el('dt', {}, 'nozzle-plane position (x, y)'), el('dd', {}, `(${f(bp[0], 2)}, ${f(bp[1], 2)}) m, ${f(Math.hypot(bp[0], bp[1]), 2)} m from the pad centre`),
    el('dt', {}, 'vertical speed'), el('dd', {}, `${f(bv[2], 2)} m/s`),
    el('dt', {}, 'horizontal speed'), el('dd', {}, `${f(Math.hypot(bv[0], bv[1]), 2)} m/s`),
    el('dt', {}, 'tilt from vertical'), el('dd', {}, `${f(Math.acos(Math.min(1, t.tilt_cos)) * 180 / Math.PI, 2)}° (cosine ${f(t.tilt_cos, 5)})`),
    el('dt', {}, 'angular rate'), el('dd', {}, `${g3(Math.hypot(...t.angular_velocity_radps))} rad/s`),
    el('dt', {}, 'propellant left'), el('dd', {}, `${f(t.propellant_kg, 1)} kg of ${f(r.states[0].truth.propellant_kg, 1)} kg`));
}

// ---------------------------------------------------------------- charts
function niceTicks(lo, hi, n = 4) {
  if (!(hi > lo)) { lo -= 1; hi += 1; }
  const raw = (hi - lo) / n, p = Math.pow(10, Math.floor(Math.log10(raw))), step = [1, 2, 5, 10].map(s => s * p).find(s => s >= raw);
  const out = []; for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) out.push(+v.toFixed(10));
  return {ticks: out, lo: Math.min(lo, out[0]), hi: Math.max(hi, out[out.length - 1])};
}
function legend(series) {
  return el('div', {class: 'legend meta'}, series.map(s => el('span', {}, sv('svg', {viewBox: '0 0 26 10', 'aria-hidden': 'true'},
    sv('line', {class: `line l${s.n}${s.style ? ' ' + s.style : ''}`, x1: 1, x2: 25, y1: 5, y2: 5})), s.name)));
}
const endAll = () => state.mode === 'compare' ? Math.max(...POLICY_NAMES.map(p => endT(state.pair[p]))) : endT(state.single);
function window_() {
  const end = endAll();
  return state.zoom === 'final' ? [Math.max(0, end - ZOOM_S), end] : [0, end];
}
// series: [{name, xs, ys, n, style}]. Lines break at missing values (sensor dropouts) instead of bridging them.
function timeChart({title, unit, series, refs = [], spans = [], marks = [], note}) {
  const W = 360, H = 200, L = 50, R = 12, T = 10, B = 32, [x0, x1] = window_(), t = state.t;
  const inside = (s, i) => s.xs[i] >= x0 - 1e-9 && s.xs[i] <= x1 + 1e-9 && Number.isFinite(s.ys[i]);
  const ys = series.flatMap(s => s.ys.filter((y, i) => inside(s, i))).concat(refs.map(x => x.y));
  const xr = niceTicks(x0, x1), yr = niceTicks(ys.length ? Math.min(...ys) : 0, ys.length ? Math.max(...ys) : 1);
  const X = x => L + (x - xr.lo) / (xr.hi - xr.lo) * (W - L - R), Y = y => H - B - (y - yr.lo) / (yr.hi - yr.lo) * (H - T - B);
  const summary = series.map(s => { const v = s.ys.filter((y, i) => inside(s, i)); return v.length ? `${s.name} from ${g3(v[0])} to ${g3(v[v.length - 1])} ${unit}` : `${s.name} has no value in this window`; }).join('; ');
  const svg = sv('svg', {viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': `${title}: ${summary}. Use the time slider for exact values.`});
  for (const v of yr.ticks) { svg.append(sv('line', {class: 'grid', x1: L, x2: W - R, y1: Y(v), y2: Y(v)})); svg.append(sv('text', {class: 'axis', x: L - 6, y: Y(v) + 4, 'text-anchor': 'end'}, String(v))); }
  for (const v of xr.ticks) svg.append(sv('text', {class: 'axis', x: X(v), y: H - B + 16, 'text-anchor': 'middle'}, String(v)));
  svg.append(sv('text', {class: 'axis', x: W - R, y: H - 4, 'text-anchor': 'end'}, 'time (s)'));
  if (yr.lo < 0 && yr.hi > 0) svg.append(sv('line', {class: 'zero', x1: L, x2: W - R, y1: Y(0), y2: Y(0)}));
  for (const sp of spans) {
    const a = Math.max(sp.from, xr.lo), b = Math.min(sp.to, xr.hi);
    if (b > a) svg.append(sv('rect', {class: 'span', x: X(a), y: T, width: Math.max(1, X(b) - X(a)), height: H - T - B}, sv('title', {}, `active fault: ${sp.name}`)));
  }
  for (const m of marks) if (m.t >= xr.lo && m.t <= xr.hi) svg.append(sv('line', {class: 'evt', x1: X(m.t), x2: X(m.t), y1: T, y2: H - B}, sv('title', {}, `${m.name} at ${f(m.t, 2)} s`)));
  for (const r of refs) { svg.append(sv('line', {class: 'refline', x1: L, x2: W - R, y1: Y(r.y), y2: Y(r.y)})); svg.append(sv('text', {class: 'axis', x: W - R - 2, y: Y(r.y) - 4, 'text-anchor': 'end'}, r.label)); }
  for (const s of series) {
    let d = '', pen = false;
    s.xs.forEach((x, i) => { if (inside(s, i)) { d += `${pen ? 'L' : 'M'}${X(x).toFixed(1)},${Y(s.ys[i]).toFixed(1)}`; pen = true; } else pen = false; });
    svg.append(sv('path', {class: `line l${s.n}${s.style ? ' ' + s.style : ''}`, d}));
  }
  if (t >= xr.lo && t <= xr.hi) {
    svg.append(sv('line', {class: 'cursor', x1: X(t), x2: X(t), y1: T, y2: H - B}));
    for (const s of series) { const i = nearestIn(s.xs, t); if (i >= 0 && Math.abs(s.xs[i] - t) < 0.15 && Number.isFinite(s.ys[i])) svg.append(sv('circle', {class: `dot${s.n}`, cx: X(s.xs[i]), cy: Y(s.ys[i]), r: 4})); }
  }
  const hit = sv('rect', {x: L, y: T, width: W - L - R, height: H - T - B, fill: 'transparent'});
  const pick = e => { const box = svg.getBoundingClientRect(); setTime(xr.lo + ((e.clientX - box.left) * W / box.width - L) / (W - L - R) * (xr.hi - xr.lo)); };
  hit.addEventListener('pointermove', pick); hit.addEventListener('pointerdown', pick);
  svg.append(hit);
  return el('div', {class: 'panel'}, el('p', {class: 'chart-title'}, `${title} (${unit})`), legend(series), svg, note ? el('p', {class: 'meta'}, note) : null);
}
function nearestIn(xs, t) {
  let lo = 0, hi = xs.length - 1; if (hi < 0) return -1;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (xs[mid] < t) lo = mid + 1; else hi = mid; }
  return lo > 0 && Math.abs(xs[lo - 1] - t) <= Math.abs(xs[lo] - t) ? lo - 1 : lo;
}
function trackChart(runs) {
  const pad = state.caps.requirements.pad_radius_m, keep = state.caps.requirements.keep_out_radius_m, W = 360, L = 40, R = 12, T = 10, B = 30;
  const pts = runs.flatMap(x => x.r.states.map(s => s.truth.base_position_m));
  const xlo = Math.min(-keep, ...pts.map(p => p[0])), xhi = Math.max(keep, ...pts.map(p => p[0]));
  const ylo = Math.min(-keep, ...pts.map(p => p[1])), yhi = Math.max(keep, ...pts.map(p => p[1]));
  const k = (W - L - R) / (xhi - xlo), H = Math.min(340, Math.round((yhi - ylo) * k) + T + B);
  const sc = Math.min(k, (H - T - B) / (yhi - ylo)), X = x => L + (x - xlo) * sc, Y = y => H - B - (y - ylo) * sc;
  const svg = sv('svg', {viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': `Ground track of the nozzle exit plane, east against north, equal scale, with the ${pad} m pad radius and the ${keep} m keep-out radius. ` +
    runs.map(x => { const p = x.r.states[x.r.states.length - 1].truth.base_position_m; return `${x.name} ends ${f(Math.hypot(p[0], p[1]), 1)} m from the pad centre`; }).join('; ') + '.'});
  const xt = niceTicks(xlo, xhi, 5), yt = niceTicks(ylo, yhi, 4);
  for (const v of xt.ticks) { svg.append(sv('line', {class: 'grid', x1: X(v), x2: X(v), y1: T, y2: H - B})); svg.append(sv('text', {class: 'axis', x: X(v), y: H - B + 14, 'text-anchor': 'middle'}, String(v))); }
  for (const v of yt.ticks) { svg.append(sv('line', {class: 'grid', x1: L, x2: W - R, y1: Y(v), y2: Y(v)})); svg.append(sv('text', {class: 'axis', x: L - 5, y: Y(v) + 4, 'text-anchor': 'end'}, String(v))); }
  svg.append(sv('circle', {class: 'keepc', cx: X(0), cy: Y(0), r: keep * sc}, sv('title', {}, `S2 keep-out radius ${keep} m`)));
  svg.append(sv('circle', {class: 'padc', cx: X(0), cy: Y(0), r: pad * sc}, sv('title', {}, `R5 pad radius ${pad} m`)));
  svg.append(sv('text', {class: 'axis', x: X(0) + keep * sc * 0.72, y: Y(0) - keep * sc * 0.72 - 3}, `S2 ${keep} m`));
  svg.append(sv('text', {class: 'axis', x: X(0) + pad * sc * 0.72 + 2, y: Y(0) + pad * sc * 0.72 + 12}, `R5 ${pad} m`));
  svg.append(sv('text', {class: 'axis', x: W - R, y: H - 3, 'text-anchor': 'end'}, 'east x (m)'));
  svg.append(sv('text', {class: 'axis', x: 2, y: T + 8}, 'north y (m)'));
  for (const x of runs) {
    svg.append(sv('path', {class: `line l${x.n}${x.style ? ' ' + x.style : ''}`, d: x.r.states.map((s, i) => `${i ? 'L' : 'M'}${X(s.truth.base_position_m[0]).toFixed(1)},${Y(s.truth.base_position_m[1]).toFixed(1)}`).join('')}));
    const last = x.r.states[x.r.states.length - 1].truth.base_position_m;
    svg.append(sv('circle', {class: 'end', cx: X(last[0]), cy: Y(last[1]), r: 5}, sv('title', {}, `${x.name}: end of run`)));
    const c = x.r.states[nearest(x.r, state.t)].truth.base_position_m;
    svg.append(sv('circle', {class: `dot${x.n}`, cx: X(c[0]), cy: Y(c[1]), r: 4}));
  }
  return el('div', {class: 'panel'}, el('p', {class: 'chart-title'}, 'Ground track of the nozzle exit plane (m, equal scale)'),
    legend(runs.map(x => ({name: x.name, n: x.n, style: x.style}))), svg,
    el('p', {class: 'meta'}, `Green disc: ${pad} m pad radius (R5). Red dashed circle: ${keep} m keep-out radius (S2). The ring marks where the run ends; the filled dot is the time slider position.`));
}
function charts(runs) {
  // runs: [{r, name, n, style}]; one run gives the full set, two give overlays.
  const one = runs.length === 1, a = runs[0].r;
  const each = (name, label, extra = {}) => runs.map(x => ({name: one ? label : x.name, xs: ts(x.r), ys: col(x.r, name), n: one ? (extra.n || 1) : x.n, style: one ? extra.style : x.style}));
  const spans = faultSpans(a), marks = one ? eventMarks(a) : [];
  const out = [];
  if (one) {
    out.push(timeChart({title: 'Altitude of the nozzle exit plane', unit: 'm', spans, marks,
      series: [{name: 'truth', xs: ts(a), ys: col(a, 'truth'), n: 1}, {name: 'altimeter reading', xs: ts(a), ys: col(a, 'altimeter'), n: 2, style: 'dash'},
        {name: 'controller estimate, moved to the nozzle plane', xs: ts(a), ys: col(a, 'estimate'), n: 3, style: 'dots'}],
      note: 'Dotted vertical lines: ignition, cutoff, flameout, touchdown. Shaded: an active fault. The estimate is of the centre of mass; it is moved to the nozzle plane with the true offset, so the gap to the truth is the estimator error alone.'}));
    out.push(timeChart({title: 'What the controller got wrong: reading minus truth', unit: 'm', spans, marks,
      series: [{name: 'controller estimate error', xs: ts(a), ys: col(a, 'estErr'), n: 1}, {name: 'altimeter error', xs: ts(a), ys: col(a, 'altErr'), n: 2, style: 'dash'}],
      note: 'An altimeter bias shows as a constant offset of the altimeter line from the start of the fault. Gaps are sensor dropouts, not zeros.'}));
    out.push(timeChart({title: 'Vertical speed of the nozzle exit plane', unit: 'm/s', spans, marks,
      series: [{name: 'truth', xs: ts(a), ys: col(a, 'vz'), n: 1}, {name: 'controller estimate (centre of mass)', xs: ts(a), ys: col(a, 'vzEst'), n: 3, style: 'dots'}],
      refs: [{y: -state.caps.requirements.r1_vertical_speed_mps, label: 'R1 limit at contact'}]}));
    out.push(timeChart({title: 'Throttle', unit: 'fraction', spans, marks,
      series: [{name: 'commanded', xs: ts(a), ys: col(a, 'cmd'), n: 1}, {name: 'applied by the actuator', xs: ts(a), ys: col(a, 'applied'), n: 2, style: 'dash'}]}));
    out.push(timeChart({title: 'Thrust-vector deflection, applied', unit: 'tangent', spans, marks,
      series: [{name: 'body y', xs: ts(a), ys: col(a, 'gy'), n: 1}, {name: 'body z', xs: ts(a), ys: col(a, 'gz'), n: 2, style: 'dash'}]}));
  } else {
    out.push(timeChart({title: 'Altitude error of the controller estimate (estimate minus truth)', unit: 'm', spans,
      series: each('estErr'), note: 'Both policies saw the same fault. The line that leaves zero is the policy that believed a wrong altitude.'}));
    out.push(timeChart({title: 'Altitude of the nozzle exit plane (truth)', unit: 'm', spans, series: each('truth')}));
    out.push(timeChart({title: 'Vertical speed of the nozzle exit plane (truth)', unit: 'm/s', spans, series: each('vz'),
      refs: [{y: -state.caps.requirements.r1_vertical_speed_mps, label: 'R1 limit at contact'}]}));
    out.push(timeChart({title: 'Throttle applied', unit: 'fraction', spans, series: each('applied')}));
  }
  out.push(trackChart(runs.map(x => ({r: x.r, name: one ? 'truth' : x.name, n: x.n, style: x.style}))));
  return out;
}
function readout(r) {
  const s = r.states[nearest(r, state.t)], eng = s.applied.engine;
  return el('dl', {class: 'kv'},
    el('dt', {}, 'sample time'), el('dd', {}, `${f(s.t_s, 2)} s${s.kind === 'touchdown' ? ' (touchdown, interpolated)' : ''}`),
    el('dt', {}, 'altitude, truth'), el('dd', {}, `${f(cols.truth(s), 2)} m`),
    el('dt', {}, 'altimeter reading'), el('dd', {}, Number.isFinite(cols.altimeter(s)) ? `${f(cols.altimeter(s), 2)} m` : 'no reading (dropout)'),
    el('dt', {}, 'controller estimate'), el('dd', {}, `${f(cols.estimate(s), 2)} m (error ${f(cols.estErr(s), 2)} m)`),
    el('dt', {}, 'vertical speed, truth'), el('dd', {}, `${f(cols.vz(s), 2)} m/s`),
    el('dt', {}, 'engine'), el('dd', {}, `${eng}, throttle ${f(cols.applied(s), 2)} (commanded ${f(cols.cmd(s), 2)})`),
    el('dt', {}, 'active faults'), el('dd', {}, s.active_faults.length ? s.active_faults.map(words).join(', ') : 'none'));
}

// ---------------------------------------------------------------- result
function describeRun(r) {
  return `${r.request.policy} policy · ${describeFault(r.request.fault)} · seed ${r.request.seed} · run ${r.run_id}`;
}
function setTime(t) { state.t = Math.max(0, Math.min(endAll(), t)); renderLive(); }
function timeControls() {
  const end = endAll();
  const slider = el('input', {type: 'range', id: 'time-slider', min: 0, max: end.toFixed(2), step: 0.1, value: state.t, 'aria-label': 'Time cursor', 'aria-describedby': 'time-label',
    oninput: e => setTime(+e.target.value)});
  const zoom = (id, label) => el('button', {'data-zoom': id, 'aria-pressed': state.zoom === id ? 'true' : 'false', onclick: () => { state.zoom = id; renderLive(); }}, label);
  return el('div', {class: 'controls'}, el('span', {class: 'meta'}, 'Time axis'), zoom('full', 'Whole flight'), zoom('final', `Final ${ZOOM_S} s`),
    slider, el('b', {id: 'time-label', role: 'status', 'aria-live': 'off'}, ''));
}
// Everything that depends on the time cursor or the zoom.
function renderLive() {
  const box = $('live'); if (!box) return;
  const runs = liveRuns();
  if (!runs.length) { fill(box, el('p', {class: 'meta'}, 'No verified run to plot.')); return; }
  const label = $('time-label'); if (label) label.textContent = `t = ${f(state.t, 2)} s`;
  const slider = $('time-slider'); if (slider && +slider.value !== state.t) slider.value = state.t;
  for (const b of document.querySelectorAll('[data-zoom]')) b.setAttribute('aria-pressed', b.dataset.zoom === state.zoom ? 'true' : 'false');
  fill(box, el('div', {class: 'charts'}, charts(runs)),
    el('div', {class: runs.length > 1 ? 'grid2' : ''}, runs.map(x => el('div', {class: 'panel'}, el('h4', {}, runs.length > 1 ? `${x.name}: values at the cursor` : 'Values at the cursor'), readout(x.r)))));
}
function liveRuns() {
  if (state.mode === 'compare') return POLICY_NAMES.filter(p => verified(state.pair[p])).map((p, i) => ({r: state.pair[p], name: p, n: p === 'baseline' ? 1 : 2, style: p === 'robust' ? 'dash' : ''}));
  return [{r: state.single, name: state.single.request.policy, n: 1, style: ''}];
}
function eventList(r) { return el('ol', {}, r.events.map(e => el('li', {}, eventText(e)))); }
function noteBox() { return state.note ? el('p', {class: 'note'}, state.note) : null; }

function drawResult() {
  if (state.mode === 'single') return drawSingle();
  if (state.mode === 'compare') return drawCompare();
  fill($('result'), );
}
function liveSection() {
  return [el('h3', {}, 'Charts'), el('div', {class: 'tc'}, timeControls()), el('div', {id: 'live'})];
}
function drawSingle() {
  const r = state.single, ok = verified(r);
  if (!r.states.length) { fill($('result'), el('p', {class: 'bad'}, 'The run produced no recorded samples.')); return; }
  const details = [
    el('h3', {}, 'Requirements at contact (R1 to R6)'), reqTable(r),
    el('h3', {}, 'Safety invariants (S1 to S4)'), invTable(r),
    el('h3', {}, 'Touchdown state (true state, interpolated to the contact instant)'), touchdownCard(r),
    ...liveSection(),
    el('h3', {}, 'Events'), eventList(r)];
  fill($('result'), 
    el('h2', {id: 'result-heading', tabindex: '-1'}, ok ? 'Result' : 'Result: REJECTED evidence'),
    el('p', {class: 'meta'}, describeRun(r)), noteBox(), ...statements(r), actedNote(r),
    ...(ok ? details : [el('section', {class: 'unverified', 'aria-label': 'Unverified stored data'},
      el('b', {class: 'bad'}, 'UNVERIFIED stored data, shown for diagnosis only'), details)]));
  renderLive();
}
function compareRows() {
  const [b, r] = POLICY_NAMES.map(p => state.pair[p]), labels = state.caps.labels, rows = [];
  const cell = (run, x, kind) => {
    if (!verified(run)) return ['withheld', ''];
    if (kind === 'outcome') return [words(run.verification.outcome), run.verification.outcome === 'landed' ? 'ok' : 'bad'];
    if (!x) return ['n/a', ''];
    if (kind === 'req' && !x.evaluated) return ['not evaluated', 'warn'];
    const v = kind === 'req' ? `${val(x.value, x.unit)} ${x.unit}` : `${x.worst_value === null || x.worst_value === undefined ? 'n/a' : val(x.worst_value, x.unit)} ${x.unit}`;
    return [`${v}: ${x.pass ? 'pass' : 'FAIL'}`, x.pass ? 'ok' : 'bad'];
  };
  rows.push({name: 'Mission outcome', limit: 'R1 to R6 all met', a: cell(b, null, 'outcome'), b: cell(r, null, 'outcome'), differs: verified(b) && verified(r) && b.verification.outcome !== r.verification.outcome});
  for (const [kind, key] of [['req', 'requirements'], ['inv', 'invariants']]) {
    for (const x of (b.verification[key] || [])) {
      const y = (r.verification[key] || []).find(z => z.id === x.id);
      rows.push({name: `${short(x.id)} ${labels[x.id] || words(x.id)}`, limit: kind === 'inv' ? `${x.limit} ${x.unit}` : limitText(x),
        a: cell(b, x, kind), b: cell(r, y, kind), differs: verified(b) && verified(r) && !!y && (x.pass !== y.pass)});
    }
  }
  return rows;
}
function drawCompare() {
  const b = state.pair.baseline, r = state.pair.robust, both = verified(b) && verified(r);
  const req = b.request;
  const rows = compareRows();
  const flips = rows.filter(x => x.differs);
  const summary = !both ? el('p', {class: 'alert'}, `At least one run is not verified evidence (${POLICY_NAMES.filter(p => !verified(state.pair[p])).join(', ')}). Its verdicts are withheld and it is left out of the charts.`)
    : flips.length ? el('p', {class: 'statement warn'}, el('b', {}, 'The policies differ on: '), flips.map(x => x.name).join('; ') + '.')
    : el('p', {class: 'statement ok'}, el('b', {}, 'No requirement or invariant verdict differs '), 'between the two policies on this case.');
  const table = el('div', {class: 'scroll'}, el('table', {class: 'diff'}, el('thead', {}, el('tr', {}, [el('th', {}, 'Verdict'), el('th', {}, 'Limit'), el('th', {class: 'num'}, 'baseline'), el('th', {class: 'num'}, 'robust'), el('th', {}, 'Differs')])),
    el('tbody', {}, rows.map(x => el('tr', {class: x.differs ? 'differs' : ''}, el('td', {}, x.name), el('td', {}, el('code', {}, x.limit)),
      el('td', {class: 'num ' + x.a[1]}, x.a[0]), el('td', {class: 'num ' + x.b[1]}, x.b[0]), el('td', {}, x.differs ? 'yes' : 'no'))))));
  const detail = p => el('button', {onclick: () => { state.mode = 'single'; state.single = state.pair[p]; state.note = null; state.t = endAll(); drawResult(); drawResearch(); $('result-heading').focus(); }}, `Open ${p} in detail`);
  fill($('result'), 
    el('h2', {id: 'result-heading', tabindex: '-1'}, 'Comparison of the two policies'),
    el('p', {class: 'meta'}, `Same case for both: ${describeFault(req.fault)} · seed ${req.seed}. baseline run ${b.run_id}, robust run ${r.run_id}.`), noteBox(),
    summary, actedNote(b),
    el('div', {class: 'grid2'}, POLICY_NAMES.map(p => el('div', {class: 'panel'}, el('h3', {}, p), ...statements(state.pair[p]), detail(p)))),
    el('h3', {}, 'Requirement and invariant verdicts side by side'), table,
    el('p', {class: 'meta'}, 'Requirements are evaluated on the true state at touchdown. Differences are computed from the verdicts of the two runs, each replayed by the Rust build.'),
    ...liveSection(),
    el('h3', {}, 'Events'), el('div', {class: 'grid2'}, POLICY_NAMES.map(p => el('div', {}, el('h4', {}, p), verified(state.pair[p]) ? eventList(state.pair[p]) : el('p', {class: 'meta'}, WITHHELD + '.')))));
  renderLive();
}

// ---------------------------------------------------------------- research
function drawResearch() {
  const runs = state.mode === 'compare' ? POLICY_NAMES.map(p => state.pair[p]) : state.single ? [state.single] : [];
  const m = state.models.models[MODEL];
  const kv = obj => el('dl', {class: 'kv'}, Object.entries(obj).flatMap(([k, v]) => [el('dt', {}, k), el('dd', {}, el('code', {}, String(v)))]));
  const model = [el('h3', {}, 'Model'), kv({id: m.model.id, physics: m.model.physics, ...m.model.frames, units: Object.entries(m.model.units).map(([k, v]) => `${k} ${v}`).join(', ')})];
  if (!runs.length) { fill($('panel-research'), el('p', {}, 'Run a scenario first; this panel then shows the exact request, provenance hashes, replay checks and integrity results.'), ...model); return; }
  fill($('panel-research'), ...runs.flatMap(r => [
    el('h2', {}, `Run ${r.run_id} (${r.request.policy})`),
    el('h3', {}, 'Request (as validated by the adapter)'), el('pre', {}, JSON.stringify(r.request, null, 2)),
    el('h3', {}, 'Provenance'), el('p', {class: 'meta'}, 'run_id: first 16 hex characters of sha256 of the validated request, the case it produces and the vv-rocket binary hash.'),
    kv({adapter: r.adapter, source_sha256: r.provenance.source_sha256, binary_sha256: r.provenance.binary_sha256, manifest_sha256: r.provenance.manifest_sha256}),
    el('h3', {}, 'Input and artifact sha256'), kv(Object.assign({}, ...Object.entries(r.inputs).map(([k, v]) => ({['inputs/' + k]: v})), r.provenance.artifacts)),
    el('h3', {}, 'Replay checks (vv-rocket replay)'),
    el('ul', {}, (r.replay.checks || [{name: r.replay.status + ' ' + (r.replay.detail || ''), pass: false}]).map(c => el('li', {class: c.pass ? 'ok' : 'bad'}, `${c.pass ? 'pass' : 'FAIL'}: ${c.name}`))),
    el('h3', {}, 'Integrity'), el('p', {class: r.integrity.problems.length ? 'bad' : 'ok'}, r.integrity.problems.length ? r.integrity.problems.join('; ') : r.reused ? 'All files match a fresh regeneration of this request.' : 'No integrity problem found.'),
    el('h3', {}, 'Summary (trace.json)'), kv(r.summary)]), ...model);
}

// ---------------------------------------------------------------- campaign
async function loadCampaign() {
  fill($('panel-campaign'), el('p', {class: 'meta'}, 'Reading the campaign summary from disk…'));
  try {
    const resp = await fetch('/api/campaign');
    state.campaign = await resp.json();
    if (!resp.ok) throw new Error('bad status');
  } catch (e) { state.campaign = {found: false, message: 'the local server did not answer the campaign request', reason: 'request failed'}; }
  drawCampaign();
}
function campaignRequest(run, policy) {
  const nominal = run.fault === 'nominal' || run.fault === null;
  if (nominal) return {schema: SCHEMA, model: MODEL, policy, seed: run.seed, fault: null};
  const w = run.window;
  if (!Array.isArray(w) || w.length !== 2) throw new Error('this campaign run has no usable fault window');
  return {schema: SCHEMA, model: MODEL, policy, seed: run.seed, fault: {kind: run.fault, magnitude: run.magnitude === null || run.magnitude === undefined ? 0 : run.magnitude, start_s: w[0], end_s: w[1]}};
}
async function rerun(run, compare) {
  let bodies;
  try { bodies = (compare ? POLICY_NAMES : [run.policy]).map(p => campaignRequest(run, p)); } catch (e) { setError(e.message); return; }
  const c = state.campaign && state.campaign.summary;
  const stored = `The campaign file says this run (${run.policy}, seed ${run.seed}) ended ${words(run.outcome)}${run.failed && run.failed.length ? ' with ' + run.failed.join(', ') + ' failed' : ''}. Everything below was recomputed now by this build; the file was not used for it.`;
  const done = await runBodies(bodies, stored);
  if (done && c && c.source_sha256) {
    const r = state.mode === 'single' ? state.single : state.pair.baseline;
    if (r.provenance.source_sha256 && r.provenance.source_sha256 !== c.source_sha256) state.note += ' This build has a different source hash from the one that produced the campaign, so the two may legitimately differ.';
    drawResult();
  }
}
function drawCampaign() {
  const c = state.campaign, box = $('panel-campaign');
  if (!c || !c.found) { fill(box, el('h2', {}, 'Campaign evidence'), el('p', {class: 'note'}, c ? c.message : 'No campaign information.'),
    c && c.reason ? el('p', {class: 'meta'}, `Reason: ${c.reason}.`) : null, el('button', {onclick: () => { state.campaign = null; loadCampaign(); }}, 'Look again')); return; }
  const s = c.summary, cells = new Map(s.cells.map(x => [`${x.fault}|${x.policy}`, x]));
  const faults = ['nominal'].concat(state.caps.faults.map(x => x.kind));
  const pairOf = new Map(s.pairs.map(x => [x.fault, x]));
  const flt = state.campaignFilter;
  const cellButton = (fault, policy) => {
    const x = cells.get(`${fault}|${policy}`); if (!x) return el('td', {}, 'no runs');
    const on = flt && flt.fault === fault && flt.policy === policy;
    return el('td', {}, el('button', {'aria-pressed': on ? 'true' : 'false', 'aria-label': `${fault} with ${policy}: ${x.landed} of ${x.runs} landed with all invariants. Show these runs.`,
      onclick: () => { state.campaignFilter = on ? null : {fault, policy}; drawCampaign(); }},
      `${x.landed} of ${x.runs} landed`, el('span', {class: 'sub'}, `hard landing ${x.hard_landing}, no contact ${x.no_contact}, invariant failures ${x.invariant_failure_runs}`)));
  };
  const matrix = el('div', {class: 'scroll matrix'}, el('table', {}, el('thead', {}, el('tr', {}, ['Scenario', 'baseline', 'robust', 'Paired (same seed)'].map(h => el('th', {}, h)))),
    el('tbody', {}, faults.map(k => { const p = pairOf.get(k); return el('tr', {}, el('td', {}, words(k)), cellButton(k, 'baseline'), cellButton(k, 'robust'),
      el('td', {}, p ? `both ${p.both_land}, only baseline ${p.only_baseline}, only robust ${p.only_robust}, neither ${p.neither}` : 'n/a')); }))));
  const verdictClass = v => v === 'supported' || v === 'observed' ? 'ok' : v === 'not_evaluated' ? 'warn' : 'bad';
  const hyps = s.hypotheses.map(h => el('div', {class: 'panel'}, el('h4', {}, `${h.id}: `, el('span', {class: verdictClass(h.verdict)}, words(h.verdict))), el('p', {}, h.statement), el('p', {class: 'meta'}, 'Criterion: ' + h.criterion), el('p', {class: 'meta'}, 'Observed: ' + h.evidence)));
  const runs = s.runs.filter(x => !flt || (x.fault === flt.fault && x.policy === flt.policy));
  const SHOW = 40;
  const list = el('div', {class: 'scroll'}, el('table', {}, el('thead', {}, el('tr', {}, ['Seed', 'Group', 'Scenario', 'Policy', 'Magnitude', 'Window (s)', 'Stored outcome', 'Failed', 'Recompute'].map(h => el('th', {}, h)))),
    el('tbody', {}, runs.slice(0, SHOW).map(x => el('tr', {}, el('td', {}, x.seed), el('td', {}, x.group), el('td', {}, words(x.fault)), el('td', {}, x.policy),
      el('td', {class: 'num'}, x.magnitude === null || x.magnitude === undefined ? 'none' : g3(x.magnitude)), el('td', {}, Array.isArray(x.window) ? `${f(x.window[0], 2)} to ${f(x.window[1], 2)}` : 'none'),
      el('td', {class: x.outcome === 'landed' && !(x.failed || []).length ? 'ok' : 'bad'}, words(x.outcome)), el('td', {}, (x.failed || []).join(', ') || 'none'),
      el('td', {}, el('div', {class: 'controls'},
        el('button', {onclick: () => rerun(x, false), 'aria-label': `Re-run ${x.policy} seed ${x.seed} ${x.fault} under the adapter`}, 'Re-run'),
        el('button', {onclick: () => rerun(x, true), 'aria-label': `Compare both policies on seed ${x.seed} ${x.fault}`}, 'Compare'))))))));
  const boundary = s.boundary_findings.length ? [el('h3', {}, 'Recovery boundary sweep'), el('ul', {}, s.boundary_findings.map(x => el('li', {}, `${words(x.fault)}, ${x.policy}: ${x.finding}`)))] : [];
  fill(box, 
    el('h2', {}, 'Campaign evidence'),
    el('p', {class: 'note'}, el('b', {}, 'Read from disk, not recomputed here. '), 'The counts, hypothesis verdicts and run list below come from the campaign summary file written by scripts/m9_campaign.py and are shown as stored. A click on a run sends it back through the adapter: that run is executed again now, replayed, and shown with fresh verdicts.',
      el('br'), el('code', {}, `summary.json sha256 ${c.sha256}`)),
    s.preregistered ? null : el('p', {class: 'alert'}, 'This campaign is a subset of the pre-registered matrix. Its hypothesis verdicts have no test value.'),
    kv2({runs: s.total_runs, seeds: Array.isArray(s.seeds) && s.seeds.length ? `${s.seeds[0]} to ${s.seeds[s.seeds.length - 1]}` : 'none', machine: s.machine, command: s.command,
      'wall-clock duration (s)': s.duration_s, binary_sha256: s.binary_sha256, source_sha256: s.source_sha256, 'determinism check': s.determinism_check === null || s.determinism_check === undefined ? 'not recorded' : JSON.stringify(s.determinism_check)}),
    el('h3', {}, 'Success matrix: scenario by policy'), el('p', {class: 'meta'}, 'Landed means outcome landed with all four invariants holding. Select a cell to list its runs.'), matrix,
    el('h3', {}, 'Pre-registered hypotheses'), el('p', {class: 'meta'}, 'Statements, criteria and evidence are stored text from the summary file (Portuguese). No p-values: 30 seeds with assumed dispersions do not support a statistical inference about a real vehicle.'), ...hyps,
    ...boundary,
    el('h3', {}, flt ? `Runs: ${words(flt.fault)}, ${flt.policy}` : 'Runs (all cells)'),
    el('p', {class: 'meta'}, `${runs.length} runs${runs.length > SHOW ? `, showing the first ${SHOW}; select a matrix cell to narrow the list` : ''}. Stored outcomes are from the file.`), list,
    el('h3', {}, 'Limitations stated by the campaign'), el('ul', {}, s.limitations.map(x => el('li', {}, x))));
}
function kv2(obj) { return el('dl', {class: 'kv'}, Object.entries(obj).flatMap(([k, v]) => [el('dt', {}, k), el('dd', {}, el('code', {}, v === null || v === undefined ? 'n/a' : String(v)))])); }

// ---------------------------------------------------------------- claims
function drawClaims() {
  const list = items => el('ul', {}, items.map(x => el('li', {}, x)));
  fill($('panel-claims'), 
    el('h2', {}, 'What this page claims, and what it does not'),
    el('p', {class: 'meta'}, 'Source: docs/m9-powered-landing.md. The requirements, dispersions and fault ranges were fixed before the campaign and are not adjusted so that a scenario passes.'),
    el('div', {class: 'cols3'},
      el('div', {class: 'panel'}, el('h3', {class: 'ok'}, 'Verified'), list([
        'Determinism: a run is a function of the case and the seed. Replay recomputes the trace, the verdicts and the manifest and compares them byte for byte; a run that fails replay is shown as unverified and its verdicts are withheld.',
        'The requirements R1 to R6 and the invariants S1 to S4 are evaluated by a verifier on the true simulated state, separately from what the controller believed, and recomputed on every replay.',
        'The controller code receives only sensor readings and the mission configuration; a test checks that it does not reference the true state.',
        'The stored run is bound to its request, its seed, its case and the build that produced it; edited or relocated files are rejected.',
        'The plotted altitude error is estimate minus truth: the page never uses the truth to hide an estimator error.'])),
      el('div', {class: 'panel'}, el('h3', {class: 'warn'}, 'Assumed'), list([
        'The requirement limits (3 m/s vertical, 1 m/s horizontal, 5° tilt, 0.1 rad/s, 10 m pad radius, 1% propellant) and the invariant limits (30° tilt, 50 m keep-out, 3 g0 axial load).',
        'The dispersions of the initial state, propellant, thrust and Isp, and the sensor noise levels.',
        'The fault models and their ranges; one fault of each kind at most.',
        'The vehicle, the actuator rate limits and the 50 Hz control cycle. The controller gains were tuned on the nominal case with seeds 0 to 40.'])),
      el('div', {class: 'panel'}, el('h3', {class: 'bad'}, 'Not claimed'), list([
        'That the model represents a real vehicle, or that the code is flight software.',
        'Contact dynamics: touchdown is the instant the nozzle exit plane reaches the ground. There are no legs, no tipping, no bounce and no landing-site model.',
        'A reliability or success probability: a count over 30 seeds with assumed dispersions is not an estimate for a real vehicle.',
        'That either controller is optimal or adequate for flight, or that it handles combined faults or faults outside the pre-registered ranges.',
        'Wind, aerodynamic moments, reaction-control thrusters or Earth rotation.'])))
  );
}

async function boot() {
  wireTabs();
  try {
    state.models = await (await fetch('/api/models')).json();
    if (!state.models.models || !state.models.models[MODEL]) throw new Error('model missing');
    state.caps = state.models.models[MODEL].capabilities;
  } catch (e) { setError('could not load the landing model description from the local server.'); return; }
  $('physics').append(' ', el('span', {class: 'meta'}, `Model ${MODEL}; adapter contract ${state.models.models[MODEL].schema}.`));
  drawRun(); drawClaims(); drawResearch();
}
boot();
"""
