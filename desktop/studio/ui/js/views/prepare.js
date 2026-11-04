// Mission preparation, built entirely from the domain manifest and catalog: domain, scenario,
// controller, seed (with the protected ranges refused inline), faults, parameters, run, matched
// comparison of controllers, saved scenarios and curated demonstrations.

import { h, clear, icon, num, prose, words, debounce, nextId } from '../dom.js';
import { api } from '../api.js';
import { state, pref, setPref, visibleDomains, domainById, on, emit } from '../store.js';
import { toast, errorText, askName } from '../ui.js';
import { faultText } from '../model.js';

const REQUEST_SCHEMA = 'vv-run-request.v1';
const MAX_COMPARE = 8;

let root;
let form = null; // {domain, scenario, controller, seed, faults:[{kind,magnitude,start,end}], params:{}, compare:Set}
let errors = {}; // field key -> message
let backendError = null;
let validated = null; // 'ok' | 'bad' | 'pending' | null
let busy = false;
let savedScenarios = [];
let validateSeq = 0;
let navigate = () => {};

export function initPrepare(el, nav) {
  root = el;
  navigate = nav;
  on('domains', () => { resetForm(pref('lastDomain')); render(); });
  on('prefs', ({ key }) => {
    if (key === 'showDeveloperDomains') {
      if (form && !visibleDomains().some((d) => d.manifest.id === form.domain)) resetForm(null);
      render();
    }
  });
  on('scenarios-changed', () => loadSaved());
}

export function showPrepare() {
  if (!form) resetForm(pref('lastDomain'));
  loadSaved();
  render();
}

async function loadSaved() {
  try {
    savedScenarios = await api.listScenarios();
  } catch {
    savedScenarios = [];
  }
  if (root && !root.hidden) renderSide();
}

function domains() {
  return visibleDomains().filter((d) => d.catalog);
}

function current() {
  return form && domainById(form.domain);
}

function resetForm(domainId, request) {
  const list = domains();
  const d = list.find((x) => x.manifest.id === (request ? request.domain : domainId)) || list[0];
  if (!d) { form = null; return; }
  const cat = d.catalog;
  const sc = (request && cat.scenarios.find((s) => s.id === request.scenario)) || cat.scenarios[0];
  const seedDefault = request ? String(request.seed) : String(cat.demos[0] && cat.demos[0].requests[0] ? cat.demos[0].requests[0].seed : d.manifest.seeds.min);
  form = {
    domain: d.manifest.id,
    scenario: sc ? sc.id : '',
    controller: request ? request.controller : sc ? sc.default_controller : '',
    seed: seedDefault,
    faults: request ? request.faults.map((f) => ({ ...f })) : [],
    params: request ? { ...request.parameters } : {},
    compare: new Set(),
  };
  errors = {};
  backendError = null;
  validated = null;
  if (request) scheduleValidate();
}

export function openRequest(request) {
  resetForm(request.domain, request);
  setPref('lastDomain', request.domain);
  navigate('prepare');
}

// ----------------------------------------------------------------------------- validation

const MAX_SAFE = Number.MAX_SAFE_INTEGER;

function seedCheck(d, text) {
  const s = String(text).trim();
  if (!/^\d+$/.test(s)) return { error: 'The seed must be a whole number of zero or more.' };
  if (s.length > 16 || Number(s) > MAX_SAFE) return { error: `Seeds above ${MAX_SAFE} cannot be represented exactly by the interface; choose a smaller seed.` };
  const seed = Number(s);
  const p = d.manifest.seeds;
  if (seed < p.min || seed > p.max) return { error: `Seed ${seed} is outside the range of this domain (${p.min} to ${rangeMax(p.max)}).` };
  for (const r of p.protected) {
    if (seed >= r.start && seed <= r.end) return { error: `Seed ${seed} is protected (${r.start} to ${r.end}): ${prose(r.reason)}`, protected: true };
  }
  return { seed };
}

function rangeMax(max) {
  return max >= 2 ** 53 ? '2^63 - 1' : String(max);
}

