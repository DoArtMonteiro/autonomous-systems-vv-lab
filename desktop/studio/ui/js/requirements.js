// Reading of a run record's requirements and safety verdicts for display, shared by the Lab, the
// comparison, the Library and the player. Nothing here computes a flight: every number is a value
// the record carries (the observed text, the expected text, the published margin metrics) or a
// plain derivation of them (a margin from limit minus observed, a cosine shown as an angle), and a
// derived value says so in its title. A value that cannot be read is shown as it was written.

/** Significant figures shown; the full recorded text stays in the title of the element. */
export const SIG = 4;

export const fmtSig = (v, d = SIG) => (v === null || v === undefined || !Number.isFinite(v) ? '–' : Number(v.toPrecision(d)).toString());

/** Every number in a recorded text, cut to four significant figures ("1.654537 m/s" -> "1.655 m/s"). */
export function shortText(text) {
  // A decimal number on its own (not part of an id or token such as R1_x, 9e6edb2e or v1.2.3) with five or
  // more significant digits is cut to four; everything else is left as it was written.
  return String(text ?? '').replace(/(?<![\w.])-?\d+\.\d+(?:e[-+]?\d+)?(?![\w.])/gi, (n) => {
    const digits = n.replace(/e.*$/i, '').replace(/[^0-9]/g, '').replace(/^0+/, '');
    const v = Number(n);
    return digits.length >= 5 && Number.isFinite(v) ? Number(v.toPrecision(SIG)).toString() : n;
  });
}

// Numbers the domain publishes with a record: the metrics requirement_observed.<id>,
// requirement_limit.<id> and requirement_margin.<id> (margin positive when met, in the unit of the
// metric). They are read once per record; a record without them (older records, requirements that
// are not one quantity against one bound) falls back to the text of the requirement.
const NUMBERS = new WeakMap();

export function indexNumbers(record) {
  const byId = new Map((record.metrics || []).map((m) => [m.id, m]));
  for (const r of record.requirements || []) {
    const margin = byId.get(`requirement_margin.${r.id}`);
    const limit = byId.get(`requirement_limit.${r.id}`);
    const observed = byId.get(`requirement_observed.${r.id}`);
    if (margin && limit && observed && Number.isFinite(margin.value) && Number.isFinite(limit.value) && Number.isFinite(observed.value)) {
      // The bound it is held to: the margin is limit minus observed for an upper bound, observed minus limit for a lower one.
      const tol = 1e-9 * Math.max(1, Math.abs(limit.value), Math.abs(observed.value));
      const op = Math.abs(margin.value - (limit.value - observed.value)) <= tol ? '<=' : Math.abs(margin.value - (observed.value - limit.value)) <= tol ? '>=' : '';
      NUMBERS.set(r, { margin: margin.value, limit: limit.value, observed: observed.value, op, unit: margin.unit || '' });
    }
  }
  return record;
}

const NUM = '(-?[\\d.]+(?:e[-+]?\\d+)?)';

export function opOf(r) {
  const n = NUMBERS.get(r);
  if (n) return n.op;
  const m = /^\s*(<=|>=|<|>)/.exec(r.expected || '');
  return m ? m[1] : '';
}

export function limitOf(r) {
  const n = NUMBERS.get(r);
  if (n) return { op: opOf(r), value: n.limit };
  const m = new RegExp(`^\\s*(<=|>=|<|>)\\s*${NUM}`, 'i').exec(r.expected || '');
  return m ? { op: m[1], value: Number(m[2]) } : null;
}

export function observedOf(r) {
  // The domain's published reading, not the first number of its sentence ("apoapsis 301.90 km, error +1.90 km").
  const n = NUMBERS.get(r);
  if (n) return n.observed;
  const m = new RegExp(NUM, 'i').exec(r.observed || '');
  return m ? Number(m[1]) : null;
}

export function unitOf(r) {
  const n = NUMBERS.get(r);
  if (n) return n.unit;
  const m = new RegExp(`${NUM}\\s*(.*)$`, 'i').exec(r.expected || '');
  return m ? m[2].trim() : '';
}

/**
 * Margin to the limit in the requirement's unit, positive when met: the domain's number when it
 * published one, otherwise limit minus observed parsed from the two texts (as precise as they are;
 * a composite observation gives none).
 */
export function marginOf(r) {
  const n = NUMBERS.get(r);
  if (n) return n.margin;
  const lim = limitOf(r);
  const obs = observedOf(r);
  if (!lim || obs === null || !Number.isFinite(obs)) return null;
  return lim.op.startsWith('<') ? lim.value - obs : obs - lim.value;
}

