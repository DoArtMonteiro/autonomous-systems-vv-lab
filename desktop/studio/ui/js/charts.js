// Generic telemetry: uPlot charts built from record.channels, grouped by (channel group or unit,
// timebase). Charts are built once per record and selection; the shared time cursor only moves an
// overlay line and updates text readouts, so scrubbing never rebuilds a chart. Null samples stay
// null and draw as gaps.

import uPlot from '../vendor/uplot/uPlot.esm.js';
import { h, clear, num, lowerIndex, nextId, icon, words } from './dom.js';
import { KINDS, KIND_LETTER, bandK } from './model.js';
import { pref, setPref } from './store.js';

export const SERIES = ['#56B4E9', '#E69F00', '#009E73', '#CC79A7', '#5B8FD9', '#D55E00', '#C9B800', '#9AA0A6'];
const DASH = { truth: [], observation: [], estimate: [7, 3], uncertainty: [2, 3], command: [], metric: [], limit: [4, 4] };
const WIDTH = { truth: 1.7, observation: 1.1, estimate: 1.5, uncertainty: 1.2, command: 1.3, metric: 1.3, limit: 1.2 };

export function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function isEnumerated(values) {
  const set = new Set();
  for (const v of values) {
    if (v === null) continue;
    if (!Number.isInteger(v)) return false;
    set.add(v);
    if (set.size > 6) return false;
  }
  return set.size > 0;
}

