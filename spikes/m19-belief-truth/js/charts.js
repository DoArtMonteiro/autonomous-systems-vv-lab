// SVG drawing for the Belief vs Truth view: the time axis, the error strips, the guidance lane and
// the pad plan. Pure drawing: values come from the Model, nothing is derived here.
//
// Rules kept by this file:
//  - Observations (series with render "points") are drawn only as separate markers, never joined.
//  - Lines break at nulls. Nothing is interpolated between samples; the cursor snaps to samples.
//  - Every number printed inside an SVG is an axis scale label, marked data-layout="1".

import { lineRuns, pointList, formatNumber } from "./model.js";

const NS = "http://www.w3.org/2000/svg";
export const ML = 58; // left margin (y labels)
export const MR = 14;

function el(tag, attrs = {}, parent) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
  if (parent) parent.appendChild(e);
  return e;
}

function text(parent, x, y, str, attrs = {}, layout = false) {
  const e = el("text", { x, y, ...attrs }, parent);
  e.textContent = str;
  if (layout) e.setAttribute("data-layout", "1");
  return e;
}

export function niceStep(span, target) {
  const raw = span / target;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const f = raw / mag;
  const m = f < 1.5 ? 1 : f < 3.5 ? 2 : f < 7.5 ? 5 : 10;
  return m * mag;
}

function decimals(step) {
  return step >= 1 ? 0 : Math.min(3, Math.ceil(-Math.log10(step) - 1e-9));
}

export function xScale(width, t0, t1) {
  const w = width - ML - MR;
  return (t) => ML + ((t - t0) / (t1 - t0)) * w;
}

export function timeAt(width, t0, t1, px) {
  const w = width - ML - MR;
  return t0 + ((px - ML) / w) * (t1 - t0);
}

function clear(svg, width, height) {
  while (svg.firstChild) svg.removeChild(svg.firstChild);
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("width", width);
  svg.setAttribute("height", height);
}

function shape(parent, kind, cx, cy, r, cls) {
  let e;
  if (kind === "triangle") {
    e = el("polygon", { points: `${cx},${cy - r - 1} ${cx + r + 1},${cy + r} ${cx - r - 1},${cy + r}` }, parent);
  } else if (kind === "square") {
    e = el("rect", { x: cx - r, y: cy - r, width: 2 * r, height: 2 * r }, parent);
  } else if (kind === "diamond") {
    e = el("polygon", { points: `${cx},${cy - r - 1} ${cx + r + 1},${cy} ${cx},${cy + r + 1} ${cx - r - 1},${cy}` }, parent);
  } else {
    e = el("circle", { cx, cy, r }, parent);
  }
  e.setAttribute("class", cls);
  return e;
}

function visible(xs, t0, t1) {
  const out = [];
  xs.forEach((t, i) => {
    if (t >= t0 - 1e-9 && t <= t1 + 1e-9) out.push(i);
  });
  return out;
}

