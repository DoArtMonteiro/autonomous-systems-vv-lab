// Experiment Lab (M17): start from a run, change what the domain catalog declares, run a new
// simulation and see what changed and why, then check whether the change holds on other seeds or
// along one parameter. Every number shown comes from a run record computed by the platform; the
// Lab only reads requests and records and never edits either. The parameter hints are the domain's
// hand-written `influences`, labelled as such, not a computed attribution.

import { h, clear, prose } from '../dom.js';
import { api } from '../api.js';
import { domainById, visibleDomains, emit, loadRecord } from '../store.js';
import { toast, errorText } from '../ui.js';
import { verdictOfOutcome, verdictOfSafety, faultText } from '../model.js';
import { verdictGlyph } from '../verification.js';

const REQUEST_SCHEMA = 'vv-run-request.v1';
const BATCH = 8; // the platform's MAX_COMPARE
const DEV_SEED = 5000;

let root;
let navigate = () => {};
let lab = null; // {domain, base:{id, record}, form, exp:{id, record}, gen, sweep, busy, focus:Set}

export function initLab(el, nav) {
  root = el;
  navigate = nav;
}

/** opts: {runId} to start from a stored run, or nothing to keep the current experiment. */
export async function showLab(opts) {
  if (opts && opts.runId && (!lab || lab.base.id !== opts.runId)) {
    try {
      const record = await loadRecord(opts.runId);
      startFrom(opts.runId, record);
    } catch (e) {
      toast(errorText(e), 'error');
    }
  }
  render();
}

/** For tests and the palette: the Lab's state without its records. */
export function labState() {
  if (!lab) return null;
  return { base: lab.base.id, exp: lab.exp ? lab.exp.id : null, busy: lab.busy, changes: changes(), gen: lab.gen && lab.gen.base ? { n: lab.gen.seeds.length, base: lab.gen.base.filter(passes).length, exp: lab.gen.exp.filter(passes).length } : null, sweep: lab.sweep && lab.sweep.records ? lab.sweep.values.length : null };
}

function startFrom(id, record) {
  const req = record.request;
  lab = {
    domain: req.domain,
    base: { id, record },
    form: { scenario: req.scenario, controller: req.controller, seed: req.seed, faults: req.faults.map((f) => ({ ...f })), params: { ...req.parameters } },
    exp: null,
    gen: null,
    sweep: null,
    busy: null,
    // The first failed requirement is in focus; the others can be added from the baseline card.
    focus: new Set(failedOf(record).slice(0, 1).map((r) => r.id)),
  };
}

// ----------------------------------------------------------------------------- record reading

function failedOf(record) {
  return (record.requirements || []).filter((r) => r.status === 'fail');
}

/** The number and comparison of a requirement's expected text ("<= 3 m/s", ">= 0.9962 cos"). */
function limitOf(r) {
  const m = /^\s*(<=|>=|<|>)\s*(-?[\d.]+(?:e[-+]?\d+)?)/i.exec(r.expected || '');
  return m ? { op: m[1], value: Number(m[2]) } : null;
}

function observedOf(r) {
  const m = /(-?[\d.]+(?:e[-+]?\d+)?)/i.exec(r.observed || '');
  return m ? Number(m[1]) : null;
}

/**
 * Margin to the limit in the requirement's unit, positive when met: parsed from the record's
 * expected and observed text, so it is only as precise as that text.
 */
function marginOf(r) {
  const lim = limitOf(r);
  const obs = observedOf(r);
  if (!lim || obs === null || !Number.isFinite(obs)) return null;
  return lim.op.startsWith('<') ? lim.value - obs : obs - lim.value;
}

function unitOf(r) {
  const m = /-?[\d.]+(?:e[-+]?\d+)?\s*(.*)$/i.exec(r.expected || '');
  return m ? m[1].trim() : '';
}

// Element.append writes null as the text "null"; optional parts go through this instead.
const add = (el, ...kids) => el.append(...kids.filter((k) => k !== null && k !== undefined && k !== false));

const fmt = (v, d = 3) => (v === null || v === undefined || !Number.isFinite(v) ? '–' : Number(v.toPrecision(d)).toString());

// ----------------------------------------------------------------------------- requests

function domain() {
  return domainById(lab.domain);
}

function catalog() {
  const d = lab && domain();
  return d ? d.catalog : null;
}

function scenarioSpec() {
  const cat = catalog();
  return cat ? cat.scenarios.find((s) => s.id === lab.form.scenario) : null;
}

function buildRequest(over = {}) {
  const f = { ...lab.form, ...over };
  const sc = catalog().scenarios.find((s) => s.id === f.scenario);
  const params = {};
  for (const [k, v] of Object.entries(f.params)) if (sc && sc.parameters.includes(k) && Number.isFinite(v)) params[k] = v;
  return { schema: REQUEST_SCHEMA, domain: lab.domain, scenario: f.scenario, controller: f.controller, seed: Number(f.seed), faults: f.faults.map((x) => ({ ...x })), parameters: params };
}

function paramValue(req, spec) {
  const v = req.parameters ? req.parameters[spec.id] : undefined;
  return v === undefined ? spec.default : v;
}

