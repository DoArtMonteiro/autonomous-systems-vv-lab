// The research library: stored runs (searchable and filterable, with editable label, notes and
// tags), saved scenarios and saved comparisons. Up to eight runs can be selected and compared.

import { h, clear, icon, words, nextId } from '../dom.js';
import { api } from '../api.js';
import { state, domainById, on, emit } from '../store.js';
import { verdictOfOutcome, verdictOfSafety } from '../model.js';
import { verdictGlyph } from '../verification.js';
import { toast, errorText } from '../ui.js';
import { openSaved, openRequest } from './prepare.js';

let root;
let navigate = () => {};
let runs = [];
let scenarios = [];
let comparisons = [];
let tab = 'runs';
let filter = { q: '', domain: '', outcome: '', safety: '' };
let selected = null;
const picked = new Set();

export function initLibrary(el, nav) {
  root = el;
  navigate = nav;
  on('runs-changed', () => { if (!root.hidden) refresh(); });
}

export async function showLibrary(opts) {
  if (opts && opts.select) { selected = opts.select; tab = 'runs'; }
  await refresh();
}

async function refresh() {
  try {
    [runs, scenarios, comparisons] = await Promise.all([api.listRuns(), api.listScenarios(), api.listComparisons()]);
  } catch (e) {
    toast(errorText(e), 'error');
  }
  render();
}

function render() {
  clear(root);
  const tabs = [['runs', `Runs`, runs.length], ['scenarios', 'Saved scenarios', scenarios.length], ['comparisons', 'Saved comparisons', comparisons.length]];
  const tabBar = h('div', { class: 'tabs', role: 'tablist', 'aria-label': 'Library sections', style: { borderBottom: 0, padding: 0 } },
    tabs.map(([id, text, n]) => h('button', { type: 'button', role: 'tab', class: 'tab', 'aria-selected': String(tab === id), onclick: () => { tab = id; render(); } }, text, h('span', { class: 'count' }, String(n)))));
  const head = h('div', { class: 'lib-head' }, h('h1', null, 'Library'), tabBar, h('div', { class: 'spacer' }),
    h('span', { class: 'dim small mono lib-path', title: state.info ? state.info.library : '' }, state.info ? state.info.library : ''),
    h('button', { type: 'button', class: 'btn', onclick: () => api.reveal(null).catch((e) => toast(errorText(e), 'error')) }, icon('folder'), 'Open library folder'));
  if (tab === 'runs') root.append(h('div', { class: 'lib' }, head, filters(), runTable()));
  else if (tab === 'scenarios') root.append(h('div', { class: 'lib' }, head, h('div'), savedList(scenarios, 'scenario')));
  else root.append(h('div', { class: 'lib' }, head, h('div'), savedList(comparisons, 'comparison')));
}

function domainName(id) {
  const d = domainById(id);
  return d ? d.manifest.name : id;
}

function scenarioLabel(m) {
  const d = domainById(m.summary.domain);
  const s = d && d.catalog && d.catalog.scenarios.find((x) => x.id === m.summary.scenario);
  return s ? s.label : m.summary.scenario;
}

function controllerLabel(m) {
  const d = domainById(m.summary.domain);
  const c = d && d.catalog && d.catalog.controllers.find((x) => x.id === m.summary.controller);
  return c ? c.label : m.summary.controller;
}

function matches(m) {
  const s = m.summary;
  if (filter.domain && s.domain !== filter.domain) return false;
  if (filter.outcome && s.outcome_status !== filter.outcome) return false;
  if (filter.safety && s.safety_status !== filter.safety) return false;
  if (filter.q) {
    const hay = [m.run_id, m.label, m.notes, m.tags.join(' '), s.domain, s.scenario, scenarioLabel(m), s.controller, controllerLabel(m), String(s.seed), s.faults.join(' '), s.outcome_label, s.outcome_code, s.safety_status, s.safety_class || '', s.failed.join(' ')].join(' ').toLowerCase();
    return filter.q.toLowerCase().split(/\s+/).filter(Boolean).every((w) => hay.includes(w));
  }
  return true;
}

