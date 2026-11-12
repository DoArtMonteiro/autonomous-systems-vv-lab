// Comparison of up to eight stored runs: one colour per run, overlaid scene paths when every run has
// the same scene kind, overlaid signals on a shared time axis, and an outcome, safety and
// requirement matrix that marks the rows where the runs disagree.

import uPlot from '../../vendor/uplot/uPlot.esm.js';
import { h, clear, icon, num, prose, timeText, lowerIndex, nextId } from '../dom.js';
import { state, domainById, loadRecord, pref, setPref } from '../store.js';
import { modelOf, distinguishingLabels, requestText, verdictOfOutcome, verdictOfSafety, verdictOfRequirement, RUN_COLOURS, runDash, runSwatch, CATEGORY_TITLE, STATUS_TEXT } from '../model.js';
import { verdictGlyph } from '../verification.js';
import { axisStyle, cursorLine, cssVar } from '../charts.js';
import { sceneFor, sceneKind } from '../scenes/registry.js';
import { TimeCursor } from '../cursor.js';
import { api } from '../api.js';
import { toast, errorText, askName } from '../ui.js';

const MAX = 8;
let root;
let navigate = () => {};
let cmp = null;

export function initCompare(el, nav) {
  root = el;
  navigate = nav;
}

export function comparison() {
  return cmp;
}

export async function showCompare(opts) {
  if (opts && opts.runIds) {
    await open(opts.runIds.slice(0, MAX), opts.errors || [], opts.demo || null, opts.name || null);
  } else if (!cmp) {
    clear(root).append(h('div', { class: 'settings' },
      h('h1', null, 'Nothing to compare yet'),
      h('p', { class: 'dim' }, 'Tick several controllers in Configure, run a multi-run mission or demonstration, or select up to eight runs in Records.'),
      h('div', { class: 'row' }, h('button', { type: 'button', class: 'btn btn-primary', onclick: () => navigate('prepare') }, 'Configure'), h('button', { type: 'button', class: 'btn', onclick: () => navigate('library') }, 'Records'))));
  } else {
    requestAnimationFrame(() => resizeCharts());
  }
}

function dispose() {
  if (!cmp) return;
  if (cmp.cursor) cmp.cursor.dispose();
  if (cmp.scene) cmp.scene.dispose();
  for (const c of cmp.charts || []) c.u.destroy();
  if (cmp.ro) cmp.ro.disconnect();
  cmp = null;
}

async function open(runIds, errors, demo, name) {
  clear(root).append(h('div', { class: 'busy-overlay' }, h('p', null, `Loading ${runIds.length} run records…`)));
  const records = [];
  const loadErrors = [...errors];
  for (const id of runIds) {
    try {
      records.push({ id, record: await loadRecord(id) });
    } catch (e) {
      loadErrors.push({ runId: id, error: e });
    }
  }
  dispose();
  const models = records.map((r) => modelOf(r.record));
  const domainIds = [...new Set(records.map((r) => r.record.domain.id))];
  const cat = domainIds.length === 1 && domainById(domainIds[0]) ? domainById(domainIds[0]).catalog : null;
  const labels = distinguishingLabels(records.map((r) => r.record.request), cat);
  const t0 = Math.min(...models.map((m) => m.t0));
  const t1 = Math.max(...models.map((m) => m.t1));
  const unit = cat ? cat.time.unit : 's';
  cmp = { runIds: records.map((r) => r.id), records, models, labels, errors: loadErrors, demo, name, cat, unit, domainIds, t0, t1, colours: RUN_COLOURS };
  if (records.length) cmp.cursor = new TimeCursor({ t0, t1, unit, samples: models[0].primary ? models[0].timebases[models[0].primary] : [], events: [] });
  state.comparison = cmp;
  build();
}

