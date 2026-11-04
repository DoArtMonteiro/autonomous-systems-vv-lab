// Entry point: startup state while the platform starts in the shell, theme, routing between the six
// workspaces, global keyboard shortcuts and the command palette.

import { api, logUiError } from './api.js';
import { h, clear, prose } from './dom.js';
import { state, loadPrefs, pref, on, emit, visibleDomains } from './store.js';
import { showHelp, palette, toast, errorText } from './ui.js';
import { initPrepare, showPrepare, runMission, startDemo, openSaved } from './views/prepare.js';
import { initRun, showRun, runKey, rethemeRun, runWorkspace } from './views/run.js';
import { initCompare, showCompare, compareKey, rethemeCompare } from './views/compare.js';
import { initLibrary, showLibrary } from './views/library.js';
import { initSettings, showSettings } from './views/settings.js';
import { initDiscover, showDiscover, rethemeDiscover } from './views/discover.js';
import { initHome, showHome } from './views/home.js';
import { initMissions, showMissions } from './views/missions.js';
import { initPlayer, showPlayer, playerKey, rethemePlayer, playerState } from './views/player.js';
import { EXPERIENCES } from './experiences.js';

// Keyboard digits follow this order; `mission` (the player) has no digit and lights "Missions".
const VIEWS = ['home', 'missions', 'discover', 'prepare', 'run', 'compare', 'library', 'settings', 'mission'];
const NAV_OF = { mission: 'missions' };
let currentView = null;

// ----------------------------------------------------------------------------- theme

const dark = matchMedia('(prefers-color-scheme: dark)');
function applyTheme() {
  const t = pref('theme');
  const resolved = t === 'light' || t === 'dark' ? t : dark.matches ? 'dark' : 'light';
  if (document.documentElement.dataset.theme !== resolved) {
    document.documentElement.dataset.theme = resolved;
    emit('theme', resolved);
  }
}
dark.addEventListener('change', applyTheme);
on('prefs', ({ key }) => { if (key === 'theme') applyTheme(); });
on('theme', () => { rethemeRun(); rethemeCompare(); rethemeDiscover(); rethemePlayer(); });

// ----------------------------------------------------------------------------- routing

export async function navigate(view, opts) {
  if (!VIEWS.includes(view)) return;
  currentView = view;
  for (const v of VIEWS) document.getElementById(`view-${v}`).hidden = v !== view;
  for (const b of document.querySelectorAll('.nav-btn')) {
    if (b.dataset.view === (NAV_OF[view] || view)) b.setAttribute('aria-current', 'page');
    else b.removeAttribute('aria-current');
  }
  try {
    if (view === 'home') showHome();
    else if (view === 'missions') showMissions(opts);
    else if (view === 'mission') await showPlayer(opts);
    else if (view === 'discover') await showDiscover(opts);
    else if (view === 'prepare') showPrepare();
    else if (view === 'run') await showRun(opts);
    else if (view === 'compare') await showCompare(opts);
    else if (view === 'library') await showLibrary(opts);
    else if (view === 'settings') showSettings();
  } catch (e) {
    logUiError(`navigate ${view}: ${e && e.stack ? e.stack : JSON.stringify(e)}`);
    toast(errorText(e), 'error');
  }
}

// ----------------------------------------------------------------------------- startup

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function setStatus(text, cls) {
  const el = document.getElementById('platform-status');
  el.textContent = text;
  el.className = `status-dot ${cls || ''}`;
}

async function loadDomains() {
  const list = await api.listDomains();
  state.domains = list.domains;
  state.rejected = list.rejected;
  emit('domains');
}

async function refreshInfo() {
  state.info = await api.appInfo();
}

function startupFailed(title, detail, rejected) {
  const box = document.getElementById('startup');
  box.classList.add('failed');
  document.getElementById('startup-text').textContent = title;
  const det = clear(document.getElementById('startup-detail'));
  if (detail) det.append(h('p', { class: 'error-text mono' }, detail));
  if (rejected && rejected.length) {
    det.append(h('h3', null, 'Rejected domain directories'), h('ul', null, rejected.map((r) => h('li', { class: 'small' }, h('span', { class: 'mono' }, r.dir), `: ${r.reason}`))));
  }
  det.append(h('div', { class: 'row', style: { marginTop: '10px' } }, h('button', { type: 'button', class: 'btn btn-primary', onclick: async () => {
    box.classList.remove('failed');
    document.getElementById('startup-text').textContent = 'Restarting the platform…';
    clear(det);
    try { await api.restartPlatform(); } catch (e) { logUiError(`restart: ${e.message}`); }
    boot();
  } }, 'Restart the platform')));
  setStatus('Platform error', 'bad');
}

async function boot() {
  const text = document.getElementById('startup-text');
  const t0 = performance.now();
  let info = null;
  for (;;) {
    try {
      info = await api.appInfo();
    } catch (e) {
      startupFailed('The desktop shell did not answer.', errorText(e));
      return;
    }
    if (info.ready || info.start_error) break;
    const s = (performance.now() - t0) / 1000;
    if (s > 2) text.textContent = `Starting the platform: discovering domain hosts and reading their catalogs (${s.toFixed(0)} s).`;
    if (s > 90) { startupFailed('The platform did not finish starting within 90 s.', 'See the studio log for details.'); return; }
    await sleep(150);
  }
  state.info = info;
  if (info.start_error) {
    startupFailed('The platform could not start.', info.start_error, []);
    return;
  }
  try {
    await loadDomains();
  } catch (e) {
    startupFailed('The domain list could not be read.', errorText(e));
    return;
  }
  const usable = state.domains.filter((d) => d.catalog);
  if (!usable.length) {
    startupFailed('No usable domain host was found.', state.domains.map((d) => `${d.manifest.id}: ${d.error}`).join('\n') || 'No domain directory was discovered.', state.rejected);
    return;
  }
  document.getElementById('startup').hidden = true;
  const broken = state.domains.filter((d) => !d.catalog);
  setStatus(`${visibleDomains().filter((d) => d.catalog).length} domains ready`, 'ok');
  if (state.rejected.length || broken.length) toast(`${state.rejected.length + broken.length} domain${state.rejected.length + broken.length > 1 ? 's' : ''} could not be loaded; see Settings for the reasons.`, 'error', 8000);
  navigate(currentView || 'home');
}

