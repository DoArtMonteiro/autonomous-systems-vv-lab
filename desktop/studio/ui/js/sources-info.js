// Compact sources-and-accuracy control for a scene drawn on a geographic environment (M16). The short
// credit of every source whose licence asks for one stays on the map; the full provenance, accuracy
// limits, attribution notices and licences of every source open in a panel on hover, click, tap or
// the keyboard (Enter or Space; Escape closes). The same details are always available in Settings,
// Environments. The manifest comes from the shell, which validates its types; everything here still
// treats it as data of unknown shape and never throws on a surprise.

import { h } from './dom.js';

let seq = 0;

const isObj = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);
const str = (v) => (typeof v === 'string' ? v : '');
const list = (v) => (Array.isArray(v) ? v : []);
const num = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : 0);
const sourcesOf = (m) => list(isObj(m) ? m.sources : null).filter(isObj);

/** Short credit for each source: the pack's `credit` when given, else its attribution. */
export function shortCredits(m) {
  return [...new Set(sourcesOf(m).map((s) => str(s.credit) || str(s.attribution)).filter(Boolean))];
}

/**
 * Whether a source's licence asks for a credit. Fails towards showing: only a licence that says it
 * is public domain without asking for a credit (USGS, the NGA geoid) is left off the map. The NAIP
 * policy is public domain but asks for a credit, so it stays; the ODbL, CC BY, Copernicus and
 * Sentinel notices all stay.
 */
export function asksForCredit(s) {
  const l = str(isObj(s) ? s.licence : '');
  if (/\b(ODbL|CC[- ]BY)\b/i.test(l)) return true; // never dropped, whatever else the text says
  return !(/public domain/i.test(l) && !/request/i.test(l));
}

/**
 * Credits that stay on the map itself: the short credit of each source that asks for one,
 * one per distinct text. The full notices, with the licences, stay in the panel one press away.
 */
export function mapCredits(m) {
  return [...new Set(sourcesOf(m).filter(asksForCredit).map((s) => str(s.credit) || str(s.attribution)).filter(Boolean))];
}

const n = (v) => num(v).toLocaleString('en');

/** What the pack's world layer (schema v3) puts on the ground, with the source of each height. */
export function worldText(env) {
  const w = isObj(env) ? env.world : null;
  if (!isObj(w) || (!isObj(w.features) && !isObj(w.vegetation))) return null;
  const parts = [];
  const f = isObj(w.features) ? w.features : null;
  if (f) {
    const hs = isObj(f.height_sources) ? f.height_sources : {};
    const by = [['lidar', 'from lidar'], ['osm-height', 'from the OSM height tag'], ['osm-levels', 'from OSM building levels'], ['default', 'estimated (a default height per kind)']]
      .filter(([k]) => num(hs[k])).map(([k, t]) => `${n(hs[k])} ${t}`);
    parts.push(`${n(f.buildings)} building footprints from OpenStreetMap${by.length ? ` (heights: ${by.join(', ')})` : ''}`);
    if (f.lidar_structures) parts.push(`${n(f.lidar_structures)} structures outlined from lidar cells with surveyed heights`);
    if (f.structures) parts.push(`${n(f.structures)} towers and masts at OSM positions`);
  }
  const v = isObj(w.vegetation) ? w.vegetation : null;
  if (v) parts.push(`${n(v.trees)} trees and ${n(v.shrubs)} shrub clumps at lidar positions and heights`);
  else parts.push('no vegetation (this pack has no lidar, and none is invented)');
  const known = f ? Object.entries(hs0(f)).filter(([k]) => k !== 'default').reduce((a, [, c]) => a + num(c), 0) : 0;
  const est = f ? num(hs0(f).default) : 0;
  const heights = f ? ` Building heights are data for ${n(known)} of ${n(f.buildings)}; the other ${n(est)} are estimates and are drawn low, in a paler tone.` : '';
  return `${parts.join('; ')}. Footprints and plant positions are data; walls, roofs and plant shapes are drawn.${heights}`;
}

const km = (m) => `${(num(m) / 1000).toLocaleString('en', { maximumFractionDigits: 1 })} km`;