/** Time axis: every sample as a tick, events at their exact times, the cursor sample marked. */
export function drawTimeAxis(svg, { model, width, t0, t1, cursor }) {
  const H = 114;
  clear(svg, width, H);
  const X = xScale(width, t0, t1);
  const base = 80;
  const xs = model.t;
  const inView = visible(xs, t0, t1);
  const spacing = inView.length > 1 ? Math.abs(X(xs[inView[1]]) - X(xs[inView[0]])) : 99;
  // Baseline.
  el("line", { x1: ML, y1: base, x2: width - MR, y2: base, class: "ax-base" }, svg);
  // One tick per sample. A longer tick on whole seconds; a diamond for the off-grid touchdown sample.
  for (const i of inView) {
    const x = X(xs[i]);
    const whole = Math.abs(xs[i] - Math.round(xs[i])) < 1e-9;
    if (model.series("kind").values[i] === "touchdown") {
      shape(svg, "diamond", x, base, 4, "ax-td-sample");
    } else {
      el("line", { x1: x, y1: base, x2: x, y2: base + (whole ? 11 : 6), class: "ax-tick" }, svg);
    }
  }
  // Labels on a readable step.
  const span = t1 - t0;
  const step = niceStep(span, Math.max(3, (width - ML - MR) / 70));
  const dg = decimals(step);
  for (let t = Math.ceil(t0 / step - 1e-9) * step; t <= t1 + 1e-9; t += step) {
    text(svg, X(t), base + 28, formatNumber(Number(t.toFixed(6)), dg), { class: "ax-label", "text-anchor": "middle" }, true);
  }
  text(svg, ML, base + 43, "logical time, s (one tick per recorded sample)", { class: "ax-caption" });
  if (spacing < 2) {
    // Dense view: say so, the ticks merge into a band.
    text(svg, width - MR, base + 43, "ticks merge at this zoom", { class: "ax-caption", "text-anchor": "end" });
  }
  // Events.
  model.data.events.forEach((ev, k) => {
    const t = model.scalar(ev.t).v;
    if (t < t0 - 1e-9 || t > t1 + 1e-9) return;
    const x = X(t);
    const row = k;
    const top = 6 + row * 15;
    el("line", { x1: x, y1: top + 7, x2: x, y2: base, class: `ev-line ev-${ev.dash}` }, svg);
    const kind = { ignition: "square", fault_start: "triangle", altimeter_rejected: "circle", touchdown: "diamond" }[ev.id];
    shape(svg, kind, x, top + 3, 4, `ev-mark ev-cls-${ev.cls.replace("-", "")}`);
    const right = x > width - 180;
    text(svg, right ? x - 8 : x + 8, top + 7, ev.label, { class: "ev-label", "text-anchor": right ? "end" : "start" });
  });
  // Cursor.
  const cx = X(xs[cursor]);
  if (xs[cursor] >= t0 - 1e-9 && xs[cursor] <= t1 + 1e-9) {
    el("polygon", { points: `${cx - 6},${base + 14} ${cx + 6},${base + 14} ${cx},${base + 3}`, class: "cursor-mark" }, svg);
  }
  return { X };
}

function autoDomain(values, extras, pad = 0.08) {
  let lo = Infinity;
  let hi = -Infinity;
  for (const v of values) {
    if (v === null || v === undefined) continue;
    lo = Math.min(lo, v);
    hi = Math.max(hi, v);
  }
  for (const v of extras) {
    lo = Math.min(lo, v);
    hi = Math.max(hi, v);
  }
  if (!isFinite(lo)) {
    lo = -1;
    hi = 1;
  }
  const p = (hi - lo || 1) * pad;
  return [lo - p, hi + p];
}

/**
 * One strip in error space. cfg.layers: {series, kind: "line"|"points", cls, shape}.
 * Truth is the zero line by construction. cfg.bands: horizontal reference lines {y, cls}.
 */
export function drawStrip(svg, cfg) {
  const { model, width, t0, t1, cursor, layers, height, bands = [], zero = true } = cfg;
  clear(svg, width, height);
  const X = xScale(width, t0, t1);
  const xs = model.t;
  const inView = visible(xs, t0, t1);
  const mt = 10;
  const mb = 16;
  const vals = [];
  for (const L of layers) {
    const s = model.series(L.series);
    for (const i of inView) vals.push(s.values[i]);
  }
  const [y0, y1] = cfg.domain || autoDomain(vals, [...(zero ? [0] : []), ...bands.map((b) => b.y)]);
  const Y = (v) => mt + (1 - (v - y0) / (y1 - y0)) * (height - mt - mb);
  // Grid and y labels.
  const step = niceStep(y1 - y0, 4);
  const dg = decimals(step);
  for (let v = Math.ceil(y0 / step - 1e-9) * step; v <= y1 + 1e-9; v += step) {
    const y = Y(v);
    el("line", { x1: ML, y1: y, x2: width - MR, y2: y, class: "grid" }, svg);
    text(svg, ML - 6, y + 4, formatNumber(Number(v.toFixed(6)), dg), { class: "ax-label", "text-anchor": "end" }, true);
  }
  // Events as vertical lines.
  for (const ev of model.data.events) {
    const t = model.scalar(ev.t).v;
    if (t >= t0 - 1e-9 && t <= t1 + 1e-9) el("line", { x1: X(t), y1: mt, x2: X(t), y2: height - mb, class: `ev-line ev-${ev.dash}` }, svg);
  }
  // Sample ticks along the bottom when there is room: every point sits on a tick.
  if (inView.length > 1 && Math.abs(X(xs[inView[1]]) - X(xs[inView[0]])) >= 3) {
    for (const i of inView) el("line", { x1: X(xs[i]), y1: height - mb, x2: X(xs[i]), y2: height - mb + 4, class: "ax-tick" }, svg);
  }
  for (const b of bands) {
    el("line", { x1: ML, y1: Y(b.y), x2: width - MR, y2: Y(b.y), class: b.cls }, svg);
  }
  if (zero) el("line", { x1: ML, y1: Y(0), x2: width - MR, y2: Y(0), class: "zero-truth" }, svg);
  // Layers.
  for (const L of layers) {
    const s = model.series(L.series);
    if (L.kind === "line") {
      for (const run of lineRuns(s, xs)) {
        const pts = run.filter(([t]) => t >= t0 - 1e-9 && t <= t1 + 1e-9);
        if (pts.length < 2) continue;
        el("polyline", { points: pts.map(([t, y]) => `${X(t).toFixed(1)},${Y(y).toFixed(1)}`).join(" "), class: L.cls }, svg);
      }
    } else {
      for (const [t, y] of pointList(s, xs)) {
        if (t < t0 - 1e-9 || t > t1 + 1e-9) continue;
        shape(svg, L.shape, X(t), Y(y), 2.6, L.cls);
      }
    }
  }
  // Cursor: line at the snapped sample and a ring on every value recorded there.
  const cx = X(xs[cursor]);
  if (xs[cursor] >= t0 - 1e-9 && xs[cursor] <= t1 + 1e-9) {
    el("line", { x1: cx, y1: mt, x2: cx, y2: height - mb, class: "cursor-line" }, svg);
    for (const L of layers) {
      const v = model.series(L.series).values[cursor];
      if (v !== null && v !== undefined) el("circle", { cx, cy: Y(v), r: 6.5, class: "cursor-ring" }, svg);
    }
  }
  return { X, Y, domain: [y0, y1] };
}