function filters() {
  const q = h('input', { type: 'search', class: 'input', id: 'lib-search', placeholder: 'Search label, notes, scenario, controller, seed, fault, failed id…', value: filter.q, 'aria-label': 'Search runs' });
  q.addEventListener('input', () => { filter.q = q.value; drawRows(); });
  const domains = [...new Set(runs.map((r) => r.summary.domain))];
  const sel = (key, label, opts) => {
    const s = h('select', { class: 'select', 'aria-label': label, onchange: (e) => { filter[key] = e.target.value; drawRows(); } },
      h('option', { value: '' }, `${label}: all`), opts.map(([v, t]) => h('option', { value: v, selected: filter[key] === v }, t)));
    return s;
  };
  const cmpBtn = h('button', { type: 'button', class: 'btn btn-primary', id: 'lib-compare', disabled: picked.size < 2, onclick: () => navigate('compare', { runIds: [...picked] }) }, `Compare selected (${picked.size})`);
  filtersEl = h('div', { class: 'lib-filters' }, q,
    sel('domain', 'Domain', domains.map((d) => [d, domainName(d)])),
    sel('outcome', 'Outcome', [['success', 'success'], ['partial', 'partial'], ['failure', 'failure']]),
    sel('safety', 'Safety', [['safe', 'safe'], ['unsafe', 'unsafe']]),
    h('div', { class: 'spacer' }),
    h('span', { class: 'dim small', id: 'lib-count' }),
    cmpBtn);
  return filtersEl;
}

let filtersEl;
let tbody;
let detailHost;
let mainEl;

function runTable() {
  tbody = h('tbody');
  const table = h('table', { class: 'lib-table' },
    h('thead', null, h('tr', null,
      h('th', { scope: 'col' }, h('span', { class: 'sr-only' }, 'Select for comparison')),
      ['Run', 'Domain', 'Scenario', 'Controller', 'Seed', 'Faults', 'Outcome', 'Safety', 'Failed', 'Created (UTC)'].map((t) => h('th', { scope: 'col' }, t)))),
    tbody);
  detailHost = h('aside', { class: 'lib-detail', 'aria-label': 'Selected run' });
  mainEl = h('div', { class: ['lib-main', selected ? '' : 'no-detail'] }, h('div', { class: 'lib-table-wrap' }, table), detailHost);
  drawRows();
  drawDetail();
  return mainEl;
}

function drawRows() {
  if (!tbody) return;
  clear(tbody);
  const list = runs.filter(matches);
  const count = root.querySelector('#lib-count');
  if (count) count.textContent = `${list.length} of ${runs.length} runs`;
  if (!list.length) {
    tbody.append(h('tr', null, h('td', { colspan: '11', class: 'empty' }, runs.length ? 'No run matches the search and filters.' : 'The library has no runs yet. Run a mission from the library or configure one.')));
    return;
  }
  for (const m of list) {
    const s = m.summary;
    const ov = verdictOfOutcome(s.outcome_status);
    const sv = verdictOfSafety(s.safety_status);
    const cbId = nextId('pick');
    const cb = h('input', { type: 'checkbox', id: cbId, 'aria-label': `Select run ${m.run_id} for comparison`, checked: picked.has(m.run_id), onclick: (e) => e.stopPropagation(), onchange: (e) => {
      if (e.target.checked) {
        if (picked.size >= 8) { e.target.checked = false; toast('A comparison holds at most 8 runs.', 'info'); return; }
        picked.add(m.run_id);
      } else picked.delete(m.run_id);
      const b = root.querySelector('#lib-compare');
      if (b) { b.disabled = picked.size < 2; b.textContent = `Compare selected (${picked.size})`; }
    } });
    const tr = h('tr', { class: selected === m.run_id ? 'is-selected' : '', tabindex: '0', dataset: { run: m.run_id }, 'aria-selected': String(selected === m.run_id),
      onclick: () => select(m.run_id), ondblclick: () => navigate('run', { runId: m.run_id, meta: m }),
      onkeydown: (e) => { if (e.key === 'Enter') navigate('run', { runId: m.run_id, meta: m }); else if (e.key === ' ') { e.preventDefault(); select(m.run_id); } } },
    h('td', null, cb),
    h('td', null, m.label ? h('div', { class: 'run-label' }, m.label) : null, h('div', { class: 'mono dim small' }, m.run_id), m.tags.length ? h('div', { class: 'small' }, m.tags.map((t) => h('span', { class: 'tag' }, t))) : null),
    h('td', null, domainName(s.domain)),
    h('td', null, scenarioLabel(m)),
    h('td', null, controllerLabel(m)),
    h('td', { class: 'mono' }, String(s.seed)),
    h('td', { class: 'small' }, s.faults.length ? s.faults.map(words).join(', ') : h('span', { class: 'dim' }, 'none')),
    h('td', null, h('span', { class: ['cell', `v-${ov}`] }, verdictGlyph(ov), s.outcome_label)),
    h('td', null, h('span', { class: ['cell', `v-${sv}`] }, verdictGlyph(sv), s.safety_status, s.safety_class ? h('span', { class: ['class-badge', `class-${s.safety_class}`] }, s.safety_class) : null)),
    h('td', { class: 'failed' }, s.failed.join(' ')),
    h('td', { class: 'mono dim small' }, m.created_utc.replace('T', ' ').replace('Z', '')));
    tbody.append(tr);
  }
}

