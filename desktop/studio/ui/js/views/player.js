// The mission player: one curated experience from the library, run by its domain host and replayed
// from the run records. The scene, the readouts, the phase band, the events and the result are all
// read from the records; phases and the divergence instant are derived from recorded channels and
// labelled as derived. Playback moves a display cursor over stored samples; it never runs or changes
// a simulation. Analysis, comparison and the claim behind the mission are one click away.

import { h, clear, icon, num, prose, lowerIndex, timeText } from '../dom.js';
import { loadRecord, emit, pref, setPref } from '../store.js';
import { modelOf } from '../model.js';
import { TimeCursor } from '../cursor.js';
import { SERIES } from '../charts.js';
import { api, logUiError } from '../api.js';
import { errorText } from '../ui.js';
import { experienceById, resolve, GRADES, DOMAIN_NAMES } from '../experiences.js';
import { claimStatus, forgetClaims } from '../claims.js';
import { mountCinema } from '../scenes/rocket-cinema.js';
import { ground2d } from '../scenes/ground.js';
import { openRequest } from './prepare.js';

let root;
let navigate = () => {};
let pl = null; // {exp, demo, domain, runs:[{runId, record, model, label, colour}], cursor, active, scene, revealed}
let loading = null; // {id} of the load in progress; a newer load replaces it
let visible = false;

const SPEEDS = [0.5, 1, 2, 4];
const ENGINE = ['Engine off', 'Engine on', 'Engine cut', 'Flameout'];
const ROCKET_METRICS = ['touchdown_vertical_speed', 'touchdown_horizontal_speed', 'touchdown_pad_distance'];
const KIND_WORD = { T: 'true state', E: 'controller estimate', O: 'sensor observation', D: 'derived' };

export function initPlayer(el, nav) {
  root = el;
  navigate = nav;
}

/** Read-only facts for tests. */
export function playerState() {
  if (!pl) return null;
  return { experience: pl.exp.id, runs: pl.runs.map((r) => r.runId), active: pl.active, t: pl.cursor.t, t1: pl.cursor.t1, revealed: pl.revealed, playing: pl.cursor.playing, scene: pl.scene ? (pl.scene.ok === false ? 'fallback' : pl.kind) : null };
}

export async function showPlayer(opts) {
  visible = true;
  const id = opts && opts.experienceId;
  if (id && loading && loading.id === id) return; // the same mission is already loading
  if (id && (!pl || pl.exp.id !== id)) {
    await load(id);
  } else if (!pl && !loading) {
    renderEmpty();
  } else if (pl) {
    // A challenge run elsewhere may have changed what the claim card should say.
    forgetClaims();
    renderSide();
    if (pl.scene && pl.scene.redraw) requestAnimationFrame(() => { if (pl && pl.scene && pl.scene.redraw) pl.scene.redraw(); });
  }
}

/** Called when another view is shown: playback stops, nothing renders off screen. */
export function leavePlayer() {
  visible = false;
  if (pl) pl.cursor.pause();
}

function renderEmpty() {
  clear(root).append(h('div', { class: 'pl-empty' },
    h('p', { class: 'eyebrow' }, 'Mission player'),
    h('h1', null, 'No mission is playing'),
    h('p', { class: 'dim' }, 'Choose a mission in the library. It runs on this machine and plays back here.'),
    h('button', { type: 'button', class: 'btn btn-primary', onclick: () => navigate('missions') }, 'Open the mission library')));
}

function dispose() {
  if (!pl) return;
  if (pl.unsub) pl.unsub();
  if (pl.unplay) pl.unplay();
  pl.cursor.dispose();
  if (pl.scene) pl.scene.dispose();
  pl = null;
}

// ----------------------------------------------------------------------------- loading

