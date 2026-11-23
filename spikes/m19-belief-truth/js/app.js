// Belief vs Truth, iteration 2: wiring. State is a cursor (a sample index), a time window, the plan
// extent and the divergence threshold. Nothing here derives a value: numbers come from the Model.

import { loadModel, word } from "./model.js";
import { drawTimeAxis, drawStrip, drawLane, drawPlan, timeAt } from "./charts.js";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const clsKey = (c) => c.replace("-", "");

let model;
const state = { cursor: 0, t0: 0, t1: 1, zoom: "full", plan: "window", divTh: "3", divMetric: 0 };
let lastTrigger = null;
let trackHalf = 100;

// ---------------------------------------------------------------------------------------------
// Small DOM helper

function h(tag, cls, ...kids) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  for (const k of kids) {
    if (k === null || k === undefined) continue;
    e.append(k instanceof Node ? k : document.createTextNode(String(k)));
  }
  return e;
}

// ---------------------------------------------------------------------------------------------
// Value buttons: the single way a number reaches the page. Each opens the evidence drawer.

function tagEl(cls, label) {
  const t = h("span", `tag tag-${clsKey(cls)}`, label || cls);
  t.title = model.data.classes[cls] || cls;
  return t;
}

function approxEl() {
  const t = h("span", "tag tag-approx", "approx.");
  t.title = "Uses a proxy or a term the run does not record";
  return t;
}

function indexFrom(at) {
  if (at === undefined || at === null || at === "") return 0;
  if (/^\d+$/.test(at)) return Number(at);
  const k = model.data.index[at];
  if (k === undefined) throw new Error(`unknown index name ${at}`);
  return k;
}

/** Value button for a scalar id, or a series id at sample i. */
function V(ref, { i = 0, digits, unit, tag = true, nounit = false } = {}) {
  const cls = model.cls(ref, i);
  const b = h("button", "val");
  b.type = "button";
  b.dataset.ref = ref;
  b.dataset.i = String(i);
  const effective = digits === undefined ? model.digits(ref) : digits;
  b.dataset.digits = effective === undefined ? "" : String(effective);
  const txt = model.text(ref, i, digits);
  b.appendChild(h("span", "num", txt));
  const isNum = typeof model.value(ref, i) === "number";
  const u = unit !== undefined ? unit : model.entry(ref).unit;
  if (u && !nounit && isNum) b.appendChild(h("span", "unit", ` ${u}`));
  if (tag) {
    b.appendChild(tagEl(cls));
    if (model.approx(ref)) b.appendChild(approxEl());
  }
  b.setAttribute("aria-label", `${txt}${u && !nounit && isNum ? " " + u : ""}, evidence class ${cls}${model.approx(ref) ? ", approximate" : ""}. Open evidence.`);
  return b;
}

/** A word chosen from a boolean in the data (never typed into the page). */
function wordBtn(kind, ref, { i = 0, tag = true } = {}) {
  const b = V(ref, { i, tag });
  b.firstChild.textContent = word(kind, model.value(ref, i));
  b.dataset.display = "label";
  b.classList.add(model.value(ref, i) ? "w-yes" : "w-no");
  return b;
}

function fillPlaceholders(root = document) {
  for (const ph of $$("[data-fact-tag]", root)) {
    ph.replaceWith(h("span", "s-src", tagEl("S"), " ", factButton(ph.dataset.factTag)));
  }
  for (const ph of $$("[data-v]", root)) {
    const ref = ph.dataset.v;
    const i = indexFrom(ph.dataset.at);
    if (ph.dataset.word) {
      ph.replaceWith(wordBtn(ph.dataset.word, ref, { i }));
    } else if (ph.dataset.text) {
      const b = V(ref, { i, tag: false });
      b.dataset.display = "label";
      ph.replaceWith(b);
    } else {
      const d = ph.dataset.digits === undefined ? undefined : Number(ph.dataset.digits);
      ph.replaceWith(V(ref, { i, digits: d, nounit: ph.dataset.nounit === "1" }));
    }
  }
}

// ---------------------------------------------------------------------------------------------
// Evidence drawer

function kv(dl, k, content) {
  const dd = h("dd");
  if (content instanceof Node) dd.appendChild(content);
  else dd.textContent = content;
  dl.append(h("dt", null, k), dd);
}

const code = (s) => h("code", null, s);

function factNode(id) {
  const f = model.data.source_facts[id];
  const wrap = h("div", null, code(`${f.file}:${f.lines[0]}-${f.lines[1]}`), ` ${f.claim}`);
  if (f.identical_to_recording === true) wrap.append(" This file is identical to the recording tree.");
  if (f.identical_to_recording === false) wrap.append(" This file DIFFERS from the recording tree.");
  return wrap;
}

function openEvidence(ref, i, trigger) {
  lastTrigger = trigger || document.activeElement;
  const e = model.entry(ref);
  const cls = model.cls(ref, i);
  const body = $("#drawer-body");
  body.textContent = "";
  $("#drawer-title").textContent = e.label || ref;
  const dl = h("dl", "kv");
  kv(dl, "Class", h("div", null, tagEl(cls), ` ${model.data.classes[cls]}`));
  const valueLine = h("div", null, code(model.raw(ref, i)));
  if (e.unit && typeof model.value(ref, i) === "number") valueLine.append(` ${e.unit}`);
  kv(dl, "Raw value", valueLine);
  if (model.isSeries(ref)) {
    kv(dl, "Sample", `index ${i}, step ${model.value("step", i)}, ${model.value("kind", i)} sample`);
    if (e.cls_by_index && e.cls_by_index[String(i)]) {
      kv(dl, "Class here", `${cls} at this sample: the host interpolated the contact state (S_touchdown_sample).`);
    }
  }
  if (e.reference) kv(dl, "Reference point", e.reference);
  const ptr = model.pointer(ref, i);
  if (ptr) {
    const file = ptr.split("#")[0];
    kv(dl, "Record path", code(ptr + (e.reduce ? `  (${e.reduce} of the entries)` : "")));
    const inp = model.data.inputs[file] || model.data.extra_inputs[file];
    kv(dl, "File", `${inp.path}, sha256 ${inp.sha256.slice(0, 16)}...`);
    if (e.null_parent) kv(dl, "Null rule", "A null parent in the record (the whole sensor vector) gives a null value.");
  }
  if (e.derivation) {
    const d = model.data.derivations[e.derivation.name];
    kv(dl, "Derivation", code(e.derivation.name));
    kv(dl, "Formula", d.formula);
    if (e.derivation.params) kv(dl, "Parameters", code(JSON.stringify(e.derivation.params)));
    kv(dl, "Approximate", d.approx ? "yes: uses a proxy or an unrecorded term" : "no");
    const inputs = model.derivationInputs(ref, i);
    const interpolatedInput = inputs.some((inpt) => inpt.index !== null && model.cls(inpt.id, inpt.index) !== model.entry(inpt.id).cls);
    if (interpolatedInput) kv(dl, "Against interpolated truth", `${cls}, computed against the host-interpolated truth of the touchdown sample.`);
    const ul = h("ul", "inputs");
    for (const inpt of inputs) {
      const ie = model.entry(inpt.id);
      const where = model.pointer(inpt.id, inpt.index ?? 0);
      const li = h("li", null, tagEl(model.cls(inpt.id, inpt.index ?? 0)), ` ${ie.label}: `, code(model.raw(inpt.id, inpt.index ?? 0)));
      if (where) li.append(" at ", code(where));
      else li.append(` (derived: ${ie.derivation.name})`);
      ul.appendChild(li);
    }
    kv(dl, "Inputs", ul);
  }
  for (const f of e.source_facts || []) kv(dl, "Source code", factNode(f));
  if (e.note) kv(dl, "Note", e.note);
  body.appendChild(dl);
  showDrawer();
}