/** What differs between two requests, in words a reader can check against both records. */
function requestDiff(a, b) {
  const cat = catalog();
  const out = [];
  const label = (items, id) => (items.find((x) => x.id === id) || { label: id }).label;
  if (a.scenario !== b.scenario) out.push({ text: `Scenario: ${label(cat.scenarios, a.scenario)} → ${label(cat.scenarios, b.scenario)}`, judging: false });
  if (a.controller !== b.controller) out.push({ text: `Controller: ${label(cat.controllers, a.controller)} → ${label(cat.controllers, b.controller)}`, judging: false });
  if (a.seed !== b.seed) out.push({ text: `Seed: ${a.seed} → ${b.seed}`, judging: false });
  for (const p of cat.parameters) {
    const va = paramValue(a, p);
    const vb = paramValue(b, p);
    if (va !== vb) out.push({ text: `${p.label}: ${fmt(va, 6)} → ${fmt(vb, 6)}${p.unit ? ` ${p.unit}` : ''}`, judging: p.group === 'Requirements' });
  }
  const fa = a.faults.map((f) => faultText(f, cat)).join(' + ') || 'none';
  const fb = b.faults.map((f) => faultText(f, cat)).join(' + ') || 'none';
  if (fa !== fb) out.push({ text: `Faults: ${fa} → ${fb}`, judging: false });
  return out;
}

function changes() {
  return lab && catalog() ? requestDiff(lab.base.record.request, buildRequest()).map((d) => d.text) : [];
}

/** Development seeds for a check: from 5000 upward, skipping every protected range. */
function devSeeds(n) {
  const p = domain().manifest.seeds;
  const out = [];
  for (let s = DEV_SEED; out.length < n && s <= p.max; s += 1) {
    if (p.protected.some((r) => s >= r.start && s <= r.end)) continue;
    out.push(s);
  }
  return out;
}

async function runMany(requests, progress) {
  const out = [];
  for (let i = 0; i < requests.length; i += BATCH) {
    const chunk = requests.slice(i, i + BATCH);
    const items = await api.compare(chunk);
    for (const it of items) out.push(it.status === 'ok' ? { id: it.outcome.run_id, reused: it.outcome.reused } : { error: errorText(it.error) });
    if (progress) progress(out.length, requests.length);
  }
  emit('runs-changed');
  return out;
}

async function tag(id, reused, note) {
  if (reused) return; // a stored run keeps the label and notes its owner gave it
  try {
    await api.updateNotes(id, `Experiment from ${lab.base.id.slice(0, 10)}`, note, ['experiment', `from:${lab.base.id}`]);
  } catch {
    // The run exists either way; a failed label is not a failed experiment.
  }
}

// ----------------------------------------------------------------------------- actions

async function runExperiment() {
  if (lab.busy) return;
  const req = buildRequest();
  lab.busy = 'run';
  render();
  try {
    await api.validate(req);
    const out = await api.run(req);
    await tag(out.run_id, out.reused, `Derived from run ${lab.base.id}. Changes: ${changes().join('; ') || 'none'}.`);
    emit('runs-changed');
    lab.exp = { id: out.run_id, record: await loadRecord(out.run_id), reused: out.reused };
    lab.gen = null;
  } catch (e) {
    toast(errorText(e), 'error');
  } finally {
    lab.busy = null;
    render();
  }
}

async function checkSeeds(n) {
  if (lab.busy) return;
  const seeds = devSeeds(n);
  const a = seeds.map((s) => ({ ...lab.base.record.request, seed: s }));
  const b = seeds.map((s) => buildRequest({ seed: s }));
  lab.busy = 'gen';
  lab.gen = { seeds, progress: 0, total: a.length + b.length };
  render();
  try {
    const res = await runMany([...a, ...b], (k, total) => { lab.gen.progress = k; lab.gen.total = total; renderResult(); });
    const records = await Promise.all(res.map((r) => (r.id ? loadRecord(r.id) : null)));
    lab.gen = { seeds, base: records.slice(0, seeds.length), exp: records.slice(seeds.length), errors: res.filter((r) => r.error).map((r) => r.error) };
  } catch (e) {
    toast(errorText(e), 'error');
    lab.gen = null;
  } finally {
    lab.busy = null;
    render();
  }
}

async function runSweep(paramId, from, to, k) {
  if (lab.busy) return;
  const spec = catalog().parameters.find((p) => p.id === paramId);
  if (!spec) return;
  const values = [];
  for (let i = 0; i < k; i += 1) {
    const raw = from + ((to - from) * i) / (k - 1);
    const stepped = spec.step > 0 ? Math.round(raw / spec.step) * spec.step : raw;
    const v = Math.min(spec.max, Math.max(spec.min, Number(stepped.toPrecision(10))));
    if (!values.includes(v)) values.push(v);
  }
  const reqs = values.map((v) => buildRequest({ params: { ...lab.form.params, [paramId]: v } }));
  lab.busy = 'sweep';
  lab.sweep = { paramId, values, progress: 0, total: reqs.length };
  render();
  try {
    const res = await runMany(reqs, (n, total) => { lab.sweep.progress = n; lab.sweep.total = total; renderResult(); });
    const records = await Promise.all(res.map((r) => (r.id ? loadRecord(r.id) : null)));
    lab.sweep = { paramId, values, records, ids: res.map((r) => r.id || null), errors: res.filter((r) => r.error).map((r) => r.error) };
  } catch (e) {
    toast(errorText(e), 'error');
    lab.sweep = null;
  } finally {
    lab.busy = null;
    render();
  }
}

// ----------------------------------------------------------------------------- rendering

let parts = null;

