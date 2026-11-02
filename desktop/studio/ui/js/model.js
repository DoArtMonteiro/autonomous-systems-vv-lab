// Generic reading of a vv-run.v1 record. Nothing here knows a domain: channels, timebases, events and
// requirements are taken from the record itself (never from the catalog, which may list fewer).

import { words, num } from './dom.js';

export const KINDS = ['truth', 'observation', 'estimate', 'uncertainty', 'command', 'metric', 'limit'];
export const KIND_LETTER = { truth: 'T', observation: 'O', estimate: 'E', uncertainty: 'U', command: 'C', metric: 'M', limit: 'L' };
export const SOURCES = ['fault', 'controller', 'verifier', 'truth'];
export const CATEGORY_TITLE = { requirement: 'Mission requirements', invariant: 'Safety invariants', declaration: 'Controller declarations, judged on truth' };

/** Wraps a record with lookups the views need. Computed once per record. */
export function modelOf(record) {
  if (record.__model) return record.__model;
  const channels = record.channels || [];
  const byId = new Map(channels.map((c) => [c.id, c]));
  const timebases = record.timebases || {};
  let t0 = Infinity;
  let t1 = -Infinity;
  for (const tb of Object.values(timebases)) {
    if (tb.length) {
      t0 = Math.min(t0, tb[0]);
      t1 = Math.max(t1, tb[tb.length - 1]);
    }
  }
  for (const e of record.events || []) {
    if (Number.isFinite(e.t)) {
      t0 = Math.min(t0, e.t);
      t1 = Math.max(t1, e.t);
    }
  }
  if (!Number.isFinite(t0)) { t0 = 0; t1 = 1; }
  if (t1 <= t0) t1 = t0 + 1;
  // Primary timebase: the one the scene names, else the one with the most samples.
  let primary = record.scene && record.scene.channels && record.scene.channels.timebase;
  if (!primary || !timebases[primary]) {
    primary = Object.keys(timebases).sort((a, b) => timebases[b].length - timebases[a].length)[0] || null;
  }
  const events = [...(record.events || [])].map((e, i) => ({ ...e, index: i })).sort((a, b) => a.t - b.t || a.index - b.index);
  const m = {
    record,
    channels,
    byId,
    timebases,
    t0,
    t1,
    primary,
    events,
    bands: bandPairs(channels),
    times: (c) => timebases[c.timebase] || [],
  };
  Object.defineProperty(record, '__model', { value: m, enumerable: false });
  return m;
}

/**
 * Pairs an uncertainty channel `sigma_<s>` (same unit and timebase) with
 * - the estimate channel `<prefix>_<s>`: band estimate ± kσ;
 * - the estimation-error metric `err_<s>`: band 0 ± kσ, the envelope the error should stay inside.
 * Returns channel id -> {sigma, around: 'value' | 'zero'}. Unpaired uncertainty stays a plain trace.
 */
function bandPairs(channels) {
  const pairs = new Map();
  for (const u of channels.filter((c) => c.kind === 'uncertainty')) {
    const m = /^sigma_(.+)$/.exec(u.id);
    if (!m) continue;
    const same = (c) => c.unit === u.unit && c.timebase === u.timebase;
    const est = channels.filter((c) => c.kind === 'estimate' && same(c) && c.id.endsWith(`_${m[1]}`) && c.id.split('_').length === 2);
    if (est.length === 1) pairs.set(est[0].id, { sigma: u.id, around: 'value' });
    const err = channels.find((c) => c.kind === 'metric' && same(c) && c.id === `err_${m[1]}`);
    if (err) pairs.set(err.id, { sigma: u.id, around: 'zero' });
  }
  return pairs;
}

/** Band multiplier declared by the record scene (`uncertainty_band_k`), else 1. */
export function bandK(record) {
  const k = record.scene && record.scene.uncertainty_band_k;
  return typeof k === 'number' && Number.isFinite(k) && k > 0 ? { k, declared: true } : { k: 1, declared: false };
}

export function verdictOfOutcome(status) {
  return { success: 'pass', partial: 'partial', failure: 'fail' }[status] || 'neutral';
}

export function verdictOfSafety(status) {
  return status === 'safe' ? 'pass' : status === 'unsafe' ? 'unsafe' : 'neutral';
}

export function verdictOfRequirement(r) {
  if (r.status === 'pass') return 'pass';
  if (r.status === 'fail') return r.category === 'invariant' ? 'unsafe' : 'fail';
  return 'neutral';
}

export const STATUS_TEXT = { pass: 'Pass', fail: 'Fail', not_evaluated: 'Not evaluated' };

/** Short descriptor of a request: scenario · controller · seed · faults. */
export function requestText(req, catalog) {
  const sc = catalog && catalog.scenarios.find((s) => s.id === req.scenario);
  const ct = catalog && catalog.controllers.find((c) => c.id === req.controller);
  return {
    scenario: sc ? sc.label : req.scenario,
    controller: ct ? ct.label : req.controller,
    seed: String(req.seed),
    faults: req.faults.length ? req.faults.map((f) => faultText(f, catalog)).join(' + ') : 'no injected fault',
  };
}

export function faultText(f, catalog) {
  const spec = catalog && catalog.faults.find((x) => x.kind === f.kind);
  const unit = catalog ? catalog.time.unit : '';
  const label = spec ? spec.label : words(f.kind);
  const mag = f.magnitude !== null && f.magnitude !== undefined ? ` ${num(f.magnitude)}${spec && spec.magnitude && spec.magnitude.unit ? ` ${spec.magnitude.unit}` : ''}` : '';
  return `${label}${mag} [${num(f.start)}, ${num(f.end)}] ${unit}`;
}

/**
 * Labels for a set of requests that name only what differs between them (controller, scenario,
 * seed, faults, parameters), so two runs that differ by one parameter are still told apart.
 */
export function distinguishingLabels(requests, catalog) {
  const keys = ['scenario', 'controller', 'seed', 'faults', 'parameters'];
  const val = (r, k) => (k === 'faults' ? JSON.stringify(r.faults) : k === 'parameters' ? JSON.stringify(r.parameters) : String(r[k]));
  const differing = keys.filter((k) => new Set(requests.map((r) => val(r, k))).size > 1);
  return requests.map((r, i) => {
    const t = requestText(r, catalog);
    const parts = [];
    for (const k of differing.length ? differing : ['controller']) {
      if (k === 'scenario') parts.push(t.scenario);
      else if (k === 'controller') parts.push(t.controller);
      else if (k === 'seed') parts.push(`seed ${r.seed}`);
      else if (k === 'faults') parts.push(r.faults.length ? r.faults.map((f) => words(f.kind)).join(' + ') : 'no fault');
      else if (k === 'parameters') {
        const ps = Object.entries(r.parameters);
        parts.push(ps.length ? ps.map(([p, v]) => `${p} = ${num(v)}`).join(', ') : 'default parameters');
      }
    }
    return parts.join(' · ') || `run ${i + 1}`;
  });
}

/** One colour per run in a comparison: Okabe-Ito order, safe for the common colour-vision deficiencies. */
export const RUN_COLOURS = ['#56B4E9', '#E69F00', '#CC79A7', '#009E73', '#0072B2', '#D55E00', '#999999', '#F0E442'];