function localErrors(d) {
  const cat = d.catalog;
  const e = {};
  const sc = cat.scenarios.find((s) => s.id === form.scenario);
  if (!sc) e.scenario = 'Choose a scenario.';
  if (sc && !sc.controllers.includes(form.controller)) e.controller = 'This controller is not available for the scenario.';
  const sv = seedCheck(d, form.seed);
  if (sv.error) e.seed = sv.error;
  form.faults.forEach((f, i) => {
    const spec = cat.faults.find((x) => x.kind === f.kind);
    if (!spec) { e[`fault${i}`] = 'Unknown fault.'; return; }
    if (spec.controllers && !spec.controllers.includes(form.controller)) {
      e[`fault${i}`] = `Needs one of the controllers ${spec.controllers.map((c) => label(cat.controllers, c)).join(', ')}.`;
      return;
    }
    if (!Number.isFinite(f.start) || !Number.isFinite(f.end)) { e[`fault${i}`] = 'The window needs a start and an end.'; return; }
    if (f.start < 0 || f.end < f.start) { e[`fault${i}`] = 'The window must satisfy 0 <= start <= end.'; return; }
    if (spec.window) {
      const len = f.end - f.start;
      if (len < spec.window.min_length - 1e-9 || len > spec.window.max_length + 1e-9) e[`fault${i}`] = `Window length must be ${num(spec.window.min_length)} to ${num(spec.window.max_length)} ${cat.time.unit}; it is ${num(len)}.`;
    }
    if (spec.magnitude) {
      if (!Number.isFinite(f.magnitude)) e[`fault${i}`] = 'Enter a magnitude.';
      else if (f.magnitude < spec.magnitude.min || f.magnitude > spec.magnitude.max) e[`fault${i}`] = `Magnitude must be ${num(spec.magnitude.min)} to ${num(spec.magnitude.max)} ${spec.magnitude.unit}.`;
    }
  });
  for (const [id, v] of Object.entries(form.params)) {
    const spec = cat.parameters.find((p) => p.id === id);
    if (!spec) continue;
    if (!Number.isFinite(v)) e[`param:${id}`] = 'Enter a number.';
    else if (v < spec.min || v > spec.max) e[`param:${id}`] = `Must be ${num(spec.min)} to ${num(spec.max)} ${spec.unit}.`;
    else if (spec.integer && !Number.isInteger(v)) e[`param:${id}`] = 'Must be a whole number.';
  }
  return e;
}

function label(items, id) {
  const it = items.find((x) => x.id === id);
  return it ? it.label : id;
}

/** Maps a platform validation message onto the field it names. */
function routeBackend(msg) {
  let m;
  if ((m = /^faults\[(\d+)\][.:]?\s*(.*)$/.exec(msg))) return [`fault${m[1]}`, m[2] || msg];
  if ((m = /^parameter (\S+)/.exec(msg))) return [`param:${m[1]}`, msg];
  if (/^seed /.test(msg)) return ['seed', msg];
  if (/^controller /.test(msg)) return ['controller', msg];
  if (/scenario/.test(msg) && /^unknown scenario/.test(msg)) return ['scenario', msg];
  return ['form', msg];
}

export function buildRequest(controller) {
  const d = current();
  const sc = d.catalog.scenarios.find((s) => s.id === form.scenario);
  const params = {};
  for (const [id, v] of Object.entries(form.params)) if (sc && sc.parameters.includes(id)) params[id] = v;
  return {
    schema: REQUEST_SCHEMA,
    domain: form.domain,
    scenario: form.scenario,
    controller: controller || form.controller,
    seed: Number(String(form.seed).trim()),
    faults: form.faults.map((f) => ({ kind: f.kind, magnitude: f.magnitude ?? null, start: f.start, end: f.end })),
    parameters: params,
  };
}

const scheduleValidate = debounce(async () => {
  const d = current();
  if (!d) return;
  errors = localErrors(d);
  if (Object.keys(errors).length) {
    backendError = null;
    validated = 'bad';
    renderErrors();
    return;
  }
  const seq = ++validateSeq;
  validated = 'pending';
  renderErrors();
  try {
    await api.validate(buildRequest());
    if (seq !== validateSeq) return;
    backendError = null;
    validated = 'ok';
  } catch (e) {
    if (seq !== validateSeq) return;
    const [key, msg] = routeBackend(e.message || '');
    if (key === 'form') backendError = errorText(e);
    else errors[key] = msg;
    validated = 'bad';
  }
  renderErrors();
}, 220);

