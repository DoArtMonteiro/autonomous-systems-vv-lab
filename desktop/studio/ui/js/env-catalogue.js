// Environment catalogue (M16.1): every validated pack as a card built from its manifest, with a
// thumbnail of its own image (read over IPC, re-hashed by the shell), the resolution of each layer,
// the relief around the pad, the site note, the short credits, its size and whether it is bundled
// or imported. Choosing a card switches the scene; nothing is fetched from the network.

import { h } from './dom.js';
import { api } from './api.js';
import { modal } from './ui.js';
import { mb } from './environments.js';
import { shortCredits } from './sources-info.js';

const isObj = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);
const num = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : 0);
const n = (v) => num(v).toLocaleString('en');

/** One line on the pack's world layer (v3), or null. */
export function worldLine(e) {
  const w = e.world;
  if (!isObj(w)) return null;
  const bits = [];
  if (isObj(w.features)) bits.push(`${n(num(w.features.buildings) + num(w.features.lidar_structures))} buildings and structures`);
  if (isObj(w.vegetation)) bits.push(`${n(w.vegetation.count)} lidar trees and shrubs`);
  return bits.length ? `3D: ${bits.join(', ')}` : null;
}

const thumbs = new Map(); // id -> Promise of an object URL

function bytesOf(b) {
  if (b instanceof ArrayBuffer) return b;
  if (ArrayBuffer.isView(b)) return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength);
  return new Uint8Array(b).buffer;
}

/** A small thumbnail of the pack's base image (object URL, cached for the session). */
export function thumbnail(id) {
  if (!thumbs.has(id)) {
    const p = (async () => {
      const b = await api.environmentFile(id, 'image.jpg');
      const bmp = await createImageBitmap(new Blob([bytesOf(b)], { type: 'image/jpeg' }), { resizeWidth: 320, resizeHeight: 320, resizeQuality: 'medium' });
      const c = document.createElement('canvas');
      c.width = c.height = 320;
      c.getContext('2d').drawImage(bmp, 0, 0);
      bmp.close();
      const blob = await new Promise((r) => c.toBlob(r, 'image/jpeg', 0.82));
      return URL.createObjectURL(blob);
    })();
    p.catch(() => thumbs.delete(id));
    thumbs.set(id, p);
  }
  return thumbs.get(id);
}

/** One line per layer: "2 km at 0.5 m image, 4 m terrain", then the base. */
export function resolutionLines(e) {
  const km = (m) => `${(num(m) / 1000).toLocaleString('en', { maximumFractionDigits: 1 })} km`;
  const sp = (o) => (isObj(o) ? num(o.spacing_m) : 0);
  const out = [];
  for (const l of Array.isArray(e.layers) ? e.layers : []) if (isObj(l) && l.role === 'detail') out.push(`${km(2 * num(l.extent_m))} square: image ${sp(l.image)} m, terrain ${sp(l.height)} m`);
  out.push(`${km(2 * num(e.extent_m))} square: image ${sp(e.image)} m, terrain ${sp(e.height)} m`);
  return out;
}

export function relief(e) {
  const r = (Array.isArray(e.relief) ? e.relief : []).find((x) => isObj(x) && x.radius_m === 500);
  return r ? `${(num(r.max_up_m) - num(r.min_up_m)).toFixed(0)} m of relief within 500 m of the pad` : null;
}

/** The card of one environment. `current` marks the one in use; `onUse(id)` chooses it. */
export function envCard(e, { current, onUse } = {}) {
  const img = h('img', { class: 'envc-img', alt: '', width: 160, height: 160, loading: 'lazy' });
  thumbnail(e.id).then((u) => { img.src = u; }).catch(() => img.classList.add('is-missing'));
  const chosen = e.id === current;
  return h('article', { class: ['envc', chosen ? 'is-current' : ''], dataset: { env: e.id } },
    h('div', { class: 'envc-thumb' }, img, h('span', { class: 'envc-kind' }, e.kind === 'bundled' ? 'Installed with Studio' : 'Imported')),
    h('div', { class: 'envc-body' },
      h('h3', { class: 'envc-name' }, String(e.name)),
      h('p', { class: 'envc-sum' }, String(e.summary)),
      typeof e.site_note === 'string' && e.site_note ? h('p', { class: 'envc-site' }, e.site_note) : null,
      h('ul', { class: 'envc-facts' },
        ...resolutionLines(e).map((x) => h('li', null, x)),
        relief(e) ? h('li', null, relief(e)) : null,
        worldLine(e) ? h('li', null, worldLine(e)) : null,
        h('li', null, `${mb(e.bytes)} on disk, offline`)),
      h('p', { class: 'envc-credit' }, shortCredits(e).join(' · ')),
      onUse ? h('div', { class: 'envc-actions' }, chosen
        ? h('span', { class: 'envc-using' }, 'In use')
        : h('button', { type: 'button', class: 'btn btn-sm btn-primary', dataset: { use: e.id }, onclick: () => onUse(e.id) }, 'Use this environment')) : null));
}

/** Opens the catalogue over the player. */
export function openCatalogue(envs, current, onUse) {
  const grid = h('div', { class: 'envc-grid' });
  let m = null;
  for (const e of envs) grid.append(envCard(e, { current, onUse: (id) => { if (m) m.close(); onUse(id); } }));
  const body = h('div', { class: 'envc-wrap' },
    h('p', { class: 'small dim' }, 'Every environment is a validated local pack: its files are hashed and its geodetic check points recomputed before it is listed. The simulation runs on flat ground in every case; the landscape is context. Packs are built with ', h('code', null, 'scripts/geo/build_environment.py'), ', with buildings and lidar vegetation added by ', h('code', null, 'scripts/geo/build_features.py'), ', and imported in Settings, Environments.'),
    grid);
  m = modal({ title: 'Environments', body, wide: true, label: 'Environment catalogue' });
  m.box.classList.add('envc-modal');
  return m;
}

/** Releases the thumbnails (when the list of packs changes). */
export function forgetThumbnails() {
  for (const p of thumbs.values()) p.then((u) => URL.revokeObjectURL(u)).catch(() => {});
  thumbs.clear();
}

