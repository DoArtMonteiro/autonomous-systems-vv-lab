// Scene renderer for kind "ground-2d": the 2D kinematic ground vehicle. Draws the world bounds, the
// start, the goal and its arrival radius, the restricted zones, the true path, the GPS samples (with
// gaps where no sample exists) and the vehicle at the cursor.

import { h, clear, lowerIndex, sampleAt, num, timeText } from '../dom.js';
import { Plot2D, polyline, dots, extent } from './plot2d.js';

const CH = { tx: 'truth_x_mm', ty: 'truth_y_mm', gx: 'gps_x_mm', gy: 'gps_y_mm', hx: 'held_x_mm', hy: 'held_y_mm' };

function vals(model, id) {
  const c = model.byId.get(id);
  return c ? { v: c.values, t: model.timebases[c.timebase] || [] } : null;
}

function geometry(scene) {
  return {
    bounds: scene.bounds || null,
    start: scene.start || null,
    goal: scene.goal || null,
    radius: typeof scene.arrival_radius_mm === 'number' ? scene.arrival_radius_mm : null,
    zones: Array.isArray(scene.restricted_zones) ? scene.restricted_zones : [],
    waypoints: Array.isArray(scene.waypoints) ? scene.waypoints : [],
  };
}

function drawWorld(ctx, P, g) {
  const c = P.colour;
  if (g.bounds) {
    ctx.strokeStyle = c('--fg-2');
    ctx.setLineDash([]);
    ctx.lineWidth = 1.5;
    ctx.strokeRect(P.x(g.bounds.min_x), P.y(g.bounds.max_y), P.x(g.bounds.max_x) - P.x(g.bounds.min_x), P.y(g.bounds.min_y) - P.y(g.bounds.max_y));
    ctx.font = `10.5px ${c('--sans')}`;
    ctx.fillStyle = c('--fg-3');
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText('world boundary', Math.max(P.x(g.bounds.min_x), P.pad.l) + 4, Math.max(P.y(g.bounds.max_y), P.pad.t) + 3);
  }
  for (const z of g.zones) {
    const vs = z.vertices || [];
    if (!vs.length) continue;
    ctx.beginPath();
    vs.forEach((p, i) => (i ? ctx.lineTo(P.x(p.x), P.y(p.y)) : ctx.moveTo(P.x(p.x), P.y(p.y))));
    ctx.closePath();
    ctx.fillStyle = c('--unsafe-wash');
    ctx.fill();
    ctx.strokeStyle = c('--unsafe');
    ctx.lineWidth = 1.2;
    ctx.setLineDash([5, 3]);
    ctx.stroke();
    ctx.setLineDash([]);
  }
  if (g.goal) {
    const r = g.radius ? Math.max(3, g.radius * P.scale) : 6;
    ctx.strokeStyle = c('--pass');
    ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.arc(P.x(g.goal.x), P.y(g.goal.y), r, 0, Math.PI * 2); ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(P.x(g.goal.x) - 5, P.y(g.goal.y)); ctx.lineTo(P.x(g.goal.x) + 5, P.y(g.goal.y));
    ctx.moveTo(P.x(g.goal.x), P.y(g.goal.y) - 5); ctx.lineTo(P.x(g.goal.x), P.y(g.goal.y) + 5);
    ctx.stroke();
  }
  if (g.start) {
    ctx.fillStyle = c('--fg-2');
    ctx.fillRect(P.x(g.start.x) - 4, P.y(g.start.y) - 4, 8, 8);
  }
}

function label(ctx, P, text, x, y) {
  ctx.font = `11px ${P.colour('--sans')}`;
  ctx.fillStyle = P.colour('--fg-2');
  ctx.textAlign = 'left';
  ctx.textBaseline = 'bottom';
  ctx.fillText(text, P.x(x) + 7, P.y(y) - 5);
}

function vehicle(ctx, P, x, y, dx, dy, colour) {
  const ang = Math.atan2(-dy, dx);
  ctx.save();
  ctx.translate(P.x(x), P.y(y));
  ctx.rotate(Number.isFinite(ang) ? ang : 0);
  ctx.beginPath();
  ctx.moveTo(9, 0); ctx.lineTo(-6, -6); ctx.lineTo(-3, 0); ctx.lineTo(-6, 6); ctx.closePath();
  ctx.fillStyle = colour;
  ctx.fill();
  ctx.lineWidth = 1.5;
  ctx.strokeStyle = P.colour('--bg-0');
  ctx.stroke();
  ctx.restore();
}

function legendList(items) {
  return h('ul', { class: 'scene-legend' }, items.map(([cls, text]) => h('li', null, h('span', { class: ['lg', cls] }), text)));
}

