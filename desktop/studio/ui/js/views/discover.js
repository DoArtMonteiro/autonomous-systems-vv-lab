// Discovery Lab (M13): challenge a bounded safety claim and read the evidence the engine computed.
// Nothing here decides a verdict. Every status word comes from investigation.json, which
// `vv-exec investigate-verify` recomputes from scratch; this view only arranges it.

import uPlot from '../../vendor/uplot/uPlot.esm.js';
import { h, s, clear, num, shortHash } from '../dom.js';
import { invoke } from '../api.js';
import { toast, errorText } from '../ui.js';
import { cssVar, axisStyle } from '../charts.js';

const api = {
  claims: () => invoke('list_claims'),
  packages: () => invoke('list_investigations'),
  open: (name) => invoke('investigation', { name }),
  run: (file) => invoke('investigate', { file }),
  verify: (name) => invoke('verify_investigation', { name }),
  cancel: () => invoke('cancel_investigation'),
  reveal: (name) => invoke('reveal_investigation', { name }),
};

const st = {
  root: null,
  claims: [],
  packages: [],
  claimFile: null,
  pkgName: null,
  data: null,
  running: null,
  charts: [],
  primary: 'counterexample',
  compare: 'twin',
  envelopeSet: 'none',
};

// Plain words for the engine's status codes. Unknown codes are shown as they are.
export const WORDS = {
  refuted: ['Refuted', 'bad', 'A reproduced counterexample breaks the claim beyond its tolerance.'],
  refuted_without_byte_reproduction: ['Refuted, not byte-reproduced', 'bad', 'The counterexample fails on fresh seeds, but the canonical writer did not reproduce its trace byte for byte.'],
  counterexample_within_tolerance: ['Counterexample within tolerance', 'warn', 'A violation was found, but its rate does not exceed the claim tolerance with confidence.'],
  not_refuted_within_budget: ['Not refuted within budget', 'ok', 'No violation found in the challenge budget. This bounds the rate; it does not prove the claim.'],
  experimentally_supported: ['Experimentally supported', 'ok', 'Every declared intervention changed the outcome as predicted, at the counterexample and across the failure region.'],
  supported_only_locally: ['Supported only locally', 'warn', 'The prediction holds at the counterexample but not across the failure region.'],
  contradicted: ['Contradicted', 'bad', 'An intervention or trace check went against the prediction.'],
  unresolved: ['Unresolved', 'warn', 'The evidence neither supports nor contradicts the hypothesis.'],
  untested: ['Untested', 'neutral', 'No intervention or check could be run.'],
  supported: ['Supported', 'ok', ''],
  supported_locally: ['Supported locally', 'warn', ''],
  inconclusive: ['Inconclusive', 'warn', ''],
  not_run: ['Not run', 'neutral', ''],
  general: ['General', 'ok', 'Acts on at least 90 % of the failing envelope pairs.'],
  local: ['Local', 'warn', 'Acts on fewer than 90 % of the failing envelope pairs.'],
  ineffective: ['Ineffective', 'bad', 'Removes the violation in fewer than 90 % of the counterexample seeds.'],
  effective_no_regression_observed: ['Effective, no regression observed', 'ok', 'Removes the violation; no new violation of any requirement or invariant in the paired tests, none in the re-challenge. Observed, within the tests run.'],
  effective_with_residual_counterexamples: ['Effective, residual counterexamples', 'warn', 'Removes this counterexample, but a fresh search still finds violations of the claim.'],
  effective_with_regressions: ['Effective, with regressions', 'bad', 'Removes the violation but adds new safety or claim violations elsewhere.'],
  effective_with_tradeoffs: ['Effective, with trade-offs', 'warn', 'Removes the violation, adds no safety or claim violation, but some paired runs gain other requirement violations (listed below).'],
  inconclusive_no_replication: ['Inconclusive', 'warn', 'A counterexample was found but no replication run completed.'],
  withdrawn: ['Withdrawn', 'bad', 'The package failed recomputation; it supports nothing.'],
  necessary: ['Necessary', 'ok', 'Reverting it alone removes the violation.'],
  sufficient: ['Sufficient', 'ok', 'Alone, at the registered conditions, it causes the violation.'],
  necessary_and_sufficient: ['Necessary and sufficient', 'ok', ''],
  contributing: ['Contributing', 'warn', 'Neither necessary nor sufficient on its own.'],
  not_required: ['Not required', 'neutral', 'Minimisation moved it back to its registered value.'],
};

function word(code) {
  return WORDS[code] || [String(code || '').replace(/_/g, ' '), 'neutral', ''];
}

function chip(code, extra) {
  const [label, tone, hint] = word(code);
  return h('span', { class: `dl-chip ${tone}`, title: hint || null }, glyph(tone), label, extra ? h('span', { class: 'dim' }, ` ${extra}`) : null);
}

function glyph(tone) {
  const g = { ok: '✓', bad: '✕', warn: '◐', neutral: '○' }[tone] || '○';
  return h('span', { class: 'dl-glyph', 'aria-hidden': 'true' }, g);
}

const pct = (k, n) => (n ? `${Math.round((100 * k) / n)} %` : 'n/a');
const frac = (k, n) => `${k} of ${n}`;
const unitText = (u) => (u === 'model' ? '' : u);
const valueText = (v, u) => `${num(v, 4)}${unitText(u) ? ` ${unitText(u)}` : ''}`;

// ------------------------------------------------------------------------ entry points

export function initDiscover(root) {
  st.root = root;
  if (window.__TAURI__ && window.__TAURI__.event) {
    window.__TAURI__.event.listen('discovery-progress', (ev) => {
      if (!st.running) return;
      const p = ev.payload || {};
      st.running.stages[p.stage] = { done: p.done, total: p.total };
      st.running.last = p.stage;
      renderProgress();
    });
  }
}

export async function showDiscover(opts) {
  try {
    const [claims, packages] = await Promise.all([api.claims(), api.packages()]);
    st.claims = claims;
    st.packages = packages;
  } catch (e) {
    st.claims = [];
    st.packages = [];
    toast(errorText(e), 'error');
  }
  const wanted = opts && opts.claimId && st.claims.find((c) => c.claim && c.claim.id === opts.claimId);
  if (wanted && !st.running) { st.claimFile = wanted.file; st.pkgName = null; st.data = null; }
  if (!st.claimFile && st.claims.length) st.claimFile = st.claims[0].file;
  render();
}

export function rethemeDiscover() {
  if (st.data) renderPackage();
}

// ------------------------------------------------------------------------ layout

function render() {
  const root = clear(st.root);
  root.append(h('div', { class: 'dl' }, rail(), h('div', { class: 'dl-main', id: 'dl-main', tabindex: '-1' })));
  if (st.running) renderProgress();
  else if (st.pkgName && st.data) renderPackage();
  else renderClaim();
}

/** `<claim>-20261103T201234Z` as `2026-11-03 20:12 UTC`. */
function stamp(name) {
  const m = /(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})\d{2}Z$/.exec(name);
  return m ? `${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]} UTC` : name;
}

