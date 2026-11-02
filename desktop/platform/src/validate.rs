//! Generic request validation against a domain catalog and manifest. The platform runs it before a
//! host starts and every host built on `host_sdk` runs it again; domain-specific rules (time steps,
//! schema-version restrictions) stay in the host. Normalisation fills parameter defaults and fault
//! magnitudes so that equal simulations have one canonical request and one run identity.

use std::collections::BTreeMap;

use crate::contract::{DomainCatalog, DomainManifest, REQUEST_SCHEMA, RunRequest};
use crate::seeds::check_seed;

const MAX_PARAMETERS: usize = 64;

fn finite(value: f64, name: &str) -> Result<(), String> {
    if value.is_finite() {
        Ok(())
    } else {
        Err(format!("{name} must be a finite number"))
    }
}

pub fn normalise(
    manifest: &DomainManifest,
    catalog: &DomainCatalog,
    request: &RunRequest,
) -> Result<RunRequest, String> {
    if request.schema != REQUEST_SCHEMA {
        return Err(format!("schema must be {REQUEST_SCHEMA}"));
    }
    if request.domain != manifest.id {
        return Err(format!("domain must be {}", manifest.id));
    }
    check_seed(&manifest.seeds, request.seed)?;
    let scenario = catalog
        .scenarios
        .iter()
        .find(|s| s.id == request.scenario)
        .ok_or_else(|| format!("unknown scenario {}", request.scenario))?;
    if !scenario.controllers.contains(&request.controller) {
        return Err(format!(
            "controller {} is not available for scenario {}",
            request.controller, scenario.id
        ));
    }
    if request.parameters.len() > MAX_PARAMETERS {
        return Err(format!("at most {MAX_PARAMETERS} parameters"));
    }
    let mut parameters = BTreeMap::new();
    for id in &scenario.parameters {
        let spec = catalog
            .parameters
            .iter()
            .find(|p| &p.id == id)
            .ok_or_else(|| format!("catalog error: scenario names unknown parameter {id}"))?;
        let value = request.parameters.get(id).copied().unwrap_or(spec.default);
        finite(value, &format!("parameter {id}"))?;
        if value < spec.min || value > spec.max {
            return Err(format!(
                "parameter {id} must be in {} to {} {}",
                spec.min, spec.max, spec.unit
            ));
        }
        if spec.integer && value.fract() != 0.0 {
            return Err(format!("parameter {id} must be a whole number"));
        }
        parameters.insert(id.clone(), value);
    }
    if let Some(unknown) = request
        .parameters
        .keys()
        .find(|k| !scenario.parameters.contains(k))
    {
        return Err(format!(
            "parameter {unknown} is not accepted by scenario {}",
            scenario.id
        ));
    }
    if request.faults.len() > catalog.max_faults as usize {
        return Err(format!("at most {} faults", catalog.max_faults));
    }
    let mut faults = Vec::with_capacity(request.faults.len());
    for (index, fault) in request.faults.iter().enumerate() {
        let name = format!("faults[{index}]");
        let spec = catalog
            .faults
            .iter()
            .find(|f| f.kind == fault.kind)
            .ok_or_else(|| format!("{name}: unknown fault kind {}", fault.kind))?;
        if request.faults[..index].iter().any(|f| f.kind == fault.kind) {
            return Err(format!("{name}: fault kind {} is repeated", fault.kind));
        }
        if let Some(allowed) = &spec.controllers
            && !allowed.contains(&request.controller)
        {
            return Err(format!(
                "{name}: {} needs one of the controllers {}",
                fault.kind,
                allowed.join(", ")
            ));
        }
        finite(fault.start, &format!("{name}.start"))?;
        finite(fault.end, &format!("{name}.end"))?;
        if fault.start < 0.0 || fault.end < fault.start {
            return Err(format!("{name}: the window must satisfy 0 <= start <= end"));
        }
        if let Some(window) = &spec.window {
            let length = fault.end - fault.start;
            if length < window.min_length - 1e-9 || length > window.max_length + 1e-9 {
                return Err(format!(
                    "{name}: window length must be in {} to {} {}",
                    window.min_length, window.max_length, catalog.time.unit
                ));
            }
        }
        let magnitude = match (&spec.magnitude, fault.magnitude) {
            (None, None) => None,
            (None, Some(_)) => return Err(format!("{name}: {} takes no magnitude", fault.kind)),
            (Some(m), given) => {
                let value = given.unwrap_or(m.default);
                finite(value, &format!("{name}.magnitude"))?;
                if value < m.min || value > m.max {
                    return Err(format!(
                        "{name}: magnitude must be in {} to {} {}",
                        m.min, m.max, m.unit
                    ));
                }
                Some(value)
            }
        };
        let mut normal = fault.clone();
        normal.magnitude = magnitude;
        faults.push(normal);
    }
    Ok(RunRequest {
        schema: REQUEST_SCHEMA.into(),
        domain: request.domain.clone(),
        scenario: request.scenario.clone(),
        controller: request.controller.clone(),
        seed: request.seed,
        faults,
        parameters,
    })
}