async function load(id) {
  const exp = experienceById(id);
  const r = exp ? resolve(exp) : null;
  if (!exp || !r.demo) {
    loading = null;
    dispose();
    if (!exp) { renderEmpty(); return; }
    clear(root).append(h('div', { class: 'pl-empty' }, h('h1', null, exp.title), h('p', { class: 'error-text' }, r.reason),
      h('button', { type: 'button', class: 'btn', onclick: () => navigate('missions') }, 'Back to the library')));
    return;
  }
  const token = { id };
  loading = token;
  dispose();
  const status = h('p', { class: 'pl-loading-text', role: 'status', 'aria-live': 'polite' }, 'Starting the simulation…');
  clear(root).append(h('div', { class: 'pl-loading' },
    h('p', { class: 'eyebrow' }, `${DOMAIN_NAMES[exp.domain] || exp.domain} · ${exp.kicker}`),
    h('h1', null, exp.title),
    h('p', { class: 'pl-loading-lead' }, exp.summary),
    h('div', { class: 'pl-loading-bar', 'aria-hidden': 'true' }, h('span')),
    status));
  const runs = [];
  try {
    for (let i = 0; i < r.demo.requests.length; i++) {
      status.textContent = r.demo.requests.length > 1 ? `Simulating run ${i + 1} of ${r.demo.requests.length}: ${exp.runs[i]}…` : 'Simulating the mission on this machine…';
      const out = await api.run(r.demo.requests[i]);
      if (loading !== token) return;
      const record = await loadRecord(out.run_id);
      if (loading !== token) return;
      runs.push({ runId: out.run_id, record, model: modelOf(record), label: exp.runs[i], colour: SERIES[i % SERIES.length] });
    }
  } catch (e) {
    logUiError(`player ${id}: ${e && e.message ? e.message : e}`);
    if (loading !== token) return;
    loading = null;
    clear(root).append(h('div', { class: 'pl-empty' }, h('h1', null, 'The mission could not run'), h('p', { class: 'error-text' }, errorText(e)),
      h('div', { class: 'row' }, h('button', { type: 'button', class: 'btn btn-primary', onclick: () => load(id) }, 'Try again'), h('button', { type: 'button', class: 'btn', onclick: () => navigate('missions') }, 'Back to the library'))));
    return;
  }
  if (loading !== token) return;
  loading = null;
  emit('runs-changed');
  forgetClaims();
  const t0 = Math.min(...runs.map((x) => x.model.t0));
  const t1 = Math.max(...runs.map((x) => x.model.t1));
  const longest = runs.reduce((a, b) => (b.model.t1 > a.model.t1 ? b : a));
  const unit = r.domain.catalog.time.unit;
  const cursor = new TimeCursor({ t0, t1, unit, samples: longest.model.primary ? longest.model.timebases[longest.model.primary] : [], events: runs.flatMap((x) => x.model.events) });
  const saved = Number(pref('missionSpeed'));
  cursor.speed = SPEEDS.includes(saved) ? saved : unit === 'tick' ? 0.5 : 1;
  pl = { exp, demo: r.demo, domain: r.domain, runs, cursor, active: 0, scene: null, revealed: false, unit, kind: runs[0].record.scene && runs[0].record.scene.kind };
  build();
  cursor.set(t0);
  if (visible && !matchMedia('(prefers-reduced-motion: reduce)').matches) cursor.play();
}

// ----------------------------------------------------------------------------- derived views

/** Phase segments of a run from its recorded channels (derived, not a simulator output). */
function phasesOf(run) {
  const m = run.model;
  const eng = m.byId.get('engine_state');
  const fb = m.byId.get('fallback');
  const src = eng || fb;
  if (!src) return [];
  const times = m.timebases[src.timebase] || [];
  const name = (v) => (eng ? ENGINE[v] || `Engine ${v}` : v === 1 ? 'Safety fallback' : 'Driving');
  const out = [];
  for (let i = 0; i < times.length; i++) {
    const v = src.values[i];
    if (v === null || v === undefined) continue;
    const last = out[out.length - 1];
    if (last && last.v === v) last.t1 = times[i];
    else out.push({ v, t0: times[i], t1: times[i], label: name(v), kind: eng ? `eng-${v}` : v === 1 ? 'fallback' : 'drive' });
  }
  for (let i = 0; i + 1 < out.length; i++) out[i].t1 = out[i + 1].t0;
  const td = run.record.scene && run.record.scene.touchdown;
  if (td && Number.isFinite(td.t) && out.length) out[out.length - 1].t1 = Math.max(out[out.length - 1].t1, td.t);
  return out;
}

/** First instant at which run b's true position departs from run a's by more than `tol` (derived). */
function divergence(a, b, rocket) {
  const ids = rocket ? ['pos_x', 'pos_y', 'pos_z'] : ['truth_x_mm', 'truth_y_mm'];
  const tol = rocket ? 1.0 : 0.5;
  const unit = rocket ? 'm' : 'mm';
  const ca = ids.map((id) => a.model.byId.get(id));
  const cb = ids.map((id) => b.model.byId.get(id));
  if (ca.some((c) => !c) || cb.some((c) => !c)) return null;
  const ta = a.model.timebases[ca[0].timebase] || [];
  const tb = b.model.timebases[cb[0].timebase] || [];
  const n = Math.min(ta.length, tb.length);
  for (let i = 0; i < n; i++) {
    if (ta[i] !== tb[i]) return null; // different sampling: not comparable sample by sample
    let d2 = 0;
    for (let k = 0; k < ids.length; k++) {
      const x = ca[k].values[i];
      const y = cb[k].values[i];
      if (x === null || y === null) continue;
      d2 += (x - y) * (x - y);
    }
    if (Math.sqrt(d2) > tol) return { t: ta[i], tol, unit };
  }
  return { t: null, tol, unit };
}