function select(id) {
  selected = id;
  for (const tr of tbody.querySelectorAll('tr[data-run]')) {
    const on = tr.dataset.run === id;
    tr.classList.toggle('is-selected', on);
    tr.setAttribute('aria-selected', String(on));
  }
  mainEl.classList.remove('no-detail');
  drawDetail();
}

function drawDetail() {
  if (!detailHost) return;
  clear(detailHost);
  const m = runs.find((r) => r.run_id === selected);
  if (!m) return;
  const label = h('input', { class: 'input', value: m.label, maxlength: '200', id: 'lib-label' });
  const notes = h('textarea', { class: 'input', rows: '5', maxlength: '4000', id: 'lib-notes' }, m.notes);
  const tags = h('input', { class: 'input', value: m.tags.join(', '), id: 'lib-tags', placeholder: 'comma separated' });
  const status = h('span', { class: 'small dim', 'aria-live': 'polite' });
  const save = h('button', { type: 'button', class: 'btn btn-primary', onclick: async () => {
    save.disabled = true;
    try {
      const t = tags.value.split(',').map((x) => x.trim()).filter(Boolean);
      const updated = await api.updateNotes(m.run_id, label.value, notes.value, t);
      Object.assign(m, updated);
      status.textContent = 'Saved.';
      drawRows();
      emit('runs-changed-meta', updated);
    } catch (e) {
      status.textContent = errorText(e);
    } finally {
      save.disabled = false;
    }
  } }, 'Save label and notes');
  detailHost.append(
    h('div', { class: 'row', style: { justifyContent: 'space-between' } }, h('h2', null, m.label || scenarioLabel(m)), h('button', { type: 'button', class: 'icon-btn', 'aria-label': 'Close details', onclick: () => { select(null); mainEl.classList.add('no-detail'); } }, icon('close'))),
    h('p', { class: 'mono dim small' }, `${m.run_id} · host ${m.host_sha256.slice(0, 12)}…`),
    h('div', { class: 'row' },
      h('button', { type: 'button', class: 'btn', onclick: () => navigate('run', { runId: m.run_id, meta: m }) }, 'Open run'),
      h('button', { type: 'button', class: 'btn btn-quiet', onclick: async () => {
        try { const rec = await api.record(m.run_id); openRequest(rec.request); } catch (e) { toast(errorText(e), 'error'); }
      } }, 'Configure a variant')),
    h('label', { class: 'field' }, h('span', { class: 'field-label' }, 'Label'), label),
    h('label', { class: 'field' }, h('span', { class: 'field-label' }, 'Notes'), notes),
    h('label', { class: 'field' }, h('span', { class: 'field-label' }, 'Tags'), tags),
    h('div', { class: 'row' }, save, status),
    h('p', { class: 'dim small' }, 'Labels, notes and tags are library metadata. They never enter a simulation, a run identity or an evidence hash.'));
}

function savedList(items, kind) {
  const host = h('div', { class: 'lib-list' });
  if (!items.length) {
    host.append(h('p', { class: 'empty' }, kind === 'scenario' ? 'No saved scenario. Save one from Configure.' : 'No saved comparison. Save one from a comparison.'));
    return host;
  }
  for (const it of items) {
    const sub = kind === 'scenario'
      ? `${it.requests.length} request${it.requests.length > 1 ? 's' : ''} · ${it.requests[0] ? domainName(it.requests[0].domain) : ''} · ${[...new Set(it.requests.map((r) => r.controller))].join(', ')} · seed ${[...new Set(it.requests.map((r) => r.seed))].join(', ')}`
      : `${it.run_ids.length} runs · ${it.run_ids.join(' ')}`;
    host.append(h('div', { class: 'lib-row' },
      h('div', { class: 'grow' }, h('div', { class: 'run-label' }, it.name), h('div', { class: 'dim small mono' }, sub), it.notes ? h('div', { class: 'small' }, it.notes) : null, h('div', { class: 'dim small mono' }, it.created_utc)),
      kind === 'scenario'
        ? h('button', { type: 'button', class: 'btn', onclick: () => openSaved(it) }, 'Open in Configure')
        : h('button', { type: 'button', class: 'btn', onclick: () => navigate('compare', { runIds: it.run_ids, name: it.name }) }, 'Open comparison'),
      h('button', { type: 'button', class: 'btn btn-quiet btn-danger', onclick: async () => {
        try {
          if (kind === 'scenario') await api.deleteScenario(it.id); else await api.deleteComparison(it.id);
          toast(`Deleted “${it.name}”.`, 'ok');
          if (kind === 'scenario') emit('scenarios-changed');
          refresh();
        } catch (e) { toast(errorText(e), 'error'); }
      } }, 'Delete')));
  }
  return host;
}