function build() {
  clear(root);
  const { records, labels, colours, cat } = cmp;
  const saveBtn = h('button', { type: 'button', class: 'btn', disabled: records.length < 2, onclick: () => save() }, 'Save comparison…');
  const head = h('header', { class: 'cmp-head' },
    h('div', { class: 'cmp-head-row' },
      h('h1', null, cmp.name || (cmp.demo ? cmp.demo.title : `Comparison of ${records.length} runs`)),
      h('span', { class: 'dim small' }, cmp.domainIds.length === 1 ? `${domainById(cmp.domainIds[0]) ? domainById(cmp.domainIds[0]).manifest.name : cmp.domainIds[0]}` : `${cmp.domainIds.length} domains`),
      h('div', { class: 'spacer' }), saveBtn),
    cmp.demo ? h('div', { class: 'demo-banner' }, h('div', null, h('span', { class: 'dim' }, 'Expected, stated by the domain: '), prose(cmp.demo.expectation)),
      cmp.demo.look_at.length ? h('div', { class: 'small' }, h('span', { class: 'dim' }, 'Look at: '), cmp.demo.look_at.map(prose).join(' · ')) : null) : null,
    h('div', { class: 'run-legend', role: 'list', 'aria-label': 'Runs in this comparison' }, records.map((r, i) => {
      const rec = r.record;
      const rt = requestText(rec.request, cat);
      const ov = verdictOfOutcome(rec.outcome.status);
      const unjudged = rec.safety.status === 'safe' && rec.safety.class === 'not_evaluated';
      const sv = unjudged ? 'neutral' : verdictOfSafety(rec.safety.status);
      return h('div', { class: 'run-key', role: 'listitem', dataset: { run: r.id } },
        h('span', { class: 'key-swatch', style: { background: runSwatch(colours[i], runDash(i)) }, 'aria-hidden': 'true' }),
        h('span', { class: 'key-label', title: labels[i] }, labels[i]),
        h('button', { type: 'button', class: 'link small', 'aria-label': `Open run ${i + 1}`, onclick: () => navigate('run', { runId: r.id }) }, 'Open'),
        h('span', { class: 'key-verdicts' },
          h('span', { class: ['mini', `v-${ov}`], title: prose(rec.outcome.explanation) }, verdictGlyph(ov), rec.outcome.label),
          h('span', { class: ['mini', `v-${sv}`], title: prose(rec.safety.explanation) }, verdictGlyph(sv), unjudged ? 'not evaluated' : rec.safety.status, rec.safety.class && !unjudged ? ` · class ${rec.safety.class}` : '')),
        h('span', { class: 'key-sub', title: `${rt.controller} · seed ${rt.seed} · ${rt.faults} · ${r.id}` }, `${rt.controller} · seed ${rt.seed} · ${rt.faults} · ${r.id}`));
    })),
    cmp.errors.length ? h('div', { class: 'cmp-errors', role: 'alert' }, h('strong', null, `${cmp.errors.length} run${cmp.errors.length > 1 ? 's' : ''} could not be included`),
      h('ul', null, cmp.errors.map((e) => h('li', { class: 'small' }, e.request ? `${e.request.controller}, seed ${e.request.seed}: ` : `${e.runId}: `, errorText(e.error))))) : null);

  // Scene and matrix.
  const kinds = [...new Set(records.map((r) => sceneKind(r.record)))];
  const renderer = kinds.length === 1 ? sceneFor(records[0].record) : null;
  const sceneHost = h('section', { class: 'cmp-scene', 'aria-label': 'Overlaid scene' });
  const matrixHost = h('section', { class: 'cmp-matrix', 'aria-label': 'Verdict matrix' });
  const body = h('div', { class: 'cmp-body' });
  if (renderer && renderer.compare && records.length) body.append(sceneHost);
  body.append(matrixHost);
  const signals = h('section', { class: 'cmp-signals', 'aria-label': 'Overlaid signals' });
  root.append(h('div', { class: 'cmp' }, head, body, signals));
  if (renderer && renderer.compare && records.length) {
    try {
      cmp.scene = renderer.compare(sceneHost, cmp.models, colours, labels, cmp.cursor);
    } catch (e) {
      sceneHost.append(h('p', { class: 'error-text' }, `The overlaid scene could not be drawn: ${e.message}`));
    }
  } else if (records.length) {
    matrixHost.prepend(h('p', { class: 'dim small' }, kinds.length > 1 ? 'The runs have different scene kinds, so no overlaid scene is drawn.' : 'These runs declare no scene; compare them through the matrix and the signals.'));
  }
  matrixHost.append(matrix());
  if (records.length) buildSignals(signals);
}

// ----------------------------------------------------------------------------- matrix

