// The run workspace: identity and the two headline verdicts, the scene (from the registry), the
// verification, metrics, notes and provenance tabs, the telemetry charts and the event timeline,
// all on one shared time cursor.

import { h, clear, icon, prose, timeText, words } from '../dom.js';
import { state, domainById, loadRecord, emit } from '../store.js';
import { modelOf, requestText } from '../model.js';
import { TimeCursor } from '../cursor.js';
import { Telemetry } from '../charts.js';
import { Timeline } from '../timeline.js';
import { verdictBlocks, requirementList, metricTable, notesBlock } from '../verification.js';
import { provenancePanel } from '../provenance.js';
import { sceneFor, sceneKind } from '../scenes/registry.js';
import { errorText } from '../ui.js';
import { api, logUiError } from '../api.js';

let root;
let ws = null; // {runId, record, model, cursor, telemetry, timeline, scene, tabs}
let navigate = () => {};

export function initRun(el, nav) {
  root = el;
  navigate = nav;
}

export function runWorkspace() {
  return ws;
}

export async function showRun(opts) {
  if (opts && opts.runId && (!ws || ws.runId !== opts.runId || opts.demo)) {
    await open(opts.runId, opts.meta, opts.demo);
  } else if (!ws) {
    renderEmpty();
  } else {
    // Charts measured while hidden need a resize once visible.
    requestAnimationFrame(() => { if (ws && ws.telemetry) ws.telemetry.resize(); });
  }
}

function renderEmpty() {
  clear(root).append(h('div', { class: 'settings' },
    h('h1', null, 'No run open'),
    h('p', { class: 'dim' }, 'Run a mission or a demonstration from Prepare, or open a stored run from the Library.'),
    h('div', { class: 'row' },
      h('button', { type: 'button', class: 'btn btn-primary', onclick: () => navigate('prepare') }, 'Prepare a mission'),
      h('button', { type: 'button', class: 'btn', onclick: () => navigate('library') }, 'Open the library'))));
}

function dispose() {
  if (!ws) return;
  ws.cursor.dispose();
  if (ws.telemetry) ws.telemetry.dispose();
  if (ws.timeline) ws.timeline.dispose();
  if (ws.scene) ws.scene.dispose();
  ws = null;
}

async function open(runId, meta, demo) {
  clear(root).append(h('div', { class: 'busy-overlay' }, h('p', null, 'Loading the run record…')));
  let record;
  try {
    record = await loadRecord(runId);
  } catch (e) {
    clear(root).append(h('div', { class: 'settings' }, h('h1', null, 'The run could not be opened'), h('p', { class: 'error-text' }, errorText(e))));
    return;
  }
  if (!meta) {
    try {
      meta = (await api.listRuns()).find((m) => m.run_id === runId) || null;
    } catch { meta = null; }
  }
  dispose();
  const model = modelOf(record);
  const d = domainById(record.domain.id);
  const cat = d && d.catalog;
  const unit = cat ? cat.time.unit : 's';
  const samples = model.primary ? model.timebases[model.primary] : [];
  const cursor = new TimeCursor({ t0: model.t0, t1: model.t1, unit, samples, events: model.events });
  ws = { runId, record, model, cursor, meta, demo, unit, domain: d };
  state.current = { runId, record };
  emit('current-run', runId);
  build();
}

