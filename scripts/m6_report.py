"""Render the M6 static experiment report (one self-contained HTML file).

Inputs: `evidence.json` (deterministic, from `vv-repair`), the analysis from
`m6_analysis.analyze`, and an optional `run` block with wall times and checks
measured by `m6_repair_lab.py`. Every string from the evidence is escaped.
"""

from __future__ import annotations

from html import escape

FAULT_TEXT = {
    "gps_dropout": lambda a: f"GPS dropout ticks {a['start']}-{a['end']}",
    "packet_loss": lambda a: f"packet loss ticks {a['start']}-{a['end']}",
    "gps_dropout_rate": lambda a: f"GPS dropout rate {a['permille']}/1000",
    "packet_loss_rate": lambda a: f"packet loss rate {a['permille']}/1000",
    "comm_delay": lambda a: f"observation delay {a['min']}-{a['max']} ticks",
    "gps_noise": lambda a: f"GPS noise up to {a['max_mm']} mm",
    "actuator_delay": lambda a: f"actuation delayed {a['delay_ticks']} ticks at ticks {a['start']}-{a['end']} (p={a['permille']}/1000)",
    "actuator_lost": lambda a: f"command lost at ticks {a['start']}-{a['end']} (p={a['permille']}/1000)",
    "actuator_continued": lambda a: f"motion continues after stop at ticks {a['start']}-{a['end']} (p={a['permille']}/1000)",
}


def atom_text(atom: dict) -> str:
    render = FAULT_TEXT.get(atom.get("kind", ""))
    return escape(render(atom)) if render else escape(str(atom))


def pct(value: float | None, digits: int = 1) -> str:
    return "n/a" if value is None else f"{100 * value:.{digits}f}%"


def ci_pct(block: dict, digits: int = 1) -> str:
    if block.get("low") is None:
        return "n/a"
    return f"[{100 * block['low']:+.{digits}f}, {100 * block['high']:+.{digits}f}] pp"


def pvalue(value: float) -> str:
    return "&lt;1e-6" if value < 1e-6 else f"{value:.2g}"


def lost_cell(block: dict, acceptance: dict) -> str:
    lost, done = block["completion_lost"], block["baseline_completed"]
    rate = f"{1000 * lost / done:.0f}&permil;" if done else "n/a"
    return (
        f"{lost} lost / {block['completion_gained']} gained of {done} "
        f"({rate}; limit {acceptance['max_completion_loss_permille']}&permil;)"
    )


def num(value: float | None, digits: int = 1) -> str:
    return "n/a" if value is None else f"{value:+.{digits}f}"


def causal_text(item: dict) -> str:
    identity = item["identity"]
    faults = "; ".join(atom_text(atom) for atom in item["atoms"]) or "no injected fault"
    kind = "contract" if identity["kind"] == "temporal" else "safety invariant"
    prop = escape(identity["property"])
    parts = [f"Faults: {faults} (horizon {item['steps']} ticks)."]
    if identity.get("trigger_tick") is not None:
        parts.append(
            f"The {kind} <code>{prop}</code> was triggered at tick {identity['trigger_tick']} "
            f"with deadline tick {identity.get('deadline_tick')}; it failed at tick {identity['violation_tick']}."
        )
    else:
        trigger = escape(identity.get("trigger_event_kind") or "an event")
        parts.append(f"The {kind} <code>{prop}</code> failed at tick {identity['violation_tick']}, set off by {trigger}.")
    if identity["mechanism"]:
        parts.append(f"Actuator mechanism in the window: {escape(', '.join(identity['mechanism']))}.")
    evidence = item["evidence"]
    if evidence["expected"] or evidence["observed"]:
        parts.append(f"Expected: {escape(evidence['expected'])}. Observed: {escape(evidence['observed'])}.")
    return " ".join(parts)


def _point(p: dict) -> str:
    return f"({p['x_mm']}, {p['y_mm']})"


def _action(a: dict | None) -> str:
    if not a:
        return "-"
    return "hold" if a.get("heading") is None else f"{a['heading']} {a.get('distance_mm', '')}"


