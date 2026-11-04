// The mission library: presentation of the curated demonstrations. Every experience points at a
// demonstration that its domain host ships and tests (`demos` in the catalog: requests, narrative,
// expectation). This file only adds how to present it: plain-language objective, what to watch,
// category, the label of each run, the claim it can challenge and the evidence grade. It never states
// a result; results come from the run records the host computes.

import { domainById, visibleDomains } from './store.js';

/** Evidence grades, from the weakest to the strongest the platform can show. */
export const GRADES = {
  demonstration: { label: 'Demonstration', tone: 'neutral', text: 'One development seed, chosen to show the behaviour. It illustrates; it does not measure a rate.' },
  exploratory: { label: 'Exploratory finding', tone: 'explore', text: 'Measured on fresh development seeds by an investigation. Not confirmed by a preregistered protocol.' },
};

export const CATEGORIES = [
  { id: 'start', label: 'Start here' },
  { id: 'faults', label: 'Faults and failures' },
  { id: 'compare', label: 'Compare systems' },
  { id: 'robustness', label: 'Robustness' },
  { id: 'claims', label: 'Challenge a claim' },
];

export const DOMAIN_NAMES = { 'rocket-landing': 'Rocket landing', 'ground-vehicle': 'Ground vehicle' };

/** Order is the order of the library and of the home showcase. */
export const EXPERIENCES = [
  {
    id: 'first-landing', domain: 'rocket-landing', demo: 'nominal-landing',
    title: 'Land a rocket', kicker: 'Start here',
    summary: 'A rocket stage of about 30 t falls from 3 km at 200 m/s and has to stop on a pad with its engine alone.',
    objective: 'Touch down slower than 3 m/s, within 10 m of the pad centre, upright, with fuel to spare, and never break a safety rule on the way.',
    watch: ['The engine lights at about 4 s and the fall slows from 200 m/s to under 2 m/s.', 'The estimate the controller flies on stays close to the true position.'],
    learn: ['What an autonomous controller is asked to do', 'Why the mission result and safety are judged separately'],
    categories: ['start'], level: 'Explorer', minutes: 1, runs: ['Robust controller'],
    grade: 'demonstration', claim: null, next: 'lying-altimeter',
  },
  {
    id: 'lying-altimeter', domain: 'rocket-landing', demo: 'altimeter-reads-high',
    title: 'A sensor that lies', kicker: 'Hidden failure',
    summary: 'The radar altimeter reports 50 m too much height. One controller believes it; the other checks it.',
    objective: 'Same stage, same fault, same random seed. Only the way each controller treats the altimeter differs.',
    watch: ['The baseline run keeps falling fast after the robust run has slowed down.', 'The robust controller rejects the altimeter 0.1 s into the flight.'],
    learn: ['How one wrong sensor can crash a vehicle that works', 'Why cross-checking sensors matters'],
    categories: ['start', 'faults', 'compare'], level: 'Explorer', minutes: 2,
    runs: ['Baseline: trusts the altimeter', 'Robust: cross-checks it'],
    grade: 'demonstration', claim: null, next: 'late-gnss',
  },
  {
    id: 'late-gnss', domain: 'rocket-landing', demo: 'late-gnss-bias',
    title: 'Smaller, later, worse?', kicker: 'Surprising counterexample',
    summary: 'A smaller GNSS error that starts 0.02 s later slips past the safety logic that catches a larger one.',
    objective: 'The guarded controller was registered as landing softly (R1) with a GNSS bias of 5 to 30 m present from the start. Does that still hold when the bias starts a moment later?',
    watch: ['The registered run rejects the altimeter at 0.1 s; the later run never does.', 'The registered run touches down at about 2 m/s but off the pad; the later run hits the pad at about 17 m/s.'],
    learn: ['Why the timing of a fault can matter more than its size', 'Why a counterexample is reported per requirement, not as a single score'],
    categories: ['start', 'faults', 'claims'], level: 'Analyst', minutes: 3,
    runs: ['Registered: 15 m from 0 s', 'Later: 9.72 m from 0.02 s'],
    grade: 'exploratory', claim: 'g3-onset', next: 'threshold-trade-off',
  },
  {
    id: 'threshold-trade-off', domain: 'rocket-landing', demo: 'threshold-trade-off',
    title: 'A fix with a price', kicker: 'Mitigation and trade-off',
    summary: 'Lowering one threshold removes the hard landing and moves the failure to another requirement.',
    objective: 'Test the candidate mitigation of the M13 investigation: reject the altimeter at 1 m of disagreement instead of 3 m.',
    watch: ['With 1 m the altimeter is rejected at 0.18 s; with 3 m it never is.', 'The hard, unsafe landing becomes a touchdown at about 2 m/s, but about 13 m from the pad centre.'],
    learn: ['Why a fix must be checked against every requirement', 'How a regression hides behind an improvement'],
    categories: ['robustness', 'compare', 'claims'], level: 'Analyst', minutes: 3,
    runs: ['Threshold 3 m (default)', 'Threshold 1 m (mitigation)'],
    grade: 'exploratory', claim: 'g3-onset', next: 'corridor',
  },
  {
    id: 'corridor', domain: 'ground-vehicle', demo: 'corridor-gps-noise',
    title: 'One millimetre', kicker: 'Second domain: ground vehicle',
    summary: 'A ground vehicle beside a restricted zone. 1 mm of GPS noise can send it into the zone (12 of 30 fresh seeds in the M13 investigation).',
    objective: 'Reach the waypoint 250 mm above the corner of the zone without ever entering it.',
    watch: ['With exact GPS the vehicle stops on the waypoint.', 'With 1 mm of noise it hunts around the waypoint and steps into the zone at tick 21.'],
    learn: ['How a tolerance set to zero makes a system fragile', 'That the platform is not specific to rockets'],
    categories: ['start', 'robustness', 'claims'], level: 'Explorer', minutes: 2,
    runs: ['Exact GPS', '1 mm of GPS noise', '1 mm noise, 250 mm arrival radius'],
    grade: 'exploratory', claim: 'corridor-noise', next: 'first-landing',
  },
  {
    id: 'two-faults', domain: 'rocket-landing', demo: 'bias-and-outage-unsafe',
    title: 'Two faults at once', kicker: 'Faults and failures',
    summary: 'A biased altimeter and a 10 s GNSS outage. The baseline stage stops descending and climbs under power.',
    objective: 'Land with two sensors faulty at the same time, comparing three controllers.',
    watch: ['The baseline run stops falling near 380 m and climbs.', 'Robust and guarded reject the altimeter and land.'],
    learn: ['What an unsafe run looks like, as opposed to a failed mission'],
    categories: ['faults', 'compare'], level: 'Analyst', minutes: 3,
    runs: ['Baseline', 'Robust', 'Guarded'], grade: 'demonstration', claim: null, next: null,
  },
  {
    id: 'short-outage', domain: 'rocket-landing', demo: 'bias-and-short-outage',
    title: 'Riding out an outage', kicker: 'Faults and failures',
    summary: 'A 20 m altimeter bias and a 6 s GNSS outage; both estimators carry the stage through.',
    objective: 'Land when one sensor lies and another goes silent for six seconds.',
    watch: ['Both controllers reject the altimeter at 0.1 s.', 'Both touch down about 3 m from the pad centre.'],
    learn: ['How an estimator bridges a sensor outage'],
    categories: ['faults'], level: 'Analyst', minutes: 2,
    runs: ['Robust', 'Guarded'], grade: 'demonstration', claim: null, next: null,
  },
  {
    id: 'ground-nominal', domain: 'ground-vehicle', demo: 'nominal-drive',
    title: 'A clean drive', kicker: 'Ground vehicle',
    summary: 'The ground vehicle drives 1.5 m east and stops on its waypoint with no fault.',
    objective: 'Reach the waypoint and stop, keeping every temporal contract and safety invariant.',
    watch: ['Seven ticks to the goal; every contract holds.'], learn: ['The reference run of the ground domain'],
    categories: ['start'], level: 'Explorer', minutes: 1, runs: ['Dominant-axis controller'], grade: 'demonstration', claim: null, next: 'corridor',
  },
  {
    id: 'axis-policy', domain: 'ground-vehicle', demo: 'axis-policy-comparison',
    title: 'Stalled but safe', kicker: 'Compare systems',
    summary: 'Two controllers, one mission. One arrives; the other shuttles in place and never turns north.',
    objective: 'Reach a waypoint 2 m north and 0.25 m east with 0.5 m steps.',
    watch: ['x_first jumps over the small x error every tick.'], learn: ['Why a stalled mission is not an unsafe run'],
    categories: ['compare'], level: 'Analyst', minutes: 2, runs: ['dominant_axis', 'x_first'], grade: 'demonstration', claim: null, next: null,
  },
  {
    id: 'delayed-command', domain: 'ground-vehicle', demo: 'delayed-command-after-fallback',
    title: 'A late command', kicker: 'Faults and failures',
    summary: 'A movement command delayed by the actuator runs after the vehicle has entered its safety fallback.',
    objective: 'Hold still in fallback while a GPS dropout lasts.',
    watch: ['The old command moves the vehicle 250 mm at tick 7, in fallback.'], learn: ['How a timing fault breaks a safety invariant'],
    categories: ['faults'], level: 'Analyst', minutes: 2, runs: ['With the built-in faults', 'Faults removed'], grade: 'demonstration', claim: null, next: null,
  },
];

export function experienceById(id) {
  return EXPERIENCES.find((e) => e.id === id) || null;
}

/** The domain demonstration an experience presents, or null with the reason it is unavailable. */
export function resolve(exp) {
  const d = domainById(exp.domain);
  if (!d || !visibleDomains().includes(d)) return { demo: null, domain: null, reason: `The ${DOMAIN_NAMES[exp.domain] || exp.domain} domain is not installed.` };
  if (!d.catalog) return { demo: null, domain: d, reason: `The ${d.manifest.name} host did not start: ${d.error || 'no catalog'}.` };
  const demo = d.catalog.demos.find((x) => x.id === exp.demo);
  if (!demo) return { demo: null, domain: d, reason: `The ${d.manifest.name} host does not ship the demonstration “${exp.demo}”.` };
  if (demo.requests.length !== exp.runs.length) return { demo: null, domain: d, reason: `The demonstration has ${demo.requests.length} runs; this build expects ${exp.runs.length}.` };
  return { demo, domain: d, reason: null };
}

/** Experiences with their demonstration, or the reason it is unavailable, in library order. */
export function available() {
  return EXPERIENCES.map((e) => ({ exp: e, ...resolve(e) }));
}