const DEG = 180 / Math.PI;

/**
 * One requirement for display: observed value, limit and margin in one unit, to four significant
 * figures, with the full recorded text for a title. A tilt recorded as a cosine is shown as an
 * angle in degrees (derived: acos of the recorded value), so every tilt reads the same way.
 */
export function reqView(r) {
  const full = `${r.label}: observed ${r.observed}, expected ${r.expected}`;
  const lim = limitOf(r);
  const obs = observedOf(r);
  let unit = unitOf(r);
  let margin = marginOf(r);
  if (lim && obs !== null && Number.isFinite(obs) && unit === 'cos' && Math.abs(lim.value) <= 1 && Math.abs(obs) <= 1) {
    const o = Math.acos(obs) * DEG;
    const l = Math.acos(lim.value) * DEG;
    const flipped = lim.op === '>=' ? '<=' : lim.op === '<=' ? '>=' : lim.op;
    const m = lim.op.startsWith('>') ? l - o : o - l;
    return {
      numeric: true, obs: o, limit: l, op: flipped, unit: '°', margin: m,
      obsText: `${fmtSig(o)} °`, limitText: `${flipped} ${fmtSig(l)} °`, marginText: `${m >= 0 ? '+' : '-'}${fmtSig(Math.abs(m))} °`, marginDerived: true,
      full: `${full} (shown as an angle: arccos of the recorded cosine)`,
    };
  }
  if (lim && obs !== null && Number.isFinite(obs)) {
    const u = unit ? ` ${unit}` : '';
    return {
      numeric: true, obs, limit: lim.value, op: lim.op, unit, margin,
      obsText: `${fmtSig(obs)}${u}`, limitText: `${lim.op ? `${lim.op} ` : ''}${fmtSig(lim.value)}${u}`,
      marginText: margin === null ? '' : `${margin >= 0 ? '+' : '-'}${fmtSig(Math.abs(margin))}${u}`, marginDerived: !NUMBERS.has(r),
      full,
    };
  }
  return { numeric: false, obs: null, limit: null, op: '', unit, margin: null, obsText: shortText(r.observed), limitText: shortText(r.expected), marginText: '', marginDerived: false, full };
}

const STAGES = { booster: 'Booster', upper: 'Upper stage', stack: 'Stack' };

/** The label of a requirement with the stage it belongs to when its id names one ("booster.R2_..."), so two stages never share a name. */
export function reqLabel(r) {
  const m = /^([a-z_]+)\./.exec(r.id || '');
  const stage = m ? STAGES[m[1]] : null;
  const label = r.category === 'invariant' ? `${r.label} · ${stage ? `${stage} · ` : ''}safety` : stage ? `${r.label} · ${stage}` : r.label;
  return label;
}

// ----------------------------------------------------------------------------- safety wording

/**
 * The safety verdict in the words of the mission player: how many safety rules were checked and how
 * many broke, never a bare "safe". Only evaluated invariants are counted (a rule the run never judged
 * is neither checked nor passed), a broken rule is looked at before anything else so it never reads as
 * neutral, and no count is written that the record's own rows do not give. `verdict` is the glyph
 * class: `unsafe`, `neutral` or `held`. "No safety rule broken" is never `pass`: that class is green and belongs to
 * a requirement that was met, while a rule that held is a bounded statement (judged on the true state, only the
 * rules the domain lists) and is drawn in a neutral tone of its own, so it never reads as the outcome of the mission.
 */
export function safetyWording(record) {
  const inv = (record.requirements || []).filter((q) => q.category === 'invariant');
  const judged = inv.filter((q) => q.status !== 'not_evaluated');
  const notEvaluated = inv.length - judged.length;
  const broken = judged.filter((q) => q.status === 'fail').length;
  const base = { n: inv.length, checked: judged.length, notEvaluated, broken };
  // The same counts for a status line: "5 of 5 safety rules held" (held = evaluated and not broken).
  const held = `${judged.length - broken} of ${inv.length} safety rules held${notEvaluated ? ` (${notEvaluated} not evaluated)` : ''}`;
  if (record.safety.status === 'unsafe' || broken) {
    const text = broken ? `${broken} of ${judged.length} safety rules broken` : 'A safety rule was broken';
    return { ...base, text, heldText: text, verdict: 'unsafe', unjudged: false };
  }
  const unjudged = (record.safety.status === 'safe' && record.safety.class === 'not_evaluated') || (inv.length > 0 && judged.length === 0);
  if (unjudged) return { ...base, text: 'Safety not evaluated', heldText: 'safety not evaluated', verdict: 'neutral', unjudged: true };
  if (!inv.length) return { ...base, text: 'No safety rule broken', heldText: 'no safety rule broken', verdict: 'held', unjudged: false };
  const count = notEvaluated ? `${judged.length} of ${inv.length} checked; ${notEvaluated} not evaluated` : `${judged.length} checked`;
  return { ...base, text: `No safety rule broken (${count})`, heldText: held, verdict: 'held', unjudged: false };
}

