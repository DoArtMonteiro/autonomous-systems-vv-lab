// Scene renderer for kind "ascent": a multi-entity launch (vv-run.v2). Draws every entity of the
// record (stack, then booster and upper stage after separation) as altitude over downrange, or in a
// planar view that keeps the curvature of the Earth, with the recovery zone and the target orbit.
// An entity selector picks whose telemetry and requirements are listed. Everything drawn comes from
// the record; positions between samples are interpolated for display only.

import { h, clear, sampleAt, num, timeText } from '../dom.js';
import { Plot2D, polyline, extent } from './plot2d.js';
import { RUN_COLOURS, runDash, verdictOfRequirement, STATUS_TEXT } from '../model.js';

// Okabe-Ito colours; green is left to the pass colour of the target orbit and the recovery zone.
const ENTITY_COLOUR = { stack: RUN_COLOURS[0], booster: RUN_COLOURS[1], upper: RUN_COLOURS[2] };

function entitiesOf(model) {
  const rec = model.record;
  const scene = rec.scene || {};
  const meta = Array.isArray(rec.entities) ? rec.entities : [];
  return (Array.isArray(scene.entities) ? scene.entities : []).map((se, i) => {
    const alt = model.byId.get(se.altitude);
    const dr = model.byId.get(se.downrange);
    const m = meta.find((e) => e.id === se.id) || {};
    return {
      id: se.id,
      label: se.label || se.id,
      kind: se.kind,
      parent: se.parent || null,
      times: model.timebases[se.timebase] || [],
      alt: alt ? alt.values : [],
      dr: dr ? dr.values : [],
      colour: ENTITY_COLOUR[se.id] || RUN_COLOURS[i % RUN_COLOURS.length],
      dash: runDash(i),
      meta: m,
    };
  });
}

/** Planar position with the curvature of the Earth: x along the surface tangent at the pad, y up. */
function curved(R, drKm, altKm) {
  const th = drKm / R;
  const rho = R + altKm;
  return [rho * Math.sin(th), rho * Math.cos(th) - R];
}

function mapped(ents, R, mode) {
  return ents.map((e) => {
    if (mode === 'profile') return { xs: e.dr, ys: e.alt };
    const xs = [];
    const ys = [];
    for (let i = 0; i < e.dr.length; i++) {
      if (e.dr[i] === null || e.alt[i] === null) { xs.push(null); ys.push(null); continue; }
      const [x, y] = curved(R, e.dr[i], e.alt[i]);
      xs.push(x); ys.push(y);
    }
    return { xs, ys };
  });
}

function viewOf(paths, mode, target) {
  const [x0, x1] = extent(paths.map((p) => p.xs), 0.04);
  const [y0, y1] = extent([...paths.map((p) => p.ys), [0, target || 0]], 0.08);
  if (mode === 'profile') return { xmin: Math.min(0, x0), xmax: x1, ymin: Math.min(0, y0), ymax: y1 };
  return { xmin: x0, xmax: x1, ymin: y0, ymax: y1 };
}