function changed() {
  validated = 'pending';
  scheduleValidate();
  renderErrors();
}

// ----------------------------------------------------------------------------- render

function render() {
  if (!root) return;
  clear(root);
  const d = current();
  if (!d) {
    root.append(h('div', { class: 'settings' }, h('h1', null, 'No domain available'),
      h('p', null, 'No user-facing domain host was discovered, or its catalog could not be read. Open Settings to see discovered and rejected domains, or enable developer domains.')));
    return;
  }
  side = h('aside', { class: 'prep-side', 'aria-label': 'Domains, demonstrations and saved scenarios' });
  main = h('div', { class: 'prep-main' });
  root.append(h('div', { class: 'prep' }, side, main));
  renderSide();
  renderMain();
}

let side;
let main;

function renderSide() {
  if (!side) return;
  clear(side);
  const list = domains();
  const d = current();
  side.append(h('section', null,
    h('h2', { class: 'pane-title' }, 'Domain'),
    h('div', { class: 'domain-list', role: 'radiogroup', 'aria-label': 'Domain' }, list.map((x) => h('button', {
      type: 'button', role: 'radio', class: 'domain-opt', 'aria-checked': String(x.manifest.id === form.domain), dataset: { domain: x.manifest.id },
      onclick: () => { resetForm(x.manifest.id); setPref('lastDomain', x.manifest.id); render(); },
    }, h('span', { class: 'radio-mark', 'aria-hidden': 'true' }),
    h('span', { class: 'd-name' }, x.manifest.name, x.manifest.user_facing ? null : h('span', { class: 'tag tag-dev' }, 'developer')),
    h('span', { class: 'd-meta mono' }, `${x.manifest.id} ${x.manifest.version}`))))));

  const demos = d.catalog.demos || [];
  side.append(h('section', { 'aria-label': 'Demonstrations' },
    h('h2', { class: 'pane-title' }, `Demonstrations (${demos.length})`),
    demos.length ? demos.map((demo) => demoCard(d, demo)) : h('p', { class: 'empty small' }, 'This domain ships no curated demonstration. Configure a run on the right.')));

  const mine = savedScenarios.filter((s) => s.requests.length && s.requests[0].domain === d.manifest.id);
  side.append(h('section', { 'aria-label': 'Saved scenarios' },
    h('h2', { class: 'pane-title' }, `Saved scenarios (${mine.length})`),
    mine.length ? h('div', null, mine.map((s) => h('div', { class: 'saved-item' },
      h('div', { class: 'grow' }, h('div', { class: 'name', title: s.name }, s.name), h('div', { class: 'dim small mono' }, `${s.requests.length} request${s.requests.length > 1 ? 's' : ''} · ${s.created_utc.slice(0, 10)}`)),
      h('button', { type: 'button', class: 'btn btn-quiet', onclick: () => openSaved(s) }, 'Open'))))
      : h('p', { class: 'empty small' }, 'Save the mission on the right to reopen it later.')));
}

function demoCard(d, demo) {
  const n = demo.requests.length;
  const cat = d.catalog;
  const ctrls = [...new Set(demo.requests.map((r) => label(cat.controllers, r.controller)))].join(', ');
  const faults = [...new Set(demo.requests.flatMap((r) => r.faults.map((f) => words(f.kind))))];
  const runBtn = h('button', { type: 'button', class: 'btn btn-primary', dataset: { demo: demo.id }, onclick: () => runDemo(d, demo, runBtn) }, icon('play'), n > 1 ? `Run all ${n} and compare` : 'Run demonstration');
  return h('article', { class: 'demo', dataset: { demo: demo.id } },
    h('div', { class: 'demo-title' }, demo.title),
    h('div', { class: 'demo-meta' }, `${n} run${n > 1 ? 's' : ''} · ${ctrls} · seed ${[...new Set(demo.requests.map((r) => r.seed))].join(', ')} · ${faults.length ? faults.join(' + ') : 'no injected fault'}`),
    h('details', null,
      h('summary', null, icon('chev'), 'Narrative, what to look at, expected result'),
      h('div', { class: 'demo-body' },
        h('p', null, prose(demo.narrative)),
        demo.look_at.length ? [h('h4', null, 'What to look at'), h('ul', null, demo.look_at.map((x) => h('li', null, prose(x))))] : null,
        h('h4', null, 'Expected result, stated by the domain'),
        h('p', { class: 'expect' }, prose(demo.expectation)))),
    h('div', null, runBtn));
}

