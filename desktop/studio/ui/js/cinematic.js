// Cinematic View (M17): an optional, separately installed renderer. This file only asks the shell
// for the module's status, installs or removes it, and asks the shell to start it for a run and an
// environment by id. The shell verifies the module and resolves every path; nothing here is a path.

import { h, clear } from './dom.js';
import { api } from './api.js';
import { toast, errorText } from './ui.js';

let status = null; // Promise of the shell's status

function current(reload = false) {
  if (!status || reload) {
    status = api.cinematicStatus().catch((e) => { status = null; throw e; });
  }
  return status;
}

const mbText = (b) => `${(b / 1048576).toFixed(0)} MB`;

/**
 * "Cinematic view" button for the player: opens the stored run `runId()` on environment `envId()`
 * in the module. Disabled, with the reason as its title, when the module is not installed or not
 * verified, when there is no environment, or when the scene is not a rocket landing.
 */
export function cinematicButton(runId, envId, rocket) {
  const b = h('button', { type: 'button', class: 'btn btn-quiet', dataset: { action: 'cinematic' }, disabled: true, 'aria-disabled': 'true', title: 'Checking the Cinematic View module…' }, 'Cinematic view');
  const off = (why) => { b.disabled = true; b.setAttribute('aria-disabled', 'true'); b.title = why; };
  if (!rocket) { off('The Cinematic View replays rocket landings only.'); return b; }
  // Read afresh each time the player is built: the module folder can change outside this window
  // (another Studio window, an uninstall, a manual removal), and a stale "installed" would offer a
  // launch that cannot work.
  current(true).then((s) => {
    if (!s.installed || !s.verified) return off(s.reason || 'The Cinematic View module is not installed.');
    if (!envId()) return off('The Cinematic View needs a geographic environment; none is installed.');
    b.disabled = false;
    b.removeAttribute('aria-disabled');
    b.title = `Open this run in the Cinematic View ${s.version} (a separate window; read-only replay of the record)`;
  }).catch((e) => off(`The module status could not be read: ${errorText(e)}`));
  b.addEventListener('click', () => {
    if (b.disabled) return;
    api.cinematicLaunch(runId(), envId()).then(() => toast('The Cinematic View opens in its own window.', 'info'))
      .catch((e) => toast(errorText(e), 'error'));
  });
  return b;
}

/** Settings section: status, install from a module zip (hash shown first), uninstall. */
export function cinematicSection() {
  const body = h('div', { class: 'sec-body' }, h('p', { class: 'dim small' }, 'Reading the module status…'));
  const fill = (s) => {
    const install = h('button', { type: 'button', class: 'btn btn-quiet', onclick: () => {
      install.disabled = true;
      api.cinematicInstallFromFile().then((r) => {
        if (!r) { install.disabled = false; return; }
        status = Promise.resolve(r);
        fill(r);
        if (r.installed && r.verified) toast(`Cinematic View ${r.version} installed. Its files matched the module manifest.`, 'info');
        else toast(r.reason || 'The module was installed but did not pass its integrity check.', 'error', 8000);
      })
        .catch((e) => { toast(errorText(e), 'error'); install.disabled = false; });
    } }, s.installed ? 'Replace from a module zip…' : 'Install from a module zip…');
    const remove = s.installed ? h('button', { type: 'button', class: 'btn btn-quiet', onclick: () => {
      api.cinematicUninstall().then((r) => { toast('Cinematic View removed.', 'info'); status = Promise.resolve(r); fill(r); }).catch((e) => toast(errorText(e), 'error'));
    } }, 'Uninstall') : null;
    clear(body).append(
      h('p', { class: 'small' }, s.installed && s.verified
        ? `Installed: version ${s.version}, Godot ${s.godot}, ${mbText(s.disk_bytes)} on disk. Every file matched its manifest when last checked; Studio checks them again each time it opens the view.`
        : (s.reason || 'Not installed.')),
      h('p', { class: 'dim small' }, 'An optional high-fidelity replay window built on Godot 4.7.2 (MIT). It reads the stored record and a validated environment pack and never simulates; the stage, plume and vegetation shapes are illustrative. It is installed only from a module zip with its .sha256 file beside it. Studio copies the zip once, shows its SHA-256 and asks you to confirm, then compares every file with the module manifest. The .sha256 file and the manifest travel with the zip, so they show it is intact, not who built it: compare the SHA-256 with a value from a source you trust. Nothing is downloaded.'),
      h('div', { class: 'row' }, install, remove));
  };
  current().then(fill).catch((e) => clear(body).append(h('p', { class: 'error-text' }, `The module status could not be read: ${errorText(e)}`)));
  return h('section', null, h('h2', null, 'Cinematic View (optional module)'), body);
}
