//! Simplificações por átomo e extração das janelas realizadas de uma taxa.

use autonomous_systems_vv_lab::ControllerEvaluationOutcome;
use autonomous_systems_vv_lab::model::EventPayload;

use crate::atoms::Fault;

/// Valores menores a tentar: metade, 3/4 e 7/8; só passos de 1 para valores pequenos.
fn smaller_values(value: u32, floor: u32) -> Vec<u32> {
    let mut candidates = vec![value / 2, value - value / 4, value - value / 8];
    if value <= 8 {
        candidates.push(value.saturating_sub(1));
    }
    let mut values: Vec<u32> = candidates
        .into_iter()
        .filter(|candidate| *candidate >= floor && *candidate < value)
        .collect();
    values.sort_unstable();
    values.dedup();
    values
}

/// Variantes estritamente mais simples de uma falha, da mais agressiva à menor.
pub fn simpler(fault: &Fault) -> Vec<(&'static str, Fault)> {
    let mut options: Vec<(&'static str, Fault)> = Vec::new();
    if let Some((start, end)) = fault.window() {
        let length = end - start + 1;
        let half = length / 2;
        if half >= 1 {
            options.push(("shrink front half", fault.with_window(start + half, end)));
            options.push(("shrink back half", fault.with_window(start, end - half)));
        }
        if half > 1 {
            options.push(("shrink front", fault.with_window(start + 1, end)));
            options.push(("shrink back", fault.with_window(start, end - 1)));
        }
    }
    match fault {
        Fault::ActuatorDelay {
            start,
            end,
            delay_ticks,
            permille,
        } => {
            let mut delays = vec![1_u32];
            delays.extend(smaller_values(*delay_ticks, 1));
            delays.retain(|delay| delay < delay_ticks);
            delays.dedup();
            for delay in delays {
                options.push((
                    "lower delay",
                    Fault::ActuatorDelay {
                        start: *start,
                        end: *end,
                        delay_ticks: delay,
                        permille: *permille,
                    },
                ));
            }
        }
        Fault::GpsNoise { max_mm } => {
            for value in smaller_values(*max_mm as u32, 1) {
                options.push((
                    "lower noise",
                    Fault::GpsNoise {
                        max_mm: value as i32,
                    },
                ));
            }
        }
        Fault::GpsDropoutRate { permille } => {
            for value in smaller_values(u32::from(*permille), 1) {
                options.push((
                    "lower rate",
                    Fault::GpsDropoutRate {
                        permille: value as u16,
                    },
                ));
            }
        }
        Fault::PacketLossRate { permille } => {
            for value in smaller_values(u32::from(*permille), 1) {
                options.push((
                    "lower rate",
                    Fault::PacketLossRate {
                        permille: value as u16,
                    },
                ));
            }
        }
        Fault::CommDelay { min, max } => {
            if *min > 0 {
                options.push(("zero minimum delay", Fault::CommDelay { min: 0, max: *max }));
            }
            for value in smaller_values(*max, *min) {
                options.push((
                    "lower maximum delay",
                    Fault::CommDelay {
                        min: *min,
                        max: value,
                    },
                ));
            }
        }
        _ => {}
    }
    options
}

/// Corridas consecutivas de amostras GPS perdidas (ou pacotes não entregues).
/// `None` se houver demasiadas corridas para as trocar por janelas.
pub fn dropped_runs(outcome: &ControllerEvaluationOutcome, gps: bool) -> Option<Vec<(u32, u32)>> {
    const MAX_RUNS: usize = 16;
    let mut ticks: Vec<u32> = outcome
        .artifact
        .events
        .iter()
        .filter_map(|record| match (&record.event, gps) {
            (EventPayload::GpsSample { dropped: true, .. }, true) => Some(record.tick),
            (
                EventPayload::PacketOutcome {
                    delivered: false, ..
                },
                false,
            ) => Some(record.tick),
            _ => None,
        })
        .collect();
    ticks.sort_unstable();
    ticks.dedup();
    let mut runs: Vec<(u32, u32)> = Vec::new();
    for tick in ticks {
        match runs.last_mut() {
            Some(last) if last.1 + 1 == tick => last.1 = tick,
            _ => runs.push((tick, tick)),
        }
    }
    (runs.len() <= MAX_RUNS).then_some(runs)
}