/** Guidance-source lane. Rule row from the recorded flag time; lower-source marks per sample. */
export function drawLane(svg, { model, width, t0, t1, cursor }) {
  const H = 112;
  clear(svg, width, H);
  const X = xScale(width, t0, t1);
  const xs = model.t;
  const tFlag = model.scalar("run.reject_first_t_s").v;
  const tEnd = xs[model.last];
  const defs = el("defs", {}, svg);
  const pat = el("pattern", { id: "hatch", width: 6, height: 6, patternUnits: "userSpaceOnUse", patternTransform: "rotate(45)" }, defs);
  el("rect", { width: 6, height: 6, class: "hatch-bg" }, pat);
  el("line", { x1: 0, y1: 0, x2: 0, y2: 6, class: "hatch-line" }, pat);
  const clampX = (t) => X(Math.max(t0, Math.min(t1, t)));
  const seg = (ta, tb, cls, label) => {
    const a = clampX(ta);
    const b = clampX(tb);
    if (b - a < 1) return;
    el("rect", { x: a, y: 8, width: b - a, height: 30, class: cls }, svg);
    if (b - a > 90) text(svg, a + 6, 28, label, { class: "lane-label" });
  };
  seg(xs[0], Math.min(tFlag, tEnd), "lane-est", "estimator");
  seg(Math.min(tFlag, tEnd), tEnd, "lane-min", "min(estimator, altimeter)");
  text(svg, ML, 52, "rule active (source code applied to the recorded flag)", { class: "ax-caption" });
  // Per-sample lower-source marks (derived, approximate).
  const rowAlt = 72;
  const rowEst = 96;
  text(svg, ML - 6, rowAlt + 4, "altimeter", { class: "lane-rowlabel", "text-anchor": "end" });
  text(svg, ML - 6, rowEst + 4, "estimator", { class: "lane-rowlabel", "text-anchor": "end" });
  el("line", { x1: ML, y1: rowAlt, x2: width - MR, y2: rowAlt, class: "grid" }, svg);
  el("line", { x1: ML, y1: rowEst, x2: width - MR, y2: rowEst, class: "grid" }, svg);
  const lower = model.series("lower_source").values;
  visible(xs, t0, t1).forEach((i) => {
    if (lower[i] === null) return;
    if (lower[i] === "altimeter") shape(svg, "triangle", X(xs[i]), rowAlt, 2.8, "pt-alt");
    else shape(svg, "circle", X(xs[i]), rowEst, 2.8, "pt-est-lane");
  });
  const ev = model.data.events.find((e) => e.id === "altimeter_rejected");
  const x = clampX(tFlag);
  if (tFlag >= t0 && tFlag <= t1) el("line", { x1: x, y1: 4, x2: x, y2: H - 4, class: `ev-line ev-${ev.dash}` }, svg);
  const cx = X(xs[cursor]);
  if (xs[cursor] >= t0 - 1e-9 && xs[cursor] <= t1 + 1e-9) el("line", { x1: cx, y1: 4, x2: cx, y2: H - 4, class: "cursor-line" }, svg);
  return { X };
}

