// Vehicle hangar (M18): every vehicle the installed domains simulate, with the attributes each host
// reads from the case template it really flies (catalog `facts`, never typed in the interface), its
// evidence level, the missions that fly it and a way into the Experiment Lab with its design
// parameters open. Nothing here computes a flight: a run starts only in the Lab or the player.

import { h, clear, prose } from '../dom.js';
import { visibleDomains } from '../store.js';
import { EXPERIENCES, resolve } from '../experiences.js';

let root;
let navigate = () => {};

export function initVehicles(el, nav) {
  root = el;
  navigate = nav;
}

const ROLE = {
  'launch-ascent': { order: 0, title: 'Launch vehicles', text: 'Two-stage launchers flown from the pad to a low orbit. After separation the booster and the upper stage are simulated as two vehicles, each judged against its own requirements.', group: 'Vehicle' },
  'rocket-landing': { order: 1, title: 'Landing stages', text: 'Reusable stages that brake to a pad with one gimballed engine. Change the dry mass, the propellant, the thrust or the engine efficiency and fly it again.', group: 'Vehicle design' },
  'ground-vehicle': { order: 2, title: 'Autonomous ground robots', text: 'A wheeled robot driving a corridor beside a restricted zone with noisy GPS. The same verification contract as the rockets.', group: null },
};

/**
 * Evidence level of a vehicle, as its domain states it in the catalog (`evidence`). A vehicle is a
 * reference case only when the domain says so; an unknown or missing level is shown as exploratory,
 * the cautious reading.
 */
function evidence(v) {
  if (v.evidence === 'reference') return { word: 'Reference case', tone: 'ref', text: 'The frozen, pre-registered case the platform’s verification results rest on. Verified model behaviour, not validated against flight data.' };
  return { word: 'Exploratory', tone: 'explore', text: 'Illustrative values of the right order of magnitude. Runs are recomputable records of this model, not evidence for any pre-registered claim.' };
}

const numText = (x) => {
  const a = Math.abs(x);
  const d = a >= 100 ? 0 : a >= 10 ? 1 : 2;
  return x.toLocaleString('en', { maximumFractionDigits: d, minimumFractionDigits: 0 });
};
const factText = (f) => `${numText(f.value)}${f.unit ? (f.unit === '%' ? '%' : ` ${f.unit}`) : ''}`;

/** Missions of the library that fly this vehicle (by the scenario of their first run). */
function missionsOf(d, v) {
  const scen = new Set(d.catalog.scenarios.filter((s) => s.vehicle === v.id).map((s) => s.id));
  return EXPERIENCES.filter((e) => e.domain === d.manifest.id).map((e) => ({ e, r: resolve(e) })).filter(({ r }) => r.demo && scen.has(r.demo.requests[0].scenario));
}

/** A silhouette scaled by the cube root of the full mass: illustrative, labelled as such. */
function silhouette(domainId, v, scale) {
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', '0 0 60 120');
  svg.setAttribute('class', 'hg-sil');
  svg.setAttribute('aria-hidden', 'true');
  const rect = (x, y, w, hh, cls) => { const r = document.createElementNS(ns, 'rect'); Object.entries({ x, y, width: w, height: hh, rx: 1.5, class: cls }).forEach(([k, val]) => r.setAttribute(k, val)); svg.append(r); };
  const poly = (pts, cls) => { const p = document.createElementNS(ns, 'polygon'); p.setAttribute('points', pts); p.setAttribute('class', cls); svg.append(p); };
  const s = Math.max(0.35, Math.min(1, scale));
  if (domainId === 'ground-vehicle') {
    rect(12, 86, 36, 14, 'hg-body'); rect(18, 78, 18, 8, 'hg-band');
    for (const x of [16, 40]) { const c = document.createElementNS(ns, 'circle'); c.setAttribute('cx', x); c.setAttribute('cy', 103); c.setAttribute('r', 5); c.setAttribute('class', 'hg-band'); svg.append(c); }
    return svg;
  }
  const H = 104 * s;
  const W = Math.max(7, 14 * s);
  const x = 30 - W / 2;
  const top = 112 - H;
  if (domainId === 'launch-ascent') {
    const h2 = H * 0.32;
    poly(`${x},${top + 10} ${30},${top} ${x + W},${top + 10}`, 'hg-band');
    rect(x, top + 10, W, h2 - 10, 'hg-body');
    rect(x, top + h2, W, 2, 'hg-band');
    rect(x, top + h2 + 2, W, H - h2 - 8, 'hg-body');
    rect(x - 2, 104, W + 4, 6, 'hg-band');
  } else {
    rect(x, top, W, H - 10, 'hg-body');
    rect(x, top + 3, W, 4, 'hg-band');
    poly(`${x + 2},${112 - 10} ${x - 6},112 ${x + 2},${112 - 4}`, 'hg-band');
    poly(`${x + W - 2},${112 - 10} ${x + W + 6},112 ${x + W - 2},${112 - 4}`, 'hg-band');
    rect(30 - 3, 104, 6, 6, 'hg-band');
  }
  return svg;
}

function fullMass(v) {
  const get = (label) => ((v.facts || []).find((f) => f.label === label) || {}).value;
  return get('Liftoff mass') || ((get('Dry mass') || 0) + (get('Propellant') || 0)) || null;
}

