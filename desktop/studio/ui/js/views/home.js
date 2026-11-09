// Mission Control home (M18): three paths into the platform (launch a mission, design a vehicle,
// explore environments and the cinematic replay), the end-to-end experiment as one strip of steps,
// the featured missions and the claim challenge. Nothing here shows a result; results appear only in
// the mission player and the analysis views, from run records.

import { h, clear } from '../dom.js';
import { state, visibleDomains } from '../store.js';
import { available, DOMAIN_NAMES, GRADES } from '../experiences.js';
import { listEnvironments } from '../environments.js';
import { thumbnail } from '../env-catalogue.js';

let root;
let navigate = () => {};

const FEATURED = ['to-orbit', 'first-landing', 'off-the-pad', 'lying-altimeter', 'late-gnss', 'corridor'];

export function initHome(el, nav) {
  root = el;
  navigate = nav;
}

const svgNS = 'http://www.w3.org/2000/svg';
function svg(viewBox, cls, build) {
  const s = document.createElementNS(svgNS, 'svg');
  s.setAttribute('viewBox', viewBox);
  s.setAttribute('class', cls);
  s.setAttribute('aria-hidden', 'true');
  const el = (tag, attrs) => { const e = document.createElementNS(svgNS, tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); s.append(e); return e; };
  build(el);
  return s;
}

/** Illustration of the mission path: an ascent arc, separation and a return arc. Drawn, not data. */
function missionArt() {
  return svg('0 0 320 150', 'hm-art hm-art-mission', (el) => {
    el('path', { d: 'M10 140 Q 300 140 310 140', class: 'hm-ground' });
    el('path', { d: 'M40 138 C 60 90, 110 40, 200 22 S 300 12, 316 10', class: 'hm-arc' });
    el('path', { d: 'M150 34 C 120 60, 80 110, 48 138', class: 'hm-arc hm-arc-back' });
    el('circle', { cx: 150, cy: 34, r: 3.5, class: 'hm-dot' });
    el('circle', { cx: 40, cy: 138, r: 3, class: 'hm-dot' });
    el('text', { x: 158, y: 50, class: 'hm-art-t' }).textContent = 'separation';
  });
}

function vehicleArt() {
  return svg('0 0 320 150', 'hm-art hm-art-vehicle', (el) => {
    el('path', { d: 'M10 140 L 310 140', class: 'hm-ground' });
    const rocket = (x, w, hgt, two) => {
      const top = 138 - hgt;
      el('polygon', { points: `${x},${top + 10} ${x + w / 2},${top} ${x + w},${top + 10}`, class: 'hm-band' });
      el('rect', { x, y: top + 10, width: w, height: hgt - 12, rx: 1.5, class: 'hm-body' });
      if (two) el('rect', { x, y: top + hgt * 0.34, width: w, height: 2, class: 'hm-band' });
    };
    rocket(70, 16, 118, true);
    rocket(120, 11, 74, true);
    rocket(170, 13, 64, false);
    rocket(212, 15, 80, false);
    rocket(256, 9, 44, false);
  });
}

function featuredItem(x, i, launch) {
  const g = GRADES[x.exp.grade];
  return h('li', { dataset: { experience: x.exp.id } }, h('button', { type: 'button', class: 'home-show-item', dataset: { action: 'launch' }, disabled: !x.demo, title: x.reason || null, onclick: () => launch(x.exp.id) },
    h('span', { class: 'home-show-n mono' }, String(i + 1).padStart(2, '0')),
    h('span', { class: 'home-show-body' },
      h('span', { class: 'home-show-k' }, `${DOMAIN_NAMES[x.exp.domain]} · ${x.exp.kicker}`),
      h('span', { class: 'home-show-t' }, x.exp.title),
      h('span', { class: 'home-show-s' }, x.exp.summary),
      x.reason ? h('span', { class: 'warn-text small' }, x.reason) : null),
    h('span', { class: `grade grade-${g.tone}` }, g.label)));
}