/** Pad plan at true scale. Window half-width in metres is a layout choice. */
export function drawPlan(svg, { model, size, half, cursor }) {
  clear(svg, size, size);
  const m = 30;
  const S = (size - 2 * m) / (2 * half);
  const px = (x) => m + (x + half) * S;
  const py = (y) => m + (half - y) * S;
  const inside = (x, y) => Math.abs(x) <= half && Math.abs(y) <= half;
  // Grid every 10 m in the pad frame.
  for (let g = -half; g <= half; g += 10) {
    el("line", { x1: px(g), y1: py(-half), x2: px(g), y2: py(half), class: "grid" }, svg);
    el("line", { x1: px(-half), y1: py(g), x2: px(half), y2: py(g), class: "grid" }, svg);
    text(svg, px(g), size - 10, formatNumber(g, 0), { class: "ax-label", "text-anchor": "middle" }, true);
    text(svg, m - 6, py(g) + 4, formatNumber(g, 0), { class: "ax-label", "text-anchor": "end" }, true);
  }
  text(svg, size / 2, 12, "north (y) up, east (x) right, metres", { class: "ax-caption", "text-anchor": "middle" });
  const padX = model.scalar("case.pad_x_m").v;
  const padY = model.scalar("case.pad_y_m").v;
  const r5 = model.scalar("case.r5_radius_m").v;
  el("circle", { cx: px(padX), cy: py(padY), r: r5 * S, class: "plan-r5" }, svg);
  el("line", { x1: px(padX) - 7, y1: py(padY), x2: px(padX) + 7, y2: py(padY), class: "plan-pad" }, svg);
  el("line", { x1: px(padX), y1: py(padY) - 7, x2: px(padX), y2: py(padY) + 7, class: "plan-pad" }, svg);
  // Trails up to the cursor, clipped to the window by omission of points outside it.
  const trail = (sx, sy, cls) => {
    let run = [];
    const flush = () => {
      if (run.length > 1) el("polyline", { points: run.join(" "), class: cls }, svg);
      run = [];
    };
    for (let i = 0; i <= cursor; i++) {
      const x = model.value(sx, i);
      const y = model.value(sy, i);
      if (inside(x - padX, y - padY)) run.push(`${px(x - padX).toFixed(1)},${py(y - padY).toFixed(1)}`);
      else flush();
    }
    flush();
  };
  trail("base_x", "base_y", "plan-trail-truth");
  trail("believed_nozzle_x", "believed_nozzle_y", "plan-trail-belief");
  // Fixed touchdown pair and the gap between them.
  const tx = model.scalar("td.true_nozzle_x").v - padX;
  const ty = model.scalar("td.true_nozzle_y").v - padY;
  const bx = model.scalar("td.believed_nozzle_x").v - padX;
  const by = model.scalar("td.believed_nozzle_y").v - padY;
  el("line", { x1: px(tx), y1: py(ty), x2: px(bx), y2: py(by), class: "plan-gap" }, svg);
  shape(svg, "diamond", px(bx), py(by), 6, "plan-belief");
  shape(svg, "circle", px(tx), py(ty), 6, "plan-truth");
  text(svg, px(tx) - 10, py(ty) + 4, "true", { class: "plan-label", "text-anchor": "end" });
  text(svg, px(bx), py(by) - 12, "believed", { class: "plan-label", "text-anchor": "middle" });
  // Cursor markers when inside the window.
  const cur = (sx, sy, kind, cls, r) => {
    const x = model.value(sx, cursor);
    const y = model.value(sy, cursor);
    if (x === null || y === null) return false;
    if (!inside(x - padX, y - padY)) return false;
    shape(svg, kind, px(x - padX), py(y - padY), r, cls);
    return true;
  };
  const shown = {
    truth: cur("base_x", "base_y", "circle", "plan-cur-truth", 3.5),
    belief: cur("believed_nozzle_x", "believed_nozzle_y", "diamond", "plan-cur-belief", 3.5),
    gnss: cur("gnss_x", "gnss_y", "square", "plan-cur-gnss", 3),
  };
  return { shown };
}