function render() {
  if (!root) return;
  clear(root);
  if (!lab || !catalog()) { parts = null; renderEmpty(); return; }
  const sc = scenarioSpec();
  const rec = lab.base.record;
  const cat = catalog();
  const exploratory = (rec.notes || []).some((n) => n.startsWith('Exploratory case')) || changes().length > 0;
  parts = { base: h('section', { class: 'lab-col lab-base', 'aria-label': 'Baseline run' }), edit: h('section', { class: 'lab-col lab-edit', 'aria-label': 'Conditions to change' }), result: h('section', { class: 'lab-col lab-result', 'aria-label': 'Result', 'aria-live': 'polite' }) };
  root.append(h('div', { class: 'lab' },
    h('header', { class: 'lab-head' },
      h('div', null,
        h('p', { class: 'eyebrow' }, `Experiment Lab · ${domain().manifest.name}`),
        h('h1', null, 'What would change this outcome?'),
        h('p', { class: 'lab-lede' }, 'Change a condition the model defines, run a new simulation and compare it with the run you started from. Each run is recomputed and judged on its own; nothing in the baseline record is edited.')),
      h('div', { class: 'lab-head-tags' },
        exploratory ? h('span', { class: 'lab-tag lab-tag-exp', title: 'Values outside the pre-registered configuration. Results are exploratory and are not evidence for any pre-registered claim.' }, 'Exploratory') : null,
        sc ? h('span', { class: 'lab-tag' }, sc.label) : null)),
    h('div', { class: 'lab-grid' }, parts.base, parts.edit, parts.result)));
  renderBase(rec);
  renderEdit(cat, sc);
  renderResult();
}

function renderEmpty() {
  const doms = visibleDomains().filter((d) => d.catalog);
  root.append(h('div', { class: 'lab lab-empty' },
    h('p', { class: 'eyebrow' }, 'Experiment Lab'),
    h('h1', null, 'Start from a run'),
    h('p', { class: 'lab-lede' }, 'Open a mission or a stored run and choose “Experiment from this run”, or start from the default conditions of a domain. The Lab keeps that run as the baseline and compares every new run with it.'),
    h('div', { class: 'row' }, doms.map((d) => h('button', { type: 'button', class: 'btn', onclick: (e) => startDefault(d, e.currentTarget) }, `Default run: ${d.manifest.name}`)),
      h('button', { type: 'button', class: 'btn btn-quiet', onclick: () => navigate('library') }, 'Choose a stored run'))));
}

async function startDefault(d, btn) {
  const cat = d.catalog;
  const sc = cat.scenarios[0];
  const req = { schema: REQUEST_SCHEMA, domain: d.manifest.id, scenario: sc.id, controller: sc.default_controller, seed: DEV_SEED, faults: [], parameters: {} };
  if (btn) { btn.classList.add('is-busy'); btn.disabled = true; }
  try {
    const out = await api.run(req);
    emit('runs-changed');
    startFrom(out.run_id, await loadRecord(out.run_id));
    render();
  } catch (e) {
    toast(errorText(e), 'error');
    if (btn) { btn.classList.remove('is-busy'); btn.disabled = false; }
  }
}

function verdictPill(record) {
  const ov = verdictOfOutcome(record.outcome.status);
  const sv = verdictOfSafety(record.safety.status);
  return h('div', { class: 'lab-verdicts' },
    h('span', { class: ['mini', `v-${ov}`], title: prose(record.outcome.explanation) }, verdictGlyph(ov), record.outcome.label),
    h('span', { class: ['mini', `v-${sv}`], title: prose(record.safety.explanation) }, verdictGlyph(sv), record.safety.status === 'safe' ? 'Safe' : record.safety.status));
}

function runLine(req) {
  const cat = catalog();
  const ctl = (cat.controllers.find((c) => c.id === req.controller) || { label: req.controller }).label;
  const faults = req.faults.map((f) => faultText(f, cat)).join(' + ') || 'no fault';
  const sc = (cat.scenarios.find((s) => s.id === req.scenario) || { label: req.scenario }).label;
  return `${sc} · ${ctl} controller · seed ${req.seed} · ${faults}`;
}

function marginBar(r) {
  const m = marginOf(r);
  const lim = limitOf(r);
  if (m === null || !lim) return null;
  const scale = Math.max(Math.abs(lim.value), 1e-9);
  const frac = Math.max(-1, Math.min(1, m / scale));
  return h('span', { class: ['lab-mbar', m >= 0 ? 'is-ok' : 'is-bad'], 'aria-hidden': 'true' },
    h('span', { class: 'lab-mbar-fill', style: { width: `${Math.abs(frac) * 50}%`, [m >= 0 ? 'left' : 'right']: '50%' } }));
}