function openFact(id, trigger) {
  lastTrigger = trigger || document.activeElement;
  const f = model.data.source_facts[id];
  $("#drawer-title").textContent = `Source code: ${id}`;
  const body = $("#drawer-body");
  body.textContent = "";
  const dl = h("dl", "kv");
  kv(dl, "Class", h("div", null, tagEl("S"), ` ${model.data.classes.S}`));
  kv(dl, "File and lines", code(`${f.file}:${f.lines[0]}-${f.lines[1]}`));
  kv(dl, "Claim", f.claim);
  kv(dl, "Anchors checked", f.anchors.join("  |  "));
  kv(dl, "File sha256", `${model.data.source_files[f.file].slice(0, 16)}...`);
  if (f.identical_to_recording !== null) {
    kv(dl, "Against the recording tree", f.identical_to_recording ? "identical (same per-file hash)" : "differs");
  }
  body.appendChild(dl);
  showDrawer();
}

function showDrawer() {
  const d = $("#drawer");
  d.hidden = false;
  d.focus();
}

function closeDrawer() {
  const d = $("#drawer");
  d.hidden = true;
  if (lastTrigger && document.contains(lastTrigger)) lastTrigger.focus();
}

function factButton(id, label = "source") {
  const b = h("button", "link", label);
  b.type = "button";
  b.dataset.fact = id;
  return b;
}

// ---------------------------------------------------------------------------------------------
// Evidence bar and sections

function renderBar() {
  const chips = $("#chips");
  const mk = (label, ...nodes) => chips.appendChild(h("li", null, h("span", "chip-l", label), ...nodes));
  mk("Seed", V("run.seed"));
  mk("Policy", V("run.policy"));
  mk("Fault", V("run.fault_kind"), " on GNSS x and z, ", V("case.fault_magnitude_m"), ", configured ", V("case.fault_start_s"), " to ", V("case.fault_end_s"));
  mk("Recorded by", "rocket-landing host ", V("run.version"));
  mk("Cadence", "trace every ", V("run.sample_interval_s"), ", GNSS every ", V("cad.gnss_period_s"), ", altimeter and IMU every ", V("case.control_period_s"));
  const note = V("run.verdict_note");
  note.firstChild.textContent = "host note";
  note.dataset.display = "label";
  mk("Verdicts", "computed per step by the host, ", note);
  const hb = V("run.hash.source");
  hb.firstChild.textContent = String(model.value("run.hash.source", 0)).slice(0, 10) + "...";
  hb.dataset.display = "label";
  mk("Run source hash", hb, " is ", wordBtn("equal", "prov.hash_matches"), " to the current tree's (see Provenance)");
}

function renderClassList() {
  const dl = $("#class-list");
  for (const [k, v] of Object.entries(model.data.classes)) dl.append(h("dt", null, tagEl(k)), h("dd", null, v));
}

function renderEventList() {
  const ul = $("#event-list");
  for (const ev of model.data.events) {
    const li = h("li");
    const b = h("button", "ev-btn", ev.label);
    b.type = "button";
    b.dataset.jump = String(ev.nav_index);
    li.append(b, " at ", V(ev.t));
    if (ev.on_sample_tick) li.append(", on a recorded sample");
    else li.append(", between the recorded samples at ", V("t_s", { i: ev.between[0], tag: false }), " and ", V("t_s", { i: ev.between[1], tag: false }));
    ul.appendChild(li);
  }
}

