// Compact sources-and-accuracy control for a scene drawn on a geographic environment (M16). A short
// credit line stays visible; the full provenance, accuracy limits, attribution notices and licences
// open in a panel on hover, click, tap or the keyboard (Enter or Space; Escape closes). The same
// details are always available in Settings, Environments.

import { h } from './dom.js';

let seq = 0;

/** Short credit for each source: the pack's `credit` when given, else its attribution. */
export function shortCredits(m) {
  return [...new Set((m.sources || []).map((s) => s.credit || s.attribution).filter(Boolean))];
}

/**
 * Credits that stay on the map itself. Only the ODbL asks for attribution in view of the map
 * (OSMF attribution guidelines); the Copernicus DEM (Art. 6), Sentinel and CC BY notices are met by
 * the panel one press away, Settings, the installed NOTICE and every exported evidence package, and
 * public-domain sources ask for none. The full text of every notice stays in the panel.
 */
export function mapCredits(m) {
  return [...new Set((m.sources || []).filter((s) => /\bODbL\b/.test(s.licence || '')).map((s) => s.credit || s.attribution).filter(Boolean))];
}

const n = (v) => Number(v || 0).toLocaleString('en');

/** What the pack's world layer (schema v3) puts on the ground, with the source of each height. */
export function worldText(env) {
  const w = env.world;
  if (!w || (!w.features && !w.vegetation)) return null;
  const parts = [];
  const f = w.features;
  if (f) {
    const hs = f.height_sources || {};
    const by = [['lidar', 'from lidar'], ['osm-height', 'from the OSM height tag'], ['osm-levels', 'from OSM building levels'], ['default', 'estimated (a default height per kind)']]
      .filter(([k]) => hs[k]).map(([k, t]) => `${n(hs[k])} ${t}`);
    parts.push(`${n(f.buildings)} building footprints from OpenStreetMap${by.length ? ` (heights: ${by.join(', ')})` : ''}`);
    if (f.lidar_structures) parts.push(`${n(f.lidar_structures)} structures outlined from lidar cells with surveyed heights`);
    if (f.structures) parts.push(`${n(f.structures)} towers and masts at OSM positions`);
  }
  const v = w.vegetation;
  if (v) parts.push(`${n(v.trees)} trees and ${n(v.shrubs)} shrub clumps at lidar positions and heights`);
  else parts.push('no vegetation (this pack has no lidar, and none is invented)');
  const known = f ? Object.entries(f.height_sources || {}).filter(([k]) => k !== 'default').reduce((a, [, v]) => a + v, 0) : 0;
  const est = f ? (f.height_sources || {}).default || 0 : 0;
  const heights = f ? ` Building heights are data for ${n(known)} of ${n(f.buildings)}; the other ${n(est)} are estimates and are drawn low, in a paler tone.` : '';
  return `${parts.join('; ')}. Footprints and plant positions are data; walls, roofs and plant shapes are drawn.${heights}`;
}

const km = (m) => `${(m / 1000).toLocaleString('en', { maximumFractionDigits: 1 })} km`;

/** Resolution of each layer, finest first, from the validated manifest. */
function contextText(env, h1, im) {
  const d = (env.layers || []).find((l) => l.role === 'detail');
  const base = `terrain ${h1.spacing_m || '?'} m and image ${im.spacing_m || '?'} m per pixel`;
  if (!d) return `${base}, from the validated pack.`;
  return `within the ${km(2 * d.extent_m)} square around the pad, terrain ${d.height.spacing_m} m and image ${d.image.spacing_m} m per pixel; beyond it, out to ${km(2 * env.extent_m)}, ${base}. From the validated pack; the ${d.blend_m} m margin where the layers meet is blended for display.`;
}

function licenceUrl(text) {
  const m = /(https?:\/\/\S+)/.exec(text || '');
  return m ? m[1].replace(/[.,;)]+$/, '') : null;
}

/**
 * The control. `env` is the validated manifest; `warn` an optional short warning shown as a chip;
 * `onSettings` opens Settings at the environment.
 */