function renderBase(rec) {
  const el = parts.base;
  const failed = failedOf(rec);
  add(el, 
    h('p', { class: 'lab-h' }, 'Baseline'),
    h('p', { class: 'lab-run' }, runLine(rec.request)),
    h('p', { class: 'lab-id mono small' }, lab.base.id),
    verdictPill(rec),
    failed.length
      ? h('div', { class: 'lab-fails' },
        h('p', { class: 'lab-h2' }, `${failed.length} requirement${failed.length > 1 ? 's' : ''} not met`),
        h('ul', { class: 'lab-req-list' }, failed.map((r) => {
          const on = lab.focus.has(r.id);
          const m = marginOf(r);
          return h('li', null, h('button', { type: 'button', class: ['lab-req', on ? 'is-focus' : ''], 'aria-pressed': String(on), title: 'Highlight the parameters the domain lists as acting on this requirement', onclick: () => { if (on) lab.focus.delete(r.id); else lab.focus.add(r.id); render(); } },
            h('span', { class: 'lab-req-l' }, r.label),
            h('span', { class: 'lab-req-v mono' }, `${r.observed} · limit ${r.expected}`),
            marginBar(r),
            m === null ? null : h('span', { class: 'lab-req-m small' }, `${fmt(Math.abs(m))} ${unitOf(r)} ${m >= 0 ? 'inside' : 'beyond'} the limit`)));
        })),
        h('p', { class: 'small dim' }, 'Margins are read from the expected and observed values in the record. Select a requirement to highlight the parameters the domain lists for it.'))
      : h('p', { class: 'lab-allmet' }, 'Every requirement met. Try a harder condition to find where this configuration stops meeting them.'),
    h('div', { class: 'row lab-base-actions' },
      h('button', { type: 'button', class: 'btn btn-quiet', onclick: () => navigate('run', { runId: lab.base.id }) }, 'Analyse the baseline')),
    h('details', { class: 'lab-model' }, h('summary', null, 'Model and its limits'), h('p', { class: 'small' }, prose(domain().manifest.model_validity))));
}

function field(spec, cat, base) {
  const val = lab.form.params[spec.id] ?? spec.default;
  const baseVal = paramValue(base, spec);
  const changed = val !== baseVal;
  // A requirement limit is never suggested as a fix: relaxing the judgement is not a better flight.
  const hinted = spec.group !== 'Requirements' && (spec.influences || []).some((id) => lab.focus.has(id));
  const id = `lab-p-${spec.id}`;
  const set = (v) => {
    if (!Number.isFinite(v)) return;
    v = Math.min(spec.max, Math.max(spec.min, v));
    if (v === spec.default) delete lab.form.params[spec.id]; else lab.form.params[spec.id] = v;
    renderEditSoon();
  };
  const reqNames = (spec.influences || []).map((rid) => (cat.requirements.find((r) => r.id === rid) || { label: rid }).label);
  return h('div', { class: ['lab-field', changed ? 'is-changed' : '', hinted ? 'is-hint' : ''], dataset: { param: spec.id } },
    h('div', { class: 'lab-field-top' },
      h('label', { for: id, class: 'lab-field-l' }, spec.label, spec.unit ? h('span', { class: 'dim' }, ` (${spec.unit})`) : null),
      hinted ? h('span', { class: 'lab-hint', title: `The domain lists this parameter as acting on: ${reqNames.join(', ')}. A hint written by the domain, not computed from this run.` }, 'Listed for this failure') : null,
      changed ? h('button', { type: 'button', class: 'link small', onclick: () => { if (baseVal === spec.default) delete lab.form.params[spec.id]; else lab.form.params[spec.id] = baseVal; renderEditSoon(); } }, 'Reset') : null),
    h('div', { class: 'lab-field-ctl' },
      h('input', { type: 'range', min: spec.min, max: spec.max, step: spec.step || 'any', value: val, 'aria-label': spec.label, oninput: (e) => set(Number(e.target.value)) }),
      h('input', { type: 'number', id, class: 'input mono lab-num', min: spec.min, max: spec.max, step: spec.step || 'any', value: val, onchange: (e) => set(Number(e.target.value)) })),
    h('p', { class: 'lab-field-d small' }, `Baseline ${fmt(baseVal, 6)} · range ${fmt(spec.min, 6)} to ${fmt(spec.max, 6)}. `, prose(spec.description)));
}

let editTimer = 0;
function renderEditSoon() {
  clearTimeout(editTimer);
  editTimer = setTimeout(() => {
    if (!parts) return;
    // Keep the scroll position and the focused control across the redraw of the editor.
    const top = parts.edit.scrollTop;
    const focusId = document.activeElement && parts.edit.contains(document.activeElement) ? document.activeElement.id : null;
    clear(parts.edit);
    renderEdit(catalog(), scenarioSpec());
    parts.edit.scrollTop = top;
    if (focusId) { const f = document.getElementById(focusId); if (f) f.focus(); }
    renderResult();
  }, 60);
}

const GROUP_ORDER = ['Controller tuning', 'Initial conditions', 'Sensors', 'Requirements'];