function renderDecisions() {
  const dl = $("#decision-list");
  const item = (title, ...nodes) => dl.append(h("dt", null, title), h("dd", null, ...nodes));
  item(
    "Ignition",
    "Engine ignition recorded (truth event) at ", V("run.ignition_t_s"), "; the event detail records command step ", V("run.ignition_command_t_s"),
    " as its command time. First recorded sample with the engine on: ", V("ign.first_engine_on_t"), "; first recorded sample with a throttle command above zero: ", V("ign.first_command_t"),
    ". Ignition comes ", wordBtn("before", "check.ignition_before_fault"), " the fault starts at ", V("case.fault_start_s"),
    ". Rule (source code): light the engine when descending faster than the target and the needed deceleration reaches ", V("case.ignition_fraction", { nounit: true }),
    " of the available thrust-to-mass ", factButton("S_ignition_rule"), ".",
  );
  item(
    "Commands",
    "Throttle and gimbal commands are recorded every sample (class K). They are in the readout at the cursor. ",
    "The recorded flags show no ascent abort at any sample: ", V("check.no_ascent_abort_flag", { nounit: true }), ".",
  );
  item(
    "No cutoff, abort or relight",
    "Engine cutoff: ", V("run.cutoff_t_s"), ". Flameout: ", V("run.flameout_t_s"), ". Ascent abort first flagged: ", V("run.ascent_abort_first"),
    ". Ignitions (S4 worst value): ", V("inv.S4_no_relight.worst_value", { nounit: true }), ".",
  );
  item(
    "Detection: one condition",
    "The altimeter rejection and the sensor disagreement flags are the same condition ", factButton("S_detection_same"),
    ": first flagged at ", V("run.reject_first_t_s"), " (step ", V("run.reject_first_step", { tag: false }), "); identical at every sample: ", V("check.detection_flags_identical", { nounit: true }), ".",
  );
  item(
    "What the rejection does",
    "Source code, not recorded: from the first control cycle whose residual exceeds the threshold the altimeter is no longer fused into the estimate, which starts before the flag; ",
    "after the flag (", V("case.altimeter_rejection_cycles", { nounit: true }), " consecutive cycles) guarded guidance also reads the lower of the estimated nozzle altitude and the altimeter ",
    factButton("S_rejection_not_fused"), " ", factButton("S_guidance_min", "guidance rule"), ".",
  );
  item(
    "Could the controller tell which sensor was wrong?",
    "By the implemented logic, no: its only test is the residual between the altimeter and its own estimate. This is a statement about the code, not a grade with hindsight. ",
    "For reference, the truth shows the altimeter at ", V("err_altimeter", { i: model.data.index.last_periodic }), " from the true nozzle altitude and GNSS z at ",
    V("err_gnss_z", { i: model.data.index.last_periodic }), " from the true z at the last periodic sample; the controller does not have the truth.",
  );
  item(
    "Sensor cadence",
    "The controller runs every ", V("case.control_period_s"), " and observes the altimeter and the IMU each time. GNSS delivers one fix every ", V("cad.gnss_period_s"),
    " (every ", V("case.gnss_period_cycles", { nounit: true }), " control cycles) ", factButton("S_cadence"), ". The trace stores a sample every ", V("run.sample_interval_s"),
    ", so ", V("gnss.fix_samples", { nounit: true }), " samples carry a fix and ", V("gnss.no_fix_samples", { nounit: true }),
    " does not: the off-grid touchdown sample, whose control cycle had no fix (", V("check.no_fix_only_at_touchdown", { nounit: true }), ").",
  );
}

function renderDivergence() {
  const root = $("#div-body");
  const first = model.data.index.fault_first_sample;
  const pre = model.data.index.pre_fault_last;
  const t = h("table", "rt wide");
  t.append(h("caption", null, "Estimate error around the fault start, recorded samples"));
  const head = h("tr");
  for (const c of ["Sample", "t", "Horizontal error (host)", "x error (view)"]) head.append(h("th", null, c));
  t.append(h("thead", null, head));
  const tb = h("tbody");
  for (const i of [pre, first]) {
    const tr = h("tr");
    tr.append(h("th", null, i === first ? "first with the fault active" : "last before the fault"), h("td", null, V("t_s", { i })), h("td", null, V("err_h_host", { i })), h("td", null, V("err_est_x", { i })));
    tb.append(tr);
  }
  t.append(tb);
  root.append(t);
  root.append(h("p", "fig-note", "The fault starts at ", V("run.fault_start_event_t_s"), ", a recorded event. The error at the ", V("t_s", { i: first }), " sample is the state after the fault took effect in that control cycle, not a gradual rise. ",
    "One GNSS fix that carries the bias moves the estimate by gain times bias, ", V("lane.expected_first_fix_jump_m"), " (inference from the fixed gain, ", factButton("S_estimator_fixed_gain"), ")."));
  const ctl = h("div", "div-controls");
  const sel = h("select");
  sel.id = "div-th";
  sel.dataset.layout = "1";
  for (const th of model.data.divergence.thresholds) {
    const o = h("option", null, `${th} m`);
    o.value = String(th);
    if (String(th) === state.divTh) o.selected = true;
    sel.append(o);
  }
  const lab = h("label", null, "Threshold ", sel);
  const msel = h("select");
  msel.id = "div-metric";
  model.data.divergence.metrics.forEach((m, k) => {
    const o = h("option", null, k === 0 ? "horizontal error" : "vertical error");
    o.value = String(k);
    msel.append(o);
  });
  const mlab = h("label", null, "Quantity ", msel);
  ctl.append(lab, mlab);
  root.append(ctl);
  const out = h("p", "div-out");
  out.id = "div-out";
  out.setAttribute("aria-live", "polite");
  root.append(out);
  const draw = () => {
    state.divTh = sel.value;
    state.divMetric = Number(msel.value);
    const m = model.data.divergence.metrics[state.divMetric];
    const sid = m.scalars[state.divTh];
    const e = model.scalar(sid);
    out.textContent = "";
    if (e.v === null) {
      out.append("No recorded sample is above this threshold.");
      return;
    }
    const at = e.derivation.at_index;
    const jump = h("button", "link", "Show this sample");
    jump.type = "button";
    jump.dataset.row = String(at);
    out.append("First recorded sample above the threshold: t = ", V(sid), ", with the error ", V(m.series, { i: at }), ". ", jump, " The sample is recorded; the true crossing lies between it and the one before.");
  };
  sel.addEventListener("change", draw);
  msel.addEventListener("change", draw);
  draw();
}

function renderInitial() {
  const root = $("#init-body");
  const t = h("table", "rt wide");
  t.append(h("caption", null, "Initial state: nominal, dispersed by the seed, and the dispersion half-width"));
  const head = h("tr");
  for (const c of ["", "Nominal (case file)", "Dispersed (this run)", "Half-width (case file)"]) head.append(h("th", null, c));
  t.append(h("thead", null, head));
  const tb = h("tbody");
  for (const [kind, label] of [["p", "Position"], ["v", "Velocity"]]) {
    for (const ax of "xyz") {
      const tr = h("tr");
      tr.append(h("th", null, `${label} ${ax}`), h("td", null, V(`init.nominal_${kind}${ax}`)), h("td", null, V(`init.disp_${kind}${ax}`)), h("td", null, V(`init.range_${kind}${ax}`)));
      tb.append(tr);
    }
  }
  t.append(tb);
  root.append(t);
  root.append(h("p", null, "The fault ", V("run.fault_kind", { tag: false }), " of ", V("case.fault_magnitude_m"), " is configured from ", V("case.fault_start_s"), " to ", V("case.fault_end_s"),
    "; the run ended at touchdown, ", V("run.touchdown_t_s"), ", so the fault was ", wordBtn("until_end", "fault.active_at_last_sample"), " (the last sample's recorded active faults)."));
}

