// Belief vs Truth, iteration 1: wiring. State is a cursor (a sample index) and a time window.

import { loadModel, MINUS } from "./model.js";
import { drawTimeAxis, drawStrip, drawLane, drawPlan, timeAt, ML, MR } from "./charts.js";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const clsKey = (c) => c.replace("-", "");

let model;
const state = { cursor: 0, t0: 0, t1: 1, zoom: "full" };
let lastTrigger = null;

// ---------------------------------------------------------------------------------------------
// Value buttons: the single way a number reaches the page. Each opens the evidence drawer.

function tagEl(cls) {
  const t = document.createElement("span");
  t.className = `tag tag-${clsKey(cls)}`;
  t.textContent = cls;
  t.title = model.data.classes[cls] || cls;
  return t;
}

function indexFrom(at) {
  if (at === undefined || at === null || at === "") return 0;
  if (/^\d+$/.test(at)) return Number(at);
  const k = model.data.index[at];
  if (k === undefined) throw new Error(`unknown index name ${at}`);
  return k;
}

/** Build a value button for a scalar id, or a series id at sample i. */
function V(ref, { i = 0, digits, unit, tag = true, nounit = false } = {}) {
  const cls = model.cls(ref, i);
  const b = document.createElement("button");
  b.type = "button";
  b.className = "val";
  b.dataset.ref = ref;
  b.dataset.i = String(i);
  const effective = digits === undefined ? model.digits(ref) : digits;
  b.dataset.digits = effective === undefined ? "" : String(effective);
  const txt = model.text(ref, i, digits);
  const num = document.createElement("span");
  num.className = "num";
  num.textContent = txt;
  b.appendChild(num);
  const u = unit !== undefined ? unit : model.entry(ref).unit;
  if (u && !nounit && typeof model.value(ref, i) === "number") {
    const us = document.createElement("span");
    us.className = "unit";
    us.textContent = ` ${u}`;
    b.appendChild(us);
  }
  if (tag) b.appendChild(tagEl(cls));
  b.setAttribute("aria-label", `${txt}${u && !nounit && typeof model.value(ref, i) === "number" ? " " + u : ""}, evidence class ${cls}. Open evidence.`);
  return b;
}

function fillPlaceholders(root = document) {
  for (const ph of $$("[data-v]", root)) {
    const ref = ph.dataset.v;
    const i = indexFrom(ph.dataset.at);
    const d = ph.dataset.digits === undefined ? undefined : Number(ph.dataset.digits);
    ph.replaceWith(V(ref, { i, digits: d }));
  }
}

// ---------------------------------------------------------------------------------------------
// Evidence drawer

function kv(dl, k, content) {
  const dt = document.createElement("dt");
  dt.textContent = k;
  const dd = document.createElement("dd");
  if (content instanceof Node) dd.appendChild(content);
  else dd.textContent = content;
  dl.append(dt, dd);
}

function code(s) {
  const c = document.createElement("code");
  c.textContent = s;
  return c;
}

