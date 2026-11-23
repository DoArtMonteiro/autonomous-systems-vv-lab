// Unit tests of the Studio's reading of a run record's requirements and safety verdicts
// (desktop/studio/ui/js/requirements.js has no imports, so it runs under plain Node).
// Run through tests/test_ui_requirements.py, or: node tests/ui_requirements.test.mjs
import assert from 'node:assert/strict';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';

// fileURLToPath keeps a path with spaces or '&' (for example "v&v lab") intact.
const here = path.dirname(fileURLToPath(import.meta.url));
const mod = await import(pathToFileURL(path.join(here, '..', 'desktop', 'studio', 'ui', 'js', 'requirements.js')).href);
const { SAFETY_SCOPE, expectationGloss, missionTone, completionFacts, noFailureSentence, safetyWording, reqView, failureSentence, plainName, headlineChange, indexNumbers, shortText, SAFETY_NOTE, requirementWording, statusLine, endChip } = mod;
const model = await import(pathToFileURL(path.join(here, '..', 'desktop', 'studio', 'ui', 'js', 'model.js')).href);
const { conditionsName, conditionsShared, displayRunLabel, verdictOfSafety, verdictOfOutcome, conditionsBrief, verdictOfRequirement, statusClassOf, plumeLengthAt } = model;

const inv = (id, status) => ({ id, label: `Rule ${id}`, category: 'invariant', status, expected: '<= 1 m', observed: '0.5 m' });
const req = (id, status, label = `Req ${id}`) => ({ id, label, category: 'requirement', status, expected: '<= 3 m/s', observed: '1.654537 m/s' });
const rec = (status, cls, rows) => ({ safety: { status, class: cls }, requirements: rows, metrics: [] });

let n = 0;
const test = (name, fn) => { fn(); n += 1; console.log(`ok ${n} ${name}`); };

test('unsafe with failing rows counts the evaluated rows', () => {
  const w = safetyWording(rec('unsafe', 'A', [inv('S1', 'fail'), inv('S2', 'pass'), inv('S3', 'pass'), req('R1', 'pass')]));
  assert.equal(w.text, '1 of 3 safety rules broken');
  assert.equal(w.verdict, 'unsafe');
});

test('unsafe without any invariant row writes no number', () => {
  const w = safetyWording(rec('unsafe', 'B', [req('R1', 'fail')]));
  assert.equal(w.text, 'A safety rule was broken');
  assert.equal(w.verdict, 'unsafe');
});

test('a failing row is never neutral, even when the class says not evaluated', () => {
  const w = safetyWording(rec('safe', 'not_evaluated', [inv('S1', 'fail'), inv('S2', 'not_evaluated')]));
  assert.equal(w.verdict, 'unsafe');
  assert.equal(w.text, '1 of 1 safety rules broken');
});

test('safe with all rows evaluated says how many were checked', () => {
  const w = safetyWording(rec('safe', null, [inv('S1', 'pass'), inv('S2', 'pass'), inv('S3', 'pass')]));
  assert.equal(w.text, 'No safety rule broken (3 checked)');
  assert.equal(w.verdict, 'held');
});

test('safe with some rows not evaluated counts only the evaluated ones and says so', () => {
  const w = safetyWording(rec('safe', null, [inv('S1', 'pass'), inv('S2', 'not_evaluated'), inv('S3', 'pass')]));
  assert.equal(w.text, 'No safety rule broken (2 of 3 checked; 1 not evaluated)');
  assert.equal(w.verdict, 'held');
  assert.equal(w.checked, 2);
});

test('rows that were all not evaluated are neutral, not a pass', () => {
  const w = safetyWording(rec('safe', null, [inv('S1', 'not_evaluated'), inv('S2', 'not_evaluated')]));
  assert.equal(w.text, 'Safety not evaluated');
  assert.equal(w.verdict, 'neutral');
});