function reqRowButtons(r) {
  const td = h("td");
  const b = h("button", "mini", "At touchdown");
  b.type = "button";
  b.dataset.action = "touchdown";
  td.append(b);
  if (r.short === "R5") {
    const p = h("button", "mini", "On the pad plan");
    p.type = "button";
    p.dataset.action = "plan";
    td.append(" ", p);
  }
  return td;
}

function passCell(sid) {
  const td = h("td");
  const ok = model.scalar(sid).v;
  const b = V(sid, { tag: false });
  b.firstChild.textContent = word("verdict", ok);
  b.dataset.display = "label";
  b.classList.add(ok ? "is-pass" : "is-fail");
  b.prepend(h("span", "glyph", ok ? "✓ " : "✗ "));
  td.appendChild(b);
  return td;
}

function renderVerdicts() {
  const rt = $("#req-table");
  rt.insertAdjacentHTML("beforeend", "<thead><tr><th scope='col'>Id</th><th scope='col'>Requirement</th><th scope='col'>Value</th><th scope='col'>Limit</th><th scope='col'>Verdict</th><th scope='col'>Judged at</th><th scope='col'>Faults active (not attribution)</th><th scope='col'>Show</th></tr></thead>");
  const tb = h("tbody");
  for (const r of model.data.requirements) {
    const f = r.fields;
    const tr = h("tr");
    const lim = h("td");
    const op = model.scalar(f.expected).v.match(/^[<>]=?/);
    lim.append(op ? op[0] : "", " ", V(f.limit, { tag: false }));
    const ref = h("td");
    if (r.reference) {
      ref.append(r.reference.text, " ", V(r.reference.check, { tag: false, nounit: true }), " ", factButton("S_requirements_nozzle", "source"));
    }
    tr.append(h("th", null, r.short), h("td", null, model.scalar(r.label).v), h("td", null, V(f.value, { tag: false })), lim, passCell(f.pass), ref, h("td", null, V(f.cause, { nounit: true, tag: false })), reqRowButtons(r));
    if (!model.scalar(f.pass).v) tr.classList.add("row-fail");
    tb.append(tr);
  }
  rt.append(tb);

  const note = $("#req-notes");
  note.append(
    h("p", "fig-note", "R2 judges the nozzle-plane horizontal speed at contact, ", V("req.R2_horizontal_speed.value", { tag: true }),
      ". The centre of mass moves at ", V("td.cm_horizontal_speed"), ". The ", V("td.nozzle_minus_cm_speed"), " difference is about the angular rate times the lever arm, ",
      V("td.angular_rate_times_lever"), ": the nozzle plane sits below the rotating body's centre of mass."),
    h("p", "fig-note", "R6 limit: the margin fraction ", V("case.r6_margin_fraction", { nounit: true }), " of the initial propellant ", V("init.propellant_kg"), " is ", V("req.R6_propellant_margin.limit"),
      " (", V("check.r6_limit_is_fraction_of_initial", { nounit: true }), "); the value is the propellant left at touchdown, ", V("req.R6_propellant_margin.value"), ". The record's own words: ", V("req.R6.explanation", { nounit: true }), "."),
  );

  const it = $("#inv-table");
  it.insertAdjacentHTML("beforeend", "<thead><tr><th scope='col'>Id</th><th scope='col'>Invariant</th><th scope='col'>Worst value</th><th scope='col'>Limit</th><th scope='col'>Verdict</th><th scope='col'>First failure</th></tr></thead>");
  const tb2 = h("tbody");
  for (const r of model.data.invariants) {
    const f = r.fields;
    const tr = h("tr");
    tr.append(h("th", null, r.short), h("td", null, model.scalar(r.label).v), h("td", null, V(f.worst_value, { tag: false })), h("td", null, r.bound === "lower" ? "≥ " : "≤ ", V(f.limit, { tag: false })), passCell(f.pass), h("td", null, V(f.first_failure, { nounit: true, tag: false })));
    tb2.append(tr);
  }
  it.append(tb2);
  $("#inv-note").append(
    "Invariants keep a worst value and a first failure and have no recorded time, so none is drawn on the time axis. They are separate from the mission requirements. S2 is evaluated at contact, and its worst value equals the R5 value: ",
    V("check.s2_equals_r5", { nounit: true }), " ", factButton("S_invariant_limits"), ".",
  );

  const out = $("#outcome");
  const failing = model.data.requirements.filter((r) => !model.scalar(r.fields.pass).v);
  out.append(
    h("p", null, "Outcome label: ", V("run.outcome_label", { nounit: true }), " (code ", V("run.outcome_code", { tag: false }), ")."),
    h("p", null, "The code is assigned when contact happened and the requirements, or S5, are not all satisfied ", factButton("S_outcome_rule"), ". It does not say the impact was hard. Requirements with a negative verdict in this run: ",
      failing.length ? failing.map((r) => r.short).join(", ") : "none", ". The R1 verdict, vertical speed at contact ",
      V("req.R1_vertical_speed.value", { tag: false }), " against a limit of ", V("req.R1_vertical_speed.limit", { tag: false }), ", is ", wordBtn("verdict", "req.R1_vertical_speed.pass", { tag: false }), "."),
  );
}

function renderProvenance() {
  const root = $("#prov-body");
  root.append(h("p", "u-box", h("strong", null, "Verdicts shown are stored, not recomputed by this view; the build that wrote the run is " + (model.scalar("prov.hash_matches").v ? "" : "not ") + "the current tree.")));
  const dl = h("dl", "facts");
  const item = (title, ...nodes) => dl.append(h("dt", null, title), h("dd", null, ...nodes));
  const hashB = (ref) => {
    const b = V(ref);
    b.firstChild.textContent = String(model.value(ref, 0)).slice(0, 12) + "...";
    b.dataset.display = "label";
    return b;
  };
  item("Recorded source hash", "The run declares the hash of the simulator sources that wrote it: ", hashB("run.hash.source"), ".");
  item(
    "Run file hashes",
    "Declared by run.json for the files of this run: case ", hashB("run.hash.case"), ", trace ", hashB("run.hash.trace"), ", verification ", hashB("run.hash.verification"),
    ". They match the files and the record's own list (checked by the extractor and the tests).",
  );
  item("Current tree", "The same algorithm over this tree gives ", hashB("prov.current_sha"), ": ", wordBtn("equal", "prov.hash_matches"), " to the recorded one.");
  item(
    "What differs",
    "Hashed sources that differ from the recording tree: ", V("prov.differing_files", { nounit: true }), ". The tree at commit ", V("prov.recording_commit", { nounit: true }),
    " reproduces the recorded hash (proved by the test with git; it reproduces the hash, it is not a claim that it built the run). ",
    "Every simulator source cited by this view is identical to that tree: ", V("prov.cited_sources_identical", { nounit: true }), ".",
  );
  item(
    "The version string is not enough",
    "The run records domain version ", V("run.version"), " and the current tree reports ", V("prov.current_domain_version"), ". The version alone does not identify the build: the stored request has ",
    V("prov.stored_parameters", { nounit: true }), " parameters, fewer than the current catalogue, and the simulator sources differ as above.",
  );
  item(
    "Replay under the current host",
    "The strict replay is rejected for this run, because the stored request is not canonical under the current catalogue. The earlier-build replay re-simulates with current defaults and agrees on the compared fields (outcome, safety, requirement verdicts, telemetry channels, events, metrics); texts, the scene and the native files are not compared ",
    factButton("S_replay_host_sdk"), ". The test that asserts both ", factButton("S_earlier_build_test", "test"), " was run for this iteration; its result line: ", V("prov.earlier_build_result", { nounit: true }), ".",
  );
  root.append(dl);
}