function failedCheck(p) {
  return Boolean(p.verification && !p.verification.stale && !p.verification.report.pass);
}

export function verdictOf(p) {
  return failedCheck(p) ? 'withdrawn' : p.verdict && p.verdict.claim;
}

function latestFor(claimId) {
  return st.packages.find((p) => p.claim_id === claimId);
}

function rail() {
  const claims = h('ul', { class: 'dl-list', 'aria-label': 'Claims' },
    st.claims.map((c) => {
      const cl = c.claim;
      const last = cl ? latestFor(cl.id) : null;
      const sel = !st.pkgName && st.claimFile === c.file;
      return h('li', null, h('button', {
        type: 'button', class: ['dl-item', sel && 'sel'], 'aria-current': sel ? 'true' : null,
        onclick: () => { st.claimFile = c.file; st.pkgName = null; st.data = null; render(); },
      },
      h('span', { class: 'dl-item-title' }, cl ? cl.title : c.file),
      cl ? h('span', { class: 'dl-item-sub' }, `${cl.domain} · ${cl.property.replace(/^\w+:/, '')}`) : h('span', { class: 'error-text small' }, c.error),
      last ? h('span', { class: 'dl-item-chips' }, chip(verdictOf(last))) : h('span', { class: 'dl-item-sub dim' }, 'Not investigated yet')));
    }));
  const pk = h('ul', { class: 'dl-list', 'aria-label': 'Investigations' },
    st.packages.length ? st.packages.map((p) => {
      const sel = st.pkgName === p.name;
      const vr = p.verification && !p.verification.stale ? p.verification.report : null;
      const stale = p.verification && p.verification.stale;
      return h('li', null, h('button', {
        type: 'button', class: ['dl-item', sel && 'sel'], 'aria-current': sel ? 'true' : null,
        onclick: () => openPackage(p.name),
      },
      h('span', { class: 'dl-item-title' }, p.title),
      h('span', { class: 'dl-item-sub mono' }, stamp(p.name)),
      h('span', { class: 'dl-item-chips' }, chip(verdictOf(p)),
        vr ? h('span', { class: `dl-chip ${vr.pass ? 'ok' : 'bad'}` }, glyph(vr.pass ? 'ok' : 'bad'), vr.pass ? 'Recomputed' : 'Failed check')
          : h('span', { class: `dl-chip ${stale ? 'warn' : 'neutral'}` }, glyph(stale ? 'warn' : 'neutral'), stale ? 'Changed since recomputed' : 'Not recomputed'))));
    }) : h('li', { class: 'empty small' }, 'No investigation yet. Choose a claim and challenge it.'));
  return h('aside', { class: 'dl-rail' },
    h('h2', { class: 'dl-rail-h' }, 'Claims'), claims,
    h('h2', { class: 'dl-rail-h' }, 'Investigations'), pk);
}

function main() {
  destroyCharts();
  return clear(document.getElementById('dl-main'));
}

function destroyCharts() {
  for (const c of st.charts) c.destroy();
  st.charts = [];
}

// ------------------------------------------------------------------------ claim view

function selectedClaim() {
  return st.claims.find((c) => c.file === st.claimFile);
}

function renderClaim() {
  const m = main();
  const entry = selectedClaim();
  if (!entry) {
    m.append(h('div', { class: 'dl-empty' }, h('h1', null, 'Discovery Lab'), h('p', null, 'No claim is installed. Claims live in the discovery folder next to the engine.')));
    return;
  }
  if (!entry.claim) {
    m.append(h('div', { class: 'dl-empty' }, h('h1', null, entry.file), h('p', { class: 'error-text' }, entry.error)));
    return;
  }
  const c = entry.claim;
  const b = c.budget;
  const runs = (c.planned_probes || 0) + b.challenge * (1 + c.mitigations.length) + b.minimise;
  m.append(
    h('header', { class: 'dl-head' },
      h('p', { class: 'dl-kicker' }, 'Claim under test'),
      h('h1', null, c.title),
      h('p', { class: 'dl-statement' }, c.statement),
      h('div', { class: 'dl-chips' },
        h('span', { class: 'dl-chip neutral' }, c.domain),
        h('span', { class: 'dl-chip neutral mono' }, c.property),
        h('span', { class: 'dl-chip neutral' }, c.tolerance ? `tolerance ${num(c.tolerance * 100, 3)} % of runs` : 'no violation tolerated'),
        h('span', { class: 'dl-chip warn' }, glyph('warn'), c.evidence_grade === 'exploratory' ? 'Exploratory grade' : c.evidence_grade)),
      h('div', { class: 'dl-actions' },
        h('button', { type: 'button', class: 'btn btn-primary dl-cta', onclick: () => challenge(entry) }, 'Challenge this claim'),
        h('span', { class: 'dim small' }, `At most ${runs.toLocaleString('en')} simulations, as planned by the engine from the budget, on development seeds. Each one is logged and recomputable.`)),
      h('ol', { class: 'dl-howto', 'aria-label': 'What a challenge does' },
        h('li', null, h('b', null, 'Search'), 'The engine tries conditions inside the declared envelope, looking for runs where the claim stops holding.'),
        h('li', null, h('b', null, 'Reproduce'), 'A counterexample counts only if it fails again on fresh seeds the search never saw.'),
        h('li', null, h('b', null, 'Explain'), 'Declared interventions test what causes the failure, one factor at a time.'),
        h('li', null, h('b', null, 'Mitigate and verify'), 'Candidate fixes are tested for the failure and for new regressions; every verdict is recomputed from scratch.'))),
    section('Where the claim comes from', h('p', { class: 'dl-prose' }, c.origin)),
    section('Assumptions and envelope', h('p', { class: 'dl-prose dim' }, 'The challenge varies these and only these, inside the declared box. The registered value is where the claim was originally supported.'),
      h('div', { class: 'dl-assume' }, c.assumptions.map((a) => assumptionRow(a)))),
    section('Declared before the run',
      h('p', { class: 'dl-prose dim' }, 'Hypotheses and candidate mitigations are fixed in the claim file. The engine tests them; it does not invent or tune them.'),
      h('div', { class: 'dl-two' },
        h('div', null, h('h3', null, 'Mechanism hypotheses'), h('ul', { class: 'dl-bullets' }, c.hypotheses.map((x) => h('li', null, h('b', null, x.id), ': ', x.statement, h('ul', { class: 'dl-sub' }, x.interventions.map((i) => h('li', null, `Intervention ${i.id}: ${i.description} Predicts the property ${i.predicts === 'holds' ? 'holds' : 'is violated'}.`)), x.trace_checks.map((t) => h('li', null, `Trace check ${t.id}: ${t.description}`)))))) ),
        h('div', null, h('h3', null, 'Candidate mitigations'), h('ul', { class: 'dl-bullets' }, c.mitigations.map((x) => h('li', null, h('b', null, x.title), ': ', x.rationale))),
          h('h3', null, 'Regression families'), h('p', { class: 'small' }, c.regression.map((f) => f.title).join(', ') || 'none')))),
    section('Seeds and rules',
      h('table', { class: 'dl-table' }, h('tbody', null,
        row('Discovery seeds', `${c.seeds.discovery.low} to ${c.seeds.discovery.high}`, 'Used by the challenge search only.'),
        row('Evaluation seeds', `${c.seeds.evaluation.low} to ${c.seeds.evaluation.high}`, 'Replication, attribution, envelope, mechanism; the same seeds in every stage, so comparisons are paired.'),
        row('Regression seeds', `${c.seeds.regression.low} to ${c.seeds.regression.high}`, 'Mitigation regressions and re-challenge; never used to find or explain the failure.'),
        row('Refutation rule', c.rules.refutation, ''),
        row('Intervention rule', c.rules.intervention, ''),
        row('Claim file', shortHash(c.claim_sha256, 16), 'sha256'),
        row('Model source', shortHash(c.source_sha256, 16), 'sha256 of the simulator sources this engine was built from')))),
  );
}