test('a record whose safety class is not_evaluated is neutral', () => {
  const w = safetyWording(rec('safe', 'not_evaluated', [inv('S1', 'pass')]));
  assert.equal(w.text, 'Safety not evaluated');
  assert.equal(w.verdict, 'neutral');
  assert.equal(w.unjudged, true);
});

test('safe with no rows at all writes no count', () => {
  const w = safetyWording(rec('safe', null, []));
  assert.equal(w.text, 'No safety rule broken');
  assert.equal(w.verdict, 'held');
});

test('the safety note is generic and says requirements are judged separately', () => {
  assert.match(SAFETY_NOTE, /Mission requirements are judged separately/);
  assert.doesNotMatch(SAFETY_NOTE, /landing|contact speed/);
});

test('failureSentence names the failed requirements in plain words', () => {
  const r = rec('safe', null, [req('R1_vertical_speed', 'fail', 'Vertical speed at contact'), req('R2_horizontal_speed', 'fail', 'Horizontal speed at contact'), req('R3_tilt', 'pass', 'Tilt at contact'), inv('S1', 'pass')]);
  assert.equal(failureSentence(r), '2 mission requirements failed: Vertical speed at contact, Horizontal speed at contact.');
  assert.equal(failureSentence(rec('safe', null, [req('R1', 'pass'), req('R2', 'pass')])), 'All 2 mission requirements met.');
  assert.equal(plainName({ id: 'upper.R4_periapsis' }), 'periapsis');
});

test('a tilt recorded as a cosine is shown as an angle, derived', () => {
  const v = reqView({ id: 'R3_tilt', label: 'Tilt at contact', category: 'requirement', status: 'pass', expected: '>= 0.9961946981 cos', observed: '0.999937 cos' });
  assert.equal(v.unit, '°');
  assert.equal(v.limitText, '<= 5 °');
  assert.ok(Math.abs(v.obs - 0.6444) < 0.01, String(v.obs));
});

test('the published observed value is used, not the first number of the sentence', () => {
  const r = { id: 'upper.R5_apoapsis', label: 'Apoapsis on target', category: 'requirement', status: 'pass', expected: 'apoapsis within 15 km of 300 km', observed: 'apoapsis 301.90 km, error +1.90 km' };
  const record = { requirements: [r], metrics: [
    { id: 'requirement_observed.upper.R5_apoapsis', value: 1.9, unit: 'km' },
    { id: 'requirement_limit.upper.R5_apoapsis', value: 15, unit: 'km' },
    { id: 'requirement_margin.upper.R5_apoapsis', value: 13.1, unit: 'km' }] };
  indexNumbers(record);
  const v = reqView(r);
  assert.equal(v.obsText, '1.9 km');
  assert.equal(v.limitText, '<= 15 km');
  assert.equal(v.marginText, '+13.1 km');
});

test('numbers in a recorded text are cut to four significant figures', () => {
  assert.equal(shortText('1.654537 m/s'), '1.655 m/s');
  assert.equal(shortText('worst 34508.8534 Pa at tick 3415'), 'worst 34510 Pa at tick 3415');
});

test('the headline names the largest change with its numbers', () => {
  const a = rec('safe', null, [req('R1', 'pass', 'Vertical speed at contact')]);
  const b = rec('safe', null, [{ ...req('R1', 'fail', 'Vertical speed at contact'), observed: '60.077734 m/s' }]);
  const h = headlineChange(a, b);
  assert.match(h.text, /Vertical speed at contact 1\.655 → 60\.08 m\/s \(limit <= 3 m\/s\)/);
  assert.equal(h.flip, true);
});

const decl = (id, status) => ({ id, label: `Declaration ${id}`, category: 'declaration', status, expected: 'x', observed: 'y' });

test('requirementWording says all met only when every mission row passes', () => {
  assert.equal(requirementWording(rec('safe', null, [req('R1', 'pass'), req('R2', 'pass')])), 'all 2 requirements met');
  assert.equal(requirementWording(rec('safe', null, [inv('S1', 'pass')])), '');
});