function value(run, id, t) {
  const c = run.model.byId.get(id);
  if (!c) return null;
  const times = run.model.timebases[c.timebase] || [];
  const i = lowerIndex(times, t);
  if (i < 0) return null;
  const v = c.values[i];
  return v === undefined ? null : v;
}

function metricValue(run, id) {
  const m = (run.record.metrics || []).find((x) => x.id === id);
  return m && Number.isFinite(m.value) ? m.value : null;
}

function readouts(run, t, rocket) {
  const v = (id) => value(run, id, t);
  if (rocket) {
    const vz = v('vel_z');
    const thr = v('act_throttle');
    const rej = v('altimeter_rejected');
    // After touchdown the speeds are the verifier's values at the contact instant, not the last
    // 0.1 s sample before it.
    const contact = t >= run.model.t1 - 1e-9 && metricValue(run, 'touchdown_vertical_speed') !== null;
    if (contact) {
      return [
        ['Altitude', 0, 'm', 'T', 'Contact: the nozzle exit plane reached the ground'],
        ['Descent rate', metricValue(run, 'touchdown_vertical_speed'), 'm/s', 'T', 'Vertical speed at the contact instant, from the verifier'],
        ['Horizontal speed', metricValue(run, 'touchdown_horizontal_speed'), 'm/s', 'T', 'Horizontal speed at the contact instant, from the verifier'],
        ['Tilt', v('tilt_deg'), '°', 'T', 'Last recorded sample'],
        ['Throttle', thr === null ? null : 100 * thr, '%', 'T', 'Last recorded sample'],
        ['From pad centre', metricValue(run, 'touchdown_pad_distance'), 'm', 'D', 'Distance of the nozzle plane from the pad centre at contact'],
        ['Altitude error', v('err_z'), 'm', 'D', 'Last recorded sample: vertical position the controller believes minus the true one'],
        ['Altimeter', rej === null ? null : rej === 1 ? 'rejected' : 'in use', '', 'E', 'Whether the controller had rejected the radar altimeter'],
      ];
    }
    return [
      ['Altitude', v('altitude'), 'm', 'T', 'Nozzle exit plane above the ground, true state'],
      ['Descent rate', vz === null ? null : -vz, 'm/s', 'T', 'Vertical speed, true state, positive downward'],
      ['Horizontal speed', v('vel_h'), 'm/s', 'T', 'True state'],
      ['Tilt', v('tilt_deg'), '°', 'T', 'Body axis from vertical, true state'],
      ['Throttle', thr === null ? null : 100 * thr, '%', 'T', 'Throttle the engine really applied'],
      ['From pad centre', v('pad_distance'), 'm', 'D', 'Distance of the nozzle plane from the pad centre, derived from the true state'],
      ['Altitude error', v('err_z'), 'm', 'D', 'Vertical position the controller believes minus the true one'],
      ['Altimeter', rej === null ? null : rej === 1 ? 'rejected' : 'in use', '', 'E', 'Whether the controller has rejected the radar altimeter'],
    ];
  }
  const fb = v('fallback');
  return [
    ['East', v('truth_x_mm'), 'mm', 'T', 'True position'],
    ['North', v('truth_y_mm'), 'mm', 'T', 'True position'],
    ['GPS north', v('gps_y_mm'), 'mm', 'O', 'GPS sample, empty when no sample arrived'],
    ['To goal', v('goal_distance_mm'), 'mm', 'D', 'Manhattan distance to the goal'],
    ['Confidence', v('confidence_permille'), '‰', 'E', 'Confidence in the last accepted fix'],
    ['Mode', fb === null ? null : fb === 1 ? 'fallback' : 'normal', '', 'D', 'Safety fallback of the controller'],
  ];
}

// ----------------------------------------------------------------------------- layout