def trace_table(rows: list[dict]) -> str:
    head = (
        "<tr><th>tick</th><th>truth from</th><th>truth to</th><th>safety</th>"
        "<th>requested</th><th>realized</th><th>actuator</th></tr>"
    )
    body = "".join(
        f"<tr><td>{r['tick']}</td><td>{_point(r['truth_from'])}</td><td>{_point(r['truth_position'])}</td>"
        f"<td>{escape(str(r['safety_state']))}</td><td>{escape(_action(r['requested_action']))}</td>"
        f"<td>{escape(_action(r['realized_action']))}</td><td>{escape(str(r.get('actuator_behavior') or '-'))}</td></tr>"
        for r in rows
    )
    return f'<div class="scroll"><table class="trace">{head}{body}</table></div>'


def replay_cells(item: dict, order: list[str]) -> str:
    cells = []
    for config in order:
        status = escape(item["replay"][config]["status"])
        cells.append(f'<td class="st st-{status}">{status}</td>')
    return "".join(cells)


def bars_svg(candidates: list[dict]) -> str:
    """Held-out fixed (left) and broken (right) pairs per candidate."""
    width, label_w, row_h = 640, 190, 34
    peak = max(max(c["summary"]["heldout"]["fixed"], c["summary"]["heldout"]["broken"]) for c in candidates) or 1
    half = (width - label_w - 100) / 2  # 50 px each side keeps value labels clear of the names
    centre = label_w + 50 + half
    rows = []
    for index, cand in enumerate(candidates):
        held = cand["summary"]["heldout"]
        name = escape(cand["id"])
        y = 24 + index * row_h
        fixed_w = half * held["fixed"] / peak
        broken_w = half * held["broken"] / peak
        rows.append(
            f'<text x="{label_w - 8}" y="{y + 16}" text-anchor="end" class="lab">{name}</text>'
            f'<g><title>{name}: {held["fixed"]} pairs fixed</title>'
            f'<rect x="{centre - fixed_w - 1:.1f}" y="{y + 4}" width="{fixed_w:.1f}" height="16" rx="4" class="fixed"/></g>'
            f'<g><title>{name}: {held["broken"]} pairs broken</title>'
            f'<rect x="{centre + 1:.1f}" y="{y + 4}" width="{broken_w:.1f}" height="16" rx="4" class="broken"/></g>'
            f'<text x="{centre - fixed_w - 6:.1f}" y="{y + 16}" text-anchor="end" class="val">{held["fixed"]}</text>'
            f'<text x="{centre + broken_w + 6:.1f}" y="{y + 16}" class="val">{held["broken"]}</text>'
        )
    height = 24 + len(candidates) * row_h + 8
    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Fixed and broken held-out pairs per candidate">'
        f'<text x="{centre - 8}" y="14" text-anchor="end" class="axis">fixed</text>'
        f'<text x="{centre + 8}" y="14" class="axis">broken</text>'
        f'<line x1="{centre}" x2="{centre}" y1="20" y2="{height - 4}" class="zero"/>' + "".join(rows) + "</svg>"
    )


def _ticks(low: float, high: float) -> list[float]:
    step = 0.1 if high - low > 0.3 else 0.05
    values, value = [], round(int(low / step) * step - step, 4)
    while value <= high + 1e-9:
        if value >= low - 1e-9:
            values.append(round(value, 4))
        value = round(value + step, 4)
    return values