function openEvidence(ref, i, trigger) {
  lastTrigger = trigger || document.activeElement;
  const e = model.entry(ref);
  const cls = model.cls(ref, i);
  const body = $("#drawer-body");
  body.textContent = "";
  $("#drawer-title").textContent = e.label || ref;
  const dl = document.createElement("dl");
  dl.className = "kv";
  const head = document.createElement("div");
  head.append(tagEl(cls), document.createTextNode(` ${model.data.classes[cls]}`));
  kv(dl, "Class", head);
  const valueLine = document.createElement("div");
  valueLine.append(code(model.raw(ref, i)));
  if (e.unit) valueLine.append(document.createTextNode(` ${e.unit}`));
  kv(dl, "Raw value", valueLine);
  if (model.isSeries(ref)) {
    kv(dl, "Sample", `index ${i}, step ${model.value("step", i)}, ${model.value("kind", i)} sample`);
    if (model.entry(ref).cls_by_index && model.entry(ref).cls_by_index[String(i)]) {
      kv(dl, "Class here", `Class ${cls} at this sample: the host interpolated the contact state (S_touchdown_sample).`);
    }
  }
  if (e.reference) kv(dl, "Reference point", e.reference);
  const ptr = model.pointer(ref, i);
  if (ptr) {
    const file = ptr.split("#")[0];
    kv(dl, "Record path", code(ptr));
    const inp = model.data.inputs[file];
    kv(dl, "File", `${inp.path}, sha256 ${inp.sha256.slice(0, 16)}...`);
    if (e.null_parent) kv(dl, "Null rule", "A null parent in the record (the whole sensor vector) gives a null value.");
  }
  if (e.derivation) {
    const d = model.data.derivations[e.derivation.name];
    kv(dl, "Derivation", code(e.derivation.name));
    kv(dl, "Formula", d.formula);
    kv(dl, "Approximate", d.approx ? "yes: uses a proxy or an unrecorded term" : "no");
    const ul = document.createElement("ul");
    ul.className = "inputs";
    for (const inpt of model.derivationInputs(ref, i)) {
      const li = document.createElement("li");
      const ie = model.entry(inpt.id);
      const where = inpt.index === null ? model.pointer(inpt.id, 0) : model.pointer(inpt.id, inpt.index);
      li.append(tagEl(model.cls(inpt.id, inpt.index ?? 0)), document.createTextNode(` ${ie.label}: `));
      li.append(code(model.raw(inpt.id, inpt.index ?? 0)));
      if (where) li.append(document.createTextNode(" at "), code(where));
      else li.append(document.createTextNode(` (derived: ${ie.derivation.name})`));
      ul.appendChild(li);
    }
    kv(dl, "Inputs", ul);
  }
  for (const f of e.source_facts || []) kv(dl, "Source code", factNode(f));
  if (e.note) kv(dl, "Note", e.note);
  body.appendChild(dl);
  showDrawer();
}

function factNode(id) {
  const f = model.data.source_facts[id];
  const wrap = document.createElement("div");
  wrap.append(code(`${f.file}:${f.lines[0]}-${f.lines[1]}`), document.createTextNode(` ${f.claim}`));
  return wrap;
}