// ---------------------------------------------------------------------------------------------
// Readout at the cursor

function row(label, cls, cells, approx = false) {
  const tr = h("tr");
  const th = h("th", null, label, " ");
  th.scope = "row";
  if (cls) th.append(tagEl(cls));
  if (approx) th.append(approxEl());
  tr.append(th);
  for (const c of cells) tr.append(h("td", null, c));
  return tr;
}

function table(caption, headers) {
  const t = h("table", "rt");
  t.append(h("caption", null, caption));
  if (headers) {
    const tr = h("tr");
    for (const x of ["", ...headers]) {
      const th = h("th", null, x);
      th.scope = "col";
      tr.append(th);
    }
    t.append(h("thead", null, tr));
  }
  return t;
}

function renderReadout() {
  const i = state.cursor;
  const body = $("#readout-body");
  body.textContent = "";
  const v = (id, o = {}) => V(id, { i, tag: false, nounit: true, ...o });
  const vt = (id) => V(id, { i, tag: true, nounit: true });
  const kind = model.value("kind", i);
  body.append(h("p", "ro-head", "t = ", V("t_s", { i, digits: 3 }), ", step ", V("step", { i, tag: false }), kind === "touchdown" ? ", touchdown sample, off the grid" : ", recorded sample"));
  if (kind === "touchdown") {
    body.append(h("p", "fig-note", "Truth is the host's interpolated contact state. The estimate and the observations are those of the last control cycle before contact; that cycle delivered no GNSS fix."));
  }
  if (i === model.data.index.fault_first_sample) {
    body.append(h("p", "fig-note", "First sample with the fault active. The x error here, ", V("err_est_x", { i }), ", is the state after the fault took effect in this control cycle, not a gradual rise."));
  }
  const pos = table("Centre-of-mass position, metres", ["x", "y", "z"]);
  pos.append(
    row("Truth", model.cls("truth_x", i), ["truth_x", "truth_y", "truth_z"].map((s) => v(s))),
    row("Estimate", "E", ["est_x", "est_y", "est_z"].map((s) => v(s))),
    row("GNSS", "O", ["gnss_x", "gnss_y", "gnss_z"].map((s) => v(s))),
    row("Estimate − truth", null, [vt("err_est_x"), vt("err_est_y"), vt("err_z_host")]),
    row("GNSS − truth", null, ["err_gnss_x", "err_gnss_y", "err_gnss_z"].map((s) => vt(s))),
  );
  const vel = table("Centre-of-mass velocity, metres per second", ["x", "y", "z"]);
  vel.append(
    row("Truth", model.cls("truth_vx", i), ["truth_vx", "truth_vy", "truth_vz"].map((s) => v(s))),
    row("Estimate", "E", ["est_vx", "est_vy", "est_vz"].map((s) => v(s))),
    row("GNSS velocity", "O", ["gnss_vx", "gnss_vy", "gnss_vz"].map((s) => v(s))),
    row("Host error, vertical and horizontal", "D-host", [v("err_vz_host"), v("err_vh_host"), null]),
  );
  const noz = table("Nozzle plane, vertical, metres");
  noz.append(
    row("True nozzle altitude", model.cls("base_z", i), [v("base_z")]),
    row("Altimeter", "O", [v("altimeter")]),
    row("Altimeter − true nozzle altitude", null, [vt("err_altimeter")]),
    row("Estimated nozzle altitude", "D-view", [v("est_nozzle_alt")], true),
    row("Altimeter − estimated", "D-view", [v("alt_residual")], true),
  );
  const flags = table("Flags, rule and commands");
  flags.append(
    row("Altimeter rejected (one detection)", "E", [v("alt_rejected")]),
    row("Guidance altitude rule", "S", [v("guidance_rule")]),
    row("Lower altitude", "D-view", [v("lower_source")], true),
    row("Throttle command", "K", [v("cmd_throttle")]),
    row("Gimbal command y, z (tangent)", "K", [h("span", null, v("cmd_gimbal_y"), " ", v("cmd_gimbal_z"))]),
    row("Engine (applied)", "T", [v("engine")]),
  );
  const pad = table("Distance of the nozzle plane from the pad centre, metres");
  pad.append(row("True", "D-host", [v("pad_distance_host")]), row("Believed", "D-view", [v("believed_pad_distance")], true));
  body.append(pos, vel, noz, flags, pad);
}

// ---------------------------------------------------------------------------------------------
// Charts