function card(d, v, scale) {
  const ev = evidence(v);
  const role = ROLE[d.manifest.id] || { group: null };
  const flies = missionsOf(d, v);
  const scenarios = d.catalog.scenarios.filter((s) => s.vehicle === v.id);
  const design = scenarios.find((s) => /exploratory/i.test(s.label)) || scenarios[0];
  return h('article', { class: 'hg-card', dataset: { vehicle: v.id, domain: d.manifest.id } },
    h('div', { class: 'hg-card-art' }, silhouette(d.manifest.id, v, scale),
      h('span', { class: ['hg-ev', `hg-ev-${ev.tone}`], title: ev.text }, ev.word)),
    h('div', { class: 'hg-card-body' },
      h('h3', { class: 'hg-name' }, v.label.replace(/\s*\(exploratory\)/i, '')),
      h('p', { class: 'hg-desc' }, prose(v.description)),
      v.facts && v.facts.length ? h('dl', { class: 'hg-facts' }, v.facts.slice(0, 6).map((f) => h('div', null, h('dt', null, f.label), h('dd', { class: 'mono' }, factText(f))))) : null,
      h('div', { class: 'hg-actions' },
        design ? h('button', { type: 'button', class: 'btn btn-primary btn-sm', dataset: { action: 'design', scenario: design.id },
          title: 'Simulate this vehicle as defined, then change what it is made of and fly it again in the Experiment Lab',
          onclick: () => navigate('lab', { domain: d.manifest.id, scenario: design.id, open: role.group }) }, role.group === 'Vehicle design' ? 'Design and fly' : 'Configure and fly') : null,
        flies.length ? h('button', { type: 'button', class: 'btn btn-sm', dataset: { action: 'watch', experience: flies[0].e.id }, onclick: () => navigate('mission', { experienceId: flies[0].e.id }) }, `Watch: ${flies[0].e.title}`) : null),
      flies.length > 1 ? h('p', { class: 'small dim hg-more' }, `Also in ${flies.length - 1} more mission${flies.length > 2 ? 's' : ''}: ${flies.slice(1).map((x) => x.e.title).join(', ')}.`) : null));
}

/** Side-by-side table of the vehicles of one domain, from their facts. */
function compareTable(vehicles) {
  const labels = [...new Set(vehicles.flatMap((v) => (v.facts || []).map((f) => f.label)))];
  if (!labels.length || vehicles.length < 2) return null;
  return h('div', { class: 'hg-table-wrap' }, h('table', { class: 'grid-table hg-table' },
    h('caption', { class: 'small dim' }, 'Read by the domain host from the case template each vehicle is simulated with.'),
    h('thead', null, h('tr', null, h('th', null, 'Attribute'), vehicles.map((v) => h('th', null, v.label.replace(/\s*\(exploratory\)/i, ''))))),
    h('tbody', null, labels.map((l) => h('tr', null, h('th', { scope: 'row' }, l), vehicles.map((v) => { const f = (v.facts || []).find((x) => x.label === l); return h('td', { class: 'mono' }, f ? factText(f) : '–'); }))))));
}

export function showVehicles() {
  const doms = visibleDomains().filter((d) => d.catalog && d.catalog.vehicles.length);
  doms.sort((a, b) => ((ROLE[a.manifest.id] || { order: 9 }).order - (ROLE[b.manifest.id] || { order: 9 }).order));
  const all = doms.flatMap((d) => d.catalog.vehicles.map((v) => ({ d, v })));
  const masses = all.map(({ v }) => fullMass(v)).filter(Boolean);
  const maxMass = Math.max(...masses, 1);
  const sections = doms.map((d) => {
    const role = ROLE[d.manifest.id] || { title: d.manifest.name, text: '' };
    const vs = d.catalog.vehicles;
    return h('section', { class: 'hg-sec', dataset: { domain: d.manifest.id } },
      h('header', { class: 'hg-sec-head' }, h('h2', null, role.title), h('p', null, role.text)),
      h('div', { class: 'hg-grid' }, vs.map((v) => card(d, v, fullMass(v) ? Math.cbrt(fullMass(v) / maxMass) : 0.6))),
      compareTable(vs));
  });
  clear(root).append(h('div', { class: 'hg' },
    h('header', { class: 'hg-head' },
      h('p', { class: 'eyebrow' }, 'Vehicle hangar'),
      h('h1', null, 'Pick a vehicle. Change what it is made of. Fly it.'),
      h('p', { class: 'hg-lede' }, `${all.length} vehicles across ${doms.length} simulation domains. Each one is a set of physical parameters the simulator integrates, not a skin. What a change does to a landing or an ascent is read from the new run, not assumed. Design changes run as new simulations in the Experiment Lab and can be watched, compared and replayed.`),
      h('ul', { class: 'hg-legend' },
        h('li', null, h('span', { class: 'hg-ev hg-ev-ref' }, 'Reference case'), ' frozen, pre-registered case; verified model behaviour, not flight data'),
        h('li', null, h('span', { class: 'hg-ev hg-ev-explore' }, 'Exploratory'), ' illustrative values; recomputable, not evidence for a claim'),
        h('li', null, h('span', { class: 'hg-ev hg-ev-ill' }, 'Illustrative'), ' silhouettes and 3D models are drawn, never read by the simulation'))),
    sections,
    h('section', { class: 'hg-next' },
      h('h2', null, 'Not in this build'),
      h('p', { class: 'small' }, 'Controlled booster recovery (boost-back and landing burn after separation) and orbital operations beyond the 600 s coast are not simulated yet: the booster falls ballistically after separation. Spacecraft and aircraft have no model yet; the domain contract each vehicle above uses is the one they would plug into.'))));
}