function renderMain() {
  clear(main);
  const d = current();
  const cat = d.catalog;
  const sc = cat.scenarios.find((s) => s.id === form.scenario);
  const unit = cat.time.unit;
  const formEl = h('div', { class: 'prep-form' });
  formEl.append(h('header', { class: 'prep-head' },
    h('h1', null, 'Configure a run'),
    h('span', { class: 'dim mono' }, `${d.manifest.name} · ${d.manifest.contract.name} ${d.manifest.contract.major}.${d.manifest.contract.minor}`),
    h('p', null, prose(d.manifest.description))));

  // Scenario
  const scSel = h('select', { class: 'select', id: 'f-scenario', 'aria-label': 'Scenario', 'aria-describedby': 'e-scenario', style: { maxWidth: '520px' }, onchange: (e) => {
    form.scenario = e.target.value;
    const s = cat.scenarios.find((x) => x.id === form.scenario);
    if (s && !s.controllers.includes(form.controller)) form.controller = s.default_controller;
    form.compare = new Set([...form.compare].filter((c) => s && s.controllers.includes(c)));
    for (const k of Object.keys(form.params)) if (!s.parameters.includes(k)) delete form.params[k];
    renderMain();
    changed();
  } }, cat.scenarios.map((s) => h('option', { value: s.id, selected: s.id === form.scenario }, s.label)));
  const vehicle = sc && cat.vehicles.find((v) => v.id === sc.vehicle);
  formEl.append(section('Scenario', 'Mission and vehicle', [
    scSel, errSlot('scenario'),
    sc ? h('p', { class: 'scenario-desc' }, prose(sc.description)) : null,
    vehicle ? h('p', { class: 'dim small' }, h('b', null, `Vehicle: ${vehicle.label}. `), prose(vehicle.description)) : null,
  ]));

  // Controller
  const allowed = sc ? sc.controllers : [];
  const ctlName = nextId('ctl');
  const ctls = h('div', { class: 'ctl-list', role: 'radiogroup', 'aria-label': 'Controller', 'aria-describedby': 'e-controller' }, allowed.map((id) => {
    const c = cat.controllers.find((x) => x.id === id) || { id, label: id, description: '' };
    const blocked = faultBlock(cat, id);
    const cmpId = nextId('cmp');
    const cmpBox = h('input', { type: 'checkbox', id: cmpId, checked: form.compare.has(id), disabled: Boolean(blocked), onchange: (e) => {
      if (e.target.checked) form.compare.add(id); else form.compare.delete(id);
      renderActions();
    } });
    return h('div', { class: ['ctl', id === form.controller ? 'is-on' : ''] },
      h('input', { type: 'radio', name: ctlName, id: `ctl-${id}`, value: id, checked: id === form.controller, onchange: () => { form.controller = id; renderMain(); changed(); } }),
      h('label', { class: 'ctl-name', for: `ctl-${id}` }, c.label, h('span', { class: 'mono dim small' }, `  ${id}`)),
      c.description ? h('span', { class: 'ctl-desc' }, prose(c.description)) : null,
      h('span', { class: ['ctl-cmp', blocked ? 'is-off' : ''] }, cmpBox, h('label', { for: cmpId }, blocked ? `Cannot compare: ${blocked}` : 'Include in a matched comparison')));
  }));
  formEl.append(section('Controller', 'Run one, or tick several to compare them on the same seed and faults', [ctls, errSlot('controller')]));

  // Seed
  const p = d.manifest.seeds;
  const seedIn = h('input', { class: 'input mono', id: 'f-seed', 'aria-label': 'Seed', inputmode: 'numeric', autocomplete: 'off', value: form.seed, 'aria-describedby': 'e-seed h-seed', oninput: (e) => { form.seed = e.target.value; changed(); } });
  formEl.append(section('Seed', 'Drives every random draw of the run', [
    h('div', { class: 'seed-row' },
      seedIn,
      h('div', { class: 'ranges', id: 'h-seed' },
        h('span', null, `Domain range ${p.min} to ${rangeMax(p.max)}.`),
        p.protected.length ? p.protected.map((r) => h('span', { class: 'prot' }, 'Protected ', h('b', null, `${r.start} to ${r.end}`), `: ${prose(r.reason)}`)) : h('span', null, 'No protected seeds.'))),
    errSlot('seed'),
  ]));

  // Faults
  const faultRows = h('div', { class: 'sec-body' });
  form.faults.forEach((f, i) => faultRows.append(faultRow(cat, f, i, unit)));
  const avail = cat.faults.filter((s) => !form.faults.some((f) => f.kind === s.kind));
  const addSel = h('select', { class: 'select', 'aria-label': 'Fault to add' },
    h('option', { value: '' }, 'Choose a fault to inject…'),
    ['sensor', 'actuator', 'communication', 'environment'].concat([...new Set(avail.map((a) => a.target))]).filter((t, i, a) => a.indexOf(t) === i).map((t) => {
      const group = avail.filter((a) => a.target === t);
      return group.length ? h('optgroup', { label: t }, group.map((s) => {
        const block = s.controllers && !s.controllers.includes(form.controller);
        return h('option', { value: s.kind, disabled: block }, `${s.label}${block ? ` (needs ${s.controllers.map((c) => label(cat.controllers, c)).join(', ')})` : ''}`);
      })) : null;
    }));
  const full = form.faults.length >= cat.max_faults;
  const addBtn = h('button', { type: 'button', class: 'btn', disabled: full, onclick: () => {
    const spec = cat.faults.find((s) => s.kind === addSel.value);
    if (!spec) { addSel.focus(); return; }
    form.faults.push({ kind: spec.kind, magnitude: spec.magnitude ? spec.magnitude.default : null, start: spec.default_start, end: spec.default_end });
    renderMain();
    changed();
  } }, 'Add fault');
  formEl.append(section('Faults', `Up to ${cat.max_faults}; windows in ${cat.time.label.toLowerCase()}`, [
    form.faults.length ? faultRows : h('p', { class: 'dim' }, 'No injected fault: a nominal run.'),
    full ? h('p', { class: 'dim small' }, `The domain accepts at most ${cat.max_faults} faults per run.`) : h('div', { class: 'add-fault' }, addSel, addBtn),
  ]));

  // Parameters
  const view = pref('parameterView');
  const specs = (sc ? sc.parameters : []).map((id) => cat.parameters.find((x) => x.id === id)).filter(Boolean);
  const shown = view === 'advanced' ? specs : specs.filter((s) => !s.advanced);
  const viewSeg = h('div', { class: 'seg', role: 'radiogroup', 'aria-label': 'Parameter view' },
    ...[['beginner', 'Essential'], ['advanced', 'Advanced (all)']].map(([v, t]) => h('button', { type: 'button', role: 'radio', class: 'seg-btn', 'aria-checked': String(view === v), onclick: () => { setPref('parameterView', v); renderMain(); } }, t)));
  const changedCount = Object.keys(form.params).filter((k) => specs.some((s) => s.id === k)).length;
  formEl.append(section('Parameters', `${specs.length} accepted by this scenario${changedCount ? `, ${changedCount} changed` : ''}`, [
    h('div', { class: 'row' }, viewSeg),
    shown.length ? h('div', { class: 'params' }, shown.map((s) => paramField(s))) : h('p', { class: 'dim' }, specs.length
      ? `Every parameter of this scenario is an advanced tuning value; the defaults are used. Choose Advanced to see and change the ${specs.length} parameter${specs.length > 1 ? 's' : ''}.`
      : 'This scenario takes no parameters.'),
  ]));
  formEl.append(h('div', { id: 'e-form' }));
  main.append(formEl);
  actionbar = h('div', { class: 'actionbar', role: 'region', 'aria-label': 'Run actions' });
  main.append(actionbar);
  renderActions();
  renderErrors();
  if (validated === null) changed();
}