def forest_svg(candidates: list[dict], suites: list[str]) -> str:
    """Risk difference with confidence interval, pooled and per suite (held-out)."""
    entries = []
    for cand in candidates:
        entries.append((cand["id"], "pooled", cand["summary"]["heldout"]["risk_difference"], True))
        for suite in suites:
            entries.append((cand["id"], suite, cand["suites"][suite]["heldout"]["risk_difference"], False))
    values = [v for _, _, rd, _ in entries for v in (rd["low"], rd["high"]) if v is not None] or [0.0]
    low, high = min(min(values), -0.05), max(max(values), 0.05)
    width, label_w, row_h = 640, 230, 20
    plot = width - label_w - 24

    def x(value: float) -> float:
        return label_w + (value - low) / (high - low) * plot

    height = 30 + len(entries) * row_h + 24
    parts = [
        f'<line x1="{x(t):.1f}" x2="{x(t):.1f}" y1="18" y2="{height - 20}" class="grid"/>'
        f'<text x="{x(t):.1f}" y="{height - 6}" text-anchor="middle" class="axis">{100 * t:+.0f} pp</text>'
        for t in _ticks(low, high)
    ]
    parts.append(f'<line x1="{x(0):.1f}" x2="{x(0):.1f}" y1="14" y2="{height - 20}" class="zero"/>')
    parts.append(f'<text x="{x(0) - 6:.1f}" y="12" text-anchor="end" class="axis">better</text>')
    parts.append(f'<text x="{x(0) + 6:.1f}" y="12" class="axis">worse</text>')
    for index, (cand, suite, rd, pooled) in enumerate(entries):
        y = 30 + index * row_h
        label = escape(cand if pooled else suite)
        parts.append(f'<text x="{label_w - 8}" y="{y + 4}" text-anchor="end" class="{"lab" if pooled else "sub"}">{label}</text>')
        if rd["estimate"] is None:
            continue
        line = (
            f'<line x1="{x(rd["low"]):.1f}" x2="{x(rd["high"]):.1f}" y1="{y}" y2="{y}" class="ci"/>'
            if rd["low"] is not None
            else ""
        )
        parts.append(
            f'<g><title>{escape(cand)} / {escape(suite)}: {100 * rd["estimate"]:+.1f} pp, interval {ci_pct(rd)}</title>'
            f'<rect x="{label_w}" y="{y - 9}" width="{plot}" height="18" fill="transparent"/>{line}'
            f'<circle cx="{x(rd["estimate"]):.1f}" cy="{y}" r="{5 if pooled else 4}" class="{"pt pooled" if pooled else "pt"}"/></g>'
        )
    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Change in violation rate, candidate minus baseline">'
        + "".join(parts)
        + "</svg>"
    )


CSS = """
:root{--surface:#fcfcfb;--panel:#f3f2ef;--text:#0b0b0b;--text2:#52514e;--muted:#6f6e69;--line:#dedcd6;
--s1:#2a78d6;--s2:#eb6834;--good:#0f7a3a;--bad:#b42318;--warn:#8a5a00;color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--surface:#1a1a19;--panel:#232321;--text:#f0efec;
--text2:#c3c2b7;--muted:#a3a299;--line:#3a3936;--s1:#3987e5;--s2:#d95926;--good:#4cc27a;--bad:#ff7b6b;--warn:#e0b54a;color-scheme:dark}}
:root[data-theme="dark"]{--surface:#1a1a19;--panel:#232321;--text:#f0efec;--text2:#c3c2b7;--muted:#a3a299;--line:#3a3936;
--s1:#3987e5;--s2:#d95926;--good:#4cc27a;--bad:#ff7b6b;--warn:#e0b54a;color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:var(--surface);color:var(--text);font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1080px;margin:0 auto;padding:32px 16px 64px}
h1{font-size:28px;line-height:1.2;margin:0 0 8px;text-wrap:balance}
h2{font-size:20px;margin:40px 0 12px;padding-top:16px;border-top:1px solid var(--line)}
h3{font-size:16px;margin:28px 0 8px}
p,li{color:var(--text2);max-width:80ch}
code{font:13px/1.4 ui-monospace,Consolas,monospace;overflow-wrap:anywhere}
.lede{font-size:17px;color:var(--text)}.meta{color:var(--muted);font-size:13px}
table{border-collapse:collapse;width:100%;font-size:13.5px;font-variant-numeric:tabular-nums}
th,td{text-align:left;padding:7px 9px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--text2);font-weight:600}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;margin:8px 0}
.badge{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;font-weight:600;border:1px solid currentColor}
.accept,.improved,.pass{color:var(--good)}.reject,.regressed,.fail{color:var(--bad)}
.mixed,.no_effect,.inconclusive{color:var(--warn)}
.st{font-size:12px}.st-resolved{color:var(--good)}.st-persisted{color:var(--text2)}
.st-shifted,.st-inconclusive,.st-untriggered{color:var(--warn)}
.panel{background:var(--panel);border-radius:10px;padding:16px;margin:12px 0}
.charts .panel svg{max-width:760px}
svg{width:100%;height:auto;display:block}
svg text{font:12px system-ui,sans-serif;fill:var(--text2)}
svg .lab{fill:var(--text);font-weight:600}svg .sub{fill:var(--muted)}svg .val{fill:var(--text)}
svg .axis{fill:var(--muted);font-size:11px}
.fixed{fill:var(--s1)}.broken{fill:var(--s2)}
.zero{stroke:var(--text2);stroke-width:1}.grid{stroke:var(--line);stroke-width:1}
.ci{stroke:var(--text2);stroke-width:2}.pt{fill:var(--surface);stroke:var(--s1);stroke-width:2}.pt.pooled{fill:var(--s1)}
.legend{display:flex;gap:16px;font-size:13px;color:var(--text2);margin:6px 0}
.sw{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;vertical-align:-1px}
details{margin:10px 0;border-bottom:1px solid var(--line);padding-bottom:8px}
summary{cursor:pointer;font-weight:600;padding:4px 0}
"""


