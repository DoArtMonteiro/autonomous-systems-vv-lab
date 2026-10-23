//! `report.md`: relatório determinístico (sem datas, durações nem caminhos).

use std::fmt::Write;

use autonomous_systems_vv_lab::model::Action;

use crate::model::{Body, FailureRow};

fn action(value: &Action) -> String {
    match value.heading {
        Some(heading) => format!("{heading:?} {}mm", value.distance_mm),
        None => "hold".to_owned(),
    }
}

fn status<T: serde::Serialize>(value: &T) -> String {
    serde_json::to_string(value)
        .unwrap_or_default()
        .trim_matches('"')
        .to_owned()
}

pub fn render(body: &Body, hash: &str) -> String {
    let mut out = String::new();
    let metrics = &body.metrics;
    let _ = writeln!(out, "# Adversarial campaign report\n");
    let _ = writeln!(out, "Schema `{}`, campaign sha256 `{hash}`.\n", body.schema);
    let _ = writeln!(out, "## Setup\n");
    let _ = writeln!(
        out,
        "- Scenario: `{}` ({} steps)",
        body.inputs.scenario_name, body.inputs.scenario_steps
    );
    let _ = writeln!(
        out,
        "- PRNG: {} (domain {}), campaign seed {}, sim seed {}",
        body.prng.algorithm, body.prng.domain, body.prng.campaign_seed, body.prng.sim_seed
    );
    let _ = writeln!(
        out,
        "- Policies: {}; budget {} candidates ({} phase A, rest phase B); minimize budget {} evaluations; max failures {}",
        body.limits.policies.join(", "),
        body.limits.budget,
        body.limits.phase_a_candidates,
        body.limits.minimize_budget,
        body.limits.max_failures
    );
    let _ = writeln!(
        out,
        "- Inputs sha256: scenario `{}`, contracts `{}`, actuator `{}` ({})",
        body.inputs.scenario_sha256,
        body.inputs.contracts_sha256,
        body.inputs.actuator_sha256,
        body.inputs.actuator_source
    );
    let _ = writeln!(out, "- Source sha256: `{}`", body.source_sha256);
    let _ = writeln!(out, "- Risk: {}", body.design.risk_formula);
    let _ = writeln!(out, "- Background: {}", body.design.background_policy);
    let _ = writeln!(
        out,
        "- Conflicting inputs: {}\n",
        body.design.conflicting_inputs
    );

    let _ = writeln!(out, "## Control (base, no atoms)\n");
    let _ = writeln!(out, "| policy | safety | temporal | mission | violations |");
    let _ = writeln!(out, "|---|---|---|---|---|");
    for row in &body.control {
        let _ = writeln!(
            out,
            "| {} | {} | {} | {} | {} |",
            row.policy,
            status(&row.summary.safety),
            status(&row.summary.temporal),
            status(&row.summary.mission),
            row.summary.violations.len()
        );
    }
    let _ = writeln!(out, "\n## Results\n");
    let _ = writeln!(
        out,
        "- Candidates {} (A {}, B {}); evaluations {} (control {}, search {}, minimization {}, case artifacts {})",
        metrics.candidates,
        metrics.phase_a,
        metrics.phase_b,
        metrics.evaluations.total,
        metrics.evaluations.control,
        metrics.evaluations.search,
        metrics.evaluations.minimization,
        metrics.evaluations.case_artifacts
    );
    let _ = writeln!(
        out,
        "- Violating candidates {}; failure classes found {} (novel {}, inherited from control {}; kept {}); inconclusive evaluations {}; control violations {}; unidentified violations {}\n",
        metrics.violating_candidates,
        metrics.unique_classes_found,
        metrics.novel_classes_found,
        metrics.inherited_classes_found,
        metrics.unique_classes_kept,
        metrics.inconclusive_evaluations,
        metrics.control_violations,
        metrics.unidentified_violations
    );
    if !metrics.violations_by_policy.is_empty() {
        let _ = writeln!(out, "| policy | property | violating candidates |");
        let _ = writeln!(out, "|---|---|---|");
        for (policy, properties) in &metrics.violations_by_policy {
            for (property, count) in properties {
                let _ = writeln!(out, "| {policy} | {property} | {count} |");
            }
        }
        let _ = writeln!(out);
    }
    if !body.policy_matrix.is_empty() {
        let _ = writeln!(out, "### Policy comparison matrix (candidates)\n");
        let _ = writeln!(out, "| property | outcome | candidates |");
        let _ = writeln!(out, "|---|---|---|");
        for (property, row) in &body.policy_matrix {
            for (key, count) in row {
                let _ = writeln!(out, "| {property} | {key} | {count} |");
            }
        }
        let _ = writeln!(out);
    }
    for failure in &body.failures {
        failure_section(&mut out, failure);
    }
    out
}