function build() {
  const { exp, runs, cursor } = pl;
  const rocket = pl.kind === 'rocket-3d';
  const grade = GRADES[exp.grade] || GRADES.demonstration;
  clear(root);
  const stage = h('div', { class: 'pl-stage', id: 'pl-stage' });
  const viewport = h('div', { class: ['pl-viewport', rocket ? 'is-3d' : 'is-2d'], id: 'pl-viewport' });
  const hud = h('div', { class: 'pl-hud', role: 'group', 'aria-label': 'Readouts at the playback time' });
  const phaseTag = h('div', { class: 'pl-phase', 'aria-hidden': 'true' });
  const runBar = runs.length > 1 ? h('div', { class: 'pl-runs', role: 'radiogroup', 'aria-label': 'Run shown in the scene' },
    runs.map((r, i) => h('button', { type: 'button', role: 'radio', class: 'pl-run', 'aria-checked': String(i === pl.active), dataset: { run: String(i) }, onclick: () => setActive(i) },
      h('span', { class: 'pl-swatch', style: { background: r.colour } }), r.label))) : null;
  const cams = rocket ? h('div', { class: 'seg pl-cams', role: 'radiogroup', 'aria-label': 'Camera' },
    [['follow', 'Follow'], ['pad', 'From the pad'], ['wide', 'Whole descent']].map(([m, text]) => h('button', { type: 'button', role: 'radio', class: 'seg-btn', 'aria-checked': String(m === 'follow'), dataset: { cam: m },
      onclick: (e) => { for (const b of e.currentTarget.parentElement.children) b.setAttribute('aria-checked', String(b === e.currentTarget)); if (pl.scene && pl.scene.preset) pl.scene.preset(m); } }, text))) : null;
  const note = h('p', { class: 'pl-scene-note' }, rocket
    ? (runs.length > 1 ? 'Shown run: true trajectory (solid), the controller’s estimated position (dashed yellow) and the stage. Other runs: their true trajectories as coloured lines. ' : 'True trajectory (solid), the controller’s estimated position (dashed yellow) and the stage. ') + 'Sampled every 0.1 s and interpolated for display; the stage body is drawn for orientation, the model has no length.'
    : 'True paths and GPS samples, one sample per tick. Top view, x east, y north.');
  stage.append(...[viewport, phaseTag, hud, runBar, cams, note].filter(Boolean));

  const head = h('header', { class: 'pl-head' },
    h('button', { type: 'button', class: 'pl-back', onclick: () => navigate('missions') }, h('span', { 'aria-hidden': 'true' }, '←'), ' Missions'),
    h('div', { class: 'pl-title' },
      h('p', { class: 'eyebrow' }, `${DOMAIN_NAMES[exp.domain] || exp.domain} · ${exp.kicker}`),
      h('h1', null, exp.title)),
    h('span', { class: `grade grade-${grade.tone}`, title: grade.text }, grade.label),
    h('div', { class: 'pl-head-actions' },
      h('button', { type: 'button', class: 'btn btn-quiet', dataset: { action: 'analyse' }, title: 'Open the shown run with every channel, requirement and its provenance', onclick: () => navigate('run', { runId: pl.runs[pl.active].runId }) }, 'Analyse'),
      runs.length > 1 ? h('button', { type: 'button', class: 'btn btn-quiet', dataset: { action: 'compare' }, onclick: () => navigate('compare', { runIds: runs.map((r) => r.runId), demo: pl.demo }) }, 'Compare in detail') : null,
      h('button', { type: 'button', class: 'btn btn-quiet', dataset: { action: 'configure' }, title: 'Open the shown run as an editable request', onclick: () => { openRequest(pl.runs[pl.active].record.request); navigate('prepare'); } }, 'Change the conditions')));

  const side = h('aside', { class: 'pl-side', 'aria-label': 'Mission briefing and result' });
  const transport = buildTransport();
  root.append(h('div', { class: 'pl' }, head, h('div', { class: 'pl-body' }, stage, side), transport));
  pl.dom = { viewport, hud, phaseTag, side, runBar };
  pl.phases = runs.map((r) => phasesOf(r));
  pl.div = runs.map((r, i) => (i === 0 ? null : divergence(runs[0], r, rocket)));
  mountScene();
  renderSide();
  drawBand();
  pl.unsub = cursor.subscribe((t) => onTime(t));
  onTime(cursor.t);
}

function mountScene() {
  const { viewport } = pl.dom;
  if (pl.scene) { pl.scene.dispose(); pl.scene = null; }
  clear(viewport);
  const models = pl.runs.map((r) => r.model);
  const colours = pl.runs.map((r) => r.colour);
  try {
    if (pl.kind === 'rocket-3d') {
      pl.scene = mountCinema(viewport, models, pl.active, pl.cursor, colours);
      if (pl.scene.ok === false) viewport.classList.add('no-webgl');
    } else if (pl.kind === 'ground-2d') {
      pl.scene = models.length > 1 ? ground2d.compare(viewport, models, colours, pl.runs.map((r) => r.label), pl.cursor) : ground2d.mount(viewport, models[0], pl.cursor, { unit: pl.unit });
    } else {
      viewport.append(h('p', { class: 'pl-scene-note' }, 'This domain declares no scene; the result and the analysis are complete without one.'));
    }
  } catch (e) {
    logUiError(`player scene: ${e && e.stack ? e.stack : e}`);
    clear(viewport).append(h('p', { class: 'error-text' }, `The scene could not be drawn: ${e.message}`));
    pl.scene = null;
  }
}