on('prefs', ({ key }) => {
  if (key === 'showDeveloperDomains' && state.info) setStatus(`${visibleDomains().filter((d) => d.catalog).length} domains ready`, 'ok');
});

// ----------------------------------------------------------------------------- keyboard

function typing(e) {
  const t = e.target;
  if (!t || !t.closest) return false;
  if (t.closest('input, textarea, select, [contenteditable="true"]')) {
    return !(t.type === 'checkbox' || t.type === 'radio' || t.type === 'range');
  }
  return false;
}

function paletteItems() {
  const items = [];
  for (const b of document.querySelectorAll('.nav-btn')) items.push({ group: 'go to', title: b.textContent.trim(), run: () => navigate(b.dataset.view) });
  for (const x of EXPERIENCES) items.push({ group: 'mission', title: x.title, hint: x.summary, run: () => navigate('mission', { experienceId: x.id }) });
  for (const d of visibleDomains()) {
    if (!d.catalog) continue;
    for (const demo of d.catalog.demos) items.push({ group: 'demo', title: demo.title, hint: `${d.manifest.id}, in the analysis workspace`, run: () => startDemo(d.manifest.id, demo.id) });
  }
  items.push({ group: 'action', title: 'Run the mission being prepared', hint: 'Ctrl+Enter', run: () => { navigate('prepare'); runMission(); } });
  items.push({ group: 'action', title: 'Keyboard shortcuts', hint: '?', run: () => showHelp() });
  items.push({ group: 'action', title: 'Open library folder', run: () => api.reveal(null).catch((e) => toast(errorText(e), 'error')) });
  return items;
}

async function openPalette() {
  const items = paletteItems();
  try {
    const runs = await api.listRuns();
    for (const m of runs.slice(0, 300)) {
      items.push({ group: 'run', title: m.label || `${m.summary.scenario} · ${m.summary.controller} · seed ${m.summary.seed}`, hint: `${m.run_id} · ${m.summary.faults.length ? m.summary.faults.join(' + ') : 'no fault'} · ${m.summary.outcome_label}, ${m.summary.safety_status}`, run: () => navigate('run', { runId: m.run_id, meta: m }) });
    }
    for (const s of await api.listScenarios()) items.push({ group: 'scenario', title: s.name, hint: `${s.requests.length} requests`, run: () => openSaved(s) });
  } catch (e) {
    logUiError(`palette: ${e.message}`);
  }
  palette(() => items);
}

document.addEventListener('keydown', (e) => {
  if (!document.getElementById('modal-root').hidden) return;
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); openPalette(); return; }
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); if (currentView !== 'prepare') navigate('prepare'); runMission(); return; }
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  if (typing(e)) return;
  if (e.key === '?') { e.preventDefault(); showHelp(); return; }
  if (/^[1-8]$/.test(e.key) && !(e.target && e.target.closest && e.target.closest('[role="slider"]'))) { navigate(VIEWS[Number(e.key) - 1]); e.preventDefault(); return; }
  if (e.target && e.target.closest && (e.target.closest('button, a, [role="tab"], [role="radio"], summary') && (e.key === ' ' || e.key === 'Enter'))) return;
  if (e.target && e.target.closest && e.target.closest('.r3d canvas') && e.key.startsWith('Arrow')) return;
  let handled = false;
  if (currentView === 'run') handled = runKey(e);
  else if (currentView === 'mission') handled = playerKey(e);
  else if (currentView === 'compare') handled = compareKey(e);
  if (handled) e.preventDefault();
});

for (const b of document.querySelectorAll('.nav-btn')) b.addEventListener('click', () => navigate(b.dataset.view));
document.getElementById('open-help').addEventListener('click', () => showHelp());
document.getElementById('open-palette').addEventListener('click', () => openPalette());

initHome(document.getElementById('view-home'), navigate);
initMissions(document.getElementById('view-missions'), navigate);
initPlayer(document.getElementById('view-mission'), navigate);
initDiscover(document.getElementById('view-discover'));
initPrepare(document.getElementById('view-prepare'), navigate);
initRun(document.getElementById('view-run'), navigate);
initCompare(document.getElementById('view-compare'), navigate);
initLibrary(document.getElementById('view-library'), navigate);
initSettings(document.getElementById('view-settings'), async () => { await refreshInfo(); await loadDomains(); });

// Test and debugging hook: read-only facts about the visible state.
window.__studio = {
  view: () => currentView,
  player: () => playerState(),
  run: () => { const w = runWorkspace(); return w ? { runId: w.runId, t: w.cursor.t, t0: w.model.t0, t1: w.model.t1, scene: w.record.scene.kind } : null; },
};

(async () => {
  await loadPrefs();
  applyTheme();
  await boot();
})().catch((e) => {
  logUiError(`boot: ${e && e.stack ? e.stack : JSON.stringify(e)}`);
  startupFailed('The interface could not start.', e && e.message ? e.message : String(e));
});

export { prose };
