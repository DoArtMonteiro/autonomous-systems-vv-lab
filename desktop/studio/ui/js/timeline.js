// Transport (play, step, event jumps, speed, scrubber) and the event swimlanes of a run. Events are
// drawn from record.events by source lane and severity; the injected fault windows come from the
// stored request. Selecting an event moves the shared cursor to its instant.

import { h, clear, icon, timeText, num, words } from './dom.js';
import { SOURCES } from './model.js';
import { pref, setPref } from './store.js';

const SPEEDS_S = [0.25, 0.5, 1, 2, 4, 8];
const SPEEDS_TICK = [0.5, 1, 2, 5, 10];
const SEVERITY_TEXT = { info: 'information', fault: 'fault', detection: 'detection', mode: 'mode change', warning: 'warning', violation: 'violation' };

export class Timeline {
  constructor(host, model, cursor, opts) {
    this.host = host;
    this.model = model;
    this.cursor = cursor;
    this.opts = opts;
    this.unit = opts.timeUnit;
    this.selected = null;
    this.build();
    this.unsub = cursor.subscribe((t) => this.setTime(t));
    this.unplay = cursor.onPlayState((p) => this.setPlaying(p));
    this.ro = new ResizeObserver(() => this.setTime(this.cursor.t));
    this.ro.observe(this.track);
    this.setTime(cursor.t);
  }

  frac(t) {
    const { t0, t1 } = this.model;
    return (t - t0) / (t1 - t0);
  }

