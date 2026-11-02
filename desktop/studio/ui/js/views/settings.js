// Settings and about: theme, developer domains, version and contract, library location, discovered
// and rejected domains with their reasons, platform restart, and what the product is.

import { h, clear, prose } from '../dom.js';
import { api } from '../api.js';
import { state, pref, setPref } from '../store.js';
import { toast, errorText } from '../ui.js';

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
      h('p', null, h('b', null, 'Model validity. '), 'The models are idealised research models, not flight or vehicle software, and are not validated against real data. The M10 rocket controllers are development arms: their results come from the development configuration and are not an evaluation. Each run shows the model validity and the notes of its domain next to the results.'),
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
