// Mission Control (M16): an operations layout over the replay the mission player already holds.
// Same runs, same cursor, same renderer choice; switching here never runs or reloads anything.
// Two densities: cinematic (the scene, the clock, four key values and the timeline) and technical
// (telemetry groups, live verdicts, sensors, events, comparison and the ways into analysis).
//
// Every value names its origin: T true state, E controller estimate, O sensor observation,
// C controller command, D derived, G geographic placement. Verdicts come from the record and are
// shown as judged only once the playback reaches their decisive instant.

import { h, clear, icon, prose, timeText, lowerIndex } from '../dom.js';
import { pref, setPref } from '../store.js';
import { telemetry, verdictsAt, fmt, TAG_WORD } from '../session.js';

const SEVERITY = {
  fault: { word: 'Fault injected', glyph: '◆' },
  onset: { word: 'Fault starts', glyph: '◆' },
  detection: { word: 'Controller detection', glyph: '●' },
  violation: { word: 'Violation', glyph: '▲' },
  warning: { word: 'Warning', glyph: '▲' },
  diverge: { word: 'Runs part', glyph: '⑂' },
  info: { word: 'Event', glyph: '•' },
};
const VSTATE = {
  pending: { word: 'pending', tone: 'neutral' }, met: { word: 'met', tone: 'ok' }, failed: { word: 'failed', tone: 'warn' },
  holding: { word: 'holding', tone: 'neutral' }, held: { word: 'held', tone: 'ok' }, violated: { word: 'violated', tone: 'bad' },
  'not-evaluated': { word: 'not evaluated', tone: 'neutral' },
};

