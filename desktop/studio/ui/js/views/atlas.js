// Environments and cinematic experiences (M18): every validated geographic pack as a large card with
// its own image, the facts the shell validated, the sources it credits and the way to fly there. The
// chosen pack becomes the mission player's environment (the same preference the player's selector
// writes). The simulation always runs on flat ground; the landscape is geographic context.

import { h, clear, prose } from '../dom.js';
import { pref, setPref } from '../store.js';
import { listEnvironments, mb } from '../environments.js';
import { thumbnail, resolutionLines } from '../env-catalogue.js';
import { shortCredits } from '../sources-info.js';
import { cinematicStatus } from '../cinematic.js';
import { errorText } from '../ui.js';

let root;
let navigate = () => {};

export function initAtlas(el, nav) {
  root = el;
  navigate = nav;
}

const n = (v) => Number(v || 0).toLocaleString('en');

/** Data level of a pack, from what its manifest declares (see docs/m17-environments.md). */
function level(e) {
  const d = (e.layers || []).find((l) => l.role === 'detail');
  const veg = e.world && e.world.vegetation;
  if (d && d.height.spacing_m <= 2 && veg) return { word: 'Lidar terrain and vegetation', tone: 'a' };
  if (d) return { word: 'High-resolution detail', tone: 'b' };
  return { word: 'Base imagery', tone: 'c' };
}

function worldText(e) {
  const w = e.world;
  if (!w) return null;
  const bits = [];
  if (w.features) bits.push(`${n(w.features.buildings + (w.features.lidar_structures || 0))} buildings`);
  if (w.vegetation) bits.push(`${n(w.vegetation.count)} lidar trees and shrubs`);
  return bits.join(' · ') || null;
}

function relief(e) {
  const r = (e.relief || []).find((x) => x.radius_m === 500);
  return r ? `${(r.max_up_m - r.min_up_m).toFixed(0)} m relief within 500 m` : null;
}

function useEnv(id, view = 'geospatial') {
  setPref('missionEnvironment', id);
  setPref('missionView', view);
}

function card(e, current, onPick) {
  const img = h('img', { class: 'at-img', alt: '', loading: 'lazy', width: 320, height: 320 });
  thumbnail(e.id).then((u) => { img.src = u; }).catch(() => img.classList.add('is-missing'));
  const lv = level(e);
  const chosen = e.id === current;
  const fly = (exp) => { useEnv(e.id); navigate('mission', { experienceId: exp }); };
  return h('article', { class: ['at-card', chosen ? 'is-current' : ''], dataset: { env: e.id } },
    h('div', { class: 'at-art' }, img,
      h('span', { class: `at-level at-level-${lv.tone}` }, lv.word),
      chosen ? h('span', { class: 'at-using' }, 'Used by the missions') : null),
    h('div', { class: 'at-body' },
      h('h3', { class: 'at-name' }, e.name),
      h('p', { class: 'at-sum' }, prose(e.summary)),
      h('ul', { class: 'at-facts' },
        ...resolutionLines(e).slice(0, 1).map((x) => h('li', null, x)),
        relief(e) ? h('li', null, relief(e)) : null,
        worldText(e) ? h('li', null, worldText(e)) : null,
        h('li', null, `${mb(e.bytes)}, offline · ${e.kind === 'bundled' ? 'installed with Studio' : 'imported'}`)),
      h('p', { class: 'at-credit' }, shortCredits(e).join(' · ')),
      h('div', { class: 'at-actions' },
        h('button', { type: 'button', class: 'btn btn-primary btn-sm', dataset: { action: 'fly', env: e.id }, title: 'Play the first landing on this landscape in the geospatial view', onclick: () => fly('first-landing') }, 'Land a rocket here'),
        chosen ? null : h('button', { type: 'button', class: 'btn btn-sm', dataset: { action: 'use', env: e.id }, onclick: () => { useEnv(e.id); onPick(); } }, 'Use for missions'))));
}

export async function showAtlas() {
  const status = h('p', { class: 'small dim' }, 'Reading the validated environment packs…');
  const grid = h('div', { class: 'at-grid' });
  const cine = h('section', { class: 'at-cine', 'aria-label': 'Cinematic View' });
  const page = h('div', { class: 'at' },
    h('header', { class: 'at-head' },
      h('p', { class: 'eyebrow' }, 'Environments and cinematic experiences'),
      h('h1', null, 'Choose where the mission flies.'),
      h('p', { class: 'at-lede' }, 'Real places built from open geographic data: orthophotos, lidar and survey terrain, OpenStreetMap buildings and lidar-measured vegetation. Each pack is validated on this machine before it is listed: file hashes, grid sizes and its own geodetic check points. The simulation runs on flat ground in every case; the landscape is context, never an input to the physics.'),
      status),
    grid, cine);
  clear(root).append(page);
  let list;
  try {
    list = await listEnvironments();
  } catch (e) {
    status.textContent = `The environments could not be read: ${errorText(e)}`;
    status.className = 'error-text';
    return;
  }
  const envs = list.environments;
  const render = () => {
    const current = pref('missionEnvironment');
    clear(grid).append(...envs.map((e) => card(e, current, render)));
  };
  status.textContent = `${envs.length} environments validated and installed, ${mb(envs.reduce((a, e) => a + (e.bytes || 0), 0))} in all.${list.rejected && list.rejected.length ? ` ${list.rejected.length} pack${list.rejected.length > 1 ? 's were' : ' was'} rejected; see Settings, Environments.` : ''}`;
  render();
  cine.append(h('div', null,
    h('p', { class: 'eyebrow' }, 'Cinematic View'),
    h('h2', null, 'The same record, rendered for the eye'),
    h('p', { class: 'small' }, 'An optional replay window with physically based lighting, atmosphere, volumetric plume and terrain detail. It reads the stored run record and the environment pack and never simulates: positions, attitude, throttle and events are those of the record, and the verdicts are hidden until the end of playback. Open it from a rocket landing in the mission player.'),
    h('p', { class: 'small at-cine-status', 'aria-live': 'polite' }, 'Checking the module…')));
  cinematicStatus().then((s) => {
    const el = cine.querySelector('.at-cine-status');
    el.textContent = s.installed && s.verified ? `Installed: version ${s.version}; every file matches its manifest.` : `${s.reason || 'Not installed.'} Install it in Settings from a module zip.`;
  }).catch((e) => { cine.querySelector('.at-cine-status').textContent = `The module status could not be read: ${errorText(e)}`; });
  cine.append(h('div', { class: 'row' },
    h('button', { type: 'button', class: 'btn btn-primary', onclick: () => { const id = pref('missionEnvironment') || (envs[0] && envs[0].id); if (id) useEnv(id); navigate('mission', { experienceId: 'first-landing' }); } }, 'Open a landing in the player'),
    h('button', { type: 'button', class: 'btn btn-quiet', onclick: () => navigate('settings') }, 'Module settings')));
}