function openFact(id, trigger) {
  lastTrigger = trigger || document.activeElement;
  const f = model.data.source_facts[id];
  $("#drawer-title").textContent = `Source code: ${id}`;
  const body = $("#drawer-body");
  body.textContent = "";
  const dl = document.createElement("dl");
  dl.className = "kv";
  const h = document.createElement("div");
  h.append(tagEl("S"), document.createTextNode(` ${model.data.classes.S}`));
  kv(dl, "Class", h);
  kv(dl, "File and lines", code(`${f.file}:${f.lines[0]}-${f.lines[1]}`));
  kv(dl, "Claim", f.claim);
  kv(dl, "Anchors checked", f.anchors.join("  |  "));
  kv(dl, "File sha256", `${model.data.source_files[f.file].slice(0, 16)}...`);
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

// ---------------------------------------------------------------------------------------------
// Evidence bar and static sections

function renderBar() {
  const chips = $("#chips");
  const mk = (label, nodes) => {
    const li = document.createElement("li");
    const l = document.createElement("span");
    l.className = "chip-l";
    l.textContent = label;
    li.append(l, ...nodes);
    chips.appendChild(li);
  };
  const sp = (s) => document.createTextNode(s);
  mk("Seed", [V("run.seed")]);
  mk("Policy", [V("run.policy")]);
  mk("Fault", [V("run.fault_kind"), sp(" on GNSS x and z, "), V("case.fault_magnitude_m"), sp(", from "), V("case.fault_start_s"), sp(" to "), V("case.fault_end_s")]);
  mk("Recorded by", [sp("rocket-landing host "), V("run.version")]);
  mk("Sampling", [V("run.sample_interval_s")]);
  const note = V("run.verdict_note");
  note.firstChild.textContent = "host note";
  note.dataset.display = "label";
  note.setAttribute("aria-label", "Host note on sampling and verdicts. Open evidence.");
  mk("Verdicts", [sp("computed per step by the host, "), note]);
  mk("Run hashes", [
    sp("source "), hashBtn("run.hash.source"),
    sp(" case "), hashBtn("run.hash.case"),
    sp(" trace "), hashBtn("run.hash.trace"),
    sp(" verification "), hashBtn("run.hash.verification"),
  ]);
}

function hashBtn(ref) {
  const b = V(ref);
  b.firstChild.textContent = String(model.value(ref, 0)).slice(0, 10) + "...";
  b.dataset.display = "label";
  return b;
}

function renderClassList() {
  const dl = $("#class-list");
  for (const [k, v] of Object.entries(model.data.classes)) {
    const dt = document.createElement("dt");
    dt.appendChild(tagEl(k));
    const dd = document.createElement("dd");
    dd.textContent = v;
    dl.append(dt, dd);
  }
}

function renderEventList() {
  const ul = $("#event-list");
  for (const ev of model.data.events) {
    const li = document.createElement("li");
    const b = document.createElement("button");
    b.type = "button";
    b.className = "ev-btn";
    b.dataset.jump = String(ev.nav_index);
    b.textContent = ev.label;
    li.append(b, document.createTextNode(" at "), V(ev.t));
    if (ev.on_sample_tick) li.append(document.createTextNode(", on a sample tick"));
    else {
      li.append(document.createTextNode(", between the samples at "), V("t_s", { i: ev.between[0], tag: false }), document.createTextNode(" and "), V("t_s", { i: ev.between[1], tag: false }));
    }
    ul.appendChild(li);
  }
}

function verdictCell(sid, opts = {}) {
  const td = document.createElement("td");
  td.appendChild(V(sid, { tag: false, ...opts }));
  return td;
}

function passCell(sid) {
  const td = document.createElement("td");
  const ok = model.scalar(sid).v;
  const b = V(sid, { tag: false });
  b.firstChild.textContent = ok ? "pass" : "FAIL";
  b.dataset.display = "label";
  b.classList.add(ok ? "is-pass" : "is-fail");
  const g = document.createElement("span");
  g.className = "glyph";
  g.setAttribute("aria-hidden", "true");
  g.textContent = ok ? "✓ " : "✗ ";
  b.prepend(g);
  td.appendChild(b);
  return td;
}

function renderVerdicts() {
  const rt = $("#req-table");
  rt.insertAdjacentHTML("beforeend", "<thead><tr><th scope='col'>Id</th><th scope='col'>Requirement</th><th scope='col'>Value</th><th scope='col'>Limit</th><th scope='col'>Verdict</th><th scope='col'>Faults active (not attribution)</th></tr></thead>");
  const tb = document.createElement("tbody");
  for (const r of model.data.requirements) {
    const tr = document.createElement("tr");
    const f = r.fields;
    const th = document.createElement("th");
    th.scope = "row";
    th.textContent = r.short;
    const lab = document.createElement("td");
    lab.textContent = model.scalar(r.label).v;
    const exp = V(f.limit, { tag: false });
    const limTd = document.createElement("td");
    limTd.append(model.scalar(f.expected).v.match(/^[<>]=?/)?.[0] ?? "", document.createTextNode(" "), exp);
    tr.append(th, lab, verdictCell(f.value), limTd, passCell(f.pass), verdictCell(f.cause, { nounit: true }));
    if (!model.scalar(f.pass).v) tr.classList.add("row-fail");
    tb.appendChild(tr);
  }
  rt.appendChild(tb);

  const it = $("#inv-table");
  it.insertAdjacentHTML("beforeend", "<thead><tr><th scope='col'>Id</th><th scope='col'>Invariant</th><th scope='col'>Worst value</th><th scope='col'>Limit</th><th scope='col'>Verdict</th><th scope='col'>First failure</th></tr></thead>");
  const tb2 = document.createElement("tbody");
  for (const r of model.data.invariants) {
    const f = r.fields;
    const tr = document.createElement("tr");
    const th = document.createElement("th");
    th.scope = "row";
    th.textContent = r.short;
    const lab = document.createElement("td");
    lab.textContent = model.scalar(r.label).v;
    const limTd = document.createElement("td");
    limTd.append(r.bound === "lower" ? "≥ " : "≤ ", V(f.limit, { tag: false }));
    tr.append(th, lab, verdictCell(f.worst_value), limTd, passCell(f.pass), verdictCell(f.first_failure, { nounit: true }));
    tb2.appendChild(tr);
  }
  it.appendChild(tb2);

  const out = $("#outcome");
  out.innerHTML = "";
  const p1 = document.createElement("p");
  p1.append("Outcome label: ", V("run.outcome_label", { nounit: true }), " (code ", V("run.outcome_code", { tag: false }), "). ");
  const p2 = document.createElement("p");
  p2.append(
    "The code is assigned when contact happened and any requirement failed, or S5 failed (",
    factButton("S_outcome_rule"),
    "). It does not say the impact was hard. Here only R5 failed. R1, the vertical speed at contact, was ",
    V("req.R1_vertical_speed.value", { tag: false }),
    " against a limit of ",
    V("req.R1_vertical_speed.limit", { tag: false }),
    " and passed.",
  );
  out.append(p1, p2);
}

function factButton(id) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "link";
  b.dataset.fact = id;
  b.textContent = "source";
  return b;
}