/**
 * The safety words for a run known only by its list summary (no rows): the same rule as safetyWording,
 * without a count the summary does not carry. A run whose rules were never judged is "safety not evaluated".
 */
export function summarySafetyText(s) {
  if (s.safety_status === 'unsafe') return 'a safety rule broken';
  if (s.safety_status === 'safe' && s.safety_class === 'not_evaluated') return 'safety not evaluated';
  return 'no safety rule broken';
}

/** "2 of 6 requirements failed" or "all 6 requirements met"; nothing when the record lists no mission requirement. */
export function requirementWording(record) {
  // Mission requirements only: a controller declaration is judged against the truth but is not a requirement.
  const m = (record.requirements || []).filter((q) => q.category === 'requirement');
  if (!m.length) return '';
  const failed = m.filter((q) => q.status === 'fail').length;
  const met = m.filter((q) => q.status === 'pass').length;
  const unknown = m.length - failed - met;
  if (!failed && !unknown) return `all ${m.length} requirements met`;
  if (!failed) return `${met} of ${m.length} requirements met, ${unknown} not evaluated`;
  return `${failed} of ${m.length} requirements failed${unknown ? `, ${unknown} not evaluated, ${met} met` : ''}`;
}

/**
 * The sentence for a record in which no row failed: "Every requirement met." only when every row of those
 * categories passed. A row that was not evaluated is neither met nor failed, so it is named instead of being counted
 * as met; a record with no row of the category says so. `categories` is ['requirement'] or ['requirement', 'invariant'].
 */
export function noFailureSentence(record, categories) {
  const rows = (record.requirements || []).filter((q) => categories.includes(q.category));
  const what = categories.length === 1 ? 'requirement' : 'requirement and safety rule';
  if (!rows.length) return `The record lists no ${what}.`;
  const unknown = rows.filter((q) => q.status !== 'pass' && q.status !== 'fail');
  if (!unknown.length) return `Every ${what} met.`;
  return `No ${what} failed, but ${unknown.length} ${unknown.length === 1 ? 'was' : 'were'} not evaluated: ${unknown.map(plainName).join(', ')}.`;
}

/** The combined status, failure first, with the two kinds of verdict kept apart: "2 of 6 requirements failed · 5 of 5 safety rules held". */
export function statusLine(record) {
  return [requirementWording(record), safetyWording(record).heldText].filter(Boolean).join(' · ');
}

/** The footnote that explains the D badge on a margin Studio worked out itself. */
export const DERIVED_NOTE = 'D: derived by Studio from the recorded values (the limit minus the observed value, or a cosine shown as an angle). A margin without D is the one the domain publishes.';

export const SAFETY_NOTE = 'Safety rules are judged on the true state throughout the run. Mission requirements are judged separately: a requirement can fail without any safety rule being broken.';

/** The name of a requirement for people: the label, never the id ("R1_vertical_speed"). */
export function plainName(q) {
  return q.label || String(q.id || '').replace(/^[a-z_]+\./, '').replace(/^[A-Z]\d+_/, '').replace(/_/g, ' ');
}

/** "2 mission requirements failed: Vertical speed at contact, Horizontal speed at contact." and its safety twin, from the record's rows. */
export function failureSentence(record) {
  const reqs = record.requirements || [];
  const mission = reqs.filter((q) => q.category === 'requirement');
  const failed = mission.filter((q) => q.status === 'fail');
  if (!failed.length) return mission.length && mission.every((q) => q.status === 'pass') ? `All ${mission.length} mission requirements met.` : '';
  const n = failed.length;
  return `${n} mission requirement${n === 1 ? '' : 's'} failed: ${failed.map(plainName).join(', ')}.`;
}

// ----------------------------------------------------------------------------- headline change

const SKIP_CATEGORY = new Set(['declaration']);

/**
 * The requirement that moved most between two records, as a sentence with its numbers: a flipped
 * verdict first, then the largest change of margin relative to the limit. Null when the records
 * share no numeric requirement or nothing moved.
 */