let actionbar;

function section(title, sub, body) {
  return h('section', { class: 'form-sec' }, h('div', { class: 'sec-label' }, h('h3', null, title), h('span', null, sub)), h('div', { class: 'sec-body' }, body));
}

function errSlot(key) {
  return h('div', { class: 'field-error', id: `e-${key.replace(':', '-')}`, role: 'alert', dataset: { err: key } });
}

function faultBlock(cat, controller) {
  for (const f of form.faults) {
    const spec = cat.faults.find((x) => x.kind === f.kind);
    if (spec && spec.controllers && !spec.controllers.includes(controller)) return `${spec.label} needs ${spec.controllers.map((c) => label(cat.controllers, c)).join(', ')}`;
  }
  return null;
}

function numberInput(value, unit, opts, onValue) {
  const inp = h('input', { type: 'text', inputmode: 'decimal', value: value === null || value === undefined ? '' : String(value), 'aria-label': opts.label, 'aria-describedby': opts.describedby, autocomplete: 'off' });
  inp.addEventListener('input', () => {
    const t = inp.value.trim();
    onValue(t === '' ? NaN : Number(t));
  });
  return h('div', { class: 'unit-input', dataset: { field: opts.field || '' } }, inp, unit ? h('span', { class: 'u' }, unit) : null);
}