function matrix() {
  const { records, labels, colours } = cmp;
  if (!records.length) return h('p', { class: 'empty' }, 'No run could be loaded.');
  let onlyDiff = false;
  const table = h('table', { class: 'matrix' });
  const toggleId = nextId('diff');
  const toggle = h('label', { class: 'toggle small', for: toggleId }, h('input', { type: 'checkbox', id: toggleId, onchange: (e) => { onlyDiff = e.target.checked; draw(); } }), 'Only rows where the runs disagree');
  const draw = () => {
    clear(table);
    table.append(h('thead', null, h('tr', null, h('th', { scope: 'col' }, 'Verdict'), records.map((r, i) => h('th', { scope: 'col', title: labels[i] }, h('span', { class: 'key-swatch', style: { background: runSwatch(colours[i], runDash(i)) } }), `Run ${i + 1}`)))));
    const tb = h('tbody');
    const rows = [];
    rows.push(['Mission outcome', records.map((r) => ({ v: verdictOfOutcome(r.record.outcome.status), text: r.record.outcome.label, key: r.record.outcome.code, title: prose(r.record.outcome.explanation) }))]);
    rows.push(['Safety', records.map((r) => {
      const unjudged = r.record.safety.status === 'safe' && r.record.safety.class === 'not_evaluated';
      return { v: unjudged ? 'neutral' : verdictOfSafety(r.record.safety.status), text: unjudged ? 'not evaluated' : `${r.record.safety.status}${r.record.safety.class ? ` · class ${r.record.safety.class}` : ''}`, key: `${r.record.safety.status}${r.record.safety.class}`, title: prose(r.record.safety.explanation) };
    })]);
    const ids = [];
    const cats = new Map();
    for (const r of records) for (const q of r.record.requirements || []) if (!ids.includes(q.id)) { ids.push(q.id); cats.set(q.id, q.category); }
    let diffCount = 0;
    const emitRow = (name, cells, extra) => {
      const keys = new Set(cells.map((c) => c.key));
      const differs = keys.size > 1;
      if (differs) diffCount += 1;
      if (onlyDiff && !differs) return;
      tb.append(h('tr', { class: differs ? 'differs' : '', dataset: { row: extra || name } },
        h('th', { scope: 'row' }, typeof name === 'string' ? name : name, differs ? h('span', { class: 'sr-only' }, ' (differs)') : null),
        cells.map((c) => h('td', { title: c.title || '' }, h('span', { class: ['cell', `v-${c.v}`] }, verdictGlyph(c.v), h('span', { class: ['cell-text', `v-${c.v}-text`] }, c.text))))));
    };
    for (const [name, cells] of rows) emitRow(name, cells);
    const order = ['invariant', 'requirement', 'declaration'];
    const catList = [...new Set(ids.map((id) => cats.get(id)))].sort((a, b) => (order.indexOf(a) + 1 || 9) - (order.indexOf(b) + 1 || 9));
    for (const cat of catList) {
      tb.append(h('tr', { class: 'sep' }, h('th', { colspan: String(records.length + 1) }, CATEGORY_TITLE[cat] || cat)));
      for (const id of ids.filter((x) => cats.get(x) === cat)) {
        const cells = records.map((r) => {
          const q = (r.record.requirements || []).find((x) => x.id === id);
          if (!q) return { v: 'neutral', text: 'absent', key: 'absent', title: 'This run does not report this id.' };
          const v = verdictOfRequirement(q);
          return { v, text: STATUS_TEXT[q.status] || q.status, key: q.status, title: `${q.label}\nexpected ${q.expected}\nobserved ${q.observed}${q.t !== null ? `\nat ${timeText(q.t, cmp.unit)}` : ''}` };
        });
        const first = (records.map((r) => (r.record.requirements || []).find((x) => x.id === id)).find(Boolean) || {}).label || '';
        emitRow(h('span', { class: 'req-name' }, h('span', { class: 'mono' }, id), h('span', { class: 'dim small' }, first)), cells, id);
      }
    }
    table.append(tb);
    summary.textContent = diffCount ? `${diffCount} row${diffCount > 1 ? 's' : ''} differ between the runs (marked).` : 'All runs agree on every verdict.';
  };
  const summary = h('p', { class: 'small', 'aria-live': 'polite' });
  const wrap = h('div', null, h('div', { class: 'row', style: { justifyContent: 'space-between', marginBottom: '6px' } }, h('h2', { class: 'pane-title' }, 'Outcome, safety and requirements'), toggle), summary, table);
  draw();
  return wrap;
}

// ----------------------------------------------------------------------------- signals