def _table(head: list[str], rows: list[str]) -> str:
    header = "".join(f"<th>{h}</th>" for h in head)
    return f'<div class="scroll"><table><tr>{header}</tr>{"".join(rows)}</table></div>'


def decision_table(analysis: dict) -> str:
    acceptance = analysis["acceptance"]
    rows = []
    for cand in analysis["candidates"]:
        held = cand["summary"]["heldout"]
        verdict = cand["verdict"]
        counts = cand["corpus_status_counts"]
        introduced = sum(len(block["introduced"]) for block in cand["suites"].values())
        rd = held["risk_difference"]
        rows.append(
            f"<tr><td><b>{escape(cand['id'])}</b>{' <span class=meta>(control)</span>' if cand['role'] == 'control' else ''}</td>"
            f"<td><span class='badge {verdict['decision']}'>{verdict['decision']}</span></td>"
            f"<td class='{verdict['safety']}'>{verdict['safety']}</td><td class='{verdict['progress']}'>{verdict['progress']}</td>"
            f"<td>{held['fixed']} ({held['fixed_vacuous']} vacuous) / {held['broken']} / {held['unchanged']}</td>"
            f"<td>{pct(held['baseline_violation']['rate'])} &rarr; {pct(held['candidate_violation']['rate'])}</td>"
            f"<td>{100 * rd['estimate']:+.1f} pp {ci_pct(rd)}<br><span class='meta'>strict {ci_pct(held['risk_difference_strict'])}</span></td>"
            f"<td>{lost_cell(held, acceptance)}</td>"
            f"<td>{introduced}</td><td>{held['pairs_with_new_class']}</td>"
            f"<td>{counts.get('resolved', 0)} of {sum(counts.values())}</td></tr>"
        )
    head = [
        "candidate", "decision", "safety", "progress", "fixed (vacuous) / broken / unchanged",
        "violation rate", "risk difference (interval)", "completions (held-out)", "new classes (suite level)",
        "pairs gaining a class", "corpus resolved",
    ]
    return _table(head, rows)


def gate_table(cand: dict) -> str:
    cells = "".join(f"<td class='{'pass' if ok else 'fail'}'>{'pass' if ok else 'fail'}</td>" for ok in cand["gates"].values())
    labels = {"safety": "safety (pooled strict)"}
    return _table([escape(labels.get(name, name)) for name in cand["gates"]], [f"<tr>{cells}</tr>"])


def suite_table(cand: dict) -> str:
    rows = []
    for suite, block in cand["suites"].items():
        for split in ("tuning", "heldout"):
            b = block[split]
            rows.append(
                f"<tr><td>{escape(suite)}</td><td>{split}</td><td>{b['pairs']}</td><td>{b['fixed']} / {b['broken']}</td>"
                f"<td>{pct(b['baseline_violation']['rate'])} &rarr; {pct(b['candidate_violation']['rate'])}</td>"
                f"<td>{ci_pct(b['risk_difference'], 2)}</td><td>{pvalue(b['mcnemar_p'])}</td>"
                f"<td>{b['baseline_completed']} &rarr; {b['candidate_completed']}</td>"
                f"<td>{num(b['distance_increase_mm']['mean'], 0)}</td><td>{num(b['fallback_ticks_delta']['mean'], 2)}</td>"
                f"<td>{num(b['movement_ticks_delta']['mean'], 2)}</td><td>{b['pairs_with_new_class']}</td></tr>"
            )
    head = [
        "suite", "seeds", "pairs", "fixed / broken", "violation rate", "risk difference interval", "exact McNemar p",
        "completed", "&Delta; distance remaining (mm)", "&Delta; fallback ticks", "&Delta; movement ticks",
        "pairs where the candidate adds a class",
    ]
    return _table(head, rows)