function faultRow(cat, f, i, unit) {
  const spec = cat.faults.find((x) => x.kind === f.kind);
  const key = `fault${i}`;
  const inputs = h('div', { class: 'fault-inputs' });
  if (spec && spec.magnitude) {
    const m = spec.magnitude;
    inputs.append(h('label', { class: 'field' }, h('span', { class: 'field-label' }, 'Magnitude'),
      numberInput(f.magnitude, m.unit, { label: `${spec.label} magnitude`, describedby: `e-${key}`, field: `${key}-mag` }, (v) => { f.magnitude = v; changed(); }),
      h('span', { class: 'field-hint mono' }, `${num(m.min)} to ${num(m.max)}, default ${num(m.default)}`)));
  }
  inputs.append(h('label', { class: 'field' }, h('span', { class: 'field-label' }, 'Start'),
    numberInput(f.start, unit, { label: `${spec ? spec.label : f.kind} window start`, describedby: `e-${key}`, field: `${key}-start` }, (v) => { f.start = v; changed(); }),
    h('span', { class: 'field-hint mono' }, `default ${num(spec ? spec.default_start : 0)}`)));
  inputs.append(h('label', { class: 'field' }, h('span', { class: 'field-label' }, 'End'),
    numberInput(f.end, unit, { label: `${spec ? spec.label : f.kind} window end`, describedby: `e-${key}`, field: `${key}-end` }, (v) => { f.end = v; changed(); }),
    h('span', { class: 'field-hint mono' }, spec && spec.window ? `length ${num(spec.window.min_length)} to ${num(spec.window.max_length)}` : `default ${num(spec ? spec.default_end : 0)}`)));
  return h('div', { class: 'fault-row', dataset: { fault: f.kind, index: String(i) } },
    h('div', { class: 'fault-head' },
      h('span', { class: 'glyph v-neutral', style: { color: 'var(--fault)' }, 'aria-hidden': 'true' }, icon('fault')),
      h('strong', null, spec ? spec.label : f.kind),
      h('span', { class: 'tag' }, spec ? spec.target : '?'),
      spec && spec.controllers ? h('span', { class: 'tag', title: 'Only these controllers accept this fault' }, `only ${spec.controllers.join(', ')}`) : null,
      h('span', { class: 'grow' }),
      h('button', { type: 'button', class: 'btn btn-quiet', 'aria-label': `Remove ${spec ? spec.label : f.kind}`, onclick: () => { form.faults.splice(i, 1); renderMain(); changed(); } }, icon('close'), 'Remove')),
    spec ? h('p', { class: 'dim small', style: { margin: 0 } }, prose(spec.description)) : null,
    inputs,
    errSlot(key));
}