function renderEdit(cat, sc) {
  const el = parts.edit;
  const base = lab.base.record.request;
  const vehicle = sc ? cat.vehicles.find((v) => v.id === sc.vehicle) : null;
  el.append(h('p', { class: 'lab-h' }, 'Change the conditions'));

  el.append(h('div', { class: 'lab-block' },
    h('label', { class: 'lab-field-l', for: 'lab-scenario' }, 'Vehicle and scenario'),
    h('select', { class: 'select', id: 'lab-scenario', onchange: (e) => {
      lab.form.scenario = e.target.value;
      const s = scenarioSpec();
      if (s && !s.controllers.includes(lab.form.controller)) lab.form.controller = s.default_controller;
      renderEditSoon();
    } }, cat.scenarios.map((s) => h('option', { value: s.id, selected: s.id === lab.form.scenario }, s.label))),
    vehicle ? h('p', { class: 'small lab-field-d' }, h('b', null, vehicle.label), '. ', prose(vehicle.description)) : null,
    sc ? h('p', { class: 'small lab-field-d dim' }, prose(sc.description)) : null));

  const ctl = cat.controllers.find((c) => c.id === lab.form.controller);
  el.append(h('div', { class: 'lab-block lab-two' },
    h('div', null,
      h('label', { class: 'lab-field-l', for: 'lab-ctl' }, 'Controller'),
      h('select', { class: 'select', id: 'lab-ctl', onchange: (e) => { lab.form.controller = e.target.value; renderEditSoon(); } },
        (sc ? sc.controllers : []).map((c) => h('option', { value: c, selected: c === lab.form.controller }, (cat.controllers.find((x) => x.id === c) || { label: c }).label))),
      ctl ? h('p', { class: 'small lab-field-d' }, prose(ctl.description)) : null),
    h('div', null,
      h('label', { class: 'lab-field-l', for: 'lab-seed' }, 'Seed'),
      h('input', { class: 'input mono', id: 'lab-seed', type: 'number', min: 0, value: lab.form.seed, onchange: (e) => { lab.form.seed = Math.max(0, Math.floor(Number(e.target.value) || 0)); renderEditSoon(); } }),
      h('p', { class: 'small lab-field-d' }, 'The seed draws the dispersion of the initial state and the sensor noise. Keep it to compare like with like; protected seeds are refused.'))));

  if (cat.faults.length) {
    el.append(h('div', { class: 'lab-block' },
      h('p', { class: 'lab-field-l' }, 'Injected faults'),
      lab.form.faults.length ? h('ul', { class: 'lab-faults' }, lab.form.faults.map((f, i) => {
        const spec = cat.faults.find((x) => x.kind === f.kind);
        return h('li', null,
          h('span', null, faultText(f, cat)),
          spec && spec.magnitude ? h('input', { type: 'number', class: 'input mono lab-num', 'aria-label': `${spec.label} magnitude (${spec.magnitude.unit})`, min: spec.magnitude.min, max: spec.magnitude.max, step: 'any', value: f.magnitude, onchange: (e) => { const v = Number(e.target.value); if (Number.isFinite(v)) { f.magnitude = Math.min(spec.magnitude.max, Math.max(spec.magnitude.min, v)); renderEditSoon(); } } }) : null,
          h('button', { type: 'button', class: 'link small', onclick: () => { lab.form.faults.splice(i, 1); renderEditSoon(); } }, 'Remove'));
      })) : h('p', { class: 'small dim' }, 'No fault injected.'),
      lab.form.faults.length < cat.max_faults ? h('select', { class: 'select select-sm', 'aria-label': 'Add a fault', onchange: (e) => {
        const spec = cat.faults.find((x) => x.kind === e.target.value);
        if (spec) lab.form.faults.push({ kind: spec.kind, magnitude: spec.magnitude ? spec.magnitude.default : null, start: spec.default_start, end: spec.default_end });
        renderEditSoon();
      } }, h('option', { value: '' }, 'Add a fault…'), cat.faults.map((f) => h('option', { value: f.kind }, f.label))) : null));
  }

  const specs = cat.parameters.filter((p) => sc && sc.parameters.includes(p.id));
  const groups = [...new Set([...GROUP_ORDER, ...specs.map((p) => p.group)])].filter((g) => specs.some((p) => p.group === g));
  for (const g of groups) {
    // Within a group the parameters listed for the focused failure come first.
    const listed = (p) => p.group !== 'Requirements' && (p.influences || []).some((id) => lab.focus.has(id));
    const list = specs.filter((p) => p.group === g).sort((x, y) => Number(listed(y)) - Number(listed(x)));
    const open = list.some((p) => (p.group !== 'Requirements' && (p.influences || []).some((id) => lab.focus.has(id))) || (lab.form.params[p.id] ?? p.default) !== paramValue(base, p));
    el.append(h('details', { class: 'lab-group', open },
      h('summary', null, g, h('span', { class: 'dim small' }, ` · ${list.length}`)),
      g === 'Requirements' ? h('p', { class: 'small lab-judge' }, 'These change only how a run is judged. The flight is the same; a requirement made easier is not a better landing.') : null,
      list.map((p) => field(p, cat, base))));
  }

  const diff = changes();
  el.append(h('div', { class: 'lab-run-bar' },
    h('p', { class: 'small' }, diff.length ? `${diff.length} change${diff.length > 1 ? 's' : ''} from the baseline` : 'No change from the baseline yet'),
    diff.length ? h('button', { type: 'button', class: 'btn btn-quiet', onclick: () => { startFrom(lab.base.id, lab.base.record); render(); } }, 'Reset all') : null,
    h('button', { type: 'button', class: ['btn', 'btn-primary', lab.busy === 'run' ? 'is-busy' : ''], id: 'lab-run', disabled: !!lab.busy || !diff.length, onclick: runExperiment }, 'Run experiment')));
}

function renderResult() {
  if (!parts) return;
  const el = clear(parts.result);
  el.append(h('p', { class: 'lab-h' }, 'Result'));
  if (!lab.exp) {
    el.append(h('p', { class: 'small dim' }, 'Run the experiment to see the new verdicts beside the baseline. The new run is a full simulation with its own record; the platform reuses a stored run only when the request is identical.'));
  } else {
    renderComparison(el);
  }
  renderGeneralisation(el);
  renderSweepBox(el);
}

function reqRows(base, exp) {
  const ids = [...new Set([...base.requirements.map((r) => r.id), ...exp.requirements.map((r) => r.id)])];
  return ids.map((id) => ({ id, a: base.requirements.find((r) => r.id === id), b: exp.requirements.find((r) => r.id === id) }));
}