def family_table(cand: dict) -> str:
    rows = [
        f"<tr><td>{escape(suite)}</td><td>{escape(family)}</td><td>{b['pairs']}</td><td>{b['fixed']} / {b['broken']}</td>"
        f"<td>{pct(b['baseline_violation']['rate'])} &rarr; {pct(b['candidate_violation']['rate'])}</td><td>{b['completion_lost']}</td></tr>"
        for suite, block in cand["suites"].items()
        for family, b in block["families"].items()
    ]
    return _table(["suite", "fault family", "pairs", "fixed / broken", "violation rate", "completions lost"], rows)


def class_table(cand: dict) -> str:
    rows = []
    for suite, block in cand["suites"].items():
        for label, counts in block["classes"].items():
            delta = counts["candidate"] - counts["baseline"]
            if delta:
                rows.append(
                    f"<tr><td>{escape(suite)}</td><td><code>{escape(label)}</code></td><td>{counts['baseline']}</td>"
                    f"<td>{counts['candidate']}</td><td class='{'improved' if delta < 0 else 'regressed'}'>{delta:+d}</td></tr>"
                )
    if not rows:
        return "<p>No class changed frequency on held-out pairs.</p>"
    return _table(["suite", "failure class", "baseline pairs", "candidate pairs", "change"], rows)


def counterexample(item: dict, order: list[str], run_dir: str) -> str:
    reduction = item["reduction"]
    return (
        f"<details><summary><code>{escape(item['id'])}</code> &middot; <code>{escape(item['class'])}</code> "
        f"&middot; found on {escape(item['found_on'])}</summary>"
        f"<p>{causal_text(item)}</p>"
        f"<p class='meta'>Reduced from {reduction['atoms_before']} to {reduction['atoms_after']} fault atoms and "
        f"{reduction['steps_before']} to {reduction['steps_after']} ticks in {reduction['evaluations']} evaluations; "
        f"atom-minimal verified: {str(reduction['one_minimal_verified']).lower()}. "
        f"Independent recheck: {escape(item['recheck']['result'])}. Simulation seed {item['sim_seed']}.</p>"
        + _table([escape(c) for c in order], [f"<tr>{replay_cells(item, order)}</tr>"])
        + trace_table(item["causal_trace"])
        + f"<p class='meta'>Replay: <code>vv-lab replay-m4 {escape(run_dir)}/{escape(item['case_dir'])}/m4.json</code></p></details>"
    )


def headline(candidates: list[dict], acceptance: dict) -> str:
    accepted = [c["id"] for c in candidates if c["verdict"]["decision"] == "accept"]
    if accepted:
        return f"{', '.join(accepted)} passed every registered gate."
    # The first non-control candidate is the one the experiment was designed to test.
    lead = next((c for c in candidates if c["role"] != "control"), None)
    if lead is None:
        return "No candidate passed every registered gate."
    held = lead["summary"]["heldout"]
    failed = [name for name, ok in lead["gates"].items() if not ok] or ["oracle"]
    verdict = lead["verdict"]
    text = (
        f"No candidate passed every registered gate. {lead['id']} (safety {verdict['safety']}, progress {verdict['progress']}) "
        f"fixed {held['fixed']} held-out pairs ({held['fixed_vacuous']} of them vacuous) and broke {held['broken']}, "
        f"and failed the {', '.join(failed)} gate."
    )
    regression = next((note for note in verdict["notes"] if note.startswith("fails no_suite_regression")), None)
    if regression:
        suite, detail = regression.removeprefix("fails no_suite_regression on ").split(": ", 1)
        text += f" It regressed on {suite}: {detail}."
    if "completion" in failed:
        done = held["baseline_completed"] or 1
        horizon = held["completion_lost_outcomes"].get("incomplete", 0)
        text += (
            f" It lost {held['completion_lost']} of {held['baseline_completed']} held-out completions "
            f"({1000 * held['completion_lost'] / done:.0f} per 1000 against a margin of {acceptance['max_completion_loss_permille']}); "
            f"{horizon} of those missions ran out of time rather than stalling."
        )
    return text


