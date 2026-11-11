// Derived views of a replay shared by the mission player, the geospatial view and the Flight console
// (M16). Everything here reads the run records; nothing runs or changes a simulation. Phases and the
// divergence instant are derived from recorded channels and are labelled as derived wherever shown.

import { lowerIndex } from './dom.js';

export const ENGINE = ['Engine off', 'Engine on', 'Engine cut', 'Flameout'];
export const ROCKET_METRICS = ['touchdown_vertical_speed', 'touchdown_horizontal_speed', 'touchdown_pad_distance'];
export const KIND_WORD = { T: 'true state', E: 'controller estimate', O: 'sensor observation', D: 'derived' };

/** Phase segments of a run from its recorded channels (derived, not a simulator output). */
export function phasesOf(run) {
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
export function divergence(a, b, rocket) {
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

export function value(run, id, t) {
  const c = run.model.byId.get(id);
  if (!c) return null;
  const times = run.model.timebases[c.timebase] || [];
  const i = lowerIndex(times, t);
  if (i < 0) return null;
  const v = c.values[i];
  return v === undefined ? null : v;
}

export function metricValue(run, id) {
  const m = (run.record.metrics || []).find((x) => x.id === id);
  return m && Number.isFinite(m.value) ? m.value : null;
}

export function readouts(run, t, rocket) {
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
        ['Descent rate', metricValue(run, 'touchdown_vertical_speed'), 'm/s', 'D', 'Vertical speed at the contact instant, computed by the verifier from the true state'],
        ['Horizontal speed', metricValue(run, 'touchdown_horizontal_speed'), 'm/s', 'D', 'Horizontal speed at the contact instant, computed by the verifier from the true state'],
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

/** Fixed decimals for readouts, so digits do not jump while playing. */
export function hudNum(v) {
  const a = Math.abs(v);
  if (a < 0.005) return '0.00';
  if (a >= 1000) return v.toFixed(0);
  if (a >= 100) return v.toFixed(1);
  return v.toFixed(2);
}


// ----------------------------------------------------------------------------- Flight console

/** Origin tag of a channel, read from the kind the record declares (never assumed). */
export const KIND_TAG = { truth: 'T', observation: 'O', estimate: 'E', command: 'C', metric: 'D', limit: 'L', uncertainty: 'U' };
export const TAG_WORD = { T: 'true state', O: 'sensor observation', E: 'controller estimate', C: 'controller command', D: 'derived', L: 'declared limit', U: 'uncertainty', G: 'geographic placement, derived from the environment pack', '?': 'kind not recorded' };

function row(run, id, t, label, opts = {}) {
  const c = run.model.byId.get(id);
  if (!c) return null;
  let v = value(run, id, t);
  if (v !== null && opts.map) v = opts.map(v);
  const tag = KIND_TAG[c.kind] || '?';
  const note = opts.note ? ` · ${opts.note}` : '';
  return { id, label, value: v, unit: opts.unit !== undefined ? opts.unit : c.unit, tag, digits: opts.digits, title: `${c.label || id} · channel ${id} · ${TAG_WORD[tag]}${note}` };
}

/**
 * Telemetry groups for a run at time t, specific to its domain. Every row is one recorded channel
 * (or a value derived from the geographic placement, tagged G), with the origin tag of the channel.
 * `geo` is {track} when the geospatial renderer is active.
 */
export function telemetry(run, t, rocket, geo) {
  const r = (id, label, opts) => row(run, id, t, label, opts);
  const groups = [];
  if (rocket) {
    const contact = t >= run.model.t1 - 1e-9 && metricValue(run, 'touchdown_vertical_speed') !== null;
    // At contact the speeds are the verifier's values at the contact instant (derived from the
    // true state), not the last 0.1 s sample.
    const atContact = (id, label) => ({ id, label, value: metricValue(run, id), unit: 'm/s', tag: 'D', title: `${label} at the contact instant, computed by the verifier from the true state` });
    groups.push({ id: 'motion', title: 'Flight', rows: [
      contact ? { id: 'altitude', label: 'Altitude', value: 0, unit: 'm', tag: 'T', title: 'Contact: the nozzle exit plane reached the ground' } : r('altitude', 'Altitude', { note: 'nozzle exit plane above the flat ground of the model' }),
      contact ? atContact('touchdown_vertical_speed', 'Descent rate') : r('vel_z', 'Descent rate', { map: (v) => -v, note: 'positive downward' }),
      contact ? atContact('touchdown_horizontal_speed', 'Horizontal speed') : r('vel_h', 'Horizontal speed'),
      r('tilt_deg', 'Tilt', { unit: '°' }),
      r('pad_distance', 'From pad centre'),
    ] });
    groups.push({ id: 'propulsion', title: 'Propulsion', rows: [
      r('engine_state', 'Engine', { map: (v) => ENGINE[v] || `state ${v}`, unit: '' }),
      r('act_throttle', 'Throttle applied', { map: (v) => 100 * v, unit: '%' }),
      r('cmd_throttle', 'Throttle commanded', { map: (v) => 100 * v, unit: '%' }),
      r('thrust_n', 'Thrust', { map: (v) => v / 1000, unit: 'kN' }),
      r('propellant_kg', 'Propellant'),
    ] });
    groups.push({ id: 'navigation', title: 'Navigation', rows: [
      r('est_z', 'Believed height of CoM', { note: 'controller estimate of the centre of mass' }),
      r('pos_z', 'True height of CoM'),
      r('err_z', 'Altitude error', { note: 'estimate minus truth' }),
      r('err_h', 'Horizontal error', { note: 'estimate minus truth, horizontal norm' }),
    ] });
    groups.push({ id: 'sensors', title: 'Sensors', rows: [
      r('obs_altimeter', 'Radar altimeter', { note: 'empty when no measurement arrived' }),
      r('altimeter_rejected', 'Altimeter', { map: (v) => (v === 1 ? 'rejected' : 'in use'), unit: '' }),
      r('obs_gnss_z', 'GNSS height', { note: 'empty during an outage' }),
      r('active_faults', 'Injected faults active', { unit: '' }),
    ] });
    if (geo && geo.track) {
      const tb = run.model.timebases[geo.track.timebase] || [];
      const i = lowerIndex(tb, t);
      const p = i >= 0 && geo.track.nozzle ? geo.track.nozzle.points[i] : null;
      const c = i >= 0 ? geo.track.truth.points[i] : null;
      groups.push({ id: 'geo', title: 'Geographic placement', note: 'Derived for display from the pack origin by vv-geo; not simulated.', rows: [
        c ? { id: 'lat', label: 'Latitude', value: c.lat_deg, unit: '°', tag: 'G', digits: 6, title: 'WGS84 latitude of the true centre of mass' } : null,
        c ? { id: 'lon', label: 'Longitude', value: c.lon_deg, unit: '°', tag: 'G', digits: 6, title: 'WGS84 longitude of the true centre of mass' } : null,
        c ? { id: 'msl', label: 'Above sea level', value: c.h_msl_m, unit: 'm', tag: 'G', title: 'Ellipsoidal height minus the EGM2008 undulation at the origin' } : null,
        p && p.above_terrain_m !== null ? { id: 'agl', label: 'Nozzle above terrain', value: p.above_terrain_m, unit: 'm', tag: 'G', title: 'Nozzle plane above the DEM surface under it. The simulation does not use this terrain.' } : null,
      ] });
    }
  } else {
    const fb = value(run, 'fallback', t);
    groups.push({ id: 'motion', title: 'Vehicle', rows: [
      r('truth_x_mm', 'East'), r('truth_y_mm', 'North'), r('moved_mm', 'Moved this tick'), r('goal_distance_mm', 'To goal', { note: 'Manhattan distance' }),
    ] });
    groups.push({ id: 'control', title: 'Control', rows: [
      r('command_mm', 'Command'),
      run.model.byId.get('fallback') ? { id: 'fallback', label: 'Mode', value: fb === null ? null : fb === 1 ? 'fallback' : 'normal', unit: '', tag: 'D', title: 'Safety fallback of the controller (derived channel fallback)' } : null,
    ] });
    groups.push({ id: 'navigation', title: 'Perception', rows: [
      r('held_x_mm', 'Believed east'), r('held_y_mm', 'Believed north'), r('confidence_permille', 'Confidence', { unit: '‰' }),
    ] });
    groups.push({ id: 'sensors', title: 'Sensors', rows: [
      r('gps_x_mm', 'GPS east', { note: 'empty when no sample arrived' }), r('gps_y_mm', 'GPS north'), r('fix_age_ticks', 'Fix age'),
      r('gps_dropped', 'GPS dropped', { map: (v) => (v ? 'yes' : 'no'), unit: '' }),
    ] });
  }
  for (const g of groups) g.rows = g.rows.filter(Boolean);
  return groups.filter((g) => g.rows.length);
}

/**
 * Requirement and invariant state at time t, from the verdicts in the record. A requirement is
 * judged only once the playback reaches its decisive instant; before that it is pending. An
 * invariant is "holding" until the playback passes its first failure instant, if it has one.
 */
export function verdictsAt(run, t) {
  const end = t >= run.model.t1 - 1e-9;
  return (run.record.requirements || []).map((q) => {
    const at = Number.isFinite(q.t) ? q.t : null;
    const decided = at !== null ? t >= at - 1e-9 : end;
    let state;
    if (q.status !== 'pass' && q.status !== 'fail') state = 'not-evaluated';
    else if (q.category === 'invariant') state = q.status === 'fail' ? (decided ? 'violated' : 'holding') : end ? 'held' : 'holding';
    else state = !decided ? 'pending' : q.status === 'pass' ? 'met' : 'failed';
    return { q, state, decided };
  });
}

/** Number formatting with a fixed number of decimals per magnitude (no jumping digits). */
export function fmt(v, digits) {
  if (v === null || v === undefined) return 'n/a';
  if (typeof v === 'string') return v;
  if (digits !== undefined) return v.toFixed(digits);
  return hudNum(v);
}