/** Resolution of each layer, finest first, from the validated manifest. */
function contextText(env, h1, im) {
  const d = list(env.layers).find((l) => isObj(l) && l.role === 'detail');
  const base = `terrain ${num(h1.spacing_m) || '?'} m and image ${num(im.spacing_m) || '?'} m per pixel`;
  if (!d) return `${base}, from the validated pack.`;
  const dh = isObj(d.height) ? d.height : {};
  const di = isObj(d.image) ? d.image : {};
  return `within the ${km(2 * num(d.extent_m))} square around the pad, terrain ${num(dh.spacing_m) || '?'} m and image ${num(di.spacing_m) || '?'} m per pixel; beyond it, out to ${km(2 * num(env.extent_m))}, ${base}. From the validated pack; the ${num(d.blend_m)} m margin where the layers meet is blended for display.`;
}

/** Counts by source of height, or an empty object. */
function hs0(f) {
  return isObj(f.height_sources) ? f.height_sources : {};
}

function licenceUrl(text) {
  const m = /(https?:\/\/\S+)/.exec(str(text));
  return m ? m[1].replace(/[.,;)]+$/, '') : null;
}

/**
 * The control. `env` is the validated manifest; `warn` an optional short warning shown as a chip;
 * `onSettings` opens Settings at the environment.
 */
export function sourcesInfo(env, { warn, onSettings } = {}) {
  const id = `src-info-${++seq}`;
  const h1 = isObj(env.height) ? env.height : {};
  const im = isObj(env.image) ? env.image : {};
  const acc = list(env.accuracy).filter((a) => typeof a === 'string');
  const note = str(env.site_note);
  const btn = h('button', { type: 'button', class: 'si-btn', 'aria-expanded': 'false', 'aria-controls': id, title: 'Sources, licences and accuracy' },
    h('span', { class: 'si-i', 'aria-hidden': 'true' }, 'i'), h('span', { class: 'si-btn-t' }, 'Sources'));
  const panel = h('div', { class: 'si-panel', id, role: 'region', 'aria-label': `Sources and accuracy of ${str(env.name)}`, hidden: true },
    h('p', { class: 'si-h' }, 'What the scene shows'),
    h('dl', { class: 'si-kinds' },
      h('div', null, h('dt', null, h('span', { class: 'prov prov-sim' }, 'Simulated')), h('dd', null, 'Trajectory, attitude, throttle, estimate and events, from the run record.')),
      h('div', null, h('dt', null, h('span', { class: 'prov prov-ctx' }, 'Context')), h('dd', null, `${str(env.name)}: ${contextText(env, h1, im)} The model assumes flat ground at the pad; nothing is computed against this terrain.`)),
      worldText(env) ? h('div', null, h('dt', null, h('span', { class: 'prov prov-ctx' }, 'On the ground')), h('dd', null, worldText(env))) : null,
      note ? h('div', null, h('dt', null, h('span', { class: 'prov prov-ctx' }, 'Site')), h('dd', null, note)) : null,
      h('div', null, h('dt', null, h('span', { class: 'prov prov-ill' }, 'Illustrative')), h('dd', null, `Stage shape, weathering, legs, fins, plume, the glow and dust where it meets the ground, sky, haze, sun, shadows, water finish, fine ground grain${env.world ? ', building walls and roofs, and the shapes and leaves of plants' : ''} and pad surface: drawn for legibility, not modelled.`))),
    warn ? h('p', { class: 'si-warn' }, warn) : null,
    acc.length ? h('p', { class: 'si-h' }, 'Accuracy') : null,
    acc.length ? h('ul', { class: 'si-list' }, acc.map((a) => h('li', null, a))) : null,
    h('p', { class: 'si-h' }, 'Sources and licences'),
    h('ul', { class: 'si-list si-sources' }, sourcesOf(env).map((s) => {
      const url = licenceUrl(s.licence);
      return h('li', null,
        h('p', { class: 'si-prod' }, str(s.product)),
        str(s.attribution) ? h('p', { class: 'si-attr' }, str(s.attribution)) : null,
        h('p', { class: 'si-lic' }, str(s.licence).replace(url || '\u0000', '').trim(), url ? h('span', { class: 'si-url mono' }, ` ${url}`) : null));
    })),
    onSettings ? h('button', { type: 'button', class: 'link small si-more', onclick: () => { close(); onSettings(); } }, 'Environment details in Settings') : null);
  // The credit of every source whose licence asks for one; the full notices are in the panel.
  const credits = mapCredits(env);
  const credit = credits.length ? h('p', { class: 'si-credit', title: 'Full notices and licences: Sources' }, credits.join(' · ')) : null;
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
