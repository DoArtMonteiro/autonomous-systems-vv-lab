// Generic reading of a vv-run.v1 record. Nothing here knows a domain: channels, timebases, events and
// requirements are taken from the record itself (never from the catalog, which may list fewer).

import { words, num } from './dom.js';

export const KINDS = ['truth', 'observation', 'estimate', 'uncertainty', 'command', 'metric', 'limit'];
export const KIND_LETTER = { truth: 'T', observation: 'O', estimate: 'E', uncertainty: 'U', command: 'C', metric: 'M', limit: 'L' };
export const SOURCES = ['fault', 'controller', 'verifier', 'truth'];
export const CATEGORY_TITLE = { requirement: 'Mission requirements', invariant: 'Safety rules', declaration: 'Controller declarations, judged on truth' };

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

/** A rule that held is `held`: a neutral tone of its own, never the green `pass` of a requirement that was met. */
export function verdictOfSafety(status) {
  return status === 'safe' ? 'held' : status === 'unsafe' ? 'unsafe' : 'neutral';
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
    // Every non-default parameter and every injected fault; never "no injected fault" while a noise or a limit is set.
    faults: conditionsName(req, catalog),
  };
}

const paramNumber = (v) => (typeof v === 'number' && Number.isFinite(v) ? String(Number(v.toPrecision(6))) : String(v));

/** The conditions of a run that differ from the catalog defaults: [{key, label, text}], parameters first, then faults. */
export function conditionParts(req, catalog) {
  const specs = new Map(((catalog && catalog.parameters) || []).map((p) => [p.id, p]));
  const parts = [];
  for (const [id, v] of Object.entries(req.parameters || {})) {
    const spec = specs.get(id);
    if (spec && v === spec.default) continue;
    parts.push({ key: `p:${id}`, label: spec ? spec.label : words(id), text: `${spec ? spec.label : words(id)} ${paramNumber(v)}${spec && spec.unit ? ` ${spec.unit}` : ''}` });
  }
  for (const f of req.faults || []) parts.push({ key: `f:${JSON.stringify(f)}`, label: faultText(f, catalog), text: faultText(f, catalog) });
  return parts;
}

/** The one display name of a run's conditions, from the shared parts: "GPS noise 1 mm · Arrival radius 250 mm", or "default conditions". */
export function conditionsName(req, catalog) {
  const parts = conditionParts(req, catalog);
  return parts.length ? parts.map((p) => p.text).join(' · ') : 'default conditions';
}