function commonChannels() {
  const [first, ...rest] = cmp.models;
  return first.channels.filter((c) => rest.every((m) => m.byId.has(c.id)));
}

function buildSignals(host) {
  const common = commonChannels();
  const domainKey = cmp.domainIds.join('+');
  const saved = (pref('compareSignals') || {})[domainKey];
  const lookIds = cmp.demo ? cmp.demo.look_at.map((x) => prose(x)).filter((x) => common.some((c) => c.id === x)) : [];
  let selected = (saved && saved.length ? saved : lookIds.length ? lookIds : common.filter((c) => c.kind === 'truth').slice(0, 3).map((c) => c.id))
    .filter((id) => common.some((c) => c.id === id));
  if (!selected.length && common.length) selected = [common[0].id];
  const unit = cmp.unit;
  const c = cmp.cursor;
  const time = h('output', { class: 'mono time-now' });
  const range = h('input', { type: 'range', min: String(cmp.t0), max: String(cmp.t1), step: String((cmp.t1 - cmp.t0) / 1000), value: String(cmp.t0), 'aria-label': 'Comparison time cursor', oninput: (e) => { c.pause(); c.set(Number(e.target.value)); } });
  const play = h('button', { type: 'button', class: 'tbtn tbtn-main', 'aria-label': 'Play (Space)', onclick: () => c.toggle() }, icon('play'));
  c.onPlayState((p) => { play.replaceChildren(icon(p ? 'pause' : 'play')); play.setAttribute('aria-label', p ? 'Pause (Space)' : 'Play (Space)'); });
  const transport = h('div', { class: 'cmp-transport' }, play, time, range, h('span', { class: 'dim small mono' }, timeText(cmp.t1, unit)));
  const sel = h('select', { class: 'select', 'aria-label': 'Add a signal' }, h('option', { value: '' }, `Add a signal (${common.length} common to all runs)…`),
    [...new Set(common.map((x) => x.group))].map((g) => h('optgroup', { label: g }, common.filter((x) => x.group === g).map((x) => h('option', { value: x.id }, `${x.label} (${x.id}${x.unit ? `, ${x.unit}` : ''})`)))));
  const chips = h('div', { class: 'cmp-chips' });
  const charts = h('div', { class: 'cmp-charts' });
  const pick = h('div', { class: 'cmp-pick' }, h('h2', { class: 'pane-title' }, 'Signals'), sel, chips,
    h('span', { class: 'dim small' }, 'One colour per run; drag to zoom, double-click to reset.'));
  host.append(transport, pick, charts);
  const persist = () => { const all = { ...(pref('compareSignals') || {}) }; all[domainKey] = selected; setPref('compareSignals', all); };
  sel.addEventListener('change', () => {
    if (sel.value && !selected.includes(sel.value)) { selected.push(sel.value); persist(); draw(); }
    sel.value = '';
  });
  const draw = () => {
    for (const ch of cmp.charts || []) ch.u.destroy();
    cmp.charts = [];
    clear(chips);
    clear(charts);
    for (const id of selected) {
      const ch = common.find((x) => x.id === id);
      chips.append(h('span', { class: 'cmp-chip' }, ch.label, h('button', { type: 'button', 'aria-label': `Remove ${ch.label}`, onclick: () => { selected = selected.filter((x) => x !== id); persist(); draw(); } }, icon('close'))));
      cmp.charts.push(overlayChart(charts, ch));
    }
    if (!selected.length) charts.append(h('p', { class: 'empty' }, common.length ? 'Add a signal to overlay it across the runs.' : 'The runs have no channel in common.'));
    c.set(c.t);
    for (const x of cmp.charts) x.setTime(c.t);
  };
  c.subscribe((t) => {
    time.textContent = timeText(t, unit);
    if (Number(range.value) !== t) range.value = String(t);
    for (const x of cmp.charts || []) x.setTime(t);
  });
  cmp.ro = new ResizeObserver(() => resizeCharts());
  cmp.ro.observe(charts);
  draw();
  c.set(cmp.t0);
  time.textContent = timeText(cmp.t0, unit);
}