export function sourcesInfo(env, { warn, onSettings } = {}) {
  const id = `src-info-${++seq}`;
  const h1 = env.height || {};
  const im = env.image || {};
  const btn = h('button', { type: 'button', class: 'si-btn', 'aria-expanded': 'false', 'aria-controls': id, title: 'Sources, licences and accuracy' },
    h('span', { class: 'si-i', 'aria-hidden': 'true' }, 'i'), h('span', { class: 'si-btn-t' }, 'Sources'));
  const panel = h('div', { class: 'si-panel', id, role: 'region', 'aria-label': `Sources and accuracy of ${env.name}`, hidden: true },
    h('p', { class: 'si-h' }, 'What the scene shows'),
    h('dl', { class: 'si-kinds' },
      h('div', null, h('dt', null, h('span', { class: 'prov prov-sim' }, 'Simulated')), h('dd', null, 'Trajectory, attitude, throttle, estimate and events, from the run record.')),
      h('div', null, h('dt', null, h('span', { class: 'prov prov-ctx' }, 'Context')), h('dd', null, `${env.name}: ${contextText(env, h1, im)} The model assumes flat ground at the pad; nothing is computed against this terrain.`)),
      worldText(env) ? h('div', null, h('dt', null, h('span', { class: 'prov prov-ctx' }, 'On the ground')), h('dd', null, worldText(env))) : null,
      env.site_note ? h('div', null, h('dt', null, h('span', { class: 'prov prov-ctx' }, 'Site')), h('dd', null, env.site_note)) : null,
      h('div', null, h('dt', null, h('span', { class: 'prov prov-ill' }, 'Illustrative')), h('dd', null, `Stage shape, weathering, legs, fins, plume, the glow and dust where it meets the ground, sky, haze, sun, shadows, water finish, fine ground grain${env.world ? ', building walls and roofs, and the shapes and leaves of plants' : ''} and pad surface: drawn for legibility, not modelled.`))),
    warn ? h('p', { class: 'si-warn' }, warn) : null,
    (env.accuracy || []).length ? h('p', { class: 'si-h' }, 'Accuracy') : null,
    (env.accuracy || []).length ? h('ul', { class: 'si-list' }, env.accuracy.map((a) => h('li', null, a))) : null,
    h('p', { class: 'si-h' }, 'Sources and licences'),
    h('ul', { class: 'si-list si-sources' }, (env.sources || []).map((s) => {
      const url = licenceUrl(s.licence);
      return h('li', null,
        h('p', { class: 'si-prod' }, s.product),
        s.attribution ? h('p', { class: 'si-attr' }, s.attribution) : null,
        h('p', { class: 'si-lic' }, (s.licence || '').replace(url || '\u0000', '').trim(), url ? h('span', { class: 'si-url mono' }, ` ${url}`) : null));
    })),
    onSettings ? h('button', { type: 'button', class: 'link small si-more', onclick: () => { close(); onSettings(); } }, 'Environment details in Settings') : null);
  const others = shortCredits(env).length - mapCredits(env).length;
  const credit = h('p', { class: 'si-credit', title: shortCredits(env).join(' · ') },
    mapCredits(env).join(' · '), others > 0 ? h('span', { class: 'si-more-n' }, `${mapCredits(env).length ? ' · ' : ''}${others} more in Sources`) : null);
  const wrap = h('div', { class: 'si' }, h('div', { class: 'si-row' }, btn, warn ? h('span', { class: 'si-chip', title: warn }, 'Path below terrain') : null, h('span', { class: 'si-chip si-flat', title: 'The model assumes flat ground at the pad; nothing is computed against this terrain.' }, 'Terrain is context only'), credit), panel);

  let open = false;
  let pinned = false;
  let hoverOpened = false;
  let timer = 0;
  // Outside presses close the panel; the listener exists only while the panel is open.
  const outside = (e) => {
    if (!wrap.isConnected) { document.removeEventListener('pointerdown', outside, true); return; }
    if (open && !wrap.contains(e.target)) close();
  };
  const set = (v) => {
    if (v && !open) document.addEventListener('pointerdown', outside, true);
    if (!v) document.removeEventListener('pointerdown', outside, true);
    open = v;
    panel.hidden = !v;
    btn.setAttribute('aria-expanded', String(v));
    wrap.classList.toggle('is-open', v);
    if (!v) { pinned = false; hoverOpened = false; }
  };
  function close() { set(false); }
  const isMouse = (e) => e.pointerType === 'mouse';
  wrap.addEventListener('pointerenter', (e) => {
    if (!isMouse(e)) return;
    clearTimeout(timer);
    if (!open) { set(true); hoverOpened = true; }
  });
  wrap.addEventListener('pointerleave', (e) => {
    if (!isMouse(e) || pinned) return;
    timer = setTimeout(() => { if (!pinned) close(); }, 180);
  });
  btn.addEventListener('click', () => {
    // A click on a panel opened by hovering keeps it open; otherwise a click (or a tap, or Enter
    // or Space) toggles it.
    if (open && hoverOpened && !pinned) { pinned = true; hoverOpened = false; return; }
    set(!open);
    pinned = open;
  });
  wrap.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && open) { e.stopPropagation(); close(); btn.focus(); }
  });
  wrap.addEventListener('focusout', (e) => {
    if (open && !pinned && e.relatedTarget && !wrap.contains(e.relatedTarget)) close();
  });
  return wrap;
}