// ---------------------------------------------------------------------------------------------
// Readout at the cursor

function row(label, cls, cells) {
  const tr = document.createElement("tr");
  const th = document.createElement("th");
  th.scope = "row";
  th.append(label, document.createTextNode(" "));
  if (cls) th.appendChild(tagEl(cls));
  tr.appendChild(th);
  for (const c of cells) {
    const td = document.createElement("td");
    if (c) td.appendChild(c);
    tr.appendChild(td);
  }
  return tr;
}

function table(caption, headers) {
  const t = document.createElement("table");
  t.className = "rt";
  const c = document.createElement("caption");
  c.textContent = caption;
  t.appendChild(c);
  if (headers) {
    const tr = document.createElement("tr");
    for (const h of ["", ...headers]) {
      const th = document.createElement("th");
      th.scope = "col";
      th.textContent = h;
      tr.appendChild(th);
    }
    const thead = document.createElement("thead");
    thead.appendChild(tr);
    t.appendChild(thead);
  }
  return t;
}

function renderReadout() {
  const i = state.cursor;
  const body = $("#readout-body");
  body.textContent = "";
  const v = (id, o = {}) => V(id, { i, tag: false, ...o });
  const head = document.createElement("p");
  head.className = "ro-head";
  head.append("t = ", V("t_s", { i, digits: 3 }), document.createTextNode(", step "), V("step", { i, tag: false }), document.createTextNode(`, ${model.value("kind", i)} sample`));
  body.appendChild(head);
  if (model.value("kind", i) === "touchdown") {
    const n = document.createElement("p");
    n.className = "fig-note";
    n.textContent = "Off the sampling grid. Truth is the host's interpolated contact state. The estimate and the observations are those of the last control cycle before contact.";
    body.appendChild(n);
  }
  const pos = table("Centre-of-mass position, metres", ["x", "y", "z"]);
  pos.append(
    row("Truth", model.cls("truth_x", i), ["truth_x", "truth_y", "truth_z"].map((s) => v(s, { nounit: true }))),
    row("Estimate", "E", ["est_x", "est_y", "est_z"].map((s) => v(s, { nounit: true }))),
    row("GNSS", "O", ["gnss_x", "gnss_y", "gnss_z"].map((s) => v(s, { nounit: true }))),
    row("Estimate − truth", "D-view", [v("err_est_x", { nounit: true }), v("err_est_y", { nounit: true }), v("err_z_host", { nounit: true })]),
    row("GNSS − truth", "D-view", ["err_gnss_x", "err_gnss_y", "err_gnss_z"].map((s) => v(s, { nounit: true }))),
  );
  const note = document.createElement("p");
  note.className = "fig-note";
  note.append("In the estimate-minus-truth row, z is the host's own metric (D-host); x and y are derived by this view.");
  const noz = table("Nozzle plane, vertical, metres");
  noz.append(
    row("True nozzle altitude", model.cls("base_z", i), [v("base_z", { nounit: true })]),
    row("Altimeter", "O", [v("altimeter", { nounit: true })]),
    row("Altimeter − true nozzle altitude", "D-view", [v("err_altimeter", { nounit: true })]),
    row("Estimated nozzle altitude, approx.", "D-view", [v("est_nozzle_alt", { nounit: true })]),
    row("Altimeter − estimated, approx.", "D-view", [v("alt_residual", { nounit: true })]),
  );
  const flags = table("Flags and rule");
  flags.append(
    row("Altimeter rejected (estimator)", "E", [v("alt_rejected", { nounit: true })]),
    row("Guidance altitude rule", "S", [v("guidance_rule", { nounit: true })]),
    row("Lower altitude, approx.", "D-view", [v("lower_source", { nounit: true })]),
  );
  const pad = table("Distance of the nozzle plane from the pad centre, metres");
  pad.append(
    row("True", "D-host", [v("pad_distance_host", { nounit: true })]),
    row("Believed, approx.", "D-view", [v("believed_pad_distance", { nounit: true })]),
  );
  body.append(pos, note, noz, flags, pad);
}