function setActive(i) {
  if (!pl || i === pl.active) return;
  pl.active = i;
  if (pl.dom.runBar) for (const b of pl.dom.runBar.children) b.setAttribute('aria-checked', String(Number(b.dataset.run) === i));
  if (pl.kind === 'rocket-3d') mountScene();
  drawBand();
  onTime(pl.cursor.t);
}

function onTime(t) {
  if (!pl) return;
  const run = pl.runs[pl.active];
  const rocket = pl.kind === 'rocket-3d';
  const phases = pl.phases[pl.active];
  const ph = phases.find((p) => t >= p.t0 && t < p.t1) || phases[phases.length - 1];
  const end = t >= run.model.t1 - 1e-9;
  const td = run.record.scene && run.record.scene.touchdown;
  const met = run.record.outcome.status === 'success';
  const endText = td ? (met ? 'Touchdown' : 'Touchdown, requirements not met') : 'End of run';
  const phaseText = end ? endText : ph ? ph.label : '';
  const clock = pl.unit === 'tick' ? `tick ${Math.floor(t)}` : `T+${t.toFixed(1)} s`;
  const ended = end && t > run.model.t1 + 1e-9 ? (pl.unit === 'tick' ? `run ended at tick ${run.model.t1}` : `${td ? 'touched down' : 'ended'} at ${run.model.t1.toFixed(1)} s`) : null;
  pl.dom.phaseTag.replaceChildren(...[
    h('span', { class: 'pl-clock mono' }, clock),
    phaseText ? h('span', { class: ['pl-phase-name', `ph-${end ? (met ? 'end' : 'end-bad') : ph ? ph.kind : ''}`] }, phaseText) : null,
    ended ? h('span', { class: 'pl-ended small' }, `${run.label} ${ended}`) : null].filter(Boolean));
  pl.tr.range.setAttribute('aria-valuetext', `${timeText(t, pl.unit)}, ${phaseText || 'no phase'}`);
  pl.dom.hud.replaceChildren(
    h('p', { class: 'pl-hud-h' }, h('span', { class: 'pl-swatch', style: { background: run.colour } }), run.label, end && td ? h('span', { class: 'pl-hud-at' }, 'at contact') : null),
    h('dl', null, readouts(run, t, rocket).map(([k, v, u, kind, title]) => h('div', { class: 'pl-hud-row', title },
      h('dt', null, h('abbr', { class: `kind kind-${kind}`, title: KIND_WORD[kind] }, kind), k),
      h('dd', { class: 'mono' }, v === null ? '—' : typeof v === 'string' ? v : `${hudNum(v)}${u ? ` ${u}` : ''}`)))),
    h('p', { class: 'pl-hud-key' }, 'T true state · E controller estimate · O sensor · D derived'));
  updateTransport(t);
  if (!pl.revealed && t >= pl.cursor.t1 - 1e-9) reveal();
}

/** Fixed decimals for readouts, so digits do not jump while playing. */
function hudNum(v) {
  const a = Math.abs(v);
  if (a < 0.005) return '0.00';
  if (a >= 1000) return v.toFixed(0);
  if (a >= 100) return v.toFixed(1);
  return v.toFixed(2);
}

// ----------------------------------------------------------------------------- transport