function drawWorld(ctx, P, mode, R, scene) {
  const c = P.colour;
  const zone = Array.isArray(scene.recovery_zone_km) ? scene.recovery_zone_km : null;
  const target = typeof scene.target_altitude_km === 'number' ? scene.target_altitude_km : null;
  ctx.lineWidth = 1.2;
  if (mode === 'profile') {
    ctx.strokeStyle = c('--fg-3');
    ctx.beginPath(); ctx.moveTo(P.x(P.xmin), P.y(0)); ctx.lineTo(P.x(P.xmax), P.y(0)); ctx.stroke();
    if (target !== null) {
      ctx.strokeStyle = c('--pass'); ctx.setLineDash([6, 4]);
      ctx.beginPath(); ctx.moveTo(P.x(P.xmin), P.y(target)); ctx.lineTo(P.x(P.xmax), P.y(target)); ctx.stroke();
      ctx.setLineDash([]);
    }
    if (zone) {
      ctx.fillStyle = c('--pass-wash');
      ctx.fillRect(P.x(zone[0]), P.y(0) - 6, P.x(zone[1]) - P.x(zone[0]), 6);
    }
  } else {
    const arc = (rho, from, to) => {
      ctx.beginPath();
      for (let k = 0; k <= 240; k++) {
        const th = from + ((to - from) * k) / 240;
        const x = rho * Math.sin(th);
        const y = rho * Math.cos(th) - R;
        if (k) ctx.lineTo(P.x(x), P.y(y)); else ctx.moveTo(P.x(x), P.y(y));
      }
      ctx.stroke();
    };
    const span = Math.max(Math.abs(P.xmin), Math.abs(P.xmax)) / R + 0.05;
    ctx.strokeStyle = c('--fg-3');
    arc(R, -span, span);
    if (target !== null) { ctx.strokeStyle = c('--pass'); ctx.setLineDash([6, 4]); arc(R + target, -span, span); ctx.setLineDash([]); }
    if (zone) { ctx.strokeStyle = c('--pass'); ctx.lineWidth = 5; arc(R, zone[0] / R, zone[1] / R); ctx.lineWidth = 1.2; }
  }
  ctx.font = `10.5px ${c('--sans')}`;
  ctx.fillStyle = c('--fg-3');
  ctx.textAlign = 'left';
  ctx.textBaseline = 'bottom';
  if (target !== null && mode === 'profile') {
    ctx.textAlign = 'right';
    ctx.fillText(`target orbit ${num(target)} km`, P.pad.l + P.pw - 6, P.y(target) - 3);
    ctx.textAlign = 'left';
  }
  if (zone && mode === 'profile') ctx.fillText('recovery zone', P.x(zone[0]), P.y(0) - 8);
}

const SHORT = {
  altitude_km: 'alt', downrange_km: 'downrange', speed_m_s: 'speed', radial_velocity_m_s: 'vr',
  observed_altitude_km: 'nav alt', dynamic_pressure_kpa: 'q', sensed_acceleration_g: 'accel',
  mass_t: 'mass', propellant_kg: 'propellant', throttle: 'throttle',
};

function telemetry(model, e, t) {
  const times = e.times;
  if (!times.length) return [h('span', null, `${e.label}: no samples`)];
  if (t < times[0]) return [h('span', null, `${e.label}: starts at ${timeText(times[0], 's')}`)];
  const ended = t > times[times.length - 1];
  const rows = [h('strong', { style: { color: e.colour } }, `${e.label} ${ended ? `ended at ${timeText(times[times.length - 1], 's')} (${e.meta.end_reason || 'end'})` : `at ${timeText(t, 's')}`}`)];
  const tt = ended ? times[times.length - 1] : t;
  for (const id of e.meta.channels || []) {
    const c = model.byId.get(id);
    if (!c) continue;
    const v = sampleAt(times, c.values, tt);
    const short = SHORT[id.slice(e.id.length + 1)] || c.label;
    const text = v === null || v === undefined ? 'n/a' : Math.abs(v) < 1e-3 && v !== 0 ? '< 0.001' : num(v, 5);
    rows.push(h('span', { title: `${c.kind}: ${c.label}` }, `${short} ${text}${c.unit ? ` ${c.unit}` : ''}`));
  }
  return rows;
}

function requirementList(rec, ids, title) {
  const reqs = (rec.requirements || []).filter((r) => ids.includes(r.id));
  if (!reqs.length) return null;
  return h('section', { class: 'ascent-reqs', 'aria-label': title, style: { flex: '1 1 260px', minWidth: '0' } },
    h('h3', { class: 'small' }, title),
    h('ul', { class: 'ascent-req-list', style: { listStyle: 'none', margin: '2px 0 0', padding: '0' } }, reqs.map((r) => {
      const v = verdictOfRequirement(r);
      return h('li', { class: ['ascent-req', `v-${v}`], title: r.explanation || '', style: { margin: '2px 0' } },
        h('span', { class: ['mono', 'small', `v-${v}-text`] }, STATUS_TEXT[r.status] || r.status),
        ' ', h('span', { class: 'mono small' }, r.id), ' ', h('span', { class: 'small' }, r.label),
        h('div', { class: 'dim small mono' }, r.observed));
    })));
}