test('requirementWording puts failures first and counts every status', () => {
  assert.equal(requirementWording(rec('safe', null, [req('R1', 'fail'), req('R2', 'pass'), req('R3', 'not_evaluated')])), '1 of 3 requirements failed, 1 not evaluated, 1 met');
  assert.equal(requirementWording(rec('safe', null, [req('R1', 'fail'), req('R2', 'fail'), req('R3', 'pass')])), '2 of 3 requirements failed');
});

test('requirementWording never calls unevaluated rows met', () => {
  assert.equal(requirementWording(rec('safe', null, [req('R1', 'pass'), req('R2', 'not_evaluated')])), '1 of 2 requirements met, 1 not evaluated');
  assert.equal(requirementWording(rec('safe', null, [req('R1', 'not_evaluated')])), '0 of 1 requirements met, 1 not evaluated');
});

test('requirementWording leaves declaration rows out of the count', () => {
  const r = rec('safe', null, [req('R1', 'pass'), decl('D1', 'fail'), decl('D2', 'not_evaluated')]);
  assert.equal(requirementWording(r), 'all 1 requirements met');
  assert.equal(failureSentence(r), 'All 1 mission requirements met.');
  assert.equal(failureSentence(rec('safe', null, [req('R1', 'pass'), req('R2', 'not_evaluated')])), '');
});

test('statusLine joins the requirement and safety wording, failures first, without a bare status', () => {
  const line = statusLine(rec('unsafe', null, [req('R1', 'fail'), req('R2', 'pass'), inv('S1', 'fail'), inv('S2', 'pass')]));
  assert.equal(line, '1 of 2 requirements failed · 1 of 2 safety rules broken');
  assert.equal(statusLine(rec('safe', null, [req('R1', 'pass'), inv('S1', 'pass'), inv('S2', 'pass')])), 'all 1 requirements met · 2 of 2 safety rules held');
  assert.doesNotMatch(statusLine(rec('safe', null, [inv('S1', 'pass')])), /\bsafe\b/i);
});

test('heldText counts only evaluated rules and names the unevaluated', () => {
  assert.equal(safetyWording(rec('safe', null, [inv('S1', 'pass'), inv('S2', 'not_evaluated')])).heldText, '1 of 2 safety rules held (1 not evaluated)');
  assert.equal(safetyWording(rec('safe', null, [inv('S1', 'not_evaluated')])).heldText, 'safety not evaluated');
  assert.equal(safetyWording(rec('unsafe', null, [inv('S1', 'fail'), inv('S2', 'pass')])).heldText, '1 of 2 safety rules broken');
});

test('shortText leaves digits inside ids and tokens alone and short decimals as written', () => {
  assert.equal(shortText('R1_vertical_speed 9e6edb2e v1.2.3'), 'R1_vertical_speed 9e6edb2e v1.2.3');
  assert.equal(shortText('limit 3.5 m/s, 0.25 s, seed 1337'), 'limit 3.5 m/s, 0.25 s, seed 1337');
  assert.equal(shortText('observed 60.077734 m/s'), 'observed 60.08 m/s');
});

test('marginDerived marks a margin Studio worked out and not one the domain published', () => {
  const r = req('R1', 'pass');
  assert.equal(reqView(r).marginDerived, true);
  const record = { requirements: [r], metrics: [{ id: 'requirement_observed.R1', value: 1.6, unit: 'm/s' }, { id: 'requirement_limit.R1', value: 3, unit: 'm/s' }, { id: 'requirement_margin.R1', value: 1.4, unit: 'm/s' }] };
  indexNumbers(record);
  assert.equal(reqView(r).marginDerived, false);
});

test('headlineChange returns null when nothing moved', () => {
  const a = rec('safe', null, [req('R1', 'pass')]);
  assert.equal(headlineChange(a, rec('safe', null, [req('R1', 'pass')])), null);
});

