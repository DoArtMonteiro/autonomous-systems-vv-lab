// Provenance of a stored run: identity, request, domain build, source hash, artifacts, reproduce
// commands; replay by recomputation with each check; evidence export; the raw record on demand.

import { h, clear, icon, shortHash, num, prose } from './dom.js';
import { api } from './api.js';
import { toast, errorText } from './ui.js';

export function provenancePanel(runId, record, meta) {
  const p = record.provenance || {};
  const replayOut = h('div', { class: 'replay-out', 'aria-live': 'polite' });
  const exportOut = h('div', { class: 'export-out', 'aria-live': 'polite' });
  const replayBtn = h('button', { type: 'button', class: 'btn', 'data-action': 'replay', onclick: () => doReplay() }, icon('replay'), 'Replay and verify');
  const exportBtn = h('button', { type: 'button', class: 'btn', onclick: () => doExport() }, icon('export'), 'Export evidence…');

  async function doReplay() {
    replayBtn.disabled = true;
    clear(replayOut).append(h('p', { class: 'dim' }, 'Recomputing the run from its stored request in the domain host…'));
    try {
      const rep = await api.replay(runId);
      // An earlier build's run is checked against its own record, not byte for byte: say so, and never call it rejected.
      const earlier = rep.status === 'verified_earlier_build';
      const ok = rep.status === 'verified' || earlier;
      clear(replayOut).append(
        h('div', { class: ['replay-verdict', ok ? 'v-pass' : 'v-unsafe'] },
          h('span', { class: 'glyph' }, icon(ok ? 'check' : 'warn')),
          h('strong', null, earlier ? 'Verified against its own record' : ok ? 'Verified' : 'Rejected'),
          h('span', { class: 'dim' }, earlier
            ? 'Recorded by an earlier build. It was recomputed with the current defaults and agrees with the stored record on every verdict and recorded number; its files are not compared byte for byte.'
            : ok ? 'The run was recomputed from its inputs and every check passed.' : 'At least one check failed; the stored run does not reproduce.')),
        h('ol', { class: 'checks' }, rep.checks.map((c) => h('li', { class: c.pass ? 'v-pass' : 'v-fail' },
          h('span', { class: 'glyph' }, icon(c.pass ? 'check' : 'cross')),
          h('span', null, c.name),
          c.detail ? h('span', { class: 'mono dim small' }, c.detail) : null))));
    } catch (e) {
      clear(replayOut).append(h('p', { class: 'error-text', role: 'alert' }, `Replay failed: ${errorText(e)}`));
    } finally {
      replayBtn.disabled = false;
    }
  }

  async function doExport() {
    exportBtn.disabled = true;
    try {
      const path = await api.exportEvidence(runId, true);
      clear(exportOut);
      if (path) {
        exportOut.append(h('p', null, 'Evidence package written to ', h('span', { class: 'mono' }, path), ' ',
          h('button', { type: 'button', class: 'link', onclick: () => api.reveal(path).catch((e) => toast(errorText(e), 'error')) }, 'Show in Explorer')));
      } else {
        exportOut.append(h('p', { class: 'dim' }, 'Export cancelled.'));
      }
    } catch (e) {
      clear(exportOut).append(h('p', { class: 'error-text', role: 'alert' }, `Export failed: ${errorText(e)}`));
    } finally {
      exportBtn.disabled = false;
    }
  }

  const raw = h('details', { class: 'raw' },
    h('summary', null, 'Advanced: raw record JSON'),
    h('p', { class: 'dim small' }, 'The record exactly as the domain host wrote it. Large; rendered on demand.'));
  raw.addEventListener('toggle', () => {
    if (raw.open && !raw.querySelector('pre')) {
      raw.append(h('pre', { class: 'mono raw-pre', tabindex: '0' }, JSON.stringify(record, null, 2)));
    }
  });

  const req = record.request;
  return h('div', { class: 'prov' },
    h('div', { class: 'prov-actions' }, replayBtn, exportBtn),
    replayOut,
    exportOut,
    h('table', { class: 'kv' }, h('tbody', null,
      row('Run id', runId),
      row('Created (UTC, library metadata)', meta ? meta.created_utc : 'n/a'),
      row('Domain', `${record.domain.id} ${record.domain.version}`),
      row('Contract', record.domain.contract),
      row('Simulator', p.simulator || 'n/a'),
      row('Source sha256', p.source_sha256 || 'n/a', true),
      meta ? row('Host executable sha256', meta.host_sha256, true) : null,
      row('Seed', String(req.seed)))),
    h('h3', null, 'Request'),
    h('pre', { class: 'mono code' }, JSON.stringify(req, null, 2)),
    h('h3', null, `Artifacts (${(p.artifacts || []).length})`),
    h('table', { class: 'grid-table' },
      h('thead', null, h('tr', null, h('th', null, 'path'), h('th', null, 'sha256'), h('th', { class: 'num' }, 'bytes'))),
      h('tbody', null, (p.artifacts || []).map((a) => h('tr', null,
        h('td', { class: 'mono' }, a.path),
        h('td', { class: 'mono', title: a.sha256 }, shortHash(a.sha256, 16), '…'),
        h('td', { class: 'mono num' }, num(a.bytes, 12)))))),
    h('h3', null, 'Reproduce from a repository checkout'),
    h('ul', { class: 'cmds' }, (p.reproduce || []).map((c) => h('li', null, h('code', { class: 'mono' }, prose(c))))),
    raw);
}

function row(k, v, hash) {
  return h('tr', null, h('th', { scope: 'row' }, k), h('td', { class: ['mono', hash ? 'hash' : ''], title: v }, v));
}