// ---------------------------------------------------------------------------------------------
// Charts

function glyph(kind, cls) {
  const NSs = "http://www.w3.org/2000/svg";
  const s = document.createElementNS(NSs, "svg");
  s.setAttribute("width", "30");
  s.setAttribute("height", "14");
  s.setAttribute("viewBox", "0 0 30 14");
  s.setAttribute("aria-hidden", "true");
  const mk = (tag, a) => {
    const e = document.createElementNS(NSs, tag);
    for (const [k, vv] of Object.entries(a)) e.setAttribute(k, vv);
    s.appendChild(e);
    return e;
  };
  if (kind === "line") mk("line", { x1: 2, y1: 7, x2: 28, y2: 7, class: cls });
  else if (kind === "circle") mk("circle", { cx: 15, cy: 7, r: 3, class: cls });
  else if (kind === "triangle") mk("polygon", { points: "15,3 19,11 11,11", class: cls });
  else if (kind === "diamond") mk("polygon", { points: "15,3 19,7 15,11 11,7", class: cls });
  else if (kind === "square") mk("rect", { x: 12, y: 4, width: 6, height: 6, class: cls });
  else mk("line", { x1: 2, y1: 7, x2: 28, y2: 7, class: cls });
  return s;
}

function legendItem(ul, kind, cls, ref, label, opts = {}) {
  const li = document.createElement("li");
  li.appendChild(glyph(kind, cls));
  const b = document.createElement("button");
  b.type = "button";
  b.className = "leg-btn";
  b.dataset.ref = ref;
  b.dataset.i = String(opts.i ?? 0);
  b.dataset.legend = "1";
  b.append(label, document.createTextNode(" "), tagEl(model.entry(ref).cls));
  li.appendChild(b);
  ul.appendChild(li);
}

function buildLegends() {
  legendItem($("#leg-x"), "line", "ln-est", "err_est_x", "Estimate − truth");
  legendItem($("#leg-x"), "circle", "pt-gnss", "err_gnss_x", "GNSS − truth");
  legendItem($("#leg-y"), "line", "ln-est", "err_est_y", "Estimate − truth");
  legendItem($("#leg-y"), "circle", "pt-gnss", "err_gnss_y", "GNSS − truth");
  legendItem($("#leg-z"), "line", "ln-est", "err_z_host", "Estimate − truth (host metric)");
  legendItem($("#leg-z"), "circle", "pt-gnss", "err_gnss_z", "GNSS − truth");
  legendItem($("#leg-z"), "triangle", "pt-alt", "err_altimeter", "Altimeter − true nozzle altitude");
  legendItem($("#leg-r"), "diamond", "pt-res", "alt_residual", "Altimeter − estimated nozzle altitude");
  const thr = document.createElement("li");
  thr.appendChild(glyph("line", "band-thr"));
  const tb = V("case.altimeter_threshold_m");
  thr.append("± ", tb, document.createTextNode(" rejection threshold, held for "), V("case.altimeter_rejection_cycles", { nounit: true }), document.createTextNode(" consecutive cycles"));
  $("#leg-r").appendChild(thr);
  const lane1 = $("#leg-l");
  legendItem(lane1, "square", "lane-est-key", "guidance_rule", "Rule active (from the recorded flag)");
  legendItem(lane1, "triangle", "pt-alt", "lower_source", "Altimeter lower");
  legendItem(lane1, "circle", "pt-est-lane", "lower_source", "Estimator lower");
  const lp = $("#leg-plan");
  legendItem(lp, "circle", "plan-truth", "base_x", "True nozzle plane");
  legendItem(lp, "diamond", "plan-belief", "believed_nozzle_x", "Believed nozzle plane, approx.");
  legendItem(lp, "square", "plan-cur-gnss", "gnss_x", "GNSS (centre of mass)");
}

