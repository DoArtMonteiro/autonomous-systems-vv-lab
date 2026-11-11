// The only module that talks to the Tauri shell. Every command rejects with a PlatformError
// serialised as {kind, message}; anything else (an IPC failure, a missing command) is normalised to
// the same shape so callers handle one error type.

function core() {
  const t = window.__TAURI__;
  if (!t || !t.core || typeof t.core.invoke !== 'function') {
    throw { kind: 'io', message: 'The desktop shell is not available (window.__TAURI__ is missing).' };
  }
  return t.core;
}

export function errorOf(e) {
  if (e && typeof e === 'object' && typeof e.kind === 'string' && typeof e.message === 'string') return e;
  if (e instanceof Error) return { kind: 'io', message: e.message };
  return { kind: 'io', message: typeof e === 'string' ? e : JSON.stringify(e) };
}

export async function invoke(name, args) {
  try {
    return await core().invoke(name, args || {});
  } catch (e) {
    throw errorOf(e);
  }
}

export const api = {
  appInfo: () => invoke('app_info'),
  listDomains: () => invoke('list_domains'),
  restartPlatform: () => invoke('restart_platform'),
  validate: (request) => invoke('validate', { request }),
  run: (request) => invoke('run', { request }),
  compare: (requests) => invoke('compare', { requests }),
  record: (runId) => invoke('record', { runId }),
  listRuns: () => invoke('list_runs'),
  updateNotes: (runId, label, notes, tags) => invoke('update_notes', { runId, label, notes, tags }),
  replay: (runId) => invoke('replay', { runId }),
  exportEvidence: (runId, choose) => invoke('export_evidence', { runId, choose }),
  reveal: (path) => invoke('reveal', { path: path ?? null }),
  saveScenario: (name, notes, requests) => invoke('save_scenario', { name, notes, requests }),
  listScenarios: () => invoke('list_scenarios'),
  deleteScenario: (id) => invoke('delete_scenario', { id }),
  saveComparison: (name, notes, runIds) => invoke('save_comparison', { name, notes, runIds }),
  listComparisons: () => invoke('list_comparisons'),
  deleteComparison: (id) => invoke('delete_comparison', { id }),
  getPrefs: () => invoke('get_prefs'),
  setPrefs: (prefs) => invoke('set_prefs', { prefs }),
  // M16 geographic environments: validated packs, bytes over IPC (no network, CSP unchanged).
  listEnvironments: () => invoke('list_environments'),
  environmentFile: (id, file) => invoke('environment_file', { id, file }),
  geoTrack: (id, runId) => invoke('geo_track', { id, runId }),
  importEnvironment: () => invoke('import_environment'),
  importEnvironmentPackage: () => invoke('import_environment_package'),
  removeEnvironment: (id) => invoke('remove_environment', { id }),
  revealEnvironments: () => invoke('reveal_environments'),
  // M17 Cinematic View module: status, install from a module zip (its SHA-256 is shown for confirmation first), uninstall, launch by ids.
  cinematicStatus: () => invoke('cinematic_status'),
  cinematicInstallFromFile: () => invoke('cinematic_install_from_file'),
  cinematicUninstall: () => invoke('cinematic_uninstall'),
  cinematicLaunch: (runId, envId) => invoke('cinematic_launch', { runId, envId }),
};

let reporting = false;
/** Writes a UI error to the studio log; never throws and never recurses. */
export function logUiError(message) {
  if (reporting) return;
  reporting = true;
  try {
    core().invoke('log_ui_error', { message: String(message).slice(0, 2000) }).catch(() => {}).finally(() => { reporting = false; });
  } catch {
    reporting = false;
  }
}

window.addEventListener('error', (ev) => {
  logUiError(`${ev.message} at ${ev.filename}:${ev.lineno}:${ev.colno}`);
});
window.addEventListener('unhandledrejection', (ev) => {
  const r = ev.reason;
  logUiError(`unhandled rejection: ${r && r.stack ? r.stack : JSON.stringify(errorOf(r))}`);
});