def controls_panel(candidates: list[dict]) -> str:
    items = []
    for cand in candidates:
        if cand["role"] != "control":
            continue
        expected = ", ".join(f"{axis} {value}" for axis, value in cand["expect"].items()) or "nothing declared"
        if cand["changes_oracle"] and cand["expect"].get("decision") == "reject":
            expected += " (decision reject follows from the oracle rule and is not a prediction)"
        observed = ", ".join(f"{axis} {cand['verdict'][axis]}" for axis in cand["expect"]) or "n/a"
        ok = cand["as_predicted"]
        items.append(
            f"<li><b>{escape(cand['id'])}</b>: expected {escape(expected)}; observed {escape(observed)} "
            f"<span class='badge {'pass' if ok else 'fail'}'>{'as predicted' if ok else 'not as predicted'}</span></li>"
        )
    if not items:
        return ""
    return (
        "<div class='panel'><b>Controls.</b> These configurations test the lab, not the controller. Their predictions were stated "
        "in their rationale before the first full run and formalized as machine-checked <code>expect</code> values afterwards."
        f"<ul>{''.join(items)}</ul>"
        "A positive result is only credible when every control behaves as predicted.</div>"
    )


def candidate_section(cand: dict, config: dict) -> str:
    effective = "; ".join(
        f"{escape(suite)}: fallback {e['fallback_after_ticks']}, recovery {e['recovery_after_ticks']}, "
        f"gate {e['confidence_threshold_permille']}, max age {e['max_observation_age_ticks']}, step {e['step_mm']} mm"
        for suite, e in config["effective"].items()
    )
    notes = "".join(f"<li>{escape(note)}</li>" for note in cand["verdict"]["notes"])
    verdict = cand["verdict"]
    held = cand["summary"]["heldout"]
    changes = sorted(
        (c["candidate"] - c["baseline"], suite, label)
        for suite, block in cand["suites"].items()
        for label, c in block["classes"].items()
    )
    rises = [f"<code>{escape(label)}</code> on {escape(suite)} {d:+d}" for d, suite, label in reversed(changes) if d > 0][:3]
    drops = [f"<code>{escape(label)}</code> on {escape(suite)} {d:+d}" for d, suite, label in changes if d < 0][:3]
    outcomes = ", ".join(f"{n} {escape(k)}" for k, n in held["completion_lost_outcomes"].items()) or "none"
    facts = (
        f"<p><b>Outcome (held-out).</b> Lost completions: {held['completion_lost']} ({outcomes}); "
        f"mean change in fallback ticks on those pairs {num(held['completion_lost_fallback_delta']['mean'], 2)}. "
        f"Mean change per pair: fallback {num(held['fallback_ticks_delta']['mean'], 2)} ticks, movement "
        f"{num(held['movement_ticks_delta']['mean'], 2)} ticks, distance remaining {num(held['distance_increase_mm']['mean'], 0)} mm. "
        f"Largest drops in pairs per class: {', '.join(drops) or 'none'}. Largest rises: {', '.join(rises) or 'none'}.</p>"
    )
    return (
        f"<h3>{escape(cand['id'])} <span class='badge {verdict['decision']}'>{verdict['decision']}</span></h3>"
        f"<p>{escape(cand['rationale'])}</p>"
        f"<p class='meta'>Policy <code>{escape(cand['policy'])}</code> &middot; overrides <code>{escape(str(cand['overrides']))}</code> "
        f"&middot; config sha256 <code>{cand['config_sha256'][:16]}</code></p>"
        f"<p class='meta'>Effective parameters: {effective}</p>"
        + (f"<ul>{notes}</ul>" if notes else "")
        + gate_table(cand)
        + facts
        + suite_table(cand)
        + f"<details><summary>Held-out results by fault family</summary>{family_table(cand)}</details>"
        + f"<details><summary>Failure classes whose frequency changed (held-out)</summary>{class_table(cand)}</details>"
    )