export function headlineChange(a, b) {
  const rows = [];
  for (const qa of a.requirements || []) {
    const qb = (b.requirements || []).find((x) => x.id === qa.id);
    if (!qb || SKIP_CATEGORY.has(qa.category)) continue;
    const va = reqView(qa);
    const vb = reqView(qb);
    const flip = qa.status !== qb.status && qa.status !== 'not_evaluated' && qb.status !== 'not_evaluated';
    let size = 0;
    if (va.numeric && vb.numeric) size = Math.abs(vb.obs - va.obs) / Math.max(Math.abs(va.limit), 1e-9);
    if (!flip && !(size > 1e-3)) continue;
    rows.push({ qa, qb, va, vb, flip, size });
  }
  if (!rows.length) return null;
  rows.sort((x, y) => (Number(y.flip) - Number(x.flip)) || (y.size - x.size));
  const t = rows[0];
  const text = t.va.numeric && t.vb.numeric
    ? `${reqLabel(t.qb)} ${fmtSig(t.va.obs)} → ${t.vb.obsText} (limit ${t.vb.limitText})`
    : `${reqLabel(t.qb)}: ${t.qa.status === 'pass' ? 'passes' : t.qa.status === 'fail' ? 'fails' : 'not evaluated'} → ${t.qb.status === 'pass' ? 'passes' : t.qb.status === 'fail' ? 'fails' : 'not evaluated'}`;
  return { text, flip: t.flip, id: t.qa.id, from: t.qa.status, to: t.qb.status };
}

// ----------------------------------------------------------------------------- the chip at the end of a run

/** The labels of the safety rules the record says were broken (its own rows, never the ids). */
export function brokenRules(record) {
  return (record.requirements || []).filter((q) => q.category === 'invariant' && q.status === 'fail').map((q) => q.label || q.id);
}

/** "Not met: <requirement> <value> (limit <limit>)": the failed mission requirement that is furthest past its limit. */
export function failedContactText(record) {
  indexNumbers(record);
  const failed = (record.requirements || []).filter((q) => q.status === 'fail' && q.category === 'requirement');
  if (!failed.length) return 'Reached the ground';
  const views = failed.map((q) => ({ q, v: reqView(q) }));
  const past = (x) => (x.v.numeric && Number.isFinite(x.v.margin) ? -x.v.margin / Math.max(Math.abs(x.v.limit), 1e-9) : 0);
  views.sort((x, y) => past(y) - past(x));
  const top = views[0];
  const more = views.length > 1 ? `, and ${views.length - 1} more not met` : '';
  return `Not met: ${top.q.label} ${top.v.obsText} (limit ${top.v.limitText})${more}`;
}

/**
 * The chip at the end of the run: {text, kind, end}. The safety part is the one reading of safetyWording, never a
 * green word the record did not earn: broken rules are named; a run whose rules were never judged says "safety not
 * evaluated" and is neutral (not green); a run the record marks unsafe without a failing row says a safety rule was
 * broken and is bad. A landing names the failed requirement with its value and limit and says the impact is not drawn.
 * A scene without a ground contact says how the run ended and what failed.
 */
export function endChip(record, hasContact) {
  const met = record.outcome.status === 'success';
  const sw = safetyWording(record);
  const rules = brokenRules(record);
  const ruleText = rules.length ? `safety rule${rules.length > 1 ? 's' : ''} broken: ${rules.join(', ')}`
    : sw.verdict === 'unsafe' ? 'a safety rule was broken'
      : sw.verdict === 'neutral' ? 'safety not evaluated' : '';
  const bad = !met || sw.verdict === 'unsafe';
  const kind = bad ? 'end-bad' : sw.verdict === 'neutral' ? 'end-neutral' : 'end';
  if (hasContact) {
    const parts = [met ? 'Touchdown' : failedContactText(record)];
    if (ruleText) parts.push(ruleText);
    if (bad) parts.push('impact not modelled');
    return { text: parts.join('; '), kind, end: true };
  }
  const failed = (record.requirements || []).filter((q) => q.category === 'requirement' && q.status === 'fail').map((q) => q.label || q.id);
  const parts = [`End of run: ${record.outcome.label}`];
  if (failed.length) parts.push(`requirement${failed.length > 1 ? 's' : ''} not met: ${failed.join(', ')}`);
  if (ruleText) parts.push(ruleText);
  return { text: parts.join('; '), kind, end: true };
}
