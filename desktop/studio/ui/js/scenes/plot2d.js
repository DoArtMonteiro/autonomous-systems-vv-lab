// A small precise 2D canvas plot with axes in data units, an optional equal aspect ratio, a cached
// static layer and a cheap dynamic layer redrawn on each cursor move.

import { h, num } from '../dom.js';
import { cssVar } from '../charts.js';

function niceStep(span, target) {
  const raw = span / Math.max(1, target);
  const p = 10 ** Math.floor(Math.log10(raw));
  const m = raw / p;
  return (m < 1.5 ? 1 : m < 3 ? 2 : m < 7 ? 5 : 10) * p;
}

export class Plot2D {
  /**
   * @param host element; the plot fills it
   * @param opts {xLabel, yLabel, equal, label, drawStatic(ctx, P), drawDynamic(ctx, P, t)}
   */
  constructor(host, opts) {
    this.host = host;
    this.opts = opts;
    this.base = h('canvas', { class: 'p2d-base', role: 'img', 'aria-label': opts.label || 'plot' });
    this.top = h('canvas', { class: 'p2d-top', 'aria-hidden': 'true' });
    this.wrap = h('div', { class: 'p2d' }, this.base, this.top);
    host.appendChild(this.wrap);
    this.view = { xmin: 0, xmax: 1, ymin: 0, ymax: 1 };
    this.t = 0;
    this.ro = new ResizeObserver(() => this.resize());
    this.ro.observe(this.wrap);
  }

  setView(v) {
    this.view = { ...v };
    this.resize();
  }

  resize() {
    const w = Math.max(10, this.wrap.clientWidth);
    const hgt = Math.max(10, this.wrap.clientHeight);
    const dpr = window.devicePixelRatio || 1;
    for (const c of [this.base, this.top]) {
      c.width = Math.round(w * dpr);
      c.height = Math.round(hgt * dpr);
      c.style.width = `${w}px`;
      c.style.height = `${hgt}px`;
    }
    this.w = w;
    this.h = hgt;
    this.dpr = dpr;
    this.layout();
    this.drawBase();
    this.drawTop(this.t);
  }

  layout() {
    const pad = { l: 52, r: 12, t: 10, b: 30 };
    let { xmin, xmax, ymin, ymax } = this.view;
    const pw = Math.max(1, this.w - pad.l - pad.r);
    const ph = Math.max(1, this.h - pad.t - pad.b);
    if (this.opts.equal) {
      const sx = pw / (xmax - xmin || 1);
      const sy = ph / (ymax - ymin || 1);
      const s = Math.min(sx, sy);
      const cx = (xmin + xmax) / 2;
      const cy = (ymin + ymax) / 2;
      xmin = cx - pw / s / 2; xmax = cx + pw / s / 2;
      ymin = cy - ph / s / 2; ymax = cy + ph / s / 2;
    }
    this.P = {
      xmin, xmax, ymin, ymax, pad, pw, ph,
      x: (v) => pad.l + ((v - xmin) / (xmax - xmin || 1)) * pw,
      y: (v) => pad.t + ph - ((v - ymin) / (ymax - ymin || 1)) * ph,
      scale: pw / (xmax - xmin || 1),
      colour: cssVar,
    };
  }

  drawBase() {
    const ctx = this.base.getContext('2d');
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    ctx.clearRect(0, 0, this.w, this.h);
    const P = this.P;
    const rule = cssVar('--rule');
    const fg3 = cssVar('--fg-3');
    const mono = cssVar('--mono');
    ctx.font = `11px ${mono}`;
    ctx.lineWidth = 1;
    const sx = niceStep(P.xmax - P.xmin, Math.max(2, P.pw / 90));
    const sy = niceStep(P.ymax - P.ymin, Math.max(2, P.ph / 60));
    ctx.strokeStyle = rule;
    ctx.fillStyle = fg3;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    for (let v = Math.ceil(P.xmin / sx) * sx; v <= P.xmax; v += sx) {
      const x = Math.round(P.x(v)) + 0.5;
      ctx.beginPath(); ctx.moveTo(x, P.pad.t); ctx.lineTo(x, P.pad.t + P.ph); ctx.stroke();
      ctx.fillText(num(v, 4), x, P.pad.t + P.ph + 6);
    }
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    for (let v = Math.ceil(P.ymin / sy) * sy; v <= P.ymax; v += sy) {
      const y = Math.round(P.y(v)) + 0.5;
      ctx.beginPath(); ctx.moveTo(P.pad.l, y); ctx.lineTo(P.pad.l + P.pw, y); ctx.stroke();
      ctx.fillText(num(v, 4), P.pad.l - 6, y);
    }
    ctx.fillStyle = fg3;
    ctx.textAlign = 'right';
    ctx.textBaseline = 'bottom';
    if (this.opts.xLabel) ctx.fillText(this.opts.xLabel, P.pad.l + P.pw, P.pad.t + P.ph - 4);
    ctx.save();
    ctx.translate(P.pad.l + 12, P.pad.t + 4);
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    if (this.opts.yLabel) ctx.fillText(this.opts.yLabel, 0, 0);
    ctx.restore();
    ctx.save();
    ctx.beginPath();
    ctx.rect(P.pad.l, P.pad.t, P.pw, P.ph);
    ctx.clip();
    if (this.opts.drawStatic) this.opts.drawStatic(ctx, P);
    ctx.restore();
  }

  drawTop(t) {
    this.t = t;
    if (!this.P) return;
    const ctx = this.top.getContext('2d');
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    ctx.clearRect(0, 0, this.w, this.h);
    ctx.save();
    ctx.beginPath();
    ctx.rect(this.P.pad.l, this.P.pad.t, this.P.pw, this.P.ph);
    ctx.clip();
    if (this.opts.drawDynamic) this.opts.drawDynamic(ctx, this.P, t);
    ctx.restore();
  }

  redraw() {
    this.drawBase();
    this.drawTop(this.t);
  }

  dispose() {
    this.ro.disconnect();
    this.wrap.remove();
  }
}

/** Polyline through (xs[i], ys[i]) breaking at nulls. `upto` limits the drawn samples. */
export function polyline(ctx, P, xs, ys, upto = xs.length) {
  let pen = false;
  ctx.beginPath();
  for (let i = 0; i < Math.min(upto, xs.length); i++) {
    const a = xs[i];
    const b = ys[i];
    if (a === null || b === null || a === undefined || b === undefined) { pen = false; continue; }
    const x = P.x(a);
    const y = P.y(b);
    if (pen) ctx.lineTo(x, y); else ctx.moveTo(x, y);
    pen = true;
  }
  ctx.stroke();
}

export function dots(ctx, P, xs, ys, r = 2) {
  ctx.beginPath();
  for (let i = 0; i < xs.length; i++) {
    if (xs[i] === null || ys[i] === null) continue;
    const x = P.x(xs[i]);
    const y = P.y(ys[i]);
    ctx.moveTo(x + r, y);
    ctx.arc(x, y, r, 0, Math.PI * 2);
  }
  ctx.fill();
}

export function extent(arrays, pad = 0.08) {
  let lo = Infinity;
  let hi = -Infinity;
  for (const a of arrays) for (const v of a) if (v !== null && v !== undefined && Number.isFinite(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
  if (!Number.isFinite(lo)) return [0, 1];
  const span = hi - lo || Math.abs(hi) || 1;
  return [lo - span * pad, hi + span * pad];
}