function assumptionRow(a) {
  const pos = (v) => `${Math.max(0, Math.min(100, (100 * (v - a.low)) / (a.high - a.low)))}%`;
  return h('div', { class: 'dl-assume-row' },
    h('div', { class: 'dl-assume-name' }, h('b', null, a.name), h('span', { class: 'dim small' }, a.description)),
    h('div', { class: 'dl-range', role: 'img', 'aria-label': `${a.name} from ${a.low} to ${a.high}, registered ${a.registered}` },
      h('span', { class: 'dl-range-bar' }),
      h('span', { class: 'dl-range-reg', style: { left: pos(a.registered) }, title: `registered ${valueText(a.registered, a.unit)}` }),
      h('span', { class: 'dl-range-lo mono small' }, valueText(a.low, a.unit)),
      h('span', { class: 'dl-range-hi mono small' }, valueText(a.high, a.unit))),
    h('div', { class: 'mono small' }, `registered ${valueText(a.registered, a.unit)}`));
}

function row(k, v, note) {
  return h('tr', null, h('th', { scope: 'row' }, k), h('td', { class: 'mono' }, v), h('td', { class: 'dim small' }, note));
}

function section(title, ...body) {
  return h('section', { class: 'dl-sec' }, h('h2', { class: 'dl-sec-h' }, title), ...body);
}

// ------------------------------------------------------------------------ running

const STAGES = [
  ['challenge', 'Challenge search over the envelope'],
  ['re-challenge', 'Re-challenge of each mitigation'],
  ['baseline', 'Registered conditions'],
  ['investigation', 'Replication, attribution, envelope and mechanism'],
  ['regression', 'Regression families'],
  ['artifacts', 'Canonical artifacts and signals'],
  ['verify', 'Recomputation'],
];

async function challenge(entry) {
  if (st.running) return;
  st.running = { kind: 'investigate', title: entry.claim.title, stages: {}, last: null, started: performance.now() };
  render();
  try {
    const name = await api.run(entry.file);
    st.running = null;
    toast('Investigation finished. Verifying it from scratch.', 'info');
    await refreshPackages();
    await openPackage(name);
    await verify();
  } catch (e) {
    st.running = null;
    toast(errorText(e), 'error');
    render();
  }
}

function renderProgress() {
  const m = document.getElementById('dl-main');
  if (!m || !st.running) return;
  destroyCharts();
  clear(m);
  const r = st.running;
  const secs = ((performance.now() - r.started) / 1000).toFixed(0);
  m.append(h('div', { class: 'dl-progress', role: 'status', 'aria-live': 'polite' },
    h('p', { class: 'dl-kicker' }, r.kind === 'verify' ? 'Recomputing the package' : 'Investigation running'),
    h('h1', null, r.title),
    h('ol', { class: 'dl-steps' }, STAGES.filter(([k]) => r.kind !== 'verify' || k !== 'artifacts').map(([key, label]) => {
      const hits = Object.entries(r.stages).filter(([k]) => k.startsWith(key));
      const done = hits.length && hits.every(([, v]) => v.total && v.done >= v.total);
      const active = r.last && r.last.startsWith(key) && !done;
      const counts = hits.reduce((a, [, v]) => [a[0] + v.done, a[1] + v.total], [0, 0]);
      return h('li', { class: ['dl-step', done && 'done', active && 'active'] },
        h('span', { class: 'dl-step-dot', 'aria-hidden': 'true' }), h('span', null, label),
        counts[1] ? h('span', { class: 'mono dim small' }, `${counts[0].toLocaleString('en')} / ${counts[1].toLocaleString('en')}`) : null);
    })),
    h('p', { class: 'dim small' }, `${secs} s. Every simulation is logged with its seed, case hash and trace hash.`),
    h('button', { type: 'button', class: 'btn', onclick: async () => { try { await api.cancel(); } catch (e) { toast(errorText(e), 'error'); } } }, 'Cancel')));
}

async function refreshPackages() {
  try { st.packages = await api.packages(); } catch (e) { toast(errorText(e), 'error'); }
}

async function openPackage(name) {
  try {
    st.data = await api.open(name);
    st.pkgName = name;
    const arts = Object.keys(st.data.package.artifacts || {});
    st.primary = arts.includes('counterexample') ? 'counterexample' : arts[0];
    st.compare = arts.includes('twin') ? 'twin' : null;
    st.envelopeSet = 'none';
    render();
  } catch (e) {
    toast(errorText(e), 'error');
  }
}

async function verify() {
  if (!st.pkgName || st.running) return;
  const name = st.pkgName;
  st.running = { kind: 'verify', title: st.data.package.title, stages: {}, last: null, started: performance.now() };
  render();
  try {
    await api.verify(name);
    st.running = null;
    await refreshPackages();
    await openPackage(name);
  } catch (e) {
    st.running = null;
    toast(errorText(e), 'error');
    render();
  }
}

// ------------------------------------------------------------------------ package view

/** `requirement:R1_vertical_speed` as `R1 vertical speed (requirement)`. */
function prettyProp(name) {
  const m = /^(\w+):(.*)$/.exec(name || '');
  return m ? `${m[2].replace(/_/g, ' ')} (${m[1]})` : name;
}

function summarySentence(p) {
  const f = p.findings;
  const cx = f.counterexample;
  const names = p.assumptions.map((a) => a.name);
  if (!cx) {
    const ub = f.challenge.upper_bound_if_none;
    return `No violation of ${p.property} in ${f.challenge.evaluations} challenge evaluations. Under uniform sampling of the envelope, the violation rate is below ${num(ub * 100, 3)} % with 95 % confidence. That does not show the claim holds.`;
  }
  const vals = cx.minimised.values.map((v, i) => `${names[i]} ${valueText(v, p.assumptions[i].unit)}`).join(', ');
  const reg = cx.registered.values.map((v, i) => `${names[i]} ${valueText(v, p.assumptions[i].unit)}`).join(', ');
  const other = Object.entries(f.baseline_violations || {}).filter(([k]) => k !== p.property);
  const also = other.length ? ` Those registered runs do violate other requirements: ${other.map(([k, v]) => `${prettyProp(k)} in ${v}`).join(', ')}.` : '';
  return `At ${vals}, ${prettyProp(p.property)} is violated in ${frac(cx.replication.violated, cx.replication.n)} fresh seeds. At the registered conditions, where the claim was originally supported (${reg}), it is violated in ${frac(f.baseline.violated, f.baseline.n)}.${also}`;
}