function alpha(hex, a) {
  const m = /^#([0-9a-f]{6})$/i.exec(hex);
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

/** Shared axis styling read from the theme tokens. */
export function axisStyle() {
  const muted = cssVar('--fg-3');
  const rule = cssVar('--rule');
  const font = `11px ${cssVar('--mono')}`;
  return {
    stroke: muted,
    font,
    grid: { stroke: rule, width: 1 },
    ticks: { stroke: rule, width: 1, size: 4 },
    border: { show: false },
  };
}

/** Draws fault windows (from the request) as a faint band behind the series. */
export function faultWindowHook(windows) {
  return (u) => {
    if (!windows.length) return;
    const { ctx } = u;
    const { top, height } = u.bbox;
    ctx.save();
    ctx.fillStyle = cssVar('--fault-wash');
    for (const w of windows) {
      const x0 = u.valToPos(w.start, 'x', true);
      const x1 = u.valToPos(Math.max(w.end, w.start), 'x', true);
      const l = Math.max(u.bbox.left, x0);
      const r = Math.min(u.bbox.left + u.bbox.width, Math.max(x1, x0 + 2));
      if (r > l) ctx.fillRect(l, top, r - l, height);
    }
    ctx.restore();
  };
}

/** A vertical cursor line inside a uPlot over layer; moved with a transform only. */
export function cursorLine(u) {
  const line = h('div', { class: 'u-appcursor', 'aria-hidden': 'true' });
  u.over.appendChild(line);
  return (t) => {
    const x = u.valToPos(t, 'x');
    if (!Number.isFinite(x) || x < 0 || x > u.over.clientWidth) line.style.opacity = '0';
    else {
      line.style.opacity = '1';
      line.style.transform = `translateX(${x}px)`;
    }
  };
}

export class Telemetry {
  /**
   * @param host element to render into
   * @param model record model (see model.js)
   * @param cursor TimeCursor
   * @param opts {domainId, timeUnit, onPick(t)}
   */
  constructor(host, model, cursor, opts) {
    this.host = host;
    this.model = model;
    this.cursor = cursor;
    this.opts = opts;
    this.syncKey = nextId('sync');
    this.charts = [];
    this.zooming = false;
    const saved = (pref('signals') || {})[opts.domainId];
    const ids = new Set(model.channels.map((c) => c.id));
    this.selected = new Set(saved && Array.isArray(saved.ids) ? saved.ids.filter((id) => ids.has(id)) : model.channels.map((c) => c.id));
    if (!this.selected.size) this.selected = new Set(ids);
    this.arrange = saved && saved.arrange === 'unit' ? 'unit' : 'group';
    this.windows = (model.record.request.faults || []).map((f) => ({ start: f.start, end: f.end, kind: f.kind }));
    this.build();
    this.unsub = cursor.subscribe((t) => this.setTime(t));
    this.ro = new ResizeObserver(() => this.resize());
    this.ro.observe(this.list);
  }

  persist() {
    const all = { ...(pref('signals') || {}) };
    all[this.opts.domainId] = { ids: [...this.selected], arrange: this.arrange };
    setPref('signals', all);
  }

  build() {
    clear(this.host);
    this.count = h('span', { class: 'mono dim' });
    this.pickerBtn = h('button', { class: 'btn btn-quiet', type: 'button', 'aria-haspopup': 'dialog', 'aria-expanded': 'false', onclick: () => this.togglePicker() }, icon('search'), 'Signals');
    const arrange = h('div', { class: 'seg', role: 'radiogroup', 'aria-label': 'Arrange charts' },
      ...['group', 'unit'].map((a) => h('button', {
        type: 'button', role: 'radio', class: 'seg-btn', 'aria-checked': String(this.arrange === a),
        onclick: (e) => {
          this.arrange = a;
          for (const b of e.currentTarget.parentNode.children) b.setAttribute('aria-checked', String(b === e.currentTarget));
          this.persist();
          this.rebuildCharts();
        },
      }, a === 'group' ? 'By group' : 'By unit')));
    const reset = h('button', { class: 'btn btn-quiet', type: 'button', title: 'Reset the time zoom of every chart', onclick: () => this.resetZoom() }, icon('reset'), 'Reset zoom');
    this.head = h('div', { class: 'tele-head' }, h('h2', { class: 'pane-title' }, 'Telemetry'), this.count, h('div', { class: 'spacer' }), arrange, reset, this.pickerBtn);
    this.note = h('p', { class: 'tele-note' });
    this.list = h('div', { class: 'tele-list', tabindex: '-1' });
    this.picker = this.buildPicker();
    this.host.append(this.head, this.picker, this.note, this.list);
    this.rebuildCharts();
  }

  chartGroups() {
    const chans = this.model.channels.filter((c) => this.selected.has(c.id));
    // A group that mixes units is split by unit, so one large signal never flattens the others.
    const unitsOf = new Map();
    for (const c of chans) {
      if (!unitsOf.has(c.group)) unitsOf.set(c.group, new Set());
      unitsOf.get(c.group).add(c.unit);
    }
    const groups = new Map();
    for (const c of chans) {
      const byUnit = this.arrange === 'unit';
      const split = !byUnit && unitsOf.get(c.group).size > 1;
      const key = `${byUnit ? c.unit || 'no unit' : c.group}\u0000${split ? c.unit : ''}\u0000${c.timebase}`;
      const title = byUnit ? (c.unit ? `Unit: ${c.unit}` : 'Dimensionless') : split ? `${c.group} · ${c.unit || 'dimensionless'}` : c.group;
      if (!groups.has(key)) groups.set(key, { title, timebase: c.timebase, channels: [] });
      groups.get(key).channels.push(c);
    }
    return [...groups.values()];
  }

  rebuildCharts() {
    for (const c of this.charts) c.u.destroy();
    this.charts = [];
    if (!this.list) return;
    clear(this.list);
    const groups = this.chartGroups();
    const total = this.model.channels.length;
    this.count.textContent = `${this.selected.size} of ${total} signals`;
    if (!total) {
      this.list.append(h('p', { class: 'empty' }, 'This record has no channels.'));
      return;
    }
    if (!groups.length) {
      this.list.append(h('p', { class: 'empty' }, 'No signal selected. Open Signals to choose some.'));
      return;
    }
    const { k, declared } = bandK(this.model.record);
    const anyBand = groups.some((g) => g.channels.some((c) => this.model.bands.has(c.id)));
    this.note.textContent = [
      'Drag across a chart to zoom in time; double-click or Reset zoom to restore. Gaps are samples without a value.',
      anyBand ? `Shaded bands are ±${num(k)}σ of the uncertainty the controller declares${declared ? ` (k = ${num(k)} is the gate this controller declares in the record)` : ', k = 1'}: around the estimate, and around zero on estimation-error charts, where the true error should stay inside.` : '',
      this.windows.length ? 'Tinted spans are injected fault windows.' : '',
    ].filter(Boolean).join(' ');
    for (const g of groups) this.charts.push(this.makeChart(g, k));
    this.setTime(this.cursor.t);
  }

  makeChart(g, k) {
    const times = this.model.timebases[g.timebase] || [];
    const data = [times];
    const series = [{}];
    const legend = [];
    const bands = [];
    let ci = 0;
    for (const c of g.channels) {
      const colour = c.kind === 'limit' ? cssVar('--limit') : SERIES[ci++ % SERIES.length];
      const stepped = c.kind === 'command' || isEnumerated(c.values);
      const idx = data.length;
      data.push(c.values);
      series.push({
        label: c.label,
        stroke: colour,
        width: WIDTH[c.kind] || 1.3,
        dash: DASH[c.kind] || [],
        spanGaps: false,
        points: { show: false },
        paths: stepped ? uPlot.paths.stepped({ align: 1 }) : undefined,
      });
      legend.push({ c, colour, idx });
      const pair = this.model.bands.get(c.id);
      const sigma = pair && this.model.byId.get(pair.sigma);
      if (sigma) {
        const centre = (v) => (pair.around === 'zero' ? 0 : v);
        const hi = c.values.map((v, i) => (v === null || sigma.values[i] === null ? null : centre(v) + k * sigma.values[i]));
        const lo = c.values.map((v, i) => (v === null || sigma.values[i] === null ? null : centre(v) - k * sigma.values[i]));
        const hiIdx = data.length;
        data.push(hi, lo);
        series.push({ label: `${c.label} +kσ`, stroke: 'transparent', width: 0, spanGaps: false, points: { show: false } },
          { label: `${c.label} -kσ`, stroke: 'transparent', width: 0, spanGaps: false, points: { show: false } });
        bands.push({ series: [hiIdx, hiIdx + 1], fill: alpha(colour, 0.16) });
        legend[legend.length - 1].band = { sigma, around: pair.around };
      }
    }
    const readouts = legend.map((l) => {
      const val = h('span', { class: 'ro-val mono' }, '');
      const row = h('li', { class: 'ro', title: `${l.c.id}: ${l.c.label}` },
        h('span', { class: ['swatch', `k-${l.c.kind}`], style: { '--sw': l.colour } }),
        h('span', { class: 'kind-badge', title: l.c.kind }, KIND_LETTER[l.c.kind] || '?'),
        h('span', { class: 'ro-label' }, l.c.label),
        val,
        h('span', { class: 'ro-unit mono dim' }, l.c.unit));
      return { ...l, val, row };
    });
    const units = [...new Set(g.channels.map((c) => c.unit).filter(Boolean))];
    const bandText = readouts.filter((r) => r.band).map((r) => `${r.c.id}: ${r.band.around === 'zero' ? '0' : 'estimate'} ± ${num(k)}·${r.band.sigma.id}`).join(', ');
    const plotEl = h('div', { class: 'chart-plot' });
    const wrap = h('section', { class: 'chart', 'aria-label': `${g.title} chart` },
      h('header', { class: 'chart-head' },
        h('h3', null, g.title),
        h('span', { class: 'mono dim' }, units.join(', ')),
        bandText ? h('span', { class: 'tag band-tag', title: 'Shaded band: the uncertainty the controller declares, times k' }, `band ${bandText}`) : null,
        this.model.timebases && Object.keys(this.model.timebases).length > 1 ? h('span', { class: 'tag' }, `timebase ${g.timebase}`) : null),
      h('ul', { class: 'readouts' }, readouts.map((r) => r.row)),
      plotEl);
    this.list.appendChild(wrap);
    const ax = axisStyle();
    const width = Math.max(240, plotEl.clientWidth || this.list.clientWidth - 24);
    const height = g.channels.length > 4 ? 170 : 140;
    const unit = this.opts.timeUnit;
    const opts = {
      width,
      height,
      legend: { show: false },
      cursor: {
        sync: { key: this.syncKey, setSeries: false },
        drag: { x: true, y: false, setScale: true },
        points: { show: false },
        focus: { prox: -1 },
      },
      select: { show: true },
      scales: { x: { time: false } },
      axes: [
        { ...ax, size: 28, values: (u, vals) => vals.map((v) => (unit === 'tick' ? String(Math.round(v)) : num(v, 3))) },
        { ...ax, size: 52, values: (u, vals) => vals.map((v) => num(v, 3)) },
      ],
      series,
      bands,
      hooks: {
        drawClear: [faultWindowHook(this.windows)],
        setScale: [(u, key) => { if (key === 'x') this.syncZoom(u); }],
      },
    };
    const u = new uPlot(opts, data, plotEl);
    const line = cursorLine(u);
    let downX = null;
    u.over.addEventListener('mousedown', (e) => { downX = e.clientX; });
    u.over.addEventListener('mouseup', (e) => {
      if (downX !== null && Math.abs(e.clientX - downX) < 3) {
        const rect = u.over.getBoundingClientRect();
        const t = u.posToVal(e.clientX - rect.left, 'x');
        if (Number.isFinite(t)) this.opts.onPick(t);
      }
      downX = null;
    });
    u.over.addEventListener('dblclick', () => this.resetZoom());
    return { u, line, readouts, times, plotEl, wrap };
  }

  syncZoom(src) {
    if (this.zooming) return;
    this.zooming = true;
    const { min, max } = src.scales.x;
    for (const c of this.charts) if (c.u !== src) c.u.setScale('x', { min, max });
    this.zooming = false;
    this.setTime(this.cursor.t);
  }

  resetZoom() {
    this.zooming = true;
    for (const c of this.charts) {
      const t = c.times;
      if (t.length) c.u.setScale('x', { min: t[0], max: t[t.length - 1] });
    }
    this.zooming = false;
    this.setTime(this.cursor.t);
  }

  setTime(t) {
    for (const c of this.charts) {
      c.line(t);
      const i = lowerIndex(c.times, t);
      for (const r of c.readouts) {
        const v = i >= 0 ? r.c.values[i] : null;
        const text = v === null || v === undefined ? 'gap' : num(v, 5);
        if (r.val.textContent !== text) r.val.textContent = text;
      }
    }
  }

  resize() {
    for (const c of this.charts) {
      const w = Math.max(240, c.plotEl.clientWidth);
      if (Math.abs(w - c.u.width) > 1) c.u.setSize({ width: w, height: c.u.height });
    }
    this.setTime(this.cursor.t);
  }

  /** Selects exactly these channel ids (used by "what to look at" links). Returns true if any matched. */
  focusChannels(ids) {
    const valid = ids.filter((id) => this.model.byId.has(id));
    if (!valid.length) return false;
    for (const id of valid) this.selected.add(id);
    this.rebuildCharts();
    const first = this.charts.find((c) => c.readouts.some((r) => valid.includes(r.c.id)));
    if (first) {
      first.wrap.scrollIntoView({ block: 'nearest', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
      first.wrap.classList.add('flash');
      setTimeout(() => first.wrap.classList.remove('flash'), 1200);
    }
    return true;
  }

  // ------------------------------------------------------------------------- signal picker

  buildPicker() {
    const panel = h('div', { class: 'picker', role: 'dialog', 'aria-label': 'Choose signals', hidden: true });
    const search = h('input', { type: 'search', class: 'input', placeholder: 'Search signals by name, id or unit', 'aria-label': 'Search signals' });
    const kinds = new Set(KINDS);
    const kindRow = h('div', { class: 'chips', role: 'group', 'aria-label': 'Filter by kind' });
    const body = h('div', { class: 'picker-body' });
    const present = new Set(this.model.channels.map((c) => c.kind));
    for (const k of KINDS.filter((x) => present.has(x))) {
      const b = h('button', { type: 'button', class: 'chip', 'aria-pressed': 'true', onclick: () => {
        if (kinds.has(k)) kinds.delete(k); else kinds.add(k);
        b.setAttribute('aria-pressed', String(kinds.has(k)));
        render();
      } }, h('span', { class: 'kind-badge' }, KIND_LETTER[k]), k);
      kindRow.appendChild(b);
    }
    const apply = () => { this.persist(); this.rebuildCharts(); render(); };
    const render = () => {
      clear(body);
      const q = search.value.trim().toLowerCase();
      const groups = new Map();
      for (const c of this.model.channels) {
        if (!kinds.has(c.kind)) continue;
        if (q && !`${c.id} ${c.label} ${c.unit} ${c.group}`.toLowerCase().includes(q)) continue;
        if (!groups.has(c.group)) groups.set(c.group, []);
        groups.get(c.group).push(c);
      }
      if (!groups.size) body.append(h('p', { class: 'empty' }, 'No signal matches.'));
      for (const [g, list] of groups) {
        const allOn = list.every((c) => this.selected.has(c.id));
        body.append(h('div', { class: 'pick-group' },
          h('div', { class: 'pick-group-head' },
            h('span', { class: 'pick-group-title' }, g),
            h('button', { type: 'button', class: 'link', onclick: () => {
              for (const c of list) { if (allOn) this.selected.delete(c.id); else this.selected.add(c.id); }
              apply();
            } }, allOn ? 'None' : 'All')),
          list.map((c) => {
            const id = nextId('sig');
            return h('div', { class: 'pick-row' },
              h('input', { type: 'checkbox', id, checked: this.selected.has(c.id), onchange: (e) => {
                if (e.target.checked) this.selected.add(c.id); else this.selected.delete(c.id);
                apply();
              } }),
              h('label', { for: id },
                h('span', { class: 'kind-badge', title: c.kind }, KIND_LETTER[c.kind] || '?'),
                h('span', null, c.label),
                h('span', { class: 'mono dim' }, ` ${c.id}${c.unit ? ` · ${c.unit}` : ''}`)));
          })));
      }
    };
    search.addEventListener('input', render);
    const foot = h('div', { class: 'picker-foot' },
      h('button', { type: 'button', class: 'btn btn-quiet', onclick: () => { this.selected = new Set(this.model.channels.map((c) => c.id)); apply(); } }, 'Select all'),
      h('button', { type: 'button', class: 'btn btn-quiet', onclick: () => { this.selected.clear(); apply(); } }, 'Clear'),
      h('div', { class: 'spacer' }),
      h('button', { type: 'button', class: 'btn', onclick: () => this.togglePicker(false) }, 'Done'));
    panel.addEventListener('keydown', (e) => { if (e.key === 'Escape') { e.stopPropagation(); this.togglePicker(false); } });
    panel.append(h('div', { class: 'picker-top' }, search, kindRow), body, foot);
    this.pickerSearch = search;
    render();
    return panel;
  }

  togglePicker(force) {
    const open = force !== undefined ? force : this.picker.hidden;
    this.picker.hidden = !open;
    this.pickerBtn.setAttribute('aria-expanded', String(open));
    if (open) this.pickerSearch.focus();
    else this.pickerBtn.focus();
  }

  dispose() {
    this.unsub();
    this.ro.disconnect();
    for (const c of this.charts) c.u.destroy();
    this.charts = [];
  }
}

export { words };
