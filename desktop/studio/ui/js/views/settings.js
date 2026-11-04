// Settings and about: theme, developer domains, version and contract, library location, discovered
// and rejected domains with their reasons, platform restart, and what the product is.

import { h, clear, prose } from '../dom.js';
import { api } from '../api.js';
import { state, pref, setPref } from '../store.js';
import { toast, errorText } from '../ui.js';
import { envCard } from '../env-catalogue.js';
import { listEnvironments, forgetEnvironments, mb } from '../environments.js';

let root;
let reload = async () => {};

export function initSettings(el, onRestart) {
  root = el;
  reload = onRestart;
}

export function showSettings() {
  render();
}

function render() {
  clear(root);
  const info = state.info || {};
  const theme = pref('theme');
  const themeSeg = h('div', { class: 'seg', role: 'radiogroup', 'aria-label': 'Theme', id: 'theme-seg' },
    ...[['system', 'System'], ['dark', 'Dark'], ['light', 'Light']].map(([v, t]) => h('button', {
      type: 'button', role: 'radio', class: 'seg-btn', 'aria-checked': String(theme === v), dataset: { theme: v },
      onclick: () => { setPref('theme', v); render(); },
    }, t)));
  const dev = h('input', { type: 'checkbox', id: 'pref-dev', checked: pref('showDeveloperDomains'), onchange: (e) => setPref('showDeveloperDomains', e.target.checked) });
  const restart = h('button', { type: 'button', class: 'btn', onclick: async () => {
    restart.disabled = true;
    restart.classList.add('is-busy');
    try {
      await api.restartPlatform();
      await reload();
      toast('The platform restarted: domains rediscovered and catalogs reread.', 'ok');
      render();
    } catch (e) {
      toast(errorText(e), 'error');
    } finally {
      restart.disabled = false;
      restart.classList.remove('is-busy');
    }
  } }, 'Restart platform');
  const start = info.start || {};
  root.append(h('div', { class: 'settings' },
    h('h1', { style: { paddingBottom: '6px' } }, 'Settings and about'),
    h('section', null, h('h2', null, 'Appearance'), h('div', { class: 'sec-body' }, themeSeg, h('p', { class: 'dim small' }, 'System follows the Windows light or dark setting.'))),
    h('section', null, h('h2', null, 'Domains'),
      h('div', { class: 'sec-body' },
        h('label', { class: 'toggle', for: 'pref-dev' }, dev, 'Show developer domains'),
        h('p', { class: 'dim small' }, 'Reference and test domains are discovered and runnable but hidden from the product screens unless this is on. They use the same screens with no special code.'),
        domainTable(),
        state.rejected.length ? h('div', null, h('h3', null, `Rejected domains (${state.rejected.length})`),
          h('table', { class: 'grid-table' }, h('thead', null, h('tr', null, h('th', null, 'directory'), h('th', null, 'reason'))),
            h('tbody', null, state.rejected.map((r) => h('tr', null, h('td', { class: 'mono' }, r.dir), h('td', null, r.reason)))))) : h('p', { class: 'dim small' }, 'No domain directory was rejected.'),
        h('div', { class: 'row' }, restart, h('span', { class: 'dim small' }, `${start.domains ?? state.domains.length} discovered, ${(start.rejected || []).length} rejected, ${start.recovered ?? 0} interrupted runs cleared at start.`)))),
    environmentsSection(),
    h('section', null, h('h2', null, 'Library'), h('div', { class: 'sec-body' },
      h('p', { class: 'mono' }, info.library || 'n/a'),
      h('div', { class: 'row' }, h('button', { type: 'button', class: 'btn', onclick: () => api.reveal(null).catch((e) => toast(errorText(e), 'error')) }, 'Open library folder')),
      h('p', { class: 'dim small' }, 'Runs, saved scenarios, comparisons and evidence exports live here, outside the install directory; uninstalling keeps them.'))),
    h('section', null, h('h2', null, 'Version'), h('div', { class: 'sec-body' },
      h('table', { class: 'kv' }, h('tbody', null,
        h('tr', null, h('th', null, 'Studio'), h('td', { class: 'mono' }, info.version || 'n/a')),
        h('tr', null, h('th', null, 'Domain contract'), h('td', { class: 'mono' }, info.contract || 'n/a')))))),
    h('section', { class: 'about' }, h('h2', null, 'What this is'), h('div', { class: 'sec-body' },
      h('p', null, 'V&V Lab Studio prepares missions of deterministic simulated vehicles, injects faults, runs them in separate domain host processes, and shows what the verifier concluded. Requirements and safety invariants are judged on the true state of the simulation; the controller only ever sees observations.'),
      h('p', null, 'A run is identified by its request and the host build. Replay recomputes a stored run from its inputs and compares the result; it does not trust stored conclusions. An evidence package bundles the record, the request, the native artifacts and their hashes.'),
      h('p', null, h('b', null, 'Model validity. '), 'The models are idealised research models, not flight or vehicle software, and are not validated against real data. Each run shows the model validity and the notes of its domain next to the results.'),
      state.domains.map((d) => h('p', { class: 'dim small' }, h('b', null, `${d.manifest.name}: `), prose(d.manifest.model_validity)))))));
}