function worst(list) {
  const tones = list.map(([, code]) => word(code)[1]);
  if (!tones.length) return 'neutral';
  return tones.includes('bad') ? 'bad' : tones.includes('warn') ? 'warn' : tones.every((t) => t === 'ok') ? 'ok' : 'neutral';
}

function acceptance(p, vr) {
  const f = p.findings;
  const mech = f.verdict.mechanism;
  const mit = f.verdict.mitigations;
  const tile = (label, body, tone) => h('div', { class: `dl-tile ${tone}` }, h('span', { class: 'dl-tile-k' }, label), body);
  // A stored report counts only while it is bound to the package bytes it checked.
  const verified = vr && !vr.stale ? vr.report.pass : null;
  // Evidence that failed recomputation supports nothing: its verdicts are withdrawn, not shown.
  const withdrawn = verified === false;
  const stated = verified === null ? h('span', { class: 'small dim' }, 'As stated by the package; not yet recomputed.') : null;
  const gone = (what) => h('div', null, h('b', null, 'Withdrawn'), h('span', { class: 'small dim' }, `The evidence failed recomputation, so the ${what} it states is not shown as a result.`));
  return h('div', { class: 'dl-tiles', role: 'group', 'aria-label': 'Separate verdicts' },
    tile('Evidence integrity', verified === null
      ? h('div', null, h('b', null, vr && vr.stale ? 'Changed since it was recomputed' : 'Not recomputed yet'), h('button', { type: 'button', class: 'btn btn-small', onclick: verify }, 'Recompute now'))
      : h('div', null, h('b', null, verified ? 'Recomputed, every check passed' : 'A check failed'), h('span', { class: 'small dim' }, `${vr.report.probes_recomputed.toLocaleString('en')} probes rerun · ${vr.verified_at_utc}`)),
    verified === null ? (vr && vr.stale ? 'warn' : 'neutral') : verified ? 'ok' : 'bad'),
    tile('Claim', withdrawn ? gone('verdict') : h('div', null, h('b', null, word(f.verdict.claim)[0]), h('span', { class: 'small dim' }, word(f.verdict.claim)[2]), stated), withdrawn ? 'bad' : word(f.verdict.claim)[1]),
    tile('Mechanism', withdrawn ? gone('mechanism') : h('div', null, mech.length ? mech.map(([id, s2]) => h('div', { class: 'dl-tile-line' }, h('span', { class: 'mono small' }, id), chip(s2))) : h('b', null, 'No hypothesis declared')), withdrawn ? 'bad' : worst(mech)),
    tile('Mitigation', withdrawn ? gone('mitigation result') : h('div', null, mit.length ? mit.map(([id, s2]) => h('div', { class: 'dl-tile-line' }, h('span', { class: 'mono small' }, id), chip(s2))) : h('b', null, 'No mitigation declared')), withdrawn ? 'bad' : worst(mit)),
    tile('Evidence grade', h('div', null, h('b', null, f.verdict.evidence_grade === 'exploratory' ? 'Exploratory' : 'Confirmatory'), h('span', { class: 'small dim' }, 'Simulation, development seeds. Not a confirmation, not a certification.')), 'neutral'));
}

function bodyWithdrawn(d) {
  const vr = d.verification;
  return Boolean(vr && !vr.stale && !vr.report.pass);
}

function renderPackage() {
  const m = main();
  const d = st.data;
  const p = d.package;
  const f = p.findings;
  m.append(
    h('header', { class: 'dl-head' },
      h('div', { class: 'dl-headrow' },
        h('div', null,
          h('p', { class: 'dl-kicker' }, `Investigation · ${p.domain} · ${p.engine}${bodyWithdrawn(d) ? ' · withdrawn' : ''}`),
          h('h1', null, p.title)),
        h('div', { class: 'dl-actions' },
          h('button', { type: 'button', class: 'btn', onclick: verify }, 'Recompute from scratch'),
          h('button', { type: 'button', class: 'btn', onclick: () => api.reveal(st.pkgName).catch((e) => toast(errorText(e), 'error')) }, 'Show package folder'))),
      h('p', { class: 'dl-statement' }, p.statement),
      bodyWithdrawn(d)
        ? h('p', { class: 'dl-withdrawn', role: 'alert' }, 'This package states a result, but its recomputation failed. Nothing below is evidence; it is shown only so the failed checks can be inspected in section 7.')
        : h('p', { class: 'dl-summary' }, summarySentence(p))),
    acceptance(p, d.verification),
    h('nav', { class: 'dl-story', 'aria-label': 'Investigation steps' },
      ['Challenge', 'Counterexample', 'Envelope', 'Cause', 'Mitigation', 'Limits', 'Evidence'].map((t, i) =>
        h('a', { href: `#dl-s${i}`, class: 'dl-story-step', onclick: (e) => { e.preventDefault(); document.getElementById(`dl-s${i}`).scrollIntoView({ behavior: reducedMotion() ? 'auto' : 'smooth', block: 'start' }); } }, h('span', { class: 'dl-story-n' }, String(i + 1)), t))),
    secChallenge(p),
    secCounterexample(p),
    secEnvelope(p),
    secCause(p),
    secMitigation(p),
    secLimits(p),
    secEvidence(p, d),
  );
  drawTimeline();
}