function buildTransport() {
  const c = pl.cursor;
  const play = h('button', { type: 'button', class: 'pl-play', 'aria-label': 'Play', title: 'Play or pause (Space)', onclick: () => { if (c.t >= c.t1) c.set(c.t0); c.toggle(); } }, icon('play'));
  const restart = h('button', { type: 'button', class: 'pl-tbtn', 'aria-label': 'Restart', title: 'Restart (Home)', onclick: () => { c.set(c.t0); c.play(); } }, icon('replay'));
  const range = h('input', { type: 'range', class: 'pl-range', min: String(c.t0), max: String(c.t1), step: 'any', value: String(c.t0), 'aria-label': 'Mission time', oninput: (e) => { c.pause(); c.set(Number(e.target.value)); } });
  const band = h('div', { class: 'pl-band', 'aria-hidden': 'true' });
  const marks = h('div', { class: 'pl-marks' });
  const time = h('span', { class: 'pl-time mono' });
  const speed = h('select', { class: 'select select-sm', 'aria-label': 'Playback speed', onchange: (e) => { c.speed = Number(e.target.value); setPref('missionSpeed', c.speed); } },
    SPEEDS.map((x) => h('option', { value: String(x), selected: x === c.speed }, `${x}×`)));
  const skip = h('button', { type: 'button', class: 'btn btn-quiet pl-reveal', onclick: () => revealNow() }, 'Skip to the result');
  pl.tr = { play, range, band, marks, time };
  pl.unplay = c.onPlayState((p) => { play.replaceChildren(icon(p ? 'pause' : 'play')); play.setAttribute('aria-label', p ? 'Pause' : 'Play'); });
  return h('section', { class: 'pl-transport', 'aria-label': 'Playback' },
    h('div', { class: 'pl-tcontrols' }, play, restart, time),
    h('div', { class: 'pl-track' }, band, marks, range),
    h('div', { class: 'pl-tend' }, h('label', { class: 'small dim' }, 'Speed ', speed), skip),
    h('p', { class: 'pl-legend' },
      pl.kind === 'rocket-3d' ? h('span', null, h('i', { class: 'lg-powered' }), 'engine on') : null,
      h('span', null, h('i', { class: 'lg-onset' }), 'injected fault starts'),
      h('span', null, h('i', { class: 'lg-detect' }), 'controller detection'),
      h('span', null, h('i', { class: 'lg-violation' }), 'requirement or rule violated'),
      pl.runs.length > 1 ? h('span', null, h('i', { class: 'lg-diverge' }), 'runs part') : null));
}

function drawBand() {
  const { band, marks } = pl.tr;
  const c = pl.cursor;
  const span = c.t1 - c.t0 || 1;
  const pos = (t) => `${(100 * (t - c.t0)) / span}%`;
  clear(band);
  for (const p of pl.phases[pl.active]) band.append(h('span', { class: `pl-seg ${p.kind}`, style: { left: pos(p.t0), width: `${(100 * Math.max(p.t1 - p.t0, span / 400)) / span}%` }, title: `${p.label} (derived from the recorded engine or mode channel)` }));
  clear(marks);
  const run = pl.runs[pl.active];
  const mark = (cls, t, label) => marks.append(h('button', { type: 'button', class: `pl-mark ${cls}`, style: { left: pos(t) }, 'aria-label': label, title: label, onclick: () => { c.pause(); c.set(t); } }));
  const seen = new Set();
  for (const e of run.model.events || []) {
    if (!['fault', 'detection', 'violation', 'warning'].includes(e.severity) || !Number.isFinite(e.t)) continue;
    const key = `${e.severity}@${e.t}`;
    if (seen.has(key)) continue;
    seen.add(key);
    mark(`sev-${e.severity}`, e.t, `${timeText(e.t, pl.unit)}: ${prose(e.label)}`);
  }
  for (const f of run.record.request.faults || []) mark('sev-onset', f.start, `${timeText(f.start, pl.unit)}: injected fault ${f.kind} starts`);
  for (let i = 1; i < pl.div.length; i++) {
    const d = pl.div[i];
    if (d && d.t !== null) mark('sev-diverge', d.t, `${timeText(d.t, pl.unit)}: ${pl.runs[i].label} departs from ${pl.runs[0].label} by more than ${d.tol} ${d.unit} (derived)`);
  }
}

function updateTransport(t) {
  const { range, time } = pl.tr;
  if (Number(range.value) !== t) range.value = String(t);
  time.textContent = pl.unit === 'tick' ? `tick ${Math.floor(t)} / ${pl.cursor.t1}` : `${t.toFixed(1)} / ${pl.cursor.t1.toFixed(1)} s`;
}

export function playerKey(e) {
  if (!pl) return false;
  const c = pl.cursor;
  const step = pl.unit === 'tick' ? 1 : 0.1;
  if (e.key === ' ' || e.code === 'Space') { if (c.t >= c.t1) c.set(c.t0); c.toggle(); return true; }
  if (e.key === 'ArrowRight') { c.pause(); c.set(c.t + step * (e.shiftKey ? 10 : 1)); return true; }
  if (e.key === 'ArrowLeft') { c.pause(); c.set(c.t - step * (e.shiftKey ? 10 : 1)); return true; }
  if (e.key === 'Home') { c.pause(); c.set(c.t0); return true; }
  if (e.key === 'End') { c.pause(); c.set(c.t1); return true; }
  return false;
}

export function rethemePlayer() {
  if (pl && pl.scene && pl.scene.redraw) pl.scene.redraw();
}