function mount(host, model, cursor) {
  clear(host);
  const rec = model.record;
  const scene = rec.scene || {};
  const R = typeof scene.earth_radius_km === 'number' ? scene.earth_radius_km : 6371;
  const ents = entitiesOf(model);
  let mode = 'profile';
  let selected = 'all';
  let paths = mapped(ents, R, mode);
  const readout = h('div', { class: 'scene-readout mono', 'aria-live': 'off', style: { padding: '3px 12px', whiteSpace: 'normal', lineHeight: '1.6', display: 'flex', flexDirection: 'column' } });
  const plotHost = h('div', { class: 'scene-canvas' });
  const seg = (label, items, current, onPick) => {
    const g = h('div', { class: 'seg', role: 'radiogroup', 'aria-label': label });
    for (const [k, text] of items) {
      g.append(h('button', {
        type: 'button', class: 'seg-btn', role: 'radio', 'aria-checked': String(k === current),
        onclick: (ev) => {
          for (const b of g.children) b.setAttribute('aria-checked', String(b === ev.currentTarget));
          onPick(k);
        },
      }, text));
    }
    return g;
  };
  const reqHost = h('div', { class: 'ascent-req-host', style: { display: 'flex', flexWrap: 'wrap', gap: '4px 18px', padding: '4px 12px 8px', maxHeight: '34%', overflowY: 'auto', borderTop: '1px solid var(--rule)' } });
  const viewSeg = seg('View', [['profile', 'Altitude over downrange'], ['curved', 'Earth curvature']], mode, (k) => {
    mode = k;
    paths = mapped(ents, R, mode);
    plot.opts.equal = mode === 'curved';
    plot.opts.xLabel = mode === 'profile' ? 'downrange, km' : 'km along the pad horizon';
    plot.opts.yLabel = mode === 'profile' ? 'altitude, km' : 'km above the pad';
    plot.setView(viewOf(paths, mode, scene.target_altitude_km));
  });
  const entSeg = seg('Entity', [['all', 'All'], ...ents.map((e) => [e.id, e.label.replace(/ \(.*\)$/, '')])], selected, (k) => {
    selected = k;
    plot.redraw();
    renderSide();
    renderReadout(cursor.t);
  });
  const bar = h('div', { class: 'scene-bar' },
    h('h2', { class: 'pane-title' }, 'Scene'),
    h('span', { class: 'dim small' }, scene.vehicle_label || 'launch ascent'),
    h('div', { class: 'spacer' }), viewSeg, entSeg);
  const legend = h('ul', { class: 'scene-legend' },
    ents.map((e) => h('li', null, h('span', { class: 'lg', style: { borderColor: e.colour, borderTopStyle: e.dash.length ? 'dashed' : 'solid' } }), `${e.label}${e.parent ? `, from ${e.parent}` : ''}`)),
    h('li', null, h('span', { class: 'lg lg-goal' }), 'target orbit, recovery zone'),
    h('li', null, 'true state; markers interpolated between 1 s samples for display'));
  host.append(bar, plotHost, readout, h('div', { class: 'scene-foot' }, legend), reqHost);

  const plot = new Plot2D(plotHost, {
    equal: false,
    xLabel: 'downrange, km',
    yLabel: 'altitude, km',
    label: 'Trajectories of the stack, the booster and the upper stage',
    drawStatic: (ctx, P) => {
      drawWorld(ctx, P, mode, R, scene);
      ents.forEach((e, i) => {
        const dim = selected !== 'all' && selected !== e.id;
        ctx.globalAlpha = dim ? 0.3 : 1;
        ctx.strokeStyle = e.colour;
        ctx.lineWidth = dim ? 1.2 : 2;
        ctx.setLineDash(e.dash);
        polyline(ctx, P, paths[i].xs, paths[i].ys);
        ctx.setLineDash([]);
      });
      ctx.globalAlpha = 1;
    },
    drawDynamic: (ctx, P, t) => {
      ents.forEach((e, i) => {
        const tb = e.times;
        if (!tb.length || t < tb[0] || t > tb[tb.length - 1]) return;
        const x = sampleAt(tb, paths[i].xs, t);
        const y = sampleAt(tb, paths[i].ys, t);
        if (x === null || y === null) return;
        ctx.fillStyle = e.colour;
        ctx.beginPath(); ctx.arc(P.x(x), P.y(y), selected === e.id ? 6 : 4.5, 0, Math.PI * 2); ctx.fill();
        ctx.strokeStyle = P.colour('--bg-0'); ctx.lineWidth = 1.5; ctx.stroke();
      });
    },
  });
  plot.setView(viewOf(paths, mode, scene.target_altitude_km));

  function renderSide() {
    const mission = rec.mission && Array.isArray(rec.mission.requirements) ? rec.mission.requirements : [];
    const shown = selected === 'all' ? ents : ents.filter((e) => e.id === selected);
    const lists = shown.map((e) => requirementList(rec, e.meta.requirements || [], `${e.label}: requirements`));
    if (selected === 'all') lists.push(requirementList(rec, mission, 'Mission requirements'));
    reqHost.replaceChildren(...lists.filter(Boolean));
  }
  function renderReadout(t) {
    const shown = selected === 'all' ? ents.filter((e) => e.times.length && t >= e.times[0] && t <= e.times[e.times.length - 1]) : ents.filter((e) => e.id === selected);
    readout.replaceChildren(...shown.map((e) => h('div', { style: { display: 'flex', flexWrap: 'wrap', gap: '0 12px' } }, telemetry(model, e, t))));
  }
  renderSide();
  const unsub = cursor.subscribe((t) => { plot.drawTop(t); renderReadout(t); });
  plot.drawTop(cursor.t);
  renderReadout(cursor.t);
  return { dispose: () => { unsub(); plot.dispose(); }, redraw: () => plot.redraw() };
}

