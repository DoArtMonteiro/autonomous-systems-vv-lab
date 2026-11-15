// Unit tests of the Studio's reading of a run record's requirements and safety verdicts
// (desktop/studio/ui/js/requirements.js has no imports, so it runs under plain Node).
// Run through tests/test_ui_requirements.py, or: node tests/ui_requirements.test.mjs
import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
import path from 'node:path';

const here = path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'));
const mod = await import(pathToFileURL(path.join(here, '..', 'desktop', 'studio', 'ui', 'js', 'requirements.js')).href);
const { safetyWording, reqView, failureSentence, plainName, headlineChange, indexNumbers, shortText, SAFETY_NOTE } = mod;

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
  assert.equal(w.verdict, 'pass');
});

test('safe with some rows not evaluated counts only the evaluated ones and says so', () => {
  const w = safetyWording(rec('safe', null, [inv('S1', 'pass'), inv('S2', 'not_evaluated'), inv('S3', 'pass')]));
  assert.equal(w.text, 'No safety rule broken (2 of 3 checked; 1 not evaluated)');
  assert.equal(w.verdict, 'pass');
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
  assert.equal(w.verdict, 'pass');
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

console.log(`${n} tests passed`);