export function showHome() {
  const items = available();
  const byId = new Map(items.map((x) => [x.exp.id, x]));
  const launch = (id) => navigate('mission', { experienceId: id });
  const domains = visibleDomains().filter((d) => d.catalog);
  const vehicles = domains.reduce((a, d) => a + d.catalog.vehicles.length, 0);
  const missions = items.filter((x) => x.demo).length;

  const envCount = h('b', { class: 'mono' }, '…');
  const mosaic = h('div', { class: 'hm-mosaic', 'aria-hidden': 'true' });
  const envNames = h('p', { class: 'hm-path-sub' }, 'Reading the validated packs…');
  listEnvironments().then((l) => {
    const envs = l.environments;
    envCount.textContent = String(envs.length);
    envNames.textContent = envs.map((e) => e.name.split(',')[0]).join(' · ');
    for (const e of envs.slice(0, 6)) {
      const img = h('img', { alt: '', loading: 'lazy' });
      thumbnail(e.id).then((u) => { img.src = u; }).catch(() => img.remove());
      mosaic.append(img);
    }
  }).catch(() => { envCount.textContent = '0'; envNames.textContent = 'No environment could be read.'; });

  const quick = (id, label) => {
    const x = byId.get(id);
    return x ? h('button', { type: 'button', class: 'hm-quick', dataset: { experience: id }, disabled: !x.demo, title: x.reason || x.exp.summary, onclick: () => launch(id) }, label || x.exp.title, h('span', { 'aria-hidden': 'true' }, ' →')) : null;
  };

  const head = h('section', { class: 'hm-head' },
    h('div', null,
      h('p', { class: 'eyebrow' }, 'Mission Control'),
      h('h1', { class: 'hm-h1' }, 'Fly it, break it, find out why.'),
      h('p', { class: 'hm-lead' }, 'A deterministic simulator of autonomous vehicles on this machine: launch a two-stage rocket to orbit or land a reusable stage, change what the vehicle is made of, and watch the same recorded mission as engineering telemetry or as a cinematic replay. Every run is a record the platform can replay and recompute.')),
    h('dl', { class: 'hm-stats', 'aria-label': 'What is installed' },
      h('div', null, h('dt', null, 'Missions'), h('dd', { class: 'mono' }, String(missions))),
      h('div', null, h('dt', null, 'Vehicles'), h('dd', { class: 'mono' }, String(vehicles))),
      h('div', null, h('dt', null, 'Environments'), h('dd', null, envCount)),
      h('div', null, h('dt', null, 'Domains'), h('dd', { class: 'mono' }, String(domains.length)))));

  const paths = h('section', { class: 'hm-paths', 'aria-label': 'Where to start' },
    h('article', { class: 'hm-path', dataset: { path: 'mission' } },
      missionArt(),
      h('span', { class: 'hm-art-note' }, 'Illustration'),
      h('div', { class: 'hm-path-body' },
        h('p', { class: 'hm-path-k mono' }, '01'),
        h('h2', null, 'Launch and explore a mission'),
        h('p', null, 'Ascent to orbit with staging, powered landings, sensor faults. Each mission runs the real simulator and plays back what happened, with the verdicts at the end.'),
        h('div', { class: 'hm-quicks' }, quick('to-orbit'), quick('first-landing')),
        h('button', { type: 'button', class: 'btn btn-primary', dataset: { action: 'missions' }, onclick: () => navigate('missions') }, 'Open the mission library'))),
    h('article', { class: 'hm-path', dataset: { path: 'vehicle' } },
      vehicleArt(),
      h('span', { class: 'hm-art-note' }, 'Illustration, not to scale'),
      h('div', { class: 'hm-path-body' },
        h('p', { class: 'hm-path-k mono' }, '02'),
        h('h2', null, 'Design or configure a vehicle'),
        h('p', null, `${vehicles} vehicles with distinct physical parameters the simulator integrates: mass, propellant, thrust, specific impulse, payload. Change one, fly it again and see the flight change.`),
        h('p', { class: 'hm-path-sub' }, 'Launchers · landing stages · ground robot'),
        h('button', { type: 'button', class: 'btn btn-primary', dataset: { action: 'vehicles' }, onclick: () => navigate('vehicles') }, 'Open the hangar'))),
    h('article', { class: 'hm-path', dataset: { path: 'environments' } },
      mosaic,
      h('span', { class: 'hm-art-note' }, 'Pack images, geographic context'),
      h('div', { class: 'hm-path-body' },
        h('p', { class: 'hm-path-k mono' }, '03'),
        h('h2', null, 'Explore environments and cinematic replays'),
        h('p', null, 'Real launch sites and landscapes from open geographic data, validated offline. Fly a mission over one, or replay a recorded landing in the Cinematic View.'),
        envNames,
        h('button', { type: 'button', class: 'btn btn-primary', dataset: { action: 'environments' }, onclick: () => navigate('environments') }, 'Open the environments'))));

  const flow = h('section', { class: 'hm-flow', 'aria-label': 'An experiment from start to finish' },
    h('h2', null, 'One experiment, start to finish'),
    h('ol', null,
      flowStep('Pick a vehicle', 'Hangar', () => navigate('vehicles')),
      flowStep('Pick a landscape', 'Environments', () => navigate('environments')),
      flowStep('Run the mission', 'Hangar, Design and fly', () => navigate('vehicles')),
      flowStep('Change a parameter', 'Lab, vehicle design', () => navigate('lab')),
      flowStep('Compare the runs', 'Lab and Compare', () => navigate('lab')),
      flowStep('Watch both', 'Lab, Watch both runs', () => navigate('lab'))));

  const featured = h('section', { class: 'hm-featured' },
    h('header', null, h('h2', null, 'Featured missions'), h('button', { type: 'button', class: 'link', onclick: () => navigate('missions') }, `All ${missions} missions →`)),
    h('ol', { class: 'home-show', 'aria-label': 'Featured missions' }, FEATURED.map((id) => byId.get(id)).filter(Boolean).map((x, i) => featuredItem(x, i, launch))));

  const challenge = h('section', { class: 'home-challenge' },
    h('div', null,
      h('p', { class: 'eyebrow' }, 'Research'),
      h('h2', null, 'Challenge a safety claim'),
      h('p', null, 'An engineering claim such as “the stage lands softly whenever the GNSS error is between 5 and 30 m” is only as good as the conditions it was tested in. The investigation engine searches the claim’s envelope for the conditions where it breaks.')),
    h('ol', { class: 'home-steps' },
      step('Search', 'Try conditions inside the claim’s declared envelope.'),
      step('Reproduce', 'Keep a counterexample only if it fails again on fresh seeds.'),
      step('Explain', 'Test the suspected cause with declared interventions.'),
      step('Fix and verify', 'Check candidate fixes for regressions; recompute every verdict.')),
    h('div', { class: 'row' },
      h('button', { type: 'button', class: 'btn', onclick: () => navigate('mission', { experienceId: 'late-gnss' }) }, 'See a claim break'),
      h('button', { type: 'button', class: 'btn btn-quiet', onclick: () => navigate('discover') }, 'Investigate a claim')));

  const foot = h('footer', { class: 'home-foot' },
    h('p', { class: 'small dim' }, `${domains.length} simulation domain${domains.length === 1 ? '' : 's'} installed: ${domains.map((d) => d.manifest.name).join(', ') || 'none'}.${state.info && state.info.version ? ` Studio ${state.info.version}.` : ''} Runs on this machine, offline. Same seed, same result.`),
    h('p', { class: 'small dim' }, 'Every model is an idealised demonstrator with stated assumptions, not flight or vehicle software, and none is validated against flight data. Exploratory results have not been confirmed by a preregistered protocol. 3D models, plumes and landscapes are illustration; only the record is simulation.'));

  clear(root).append(h('div', { class: 'home hm' }, head, paths, flow, featured, challenge, foot));
}

function flowStep(title, where, run) {
  return h('li', null, h('button', { type: 'button', class: 'hm-step', onclick: run }, h('b', null, title), h('span', null, where)));
}

function step(title, text) {
  return h('li', null, h('b', null, title), h('span', null, text));
}