const CATALOG = {
  scenarios: [], controllers: [], time: { unit: 's' },
  parameters: [
    { id: 'gps_noise_mm', label: 'GPS noise', default: 0, unit: 'mm' },
    { id: 'arrival_radius_mm', label: 'Arrival radius', default: 500, unit: 'mm' },
  ],
  faults: [{ kind: 'gps_dropout', label: 'GPS dropout' }],
};
const request = (parameters, faults = []) => ({ scenario: 's', controller: 'c', seed: 1, faults, parameters });

test('conditionsName lists every non-default parameter and fault, and says default conditions otherwise', () => {
  assert.equal(conditionsName(request({}), CATALOG), 'default conditions');
  assert.equal(conditionsName(request({ gps_noise_mm: 0, arrival_radius_mm: 500 }), CATALOG), 'default conditions');
  assert.equal(conditionsName(request({ gps_noise_mm: 1, arrival_radius_mm: 250 }), CATALOG), 'GPS noise 1 mm · Arrival radius 250 mm');
  assert.match(conditionsName(request({ gps_noise_mm: 1 }, [{ kind: 'gps_dropout', magnitude: null, start: 1, end: 2 }]), CATALOG), /^GPS noise 1 mm · GPS dropout/);
  assert.doesNotMatch(conditionsName(request({ gps_noise_mm: 1 }), CATALOG), /no injected fault/);
});

test('the same request always gets the same name, and different requests never share one', () => {
  const reqs = [request({}), request({ gps_noise_mm: 1 }), request({ gps_noise_mm: 1, arrival_radius_mm: 250 })];
  const names = reqs.map((r) => conditionsName(r, CATALOG));
  assert.equal(new Set(names).size, 3);
  assert.deepEqual(names, reqs.map((r) => conditionsName(JSON.parse(JSON.stringify(r)), CATALOG)));
});

test('conditionsShared says what both runs share and what they differ in', () => {
  const s = conditionsShared([request({ gps_noise_mm: 1 }), request({ gps_noise_mm: 1, arrival_radius_mm: 250 })], CATALOG);
  assert.equal(s.text, 'Both runs: GPS noise 1 mm; they differ only in Arrival radius');
  const t = conditionsShared([request({ gps_noise_mm: 1 }), request({ gps_noise_mm: 2 })], CATALOG);
  assert.equal(t.text, 'Both runs: no non-default condition in common; they differ only in GPS noise');
  const u = conditionsShared([request({}), request({ gps_noise_mm: 1 }), request({ gps_noise_mm: 1, arrival_radius_mm: 250 })], CATALOG);
  assert.equal(u.text, 'All 3 runs: no non-default condition in common; they differ only in GPS noise, Arrival radius');
});

test('displayRunLabel keeps a stored label and names an Experiment run by its parameters', () => {
  const record = { request: request({ arrival_radius_mm: 250 }) };
  assert.equal(displayRunLabel(record, CATALOG, 'My run'), 'My run');
  assert.match(displayRunLabel(record, CATALOG, 'Experiment from 9e6edb2e1234', ['from:9e6edb2e1234']), /Arrival radius 250 mm.*\(from 9e6edb2e12\)/);
  assert.equal(displayRunLabel({ request: request({}) }, CATALOG, 'Experiment from abc'), 'Experiment from abc');
});


const withOutcome = (status, label, r) => ({ ...r, outcome: { status, label, code: status } });

test('the end chip is green only when the rules were judged and none broke', () => {
  const r = withOutcome('success', 'Landed', rec('safe', null, [req('R1', 'pass'), inv('S1', 'pass')]));
  assert.deepEqual(endChip(r, true), { text: 'Touchdown', kind: 'end', end: true });
});