function build() {
  const { record, model, cursor, unit, domain: d, demo } = ws;
  clear(root);
  const cat = d && d.catalog;
  const rt = requestText(record.request, cat);

  // Header: identity, actions, verdicts, validity.
  const head = h('header', { class: 'run-head' },
    h('div', { class: 'run-id' },
      h('h1', null, ws.meta && ws.meta.label ? ws.meta.label : rt.scenario),
      h('span', { class: 'ident' }, h('b', null, rt.controller), ` · seed ${rt.seed} · ${rt.faults}`),
      h('span', { class: 'mono dim small' }, `${d ? d.manifest.name : record.domain.id} · run ${ws.runId}`)),
    h('div', { class: 'run-actions' },
      h('button', { type: 'button', class: 'btn', onclick: () => { selectTab('prov'); const b = root.querySelector('[data-action="replay"]'); if (b) b.click(); } }, icon('replay'), 'Replay'),
      h('button', { type: 'button', class: 'btn btn-quiet', onclick: () => selectTab('prov') }, 'Provenance'),
      h('button', { type: 'button', class: 'btn btn-quiet', title: 'Open the run in the library to edit its label, notes and tags', onclick: () => navigate('library', { select: ws.runId }) }, 'Label and notes')),
    h('div', { class: 'verdicts' }, verdictBlocks(record)),
    h('div', { class: 'validity-strip' },
      h('b', null, 'Model validity'),
      h('span', { class: 'vtext', title: prose(record.model_validity) }, prose(record.model_validity)),
      h('button', { type: 'button', class: 'link small', onclick: () => selectTab('notes') }, `${(record.notes || []).length} note${(record.notes || []).length === 1 ? '' : 's'}`)),
    demo ? demoBanner(demo) : null);

  // Body.
  const renderer = sceneFor(record);
  const left = h('div', { class: ['run-left', renderer ? '' : 'no-scene'] });
  let sceneHost = null;
  if (renderer) {
    sceneHost = h('section', { class: 'scene-pane', 'aria-label': 'Scene', tabindex: '-1', id: 'scene-pane' });
    left.append(sceneHost);
  }
  const tabsHost = h('section', { class: 'tabpanel-host', 'aria-label': 'Verification and run information' });
  left.append(tabsHost);
  const teleHost = h('section', { class: 'tele', 'aria-label': 'Telemetry' });
  const body = h('div', { class: 'run-body' }, left, teleHost);
  const timeHost = h('section', { class: 'timeline', 'aria-label': 'Time cursor and events', id: 'timeline-pane', tabindex: '-1' });
  root.append(h('div', { class: 'run' }, head, body, timeHost));

  // Tabs.
  const reqs = record.requirements || [];
  const failed = reqs.filter((r) => r.status === 'fail');
  const failedInv = failed.some((r) => r.category === 'invariant');
  const tabs = [
    ['verify', 'Verification', failed.length ? h('span', { class: ['count', failedInv ? 'bad' : 'warn'] }, `${failed.length} failed`) : h('span', { class: 'count' }, String(reqs.length))],
    ['metrics', 'Metrics', h('span', { class: 'count' }, String((record.metrics || []).length))],
    ['notes', 'Notes and validity', h('span', { class: 'count' }, String((record.notes || []).length))],
    ['prov', 'Provenance', null],
  ];
  const tabBar = h('div', { class: 'tabs', role: 'tablist', 'aria-label': 'Run information' });
  const panel = h('div', { class: 'tabpanel', role: 'tabpanel', tabindex: '0', id: 'run-tabpanel' });
  for (const [id, text, extra] of tabs) {
    tabBar.append(h('button', { type: 'button', role: 'tab', class: 'tab', id: `tab-${id}`, 'aria-controls': 'run-tabpanel', 'aria-selected': 'false', dataset: { tab: id }, onclick: () => selectTab(id),
      onkeydown: (e) => {
        const ids = tabs.map((t) => t[0]);
        const k = ids.indexOf(id);
        if (e.key === 'ArrowRight') { selectTab(ids[(k + 1) % ids.length]); tabBar.querySelector(`[data-tab="${ids[(k + 1) % ids.length]}"]`).focus(); }
        if (e.key === 'ArrowLeft') { selectTab(ids[(k + ids.length - 1) % ids.length]); tabBar.querySelector(`[data-tab="${ids[(k + ids.length - 1) % ids.length]}"]`).focus(); }
      } }, text, extra));
  }
  tabsHost.append(tabBar, panel);
  ws.tabBar = tabBar;
  ws.panel = panel;
  ws.panels = {
    verify: () => requirementList(record, unit, (t, r) => focusTime(t, r.id)),
    metrics: () => metricTable(record),
    notes: () => notesBlock(record, d && d.manifest),
    prov: () => provenancePanel(ws.runId, record, ws.meta),
  };
  ws.panelCache = {};
  selectTab('verify');

  // Telemetry, timeline, scene.
  ws.telemetry = new Telemetry(teleHost, model, cursor, { domainId: record.domain.id, timeUnit: unit, onPick: (t) => { cursor.pause(); cursor.set(t); } });
  ws.timeline = new Timeline(timeHost, model, cursor, { timeUnit: unit });
  if (renderer) {
    try {
      ws.scene = renderer.mount(sceneHost, model, cursor, { unit });
    } catch (e) {
      logUiError(`scene ${sceneKind(record)}: ${e && e.stack ? e.stack : e}`);
      clear(sceneHost).append(h('p', { class: 'no-scene-note error-text' }, `The scene could not be drawn: ${e.message}`));
      ws.scene = null;
    }
  }
  if (!renderer) {
    tabsHost.prepend(h('p', { class: 'no-scene-note small' }, sceneKind(record) === 'none'
      ? 'This domain declares no scene; telemetry, events and verification are complete without one.'
      : `No renderer for scene kind “${sceneKind(record)}”; telemetry, events and verification are complete without it.`));
  }
  cursor.set(model.t0);
}