/** Events of a run shown on the timeline: recorded events, injected fault onsets, divergence. */
export function eventsOf(pl, runIndex) {
  const run = pl.runs[runIndex];
  const out = [];
  const seen = new Set();
  for (const e of run.model.events || []) {
    if (!Number.isFinite(e.t)) continue;
    const sev = SEVERITY[e.severity] ? e.severity : 'info';
    const key = `${sev}@${e.t}@${e.label}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ t: e.t, sev, label: prose(e.label), source: e.source || null, run: runIndex });
  }
  for (const f of run.record.request.faults || []) {
    // The host may already record the onset as a fault event; do not show it twice.
    if (out.some((e) => e.sev === 'fault' && Math.abs(e.t - f.start) < 1e-9 && e.label.includes(f.kind))) continue;
    const mag = f.magnitude !== null && f.magnitude !== undefined ? ` (magnitude ${f.magnitude})` : '';
    out.push({ t: f.start, sev: 'onset', label: `Injected fault ${f.kind} starts${mag}, until ${timeText(f.end, pl.unit)}`, source: 'fault injection', run: runIndex });
  }
  if (runIndex > 0 && pl.div[runIndex] && pl.div[runIndex].t !== null) {
    const d = pl.div[runIndex];
    out.push({ t: d.t, sev: 'diverge', label: `${run.label} departs from ${pl.runs[0].label} by more than ${d.tol} ${d.unit}`, source: 'derived from the true positions', run: runIndex });
  }
  return out.sort((a, b) => a.t - b.t);
}

/** Severity order for the glyph of a shared marker: the most serious first. */
const RANK = ['violation', 'warning', 'onset', 'fault', 'detection', 'diverge', 'info'];

const sameEvent = (a, b) => !!a && !!b && a.t === b.t && a.run === b.run && a.label === b.label;

export function buildControl(pl, ctx) {
  const rocket = pl.kind === 'rocket-3d';
  let density = pref('controlDensity') === 'cinematic' ? 'cinematic' : 'technical';
  let selected = null;
  const viewport = h('div', { class: ['mc-viewport', rocket ? 'is-3d' : 'is-2d'], id: 'pl-viewport' });
  const clock = h('span', { class: 'mc-clock mono' });
  const phase = h('span', { class: 'mc-phase' });
  const densitySeg = h('div', { class: 'seg mc-density', role: 'radiogroup', 'aria-label': 'Density' },
    [['cinematic', 'Cinematic'], ['technical', 'Technical']].map(([d, text]) => h('button', { type: 'button', role: 'radio', class: 'seg-btn', 'aria-checked': String(d === density), dataset: { density: d }, onclick: () => setDensity(d) }, text)));
  const top = h('header', { class: 'mc-top' },
    h('div', { class: 'mc-id' },
      h('button', { type: 'button', class: 'mc-back', title: 'Back to the mission player', onclick: () => ctx.setView(pl.lastView && pl.lastView !== 'control' ? pl.lastView : 'engineering') }, h('span', { 'aria-hidden': 'true' }, '←'), ' Player'),
      h('div', { class: 'mc-id-t' }, h('p', { class: 'mc-eyebrow' }, `Mission Control · ${ctx.domainName}`), h('h1', { class: 'mc-title' }, pl.exp.title))),
    h('div', { class: 'mc-time' }, h('span', { class: 'mc-eyebrow' }, pl.unit === 'tick' ? 'Mission tick' : 'Mission elapsed time'), clock, phase),
    h('div', { class: 'mc-tools' }, ctx.viewSwitch(), ctx.envSelect(), densitySeg));
  const left = h('aside', { class: 'mc-left', 'aria-label': 'Telemetry at the playback time' });
  const right = h('aside', { class: 'mc-right', 'aria-label': 'Mission status, events and investigation' });
  const strip = h('div', { class: 'mc-strip', role: 'group', 'aria-label': 'Key values' });
  const runs = pl.runs.length > 1 ? h('div', { class: 'mc-runs', role: 'radiogroup', 'aria-label': 'Run shown in the scene' },
    pl.runs.map((r, i) => h('button', { type: 'button', role: 'radio', class: 'mc-run', 'aria-checked': String(i === pl.active), dataset: { run: String(i) }, onclick: () => ctx.setActive(i) },
      h('span', { class: 'pl-swatch', style: { background: r.colour } }), r.label))) : null;
  evidenceIsOpen = ctx.evidenceOpen || (() => false);
  const tl = buildTimeline(pl, (ev) => select(ev));
  if (ctx.analysisToggle) tl.el.querySelector('.mct-controls').append(ctx.analysisToggle());
  const evidence = h('section', { class: 'mc-evidence', hidden: true, 'aria-live': 'polite', 'aria-label': 'Selected event' });
  const legend = h('p', { class: 'mc-legend' });
  const el = h('div', { class: ['mc', `mc-${density}`], dataset: { density } }, viewport, top, left, right, strip, runs, evidence, h('footer', { class: 'mc-bottom' }, tl.el, legend), ctx.sceneNote());

  function setDensity(d) {
    density = d;
    setPref('controlDensity', d);
    el.classList.toggle('mc-cinematic', d === 'cinematic');
    el.classList.toggle('mc-technical', d === 'technical');
    el.dataset.density = d;
    for (const b of densitySeg.children) b.setAttribute('aria-checked', String(b.dataset.density === d));
    update(pl.cursor.t, true);
  }

  function select(ev) {
    selected = ev;
    pl.cursor.pause();
    if (ev.run !== pl.active && pl.runs[ev.run]) ctx.setActive(ev.run);
    pl.cursor.set(ev.t);
    renderEvidence();
    tl.highlight(ev);
    update(pl.cursor.t, true);
  }

  function renderEvidence() {
    if (!selected) { evidence.hidden = true; return; }
    const ev = selected;
    const run = pl.runs[ev.run];
    const s = SEVERITY[ev.sev] || SEVERITY.info;
    const times = (ev.group || [ev]).map((x) => x.t);
    const related = (run.record.requirements || []).filter((q) => q.status === 'fail' && Number.isFinite(q.t) && times.some((x) => Math.abs(q.t - x) < 1e-6));
    clear(evidence).append(...[
      h('div', { class: 'mc-ev-head' }, h('span', { class: `mc-glyph sev-${ev.sev}`, 'aria-hidden': 'true' }, s.glyph), h('span', { class: 'mc-eyebrow' }, `${s.word} · ${timeText(ev.t, pl.unit)}`),
        h('button', { type: 'button', class: 'mc-x', 'aria-label': 'Close the event', onclick: () => { selected = null; renderEvidence(); tl.highlight(null); } }, '×')),
      ev.group && ev.group.length > 1
        ? h('ul', { class: 'mc-ev-group' }, ev.group.map((x) => h('li', null, h('span', { class: `mc-glyph sev-${x.sev}`, 'aria-hidden': 'true' }, (SEVERITY[x.sev] || SEVERITY.info).glyph), ` ${timeText(x.t, pl.unit)} `, h('span', { class: 'mc-ev-label' }, x.label), x.source ? h('span', { class: 'dim small' }, ` · ${x.source}`) : null)))
        : h('p', { class: 'mc-ev-label' }, ev.label),
      h('p', { class: 'mc-ev-meta' }, h('span', { class: 'pl-swatch', style: { background: run.colour } }), ` ${run.label}`, ev.source && !(ev.group && ev.group.length > 1) ? ` · source: ${ev.source}` : ''),
      related.length ? h('ul', { class: 'mc-ev-rel' }, related.map((q) => h('li', null, h('b', null, q.label), `: expected ${q.expected}, observed ${q.observed}`))) : null,
      h('div', { class: 'mc-ev-actions' },
        h('button', { type: 'button', class: 'btn btn-sm', dataset: { action: 'analyse-at' }, onclick: () => ctx.navigate('run', { runId: run.runId, t: ev.t }) }, 'Analyse at this instant'),
        pl.runs.length > 1 ? h('button', { type: 'button', class: 'btn btn-sm btn-quiet', onclick: () => ctx.navigate('compare', { runIds: pl.runs.map((r) => r.runId), demo: pl.demo }) }, 'Compare runs') : null,
        pl.exp.claim ? h('button', { type: 'button', class: 'btn btn-sm btn-quiet', onclick: () => ctx.navigate('discover', { claimId: pl.exp.claim }) }, 'Challenge the claim') : null)].filter(Boolean));
    evidence.hidden = false;
  }

  // Panels are built once (and again only when their shape changes) and then updated in place, so
  // a button under the pointer or with keyboard focus is never replaced during playback.
  const allEvents = pl.runs.flatMap((_, i) => eventsOf(pl, i)).sort((a, b) => a.t - b.t);
  const valueSet = (node, r) => {
    const text = fmt(r.value, r.digits);
    const unit = r.value !== null && typeof r.value === 'number' && r.unit ? ` ${r.unit}` : '';
    if (node.firstChild && node.firstChild.nodeValue === text && node.dataset.unit === unit) return;
    node.dataset.unit = unit;
    node.replaceChildren(text, ...(unit ? [h('span', { class: 'mc-unit' }, unit)] : []));
  };
  const valueNode = (r, cls) => { const n = h('span', { class: cls }); valueSet(n, r); return n; };

  let leftSig = '';
  const leftRows = new Map();
  function telemetryPanel(t) {
    const groups = telemetry(pl.runs[pl.active], t, rocket, ctx.geo());
    const sig = groups.map((g) => `${g.id}:${g.rows.map((r) => `${r.id}/${r.tag}`).join(',')}`).join('|');
    if (sig !== leftSig) {
      leftSig = sig;
      leftRows.clear();
      left.replaceChildren(...groups.map((g) => h('section', { class: 'mc-group', dataset: { group: g.id } },
        h('h2', { class: 'mc-h' }, g.title),
        g.note ? h('p', { class: 'mc-note' }, g.note) : null,
        h('dl', { class: 'mc-dl' }, g.rows.map((r) => {
          const dd = valueNode(r, 'mc-val');
          leftRows.set(r.id, dd);
          return h('div', { class: 'mc-row', title: r.title, dataset: { channel: r.id } },
            h('dt', null, h('abbr', { class: `kind kind-${r.tag}`, title: TAG_WORD[r.tag] }, r.tag), r.label),
            h('dd', { class: 'mono' }, dd));
        })))));
      return;
    }
    for (const g of groups) for (const r of g.rows) { const n = leftRows.get(r.id); if (n) valueSet(n, r); }
  }

  // Status: verdict lines, events, comparison and the ways into analysis.
  const vLines = new Map();
  const evButtons = [];
  const cmpCells = [];
  function verdictLine(q) {
    const code = /^[A-Z]\d+_/.test(q.id) ? q.id.split('_')[0] : '';
    const li = h('li', { class: 'mc-v', dataset: { req: q.id } }, h('span', { class: 'mc-v-id mono', title: q.id }, code), h('span', { class: 'mc-v-l' }, q.label), h('span', { class: 'mc-v-s' }));
    vLines.set(q.id, li);
    return li;
  }
  function buildStatus() {
    vLines.clear();
    evButtons.length = 0;
    cmpCells.length = 0;
    const run = pl.runs[pl.active];
    const reqs = run.record.requirements || [];
    const out = [
      h('section', { class: 'mc-group', dataset: { group: 'requirements' } }, h('h2', { class: 'mc-h' }, 'Mission requirements'), h('ul', { class: 'mc-vlist' }, reqs.filter((q) => q.category !== 'invariant').map(verdictLine)),
        h('p', { class: 'mc-note' }, 'Judged at their decisive instant, usually contact; pending until then.')),
      h('section', { class: 'mc-group', dataset: { group: 'invariants' } }, h('h2', { class: 'mc-h' }, 'Safety invariants'), h('ul', { class: 'mc-vlist' }, reqs.filter((q) => q.category === 'invariant').map(verdictLine)),
        h('p', { class: 'mc-note' }, 'Judged on the true state throughout the run.')),
      h('section', { class: 'mc-group', dataset: { group: 'events' } }, h('h2', { class: 'mc-h' }, 'Events'),
        allEvents.length ? h('ol', { class: 'mc-evlist' }, allEvents.map((e) => {
          const label = h('span', { class: 'mc-ev-l' }, e.label);
          const glyph = h('span', { class: `mc-glyph sev-${e.sev}`, 'aria-hidden': 'true' }, (SEVERITY[e.sev] || SEVERITY.info).glyph);
          const b = h('button', { type: 'button', class: 'mc-evbtn', onclick: () => select(e) }, glyph, h('span', { class: 'mc-ev-t mono' }, timeText(e.t, pl.unit)),
            pl.runs.length > 1 ? h('span', { class: 'pl-swatch', style: { background: pl.runs[e.run].colour } }) : null, label);
          evButtons.push({ e, b, label, glyph, shown: null });
          return h('li', null, b);
        })) : h('p', { class: 'mc-note' }, 'No event recorded.')),
    ];
    if (pl.runs.length > 1) {
      const first = (r) => { const g = telemetry(r, pl.cursor.t, rocket, null); return g[0] ? g[0].rows.slice(0, 2) : []; };
      const heads = first(pl.runs[0]).map((x) => h('th', { scope: 'col' }, h('abbr', { class: `kind kind-${x.tag}` }, x.tag), ` ${x.label}`));
      const rows = pl.runs.map((r, i) => h('tr', null, h('th', { scope: 'row' }, h('span', { class: 'pl-swatch', style: { background: r.colour } }), ` ${r.label}`),
        ...first(r).map((x, k) => { const n = valueNode(x, 'mc-val'); cmpCells.push({ i, k, n }); return h('td', { class: 'mono', title: x.title }, n); })));
      out.push(h('section', { class: 'mc-group', dataset: { group: 'compare' } }, h('h2', { class: 'mc-h' }, 'Runs at this instant'), h('table', { class: 'mc-cmp' }, h('thead', null, h('tr', null, h('th', null, h('span', { class: 'sr-only' }, 'Run')), ...heads)), h('tbody', null, rows))));
    }
    out.push(h('section', { class: 'mc-group mc-go' }, h('h2', { class: 'mc-h' }, 'Investigate'),
      h('div', { class: 'mc-go-row' },
        h('button', { type: 'button', class: 'btn btn-sm', dataset: { action: 'analyse-here' }, onclick: () => ctx.navigate('run', { runId: pl.runs[pl.active].runId, t: pl.cursor.t }) }, 'Analyse this run here'),
        pl.runs.length > 1 ? h('button', { type: 'button', class: 'btn btn-sm btn-quiet', onclick: () => ctx.navigate('compare', { runIds: pl.runs.map((r) => r.runId), demo: pl.demo }) }, 'Compare in detail') : null,
        pl.exp.claim ? h('button', { type: 'button', class: 'btn btn-sm btn-quiet', onclick: () => ctx.navigate('discover', { claimId: pl.exp.claim }) }, 'Challenge the claim') : null)));
    right.replaceChildren(...out);
  }

  function statusPanel(t) {
    const run = pl.runs[pl.active];
    for (const v of verdictsAt(run, t)) {
      const li = vLines.get(v.q.id);
      if (!li) continue;
      const st = VSTATE[v.state];
      li.className = `mc-v v-${st.tone}`;
      li.dataset.state = v.state;
      li.lastChild.textContent = st.word;
      // Expected and observed values only once the verdict is reached: no result before its time.
      const reached = v.decided || v.state === 'held';
      const at = Number.isFinite(v.q.t) ? ` (decisive instant ${timeText(v.q.t, pl.unit)})` : '';
      li.title = reached ? `${v.q.label}: expected ${v.q.expected}, observed ${v.q.observed}${at}` : `${v.q.label}: ${st.word}`;
    }
    for (const x of evButtons) {
      const shown = !hiddenUntilReached(x.e, t);
      x.b.classList.toggle('is-past', x.e.t <= t + 1e-9);
      x.b.classList.toggle('is-sel', sameEvent(selected, x.e));
      if (x.shown === shown) continue;
      x.shown = shown;
      // A later finding is not listed at all before its time.
      x.b.parentElement.hidden = !shown;
    }
    for (const c of cmpCells) {
      const g = telemetry(pl.runs[c.i], t, rocket, null);
      const r = g[0] && g[0].rows[c.k];
      if (r) valueSet(c.n, r);
    }
  }

  const kv = new Map();
  function keyValues(t) {
    const flat = telemetry(pl.runs[pl.active], t, rocket, ctx.geo()).flatMap((x) => x.rows);
    const ids = rocket ? ['altitude', 'vel_z', 'touchdown_vertical_speed', 'act_throttle', 'err_z'] : ['truth_x_mm', 'truth_y_mm', 'goal_distance_mm', 'confidence_permille'];
    const rows = ids.map((id) => flat.find((r) => r.id === id)).filter(Boolean).slice(0, 4);
    const run = pl.runs[pl.active];
    const sig = `${pl.active}:${rows.map((r) => r.id).join(',')}`;
    if (strip.dataset.sig !== sig) {
      strip.dataset.sig = sig;
      kv.clear();
      const who = pl.runs.length > 1 ? [h('div', { class: 'mc-kv mc-kv-run' }, h('span', { class: 'mc-kv-l' }, 'Run shown'), h('span', { class: 'mc-kv-who' }, h('span', { class: 'pl-swatch', style: { background: run.colour } }), ` ${run.label}`))] : [];
      strip.replaceChildren(...who, ...rows.map((r) => {
        const n = valueNode(r, 'mc-kv-v mono');
        kv.set(r.id, n);
        return h('div', { class: 'mc-kv', title: r.title, dataset: { channel: r.id } }, h('span', { class: 'mc-kv-l' }, h('abbr', { class: `kind kind-${r.tag}` }, r.tag), r.label), n);
      }));
      return;
    }
    for (const r of rows) valueSet(kv.get(r.id), r);
  }

  function buildLegend() {
    const tags = ['T', 'E', 'O', 'C', 'D', ...(ctx.geoActive() && pl.track ? ['G'] : [])];
    legend.replaceChildren(...tags.map((k) => h('span', { title: TAG_WORD[k] }, h('abbr', { class: `kind kind-${k}` }, k), ` ${TAG_WORD[k].split(',')[0]}`)));
  }

  // Values change only from one recorded sample to the next: refresh them then, not every frame.
  let lastKey = null;
  function update(t, force) {
    clock.textContent = pl.unit === 'tick' ? String(Math.floor(t)) : `T+${t.toFixed(1)} s`;
    const ph = ctx.phaseAt(t);
    phase.textContent = ph.text;
    phase.className = `mc-phase ph-${ph.kind}`;
    tl.update(t);
    const m = pl.runs[pl.active].model;
    const key = `${pl.active}|${lowerIndex(m.timebases[m.primary] || [], t)}|${t >= m.t1 - 1e-9}|${density}|${selected ? selected.t : ''}`;
    if (!force && key === lastKey) return;
    lastKey = key;
    // The evidence card belongs to its instant: it closes once the playback moves away.
    if (selected && Math.abs(t - selected.t) > Math.max(0.5, (pl.cursor.t1 - pl.cursor.t0) / 100)) {
      selected = null;
      renderEvidence();
      tl.highlight(null);
    }
    keyValues(t);
    if (density === 'technical') {
      telemetryPanel(t);
      statusPanel(t);
    }
    if (runs) for (const b of runs.children) b.setAttribute('aria-checked', String(Number(b.dataset.run) === pl.active));
  }

  function refresh() {
    leftSig = '';
    strip.dataset.sig = '';
    buildStatus();
    buildLegend();
    tl.redraw();
    update(pl.cursor.t, true);
  }

  buildStatus();
  buildLegend();
  return { el, viewport, update, refresh, dispose: () => tl.dispose() };
}

let evidenceIsOpen = () => false;
const GATED = new Set(['violation', 'warning', 'detection', 'diverge']);

/**
 * Findings and outcomes (violations, warnings, detections, where the runs part) are not shown
 * until the playback reaches them, unless analysis mode is on or the result has been shown.
 */
export function hiddenUntilReached(e, t, open = evidenceIsOpen()) {
  return !open && GATED.has(e.sev) && e.t > t + 1e-9;
}

// ----------------------------------------------------------------------------- signature timeline

function buildTimeline(pl, onSelect) {
  const c = pl.cursor;
  const lanes = h('div', { class: 'mct-lanes' });
  const head = h('div', { class: 'mct-head', 'aria-hidden': 'true' });
  const ticks = h('div', { class: 'mct-ticks', 'aria-hidden': 'true' });
  const range = h('input', { type: 'range', class: 'mct-range', min: String(c.t0), max: String(c.t1), step: 'any', value: String(c.t), 'aria-label': 'Mission time', oninput: (e) => { c.pause(); c.set(Number(e.target.value)); } });
  const play = h('button', { type: 'button', class: 'mct-play', 'aria-label': 'Play', title: 'Play or pause (Space)', onclick: () => { if (c.t >= c.t1) c.set(c.t0); c.toggle(); } }, icon('play'));
  const prev = h('button', { type: 'button', class: 'mct-btn', 'aria-label': 'Previous event', title: 'Previous event', onclick: () => c.prevEvent() }, '‹');
  const next = h('button', { type: 'button', class: 'mct-btn', 'aria-label': 'Next event', title: 'Next event', onclick: () => c.nextEvent() }, '›');
  const onPlay = (p) => { play.replaceChildren(icon(p ? 'pause' : 'play')); play.setAttribute('aria-label', p ? 'Pause' : 'Play'); };
  const unplay = c.onPlayState(onPlay);
  onPlay(c.playing);
  const labels = h('div', { class: 'mct-labels' });
  const el = h('section', { class: 'mct', 'aria-label': 'Mission timeline' }, h('div', { class: 'mct-controls' }, prev, play, next), labels, h('div', { class: 'mct-track' }, ticks, lanes, head, range));
  const span = () => c.t1 - c.t0 || 1;
  const pos = (t) => `${(100 * (t - c.t0)) / span()}%`;
  let marks = [];

  function redraw() {
    clear(lanes);
    clear(ticks);
    clear(labels);
    marks = [];
    const s = span();
    const step = pl.unit === 'tick' ? Math.max(1, Math.ceil(s / 10)) : [1, 2, 5, 10, 20, 30, 60].find((x) => s / x <= 10) || 60;
    for (let t = Math.ceil(c.t0 / step) * step; t <= c.t1 + 1e-9; t += step) ticks.append(h('span', { class: 'mct-tick', style: { left: pos(t) } }, pl.unit === 'tick' ? String(t) : `${t} s`));
    pl.runs.forEach((run, i) => {
      const d = i > 0 ? pl.div[i] : null;
      const lane = h('div', { class: ['mct-lane', i === pl.active ? 'is-active' : ''], dataset: { run: String(i) } });
      labels.append(h('span', { class: ['mct-lane-l', i === pl.active ? 'is-active' : ''], dataset: { run: String(i) }, title: run.label }, h('span', { class: 'pl-swatch', style: { background: run.colour } }), run.label));
      for (const p of pl.phases[i]) lane.append(h('span', { class: `mct-seg ${p.kind}`, style: { left: pos(p.t0), width: `${(100 * Math.max(p.t1 - p.t0, s / 500)) / s}%` }, title: `${run.label}: ${p.label} (derived from the recorded engine or mode channel)` }));
      // Branch: until the runs part, a compared run follows the reference run within the tolerance.
      if (d && d.t !== null) {
        lane.append(h('span', { class: 'mct-shared', style: { left: '0', width: pos(d.t) }, title: `Within ${d.tol} ${d.unit} of ${pl.runs[0].label} until ${timeText(d.t, pl.unit)} (derived)` }));
        lane.append(h('span', { class: 'mct-fork', style: { left: pos(d.t) }, title: `Branch point at ${timeText(d.t, pl.unit)}` }));
      } else if (d && d.t === null) {
        lane.append(h('span', { class: 'mct-shared', style: { left: '0', width: '100%' }, title: `Within ${d.tol} ${d.unit} of ${pl.runs[0].label} throughout (derived)` }));
      }
      const end = run.model.t1;
      lane.append(h('span', { class: 'mct-end', style: { left: pos(end) }, title: `${run.label}: ${run.record.scene && run.record.scene.touchdown ? 'contact' : 'end of run'} at ${timeText(end, pl.unit)}` }));
      // Events closer than one marker width share a marker; the evidence card lists them all.
      const groups = [];
      const near = s / 160;
      for (const ev of eventsOf(pl, i)) {
        const g = groups[groups.length - 1];
        if (g && ev.t - g[0].t <= near) g.push(ev);
        else groups.push([ev]);
      }
      for (const g of groups) {
        const lead = [...g].sort((a, b) => RANK.indexOf(a.sev) - RANK.indexOf(b.sev))[0];
        const s2 = SEVERITY[lead.sev] || SEVERITY.info;
        const ev = { ...lead, group: g };
        const text = g.map((x) => `${(SEVERITY[x.sev] || SEVERITY.info).word}, ${timeText(x.t, pl.unit)}: ${x.label}`).join('; ');
        const b = h('button', { type: 'button', class: `mct-mark sev-${lead.sev}`, style: { left: pos(lead.t) }, 'aria-label': `${text} (${run.label})`, title: g.map((x) => `${timeText(x.t, pl.unit)} · ${x.label}`).join(' | '), onclick: () => onSelect(ev) },
          h('span', { 'aria-hidden': 'true' }, s2.glyph), g.length > 1 ? h('span', { class: 'mct-count', 'aria-hidden': 'true' }, String(g.length)) : null);
        marks.push({ ev, b, glyph: b.firstChild, text: `${text} (${run.label})`, tip: b.title, hidden: null });
        lane.append(b);
      }
      lanes.append(lane);
    });
    update(c.t);
  }

  function update(t) {
    head.style.left = pos(t);
    // A finding is not drawn until the playback reaches it (see hiddenUntilReached).
    for (const m of marks) {
      const hidden = m.ev.group.every((x) => hiddenUntilReached(x, t) || x.sev === 'info') && m.ev.group.some((x) => hiddenUntilReached(x, t));
      if (hidden === m.hidden) continue;
      m.hidden = hidden;
      m.b.hidden = hidden;
    }
    if (Number(range.value) !== t) range.value = String(t);
    range.setAttribute('aria-valuetext', timeText(t, pl.unit));
    for (const l of [...lanes.children, ...labels.children]) l.classList.toggle('is-active', Number(l.dataset.run) === pl.active);
  }

  function highlight(ev) {
    for (const m of marks) m.b.classList.toggle('is-sel', sameEvent(ev, m.ev));
  }

  redraw();
  return { el, update, redraw, highlight, dispose: () => unplay() };
}