function firstEvents(record) {
  const out = new Map();
  for (const e of record.events || []) if (!out.has(e.kind)) out.set(e.kind, e);
  return out;
}

function renderComparison(el) {
  const a = lab.base.record;
  const b = lab.exp.record;
  const diff = requestDiff(a.request, b.request);
  const rows = reqRows(a, b);
  const fixed = rows.filter((r) => r.a && r.b && r.a.status === 'fail' && r.b.status === 'pass');
  const broke = rows.filter((r) => r.a && r.b && r.a.status === 'pass' && r.b.status === 'fail');
  const judgingOnly = diff.length > 0 && diff.every((d) => d.judging);
  const summary = [];
  if (fixed.length) summary.push(`now meets ${fixed.map((r) => r.b.label).join(', ')}`);
  if (broke.length) summary.push(`no longer meets ${broke.map((r) => r.b.label).join(', ')}`);
  add(el, h('div', { class: 'lab-cmp-head' },
    h('div', null, h('p', { class: 'lab-h2' }, 'Baseline'), verdictPill(a)),
    h('span', { class: 'lab-arrow', 'aria-hidden': 'true' }, '→'),
    h('div', null, h('p', { class: 'lab-h2' }, 'Experiment'), verdictPill(b))),
  h('p', { class: 'lab-why' }, summary.length ? `The experiment ${summary.join(' and ')}.` : 'The same requirements pass and fail as in the baseline; the margins below show how far each moved.',
    judgingOnly ? ' Only a requirement limit changed: the flight is identical and only the judgement moved.' : ''),
  lab.exp.reused ? h('p', { class: 'small dim' }, 'An identical request was already in the library, so its stored run is shown; it was computed by the same simulator.') : null,
  h('div', { class: 'lab-diff' }, h('p', { class: 'lab-h2' }, 'What was changed'), h('ul', null, diff.map((d) => h('li', { class: 'small' }, d.text, d.judging ? h('span', { class: 'dim' }, ' (judging only)') : null)))),
  h('div', { class: 'lab-table-wrap' }, h('table', { class: 'grid-table lab-table' },
    h('thead', null, h('tr', null, h('th', null, 'Requirement'), h('th', null, 'Limit'), h('th', null, 'Baseline'), h('th', null, 'Experiment'), h('th', null, 'Margin change'))),
    h('tbody', null, rows.map(({ a: ra, b: rb }) => {
      const ma = ra ? marginOf(ra) : null;
      const mb = rb ? marginOf(rb) : null;
      const delta = ma !== null && mb !== null ? mb - ma : null;
      const r = rb || ra;
      const cell = (x) => (x ? h('td', { class: ['mono', 'small', `st-${x.status}`] }, `${x.status === 'pass' ? '✓' : x.status === 'fail' ? '✕' : '·'} ${x.observed}`) : h('td', null, '–'));
      return h('tr', { class: ra && rb && ra.status !== rb.status ? 'is-flip' : '' },
        h('td', null, r.label, r.category === 'invariant' ? h('span', { class: 'dim small' }, ' · safety') : null),
        h('td', { class: 'mono small' }, rb ? rb.expected : ra.expected),
        cell(ra), cell(rb),
        h('td', { class: ['mono', 'small', delta === null ? '' : delta > 1e-12 ? 'is-better' : delta < -1e-12 ? 'is-worse' : ''] }, delta === null ? '–' : `${delta > 0 ? '+' : ''}${fmt(delta)} ${unitOf(r)}`));
    })))),
  eventDeltas(a, b),
  h('p', { class: 'small dim' }, `One run on seed ${b.request.seed}. A change that helps one seed may not help another: check it across seeds below.`),
  h('div', { class: 'row' },
    h('button', { type: 'button', class: 'btn', onclick: () => navigate('compare', { runIds: [lab.base.id, lab.exp.id] }) }, 'Compare signals in detail'),
    h('button', { type: 'button', class: 'btn btn-quiet', onclick: () => navigate('run', { runId: lab.exp.id }) }, 'Analyse the experiment'),
    h('button', { type: 'button', class: 'btn btn-quiet', title: 'Make this run the new baseline and keep experimenting from it', onclick: () => { const e = lab.exp; startFrom(e.id, e.record); render(); } }, 'Use as new baseline')));
}

function eventDeltas(a, b) {
  const ea = firstEvents(a);
  const eb = firstEvents(b);
  const rows = [];
  for (const [kind, e] of eb) {
    const o = ea.get(kind);
    if (o && Math.abs(o.t - e.t) >= 0.005) rows.push([e.label, o.t, e.t]);
    if (!o) rows.push([e.label, null, e.t]);
  }
  for (const [kind, o] of ea) if (!eb.has(kind)) rows.push([o.label, o.t, null]);
  if (!rows.length) return null;
  return h('details', { class: 'lab-events' }, h('summary', null, `${rows.length} event${rows.length > 1 ? 's' : ''} moved, appeared or disappeared`),
    h('table', { class: 'grid-table' }, h('thead', null, h('tr', null, h('th', null, 'First event of its kind'), h('th', null, 'Baseline'), h('th', null, 'Experiment'))),
      h('tbody', null, rows.slice(0, 12).map(([l, t0, t1]) => h('tr', null, h('td', null, l), h('td', { class: 'mono small' }, t0 === null ? 'absent' : `${t0.toFixed(2)} s`), h('td', { class: 'mono small' }, t1 === null ? 'absent' : `${t1.toFixed(2)} s`))))));
}