// ----------------------------------------------------------------------------- briefing and result

function revealNow() {
  if (!pl) return;
  pl.cursor.pause();
  pl.cursor.set(pl.cursor.t1);
  reveal();
}

function reveal() {
  if (!pl || pl.revealed) return;
  pl.revealed = true;
  renderSide();
}

function tone(status) {
  if (status === 'success' || status === 'safe' || status === 'pass') return 'ok';
  if (status === 'unsafe') return 'bad';
  if (status === 'partial' || status === 'failure' || status === 'fail') return 'warn';
  return 'neutral';
}

function verdictChip(text, status, sub) {
  return h('span', { class: `vchip v-${tone(status)}` }, h('span', { class: 'vchip-k' }, sub), text);
}

function runResult(run) {
  const rec = run.record;
  const reqs = rec.requirements || [];
  const failed = reqs.filter((q) => q.status === 'fail');
  const missionReqs = reqs.filter((q) => q.category !== 'invariant');
  const invariants = reqs.filter((q) => q.category === 'invariant');
  const brokenInv = invariants.filter((q) => q.status === 'fail');
  const metFail = missionReqs.filter((q) => q.status === 'fail');
  const metrics = pl.kind === 'rocket-3d' ? ROCKET_METRICS.map((id) => rec.metrics.find((m) => m.id === id)).filter(Boolean) : [];
  const missionText = metFail.length ? `${metFail.length} of ${missionReqs.length} requirements failed` : `all ${missionReqs.length} requirements met`;
  const safetyText = brokenInv.length ? `${brokenInv.length} of ${invariants.length} safety rules broken` : `no safety rule broken (${invariants.length} checked)`;
  return h('div', { class: 'pl-run-result', dataset: { outcome: rec.outcome.code, safety: rec.safety.status } },
    h('p', { class: 'pl-run-name' }, h('span', { class: 'pl-swatch', style: { background: run.colour } }), run.label),
    h('p', { class: 'pl-run-head' }, rec.outcome.label),
    h('div', { class: 'pl-verdicts' },
      verdictChip(missionText, metFail.length ? 'fail' : 'pass', 'Mission'),
      verdictChip(safetyText, rec.safety.status, 'Safety')),
    metrics.length ? h('dl', { class: 'pl-metrics' }, metrics.map((m) => h('div', null, h('dt', null, m.label), h('dd', { class: 'mono' }, m.value === null ? '—' : `${hudNum(m.value)} ${m.unit}`)))) : null,
    failed.length ? h('ul', { class: 'pl-failed' }, failed.map((q) => h('li', null,
      h('button', { type: 'button', class: 'link', title: 'Move the playback to the decisive instant', onclick: () => { if (Number.isFinite(q.t)) { pl.cursor.pause(); pl.cursor.set(q.t); } } }, q.label),
      h('span', { class: 'small dim' }, ` ${q.category === 'invariant' ? 'safety invariant' : 'requirement'}: expected ${q.expected}, observed ${q.observed}`)))) : h('p', { class: 'small ok-text' }, 'Every requirement and safety invariant met.'));
}

function changeSummary() {
  if (pl.runs.length < 2) return null;
  const rows = [];
  for (let i = 1; i < pl.runs.length; i++) {
    const d = pl.div[i];
    if (!d) continue;
    rows.push(h('li', null, d.t === null
      ? `${pl.runs[i].label} stays within ${d.tol} ${d.unit} of ${pl.runs[0].label} for the whole run.`
      : `${pl.runs[i].label} departs from ${pl.runs[0].label} by more than ${d.tol} ${d.unit} at ${timeText(d.t, pl.unit)}.`,
    d.t !== null ? ' ' : null,
    d.t !== null ? h('button', { type: 'button', class: 'link small', onclick: () => { pl.cursor.pause(); pl.cursor.set(d.t); } }, 'Go there') : null));
  }
  return rows.length ? h('section', { class: 'pl-card' }, h('h2', null, 'Where the runs part'), h('ul', { class: 'pl-list' }, rows),
    h('p', { class: 'pl-fine' }, 'Derived from the recorded true positions, sample by sample. It marks where the motion differs, not why.')) : null;
}

