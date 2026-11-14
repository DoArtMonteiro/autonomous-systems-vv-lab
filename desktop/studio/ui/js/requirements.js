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
  return String(text ?? '').replace(/-?\d+\.?\d*(?:e[-+]?\d+)?/gi, (n) => {
    const v = Number(n);
    return Number.isFinite(v) ? Number(v.toPrecision(SIG)).toString() : n;
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
      obsText: `${fmtSig(o)} °`, limitText: `${flipped} ${fmtSig(l)} °`, marginText: `${m >= 0 ? '+' : '-'}${fmtSig(Math.abs(m))} °`,
      full: `${full} (shown as an angle: arccos of the recorded cosine)`,
    };
  }
  if (lim && obs !== null && Number.isFinite(obs)) {
    const u = unit ? ` ${unit}` : '';
    return {
      numeric: true, obs, limit: lim.value, op: lim.op, unit, margin,
      obsText: `${fmtSig(obs)}${u}`, limitText: `${lim.op ? `${lim.op} ` : ''}${fmtSig(lim.value)}${u}`,
      marginText: margin === null ? '' : `${margin >= 0 ? '+' : '-'}${fmtSig(Math.abs(margin))}${u}`,
      full,
    };
  }
  return { numeric: false, obs: null, limit: null, op: '', unit, margin: null, obsText: shortText(r.observed), limitText: shortText(r.expected), marginText: '', full };
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
 * many broke, never a bare "safe". `verdict` is the glyph class (pass, unsafe or neutral).
 */
export function safetyWording(record) {
  const inv = (record.requirements || []).filter((q) => q.category === 'invariant');
  const broken = inv.filter((q) => q.status === 'fail').length;
  const unjudged = record.safety.status === 'safe' && record.safety.class === 'not_evaluated';
  if (unjudged) return { text: 'Safety not evaluated', verdict: 'neutral', n: inv.length, broken: 0, unjudged: true };
  // A count is shown only when the records' own invariant rows give it; an unsafe verdict with none says so without a number.
  if (record.safety.status === 'unsafe' || broken) return { text: broken ? `${broken} of ${inv.length} safety rules broken` : 'A safety rule was broken', verdict: 'unsafe', n: inv.length, broken, unjudged: false };
  return { text: inv.length ? `No safety rule broken (${inv.length} checked)` : 'No safety rule broken', verdict: 'pass', n: inv.length, broken: 0, unjudged: false };
}

export const SAFETY_NOTE = 'Safety rules are judged on the true state throughout the run. Contact speed and position are mission requirements, judged separately: a hard landing fails a requirement without breaking a safety rule.';

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
    : `${reqLabel(t.qb)} ${t.va.obsText} → ${t.vb.obsText} (limit ${t.vb.limitText})`;
  return { text, flip: t.flip, id: t.qa.id, from: t.qa.status, to: t.qb.status };
}