function widthOf(node) {
  return Math.max(300, Math.floor(node.getBoundingClientRect().width || node.parentElement.clientWidth));
}

function renderAll() {
  const w = widthOf($("#strips"));
  const common = { model, width: w, t0: state.t0, t1: state.t1, cursor: state.cursor };
  drawTimeAxis($("#axis"), { ...common, width: widthOf($("#slider")) });
  drawStrip($("#svg-x"), { ...common, height: 190, layers: [
    { series: "err_est_x", kind: "line", cls: "ln-est" },
    { series: "err_gnss_x", kind: "points", cls: "pt-gnss", shape: "circle" },
  ] });
  drawStrip($("#svg-y"), { ...common, height: 120, layers: [
    { series: "err_est_y", kind: "line", cls: "ln-est" },
    { series: "err_gnss_y", kind: "points", cls: "pt-gnss", shape: "circle" },
  ] });
  drawStrip($("#svg-z"), { ...common, height: 190, layers: [
    { series: "err_z_host", kind: "line", cls: "ln-est" },
    { series: "err_gnss_z", kind: "points", cls: "pt-gnss", shape: "circle" },
    { series: "err_altimeter", kind: "points", cls: "pt-alt", shape: "triangle" },
  ] });
  const thr = model.scalar("case.altimeter_threshold_m").v;
  drawStrip($("#svg-r"), { ...common, height: 190, bands: [{ y: thr, cls: "band-thr" }, { y: -thr, cls: "band-thr" }], layers: [
    { series: "alt_residual", kind: "points", cls: "pt-res", shape: "diamond" },
  ] });
  drawLane($("#svg-l"), common);
  const pw = Math.min(widthOf($("#plan")), 400);
  const plan = drawPlan($("#svg-plan"), { model, size: pw, half: 20, cursor: state.cursor });
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
  s.setAttribute("aria-valuetext", `sample ${state.cursor} of ${model.last}, t = ${t} s, ${model.value("kind", state.cursor)}`);
  $("#cursor-status").textContent = `Cursor at sample ${state.cursor} of ${model.last}: t = ${t} s.`;
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
  const i = state.cursor;
  const tc = model.t[i];
  if (tc < state.t0 || tc > state.t1) {
    const inside = model.t.map((x, k) => [x, k]).filter(([x]) => x >= state.t0 && x <= state.t1);
    const mid = (state.t0 + state.t1) / 2;
    state.cursor = inside.reduce((b, c) => (Math.abs(c[0] - mid) < Math.abs(b[0] - mid) ? c : b), inside[0])[1];
  }
  for (const b of $$("[data-zoom]")) b.setAttribute("aria-pressed", String(b.dataset.zoom === kind));
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
  // Only snap among samples of the window; clamp the time first.
  const tt = Math.max(state.t0, Math.min(state.t1, t));
  return model.nearestSample(tt);
}

function wirePointer() {
  for (const id of ["axis", "svg-x", "svg-y", "svg-z", "svg-r", "svg-l"]) {
    const svg = $("#" + id);
    let down = false;
    svg.addEventListener("pointerdown", (ev) => {
      down = true;
      svg.setPointerCapture(ev.pointerId);
      $("#slider").focus({ preventScroll: true });
      setCursor(pointerToSample(svg, ev), { keepWindow: true });
    });
    svg.addEventListener("pointermove", (ev) => {
      if (down) setCursor(pointerToSample(svg, ev), { keepWindow: true });
    });
    svg.addEventListener("pointerup", () => {
      down = false;
    });
    svg.addEventListener("pointercancel", () => {
      down = false;
    });
  }
}

