// DOM construction helpers. Data never goes through innerHTML: every node is built here and text is
// set with textContent, so a label or note from a domain host cannot inject markup.

const SVG_NS = 'http://www.w3.org/2000/svg';

function apply(el, attrs) {
  if (!attrs) return el;
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') el.setAttribute('class', Array.isArray(v) ? v.filter(Boolean).join(' ') : v);
    else if (k === 'text') el.textContent = String(v);
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else if (k === 'dataset') Object.assign(el.dataset, v);
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else if (k === 'value' && 'value' in el) el.value = v;
    else if (k === 'checked' || k === 'disabled' || k === 'selected' || k === 'hidden') el[k] = Boolean(v);
    else el.setAttribute(k, v === true ? '' : String(v));
  }
  return el;
}

function append(el, children) {
  for (const c of children) {
    if (c === null || c === undefined || c === false) continue;
    if (Array.isArray(c)) append(el, c);
    else if (c instanceof Node) el.appendChild(c);
    else el.appendChild(document.createTextNode(String(c)));
  }
  return el;
}

/** h('div', {class: 'x'}, child, 'text', [more]) */
export function h(tag, attrs, ...children) {
  if (attrs instanceof Node || typeof attrs === 'string' || Array.isArray(attrs)) {
    children.unshift(attrs);
    attrs = null;
  }
  return append(apply(document.createElement(tag), attrs), children);
}

export function s(tag, attrs, ...children) {
  return append(apply(document.createElementNS(SVG_NS, tag), attrs), children);
}

export function clear(el) {
  while (el.firstChild) el.removeChild(el.firstChild);
  return el;
}

export function replace(el, ...children) {
  clear(el);
  return append(el, children);
}

/** Small inline icons drawn as SVG paths (no icon font, no external files). */
const ICONS = {
  play: 'M6 4l10 6-10 6z',
  pause: 'M5 4h3.5v12H5zM11.5 4H15v12h-3.5z',
  stepb: 'M5 4h2v12H5zM16 4v12L8 10z',
  stepf: 'M13 4h2v12h-2zM4 4v12l8-6z',
  prev: 'M4 4h2v12H4zM10 10l7-6v12z',
  next: 'M14 4h2v12h-2zM10 10L3 4v12z',
  check: 'M4 10.5l4 4 8-9',
  cross: 'M5 5l10 10M15 5L5 15',
  warn: 'M10 3l8 14H2zM10 8v4M10 14.2v.6',
  dash: 'M5 10h10',
  dot: 'M10 6a4 4 0 1 0 0.01 0',
  search: 'M8.5 3.5a5 5 0 1 0 0 10a5 5 0 1 0 0-10zM12.3 12.3L17 17',
  close: 'M5 5l10 10M15 5L5 15',
  chev: 'M7 5l5 5-5 5',
  reset: 'M4 10a6 6 0 1 0 2-4.5M4 3v3.5h3.5',
  folder: 'M3 5h5l2 2h7v9H3z',
  replay: 'M4 10a6 6 0 1 0 2-4.5M4 3v3.5h3.5M9 8v4l3-2z',
  export: 'M10 3v9M6 8l4 4 4-4M4 15h12',
  fault: 'M11 2L5 11h4l-1 7 6-9h-4z',
  info: 'M10 3a7 7 0 1 0 0.01 0M10 9v5M10 6.5v.5',
};

export function icon(name, cls) {
  const d = ICONS[name] || ICONS.dot;
  const filled = name === 'play' || name === 'pause' || name === 'stepb' || name === 'stepf' || name === 'prev' || name === 'next';
  return s('svg', { class: ['ico', cls], viewBox: '0 0 20 20', 'aria-hidden': 'true', focusable: 'false' },
    s('path', { d, fill: filled ? 'currentColor' : 'none', stroke: filled ? 'none' : 'currentColor', 'stroke-width': '1.6', 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }));
}

// ----------------------------------------------------------------------------- formatting

const nf = new Map();
function numberFormat(digits) {
  if (!nf.has(digits)) nf.set(digits, new Intl.NumberFormat('en-GB', { maximumFractionDigits: digits, minimumFractionDigits: 0, useGrouping: false }));
  return nf.get(digits);
}

/** A value with a sensible number of significant digits, in plain notation. */
export function num(v, sig = 4) {
  if (v === null || v === undefined || Number.isNaN(v)) return 'n/a';
  if (!Number.isFinite(v)) return v > 0 ? '+inf' : '-inf';
  const a = Math.abs(v);
  if (a === 0) return '0';
  if (a >= 1e7 || a < 1e-4) return v.toExponential(2);
  const digits = Math.max(0, Math.min(6, sig - 1 - Math.floor(Math.log10(a))));
  return numberFormat(digits).format(v);
}

export function withUnit(v, unit, sig) {
  const t = num(v, sig);
  return unit ? `${t} ${unit}` : t;
}

/** Time in the domain unit, fixed decimals for seconds and whole numbers for ticks. */
export function timeText(t, unit) {
  if (t === null || t === undefined || !Number.isFinite(t)) return 'n/a';
  if (unit === 'tick') return `tick ${Math.round(t)}`;
  return `${t.toFixed(2)} ${unit || ''}`.trim();
}

export function shortHash(hex, n = 12) {
  return typeof hex === 'string' ? hex.slice(0, n) : '';
}

/** Collapse runs of whitespace (catalog strings are wrapped in the Rust sources). */
export function prose(text) {
  return typeof text === 'string' ? text.replace(/\s+/g, ' ').trim() : '';
}

export function words(id) {
  return typeof id === 'string' ? id.replace(/_/g, ' ') : '';
}

let uid = 0;
export function nextId(prefix = 'id') {
  uid += 1;
  return `${prefix}-${uid}`;
}

export function debounce(fn, ms) {
  let t = 0;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

/** Index of the last element of a sorted array that is <= t (0 when t precedes it). */
export function lowerIndex(arr, t) {
  let lo = 0;
  let hi = arr.length - 1;
  if (hi < 0) return -1;
  if (t <= arr[0]) return 0;
  if (t >= arr[hi]) return hi;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (arr[mid] <= t) lo = mid;
    else hi = mid;
  }
  return lo;
}

/** Linear interpolation of a channel at time t, for display only. Returns null in a gap. */
export function sampleAt(times, values, t) {
  const i = lowerIndex(times, t);
  if (i < 0) return null;
  const a = values[i];
  if (i >= times.length - 1 || t <= times[i]) return a ?? null;
  const b = values[i + 1];
  if (a === null || a === undefined || b === null || b === undefined) return a ?? null;
  const f = (t - times[i]) / (times[i + 1] - times[i] || 1);
  return a + (b - a) * f;
}