function domainTable() {
  return h('table', { class: 'grid-table dom-table' },
    h('thead', null, h('tr', null, ['id', 'name', 'version', 'contract', 'shown', 'capabilities', 'catalog'].map((t) => h('th', null, t)))),
    h('tbody', null, state.domains.map((d) => h('tr', null,
      h('td', { class: 'mono' }, d.manifest.id),
      h('td', null, d.manifest.name),
      h('td', { class: 'mono' }, d.manifest.version),
      h('td', { class: 'mono' }, `${d.manifest.contract.major}.${d.manifest.contract.minor}`),
      h('td', null, d.manifest.user_facing ? 'product' : h('span', { class: 'tag tag-dev' }, 'developer')),
      h('td', { class: 'small' }, d.manifest.capabilities.join(', ')),
      h('td', { class: d.error ? 'error-text small' : 'small' }, d.error ? d.error : d.catalog ? `${d.catalog.scenarios.length} scenarios, ${d.catalog.demos.length} demos` : 'n/a')))));
}

// ----------------------------------------------------------------------------- environments (M16)

function environmentsSection() {
  const body = h('div', { class: 'sec-body', id: 'env-settings' }, h('p', { class: 'dim small' }, 'Reading the installed environments…'));
  const sec = h('section', null, h('h2', null, 'Geographic environments'), body);
  fillEnvironments(body, false);
  return sec;
}

async function fillEnvironments(body, reloadList) {
  let list;
  try {
    list = await listEnvironments(reloadList);
  } catch (e) {
    clear(body).append(h('p', { class: 'error-text' }, `The environments could not be read: ${errorText(e)}`));
    return;
  }
  const total = list.environments.reduce((a, e) => a + e.bytes, 0);
  const act = async (fn, ok) => {
    try {
      const r = await fn();
      if (r === null) return;
      forgetEnvironments();
      toast(ok, 'ok');
      fillEnvironments(body, true);
    } catch (e) {
      toast(errorText(e), 'error', 8000);
    }
  };
  clear(body).append(...[
    h('p', { class: 'small' }, h('b', null, 'No network. '), 'Studio never downloads geographic data and makes no network request. Environments are packs built on purpose with ', h('code', null, 'scripts/geo/build_environment.py'), ' from public sources, shipped with the installer or imported from a folder. Every pack is checked before it is shown: file sizes, SHA-256 hashes, the grid, attributed sources, and its geodetic check points recomputed by the georeference layer.'),
    h('div', { class: 'envc-grid envc-settings' }, list.environments.map((e) => envCard(e))),
    h('details', { class: 'env-build' }, h('summary', null, 'Build or import another environment'),
      h('p', { class: 'small' }, 'A pack is built outside Studio, once, from public sources whose licences allow redistribution, with Python, rasterio and pyproj and an Internet connection:'),
      h('pre', { class: 'mono small' }, 'python scripts/geo/build_environment.py --env <id> --out <folder>'),
      h('p', { class: 'small' }, 'The script lists the environments it can build. Import the folder it writes with the button below; Studio validates it before listing it. Sources reviewed for the next environment, El Arenosillo (Huelva, Spain): IGN PNOA orthophoto and MDT05 heights, CC BY 4.0, whose credit must read “Obra derivada de … CC-BY 4.0 scne.es” at the foot of the view.')),
    h('table', { class: 'grid-table env-table' },
      h('thead', null, h('tr', null, ['environment', 'origin', 'sources and licence', 'size', 'where', ''].map((t) => h('th', null, t)))),
      h('tbody', null, list.environments.map((e) => h('tr', { dataset: { env: e.id } },
        h('td', null, h('b', null, e.name), h('br'), h('span', { class: 'dim small' }, e.summary)),
        h('td', { class: 'mono small' }, `${e.origin.lat_deg.toFixed(5)}, ${e.origin.lon_deg.toFixed(5)}`, h('br'), `${e.origin.orthometric_height_m.toFixed(1)} m (EGM2008)`, h('br'), h('span', { class: 'dim' }, `checks within ${(e.worst_check_m * 1000).toFixed(3)} mm`)),
        h('td', { class: 'small' }, (e.sources || []).map((src) => h('details', { class: 'env-src' }, h('summary', null, src.product), h('p', null, src.provider), h('p', null, h('b', null, 'Licence. '), src.licence), h('p', null, h('b', null, 'Attribution. '), src.attribution))),
          h('details', { class: 'env-src' }, h('summary', null, 'Accuracy and limits'), h('ul', { class: 'pl-list' }, (e.accuracy || []).map((a) => h('li', null, a))))),
        h('td', { class: 'mono small' }, mb(e.bytes)),
        h('td', { class: 'small' }, e.kind === 'bundled' ? 'installed with Studio' : 'imported'),
        h('td', null, e.kind === 'imported' ? h('button', { type: 'button', class: 'btn btn-sm', onclick: () => act(() => api.removeEnvironment(e.id), `${e.name} removed.`) }, 'Remove') : null))))),
    list.rejected.length ? h('div', null, h('h3', null, `Rejected packs (${list.rejected.length})`), h('table', { class: 'grid-table' },
      h('thead', null, h('tr', null, h('th', null, 'folder'), h('th', null, 'where'), h('th', null, 'reason'))),
      h('tbody', null, list.rejected.map((r) => h('tr', null, h('td', { class: 'mono' }, r.folder), h('td', null, r.kind), h('td', { class: 'small' }, r.reason)))))) : null,
    h('p', { class: 'dim small' }, `${list.environments.length} environments, ${mb(total)} in total. Imported packs are kept in ${list.imported_dir}.`),
    h('div', { class: 'row' },
      h('button', { type: 'button', class: 'btn', dataset: { action: 'import-environment' }, onclick: () => act(() => api.importEnvironment(), 'Environment imported and validated.') }, 'Import a pack folder…'),
      h('button', { type: 'button', class: 'btn btn-quiet', onclick: () => api.revealEnvironments().catch((e) => toast(errorText(e), 'error')) }, 'Open the imported packs folder'))].filter(Boolean));
}