function compare(host, models, colours, _labels, cursor) {
  clear(host);
  const all = models.map((m) => entitiesOf(m));
  const R = 6371;
  const plotHost = h('div', { class: 'scene-canvas' });
  host.append(
    h('div', { class: 'scene-bar' }, h('h3', null, 'Trajectories, altitude over downrange'), h('span', { class: 'dim small' }, 'one colour per run; solid stack, dashed booster, dotted upper stage')),
    plotHost);
  const paths = all.map((ents) => mapped(ents, R, 'profile'));
  const flat = paths.flat();
  const plot = new Plot2D(plotHost, {
    equal: false, xLabel: 'downrange, km', yLabel: 'altitude, km', label: 'Overlaid entity trajectories of the compared runs',
    drawStatic: (ctx, P) => {
      paths.forEach((ps, r) => ps.forEach((p, i) => {
        ctx.strokeStyle = colours[r]; ctx.lineWidth = 1.8; ctx.setLineDash(runDash(i));
        polyline(ctx, P, p.xs, p.ys); ctx.setLineDash([]);
      }));
    },
    drawDynamic: (ctx, P, t) => {
      all.forEach((ents, r) => ents.forEach((e, i) => {
        const tb = e.times;
        if (!tb.length || t < tb[0] || t > tb[tb.length - 1]) return;
        const x = sampleAt(tb, paths[r][i].xs, t);
        const y = sampleAt(tb, paths[r][i].ys, t);
        if (x === null || y === null) return;
        ctx.fillStyle = colours[r];
        ctx.beginPath(); ctx.arc(P.x(x), P.y(y), 4.5, 0, Math.PI * 2); ctx.fill();
      }));
    },
  });
  plot.setView(viewOf(flat, 'profile', null));
  const unsub = cursor ? cursor.subscribe((t) => plot.drawTop(t)) : () => {};
  return { dispose: () => { unsub(); plot.dispose(); } };
}

export const ascent = { title: 'Launch ascent, entities', mount, compare };