function paramField(s) {
  const has = s.id in form.params;
  const value = has ? form.params[s.id] : s.default;
  const key = `param:${s.id}`;
  return h('div', { class: ['param', has ? 'is-changed' : ''], dataset: { param: s.id } },
    h('label', { class: 'field', style: { margin: 0 } },
      h('span', { class: 'field-label' }, s.label, h('span', { class: 'mono dim' }, s.id),
        has ? h('button', { type: 'button', class: 'link reset small', onclick: (e) => { e.preventDefault(); delete form.params[s.id]; renderMain(); changed(); } }, 'reset') : null),
      numberInput(value, s.unit, { label: s.label, describedby: `e-${key.replace(':', '-')}`, field: key }, (v) => {
        if (v === s.default) delete form.params[s.id]; else form.params[s.id] = v;
        changed();
      }),
      h('span', { class: 'field-hint' }, `${prose(s.description)} Range ${num(s.min)} to ${num(s.max)}${s.integer ? ', whole numbers' : ''}; default ${num(s.default)}.`)),
    errSlot(key));
}

function renderErrors() {
  if (!main) return;
  for (const slot of main.querySelectorAll('[data-err]')) {
    const k = slot.dataset.err;
    const msg = errors[k];
    clear(slot);
    if (msg) slot.append(icon('warn'), h('span', null, msg));
    const owner = slot.closest('.fault-row');
    if (owner) owner.classList.toggle('is-invalid', Boolean(msg));
  }
  const seed = main.querySelector('#f-seed');
  if (seed) seed.setAttribute('aria-invalid', String(Boolean(errors.seed)));
  for (const el of main.querySelectorAll('.unit-input')) {
    const f = el.dataset.field || '';
    const k = f.startsWith('param:') ? f : f.replace(/-(mag|start|end)$/, '');
    el.setAttribute('aria-invalid', String(Boolean(errors[k])));
  }
  const fe = main.querySelector('#e-form');
  if (fe) {
    clear(fe);
    if (backendError) fe.append(h('div', { class: 'form-error', role: 'alert' }, icon('warn'), h('span', null, backendError)));
  }
  renderActions();
}

function renderActions() {
  if (!actionbar || !form) return;
  clear(actionbar);
  const hasErr = Object.keys(errors).length > 0 || backendError;
  const runBtn = h('button', { type: 'button', class: ['btn', 'btn-primary', busy === 'run' ? 'is-busy' : ''], id: 'run-mission', disabled: Boolean(busy) || hasErr || validated === 'pending', 'aria-keyshortcuts': 'Control+Enter', onclick: () => runMission() }, icon('play'), 'Run mission', h('kbd', null, 'Ctrl ↵'));
  const n = form.compare.size + (form.compare.has(form.controller) ? 0 : 1);
  const cmpBtn = h('button', { type: 'button', class: ['btn', busy === 'compare' ? 'is-busy' : ''], id: 'compare-controllers', disabled: Boolean(busy) || hasErr || form.compare.size < 1 || n > MAX_COMPARE, title: 'Runs the selected controllers and the current one on the same seed, faults and parameters', onclick: () => compareControllers() },
    form.compare.size ? `Compare ${n} controllers` : 'Compare controllers');
  const saveBtn = h('button', { type: 'button', class: 'btn btn-quiet', disabled: Boolean(busy) || hasErr, onclick: () => saveScenario() }, 'Save scenario…');
  const state = validated === 'ok' ? h('span', { class: 'valid-state ok' }, icon('check'), 'Accepted by the platform')
    : validated === 'pending' ? h('span', { class: 'valid-state dim' }, 'Checking…')
      : hasErr ? h('span', { class: 'valid-state bad' }, icon('warn'), 'Fix the marked fields') : h('span', { class: 'valid-state dim' }, '');
  let preview = '';
  try { preview = JSON.stringify(buildRequest()); } catch { preview = ''; }
  actionbar.append(runBtn, cmpBtn, saveBtn, state, h('span', { class: 'req-preview', title: preview }, preview));
}