fn failure_section(out: &mut String, failure: &FailureRow) {
    let id = &failure.identity;
    let _ = writeln!(out, "## Case {:02}: {}\n", failure.case, failure.class);
    let _ = writeln!(
        out,
        "- Property violated: `{}` ({}) under policy `{}`",
        id.property, id.kind, id.policy
    );
    let _ = writeln!(
        out,
        "- Identity: trigger {:?}, deadline {:?}, violation tick {}, mechanism {}",
        id.trigger_tick,
        id.deadline_tick,
        id.violation_tick,
        id.mechanism.join(" + ")
    );
    let _ = writeln!(
        out,
        "- Found by candidate {}; expected: {}; observed: {}",
        failure.candidate_index, failure.evidence.expected, failure.evidence.observed
    );
    let _ = writeln!(
        out,
        "- Artifacts: `{}` and `{}` (replay with `vv-lab replay-m4 <dir>/m4.json`)\n",
        failure.original.dir, failure.minimized.dir
    );
    let _ = writeln!(out, "### Minimized counterexample\n");
    for atom in &failure.minimized.atoms {
        let _ = writeln!(out, "- `{}`", atom.describe());
    }
    if failure.minimized.atoms.is_empty() {
        let _ = writeln!(out, "- no fault atoms (base background reproduces it)");
    }
    let _ = writeln!(out, "- Horizon: {} steps\n", failure.minimized.steps);

    let reduction = &failure.reduction;
    let _ = writeln!(out, "### Reduction\n");
    let _ = writeln!(out, "| metric | before | after |");
    let _ = writeln!(out, "|---|---|---|");
    let _ = writeln!(
        out,
        "| atoms | {} | {} |",
        reduction.atoms.before, reduction.atoms.after
    );
    let _ = writeln!(
        out,
        "| active fault ticks | {} | {} |",
        reduction.active_fault_ticks.before, reduction.active_fault_ticks.after
    );
    let _ = writeln!(
        out,
        "| steps | {} | {} |",
        reduction.steps.before, reduction.steps.after
    );
    let _ = writeln!(
        out,
        "\nEvaluations {}/{}{}; 1-minimal in atoms verified: {}.\n",
        reduction.evaluations_used,
        reduction.evaluation_budget,
        if reduction.budget_exhausted {
            " (budget exhausted)"
        } else {
            ""
        },
        reduction.one_minimal_verified
    );
    if !failure.reduction_log.is_empty() {
        let _ = writeln!(out, "| # | phase | step | atoms | fault ticks | steps |");
        let _ = writeln!(out, "|---|---|---|---|---|---|");
        for (index, step) in failure.reduction_log.iter().enumerate() {
            let _ = writeln!(
                out,
                "| {} | {} | {} | {} | {} | {} |",
                index + 1,
                step.phase,
                step.description,
                step.atoms,
                step.active_fault_ticks,
                step.steps
            );
        }
        let _ = writeln!(out);
    }

    let _ = writeln!(out, "### Causal trace (minimized)\n");
    let _ = writeln!(
        out,
        "| tick | truth from | truth to | safety | requested | realized | behavior | fault events |"
    );
    let _ = writeln!(out, "|---|---|---|---|---|---|---|---|");
    for row in &failure.causal_trace {
        let events: Vec<String> = row
            .fault_events
            .iter()
            .map(|event| {
                format!(
                    "{}:{} src={} due={:?}",
                    status(&event.kind),
                    event.fault_id,
                    event.source_command_tick,
                    event.due_tick
                )
            })
            .collect();
        let _ = writeln!(
            out,
            "| {} | ({}, {}) | ({}, {}) | {} | {} | {} | {} | {} |",
            row.tick,
            row.truth_from.x_mm,
            row.truth_from.y_mm,
            row.truth_position.x_mm,
            row.truth_position.y_mm,
            status(&row.safety_state),
            action(&row.requested_action),
            row.realized_action
                .as_ref()
                .map_or("n/a".to_owned(), action),
            row.actuator_behavior
                .as_ref()
                .map_or("n/a".to_owned(), status),
            events.join("; ")
        );
    }

    let recheck = &failure.recheck;
    let _ = writeln!(out, "\n### Independent recheck\n");
    let _ = writeln!(
        out,
        "- Result: **{}** ({}); reported violation tick {}, recomputed {:?}\n",
        recheck.result,
        recheck.method,
        recheck.reported_violation_tick,
        recheck.recomputed_first_violation_tick
    );
    let _ = writeln!(out, "### Policy comparison on the minimized case\n");
    let _ = writeln!(
        out,
        "| policy | safety | temporal | mission | same property | same class | violations |"
    );
    let _ = writeln!(out, "|---|---|---|---|---|---|---|");
    for (policy, row) in &failure.policy_comparison {
        let _ = writeln!(
            out,
            "| {}{} | {} | {} | {} | {} | {} | {} |",
            policy,
            if row.failing_policy { " (failing)" } else { "" },
            status(&row.safety),
            status(&row.temporal),
            status(&row.mission),
            row.same_property_violated,
            row.same_class_violated,
            row.violations.join(", ")
        );
    }
    let _ = writeln!(out);
}