function passes(record) {
  return !!record && record.outcome.status === 'success' && record.safety.status === 'safe';
}

/** Wilson score interval at 95 %, in percent. */
function wilson(k, n) {
  if (!n) return [0, 0];
  const z = 1.96;
  const p = k / n;
  const d = 1 + (z * z) / n;
  const c = p + (z * z) / (2 * n);
  const r = z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n));
  return [Math.max(0, ((c - r) / d) * 100), Math.min(100, ((c + r) / d) * 100)];
}

function renderGeneralisation(el) {
  const box = h('div', { class: 'lab-box' }, h('p', { class: 'lab-h2' }, 'Does it hold on other seeds?'));
  el.append(box);
  const g = lab.gen;
  if (g && !g.base) {
    box.append(h('p', { class: 'small' }, `Running ${g.progress} of ${g.total} simulations…`), h('div', { class: 'pl-loading-bar' }, h('span')));
    return;
  }
  if (!g) {
    box.append(h('p', { class: 'small dim' }, 'Runs the baseline conditions and your conditions on the same development seeds from 5000 upward. Protected seeds are never used.'),
      h('div', { class: 'row' }, [8, 16, 32].map((n) => h('button', { type: 'button', class: 'btn', dataset: { seeds: n }, disabled: !!lab.busy || !changes().length, onclick: () => checkSeeds(n) }, `${n} seeds`))));
    return;
  }
  const n = g.seeds.length;
  const kb = g.base.filter(passes).length;
  const ke = g.exp.filter(passes).length;
  let better = 0;
  let worse = 0;
  g.seeds.forEach((_, i) => { const a = passes(g.base[i]); const b = passes(g.exp[i]); if (!a && b) better += 1; if (a && !b) worse += 1; });
  const [lb, ub] = wilson(kb, n);
  const [le, ue] = wilson(ke, n);
  const failsBy = (records) => {
    const m = new Map();
    for (const r of records) if (r) for (const q of failedOf(r)) m.set(q.label, (m.get(q.label) || 0) + 1);
    return m;
  };
  const fb = failsBy(g.base);
  const fe = failsBy(g.exp);
  const labels = [...new Set([...fb.keys(), ...fe.keys()])];
  add(box, 
    h('div', { class: 'lab-gen' },
      h('div', null, h('p', { class: 'lab-gen-n' }, `${kb}/${n}`), h('p', { class: 'small' }, `baseline conditions meet every requirement and safety rule (95 % interval ${lb.toFixed(0)} to ${ub.toFixed(0)} %)`)),
      h('div', null, h('p', { class: 'lab-gen-n' }, `${ke}/${n}`), h('p', { class: 'small' }, `your conditions meet every requirement and safety rule (95 % interval ${le.toFixed(0)} to ${ue.toFixed(0)} %)`))),
    h('p', { class: 'small' }, `Seed by seed: ${better} improved, ${worse} got worse, ${n - better - worse} unchanged. Seeds ${g.seeds[0]} to ${g.seeds[n - 1]}.`),
    labels.length ? h('table', { class: 'grid-table lab-table' }, h('thead', null, h('tr', null, h('th', null, 'Requirement not met'), h('th', null, 'Baseline runs'), h('th', null, 'Your runs'))),
      h('tbody', null, labels.map((l) => h('tr', null, h('td', null, l), h('td', { class: 'mono' }, String(fb.get(l) || 0)), h('td', { class: 'mono' }, String(fe.get(l) || 0)))))) : null,
    g.errors.length ? h('p', { class: 'small error-text' }, `${g.errors.length} run${g.errors.length > 1 ? 's' : ''} could not be computed: ${g.errors[0]}`) : null,
    h('p', { class: 'small dim' }, `An estimate on ${n} development seeds of this idealised model. It is not a reliability figure and does not validate the change.`),
    h('div', { class: 'row' }, h('button', { type: 'button', class: 'btn btn-quiet', onclick: () => { lab.gen = null; renderResult(); } }, 'Clear')));
}

function renderSweepBox(el) {
  const cat = catalog();
  const sc = scenarioSpec();
  const specs = cat.parameters.filter((p) => sc && sc.parameters.includes(p.id) && p.group !== 'Requirements');
  if (!specs.length) return;
  const box = h('div', { class: 'lab-box' }, h('p', { class: 'lab-h2' }, 'Sweep one parameter'));
  el.append(box);
  const sw = lab.sweep;
  if (sw && !sw.records) {
    box.append(h('p', { class: 'small' }, `Running ${sw.progress} of ${sw.total} simulations…`), h('div', { class: 'pl-loading-bar' }, h('span')));
    return;
  }
  const hinted = specs.find((p) => (p.influences || []).some((id) => lab.focus.has(id))) || specs[0];
  const sel = h('select', { class: 'select', id: 'lab-sweep-param', 'aria-label': 'Parameter to sweep' }, specs.map((p) => h('option', { value: p.id, selected: sw ? sw.paramId === p.id : p.id === hinted.id }, p.label)));
  const specOf = () => specs.find((p) => p.id === sel.value);
  const from = h('input', { type: 'number', class: 'input mono lab-num', 'aria-label': 'From', value: specOf().min });
  const to = h('input', { type: 'number', class: 'input mono lab-num', 'aria-label': 'To', value: specOf().max });
  sel.addEventListener('change', () => { from.value = specOf().min; to.value = specOf().max; });
  const k = h('select', { class: 'select select-sm', 'aria-label': 'Number of values' }, [5, 7, 9].map((x) => h('option', { value: x, selected: x === 7 }, `${x} values`)));
  box.append(h('p', { class: 'small dim' }, 'Runs your current conditions with one parameter stepped across a range, on the same seed. It shows a trend on one seed, not an optimum.'),
    h('div', { class: 'row lab-sweep-ctl' }, sel, from, h('span', { class: 'dim' }, 'to'), to, k,
      h('button', { type: 'button', class: 'btn', id: 'lab-sweep-run', disabled: !!lab.busy, onclick: () => {
        const s = specOf();
        const a = Math.min(s.max, Math.max(s.min, Number(from.value)));
        const b = Math.min(s.max, Math.max(s.min, Number(to.value)));
        if (!(a < b)) { toast('The sweep needs a range with “from” below “to”.', 'error'); return; }
        runSweep(s.id, a, b, Number(k.value));
      } }, 'Run sweep')));
  if (sw && sw.records) box.append(sweepResult(sw, cat));
}