// ----------------------------------------------------------------------------- actions

function setBusy(b) {
  busy = b;
  renderActions();
}

export async function runMission() {
  if (busy || !form) return;
  const d = current();
  errors = localErrors(d);
  if (Object.keys(errors).length) { renderErrors(); return; }
  setBusy('run');
  try {
    const out = await api.run(buildRequest());
    if (out.reused) toast('An identical run was already in the library; it was reopened, not recomputed.', 'info');
    emit('runs-changed');
    navigate('run', { runId: out.run_id, meta: out.meta });
  } catch (e) {
    const [key, msg] = routeBackend(e.message || '');
    if (key === 'form') backendError = errorText(e); else errors[key] = msg;
    renderErrors();
    toast(errorText(e), 'error');
  } finally {
    setBusy(false);
  }
}

async function compareControllers() {
  const ctrls = [form.controller, ...[...form.compare].filter((c) => c !== form.controller)].slice(0, MAX_COMPARE);
  setBusy('compare');
  try {
    await runCompare(ctrls.map((c) => buildRequest(c)), null);
  } finally {
    setBusy(false);
  }
}

export async function runCompare(requests, demo) {
  try {
    const items = await api.compare(requests);
    emit('runs-changed');
    const runIds = [];
    const errorsOut = [];
    items.forEach((it, i) => {
      if (it.status === 'ok') runIds.push(it.outcome.run_id);
      else errorsOut.push({ request: requests[i], error: it.error });
    });
    navigate('compare', { runIds, errors: errorsOut, demo });
  } catch (e) {
    toast(errorText(e), 'error');
  }
}

async function runDemo(d, demo, btn) {
  if (busy) return;
  busy = 'demo';
  btn.classList.add('is-busy');
  btn.disabled = true;
  try {
    if (demo.requests.length === 1) {
      const out = await api.run(demo.requests[0]);
      emit('runs-changed');
      navigate('run', { runId: out.run_id, meta: out.meta, demo });
    } else {
      await runCompare(demo.requests, demo);
    }
  } catch (e) {
    toast(errorText(e), 'error');
  } finally {
    busy = false;
    btn.classList.remove('is-busy');
    btn.disabled = false;
  }
}

/** Runs a demonstration by id (command palette). */
export function demoById(domainId, demoId) {
  const d = domainById(domainId);
  const demo = d && d.catalog && d.catalog.demos.find((x) => x.id === demoId);
  return demo ? { d, demo } : null;
}

export async function startDemo(domainId, demoId) {
  const x = demoById(domainId, demoId);
  if (!x) return;
  if (form && form.domain !== domainId) resetForm(domainId);
  navigate('prepare');
  const btn = root.querySelector(`button[data-demo="${demoId}"]`);
  if (btn) btn.click();
}

async function saveScenario() {
  const ctrls = form.compare.size ? [form.controller, ...[...form.compare].filter((c) => c !== form.controller)] : [form.controller];
  const d = current();
  const res = await askName({ title: 'Save scenario', label: 'Scenario name', initial: `${label(d.catalog.scenarios, form.scenario)} · seed ${form.seed}` });
  if (!res) return;
  try {
    await api.saveScenario(res.name, res.notes, ctrls.map((c) => buildRequest(c)));
    toast(`Saved scenario “${res.name}”.`, 'ok');
    emit('scenarios-changed');
  } catch (e) {
    toast(errorText(e), 'error');
  }
}

export function openSaved(s) {
  const first = s.requests[0];
  if (!first) return;
  resetForm(first.domain, first);
  for (const r of s.requests.slice(1)) form.compare.add(r.controller);
  setPref('lastDomain', first.domain);
  navigate('prepare');
  toast(s.requests.length > 1 ? `Opened “${s.name}”: ${s.requests.length} requests, the extra controllers are ticked for comparison.` : `Opened “${s.name}”.`, 'info');
}

export function describeRequest(req) {
  const d = domainById(req.domain);
  return d && d.catalog ? req.faults.map((f) => faultText(f, d.catalog)).join(' + ') : '';
}
