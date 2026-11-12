//! Two-stage launch ascent domain host (`vv-domain` v1, records `vv-run.v2`). It wraps the
//! `vv-ascent` simulator library of this repository: the request becomes a case (the vehicle
//! template of the scenario with the request parameters), the native artifacts are those of
//! `vv-ascent run`, and the multi-entity record is derived from them. Replay recomputes the run; it
//! never returns a stored verdict.

use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

use vv_platform::contract::*;
use vv_platform::host_sdk::{
    DomainHost, HostError, MetricFact, OutcomeBasis, OutcomeChange, RequirementChange, VerdictRules,
};
use vv_platform::seeds::check_seed;

pub mod case;
pub mod catalog;
pub mod demos;
pub mod record;

const MANIFEST_JSON: &str = include_str!("../domain.json");

pub fn manifest() -> DomainManifest {
    serde_json::from_str(MANIFEST_JSON).expect("domain.json is a valid manifest")
}

pub struct Host;

/// The changes of the verdict rules in 0.15.1, for a run stored by an older version of this domain
/// (see `VerdictRules`). Each entry is something the same run is now judged differently on; the
/// physics (timebases, channels, other metrics, events that are not violations) is unchanged and is
/// still compared. In words:
///
/// * the outcome names what the orbit is: a periapsis below the minimum but above the surface is
///   `low_periapsis_orbit`, no SECO is `seco_not_reached`, a specific energy not negative is
///   `unbound` (all three were `suborbital` or `off_target_orbit` before), and an orbit with another
///   requirement failing is `partial`, not `success`;
/// * the upper-stage propellant minimum is 1 % of the load in both cases (it was 0), so R6 can now
///   fail on a run that passed, with its limit and margin metrics;
/// * the orbit-insertion requirement without SECO is judged at the last tick of the run, not at
///   tick 0, and its violation event moves with it.
pub const VERDICT_RULES: VerdictRules = VerdictRules {
    since: "0.15.1",
    outcomes: &[
        // Every orbit was a success before; it is partial now when a requirement fails.
        OutcomeChange {
            from: ("orbit", "success"),
            to: ("orbit", "partial"),
            basis: OutcomeBasis::RequirementFailed,
        },
        OutcomeChange {
            from: ("suborbital", "failure"),
            to: ("low_periapsis_orbit", "failure"),
            basis: OutcomeBasis::Facts {
                stored: &[("upper.R4_periapsis", "fail")],
                fresh: &[
                    ("periapsis_km", MetricFact::AtLeast(0.0)),
                    ("apoapsis_km", MetricFact::Present),
                ],
            },
        },
        OutcomeChange {
            from: ("suborbital", "failure"),
            to: ("seco_not_reached", "failure"),
            basis: OutcomeBasis::Facts {
                stored: &[("upper.R4_periapsis", "not_evaluated")],
                fresh: &[("periapsis_km", MetricFact::Absent)],
            },
        },
        OutcomeChange {
            from: ("suborbital", "failure"),
            to: ("unbound", "failure"),
            basis: OutcomeBasis::Facts {
                stored: &[("upper.R4_periapsis", "fail")],
                fresh: &[
                    ("periapsis_km", MetricFact::Present),
                    ("apoapsis_km", MetricFact::Absent),
                ],
            },
        },
        OutcomeChange {
            from: ("off_target_orbit", "partial"),
            to: ("unbound", "failure"),
            basis: OutcomeBasis::Facts {
                stored: &[
                    ("upper.R4_periapsis", "pass"),
                    ("upper.R5_apoapsis", "fail"),
                ],
                fresh: &[
                    ("periapsis_km", MetricFact::Present),
                    ("apoapsis_km", MetricFact::Absent),
                ],
            },
        },
    ],
    requirements: &[RequirementChange {
        id: "upper.R6_propellant_margin",
        from: "pass",
        to: "fail",
        reason: "the minimum residual propellant is 1 % of the upper-stage load, it was 0",
        observed_metric: "requirement_observed.upper.R6_propellant_margin",
        limit_metric: "requirement_limit.upper.R6_propellant_margin",
        margin_metric: "requirement_margin.upper.R6_propellant_margin",
        old_limit: 0.0,
    }],
    retimed: &["mission.R8_orbit_insertion"],
    summary: "Outcome codes, the upper-stage propellant minimum and the instant of the orbit-insertion requirement changed in 0.15.1; timebases, channels, other metrics and the other events still agree.",
};
static SCRATCH: AtomicU64 = AtomicU64::new(0);

fn scratch_dir() -> PathBuf {
    let n = SCRATCH.fetch_add(1, Ordering::Relaxed);
    std::env::temp_dir().join(format!("vv-ascent-case-{}-{n}", std::process::id()))
}

impl DomainHost for Host {
    fn manifest(&self) -> DomainManifest {
        manifest()
    }

    fn catalog(&self) -> DomainCatalog {
        catalog::catalog()
    }

    fn check(&self, request: RunRequest) -> Result<RunRequest, String> {
        // The platform and the SDK refuse a protected seed already; this is the host's own barrier.
        check_seed(&manifest().seeds, request.seed)?;
        case::case_for(&request)?;
        Ok(request)
    }

    fn run(&self, request: &RunRequest, out: &Path) -> Result<RunRecord, HostError> {
        check_seed(&manifest().seeds, request.seed).map_err(HostError::Invalid)?;
        let case = case::case_for(request).map_err(HostError::Invalid)?;
        let bytes = serde_json::to_vec(&case).map_err(|e| HostError::Simulation(e.to_string()))?;
        let scratch = scratch_dir();
        fs::create_dir_all(&scratch).map_err(|e| HostError::Simulation(e.to_string()))?;
        let case_path = scratch.join("case.json");
        let written = fs::write(&case_path, &bytes)
            .map_err(|e| HostError::Simulation(e.to_string()))
            .and_then(|_| {
                // The same library call as `vv-ascent run`, so the native files are those of the CLI.
                vv_ascent::run::write_run(&case_path, request.seed, out)
                    .map_err(HostError::Simulation)
            });
        let _ = fs::remove_dir_all(&scratch);
        let outputs = written?;
        Ok(record::build(request, &case, &outputs))
    }

    fn native_seed_file(&self) -> Option<&'static str> {
        Some("run.json")
    }

    fn verdict_rules(&self) -> VerdictRules {
        VERDICT_RULES
    }

    fn native_replay(&self, dir: &Path) -> Vec<ReplayCheck> {
        vv_ascent::run::replay(dir)
            .checks
            .into_iter()
            .map(|c| ReplayCheck {
                name: format!("vv-ascent replay: {}", c.name),
                pass: c.pass,
                detail: c.detail,
            })
            .collect()
    }
}