function glyph(kind, cls) {
  const NSs = "http://www.w3.org/2000/svg";
  const s = document.createElementNS(NSs, "svg");
  s.setAttribute("width", "34");
  s.setAttribute("height", "14");
  s.setAttribute("viewBox", "0 0 34 14");
  s.setAttribute("aria-hidden", "true");
  const mk = (tag, a) => {
    const e = document.createElementNS(NSs, tag);
    for (const [k, vv] of Object.entries(a)) e.setAttribute(k, vv);
    s.appendChild(e);
    return e;
  };
  if (kind === "marker-line") {
    mk("line", { x1: 2, y1: 7, x2: 32, y2: 7, class: "connector" });
    mk("rect", { x: 5, y: 4.5, width: 5, height: 5, class: cls });
    mk("rect", { x: 14.5, y: 4.5, width: 5, height: 5, class: cls });
    mk("rect", { x: 24, y: 4.5, width: 5, height: 5, class: cls });
  } else if (kind === "marker-line-diamond") {
    mk("line", { x1: 2, y1: 7, x2: 32, y2: 7, class: "connector" });
    mk("polygon", { points: "17,3 21,7 17,11 13,7", class: cls });
  } else if (kind === "connector") mk("line", { x1: 2, y1: 7, x2: 32, y2: 7, class: "connector" });
  else if (kind === "line") mk("line", { x1: 2, y1: 7, x2: 32, y2: 7, class: cls });
  else if (kind === "bar") mk("rect", { x: 3, y: 4, width: 28, height: 6, class: cls });
  else if (kind === "circle") mk("circle", { cx: 17, cy: 7, r: 3, class: cls });
  else if (kind === "triangle") mk("polygon", { points: "17,3 21,11 13,11", class: cls });
  else if (kind === "diamond") mk("polygon", { points: "17,3 21,7 17,11 13,7", class: cls });
  else if (kind === "square") mk("rect", { x: 14, y: 4, width: 6, height: 6, class: cls });
  else mk("line", { x1: 2, y1: 7, x2: 32, y2: 7, class: cls });
  return s;
}

function legendItem(ul, kind, cls, ref, label) {
  const li = h("li", null, glyph(kind, cls));
  const b = h("button", "leg-btn", label, " ", tagEl(model.entry(ref).cls));
  if (model.approx(ref)) b.append(approxEl());
  b.type = "button";
  b.dataset.ref = ref;
  b.dataset.legend = "1";
  li.appendChild(b);
  ul.appendChild(li);
}

function legendPlain(ul, kind, cls, label) {
  ul.appendChild(h("li", null, glyph(kind, cls), h("span", null, label)));
}

function buildLegends() {
  const connector = (ul) => legendPlain(ul, "connector", "connector", "connector between recorded samples, not data");
  legendItem($("#leg-x"), "marker-line", "ln-est", "err_est_x", "Estimate − truth, recorded sample");
  legendItem($("#leg-x"), "circle", "pt-gnss", "err_gnss_x", "GNSS − truth");
  connector($("#leg-x"));
  legendItem($("#leg-y"), "marker-line", "ln-est", "err_est_y", "Estimate − truth, recorded sample");
  legendItem($("#leg-y"), "circle", "pt-gnss", "err_gnss_y", "GNSS − truth");
  connector($("#leg-y"));
  legendItem($("#leg-z"), "marker-line", "ln-est", "err_z_host", "Estimate − truth (host metric)");
  legendItem($("#leg-z"), "circle", "pt-gnss", "err_gnss_z", "GNSS − truth");
  legendItem($("#leg-z"), "triangle", "pt-alt", "err_altimeter", "Altimeter − true nozzle altitude");
  connector($("#leg-z"));
  legendItem($("#leg-v"), "marker-line", "ln-est", "err_vz_host", "Vertical velocity error");
  legendItem($("#leg-v"), "marker-line-diamond", "mk-vh", "err_vh_host", "Horizontal velocity error");
  legendItem($("#leg-v"), "circle", "pt-gnss", "err_gnss_vz", "GNSS vertical velocity \u2212 truth");
  connector($("#leg-v"));
  legendItem($("#leg-d"), "marker-line", "mk-true", "pad_distance_host", "True distance");
  legendItem($("#leg-d"), "marker-line-diamond", "mk-bel", "believed_pad_distance", "Believed distance");
  const ld = $("#leg-d");
  const r5 = h("li", null, glyph("line", "band-r5"), V("case.r5_radius_m"), " R5 radius");
  ld.append(r5);
  const bar = (cls, key, label) => {
    const li = h("li", null, glyph("bar", cls), `${label} within R5 from `);
    li.append(V(`win.${key}.first_t`), " to ", V(`win.${key}.last_t`));
    ld.append(li);
  };
  bar("span-true", "true", "true");
  bar("span-bel", "believed", "believed");
  connector(ld);
  legendItem($("#leg-a"), "marker-line", "mk-true", "base_z", "True nozzle altitude");
  legendItem($("#leg-r"), "diamond", "pt-res", "alt_residual", "Altimeter − estimated nozzle altitude");
  const thr = h("li", null, glyph("line", "band-thr"), "± ", V("case.altimeter_threshold_m"), " rejection threshold, held for ", V("case.altimeter_rejection_cycles", { nounit: true }), " consecutive cycles");
  $("#leg-r").appendChild(thr);
  const lane = $("#leg-l");
  legendItem(lane, "square", "lane-est-key", "guidance_rule", "Rule active (from the recorded flag)");
  legendItem(lane, "triangle", "pt-alt", "lower_source", "Altimeter lower");
  legendItem(lane, "circle", "pt-est-lane", "lower_source", "Estimator lower");
  const lp = $("#leg-plan");
  legendItem(lp, "circle", "plan-truth", "td.true_nozzle_x", "True nozzle plane at touchdown");
  legendItem(lp, "diamond", "plan-belief", "td.believed_nozzle_x", "Last estimate before contact, at the nozzle plane");
  legendItem(lp, "square", "plan-cur-gnss", "gnss_x", "GNSS (centre of mass)");
  legendPlain(lp, "connector", "connector", "track: recorded samples with a thin connector");
}

function widthOf(node) {
  return Math.max(300, Math.floor(node.getBoundingClientRect().width || node.parentElement.clientWidth));
}

function planHalf() {
  return state.plan === "window" ? 20 : trackHalf;
}

