// Application state shared by the views: platform info, domains, preferences and the open work
// (one run, or a set of runs being compared). Views subscribe to named topics.

import { api, logUiError } from './api.js';
import { debounce } from './dom.js';

const listeners = new Map();

export function on(topic, fn) {
  if (!listeners.has(topic)) listeners.set(topic, new Set());
  listeners.get(topic).add(fn);
  return () => listeners.get(topic).delete(fn);
}

export function emit(topic, payload) {
  for (const fn of listeners.get(topic) || []) {
    try {
      fn(payload);
    } catch (e) {
      logUiError(`listener ${topic}: ${e && e.stack ? e.stack : e}`);
      console.error(e);
    }
  }
}

export const state = {
  info: null,
  domains: [],
  rejected: [],
  prefs: {},
  /** run_id -> RunRecord cache (records are immutable once stored). */
  records: new Map(),
  /** The open run workspace: {runId, record}. */
  current: null,
  /** The open comparison: {runIds, records, errors, name}. */
  comparison: null,
};

const DEFAULT_PREFS = {
  theme: 'system',
  showDeveloperDomains: false,
  parameterView: 'beginner',
  playbackSpeed: 1,
  lastDomain: null,
  signals: {},
};

export function pref(key) {
  return key in state.prefs ? state.prefs[key] : DEFAULT_PREFS[key];
}

const persist = debounce(() => {
  api.setPrefs(state.prefs).catch((e) => logUiError(`set_prefs: ${e.message}`));
}, 400);

export function setPref(key, value) {
  state.prefs = { ...state.prefs, [key]: value };
  persist();
  emit('prefs', { key, value });
}

export async function loadPrefs() {
  try {
    const p = await api.getPrefs();
    state.prefs = p && typeof p === 'object' ? p : {};
  } catch (e) {
    state.prefs = {};
    logUiError(`get_prefs: ${e.message}`);
  }
}

/** Domains visible in the product UI under the current preference. */
export function visibleDomains() {
  const dev = pref('showDeveloperDomains');
  return state.domains.filter((d) => dev || d.manifest.user_facing);
}

export function domainById(id) {
  return state.domains.find((d) => d.manifest.id === id) || null;
}

export async function loadRecord(runId) {
  if (state.records.has(runId)) return state.records.get(runId);
  const rec = await api.record(runId);
  state.records.set(runId, rec);
  return rec;
}