function jumpTo(name) {
  if (name === "fault") {
    setZoom("fault");
    setCursor(model.data.index.fault_first_sample);
  }
}

function wireClicks() {
  document.addEventListener("click", (ev) => {
    const t = ev.target.closest("button, td[data-ref], tr[data-ref]");
    if (!t) return;
    if (t.matches(".val, .leg-btn, td[data-ref]")) {
      openEvidence(t.dataset.ref, Number(t.dataset.i || 0), t);
    } else if (t.dataset.fact) {
      openFact(t.dataset.fact, t);
    } else if (t.dataset.zoom) {
      setZoom(t.dataset.zoom);
    } else if (t.dataset.jump !== undefined && t.classList.contains("ev-btn")) {
      setCursor(Number(t.dataset.jump));
    } else if (t.dataset.jump === "fault") {
      jumpTo("fault");
    } else if (t.dataset.row !== undefined) {
      setCursor(Number(t.dataset.row));
    }
  });
  $("#prev-event").addEventListener("click", () => setCursor(model.eventJump(state.cursor, -1)));
  $("#next-event").addEventListener("click", () => setCursor(model.eventJump(state.cursor, 1)));
  $("#to-touchdown").addEventListener("click", () => setCursor(model.last));
  $("#req-to-td").addEventListener("click", () => setCursor(model.last));
  $("#drawer-close").addEventListener("click", closeDrawer);
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && !$("#drawer").hidden) closeDrawer();
  });
  $("#slider").addEventListener("keydown", onKey);
}

// ---------------------------------------------------------------------------------------------
// Text alternative

function renderSampleTable() {
  const t = $("#sample-table");
  const cols = [
    ["t_s", "t", 3], ["step", "step", 0], ["truth_x", "truth x", 2], ["est_x", "est x", 2], ["gnss_x", "GNSS x", 2], ["err_est_x", "est − truth x", 2],
    ["truth_z", "truth z", 2], ["est_z", "est z", 2], ["err_z_host", "est − truth z", 2], ["altimeter", "altimeter", 2],
    ["alt_residual", "residual, approx.", 2], ["alt_rejected", "rejected", undefined], ["guidance_rule", "guidance rule", undefined],
  ];
  const parts = ["<caption class='sr'>All recorded samples</caption><thead><tr><th scope='col'>Select</th>"];
  for (const [, h] of cols) parts.push(`<th scope='col'>${h}</th>`);
  parts.push("</tr></thead><tbody>");
  for (let i = 0; i < model.n; i++) {
    parts.push(`<tr><th scope='row'><button type='button' class='row-btn' data-row='${i}' data-layout='1'>sample ${i}</button></th>`);
    for (const [id, , d] of cols) {
      parts.push(`<td data-ref='${id}' data-i='${i}' data-digits='${d === undefined ? "" : d}'>${model.text(id, i, d)}</td>`);
    }
    parts.push("</tr>");
  }
  parts.push("</tbody>");
  t.innerHTML = parts.join("");
}

// ---------------------------------------------------------------------------------------------

async function main() {
  model = await loadModel("data.json");
  fillPlaceholders();
  renderBar();
  renderClassList();
  renderEventList();
  renderVerdicts();
  buildLegends();
  renderSampleTable();
  wireClicks();
  wirePointer();
  const params = new URLSearchParams(location.search);
  if (params.get("table") === "open") $("#table-alt").open = true;
  const start = params.get("sample");
  setZoom(params.get("zoom") || "full");
  setCursor(start === null ? model.data.index.flag_first_sample : Number(start), { keepWindow: true });
  let timer = null;
  new ResizeObserver(() => {
    clearTimeout(timer);
    timer = setTimeout(renderAll, 60);
  }).observe($("#strips"));
  document.documentElement.dataset.ready = "1";
}

main().catch((e) => {
  document.body.insertAdjacentHTML("afterbegin", `<p role="alert" class="fatal">The view could not start: ${String(e.message || e)}. Serve this folder over HTTP (python -m http.server) so data.json can be fetched.</p>`);
  console.error(e);
});