test('the end chip is neutral and says safety not evaluated when the rules were not judged', () => {
  const classed = withOutcome('success', 'Landed', rec('safe', 'not_evaluated', [req('R1', 'pass'), inv('S1', 'pass')]));
  assert.deepEqual(endChip(classed, true), { text: 'Touchdown; safety not evaluated', kind: 'end-neutral', end: true });
  const rows = withOutcome('success', 'Landed', rec('safe', null, [req('R1', 'pass'), inv('S1', 'not_evaluated'), inv('S2', 'not_evaluated')]));
  assert.equal(endChip(rows, true).kind, 'end-neutral');
  assert.doesNotMatch(endChip(rows, true).text, /^Touchdown$/);
  // without a ground contact too
  assert.equal(endChip(withOutcome('success', 'Mission completed', rec('safe', 'not_evaluated', [inv('S1', 'pass')])), false).text, 'End of run: Mission completed; safety not evaluated');
});

test('the end chip is bad when the record says unsafe even with no failing row', () => {
  const r = withOutcome('success', 'Landed', rec('unsafe', null, [req('R1', 'pass'), inv('S1', 'pass')]));
  assert.deepEqual(endChip(r, true), { text: 'Touchdown; a safety rule was broken; impact not modelled', kind: 'end-bad', end: true });
  assert.equal(endChip(r, false).kind, 'end-bad');
});

test('the end chip names the failed requirement and the broken rule', () => {
  const r = withOutcome('failure', 'Reached the ground', rec('unsafe', null, [{ ...req('R1', 'fail', 'Vertical speed at contact'), observed: '24.229379 m/s', expected: '<= 3 m/s' }, { ...inv('S5', 'fail'), label: 'Climb under power' }]));
  const chip = endChip(r, true);
  assert.equal(chip.kind, 'end-bad');
  assert.match(chip.text, /^Not met: Vertical speed at contact 24\.23 m\/s \(limit <= 3 m\/s\); safety rule broken: Climb under power; impact not modelled$/);
});

// ----------------------------------------------------------------------------- M19.1: the safety chip is never the green of a requirement

test('a safety rule that held is neutral and never the green class of a requirement that was met', () => {
  for (const rows of [[], [inv('S1', 'pass')], [inv('S1', 'pass'), inv('S2', 'not_evaluated')], [req('R1', 'fail'), inv('S1', 'pass')]]) {
    const w = safetyWording(rec('safe', null, rows));
    assert.equal(w.verdict, 'held', JSON.stringify(rows));
    assert.notEqual(w.verdict, 'pass');
  }
  assert.equal(verdictOfSafety('safe'), 'held');
  assert.equal(verdictOfSafety('unsafe'), 'unsafe');
  assert.equal(verdictOfSafety('not_evaluated'), 'neutral');
  // the mission outcome keeps its own green
  assert.equal(verdictOfOutcome('success'), 'pass');
});

test('beside failed requirements the safety verdict is held and the requirement wording says failed', () => {
  const r = rec('safe', null, [req('R1', 'fail'), req('R2', 'fail'), inv('S1', 'pass'), inv('S2', 'pass')]);
  assert.equal(requirementWording(r), '2 of 2 requirements failed');
  assert.equal(safetyWording(r).verdict, 'held');
  assert.equal(safetyWording(r).text, 'No safety rule broken (2 checked)');
});
test('a record with a row that was not evaluated never says every requirement met', () => {
  const rows = [req('R1', 'pass'), req('R2', 'not_evaluated', 'Mission starts and completes'), inv('S1', 'pass')];
  const r = rec('safe', null, rows);
  assert.equal(noFailureSentence(r, ['requirement', 'invariant']), 'No requirement or safety rule failed, but 1 was not evaluated: Mission starts and completes (requirement).');
  const two = rec('safe', null, [req('R1', 'pass'), inv('S1', 'not_evaluated'), req('R2', 'not_evaluated', 'Apoapsis')]);
  assert.equal(noFailureSentence(two, ['requirement', 'invariant']), 'No requirement or safety rule failed, but 2 were not evaluated: Rule S1 (safety rule), Apoapsis (requirement).');
  assert.doesNotMatch(noFailureSentence(r, ['requirement']), /^Every/);
  assert.equal(noFailureSentence(rec('safe', null, [req('R1', 'pass'), inv('S1', 'pass')]), ['requirement', 'invariant']), 'Every requirement and safety rule met.');
  assert.equal(noFailureSentence(rec('safe', null, [req('R1', 'pass')]), ['requirement']), 'Every requirement met.');
  assert.equal(noFailureSentence(rec('safe', null, []), ['requirement', 'invariant']), 'The record lists no requirement and safety rule.');
});
// The two texts below are the ones the ground-vehicle host writes (corridor demonstration, 1 mm of GPS noise).
const completion = (status, observed) => ({ id: 'mission_completion', label: 'Mission completion', category: 'requirement', status, expected: 'all 1 waypoint(s) reached, confirmed on the true position, with no stall of 8 ticks', observed });