function renderSide() {
  const { exp, demo } = pl;
  const side = clear(pl.dom.side);
  side.append(
    h('section', { class: 'pl-card pl-brief' },
      h('h2', null, 'Objective'), h('p', null, exp.objective),
      h('h3', null, 'Watch for'), h('ul', { class: 'pl-list' }, exp.watch.map((w) => h('li', null, w)))));
  if (!pl.revealed) {
    side.append(h('section', { class: 'pl-card pl-pending' }, h('h2', null, 'Result'), h('p', { class: 'small dim' }, 'Shown when the playback reaches the end of the run.'),
      h('button', { type: 'button', class: 'btn', dataset: { action: 'reveal' }, onclick: () => revealNow() }, 'Show the result now')));
  } else {
    const reqOnly = pl.runs.some((r) => r.record.safety.status === 'safe' && (r.record.requirements || []).some((q) => q.status === 'fail'));
    side.append(h('section', { class: 'pl-card pl-result', 'aria-live': 'polite' }, h('h2', null, 'Result'), pl.runs.map((r) => runResult(r)),
      reqOnly ? h('p', { class: 'pl-fine' }, 'Mission requirements judge the landing or the goal; safety rules are judged on the true state throughout the run. A hard or off-target landing fails a requirement without breaking a safety rule.') : null));
    const parted = changeSummary();
    if (parted) side.append(parted);
    side.append(h('section', { class: 'pl-card pl-why' }, h('h2', null, 'Why it happened'), h('p', null, prose(demo.narrative)),
      h('details', { class: 'pl-more' }, h('summary', null, 'What the simulator reported'),
        pl.runs.map((r) => h('div', null, h('p', { class: 'small' }, h('b', null, `${r.label}. `), prose(r.record.outcome.explanation)), h('p', { class: 'small dim' }, prose(r.record.safety.explanation)))))));
  }
  const claimHost = h('section', { class: 'pl-card pl-claim' });
  side.append(claimHost);
  renderClaim(claimHost);
  const grade = GRADES[exp.grade] || GRADES.demonstration;
  side.append(h('section', { class: 'pl-card pl-grade' }, h('h2', null, 'How far this goes'), h('p', { class: 'small' }, h('b', null, `${grade.label}. `), grade.text),
    h('p', { class: 'small dim' }, prose(pl.runs[0].record.model_validity))));
  if (exp.next) {
    const n = experienceById(exp.next);
    if (n) side.append(h('button', { type: 'button', class: 'pl-next', dataset: { next: n.id }, onclick: () => navigate('mission', { experienceId: n.id }) }, h('span', { class: 'eyebrow' }, 'Next mission'), h('span', { class: 'pl-next-t' }, n.title), h('span', { class: 'small dim' }, n.summary)));
  }
}

async function renderClaim(host) {
  const { exp } = pl;
  if (!exp.claim) {
    host.append(h('h2', null, 'Challenge a claim'), h('p', { class: 'small' }, 'This mission is a demonstration with no formal claim attached. Missions marked “Challenge a claim” in the library carry a bounded safety claim that the platform can try to break.'),
      h('button', { type: 'button', class: 'link small', onclick: () => navigate('missions', { category: 'claims' }) }, 'Show those missions'));
    return;
  }
  host.append(h('p', { class: 'dim small' }, 'Checking the claim with the investigation engine…'));
  const st = await claimStatus(exp.claim);
  if (!pl || pl.exp !== exp || !host.isConnected) return;
  clear(host);
  host.append(h('h2', null, 'Challenge this claim'));
  if (!st.available) {
    host.append(h('p', { class: 'small' }, `This mission rests on the claim “${exp.claim}”, but it cannot be challenged here: `, h('span', { class: 'warn-text' }, st.reason)));
    return;
  }
  host.append(
    h('p', { class: 'pl-claim-s' }, `“${st.claim.statement}”`),
    h('p', { class: 'small' }, 'Challenging means letting the platform search the claim’s declared conditions for runs where it stops holding, reproduce them on fresh seeds, test what causes the failure and whether a fix works, then recompute every verdict from scratch.'),
    st.latest
      ? h('p', { class: 'small' }, 'Latest challenge in this library: ', h('span', { class: `dl-chip ${st.latest.recomputed || st.latest.failed ? st.latest.tone : 'neutral'}` }, st.latest.word), ' ',
        st.latest.failed ? h('span', { class: 'bad-text' }, 'its recomputation failed, so its verdicts are withdrawn') : st.latest.recomputed ? h('span', { class: 'ok-text' }, 'recomputed, every check passed') : st.latest.stale ? h('span', { class: 'warn-text' }, 'changed since it was recomputed') : h('span', { class: 'dim' }, 'not recomputed yet'))
      : h('p', { class: 'small dim' }, 'Not challenged on this machine yet.'),
    h('button', { type: 'button', class: 'btn btn-primary', dataset: { action: 'challenge' }, onclick: () => navigate('discover', { claimId: exp.claim }) }, 'Challenge this claim'));
}