function renderAll() {
  const w = widthOf($("#strips"));
  const common = { model, width: w, t0: state.t0, t1: state.t1, cursor: state.cursor };
  const brk = model.data.index.fault_first_sample; // no connector across the fault start
  drawTimeAxis($("#axis"), { ...common, width: widthOf($("#slider")) });
  drawStrip($("#svg-x"), { ...common, height: 190, layers: [
    { series: "err_est_x", kind: "line", cls: "ln-est", breakBefore: brk },
    { series: "err_gnss_x", kind: "points", cls: "pt-gnss", shape: "circle" },
  ] });
  drawStrip($("#svg-y"), { ...common, height: 120, layers: [
    { series: "err_est_y", kind: "line", cls: "ln-est", breakBefore: brk },
    { series: "err_gnss_y", kind: "points", cls: "pt-gnss", shape: "circle" },
  ] });
  drawStrip($("#svg-z"), { ...common, height: 190, layers: [
    { series: "err_z_host", kind: "line", cls: "ln-est", breakBefore: brk },
    { series: "err_gnss_z", kind: "points", cls: "pt-gnss", shape: "circle" },
    { series: "err_altimeter", kind: "points", cls: "pt-alt", shape: "triangle" },
  ] });
  drawStrip($("#svg-v"), { ...common, height: 150, layers: [
    { series: "err_vz_host", kind: "line", cls: "ln-est", breakBefore: brk },
    { series: "err_vh_host", kind: "line", cls: "mk-vh", shape: "diamond", breakBefore: brk },
    { series: "err_gnss_vz", kind: "points", cls: "pt-gnss", shape: "circle" },
  ] });
  const r5 = model.scalar("case.r5_radius_m").v;
  const win = (key, cls) => ({ t0: model.scalar(`win.${key}.first_t`).v, t1: model.scalar(`win.${key}.last_t`).v, cls });
  drawStrip($("#svg-d"), { ...common, height: 190, zero: false, extras: [0], bands: [{ y: r5, cls: "band-r5" }], spans: [win("true", "span-true"), win("believed", "span-bel")], layers: [
    { series: "pad_distance_host", kind: "line", cls: "mk-true" },
    { series: "believed_pad_distance", kind: "line", cls: "mk-bel", shape: "diamond" },
  ] });
  drawStrip($("#svg-a"), { ...common, height: 110, zero: false, extras: [0], layers: [{ series: "base_z", kind: "line", cls: "mk-true" }] });
  const thr = model.scalar("case.altimeter_threshold_m").v;
  drawStrip($("#svg-r"), { ...common, height: 190, bands: [{ y: thr, cls: "band-thr" }, { y: -thr, cls: "band-thr" }], layers: [
    { series: "alt_residual", kind: "points", cls: "pt-res", shape: "diamond" },
  ] });
  drawLane($("#svg-l"), common);
  const half = planHalf();
  const plan = drawPlan($("#svg-plan"), { model, size: Math.min(widthOf($("#plan")), 420), half, cursor: state.cursor });
  $("#plan-extent").textContent = `±${half} m`;
  $("#plan-off").textContent = plan.shown.truth ? "" : "At the cursor the true nozzle plane is outside this window.";
  renderReadout();
  updateSlider();
}

function updateSlider() {
  const s = $("#slider");
  s.setAttribute("aria-valuemin", "0");
  s.setAttribute("aria-valuemax", String(model.last));
  s.setAttribute("aria-valuenow", String(state.cursor));
  const t = model.text("t_s", state.cursor, 3);
  const where = state.cursor === 0 ? ", start of the run" : state.cursor === model.last ? ", touchdown sample, off the grid" : "";
  s.setAttribute("aria-valuetext", `sample index ${state.cursor} (last index ${model.last}), t = ${t} s${where}`);
  $("#cursor-status").textContent = `Cursor at recorded sample index ${state.cursor} (last index ${model.last}, ${model.n} samples): t = ${t} s${where}.`;
}

// ---------------------------------------------------------------------------------------------
// State changes

function setCursor(i, { keepWindow = false } = {}) {
  state.cursor = model.clampIndex(i);
  const t = model.t[state.cursor];
  if (!keepWindow && (t < state.t0 || t > state.t1)) {
    const span = state.t1 - state.t0;
    let a = t - span / 2;
    let b = t + span / 2;
    if (a < 0) [a, b] = [0, span];
    state.t0 = a;
    state.t1 = b;
  }
  renderAll();
}

function setZoom(kind) {
  const tEnd = model.t[model.last];
  const fault = model.scalar("case.fault_start_s").v;
  const t = model.t[state.cursor];
  state.zoom = kind;
  if (kind === "full") [state.t0, state.t1] = [0, tEnd + 0.3];
  else if (kind === "fault") [state.t0, state.t1] = [fault - 0.4, fault + 1.1];
  else if (kind === "touchdown") [state.t0, state.t1] = [tEnd - 3, tEnd + 0.15];
  else if (kind === "cursor") [state.t0, state.t1] = [Math.max(0, t - 1), Math.max(0, t - 1) + 2];
  const tc = model.t[state.cursor];
  if (tc < state.t0 || tc > state.t1) {
    const inside = model.t.map((x, k) => [x, k]).filter(([x]) => x >= state.t0 && x <= state.t1);
    const mid = (state.t0 + state.t1) / 2;
    state.cursor = inside.reduce((b, c) => (Math.abs(c[0] - mid) < Math.abs(b[0] - mid) ? c : b), inside[0])[1];
  }
  for (const b of $$("[data-zoom]")) b.setAttribute("aria-pressed", String(b.dataset.zoom === kind));
  renderAll();
}

function setPlan(mode) {
  state.plan = mode;
  for (const b of $$("[data-plan]")) b.setAttribute("aria-pressed", String(b.dataset.plan === mode));
  renderAll();
}

function onKey(e) {
  let i = state.cursor;
  const big = e.shiftKey ? 10 : 1;
  if (e.key === "ArrowRight" || e.key === "ArrowUp") i += big;
  else if (e.key === "ArrowLeft" || e.key === "ArrowDown") i -= big;
  else if (e.key === "Home") i = 0;
  else if (e.key === "End") i = model.last;
  else if (e.key === "PageDown") i = model.eventJump(i, 1);
  else if (e.key === "PageUp") i = model.eventJump(i, -1);
  else return;
  e.preventDefault();
  setCursor(i);
}

function pointerToSample(svg, ev) {
  const rect = svg.getBoundingClientRect();
  const t = timeAt(rect.width, state.t0, state.t1, ev.clientX - rect.left);
  return model.nearestSample(Math.max(state.t0, Math.min(state.t1, t)));
}

function wirePointer() {
  let pending = null;
  let frame = 0;
  const schedule = (i) => {
    pending = i;
    if (frame) return;
    frame = requestAnimationFrame(() => {
      frame = 0;
      if (pending !== null) setCursor(pending, { keepWindow: true });
      pending = null;
    });
  };
  for (const id of ["axis", "svg-x", "svg-y", "svg-z", "svg-v", "svg-d", "svg-a", "svg-r", "svg-l"]) {
    const svg = $("#" + id);
    let down = false;
    svg.addEventListener("pointerdown", (ev) => {
      down = true;
      svg.setPointerCapture(ev.pointerId);
      $("#slider").focus({ preventScroll: true });
      setCursor(pointerToSample(svg, ev), { keepWindow: true });
    });
    svg.addEventListener("pointermove", (ev) => {
      if (down) schedule(pointerToSample(svg, ev));
    });
    svg.addEventListener("pointerup", () => {
      down = false;
    });
    svg.addEventListener("pointercancel", () => {
      down = false;
    });
  }
}