test('a failed mission completion at the goal says that the record does not name the failed clause', () => {
  const r = rec('unsafe', null, [completion('fail', 'incomplete; 1 of 1 waypoint(s) reached; 0 mm from the goal at the end')]);
  const f = completionFacts(r);
  assert.equal(f.allReached, true);
  assert.match(f.text, /^Recorded: 1 of 1 waypoint reached, 0 mm from the goal at the end, outcome incomplete\./);
  assert.match(f.text, /does not say which part of "Mission completion" failed \(it expects all 1 waypoint\(s\) reached, confirmed on the true position, with no stall of 8 ticks\)/);
  assert.match(f.text, /Reaching the goal is not the same as completing the mission\./);
});

test('a failed mission completion with waypoints missing needs no apology, and a pass or another shape gives nothing', () => {
  const short = completionFacts(rec('safe', null, [completion('fail', 'stalled; 0 of 2 waypoint(s) reached; 2250 mm from the goal at the end')]));
  assert.equal(short.allReached, false);
  assert.equal(short.text, 'Recorded: 0 of 2 waypoints reached, 2250 mm from the goal at the end, outcome stalled.');
  assert.equal(completionFacts(rec('safe', null, [completion('pass', 'completed; 1 of 1 waypoint(s) reached; 250 mm from the goal at the end')])), null);
  assert.equal(completionFacts(rec('safe', null, [completion('fail', 'something else')])), null);
  assert.equal(completionFacts(rec('safe', null, [])), null);
});
test('the compact run pill counts the conditions exactly and never lists a cut text', () => {
  const catalog = { parameters: [{ id: 'arrival_radius_mm', label: 'Arrival radius', unit: 'mm', default: 0 }], faults: [], time: { unit: 'tick' } };
  assert.equal(conditionsBrief({ parameters: {}, faults: [] }, catalog), 'default conditions');
  assert.equal(conditionsBrief({ parameters: { arrival_radius_mm: 0 }, faults: [] }, catalog), 'default conditions');
  assert.equal(conditionsBrief({ parameters: { arrival_radius_mm: 250 }, faults: [] }, catalog), '1 condition');
  assert.equal(conditionsBrief({ parameters: { arrival_radius_mm: 250 }, faults: [{ kind: 'gps_noise', magnitude: 1, start: 0, end: 32 }] }, catalog), '2 conditions');
  // the full text it stands for is the one name of the conditions
  assert.match(conditionsName({ parameters: { arrival_radius_mm: 250 }, faults: [{ kind: 'gps_noise', magnitude: 1, start: 0, end: 32 }] }, catalog), /^Arrival radius 250 mm .* Gps noise 1/i);
});