function sweepResult(sw, cat) {
  const spec = cat.parameters.find((p) => p.id === sw.paramId);
  const watch = [...new Set([...lab.focus, ...(spec.influences || [])])];
  const reqIds = watch.length ? watch : (cat.requirements || []).slice(0, 3).map((r) => r.id);
  const label = (id) => (cat.requirements.find((r) => r.id === id) || { label: id }).label;
  const table = h('div', { class: 'lab-table-wrap' }, h('table', { class: 'grid-table lab-table' },
    h('thead', null, h('tr', null, h('th', null, `${spec.label}${spec.unit ? ` (${spec.unit})` : ''}`), h('th', null, 'Outcome'), reqIds.map((id) => h('th', null, label(id))))),
    h('tbody', null, sw.values.map((v, i) => {
      const rec = sw.records[i];
      if (!rec) return h('tr', null, h('td', { class: 'mono' }, fmt(v, 6)), h('td', { colspan: 1 + reqIds.length, class: 'error-text small' }, 'not computed'));
      return h('tr', { class: passes(rec) ? 'is-pass' : '' },
        h('td', { class: 'mono' }, h('button', { type: 'button', class: 'link mono', title: 'Use this value in the experiment', onclick: () => { if (v === spec.default) delete lab.form.params[spec.id]; else lab.form.params[spec.id] = v; render(); } }, fmt(v, 6))),
        h('td', null, rec.outcome.label),
        reqIds.map((id) => { const q = rec.requirements.find((r) => r.id === id); return h('td', { class: ['mono', 'small', q ? `st-${q.status}` : ''] }, q ? q.observed : '–'); }));
    }))));
  const target = reqIds.find((id) => sw.records.some((r) => r && r.requirements.find((q) => q.id === id && marginOf(q) !== null)));
  return h('div', null, target ? sweepChart(sw, spec, target, label(target)) : null, table,
    sw.errors.length ? h('p', { class: 'small error-text' }, `${sw.errors.length} value${sw.errors.length > 1 ? 's' : ''} could not be computed: ${sw.errors[0]}`) : null,
    h('p', { class: 'small dim' }, 'Choose a value in the first column to carry it into the experiment.'));
}

function sweepChart(sw, spec, reqId, reqLabel) {
  const pts = sw.values.map((v, i) => {
    const q = sw.records[i] && sw.records[i].requirements.find((r) => r.id === reqId);
    return q ? { v, m: marginOf(q), unit: unitOf(q) } : null;
  }).filter((p) => p && p.m !== null);
  if (pts.length < 2) return null;
  const W = 420; const H = 150; const P = 28;
  const xs = pts.map((p) => p.v); const ys = [...pts.map((p) => p.m), 0];
  const x0 = Math.min(...xs); const x1 = Math.max(...xs);
  const y0 = Math.min(...ys); const y1 = Math.max(...ys);
  const X = (v) => P + ((v - x0) / (x1 - x0 || 1)) * (W - 2 * P);
  const Y = (m) => H - P - ((m - y0) / (y1 - y0 || 1)) * (H - 2 * P);
  const NS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.setAttribute('class', 'lab-chart');
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', `Margin of ${reqLabel} against ${spec.label}; above the limit line the requirement is met`);
  const el = (tag, attrs) => { const e = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v)); svg.appendChild(e); return e; };
  el('line', { x1: P, x2: W - P, y1: Y(0), y2: Y(0), class: 'lab-chart-zero' });
  el('polyline', { points: pts.map((p) => `${X(p.v)},${Y(p.m)}`).join(' '), class: 'lab-chart-line' });
  for (const p of pts) el('circle', { cx: X(p.v), cy: Y(p.m), r: 3.5, class: p.m >= 0 ? 'lab-chart-ok' : 'lab-chart-bad' });
  const t = (x, y, s, cls) => { const e = el('text', { x, y, class: cls || 'lab-chart-t' }); e.textContent = s; };
  t(P, 12, `${reqLabel}: margin to the limit (${pts[0].unit})`);
  t(W - P, Y(0) - 4, 'limit', 'lab-chart-t lab-chart-r');
  t(P, H - 8, fmt(x0, 4));
  t(W - P, H - 8, fmt(x1, 4), 'lab-chart-t lab-chart-r');
  return svg;
}
