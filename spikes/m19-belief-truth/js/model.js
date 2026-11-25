// Data model of the Belief vs Truth view. Pure functions, no DOM.
//
// The view derives nothing: every number comes from data.json (written by extract.py, where each
// value carries a record pointer or a named derivation). This module only looks values up,
// formats them and answers layout questions (nearest sample, next event).

export const MINUS = "−";

/**
 * Words for recorded or derived booleans. Verdict words are never typed into the page text: they
 * come from here, chosen by a boolean in the data.
 */
export const WORDS = {
  verdict: { true: "passed", false: "failed" },
  inside: { true: "inside", false: "outside" },
  equal: { true: "equal", false: "different" },
  before: { true: "before", false: "after" },
  until_end: { true: "active until the end of the run", false: "over before the end of the run" },
};

export function word(kind, flag) {
  return WORDS[kind][String(Boolean(flag))];
}

/** Format a number with fixed digits. The only place where numbers become text. */
export function formatNumber(v, digits) {
  if (typeof v !== "number") return String(v);
  const s = digits === undefined || digits === null ? String(v) : v.toFixed(digits);
  return s.startsWith("-") ? MINUS + s.slice(1) : s;
}

/**
 * Split a series into runs of consecutive non-null values, for drawing a line.
 * Refuses a series that is not declared as a line: observations are points, never joined.
 */
export function lineRuns(series, xs) {
  if (series.render !== "line") {
    throw new Error(`series "${series.label}" is rendered as ${series.render}, never as a line`);
  }
  const runs = [];
  let run = [];
  series.values.forEach((y, i) => {
    if (y === null || y === undefined) {
      if (run.length) runs.push(run);
      run = [];
    } else {
      run.push([xs[i], y, i]);
    }
  });
  if (run.length) runs.push(run);
  return runs;
}

/** Points of a series declared as points: exactly the non-null recorded samples, nothing between. */
export function pointList(series, xs) {
  if (series.render !== "points") {
    throw new Error(`series "${series.label}" is rendered as ${series.render}, not as points`);
  }
  const out = [];
  series.values.forEach((y, i) => {
    if (y !== null && y !== undefined) out.push([xs[i], y, i]);
  });
  return out;
}

export class Model {
  constructor(data) {
    this.data = data;
    this.n = data.n_samples;
    this.t = data.series.t_s.values;
    this.last = this.n - 1;
  }

  series(id) {
    const s = this.data.series[id];
    if (!s) throw new Error(`unknown series ${id}`);
    return s;
  }

  isSeries(id) {
    return Object.prototype.hasOwnProperty.call(this.data.series, id);
  }

  entry(ref) {
    return this.isSeries(ref) ? this.data.series[ref] : this.scalar(ref);
  }

  scalar(id) {
    const s = this.data.scalars[id];
    if (!s) throw new Error(`unknown scalar ${id}`);
    return s;
  }

  /** Value of a scalar, or of a series at sample i. */
  value(ref, i) {
    if (this.isSeries(ref)) return this.series(ref).values[i];
    return this.scalar(ref).v;
  }

  /** Evidence class of a value. A series can change class at one sample (the touchdown sample). */
  cls(ref, i) {
    const e = this.entry(ref);
    if (this.isSeries(ref) && e.cls_by_index && Object.prototype.hasOwnProperty.call(e.cls_by_index, String(i))) {
      return e.cls_by_index[String(i)];
    }
    return e.cls;
  }

  digits(ref) {
    const e = this.entry(ref);
    return e.digits === undefined ? undefined : e.digits;
  }

  /** Text of a value: numbers with their digits, null as the entry's null text (default "none"), lists joined. */
  text(ref, i, digitsOverride) {
    const v = this.value(ref, i);
    const d = digitsOverride === undefined ? this.digits(ref) : digitsOverride;
    const e = this.entry(ref);
    if ((v === null || v === undefined) && e.null_text) return e.null_text;
    return this.render(v, d);
  }

  /** Whether the entry is derived with an approximate derivation (proxy or unrecorded term). */
  approx(ref) {
    const e = this.entry(ref);
    return Boolean(e.derivation && this.data.derivations[e.derivation.name].approx);
  }

  render(v, d) {
    if (v === null || v === undefined) return "none";
    if (Array.isArray(v)) return v.length ? v.join(", ") : "none";
    if (typeof v === "boolean") return v ? "true" : "false";
    if (typeof v === "number") return formatNumber(v, d);
    return String(v);
  }

  /** Raw JSON text of a value, as stored. */
  raw(ref, i) {
    return JSON.stringify(this.value(ref, i));
  }

  /** Resolved record pointer, or null for a derived value. */
  pointer(ref, i) {
    const e = this.entry(ref);
    return e.ptr ? e.ptr.replace("{i}", String(i)) : null;
  }

  /** Inputs of a derivation, each with its raw value at the index the derived value was taken at. */
  derivationInputs(ref, i) {
    const e = this.entry(ref);
    const d = e.derivation;
    if (!d) return [];
    const at = d.at_index !== undefined ? d.at_index : i;
    const out = [];
    for (const sid of d.series_inputs || []) out.push({ id: sid, index: at });
    for (const sid of d.scalar_inputs || []) out.push({ id: sid, index: null });
    return out;
  }

  nearestSample(tSeconds) {
    let best = 0;
    let bd = Infinity;
    for (let k = 0; k < this.n; k++) {
      const d = Math.abs(this.t[k] - tSeconds);
      if (d < bd) {
        bd = d;
        best = k;
      }
    }
    return best;
  }

  clampIndex(i) {
    return Math.max(0, Math.min(this.last, i));
  }

  /** Index of the next (dir=1) or previous (dir=-1) event strictly after or before sample i. */
  eventJump(i, dir) {
    const targets = this.data.events.map((e) => e.nav_index).sort((a, b) => a - b);
    if (dir > 0) {
      const next = targets.find((k) => k > i);
      return next === undefined ? i : next;
    }
    const prev = [...targets].reverse().find((k) => k < i);
    return prev === undefined ? i : prev;
  }
}

export async function loadModel(url = "data.json") {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`could not load ${url}: ${res.status}`);
  return new Model(await res.json());
}