test('a safety rule that held is neutral wherever a row is drawn: verdictOfRequirement and statusClassOf', () => {
  // These two functions feed the Safety rules section (verification.js), the Compare matrix (compare.js), the
  // Experiment Lab cells (lab.js) and the ascent scene (scenes/ascent.js); tests/test_m191_honesty.py checks that each one uses them.
  assert.equal(verdictOfRequirement(inv('S1', 'pass')), 'held');
  assert.equal(statusClassOf(inv('S1', 'pass')), 'held');
  assert.equal(verdictOfRequirement(inv('S1', 'fail')), 'unsafe');
  assert.equal(verdictOfRequirement(inv('S1', 'not_evaluated')), 'neutral');
  assert.equal(verdictOfRequirement(req('R1', 'pass')), 'pass');
  assert.equal(statusClassOf(req('R1', 'pass')), 'pass');
  assert.equal(verdictOfRequirement(req('R1', 'fail')), 'fail');
  assert.equal(statusClassOf(req('R1', 'fail')), 'fail');
  assert.equal(statusClassOf(inv('S1', 'fail')), 'fail');
  assert.equal(verdictOfRequirement(decl('D1', 'pass')), 'pass');
});

test('the Mission chip tone is read from the statuses of the mission rows', () => {
  assert.equal(missionTone(rec('safe', null, [req('R1', 'pass'), req('R2', 'pass'), inv('S1', 'pass')])), 'pass');
  assert.equal(missionTone(rec('safe', null, [req('R1', 'pass'), req('R2', 'fail')])), 'fail');
  assert.equal(missionTone(rec('safe', null, [req('R1', 'pass'), req('R2', 'not_evaluated')])), 'neutral');
  assert.equal(missionTone(rec('safe', null, [inv('S1', 'pass')])), 'neutral');
  assert.equal(missionTone(rec('safe', null, [])), 'neutral');
  // a label that happens to say "not evaluated" does not decide it
  assert.equal(missionTone(rec('safe', null, [req('R1', 'pass', 'Not evaluated twice')])), 'pass');
});

test('no plume is drawn after the last sample, and it is drawn at and before it', () => {
  const ch = { times: [0, 0.1, 0.2, 0.3], throttle: [0.5, 0.5, 0.4, 0.4], engine: [1, 1, 1, 1] };
  assert.equal(plumeLengthAt(ch, 0.05), 6 + 22 * 0.5);
  assert.equal(plumeLengthAt(ch, 0.3), 6 + 22 * 0.4);   // the last sample itself: the contact instant
  assert.equal(plumeLengthAt(ch, 0.3 + 1e-12), 6 + 22 * 0.4);
  assert.equal(plumeLengthAt(ch, 0.31), 0);              // the playback of a longer run goes on: nothing is recorded
  assert.equal(plumeLengthAt(ch, 30), 0);
  assert.equal(plumeLengthAt({ times: [0, 1], throttle: [0.5, 0], engine: [1, 1] }, 1), 0);
  assert.equal(plumeLengthAt({ times: [0, 1], throttle: [0.5, 0.5], engine: [1, 2] }, 1), 0);   // engine off
  assert.equal(plumeLengthAt({ times: [0, 1], throttle: [0.5, 0.5] }, 0.5), 6 + 22 * 0.5);     // no engine channel: throttle decides
  assert.equal(plumeLengthAt({ times: [] }, 0), 0);
});

test('the scope sentence names safety rules and requirements apart and never writes a bare safe', () => {
  assert.match(SAFETY_SCOPE, /not the mission result/);
  assert.match(SAFETY_SCOPE, /a requirement can fail without any safety rule being broken/);
  assert.doesNotMatch(SAFETY_SCOPE, /\bsafe\b/i);
});

test('the gloss quotes the domain words, says what they mean, and appears only next to a text that uses them', () => {
  const g = expectationGloss('Baseline: hard landing, safe, R1 vertical speed fails.');
  assert.equal(g, '"safe" here means only that no safety rule was broken, and "unsafe" that one was; requirements are separate verdicts.');
  assert.equal(expectationGloss('Threshold 3 m: hard landing, unsafe, R1 fails.'), g);
  assert.equal(expectationGloss('The vehicle ends 2250 mm from the goal; the safety rules hold.'), g);
  assert.equal(expectationGloss('Reaches orbit with every requirement met.'), null);
  assert.equal(expectationGloss('The unsafely named thing'), null);
  assert.equal(expectationGloss(undefined), null);
});

console.log(`${n} tests passed`);