  build() {
    clear(this.host);
    const c = this.cursor;
    this.playBtn = h('button', { type: 'button', class: 'tbtn tbtn-main', 'aria-label': 'Play (Space)', title: 'Play or pause (Space)', onclick: () => c.toggle() }, icon('play'));
    const btn = (name, label, fn) => h('button', { type: 'button', class: 'tbtn', 'aria-label': label, title: label, onclick: fn }, icon(name));
    this.timeText = h('output', { class: 'time-now mono', 'aria-live': 'off' });
    const speeds = this.unit === 'tick' ? SPEEDS_TICK : SPEEDS_S;
    const saved = pref('playbackSpeed');
    c.speed = speeds.includes(saved) ? saved : 1;
    const speed = h('select', { class: 'select select-sm', 'aria-label': 'Playback speed', onchange: (e) => { c.speed = Number(e.target.value); setPref('playbackSpeed', c.speed); } },
      speeds.map((s) => h('option', { value: String(s), selected: s === c.speed }, this.unit === 'tick' ? `${s * 10} ticks/s` : `${s}×`)));
    const transport = h('div', { class: 'transport' },
      btn('prev', 'Previous event ([)', () => this.jump(-1)),
      btn('stepb', 'Step back one sample (Left)', () => c.step(-1)),
      this.playBtn,
      btn('stepf', 'Step forward one sample (Right)', () => c.step(1)),
      btn('next', 'Next event (])', () => this.jump(1)),
      this.timeText,
      h('span', { class: 'time-end mono dim' }, `of ${timeText(this.model.t1, this.unit)}`),
      h('div', { class: 'spacer' }),
      h('label', { class: 'dim small' }, 'Speed ', speed));

    // Track: one coordinate system shared by the scrubber and every lane.
    const present = new Set(this.model.events.map((e) => e.source));
    const lanes = [...SOURCES.filter((s) => present.has(s) || s === 'fault'), ...[...present].filter((s) => !SOURCES.includes(s))];
    this.cursorLine = h('div', { class: 'tl-cursor', 'aria-hidden': 'true' });
    this.scrub = h('div', {
      class: 'tl-scrub', role: 'slider', tabindex: '0', 'aria-label': 'Time cursor',
      'aria-valuemin': String(this.model.t0), 'aria-valuemax': String(this.model.t1),
    });
    this.scrub.addEventListener('keydown', (e) => {
      const span = this.model.t1 - this.model.t0;
      if (e.key === 'Home') { c.set(this.model.t0); e.preventDefault(); }
      else if (e.key === 'End') { c.set(this.model.t1); e.preventDefault(); }
      else if (e.key === 'PageUp') { c.set(c.t - span / 10); e.preventDefault(); }
      else if (e.key === 'PageDown') { c.set(c.t + span / 10); e.preventDefault(); }
    });
    const ticks = h('div', { class: 'tl-axis', 'aria-hidden': 'true' });
    const span = this.model.t1 - this.model.t0;
    const raw = span / 10;
    const p10 = 10 ** Math.floor(Math.log10(raw));
    let step = [1, 2, 5, 10].map((m) => m * p10).find((x) => x >= raw) || raw;
    if (this.unit === 'tick') step = Math.max(1, Math.round(step));
    for (let t = Math.ceil(this.model.t0 / step) * step; t <= this.model.t1 + 1e-9; t += step) {
      ticks.append(h('span', { class: 'tl-tick mono', style: { left: `${this.frac(t) * 100}%` } }, this.unit === 'tick' ? String(Math.round(t)) : num(t, 3)));
    }
    this.track = h('div', { class: 'tl-track' }, this.scrub, ticks);
    const rows = [];
    const windows = this.model.record.request.faults || [];
    for (const lane of lanes) {
      const laneTrack = h('div', { class: 'tl-lane-track' });
      if (lane === 'fault') {
        // One sub-row per injected window, so overlapping windows stay distinguishable.
        const n = Math.max(1, windows.length);
        const rowH = n > 1 ? 7 : 12;
        laneTrack.style.height = `${Math.max(18, 6 + n * (rowH + 2))}px`;
        windows.forEach((w, i) => {
          const a = this.frac(w.start);
          const b = this.frac(Math.max(w.end, w.start));
          laneTrack.append(h('div', { class: 'tl-window', style: { left: `${a * 100}%`, width: `max(2px, ${(b - a) * 100}%)`, top: `${3 + i * (rowH + 2)}px`, height: `${rowH}px` }, title: `${words(w.kind)} window ${timeText(w.start, this.unit)} to ${timeText(w.end, this.unit)}` }));
        });
      }
      for (const e of this.model.events.filter((x) => x.source === lane)) {
        const m = h('button', {
          type: 'button', class: ['tl-mark', `sev-${e.severity}`], style: { left: `${this.frac(e.t) * 100}%` },
          'aria-label': `${timeText(e.t, this.unit)}, ${SEVERITY_TEXT[e.severity] || e.severity}: ${e.label}`,
          title: `${timeText(e.t, this.unit)} · ${e.label}`,
          onclick: (ev) => { ev.stopPropagation(); this.select(e); },
        });
        e.el = m;
        laneTrack.append(m);
      }
      rows.push(h('div', { class: 'tl-lane' }, h('span', { class: 'tl-lane-label' }, lane), laneTrack));
    }
    this.lanesEl = h('div', { class: 'tl-lanes' }, rows);
    this.trackArea = h('div', { class: 'tl-area' }, h('div', { class: 'tl-grid' }, h('span', { class: 'tl-lane-label' }, ''), this.track), this.lanesEl, this.cursorLine);
    // Pointer scrubbing on the scrubber and on the lane background.
    const toT = (clientX) => {
      const r = this.track.getBoundingClientRect();
      const f = Math.min(1, Math.max(0, (clientX - r.left) / r.width));
      return this.model.t0 + f * (this.model.t1 - this.model.t0);
    };
    const startDrag = (e) => {
      if (e.button !== 0 || e.target.closest('.tl-mark')) return;
      c.pause();
      c.set(toT(e.clientX));
      const move = (ev) => c.set(toT(ev.clientX));
      const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); };
      window.addEventListener('pointermove', move);
      window.addEventListener('pointerup', up);
    };
    this.scrub.addEventListener('pointerdown', startDrag);
    this.lanesEl.addEventListener('pointerdown', startDrag);
    this.detail = h('div', { class: 'tl-detail', 'aria-live': 'polite' }, h('span', { class: 'dim' }, this.model.events.length ? `${this.model.events.length} events. Select a marker, or press [ and ] to step through them.` : 'This run recorded no events.'));
    this.host.append(transport, this.trackArea, this.detail);
  }

  setPlaying(p) {
    this.playBtn.replaceChildren(icon(p ? 'pause' : 'play'));
    this.playBtn.setAttribute('aria-label', p ? 'Pause (Space)' : 'Play (Space)');
  }

  setTime(t) {
    const f = this.frac(t);
    const r = this.track.getBoundingClientRect();
    const area = this.trackArea.getBoundingClientRect();
    const x = r.left - area.left + f * r.width;
    this.cursorLine.style.transform = `translateX(${x}px)`;
    const text = timeText(t, this.unit);
    if (this.timeText.textContent !== text) this.timeText.textContent = text;
    this.scrub.setAttribute('aria-valuenow', String(t));
    this.scrub.setAttribute('aria-valuetext', text);
  }

  jump(dir) {
    const t = dir > 0 ? this.cursor.nextEvent() : this.cursor.prevEvent();
    if (t !== undefined) {
      const e = this.model.events.find((x) => Math.abs(x.t - t) < 1e-9);
      if (e) this.select(e, false);
    }
  }

  select(e, move = true) {
    if (this.selected && this.selected.el) this.selected.el.classList.remove('is-selected');
    this.selected = e;
    if (e.el) e.el.classList.add('is-selected');
    if (move) {
      this.cursor.pause();
      this.cursor.set(e.t);
    }
    const same = this.model.events.filter((x) => Math.abs(x.t - e.t) < 1e-9);
    clear(this.detail);
    this.detail.append(h('span', { class: 'mono tl-detail-t' }, timeText(e.t, this.unit)));
    const list = h('ul', { class: 'tl-detail-list' });
    for (const x of same) {
      const kv = Object.entries(x.detail && typeof x.detail === 'object' ? x.detail : {}).slice(0, 6)
        .map(([k, v]) => `${k} ${typeof v === 'number' ? num(v, 5) : typeof v === 'string' ? v : JSON.stringify(v)}`).join(' · ');
      list.append(h('li', { class: x === e ? 'is-current' : '' },
        h('span', { class: ['sev', `sev-${x.severity}`] }, SEVERITY_TEXT[x.severity] || x.severity),
        h('span', { class: 'tag' }, x.source),
        h('span', null, x.label),
        kv ? h('span', { class: 'mono dim small' }, kv) : null));
    }
    this.detail.append(list);
    if (this.opts.onEvent) this.opts.onEvent(e);
  }

  dispose() {
    this.unsub();
    this.unplay();
    this.ro.disconnect();
  }
}
