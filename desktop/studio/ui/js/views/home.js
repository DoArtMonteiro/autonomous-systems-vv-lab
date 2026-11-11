// Home: what the product does, one click into a first mission, the curated showcase and the three
// ways in (watch, experiment, challenge). Nothing here shows a result; results appear only in the
// mission player and the analysis views, from run records.

import { h, clear } from '../dom.js';
import { state, visibleDomains } from '../store.js';
import { available, DOMAIN_NAMES, GRADES } from '../experiences.js';

let root;
let navigate = () => {};

const SHOWCASE = ['first-landing', 'lying-altimeter', 'late-gnss', 'threshold-trade-off', 'corridor'];

export function initHome(el, nav) {
  root = el;
  navigate = nav;
}

export function showHome() {
  const items = available();
  const byId = new Map(items.map((x) => [x.exp.id, x]));
  const first = byId.get('first-landing');
  const launch = (id) => navigate('mission', { experienceId: id });
  const domains = visibleDomains().filter((d) => d.catalog);

  const hero = h('section', { class: 'home-hero' },
    h('div', { class: 'home-hero-text' },
      h('p', { class: 'eyebrow' }, 'Autonomous Systems V&V Lab'),
      h('h1', { class: 'home-h1' }, 'Watch autonomous systems work, fail, and show you why.'),
      h('p', { class: 'home-lead' }, 'Simulate a rocket landing or a ground vehicle in a deterministic simulator, break a sensor, and see what the controller does about it. Then put an engineering claim to the test: the platform searches for the conditions under which it stops holding.'),
      h('div', { class: 'home-cta', dataset: { experience: 'first-landing' } },
        h('button', { type: 'button', class: 'btn btn-primary btn-lg', dataset: { action: 'launch' }, disabled: !first || !first.demo, title: first && first.reason ? first.reason : null, onclick: () => launch('first-landing') }, 'Watch a rocket land'),
        h('button', { type: 'button', class: 'btn btn-lg btn-ghost', onclick: () => navigate('missions') }, 'Browse all missions')),
      first && first.reason ? h('p', { class: 'warn-text small' }, first.reason) : null,
      h('p', { class: 'home-facts' },
        h('span', null, 'Runs on this machine, offline'),
        h('span', null, 'Same seed, same result'),
        h('span', null, 'Simulation evidence, not flight certification'))),
    h('ol', { class: 'home-show', 'aria-label': 'Showcase missions' },
      SHOWCASE.map((id, i) => {
        const x = byId.get(id);
        if (!x) return null;
        const g = GRADES[x.exp.grade];
        return h('li', { dataset: { experience: id } }, h('button', { type: 'button', class: 'home-show-item', dataset: { action: 'launch' }, disabled: !x.demo, title: x.reason || null, onclick: () => launch(id) },
          h('span', { class: 'home-show-n mono' }, String(i + 1).padStart(2, '0')),
          h('span', { class: 'home-show-body' },
            h('span', { class: 'home-show-k' }, `${DOMAIN_NAMES[x.exp.domain]} · ${x.exp.kicker}`),
            h('span', { class: 'home-show-t' }, x.exp.title),
            h('span', { class: 'home-show-s' }, x.exp.summary),
            x.reason ? h('span', { class: 'warn-text small' }, x.reason) : null),
          h('span', { class: `grade grade-${g.tone}` }, g.label)));
      })));

  const doors = h('section', { class: 'home-doors', 'aria-label': 'Ways in' },
    door('Watch', 'Explorer', 'Pick a mission, press play and follow the vehicle. Each mission says what it is trying to do, what to watch, and why it ended the way it did.', 'Mission library', () => navigate('missions')),
    door('Experiment', 'Analyst', 'Choose the controller, the seed, up to two faults and the tuning, then inspect every channel: true state, sensor readings, the controller’s estimate and its commands.', 'Configure a run', () => navigate('prepare')),
    door('Challenge', 'Researcher', 'Pick a bounded safety claim and let the engine search for a counterexample, reproduce it on fresh seeds, test its cause and candidate fixes, and recompute the evidence.', 'Investigate a claim', () => navigate('discover')));

  const challenge = h('section', { class: 'home-challenge' },
    h('div', null,
      h('p', { class: 'eyebrow' }, 'Signature feature'),
      h('h2', null, 'Challenge this claim'),
      h('p', null, 'An engineering claim such as “the stage lands softly whenever the GNSS error is between 5 and 30 m” is only as good as the conditions it was tested in. Challenging it asks the platform to look for the conditions where it breaks.')),
    h('ol', { class: 'home-steps' },
      step('Search', 'Try conditions inside the claim’s declared envelope.'),
      step('Reproduce', 'Keep a counterexample only if it fails again on fresh seeds.'),
      step('Explain', 'Test the suspected cause with declared interventions.'),
      step('Fix and verify', 'Check candidate fixes for regressions; recompute every verdict.')),
    h('button', { type: 'button', class: 'btn', onclick: () => navigate('mission', { experienceId: 'late-gnss' }) }, 'See a claim break'));

  const foot = h('footer', { class: 'home-foot' },
    h('p', { class: 'small dim' }, `${domains.length} simulation domain${domains.length === 1 ? '' : 's'} installed: ${domains.map((d) => d.manifest.name).join(', ') || 'none'}.${state.info && state.info.version ? ` Studio ${state.info.version}.` : ''}`),
    h('p', { class: 'small dim' }, 'Every model is an idealised demonstrator with stated assumptions, not flight or vehicle software. Findings marked exploratory have not been confirmed by a preregistered protocol.'));

  clear(root).append(h('div', { class: 'home' }, hero, doors, challenge, foot));
}

function door(title, level, text, action, run) {
  return h('article', { class: 'home-door' },
    h('p', { class: 'eyebrow' }, level),
    h('h2', null, title),
    h('p', null, text),
    h('button', { type: 'button', class: 'link home-door-a', onclick: run }, `${action} →`));
}

function step(title, text) {
  return h('li', null, h('b', null, title), h('span', null, text));
}
