// Verdict rendering shared by the run workspace and the comparison. Mission outcome and safety are
// always two separate verdicts; a requirement that was not evaluated is a third, neutral state and
// is never drawn as a pass. Status is carried by a glyph and a word as well as by colour.

import { h, icon, num, timeText, prose, words } from './dom.js';
import { safetyWording, SAFETY_NOTE, failureSentence, reqView, shortText } from './requirements.js';
import { CATEGORY_TITLE, STATUS_TEXT, verdictOfOutcome, verdictOfSafety, verdictOfRequirement } from './model.js';

// `held` is the safety rules that were not broken: an outlined shield in a neutral tone, never the green check of a requirement that was met.
const GLYPH = { pass: 'check', fail: 'cross', unsafe: 'warn', partial: 'dash', neutral: 'dash', held: 'shield' };

export function verdictGlyph(v) {
  return h('span', { class: ['glyph', `v-${v}`], 'aria-hidden': 'true' }, icon(GLYPH[v] || 'dash'));
}

/** The two headline verdicts: mission outcome and safety, never merged. */
export function verdictBlocks(record) {
  const ov = verdictOfOutcome(record.outcome.status);
  // A run whose invariants were never judged (the vehicle never flew) is not shown as safe.
  const sw = safetyWording(record);
  const unjudged = sw.unjudged;
  const sv = sw.verdict;
  // A completed mission can still have failed requirements outside the safety invariants; say so
  // first, so the one-line clamp keeps it visible.
  const failedReqs = (record.requirements || []).filter((r) => r.category !== 'invariant' && r.status === 'fail');
  const failedNote = failedReqs.length ? `${failureSentence(record)} ` : '';
  // Focusable, so keyboard users can expand the clamped explanation (:focus-within).
  const outcome = h('div', { class: ['verdict', `v-${ov}`], role: 'group', 'aria-label': 'Mission outcome', tabindex: '0' },
    h('div', { class: 'verdict-k' }, 'Mission outcome'),
    h('div', { class: 'verdict-v' }, verdictGlyph(ov), h('span', null, record.outcome.label), h('span', { class: 'verdict-s mono' }, record.outcome.status)),
    h('p', { class: 'verdict-x', title: prose(record.outcome.explanation) }, failedNote ? h('b', null, failedNote) : null, shortText(prose(record.outcome.explanation))));
  const cls = record.safety.class;
  const safety = h('div', { class: ['verdict', `v-${sv}`], role: 'group', 'aria-label': 'Safety', tabindex: '0' },
    h('div', { class: 'verdict-k' }, 'Safety, judged on the true state'),
    h('div', { class: 'verdict-v' }, verdictGlyph(sv), h('span', null, sw.text),
      cls && !unjudged ? h('span', { class: ['class-badge', `class-${cls}`], title: 'Classification of the run reported by the domain verifier' }, `class ${cls}`) : null),
    h('p', { class: 'verdict-x', title: prose(record.safety.explanation) }, shortText(prose(record.safety.explanation)), ' ', SAFETY_NOTE));
  return [outcome, safety];
}

function counts(reqs) {
  const c = { pass: 0, fail: 0, not_evaluated: 0 };
  for (const r of reqs) c[r.status in c ? r.status : 'not_evaluated'] += 1;
  return c;
}

/**
 * Requirement list grouped by category. `onTime(t, req)` is called when a row with an instant is
 * activated, so the cursor and the scene move there.
 */