function reducedMotion() {
  return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

function sec(i, title, lead, ...body) {
  return h('section', { class: 'dl-sec', id: `dl-s${i}`, 'aria-labelledby': `dl-s${i}-h` },
    h('h2', { class: 'dl-sec-h', id: `dl-s${i}-h` }, h('span', { class: 'dl-sec-n' }, String(i + 1)), title),
    lead ? h('p', { class: 'dl-prose' }, lead) : null, ...body);
}

// 1. Challenge -------------------------------------------------------------------------

function secChallenge(p) {
  const c = p.findings.challenge;
  const cx = p.findings.counterexample;
  return sec(0, 'Challenge',
    `A ${c.strategy} search drew ${c.evaluations} points from the envelope on discovery seeds. ${c.property_violations} of them violated ${p.property}${c.first_property_violation ? `, the first at evaluation ${c.first_property_violation}` : ''}.`,
    h('div', { class: 'dl-two' },
      scatter(p, c, cx),
      h('div', null,
        h('table', { class: 'dl-table' }, h('tbody', null,
          row('Evaluations', c.evaluations.toLocaleString('en'), `${c.errors} errors`),
          row('Property violations', `${c.property_violations} (${pct(c.property_violations, c.evaluations)})`, 'A rate over the search distribution, not a prevalence in the field.'),
          row('Classes with the property', String(c.property_classes.length), ''),
          row('Other failure classes', String(c.other_classes.length), 'Listed, not investigated.'))),
        c.other_classes.length ? h('ul', { class: 'dl-classes' }, c.other_classes.map((x) => h('li', { class: 'mono small' }, x))) : null)));
}

function scatter(p, c, cx) {
  const W = 360, H = 300, L = 46, B = 34, T = 10, R = 10;
  const a = p.assumptions;
  const two = a.length > 1;
  const x = (u) => L + u * (W - L - R);
  const y = (u) => H - B - u * (H - B - T);
  const unit = (q) => q / 4294967296;
  const pts = c.samples.map(([u, v]) => s('circle', { cx: x(u[0]), cy: two ? y(u[1]) : y(v ? 0.8 : 0.2), r: v ? 3.2 : 2.4, class: v ? 'dl-pt bad' : 'dl-pt ok' }));
  const mark = (q, cls, label, dx, dy, anchor) => {
    if (!q) return null;
    const px = x(unit(q[0])), py = two ? y(unit(q[1])) : y(0.5);
    return s('g', { class: cls }, s('circle', { cx: px, cy: py, r: 7 }), s('text', { x: px + dx, y: py + dy, 'text-anchor': anchor || 'start' }, label));
  };
  const ticks = (i, axis) => [0, 0.5, 1].map((u) => {
    const v = a[i].low + u * (a[i].high - a[i].low);
    return axis === 'x'
      ? s('text', { x: x(u), y: H - B + 16, 'text-anchor': 'middle', class: 'dl-ax' }, num(v, 3))
      : s('text', { x: L - 6, y: y(u) + 4, 'text-anchor': 'end', class: 'dl-ax' }, num(v, 3));
  });
  return h('figure', { class: 'dl-fig' },
    s('svg', { viewBox: `0 0 ${W} ${H}`, class: 'dl-svg', role: 'img', 'aria-label': `Search samples: ${c.property_violations} violations of ${c.evaluations}` },
      s('rect', { x: L, y: T, width: W - L - R, height: H - B - T, class: 'dl-plotbg' }),
      pts,
      cx ? mark(cx.registered.q, 'dl-mk reg', 'registered', 11, -6) : null,
      cx ? mark(cx.found.q, 'dl-mk found', 'found', 11, -8) : null,
      cx ? mark(cx.minimised.q, 'dl-mk min', 'minimised', 11, 16) : null,
      ticks(0, 'x'), two ? ticks(1, 'y') : null,
      s('text', { x: (L + W - R) / 2, y: H - 4, 'text-anchor': 'middle', class: 'dl-axl' }, `${a[0].name}${unitText(a[0].unit) ? ` (${unitText(a[0].unit)})` : ''}`),
      two ? s('text', { x: 12, y: (T + H - B) / 2, transform: `rotate(-90 12 ${(T + H - B) / 2})`, 'text-anchor': 'middle', class: 'dl-axl' }, `${a[1].name}${unitText(a[1].unit) ? ` (${unitText(a[1].unit)})` : ''}`) : null),
    h('figcaption', { class: 'small dim' }, h('span', { class: 'dl-key bad' }), ' violates the property  ', h('span', { class: 'dl-key ok' }), ' holds. Rings mark the registered point, the counterexample the engine chose (the class whose minimised point is closest to the registered conditions) and that minimised point.'));
}

// 2. Counterexample and timeline --------------------------------------------------------

function secCounterexample(p) {
  const cx = p.findings.counterexample;
  if (!cx) return sec(1, 'Counterexample', 'None found within the budget.');
  const names = p.assumptions;
  const arts = p.artifacts;
  const pick = (key, which) => h('div', { class: 'dl-seg', role: 'radiogroup', 'aria-label': which === 'primary' ? 'Run shown' : 'Run compared' },
    (which === 'compare' ? [null] : []).concat(Object.keys(arts)).map((k) => h('button', {
      type: 'button', role: 'radio', 'aria-checked': String(st[which] === k), class: ['dl-seg-b', st[which] === k && 'on'],
      onclick: () => { st[which] = k; renderPackage(); },
    }, k === null ? 'none' : k)));
  return sec(1, 'Counterexample',
    'Minimisation moved each assumption back towards its registered value while the failure class and the seed stayed the same. The result was rerun on fresh evaluation seeds and written again by the canonical simulator writer.',
    h('div', { class: 'dl-facts' },
      fact('Minimised point', cx.minimised.values.map((v, i) => `${names[i].name} ${valueText(v, names[i].unit)}`).join(' · ')),
      fact('Found at', `evaluation ${cx.found_at}, seed ${cx.seed}`),
      fact('Failure class', cx.class.replace(/\+/g, ' + ')),
      fact('Replication', `${frac(cx.replication.violated, cx.replication.n)} fresh seeds`, `95 % interval ${num(cx.replication.ci95[0] * 100, 3)} to ${num(cx.replication.ci95[1] * 100, 3)} %`),
      fact('Byte reproduction', cx.byte_reproduced ? 'search log, rerun and canonical writer agree' : 'not reproduced', shortHash(cx.trace_sha256, 16), cx.byte_reproduced ? 'ok' : 'bad')),
    h('div', { class: 'dl-tl-head' },
      h('div', null, h('span', { class: 'dim small' }, 'Show '), pick('primary', 'primary')),
      h('div', null, h('span', { class: 'dim small' }, 'against '), pick('compare', 'compare'))),
    h('p', { class: 'small dim', id: 'dl-tl-desc' }, describeArtifacts(p)),
    h('p', { class: 'dl-tl-key small' },
      h('span', { class: 'dl-swatch truth' }), 'true state  ',
      h('span', { class: 'dl-swatch belief' }), 'what the controller believed  ',
      h('span', { class: 'dl-swatch obs' }), 'what a sensor reported  ',
      h('span', { class: 'dl-swatch err' }), 'belief error  ',
      h('span', { class: 'dl-swatch flag' }), 'monitor flag (0 or 1)  ',
      'Dashed: the compared run. Vertical lines: fault start (pink), violation (red).'),
    h('div', { class: 'dl-tl', id: 'dl-tl' }),
    h('div', { class: 'dl-events', id: 'dl-events' }));
}

function describeArtifacts(p) {
  const a = p.artifacts[st.primary];
  const b = st.compare ? p.artifacts[st.compare] : null;
  return `Solid: ${st.primary}, ${a ? a.description : ''}${b ? ` Dashed: ${st.compare}, ${b.description}` : ''} True state, believed state and sensor reports are drawn apart; flags are 0 or 1.`;
}

function fact(k, v, sub, tone) {
  return h('div', { class: ['dl-fact', tone] }, h('span', { class: 'dl-fact-k' }, k), h('b', null, v), sub ? h('span', { class: 'small dim mono' }, sub) : null);
}

const ROLE_VAR = { truth: '--truth', belief: '--est', observation: '--obs', error: '--fail', flag: '--fault', command: '--accent' };

function drawTimeline() {
  const host = document.getElementById('dl-tl');
  if (!host || !st.data) return;
  const sig = st.data.signals || {};
  const a = sig[st.primary];
  if (!a) return;
  const b = st.compare ? sig[st.compare] : null;
  const groups = [];
  for (const sr of a.series) if (!groups.includes(sr.group)) groups.push(sr.group);
  const width = Math.max(320, host.clientWidth || 900);
  const sync = uPlot.sync(`dl-${st.pkgName}`);
  for (const g of groups) {
    const sa = a.series.filter((x) => x.group === g);
    const sb = b ? b.series.filter((x) => x.group === g) : [];
    const t = sa[0].t;
    // Align the comparison run on the primary time base by nearest earlier sample.
    const align = (src) => t.map((tt) => {
      let lo = 0, hi = src.t.length - 1;
      if (hi < 0 || tt < src.t[0]) return null;
      while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (src.t[mid] <= tt) lo = mid; else hi = mid - 1; }
      return tt - src.t[lo] > 0.25 ? null : src.v[lo];
    });
    const data = [t, ...sa.map((x) => x.v), ...sb.map((x) => align(x))];
    const series = [{}, ...sa.map((x) => line(x, false)), ...sb.map((x) => line(x, true))];
    const flag = sa.every((x) => x.role === 'flag');
    const el = h('div', { class: 'dl-chart' }, h('div', { class: 'dl-chart-h' }, h('b', null, g), h('span', { class: 'dim small' }, sa.map((x) => x.unit).filter(Boolean)[0] || '')));
    host.append(el);
    const ax = axisStyle();
    const u = new uPlot({
      width, height: flag ? 90 : 150,
      cursor: { sync: { key: sync.key }, points: { show: false } },
      legend: { show: true, live: true },
      scales: { x: { time: false }, y: flag ? { range: [-0.1, 1.1] } : {} },
      axes: [{ ...ax, label: 't (s)', labelSize: 14, size: 28 }, { ...ax, size: 54 }],
      series,
      hooks: { draw: [(uu) => drawEvents(uu, a.events)] },
    }, data, el);
    st.charts.push(u);
  }
  const ev = document.getElementById('dl-events');
  if (ev) {
    ev.append(h('h3', null, `Events of ${st.primary}`), h('ul', { class: 'dl-evlist' }, a.events.map((e) => h('li', { class: e.kind === 'violation' ? 'bad' : '' }, h('span', { class: 'mono' }, `${num(e.t, 4)} s`), ' ', e.label))));
  }
}