function demoBanner(demo) {
  const look = h('div', { class: 'look' });
  for (const item of demo.look_at) {
    const text = prose(item);
    const id = text.trim();
    if (ws.model.byId.has(id)) look.append(h('button', { type: 'button', class: 'link small', onclick: () => ws.telemetry.focusChannels([id]) }, `signal ${id}`));
    else if (id === 'scene') look.append(h('button', { type: 'button', class: 'link small', onclick: () => { const s = root.querySelector('#scene-pane'); if (s) s.focus(); } }, 'the scene'));
    else if (id === 'events') look.append(h('button', { type: 'button', class: 'link small', onclick: () => root.querySelector('#timeline-pane').focus() }, 'the events'));
    else if (id === 'requirements') look.append(h('button', { type: 'button', class: 'link small', onclick: () => selectTab('verify') }, 'the requirements'));
    else look.append(h('span', { class: 'small' }, text));
  }
  return h('div', { class: 'demo-banner' },
    h('div', null, h('b', null, `Demonstration: ${demo.title}. `), h('span', { class: 'dim' }, 'Expected: '), prose(demo.expectation)),
    demo.look_at.length ? h('div', { class: 'look' }, h('span', { class: 'dim small' }, 'Look at:'), look) : null);
}

export function selectTab(id) {
  if (!ws) return;
  for (const b of ws.tabBar.children) {
    const on = b.dataset.tab === id;
    b.setAttribute('aria-selected', String(on));
    b.tabIndex = on ? 0 : -1;
  }
  ws.panel.setAttribute('aria-labelledby', `tab-${id}`);
  if (!ws.panelCache[id]) ws.panelCache[id] = ws.panels[id]();
  clear(ws.panel).append(ws.panelCache[id]);
  ws.tab = id;
}

/** Moves the cursor (and so the scene, charts and timeline) to a requirement instant. */
export function focusTime(t, reqId) {
  if (!ws) return;
  ws.cursor.pause();
  ws.cursor.set(t);
  if (reqId) {
    for (const el of ws.panel.querySelectorAll('.req.is-focus')) el.classList.remove('is-focus');
    const row = ws.panel.querySelector(`.req[data-id="${CSS.escape(reqId)}"]`);
    if (row) row.classList.add('is-focus');
  }
}

/** Keyboard transport, active while the run view is shown. */
export function runKey(e) {
  if (!ws) return false;
  const c = ws.cursor;
  if (e.key === ' ' || e.code === 'Space') { c.toggle(); return true; }
  if (e.key === 'ArrowRight') { c.step(e.shiftKey ? 10 : 1); return true; }
  if (e.key === 'ArrowLeft') { c.step(e.shiftKey ? -10 : -1); return true; }
  if (e.key === ']') { ws.timeline.jump(1); return true; }
  if (e.key === '[') { ws.timeline.jump(-1); return true; }
  if (e.key === 'Home') { c.pause(); c.set(ws.model.t0); return true; }
  if (e.key === 'End') { c.pause(); c.set(ws.model.t1); return true; }
  return false;
}

export function rethemeRun() {
  if (!ws) return;
  const t = ws.cursor.t;
  ws.telemetry.rebuildCharts();
  if (ws.scene && ws.scene.redraw) ws.scene.redraw();
  ws.cursor.set(t);
}

export { words };