export function requirementList(record, unit, onTime) {
  const reqs = record.requirements || [];
  if (!reqs.length) return h('p', { class: 'empty' }, 'This record lists no requirements.');
  const order = ['invariant', 'requirement', 'declaration'];
  const cats = [...new Set(reqs.map((r) => r.category))].sort((a, b) => (order.indexOf(a) + 1 || 9) - (order.indexOf(b) + 1 || 9));
  const sections = cats.map((cat) => {
    // Failed rows first, each group in the record's own order.
    const inCat = reqs.filter((r) => r.category === cat);
    const list = [...inCat.filter((r) => r.status === 'fail'), ...inCat.filter((r) => r.status !== 'fail')];
    const c = counts(list);
    const summary = [c.fail ? `${c.fail} failed` : null, `${c.pass} passed`, c.not_evaluated ? `${c.not_evaluated} not evaluated` : null].filter(Boolean).join(' · ');
    return h('section', { class: 'req-section', 'aria-label': CATEGORY_TITLE[cat] || words(cat) },
      h('header', { class: 'req-section-head' },
        h('h3', null, CATEGORY_TITLE[cat] || words(cat)),
        h('span', { class: ['mono', 'small', c.fail ? (cat === 'invariant' ? 'v-unsafe-text' : 'v-fail-text') : 'dim'] }, summary)),
      h('ol', { class: 'req-list' }, list.map((r) => requirementRow(r, unit, onTime))));
  });
  return h('div', { class: 'req-sections' }, sections);
}

function requirementRow(r, unit, onTime) {
  const v = verdictOfRequirement(r);
  // A passing requirement holds over the whole run; its instant is not a place to look.
  const hasT = r.status !== 'pass' && typeof r.t === 'number' && Number.isFinite(r.t);
  const when = hasT
    ? h('button', { type: 'button', class: 'req-t mono', title: 'Move the time cursor to this instant', 'aria-label': `Move the cursor to ${timeText(r.t, unit)}`, onclick: () => onTime && onTime(r.t, r) }, timeText(r.t, unit))
    : h('span', { class: 'req-t mono dim', title: 'Judged over the whole run' }, 'whole run');
  // A tilt recorded as a cosine is shown as an angle (derived, display only); the recorded text is in the title.
  const rv = reqView(r);
  const deg = rv.numeric && rv.unit === '°';
  const row = h('li', { class: ['req', `v-${v}`], dataset: { id: r.id } },
    verdictGlyph(v),
    h('div', { class: 'req-main' },
      h('div', { class: 'req-title' },
        h('span', { class: 'req-id mono' }, r.id),
        h('span', { class: 'req-label' }, r.label),
        h('span', { class: ['req-status', `v-${v}-text`] }, STATUS_TEXT[r.status] || r.status)),
      h('dl', { class: 'req-eo' },
        h('dt', null, deg ? 'limit' : 'expected'), h('dd', { class: 'mono', title: deg ? `Recorded: ${r.expected}. Shown as an angle: arccos of the recorded cosine.` : null }, deg ? `${rv.limitText} (${r.expected})` : r.expected),
        h('dt', null, deg ? 'worst' : 'observed'), h('dd', { class: 'mono', title: deg ? `Recorded: ${r.observed}. Shown as an angle: arccos of the recorded cosine.` : null }, deg ? `${rv.obsText} (${r.observed})` : r.observed)),
      r.explanation ? h('p', { class: 'req-x' }, prose(r.explanation)) : null),
    when);
  return row;
}

export function metricTable(record) {
  const ms = record.metrics || [];
  if (!ms.length) return h('p', { class: 'empty' }, 'This record lists no metrics.');
  const groups = [...new Set(ms.map((m) => m.group))];
  return h('div', { class: 'metrics' }, groups.map((g) => h('section', { class: 'metric-group' },
    h('h3', null, g),
    h('table', { class: 'kv' }, h('tbody', null, ms.filter((m) => m.group === g).map((m) => h('tr', { title: m.id },
      h('th', { scope: 'row' }, m.label),
      h('td', { class: 'mono num' }, m.value === null ? 'n/a' : num(m.value, 5)),
      h('td', { class: 'mono dim' }, m.unit))))))));
}

export function notesBlock(record, manifest) {
  const notes = record.notes || [];
  return h('div', { class: 'notes' },
    h('section', { class: 'validity' },
      h('h3', null, 'Model validity'),
      h('p', null, prose(record.model_validity)),
      manifest && prose(manifest.model_validity) !== prose(record.model_validity) ? h('p', { class: 'dim' }, `Domain manifest: ${prose(manifest.model_validity)}`) : null),
    h('section', null,
      h('h3', null, `Notes from the domain (${notes.length})`),
      notes.length ? h('ul', { class: 'note-list' }, notes.map((n) => h('li', null, prose(n)))) : h('p', { class: 'empty' }, 'The domain attached no notes to this run.')));
}