function line(x, dashed) {
  const color = cssVar(ROLE_VAR[x.role] || '--fg-2');
  return {
    label: `${dashed ? '[' + st.compare + '] ' : ''}${x.label}`,
    stroke: color,
    width: x.role === 'truth' ? 1.8 : 1.4,
    dash: dashed ? [6, 4] : x.role === 'belief' ? [] : x.role === 'observation' ? [1, 3] : [],
    alpha: dashed ? 0.6 : 1,
    paths: x.role === 'flag' ? uPlot.paths.stepped({ align: 1 }) : undefined,
    points: { show: false },
    spanGaps: false,
  };
}

function drawEvents(u, events) {
  const { ctx } = u;
  const { top, height } = u.bbox;
  ctx.save();
  for (const e of events) {
    if (e.kind !== 'violation' && e.kind !== 'fault_start' && e.kind !== 'cutoff' && e.kind !== 'ignition') continue;
    const xx = u.valToPos(e.t, 'x', true);
    ctx.strokeStyle = cssVar(e.kind === 'violation' ? '--unsafe' : e.kind === 'fault_start' ? '--fault' : '--rule-strong');
    ctx.setLineDash(e.kind === 'violation' ? [] : [3, 3]);
    ctx.beginPath();
    ctx.moveTo(xx, top);
    ctx.lineTo(xx, top + height);
    ctx.stroke();
  }
  ctx.restore();
}

// 3. Envelope -----------------------------------------------------------------------------

function secEnvelope(p) {
  const e = p.findings.envelope;
  if (!e) return sec(2, 'Envelope', 'No envelope map: there was no counterexample to map around.');
  const sets = ['none', ...p.findings.mitigations.map((m) => m.id)];
  const seg = h('div', { class: 'dl-seg', role: 'radiogroup', 'aria-label': 'System shown' }, sets.map((k) => h('button', {
    type: 'button', role: 'radio', 'aria-checked': String(st.envelopeSet === k), class: ['dl-seg-b', st.envelopeSet === k && 'on'],
    onclick: () => { st.envelopeSet = k; renderPackage(); document.getElementById('dl-s2').scrollIntoView({ block: 'start' }); },
  }, k === 'none' ? 'as registered' : `with ${k}`)));
  return sec(2, 'Envelope',
    `Each cell is ${e.seeds} evaluation seeds at one point of the grid${e.fixed.length ? `, with ${e.fixed.map(([n, v]) => `${n} ${num(v, 4)}`).join(', ')}` : ''}. ${e.clean_cells[0]} of ${e.clean_cells[1]} cells show no violation. The claim can only hold on that region, at this resolution.`,
    seg,
    heatmap(p, e),
    h('p', { class: 'small dim' }, st.envelopeSet === 'none'
      ? 'Shade and number: runs per cell that violate the property. The ring is the registered point; the star the minimised counterexample, drawn at its true position between grid values.'
      : 'With a mitigation, colour shows change against the unmitigated system on the same seeds: fixed, broken, still violated or unchanged.'));
}