function mount(host, model, cursor) {
  clear(host);
  const scene = model.record.scene;
  const g = geometry(scene);
  const tx = vals(model, CH.tx);
  const ty = vals(model, CH.ty);
  const gx = vals(model, CH.gx);
  const gy = vals(model, CH.gy);
  const times = tx ? tx.t : [];
  let mode = 'mission';
  const missionView = () => {
    const xs = [g.start && g.start.x, g.goal && g.goal.x, ...(tx ? tx.v : []), ...(gx ? gx.v : [])].filter((v) => v !== null && v !== undefined);
    const ys = [g.start && g.start.y, g.goal && g.goal.y, ...(ty ? ty.v : []), ...(gy ? gy.v : [])].filter((v) => v !== null && v !== undefined);
    const [x0, x1] = extent([xs], 0.12);
    const [y0, y1] = extent([ys], 0.12);
    const span = Math.max(x1 - x0, y1 - y0, 1000);
    const cx = (x0 + x1) / 2;
    const cy = (y0 + y1) / 2;
    return { xmin: cx - span / 2, xmax: cx + span / 2, ymin: cy - span / 2, ymax: cy + span / 2 };
  };
  const worldView = () => (g.bounds ? { xmin: g.bounds.min_x, xmax: g.bounds.max_x, ymin: g.bounds.min_y, ymax: g.bounds.max_y } : missionView());
  const dropouts = Array.isArray(scene.gps_dropout_windows) ? scene.gps_dropout_windows : [];
  const readout = h('div', { class: 'scene-readout mono overlay right', 'aria-live': 'off' });
  const plotHost = h('div', { class: 'scene-canvas' }, readout);
  const zoneNote = h('span', { class: 'dim small' });
  const seg = h('div', { class: 'seg', role: 'radiogroup', 'aria-label': 'Scene extent' },
    ...[['mission', 'Mission'], ['world', 'Whole world']].map(([m, t]) => h('button', {
      type: 'button', class: 'seg-btn', role: 'radio', 'aria-checked': String(m === mode),
      onclick: (e) => {
        mode = m;
        for (const b of seg.children) b.setAttribute('aria-checked', String(b === e.currentTarget));
        plot.setView(mode === 'world' ? worldView() : missionView());
        updateZoneNote();
      },
    }, t)));
  const bar = h('div', { class: 'scene-bar' }, h('h2', { class: 'pane-title' }, 'Scene'), h('span', { class: 'dim small' }, 'top view, x east, y north, mm'), h('div', { class: 'spacer' }), seg);
  const legendItems = legendList([
    ['lg-truth', 'true path'],
    ['lg-obs', 'GPS samples (none in a dropout)'],
    ...(dropouts.length ? [['lg-fault', 'true path during a GPS dropout window']] : []),
    ['lg-zone', 'restricted zone'],
    ['lg-goal', 'goal, arrival radius'],
    ['lg-veh', 'vehicle: illustration, interpolated between ticks for display'],
  ]);
  const legend = h('details', { class: 'scene-key', open: host.clientHeight > 380 },
    h('summary', null, h('span', { class: 'lg lg-truth' }), 'true path, ', h('span', { class: 'lg lg-obs' }), 'GPS samples; vehicle is an illustration, interpolated between ticks for display'),
    legendItems);
  host.append(bar, plotHost, h('div', { class: 'scene-foot' }, legend, zoneNote));

  const plot = new Plot2D(plotHost, {
    equal: true,
    label: 'Top view of the ground mission: true path, GPS samples, goal and restricted zones',
    drawStatic: (ctx, P) => {
      drawWorld(ctx, P, g);
      if (g.start) label(ctx, P, 'start', g.start.x, g.start.y);
      if (g.goal) label(ctx, P, 'goal', g.goal.x, g.goal.y);
      if (tx && ty) {
        ctx.strokeStyle = P.colour('--truth-dim');
        ctx.lineWidth = 2;
        polyline(ctx, P, tx.v, ty.v);
        // Ticks inside a GPS dropout window, on the true path.
        ctx.strokeStyle = P.colour('--fault');
        ctx.lineWidth = 4;
        for (const w of dropouts) {
          const a = lowerIndex(times, w.start_tick);
          const b = lowerIndex(times, w.end_tick);
          polyline(ctx, P, tx.v.slice(a, b + 1), ty.v.slice(a, b + 1));
        }
      }
      if (gx && gy) {
        ctx.fillStyle = P.colour('--obs');
        dots(ctx, P, gx.v, gy.v, 2.6);
      }
    },
    drawDynamic: (ctx, P, t) => {
      if (!tx || !ty || !times.length) return;
      const i = lowerIndex(times, t);
      ctx.strokeStyle = P.colour('--truth');
      ctx.lineWidth = 2.2;
      const x = sampleAt(times, tx.v, t);
      const y = sampleAt(times, ty.v, t);
      polyline(ctx, P, [...tx.v.slice(0, i + 1), x], [...ty.v.slice(0, i + 1), y]);
      if (gx && gy && gx.v[i] !== null && gy.v[i] !== null) {
        ctx.strokeStyle = P.colour('--obs');
        ctx.lineWidth = 1.5;
        ctx.beginPath(); ctx.arc(P.x(gx.v[i]), P.y(gy.v[i]), 6, 0, Math.PI * 2); ctx.stroke();
      }
      if (x !== null && y !== null) {
        const j = Math.min(times.length - 1, i + 1);
        let dx = tx.v[j] - tx.v[Math.max(0, i)];
        let dy = ty.v[j] - ty.v[Math.max(0, i)];
        if (!dx && !dy && i > 0) { dx = tx.v[i] - tx.v[i - 1]; dy = ty.v[i] - ty.v[i - 1]; }
        vehicle(ctx, P, x, y, dx || 1, dy || 0, P.colour('--truth'));
      }
    },
  });
  plot.setView(missionView());
  function updateZoneNote() {
    const P = plot.P;
    const out = g.zones.filter((z) => (z.vertices || []).every((p) => p.x < P.xmin || p.x > P.xmax || p.y < P.ymin || p.y > P.ymax)).length;
    zoneNote.textContent = out ? `${out} restricted zone${out > 1 ? 's' : ''} outside this view; choose Whole world to see ${out > 1 ? 'them' : 'it'}.` : '';
  }
  updateZoneNote();
  const unsub = cursor.subscribe((t) => {
    plot.drawTop(t);
    const i = lowerIndex(times, t);
    if (i < 0) return;
    const gxv = gx ? gx.v[i] : null;
    readout.replaceChildren(h('span', null, timeText(times[i], 'tick')), h('span', null, `true (${num(tx.v[i], 6)}, ${num(ty.v[i], 6)}) mm`), h('span', null, `GPS ${gxv === null || gxv === undefined ? 'no sample' : `(${num(gxv, 6)}, ${num(gy.v[i], 6)}) mm`}`));
  });
  plot.drawTop(cursor.t);
  return { dispose: () => { unsub(); plot.dispose(); }, redraw: () => plot.redraw() };
}