function wireClicks() {
  document.addEventListener("click", (ev) => {
    const t = ev.target.closest("button");
    if (!t) return;
    if (t.matches(".leg-btn")) {
      openEvidence(t.dataset.ref, state.cursor, t);
    } else if (t.matches(".val, .cell")) {
      openEvidence(t.dataset.ref, Number(t.dataset.i || 0), t);
    } else if (t.dataset.fact) {
      openFact(t.dataset.fact, t);
    } else if (t.dataset.zoom) {
      setZoom(t.dataset.zoom);
    } else if (t.dataset.plan) {
      setPlan(t.dataset.plan);
    } else if (t.dataset.action === "touchdown") {
      setCursor(model.last);
    } else if (t.dataset.action === "plan") {
      setCursor(model.last);
      setPlan("window");
      const p = $("#plan");
      p.scrollIntoView({ block: "nearest" });
      p.focus({ preventScroll: true });
    } else if (t.classList.contains("ev-btn")) {
      setCursor(Number(t.dataset.jump));
    } else if (t.dataset.jump === "fault") {
      setZoom("fault");
      setCursor(model.data.index.fault_first_sample);
    } else if (t.dataset.row !== undefined) {
      setCursor(Number(t.dataset.row));
    }
  });
  $("#prev-event").addEventListener("click", () => setCursor(model.eventJump(state.cursor, -1)));
  $("#next-event").addEventListener("click", () => setCursor(model.eventJump(state.cursor, 1)));
  $("#to-touchdown").addEventListener("click", () => setCursor(model.last));
  $("#drawer-close").addEventListener("click", closeDrawer);
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && !$("#drawer").hidden) closeDrawer();
  });
  $("#slider").addEventListener("keydown", onKey);
}

// ---------------------------------------------------------------------------------------------
// Text alternative: a table of buttons with one tab stop and arrow-key movement

function renderSampleTable() {
  const t = $("#sample-table");
  const cols = [
    ["t_s", "t", 3], ["step", "step", 0], ["truth_x", "truth x", 2], ["est_x", "est x", 2], ["gnss_x", "GNSS x", 2], ["err_est_x", "est − truth x", 2],
    ["truth_z", "truth z", 2], ["est_z", "est z", 2], ["err_z_host", "est − truth z", 2], ["altimeter", "altimeter", 2],
    ["alt_residual", "residual, approx.", 2], ["alt_rejected", "rejected", undefined], ["guidance_rule", "guidance rule", undefined],
  ];
  const parts = ["<caption class='sr'>All recorded samples</caption><thead><tr><th scope='col'>Select</th>"];
  for (const [, hd] of cols) parts.push(`<th scope='col'>${hd}</th>`);
  parts.push("</tr></thead><tbody>");
  for (let i = 0; i < model.n; i++) {
    parts.push(`<tr><th scope='row'><button type='button' class='row-btn' data-row='${i}' data-layout='1' tabindex='-1'>sample ${i}</button></th>`);
    for (const [id, , d] of cols) {
      parts.push(`<td><button type='button' class='cell' data-ref='${id}' data-i='${i}' data-digits='${d === undefined ? "" : d}' tabindex='-1'>${model.text(id, i, d)}</button></td>`);
    }
    parts.push("</tr>");
  }
  parts.push("</tbody>");
  t.innerHTML = parts.join("");
  const first = $("button", t.tBodies[0]);
  first.tabIndex = 0;
  t.addEventListener("keydown", (ev) => {
    const b = ev.target.closest("button");
    if (!b) return;
    const cell = b.closest("th, td");
    const tr = cell.parentElement;
    const col = [...tr.children].indexOf(cell);
    let target = null;
    if (ev.key === "ArrowRight") target = tr.children[col + 1];
    else if (ev.key === "ArrowLeft") target = tr.children[col - 1];
    else if (ev.key === "ArrowDown") target = tr.nextElementSibling && tr.nextElementSibling.children[col];
    else if (ev.key === "ArrowUp") target = tr.previousElementSibling && tr.previousElementSibling.children[col];
    else return;
    const nb = target && $("button", target);
    if (!nb) return;
    ev.preventDefault();
    b.tabIndex = -1;
    nb.tabIndex = 0;
    nb.focus();
  });
}

// ---------------------------------------------------------------------------------------------

async function main() {
  model = await loadModel("data.json");
  let m = 0;
  for (const s of ["base_x", "base_y", "believed_nozzle_x", "believed_nozzle_y"]) for (const x of model.series(s).values) m = Math.max(m, Math.abs(x));
  trackHalf = Math.ceil(m / 20) * 20;
  fillPlaceholders();
  renderBar();
  renderClassList();
  renderEventList();
  renderDecisions();
  renderDivergence();
  renderInitial();
  renderVerdicts();
  renderProvenance();
  buildLegends();
  renderSampleTable();
  wireClicks();
  wirePointer();
  const params = new URLSearchParams(location.search);
  if (params.get("table") === "open") $("#table-alt").open = true;
  if (params.get("plan") === "track") state.plan = "track";
  for (const b of $$("[data-plan]")) b.setAttribute("aria-pressed", String(b.dataset.plan === state.plan));
  const start = params.get("sample");
  setZoom(params.get("zoom") || "full");
  setCursor(start === null ? 0 : Number(start), { keepWindow: true });
  let drawnWidth = widthOf($("#strips"));
  new ResizeObserver(() => {
    const w = widthOf($("#strips"));
    if (w === drawnWidth) return;
    drawnWidth = w;
    requestAnimationFrame(renderAll);
  }).observe($("#strips"));
  document.documentElement.dataset.ready = "1";
}

main().catch((e) => {
  document.body.insertAdjacentHTML("afterbegin", `<p role="alert" class="fatal">The view could not start: ${String(e.message || e)}. Serve this folder over HTTP (python -m http.server) so data.json can be fetched.</p>`);
  console.error(e);
});
