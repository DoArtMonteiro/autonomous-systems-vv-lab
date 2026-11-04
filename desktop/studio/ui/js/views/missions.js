// The mission library: every curated experience as a card, filtered by category and domain. A card
// says what the mission is, what it teaches, how it is graded and whether a claim stands behind it,
// and launches it in the mission player. An unavailable mission says why.

import { h, clear } from '../dom.js';
import { pref, setPref } from '../store.js';
import { available, CATEGORIES, DOMAIN_NAMES, GRADES } from '../experiences.js';

let root;
let navigate = () => {};
let filter = { category: 'all', domain: 'all' };

export function initMissions(el, nav) {
  root = el;
  navigate = nav;
}

export function showMissions(opts) {
  const saved = pref('missionFilter');
  if (saved && typeof saved === 'object' && !filter.loaded) filter = { category: saved.category || 'all', domain: saved.domain || 'all', loaded: true };
  if (opts && opts.category) filter.category = opts.category;
  render();
}

function setFilter(k, v) {
  filter = { ...filter, [k]: v };
  setPref('missionFilter', { category: filter.category, domain: filter.domain });
  render();
}

function chips(label, key, options) {
  return h('div', { class: 'ml-chips', role: 'radiogroup', 'aria-label': label },
    options.map(([v, text, count]) => h('button', { type: 'button', role: 'radio', class: 'ml-chip', 'aria-checked': String(filter[key] === v), dataset: { [key]: v }, onclick: () => setFilter(key, v) },
      text, count !== undefined ? h('span', { class: 'ml-count' }, String(count)) : null)));
}

function render() {
  const all = available();
  const inDomain = all.filter((x) => filter.domain === 'all' || x.exp.domain === filter.domain);
  const shown = inDomain.filter((x) => filter.category === 'all' || x.exp.categories.includes(filter.category));
  const domains = [...new Set(all.map((x) => x.exp.domain))];
  clear(root).append(h('div', { class: 'ml' },
    h('header', { class: 'ml-head' },
      h('p', { class: 'eyebrow' }, 'Mission library'),
      h('h1', null, 'Pick a mission'),
      h('p', { class: 'ml-lead' }, 'Each mission runs the real simulator on this machine and plays back what happened. Start at the top if this is new to you; the later ones challenge claims and compare fixes.')),
    h('div', { class: 'ml-filters' },
      chips('Category', 'category', [['all', 'All', inDomain.length], ...CATEGORIES.map((c) => [c.id, c.label, inDomain.filter((x) => x.exp.categories.includes(c.id)).length])]),
      chips('Domain', 'domain', [['all', 'Both domains'], ...domains.map((d) => [d, DOMAIN_NAMES[d] || d])])),
    shown.length ? h('ul', { class: 'ml-grid' }, shown.map((x) => card(x))) : h('p', { class: 'empty' }, 'No mission matches these filters.')));
}

function card({ exp, demo, reason }) {
  const g = GRADES[exp.grade];
  return h('li', { class: ['ml-card', !demo && 'is-off'], dataset: { experience: exp.id } },
    h('p', { class: 'ml-kicker' }, h('span', null, DOMAIN_NAMES[exp.domain] || exp.domain), h('span', { 'aria-hidden': 'true' }, ' · '), h('span', null, exp.kicker)),
    h('h2', { class: 'ml-title' }, exp.title),
    h('p', { class: 'ml-summary' }, exp.summary),
    h('div', { class: 'ml-learn' }, h('p', { class: 'ml-label' }, 'You will see'), h('ul', null, exp.learn.map((l) => h('li', null, l)))),
    h('dl', { class: 'ml-meta' },
      h('div', null, h('dt', null, 'Level'), h('dd', null, exp.level)),
      h('div', null, h('dt', null, 'Runs'), h('dd', null, String(exp.runs.length))),
      h('div', null, h('dt', null, 'Watch time'), h('dd', null, `about ${exp.minutes} min`))),
    h('div', { class: 'ml-badges' },
      h('span', { class: `grade grade-${g.tone}`, title: g.text }, g.label),
      exp.claim ? h('span', { class: 'grade grade-claim', title: 'A bounded safety claim stands behind this mission; you can challenge it from the player.' }, 'Claim behind it') : null),
    reason ? h('p', { class: 'warn-text small' }, reason) : null,
    h('button', { type: 'button', class: 'btn btn-primary ml-go', dataset: { action: 'launch' }, disabled: !demo, onclick: () => navigate('mission', { experienceId: exp.id }) }, 'Run mission'));
}