/** What the runs share and what tells them apart: {shared: [text], differ: [label], text}. */
export function conditionsShared(requests, catalog) {
  const lists = requests.map((r) => conditionParts(r, catalog));
  const keys = [...new Set(lists.flatMap((l) => l.map((p) => p.key)))];
  const shared = [];
  const differ = [];
  for (const k of keys) {
    const have = lists.map((l) => l.find((p) => p.key === k));
    if (have.every(Boolean) && have.every((x) => x.text === have[0].text)) { shared.push(have[0].text); continue; }
    // A parameter set in some runs and left at its default in others differs by that parameter.
    const label = (have.find(Boolean) || {}).label;
    if (label && !differ.includes(label)) differ.push(label);
  }
  // The same parameter with two values is one difference, named once.
  const byParam = (arr) => arr.map((t) => t);
  const seeds = new Set(requests.map((r) => r.seed));
  const controllers = new Set(requests.map((r) => r.controller));
  if (controllers.size > 1) differ.push('controller');
  if (seeds.size > 1) differ.push('seed');
  const n = requests.length;
  const who = n === 2 ? 'Both runs' : `All ${n} runs`;
  const text = `${who}: ${shared.length ? shared.join(' · ') : 'no non-default condition in common'}; ${differ.length ? `they differ only in ${byParam(differ).join(', ')}` : 'nothing in their conditions differs'}`;
  return { shared, differ, text };
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
 * Parameters are compared one by one against the catalogue default, so a stored request that lists
 * every default and one that lists only the changed value are read as the same configuration, and
 * only the parameters that really differ appear in the label.
 */
export function distinguishingLabels(requests, catalog) {
  const specs = new Map(((catalog && catalog.parameters) || []).map((p) => [p.id, p]));
  const paramValue = (r, id) => {
    const v = r.parameters ? r.parameters[id] : undefined;
    if (v !== undefined && v !== null) return v;
    const spec = specs.get(id);
    return spec ? spec.default : undefined;
  };
  const paramIds = [...new Set(requests.flatMap((r) => Object.keys(r.parameters || {})))];
  const differingParams = paramIds.filter((id) => new Set(requests.map((r) => String(paramValue(r, id)))).size > 1);
  const val = (r, k) => (k === 'faults' ? JSON.stringify(r.faults) : String(r[k]));
  const differing = ['scenario', 'controller', 'seed', 'faults'].filter((k) => new Set(requests.map((r) => val(r, k))).size > 1);
  if (differingParams.length) differing.push('parameters');
  const labels = requests.map((r, i) => {
    const t = requestText(r, catalog);
    const parts = [];
    for (const k of differing.length ? differing : ['controller']) {
      if (k === 'scenario') parts.push(t.scenario);
      else if (k === 'controller') parts.push(t.controller);
      else if (k === 'seed') parts.push(`seed ${r.seed}`);
      else if (k === 'faults') parts.push(r.faults.length ? r.faults.map((f) => faultText(f, catalog)).join(' + ') : 'no fault');
      else if (k === 'parameters') {
        for (const id of differingParams) {
          const spec = specs.get(id);
          const v = paramValue(r, id);
          const isDefault = spec && v === spec.default;
          parts.push(`${spec ? spec.label : words(id)} ${num(v)}${spec && spec.unit ? ` ${spec.unit}` : ''}${isDefault ? ' (default)' : ''}`);
        }
      }
    }
    return parts.join(' · ') || `run ${i + 1}`;
  });
  // Last resort: the requests differ in something not listed above; never show two equal labels.
  return labels.map((l, i) => (labels.indexOf(l) !== labels.lastIndexOf(l) ? `${l} (run ${i + 1})` : l));
}

/**
 * The label a run is shown by when its stored label is only "Experiment from <id>": the parameters that
 * differ from the catalog defaults, as the player and the Lab name a new run, with the run it came from.
 * A stored label that says something else is kept as it is; nothing stored is rewritten.
 */
export function displayRunLabel(record, catalog, stored, tags = []) {
  if (stored && !/^Experiment from /.test(stored)) return stored;
  const specs = new Map(((catalog && catalog.parameters) || []).map((p) => [p.id, p]));
  const params = record.request.parameters || {};
  const changed = Object.entries(params).some(([k, v]) => specs.has(k) && v !== specs.get(k).default);
  if (!changed) return stored || null;
  const label = distinguishingLabels([{ ...record.request, parameters: {} }, record.request], catalog)[1];
  const from = (tags.find((t) => t.startsWith('from:')) || '').slice(5, 15);
  return from ? `${label} (from ${from})` : label;
}

/** One colour per run in a comparison: Okabe-Ito order, safe for the common colour-vision deficiencies. */
// Amber is the colour of a failed requirement, so the second run is not amber.
export const RUN_COLOURS = ['#56B4E9', '#CC79A7', '#009E73', '#0072B2', '#D55E00', '#999999', '#F0E442', '#E69F00'];

/** One line dash per run (cycled), so compared runs differ by more than colour. */
const RUN_DASH_TABLE = [[], [6, 3], [2, 3], [8, 3, 2, 3]];
export function runDash(i) {
  return RUN_DASH_TABLE[i % RUN_DASH_TABLE.length];
}

/** CSS background drawing a run's colour with its dash pattern, for legend swatches. */
export function runSwatch(colour, dash) {
  if (!dash.length) return colour;
  let x = 0;
  const stops = [];
  dash.forEach((d, k) => { stops.push(`${k % 2 ? 'transparent' : colour} ${x}px ${x + d}px`); x += d; });
  return `repeating-linear-gradient(90deg, ${stops.join(', ')})`;
}
