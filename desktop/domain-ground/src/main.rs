//! Domain host of the ground-vehicle domain (contract `vv-domain` v1). It embeds the three M6
//! missions, applies the requested faults to their inputs, runs `vv-lab run-m4` and maps the native
//! outputs into the normalised record. The simulation itself stays in `vv-lab`.

mod catalog;
mod inputs;
mod native;
mod record;

use std::fs;
use std::path::Path;
use std::process::ExitCode;

use vv_platform::contract::*;
use vv_platform::host_sdk::{DomainHost, HostError, host_main};

use catalog::{ACTUATOR_FAULTS, GPS_DROPOUT};
use inputs::{ActuatorOverride, Overrides};

struct Host;

fn whole(value: f64, name: &str) -> Result<u32, String> {
    if value.fract() != 0.0 || !(0.0..=1e6).contains(&value) {
        return Err(format!("{name} must be a whole number of ticks"));
    }
    Ok(value as u32)
}

fn fault_order(kind: &str) -> usize {
    std::iter::once(GPS_DROPOUT)
        .chain(ACTUATOR_FAULTS)
        .position(|k| k == kind)
        .unwrap_or(usize::MAX)
}

/// Overrides of a request that `check` has accepted.
fn overrides(request: &RunRequest) -> Overrides {
    let mut out = Overrides {
        clear_builtin: request.parameters.get(catalog::PARAM_CLEAR_BUILTIN) == Some(&1.0),
        ..Overrides::default()
    };
    for fault in &request.faults {
        let (start, end) = (fault.start as u32, fault.end as u32);
        if fault.kind == GPS_DROPOUT {
            out.gps = Some((start, end));
        } else {
            out.actuator = Some(ActuatorOverride {
                kind: fault.kind.clone(),
                start,
                end,
                delay_ticks: (fault.kind == "delayed_movement")
                    .then(|| fault.magnitude.unwrap_or(0.0) as u32),
            });
        }
    }
    out
}

fn policy(request: &RunRequest) -> native::Policy {
    // Defaults are not passed, so a default request runs the exact command of the Python adapter.
    let changed = |id: &str, default: f64| {
        request
            .parameters
            .get(id)
            .filter(|v| **v != default)
            .map(|v| *v as u32)
    };
    native::Policy {
        stall_window_ticks: changed(catalog::PARAM_STALL_WINDOW, catalog::DEFAULT_STALL_WINDOW),
        min_progress_mm: changed(catalog::PARAM_MIN_PROGRESS, catalog::DEFAULT_MIN_PROGRESS),
    }
}

fn simulation_error(message: String) -> HostError {
    HostError::Simulation(message)
}

impl DomainHost for Host {
    fn manifest(&self) -> DomainManifest {
        catalog::manifest()
    }

    fn catalog(&self) -> DomainCatalog {
        catalog::catalog()
    }

    fn check(&self, mut request: RunRequest) -> Result<RunRequest, String> {
        let mission = inputs::mission(&request.scenario)
            .ok_or_else(|| format!("unknown scenario {}", request.scenario))?;
        let steps = mission.steps();
        let mut actuator = false;
        for (index, fault) in request.faults.iter().enumerate() {
            let name = format!("faults[{index}]");
            let start = whole(fault.start, &format!("{name}.start"))?;
            let end = whole(fault.end, &format!("{name}.end"))?;
            if start < 1 || end > steps {
                return Err(format!(
                    "{name}: the window must lie inside ticks 1 to {steps} of {}",
                    mission.id
                ));
            }
            if fault.kind == GPS_DROPOUT {
                continue;
            }
            if actuator {
                return Err(format!("{name}: at most one actuator fault per run"));
            }
            actuator = true;
            if let Some(delay) = fault.magnitude.filter(|_| fault.kind == "delayed_movement") {
                let delay = whole(delay, &format!("{name}.magnitude"))?;
                if delay > steps {
                    return Err(format!(
                        "{name}: the delay must not exceed the {steps} ticks of {}",
                        mission.id
                    ));
                }
            }
        }
        request.faults.sort_by_key(|f| fault_order(&f.kind));
        Ok(request)
    }

    fn run(&self, request: &RunRequest, out: &Path) -> Result<RunRecord, HostError> {
        let mission = inputs::mission(&request.scenario)
            .ok_or_else(|| HostError::Invalid(format!("unknown scenario {}", request.scenario)))?;
        let built = inputs::build(mission, &overrides(request)).map_err(simulation_error)?;
        let input_dir = out.join("inputs");
        fs::create_dir_all(&input_dir).map_err(|e| simulation_error(e.to_string()))?;
        for (name, bytes) in [
            ("scenario.json", &built.scenario),
            ("actuator.json", &built.actuator),
            ("contracts.json", &built.contracts),
        ] {
            fs::write(input_dir.join(name), bytes)
                .map_err(|e| simulation_error(format!("{name}: {e}")))?;
        }
        let policy = policy(request);
        let native_dir = out.join("native");
        native::run_m4(&native::RunArgs {
            inputs: &input_dir,
            output: &native_dir,
            seed: request.seed,
            controller: &request.controller,
            policy,
        })
        .map_err(simulation_error)?;
        let native = record::Native::load(&native_dir).map_err(simulation_error)?;
        record::build(request, &policy, &native).map_err(simulation_error)
    }

    fn native_replay(&self, dir: &Path) -> Vec<ReplayCheck> {
        let name = "vv-lab replay-m4 recomputes the native run";
        let (pass, detail) = match native::replay_m4(&dir.join("native").join("m4.json")) {
            Ok(summary) => (true, summary),
            Err(error) => (false, error),
        };
        vec![ReplayCheck {
            name: name.into(),
            pass,
            detail,
        }]
    }
}

fn main() -> ExitCode {
    host_main(&Host)
}
