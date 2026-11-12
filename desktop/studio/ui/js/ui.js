// Small shared UI pieces: toasts, a modal form dialog, the shortcut help and the command palette.

import { h, clear, icon } from './dom.js';
import { errorOf } from './api.js';

const KIND_TEXT = { invalid: 'Invalid request', protected: 'Protected seed', not_found: 'Not found', host: 'Domain host error', io: 'Error' };

export function errorText(e) {
  const err = errorOf(e);
  return `${KIND_TEXT[err.kind] || err.kind}: ${err.message}`;
}

export function toast(message, kind = 'info', ms = 4200) {
  const host = document.getElementById('toasts');
  const el = h('div', { class: ['toast', `toast-${kind}`], role: kind === 'error' ? 'alert' : 'status' },
    h('span', null, message),
    h('button', { type: 'button', class: 'icon-btn', 'aria-label': 'Dismiss', onclick: () => el.remove() }, icon('close')));
  host.appendChild(el);
  if (ms) setTimeout(() => el.remove(), ms);
  return el;
}

let lastFocus = null;

/** A modal dialog built from DOM nodes. Returns {close}. Escape and the backdrop close it. */
export function modal({ title, body, actions, label, wide }) {
  const host = document.getElementById('modal-root');
  lastFocus = document.activeElement;
  clear(host);
  const titleId = 'modal-title';
  const box = h('div', { class: ['modal', wide ? 'modal-wide' : ''], role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': titleId, 'aria-label': label },
    h('header', { class: 'modal-head' }, h('h2', { id: titleId }, title),
      h('button', { type: 'button', class: 'icon-btn', 'aria-label': 'Close', onclick: () => close() }, icon('close'))),
    h('div', { class: 'modal-body' }, body),
    actions ? h('footer', { class: 'modal-foot' }, actions) : null);
  const backdrop = h('div', { class: 'backdrop', onclick: (e) => { if (e.target === backdrop) close(); } }, box);
  host.appendChild(backdrop);
  host.hidden = false;
  const onKey = (e) => {
    if (e.key === 'Escape') { e.preventDefault(); close(); }
    if (e.key === 'Tab') {
      const f = [...box.querySelectorAll('button, input, select, textarea, [tabindex]:not([tabindex="-1"])')].filter((x) => !x.disabled && x.offsetParent !== null);
      if (!f.length) return;
      if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
      else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
    }
  };
  box.addEventListener('keydown', onKey);
  function close() {
    host.hidden = true;
    clear(host);
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }
  setTimeout(() => {
    const first = box.querySelector('input, textarea, select') || box.querySelector('.modal-foot .btn-primary') || box.querySelector('button');
    if (first) first.focus();
  }, 0);
  return { close, box };
}

/** Asks for a name and notes. Resolves {name, notes} or null. */
export function askName({ title, label = 'Name', initial = '', confirm = 'Save' }) {
  return new Promise((resolve) => {
    const name = h('input', { class: 'input', type: 'text', value: initial, maxlength: '200', 'aria-label': label });
    const notes = h('textarea', { class: 'input', rows: '3', maxlength: '4000', 'aria-label': 'Notes' });
    const err = h('p', { class: 'error-text', role: 'alert' });
    let done = false;
    const finish = (v) => { if (!done) { done = true; m.close(); resolve(v); } };
    const ok = h('button', { type: 'button', class: 'btn btn-primary', onclick: () => {
      if (!name.value.trim()) { err.textContent = 'A name is required.'; name.focus(); return; }
      finish({ name: name.value.trim(), notes: notes.value });
    } }, confirm);
    const m = modal({
      title,
      body: [h('label', { class: 'field' }, h('span', { class: 'field-label' }, label), name), h('label', { class: 'field' }, h('span', { class: 'field-label' }, 'Notes (optional)'), notes), err],
      actions: [h('button', { type: 'button', class: 'btn btn-quiet', onclick: () => finish(null) }, 'Cancel'), ok],
    });
    name.addEventListener('keydown', (e) => { if (e.key === 'Enter') ok.click(); });
    const obs = new MutationObserver(() => { if (!m.box.isConnected) { obs.disconnect(); if (!done) { done = true; resolve(null); } } });
    obs.observe(document.getElementById('modal-root'), { childList: true });
  });
}

/** Asks to confirm an action that discards something. Resolves true to go on, false to stay. */
export function askConfirm({ title, message, confirm = 'Continue', cancel = 'Keep what I have' }) {
  return new Promise((resolve) => {
    let done = false;
    const finish = (v) => { if (!done) { done = true; m.close(); resolve(v); } };
    const m = modal({
      title,
      body: [h('p', null, message)],
      actions: [h('button', { type: 'button', class: 'btn btn-primary', dataset: { action: 'keep' }, onclick: () => finish(false) }, cancel),
        h('button', { type: 'button', class: 'btn', dataset: { action: 'discard' }, onclick: () => finish(true) }, confirm)],
    });
    const obs = new MutationObserver(() => { if (!m.box.isConnected) { obs.disconnect(); if (!done) { done = true; resolve(false); } } });
    obs.observe(document.getElementById('modal-root'), { childList: true });
  });
}

export const SHORTCUTS = [
  ['Space', 'Play or pause the mission or the run'],
  ['Left / Right', 'Step one recorded sample'],
  ['Shift + Left / Right', 'Step ten samples'],
  ['[ and ]', 'Previous or next event'],
  ['Home / End', 'Start or end of the run'],
  ['Ctrl + Enter', 'Run the mission being prepared'],
  ['Ctrl + K', 'Command and search palette'],
  ['1 to 8', 'Go to Home, Missions, Investigate, Configure, Analyse, Compare, Records, Settings'],
  ['?', 'This help'],
  ['Escape', 'Close a dialog or panel'],
];

export function showHelp() {
  modal({
    title: 'Keyboard shortcuts',
    body: h('table', { class: 'kv shortcuts' }, h('tbody', null, SHORTCUTS.map(([k, v]) => h('tr', null, h('th', { scope: 'row' }, h('kbd', null, k)), h('td', null, v))))),
    actions: [h('button', { type: 'button', class: 'btn btn-primary', onclick: () => document.querySelector('#modal-root .icon-btn').click() }, 'Close')],
  });
}

/**
 * Command palette. `source()` returns [{title, hint, group, run}] at open time; typing filters.
 */
export function palette(source) {
  const items = source();
  const input = h('input', { class: 'input palette-input', type: 'text', placeholder: 'Type a command, a demonstration or a run…', 'aria-label': 'Search commands', role: 'combobox', 'aria-expanded': 'true', 'aria-controls': 'palette-list', 'aria-autocomplete': 'list' });
  const list = h('ul', { class: 'palette-list', id: 'palette-list', role: 'listbox', 'aria-label': 'Results' });
  let active = 0;
  let shown = [];
  const render = () => {
    const q = input.value.trim().toLowerCase();
    shown = items.filter((i) => !q || `${i.title} ${i.hint || ''} ${i.group}`.toLowerCase().includes(q)).slice(0, 60);
    active = Math.min(active, Math.max(0, shown.length - 1));
    clear(list);
    shown.forEach((it, i) => {
      list.append(h('li', { role: 'option', id: `pal-${i}`, 'aria-selected': String(i === active), class: i === active ? 'is-active' : '', onclick: () => choose(i) },
        h('span', { class: 'tag' }, it.group), h('span', null, it.title), it.hint ? h('span', { class: 'dim small mono' }, it.hint) : null));
    });
    input.setAttribute('aria-activedescendant', shown.length ? `pal-${active}` : '');
    if (!shown.length) list.append(h('li', { class: 'empty' }, 'Nothing matches.'));
  };
  const m = modal({ title: 'Go to', body: [input, list], label: 'Command palette', wide: true });
  const choose = (i) => {
    const it = shown[i];
    if (!it) return;
    m.close();
    it.run();
  };
  input.addEventListener('input', () => { active = 0; render(); });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown') { active = Math.min(shown.length - 1, active + 1); render(); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { active = Math.max(0, active - 1); render(); e.preventDefault(); }
    else if (e.key === 'Enter') { choose(active); e.preventDefault(); }
  });
  render();
}