def render(evidence: dict, analysis: dict, run: dict | None = None) -> str:
    run = run or {}
    experiment = evidence["experiment"]
    suites = [s["id"] for s in experiment["suites"]]
    order = [experiment["baseline"]["id"]] + [c["id"] for c in experiment["candidates"]]
    candidates = analysis["candidates"]
    configs = {c["id"]: c for c in evidence["configs"]}
    run_dir = run.get("run_dir", "runs/m6/run")
    total = evidence["totals"]
    gate = experiment["acceptance"]
    level = 100 - gate["alpha_permille"] / 10

    held_pairs = candidates[0]["summary"]["heldout"]["pairs"] if candidates else 0
    all_pairs = candidates[0]["summary"]["all"]["pairs"] if candidates else 0
    suite_items = "".join(
        f"<li><code>{escape(s['id'])}</code>: {escape(s.get('description') or s['scenario_name'])}</li>"
        for s in evidence["suites"]
    )
    rows_total = sum(
        len(rows) for by_config in evidence["results"].values() for seeds in by_config.values() for rows in seeds.values()
    )
    sections = "".join(candidate_section(cand, configs[cand["id"]]) for cand in candidates)
    introduced = "".join(counterexample(item, order, run_dir) for item in evidence["introduced"]) or "<p>None.</p>"
    worst_first = sorted(
        evidence["corpus"],
        key=lambda i: (-sum(r["status"] == "persisted" for r in i["replay"].values()), i["identity"]["kind"] != "safety", i["id"]),
    )
    corpus = "".join(counterexample(item, order, run_dir) for item in worst_first)
    corpus_rows = [
        f"<tr><td><code>{escape(i['id'])}</code></td><td><code>{escape(i['class'])}</code></td>{replay_cells(i, order)}</tr>"
        for i in evidence["corpus"]
    ]
    timing = run.get("timing_ms", {})
    perf_rows = [f"<tr><td>{escape(c)}</td><td>{escape(str(timing.get(c, 'n/a')))}</td></tr>" for c in order]
    checks = "".join(f"<li>{escape(k)}: {escape(str(v))}</li>" for k, v in run.get("checks", {}).items())

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Controller repair lab</title><style>{CSS}</style></head>
<body><main>
<p class="meta">V&amp;V lab &middot; M6 controller repair and regression &middot; simulation evidence</p>
<h1>Can a controller change fix known failures without creating new ones?</h1>
<p class="lede">{escape(headline(candidates, gate))}</p>
<p class="meta">{len(order) - 1} candidates against <code>{escape(experiment['baseline']['id'])}</code> on {len(suites)} suites,
{total['workloads']} workloads on {len(experiment['sim_seeds'])} simulation seeds: {all_pairs} pairs per candidate, {held_pairs} of them held-out.
Gates in the experiment file: interval level {level:.0f}%, completion loss at most
{gate['max_completion_loss_permille']} per 1000 baseline completions, mean distance increase at most {gate['max_mean_distance_increase_mm']} mm,
at least {gate['min_heldout_pairs']} held-out pairs per suite. The same gates apply to every M6 experiment. Their history (values set after
the first exploratory M6 run; two later rules that only tighten acceptance) and the seed history of each experiment are in
<code>docs/m6-controller-repair.md</code>. Experiment file: <code>{escape(run.get('experiment', 'scenarios/m6/experiment.json'))}</code>.</p>

<h2>Decision</h2>
<p>Held-out seeds plus the shared no-fault control workload. A pair is one workload on one simulation seed, run by the
baseline and by the candidate. <i>Fixed</i>: the baseline violates a property and the candidate does not; <i>broken</i>: the reverse.</p>
{decision_table(analysis)}
<p class="meta">A fix is <i>vacuous</i> when the candidate only leaves an obligation pending (more INCONCLUSIVE contracts) or never moves
where the baseline moved; the safety gate uses the <i>strict</i> interval, which counts vacuous fixes as unchanged.
Safety: <i>improved</i> = strict interval below zero, no suite-level new class and at least one corpus case resolved;
<i>mixed</i> = lower rate but a new class or no resolved corpus case; <i>regressed</i> = the pooled or some suite's non-strict interval lies above zero;
<i>no_effect</i> otherwise. Progress: <i>pass</i> = completion loss and distance within the margins. A <i>new class (suite level)</i>
is a failure class the baseline never shows on any workload of that suite. A class the baseline shows elsewhere can still appear on
more pairs; the per-candidate tables count those pairs.</p>
<h3>Suites</h3><ul>{suite_items}</ul>
{controls_panel(candidates)}
<div class="charts">
<div class="panel"><b>Fixed and broken pairs (held-out)</b>
<div class="legend"><span><span class="sw" style="background:var(--s1)"></span>fixed</span><span><span class="sw" style="background:var(--s2)"></span>broken</span></div>
{bars_svg(candidates)}</div>
<div class="panel"><b>Change in violation rate, candidate minus baseline</b>
<p class="meta">Point estimate and {level:.0f}% interval, pooled (filled) and per suite (hollow). Left of zero is better. All fixes counted; the safety gate uses the strict interval in the table.</p>
{forest_svg(candidates, suites)}</div></div>