function overlayChart(host, ch) {
  const tables = cmp.models.map((m) => {
    const c = m.byId.get(ch.id);
    return [m.timebases[c.timebase] || [], c.values];
  });
  const data = uPlot.join(tables);
  const ax = axisStyle();
  const unit = cmp.unit;
  const readouts = cmp.models.map((m, i) => {
    const v = h('span', { class: 'ro-val mono' });
    return { v, row: h('li', { class: 'ro' }, h('span', { class: 'swatch', style: { borderTop: '0', height: '2px', background: runSwatch(cmp.colours[i], runDash(i)) } }), h('span', { class: 'kind-badge' }, String(i + 1)), h('span', { class: 'ro-label' }, cmp.labels[i]), v, h('span', { class: 'ro-unit mono dim' }, ch.unit)) };
  });
  const plot = h('div', { class: 'chart-plot' });
  const wrap = h('section', { class: 'chart', 'aria-label': `${ch.label} across runs` },
    h('header', { class: 'chart-head' }, h('h3', null, ch.label), h('span', { class: 'mono dim' }, `${ch.id}${ch.unit ? ` · ${ch.unit}` : ''} · ${ch.kind}`)),
    h('ul', { class: 'readouts' }, readouts.map((r) => r.row)), plot);
  host.append(wrap);
  const u = new uPlot({
    width: Math.max(260, plot.clientWidth || host.clientWidth),
    height: 170,
    legend: { show: false },
    cursor: { sync: { key: 'cmp' }, drag: { x: true, y: false, setScale: true }, points: { show: false } },
    scales: { x: { time: false } },
    axes: [
      { ...ax, size: 28, values: (uu, vals) => vals.map((v) => (unit === 'tick' ? String(Math.round(v)) : num(v, 3))) },
      { ...ax, size: 52, values: (uu, vals) => vals.map((v) => num(v, 3)) },
    ],
    series: [{}, ...cmp.models.map((m, i) => ({ label: cmp.labels[i], stroke: cmp.colours[i], width: 1.6, dash: runDash(i), spanGaps: false, points: { show: false } }))],
  }, data, plot);
  u.over.addEventListener('dblclick', () => u.setScale('x', { min: cmp.t0, max: cmp.t1 }));
  const line = cursorLine(u);
  let downX = null;
  u.over.addEventListener('mousedown', (e) => { downX = e.clientX; });
  u.over.addEventListener('mouseup', (e) => {
    if (downX !== null && Math.abs(e.clientX - downX) < 3) {
      const t = u.posToVal(e.clientX - u.over.getBoundingClientRect().left, 'x');
      if (Number.isFinite(t)) { cmp.cursor.pause(); cmp.cursor.set(t); }
    }
    downX = null;
  });
  const setTime = (t) => {
    line(t);
    tables.forEach(([times, vals], i) => {
      const k = lowerIndex(times, t);
      const v = k >= 0 && t <= times[times.length - 1] + 1e-9 ? vals[k] : null;
      const text = k < 0 ? 'n/a' : t > times[times.length - 1] + 1e-9 ? 'ended' : v === null ? 'gap' : num(v, 5);
      if (readouts[i].v.textContent !== text) readouts[i].v.textContent = text;
    });
  };
  return { u, plot, setTime };
}

function resizeCharts() {
  if (!cmp) return;
  for (const c of cmp.charts || []) {
    const w = Math.max(260, c.plot.clientWidth);
    if (Math.abs(w - c.u.width) > 1) c.u.setSize({ width: w, height: c.u.height });
  }
  if (cmp.cursor) for (const c of cmp.charts || []) c.setTime(cmp.cursor.t);
}

async function save() {
  const res = await askName({ title: 'Save comparison', label: 'Comparison name', initial: cmp.name || (cmp.demo ? cmp.demo.title : `Comparison of ${cmp.runIds.length} runs`) });
  if (!res) return;
  try {
    await api.saveComparison(res.name, res.notes, cmp.runIds);
    cmp.name = res.name;
    toast(`Saved comparison “${res.name}”.`, 'ok');
  } catch (e) {
    toast(errorText(e), 'error');
  }
}

export function compareKey(e) {
  if (!cmp || !cmp.cursor) return false;
  if (e.key === ' ') { cmp.cursor.toggle(); return true; }
  if (e.key === 'ArrowRight') { cmp.cursor.step(e.shiftKey ? 10 : 1); return true; }
  if (e.key === 'ArrowLeft') { cmp.cursor.step(e.shiftKey ? -10 : -1); return true; }
  return false;
}

export function rethemeCompare() {
  if (cmp && cmp.records.length) open(cmp.runIds, cmp.errors.filter((e) => e.request), cmp.demo, cmp.name);
}

export { cssVar };