function heatmap(p, e) {
  const n = e.cells.length;
  const m = e.cells[0].length;
  const W = 520, H = m > 1 ? 380 : 120, L = 56, B = 40, T = 8, R = 8;
  const cw = (W - L - R) / n, ch = (H - B - T) / m;
  const mit = st.envelopeSet !== 'none' ? p.findings.mitigations.find((x) => x.id === st.envelopeSet) : null;
  const delta = mit ? cellDelta(p, mit.id) : null;
  const rects = [];
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < m; j++) {
      const k = e.cells[i][j];
      let cls = `dl-cell v${Math.round((4 * k) / e.seeds)}`;
      let label = `${e.axes[0].name} ${num(e.axes[0].values[i], 4)}${m > 1 ? `, ${e.axes[1].name} ${num(e.axes[1].values[j], 4)}` : ''}: ${k} of ${e.seeds} violate`;
      if (delta) {
        const dd = delta[i * m + j];
        cls = `dl-cell d-${dd.kind}`;
        label += `; with ${mit.id}: ${dd.fixed} fixed, ${dd.broken} broken, ${dd.both} still violated`;
      }
      rects.push(s('rect', { x: L + i * cw, y: H - B - (j + 1) * ch, width: cw - 1, height: ch - 1, class: cls }, s('title', null, label)));
      const shown = delta ? delta[i * m + j].both + delta[i * m + j].broken : k;
      if (shown > 0 && cw >= 18 && ch >= 14) {
        rects.push(s('text', { x: L + (i + 0.5) * cw, y: H - B - (j + 0.5) * ch + 4, 'text-anchor': 'middle', class: 'dl-cell-n', 'aria-hidden': 'true' }, String(shown)));
      }
    }
  }
  const cx = p.findings.counterexample;
  const unit = (q) => q / 4294967296;
  // Markers at their true position on the axes: cell centres are the grid values.
  const px = (q) => L + (unit(q[0]) * (n - 1) + 0.5) * cw;
  const py = (q) => (m > 1 ? H - B - (unit(q[1]) * (m - 1) + 0.5) * ch : (H - B + T) / 2);
  const ticks = [];
  const every = Math.max(1, Math.ceil(n / 6));
  for (let i = 0; i < n; i += every) ticks.push(s('text', { x: L + (i + 0.5) * cw, y: H - B + 14, 'text-anchor': 'middle', class: 'dl-ax' }, num(e.axes[0].values[i], 3)));
  if (m > 1) for (let j = 0; j < m; j += Math.max(1, Math.ceil(m / 6))) ticks.push(s('text', { x: L - 6, y: H - B - (j + 0.5) * ch + 4, 'text-anchor': 'end', class: 'dl-ax' }, num(e.axes[1].values[j], 3)));
  return h('figure', { class: 'dl-fig' }, s('svg', { viewBox: `0 0 ${W} ${H}`, class: 'dl-svg wide', role: 'img', 'aria-label': `Envelope map of ${e.axes.map((a) => a.name).join(' and ')}` },
    rects, ticks,
    cx ? s('circle', { cx: px(cx.registered.q), cy: py(cx.registered.q), r: 7, class: 'dl-mk-reg' }) : null,
    cx ? s('path', { d: star(px(cx.minimised.q), py(cx.minimised.q), 7), class: 'dl-mk-min' }) : null,
    s('text', { x: (L + W - R) / 2, y: H - 6, 'text-anchor': 'middle', class: 'dl-axl' }, `${e.axes[0].name}${unitText(e.axes[0].unit) ? ` (${unitText(e.axes[0].unit)})` : ''}`),
    m > 1 ? s('text', { x: 14, y: (T + H - B) / 2, transform: `rotate(-90 14 ${(T + H - B) / 2})`, 'text-anchor': 'middle', class: 'dl-axl' }, `${e.axes[1].name}${unitText(e.axes[1].unit) ? ` (${unitText(e.axes[1].unit)})` : ''}`) : null),
  h('figcaption', { class: 'dl-legend small' }, mit
    ? [['d-fixed', 'fixed'], ['d-broken', 'broken'], ['d-both', 'still violated'], ['d-none', 'held, unchanged']].map(([c2, t]) => h('span', null, h('span', { class: `dl-key ${c2}` }), t))
    : [0, 1, 2, 3, 4].map((v) => h('span', null, h('span', { class: `dl-key v${v}` }), v === 0 ? 'none' : v === 4 ? `all ${e.seeds}` : `about ${Math.round((v * e.seeds) / 4)} of ${e.seeds}`))));
}

function star(x, y, r) {
  let d = '';
  for (let i = 0; i < 10; i++) {
    const a = (Math.PI / 5) * i - Math.PI / 2;
    const rr = i % 2 ? r * 0.45 : r;
    d += `${i ? 'L' : 'M'}${(x + rr * Math.cos(a)).toFixed(1)},${(y + rr * Math.sin(a)).toFixed(1)}`;
  }
  return `${d}Z`;
}

/** Per-cell change of a mitigation, as the engine counted it: (fixed, broken, still violated). */
function cellDelta(p, id) {
  const mit = p.findings.mitigations.find((x) => x.id === id);
  const e = p.findings.envelope;
  const out = [];
  for (let i = 0; i < e.cells.length; i++) {
    for (let j = 0; j < e.cells[0].length; j++) {
      const [fixed, broken, both] = mit && mit.envelope_cells ? mit.envelope_cells[i][j] : [0, 0, 0];
      const kind = broken > 0 ? 'broken' : both > 0 ? 'both' : fixed > 0 ? 'fixed' : 'none';
      out.push({ kind, fixed, broken, both });
    }
  }
  return out;
}

// 4. Cause --------------------------------------------------------------------------------

function secCause(p) {
  const f = p.findings;
  return sec(3, 'Cause',
    'Two kinds of evidence. Attribution reverts or isolates each assumption on the same seeds. Mechanism hypotheses were declared in the claim before the run; each intervention changes one part of the system and predicts the outcome, first at the counterexample and then over the whole envelope.',
    f.attribution.length ? h('table', { class: 'dl-table dl-attr' },
      h('thead', null, h('tr', null, h('th', null, 'Assumption'), h('th', null, 'Registered'), h('th', null, 'Counterexample'), h('th', null, 'Necessity'), h('th', null, 'Sufficiency'), h('th', null, 'Role'))),
      h('tbody', null, f.attribution.map((a) => h('tr', null,
        h('th', { scope: 'row' }, a.name),
        h('td', { class: 'mono' }, valueText(a.registered, a.unit)),
        h('td', { class: 'mono' }, valueText(a.counterexample, a.unit)),
        h('td', null, bar(a.necessity), h('span', { class: 'small dim' }, ' reverting it alone removes the violation')),
        h('td', null, bar(a.sufficiency), h('span', { class: 'small dim' }, ' alone, at the registered conditions, it violates')),
        h('td', null, chip(a.role)))))) : null,
    h('div', { class: 'dl-hyps' }, f.mechanism.map((m) => h('article', { class: 'dl-hyp' },
      h('header', null, h('h3', null, m.id), chip(m.status)),
      h('p', { class: 'dl-prose' }, m.statement),
      h('table', { class: 'dl-table' },
        h('thead', null, h('tr', null, h('th', null, 'Test'), h('th', null, 'Without intervention'), h('th', null, 'With intervention'), h('th', { title: 'Exact McNemar test on the seeds where the outcome changed; the rule needs p below 0.01 in the predicted direction.' }, 'Paired change'), h('th', null, 'Across the envelope'), h('th', null, 'Result'))),
        h('tbody', null,
          m.interventions.map((i) => h('tr', null,
            h('th', { scope: 'row' }, h('b', null, i.id), h('div', { class: 'small dim' }, i.description, ` Predicts: property ${i.predicts === 'holds' ? 'holds' : 'violated'}.`)),
            h('td', { class: 'mono' }, `${i.control.violated}/${i.control.n} violate`),
            h('td', { class: 'mono' }, `${i.treated.violated}/${i.treated.n} violate`),
            h('td', { class: 'mono small' }, `${i.discordant[0]} fixed, ${i.discordant[1]} broken · McNemar p ${i.mcnemar_p < 1e-4 ? i.mcnemar_p.toExponential(1) : num(i.mcnemar_p, 3)}`),
            h('td', null, chip(i.region_status, i.region_status === 'untested' ? '' : i.predicts === 'holds' ? `${i.region.fixed} of ${i.region.fixed + i.region.both} failing pairs fixed` : `${i.region.broken} of ${i.region.broken + i.region.neither} holding pairs now violate`)),
            h('td', null, chip(i.status)))),
          m.trace_checks.map((t) => h('tr', null,
            h('th', { scope: 'row' }, h('b', null, t.id), h('div', { class: 'small dim' }, t.description)),
            h('td', { colspan: '3', class: 'mono small' }, `held in ${frac(t.held[0], t.held[1])} runs at the ${t.at === 'registered' ? 'registered conditions' : 'counterexample'}; ${Math.max(...t.max_abs) === 0 ? 'flag never raised' : `largest |signal| ${num(Math.min(...t.max_abs), 3)} to ${num(Math.max(...t.max_abs), 3)}`}`),
            h('td', { class: 'dim small' }, 'trace'),
            h('td', null, chip(t.status))))))))));
}