<h2>Candidates</h2>
{sections}

<h2>New failures introduced by candidates</h2>
<p>A class is new when a candidate shows it on some workload and the baseline never shows it on any workload of that suite.
Each one was reduced on the candidate and replayed on every configuration.</p>
{introduced}

<h2>Known counterexamples (regression corpus)</h2>
<p>Classes the baseline shows on tuning seeds, reduced under the baseline and replayed on every configuration.
<i>resolved</i> requires the property to pass; a bounded-response contract whose trigger never fires is <i>untriggered</i> instead,
a pending one <i>inconclusive</i>, and the same property with another actuator mechanism <i>shifted</i>.</p>
{_table(["case", "class"] + [escape(c) for c in order], corpus_rows)}
<h3>Counterexamples, most persistent first</h3>
{corpus}

<h2>Performance and cost</h2>
<p>All configurations run the same controller code, so the computation per evaluation is the same by construction.
The cost of a candidate shows in the mission metrics above: movement ticks, fallback ticks and completions.
Wall time per configuration, measured outside the simulation on {escape(run.get('machine', 'the run machine'))}:</p>
{_table(["configuration", "wall time ms (all suites and seeds)"], perf_rows)}
<p class="meta">Evaluations: {total['evaluations']} ({rows_total} paired-campaign runs and
{total['evaluations'] - rows_total} counterexample runs) plus {total['minimization_evaluations']} during reduction.
Unidentified violations: {total['unidentified_violations']}.</p>

<h2>Reproduction</h2>
<div class="panel"><code>cargo build --release<br>python scripts/m6_repair_lab.py --experiment {escape(run.get('experiment', 'scenarios/m6/experiment.json'))} --output-root {escape(run.get('output_root', 'runs/m6'))}<br>target/release/vv-repair replay {escape(run_dir)}</code></div>
<ul><li>Library source sha256 <code>{escape(evidence['source_sha256'])}</code>, unchanged from M4 and M5.</li>
<li>Evidence sha256 <code>{escape(evidence['evidence_sha256'])}</code>; experiment sha256 <code>{escape(evidence['experiment_sha256'])}</code>.</li>
<li>Seeds: tuning {experiment['tuning_seeds']}, held-out {experiment['heldout_seeds']}, simulation {experiment['sim_seeds']}.</li>{checks}</ul>

<h2>Limitations</h2>
<ul>
<li>This is simulation evidence from a small integer 2D kinematic model. It says nothing about real vehicles, and passing these gates is not a safety guarantee.</li>
<li>Candidates are configuration changes of the canonical controller: policy, watchdog, recovery, confidence gate and stride. New control laws would change the hashed library and need a separate, approved re-baseline.</li>
<li>The confidence threshold also defines the contract trigger <code>localization_unreliable</code>. A candidate that changes it changes the oracle, so its contract results are not directly comparable.</li>
<li>Pairing fixes the exogenous calendar (GPS, communication and actuator draws), not the trajectory. Pairs are not independent:
both simulation seeds share each workload, the per-family projections share atoms with their full draw, and the no-fault control appears in
both splits. The Wald intervals treat pairs as independent, so they are too narrow, and there is no correction for testing {len(order) - 1} configurations on
{len(suites)} suites. With few discordant pairs the Wald bound can disagree with the exact test; the notes say when it does.</li>
<li>The suite-level <i>new class</i> gate misses classes the baseline shows only on tuning seeds; the column <i>pairs gaining a class</i> and the
per-class tables show those increases, but they are not gated.</li>
<li>The corpus keeps at most {experiment['max_corpus_per_suite']} classes per suite in alphabetical order;
{sum(s.get('corpus_classes_dropped', 0) for s in evidence['suites'])} baseline classes were left out of it in this run.</li>
<li>Missions have a fixed horizon. A candidate that spends more ticks in fallback can lose a completion because time runs out, not because it stalls.</li>
<li>There is no environment model such as wind, slope or friction. Actuator continuation and loss stand in for disturbances; GPS noise stands in for conflicting inputs.</li>
<li>The corpus is reduced under the baseline only and capped per suite. Class identity ignores ticks, so a class that only moves in time is not counted as new.</li>
<li>Workloads come from uniform sampling without boundary bias. Not finding a failure class is not evidence that it cannot occur.</li>
</ul>
</main></body></html>
"""