function compare(host, models, colours, labels, cursor) {
  clear(host);
  const g = geometry(models[0].record.scene);
  const differ = models.some((m) => JSON.stringify(geometry(m.record.scene)) !== JSON.stringify(g));
  const paths = models.map((m) => ({ tx: vals(m, CH.tx), ty: vals(m, CH.ty), gx: vals(m, CH.gx), gy: vals(m, CH.gy) }));
  const xs = [g.start && g.start.x, g.goal && g.goal.x];
  const ys = [g.start && g.start.y, g.goal && g.goal.y];
  for (const p of paths) {
    if (p.tx) xs.push(...p.tx.v);
    if (p.ty) ys.push(...p.ty.v);
  }
  const [x0, x1] = extent([xs.filter((v) => v !== null && v !== undefined)], 0.12);
  const [y0, y1] = extent([ys.filter((v) => v !== null && v !== undefined)], 0.12);
  const span = Math.max(x1 - x0, y1 - y0, 1000);
  const plotHost = h('div', { class: 'scene-canvas' });
  host.append(
    h('div', { class: 'scene-bar' }, h('h3', null, 'Paths, top view'), h('span', { class: 'dim small' }, 'true path solid, GPS samples as dots; x east, y north, mm')),
    plotHost,
    differ ? h('p', { class: 'warn-text small' }, 'The runs have different scene geometry; start, goal and zones are drawn from the first run.') : null);
  const plot = new Plot2D(plotHost, {
    equal: true, label: 'Overlaid true paths of the compared runs',
    drawStatic: (ctx, P) => {
      drawWorld(ctx, P, g);
      paths.forEach((p, i) => {
        if (p.gx && p.gy) { ctx.fillStyle = colours[i]; ctx.globalAlpha = 0.5; dots(ctx, P, p.gx.v, p.gy.v, 2.2); ctx.globalAlpha = 1; }
        if (p.tx && p.ty) { ctx.strokeStyle = colours[i]; ctx.lineWidth = 2; ctx.setLineDash(i % 2 ? [6, 3] : []); polyline(ctx, P, p.tx.v, p.ty.v); ctx.setLineDash([]); }
      });
    },
    drawDynamic: (ctx, P, t) => {
      paths.forEach((p, i) => {
        if (!p.tx || !p.ty) return;
        const x = sampleAt(p.tx.t, p.tx.v, t);
        const y = sampleAt(p.ty.t, p.ty.v, t);
        if (x === null || y === null) return;
        ctx.fillStyle = colours[i];
        ctx.beginPath(); ctx.arc(P.x(x), P.y(y), 5, 0, Math.PI * 2); ctx.fill();
        ctx.strokeStyle = P.colour('--bg-0'); ctx.lineWidth = 1.5; ctx.stroke();
      });
    },
  });
  plot.setView({ xmin: (x0 + x1) / 2 - span / 2, xmax: (x0 + x1) / 2 + span / 2, ymin: (y0 + y1) / 2 - span / 2, ymax: (y0 + y1) / 2 + span / 2 });
  const unsub = cursor ? cursor.subscribe((t) => plot.drawTop(t)) : () => {};
  return { dispose: () => { unsub(); plot.dispose(); } };
}

export const ground2d = { title: 'Ground vehicle, top view', mount, compare };