function bar([k, n]) {
  const w = n ? (100 * k) / n : 0;
  return h('span', { class: 'dl-bar', title: `${k} of ${n}` }, h('span', { class: 'dl-bar-fill', style: { width: `${w}%` } }), h('span', { class: 'dl-bar-t mono small' }, n ? `${k}/${n}` : 'n/a'));
}

// 5. Mitigation ---------------------------------------------------------------------------

function secMitigation(p) {
  const ms = p.findings.mitigations;
  if (!ms.length) return sec(4, 'Mitigation', 'No mitigation was declared for this claim.');
  return sec(4, 'Mitigation',
    'Each candidate is judged against the unmitigated system on the same seeds: on the counterexample, over the envelope, at the registered conditions and in regression families with fresh seeds. A fresh search then tries to break the claim again with the mitigation in place. A fix that breaks something else is reported as such.',
    h('div', { class: 'dl-mits' }, ms.map((m) => h('article', { class: 'dl-mit' },
      h('header', null, h('h3', null, m.title), chip(m.status)),
      h('p', { class: 'dl-prose dim' }, m.rationale),
      h('div', { class: 'dl-facts' },
        fact('Counterexample', `${frac(m.counterexample.fixed, m.counterexample.fixed + m.counterexample.both)} seeds fixed`, `${m.counterexample.broken} broken`, m.counterexample.both ? 'warn' : 'ok'),
        fact('Envelope', `${m.envelope.fixed} fixed · ${m.envelope.broken} broken`, `${m.envelope.both} pairs still violate, of ${m.envelope.n}`, m.envelope.broken ? 'bad' : m.envelope.both ? 'warn' : 'ok'),
        fact('Re-challenge', `${m.rechallenge.property_violations} of ${m.rechallenge.evaluations} violate`, m.rechallenge.upper_bound_if_none !== null && m.rechallenge.upper_bound_if_none !== undefined ? `rate below ${num(m.rechallenge.upper_bound_if_none * 100, 3)} % (95 %)` : `first at evaluation ${m.rechallenge.first_property_violation}`, m.rechallenge.property_violations ? 'warn' : 'ok'),
        fact('Regressions', String(m.regressions), `weakest group bound ${num(m.regression_upper_bound * 100, 3)} % (95 %, not pooled)`, m.regressions ? 'bad' : 'ok'),
        fact('Trade-offs', String(m.tradeoffs || 0), 'paired runs that gain another requirement violation, such as R5 off the pad', m.tradeoffs ? 'warn' : 'ok')),
      h('table', { class: 'dl-table' },
        h('thead', null, h('tr', null, h('th', null, 'Paired test'), h('th', null, 'Pairs'), h('th', null, 'Fixed'), h('th', null, 'Broken'), h('th', null, 'Violate both ways'), h('th', null, 'Regressing'), h('th', null, 'Trade-off'), h('th', null, 'New violations'))),
        h('tbody', null,
          pairRow('Counterexample (claim property)', m.counterexample),
          pairRow('Envelope (claim property)', m.envelope),
          pairRow('Registered conditions', m.registered),
          m.families.map((fm) => pairRow(fm.title, fm.paired, fm)))),
      h('p', { class: 'small dim' }, 'The first two rows count the claim property; the others count any requirement or safety invariant, so a run that misses the pad with and without the mitigation violates both ways. Regressing: the mitigation adds a safety violation or the claim property on the same point and seed. Trade-off: it adds only another requirement violation.')))));
}

function pairRow(label, pr, fam) {
  const nv = Object.entries(pr.new_violations || {});
  const head = fam
    ? h('th', { scope: 'row' }, label, h('div', { class: 'small dim' }, `regression bound ${num(fam.regression_upper_bound * 100, 3)} %`, fam.saturated ? ' · saturated: already failing without the mitigation' : '', fam.property_violations_with && fam.property_violations_with[0] ? ` · property still violated in ${fam.property_violations_with[0]} of ${fam.property_violations_with[1]}` : ''))
    : h('th', { scope: 'row' }, label);
  return h('tr', null, head, h('td', { class: 'mono' }, String(pr.n)), h('td', { class: 'mono' }, String(pr.fixed)), h('td', { class: ['mono', pr.broken && 'error-text'] }, String(pr.broken)), h('td', { class: 'mono' }, String(pr.both)),
    h('td', { class: ['mono', pr.regressing && 'error-text'] }, String(pr.regressing || 0)), h('td', { class: ['mono', pr.tradeoff && 'warn-text'] }, String(pr.tradeoff || 0)),
    h('td', { class: 'small' }, nv.length ? nv.map(([k, v]) => h('div', { class: 'mono' }, `${k} × ${v}`)) : h('span', { class: 'dim' }, 'none')));
}

// 6. Limits -------------------------------------------------------------------------------

function secLimits(p) {
  return sec(5, 'Limits and open risks', 'Written by the engine from the findings, not by hand. What the evidence does not show is as much a result as what it shows.',
    h('ul', { class: 'dl-risks' }, p.findings.verdict.open_risks.map((r) => h('li', null, glyph('warn'), h('span', null, r)))));
}

// 7. Evidence -----------------------------------------------------------------------------

function secEvidence(p, d) {
  const vr = d.verification;
  return sec(6, 'Evidence', 'Every number above is in investigation.json. Anyone can recompute it with the engine; Studio runs the same command.',
    h('table', { class: 'dl-table' }, h('tbody', null,
      row('Package', d.name, ''),
      row('Claim file', shortHash(p.claim_sha256, 20), 'sha256'),
      row('Base case', shortHash(p.base_case_sha256, 20), 'sha256'),
      row('Model source', shortHash(p.source_sha256, 20), 'sha256 of the simulator sources'),
      row('Probes', `${p.probes.toLocaleString('en')} · ${shortHash(p.probes_sha256, 20)}`, 'every simulation of the investigation, hashed line by line'),
      row('Challenge log', shortHash(p.findings.challenge.search_log_sha256, 20), 'sha256 of the challenge search log'),
      row('Wall time', d.timing ? `${num(d.timing.wall_s, 3)} s on ${d.timing.threads} threads` : 'n/a', 'measured outside the simulation; not evidence'),
      row('Command', `vv-exec investigate-verify "${d.name}"`, 'recomputes everything; nothing stored is trusted'))),
    vr ? h('div', null, h('h3', null, `Recomputation at ${vr.verified_at_utc}`), h('ul', { class: 'dl-checks' }, vr.report.checks.map((c) => h('li', { class: c.pass ? 'ok' : 'bad' }, glyph(c.pass ? 'ok' : 'bad'), h('b', { class: 'mono' }, c.id), h('span', { class: 'small dim' }, c.detail)))))
      : h('p', { class: 'dim' }, 'Not recomputed yet.'));
}
