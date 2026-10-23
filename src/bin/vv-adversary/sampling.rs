//! Geração de átomos com enviesamento para fronteiras temporais e mutação.
//!
//! As fronteiras vêm da base, dos contratos e do controlo (ticks onde a ação
//! muda, conclusão da missão): `fallback_after_ticks`, `max_observation_age`,
//! `within_ticks` dos contratos, tick 1 e tick `steps`. Nunca há geometria.

use std::collections::BTreeSet;

use autonomous_systems_vv_lab::contracts::{Contract, ContractSet};
use autonomous_systems_vv_lab::model::Scenario;
use autonomous_systems_vv_lab::prng::XorShift64Star;
use serde::Serialize;

use crate::atoms::{Atom, Fault};

pub const MAX_ATOMS_PHASE_A: u32 = 4;
pub const MAX_ATOMS_PHASE_B: usize = 6;
const MAX_NOISE_MM: i32 = 100_000;
const MAX_DELAY_TICKS: u32 = 10_000;

/// Valores de referência usados para enviesar a geração (registados no relatório).
#[derive(Clone, Debug, Serialize)]
pub struct Refs {
    /// Falso na ablação `uniform`: ticks, janelas e atrasos sem fronteiras.
    pub biased: bool,
    pub steps: u32,
    pub anchors: Vec<u32>,
    pub lengths: Vec<u32>,
    pub delays: Vec<u32>,
    pub noises: Vec<i32>,
    pub within_ticks: Vec<u32>,
    pub fallback_after_ticks: u32,
    pub recovery_after_ticks: u32,
    pub max_observation_age_ticks: u32,
}

fn around(values: &[u32], low: u32, high: u32, out: &mut BTreeSet<u32>) {
    for value in values {
        for candidate in [value.saturating_sub(1), *value, value.saturating_add(1)] {
            if (low..=high).contains(&candidate) {
                out.insert(candidate);
            }
        }
    }
}

impl Refs {
    pub fn build(base: &Scenario, contracts: &ContractSet, control_ticks: &BTreeSet<u32>) -> Self {
        let steps = base.steps;
        let mut within = BTreeSet::new();
        for contract in &contracts.contracts {
            match contract {
                Contract::BoundedResponse { within_ticks, .. }
                | Contract::BoundedProgress { within_ticks, .. } => {
                    within.insert(*within_ticks);
                }
                _ => {}
            }
        }
        let within_ticks: Vec<u32> = within.into_iter().collect();
        let fallback = base.safety.fallback_after_ticks;
        let recovery = base.safety.recovery_after_ticks;
        let age = base.sensors.max_observation_age_ticks;

        let mut anchors = BTreeSet::from([1, 2, steps.saturating_sub(1).max(1), steps]);
        for tick in control_ticks.iter().take(16) {
            anchors.insert((*tick).clamp(1, steps));
        }
        let mut lengths = BTreeSet::from([1, 2, 3]);
        around(&[fallback, recovery, age], 1, steps, &mut lengths);
        around(&within_ticks, 1, steps, &mut lengths);
        let mut delays = BTreeSet::from([1, 2]);
        around(&[fallback, age], 1, steps.max(2), &mut delays);
        around(&within_ticks, 1, steps.max(2), &mut delays);

        let step = base.vehicle.step_mm.clamp(1, MAX_NOISE_MM);
        let radius = base.mission.arrival_radius_mm.clamp(1, MAX_NOISE_MM);
        let noises: BTreeSet<i32> = [
            1,
            radius,
            step / 2,
            step,
            step.saturating_mul(2),
            step.saturating_mul(4),
            10_000,
            MAX_NOISE_MM,
        ]
        .into_iter()
        .map(|value| value.clamp(1, MAX_NOISE_MM))
        .collect();
        Self {
            biased: true,
            steps,
            anchors: anchors.into_iter().collect(),
            lengths: lengths.into_iter().collect(),
            delays: delays.into_iter().collect(),
            noises: noises.into_iter().collect(),
            within_ticks,
            fallback_after_ticks: fallback,
            recovery_after_ticks: recovery,
            max_observation_age_ticks: age,
        }
    }
}

fn below(rng: &mut XorShift64Star, count: usize) -> usize {
    rng.inclusive_u32(0, count as u32 - 1) as usize
}

fn pick<T: Copy>(rng: &mut XorShift64Star, values: &[T]) -> T {
    values[below(rng, values.len())]
}

fn tick(rng: &mut XorShift64Star, refs: &Refs) -> u32 {
    if refs.biased && rng.inclusive_u32(0, 99) < 55 {
        let anchor = i64::from(pick(rng, &refs.anchors));
        let jitter = i64::from(pick(rng, &[-1_i32, 0, 0, 1]));
        (anchor + jitter).clamp(1, i64::from(refs.steps)) as u32
    } else {
        rng.inclusive_u32(1, refs.steps)
    }
}

fn window(rng: &mut XorShift64Star, refs: &Refs) -> (u32, u32) {
    let length = if refs.biased && rng.inclusive_u32(0, 99) < 60 {
        pick(rng, &refs.lengths)
    } else {
        rng.inclusive_u32(1, refs.steps.min(6))
    }
    .clamp(1, refs.steps);
    let mode = if refs.biased {
        rng.inclusive_u32(0, 99)
    } else {
        100
    };
    let start = if mode < 10 {
        1
    } else if mode < 20 {
        refs.steps - length + 1
    } else {
        tick(rng, refs).min(refs.steps - length + 1)
    };
    (start, start + length - 1)
}

fn delay(rng: &mut XorShift64Star, refs: &Refs, start: u32, end: u32) -> u32 {
    let roll = if refs.biased {
        rng.inclusive_u32(0, 99)
    } else {
        100
    };
    let value = if roll < 35 {
        pick(rng, &refs.delays)
    } else if roll < 65 {
        // O comando executa logo depois do fim da janela de falha.
        end - start + 1 + pick(rng, &[0_u32, 1, 2])
    } else if roll < 85 {
        // O comando vence num tick de referência do controlo.
        let anchor = pick(rng, &refs.anchors);
        let jitter = pick(rng, &[-1_i64, 0, 1]);
        (i64::from(anchor) - i64::from(start) + jitter).max(1) as u32
    } else {
        rng.inclusive_u32(1, (refs.steps / 2).max(2))
    };
    value.clamp(1, MAX_DELAY_TICKS)
}

fn permille(rng: &mut XorShift64Star) -> u16 {
    pick(rng, &[1000_u16, 1000, 1000, 1000, 750, 500, 250])
}

fn rate(rng: &mut XorShift64Star) -> u16 {
    pick(rng, &[100_u16, 250, 500, 750, 900, 1000])
}

/// Pesos por tipo: 0 gps, 1 perda, 2 taxa gps, 3 taxa perda, 4 atraso
/// comunicações, 5 ruído, 6 atraso atuador, 7 perda atuador, 8 movimento contínuo.
const KIND_SLOTS: [u8; 19] = [0, 0, 0, 1, 1, 2, 3, 4, 4, 5, 5, 6, 6, 6, 6, 7, 7, 8, 8];

fn fresh_fault(rng: &mut XorShift64Star, refs: &Refs, kind: u8) -> Fault {
    match kind {
        0 | 1 => {
            let (start, end) = window(rng, refs);
            if kind == 0 {
                Fault::GpsDropout { start, end }
            } else {
                Fault::PacketLoss { start, end }
            }
        }
        2 => Fault::GpsDropoutRate {
            permille: rate(rng),
        },
        3 => Fault::PacketLossRate {
            permille: rate(rng),
        },
        4 => {
            let max = pick(rng, &refs.delays);
            let min = match below(rng, 3) {
                0 => 0,
                1 => max,
                _ => rng.inclusive_u32(0, max),
            };
            Fault::CommDelay { min, max }
        }
        5 => Fault::GpsNoise {
            max_mm: pick(rng, &refs.noises),
        },
        6 => {
            let (start, end) = window(rng, refs);
            Fault::ActuatorDelay {
                start,
                end,
                delay_ticks: delay(rng, refs, start, end),
                permille: permille(rng),
            }
        }
        7 => {
            let (start, end) = window(rng, refs);
            Fault::ActuatorLost {
                start,
                end,
                permille: permille(rng),
            }
        }
        _ => {
            let (start, end) = window(rng, refs);
            Fault::ActuatorContinued {
                start,
                end,
                permille: permille(rng),
            }
        }
    }
}

fn kind_of(fault: &Fault) -> u8 {
    match fault {
        Fault::GpsDropout { .. } => 0,
        Fault::PacketLoss { .. } => 1,
        Fault::GpsDropoutRate { .. } => 2,
        Fault::PacketLossRate { .. } => 3,
        Fault::CommDelay { .. } => 4,
        Fault::GpsNoise { .. } => 5,
        Fault::ActuatorDelay { .. } => 6,
        Fault::ActuatorLost { .. } => 7,
        Fault::ActuatorContinued { .. } => 8,
    }
}

/// Tipos globais só podem aparecer uma vez por candidato.
fn fresh_atom(rng: &mut XorShift64Star, refs: &Refs, uid: u32, existing: &[Atom]) -> Atom {
    let mut kind = pick(rng, &KIND_SLOTS);
    for _ in 0..8 {
        let taken = (2..=5).contains(&kind) && existing.iter().any(|a| kind_of(&a.fault) == kind);
        if !taken {
            break;
        }
        kind = pick(rng, &KIND_SLOTS);
    }
    let taken = (2..=5).contains(&kind) && existing.iter().any(|a| kind_of(&a.fault) == kind);
    if taken {
        kind = 6;
    }
    Atom {
        uid,
        fault: fresh_fault(rng, refs, kind),
    }
}

/// Fase A: 1..=4 átomos novos.
pub fn fresh_set(rng: &mut XorShift64Star, refs: &Refs) -> Vec<Atom> {
    let count = rng.inclusive_u32(1, MAX_ATOMS_PHASE_A);
    let mut atoms: Vec<Atom> = Vec::new();
    for uid in 1..=count {
        let atom = fresh_atom(rng, refs, uid, &atoms);
        atoms.push(atom);
    }
    atoms
}

/// Fase B: acrescenta, remove, desloca, alarga, ajusta ou substitui um átomo.
pub fn mutate(rng: &mut XorShift64Star, refs: &Refs, parent: &[Atom]) -> Vec<Atom> {
    let next_uid = parent.iter().map(|atom| atom.uid).max().unwrap_or(0) + 1;
    for _ in 0..6 {
        let mut atoms = parent.to_vec();
        let op = below(rng, 6);
        let index = below(rng, atoms.len());
        let changed = match op {
            0 if atoms.len() < MAX_ATOMS_PHASE_B => {
                let atom = fresh_atom(rng, refs, next_uid, &atoms);
                atoms.push(atom);
                true
            }
            1 if atoms.len() > 1 => {
                atoms.remove(index);
                true
            }
            2 => shift(rng, refs, &mut atoms[index]),
            3 => widen(rng, refs, &mut atoms[index]),
            4 => tweak(rng, &mut atoms[index]),
            5 => {
                let rest: Vec<Atom> = atoms
                    .iter()
                    .enumerate()
                    .filter(|(i, _)| *i != index)
                    .map(|(_, a)| a.clone())
                    .collect();
                atoms[index] = fresh_atom(rng, refs, next_uid, &rest);
                true
            }
            _ => false,
        };
        if changed && atoms != parent {
            return atoms;
        }
    }
    let mut atoms = parent.to_vec();
    if atoms.len() < MAX_ATOMS_PHASE_B {
        let atom = fresh_atom(rng, refs, next_uid, &atoms);
        atoms.push(atom);
    }
    atoms
}

fn shift(rng: &mut XorShift64Star, refs: &Refs, atom: &mut Atom) -> bool {
    let Some((start, end)) = atom.fault.window() else {
        return false;
    };
    let length = end - start;
    let delta = pick(rng, &[-2_i64, -1, 1, 2]);
    let new_start = (i64::from(start) + delta).clamp(1, i64::from(refs.steps - length)) as u32;
    atom.fault = atom.fault.with_window(new_start, new_start + length);
    true
}

fn widen(rng: &mut XorShift64Star, refs: &Refs, atom: &mut Atom) -> bool {
    let Some((start, end)) = atom.fault.window() else {
        return false;
    };
    let amount = pick(rng, &[1_u32, 1, 2]);
    let (new_start, new_end) = match below(rng, 3) {
        0 => (start.saturating_sub(amount).max(1), end),
        1 => (start, (end + amount).min(refs.steps)),
        _ => (
            start.saturating_sub(amount).max(1),
            (end + amount).min(refs.steps),
        ),
    };
    atom.fault = atom.fault.with_window(new_start, new_end);
    true
}

fn tweak(rng: &mut XorShift64Star, atom: &mut Atom) -> bool {
    let step = i64::from(pick(rng, &[-2_i32, -1, 1, 1, 2]));
    match &mut atom.fault {
        Fault::ActuatorDelay {
            delay_ticks,
            permille: p,
            ..
        } => {
            if below(rng, 4) == 0 {
                *p = permille(rng);
            } else {
                *delay_ticks =
                    (i64::from(*delay_ticks) + step).clamp(1, i64::from(MAX_DELAY_TICKS)) as u32;
            }
            true
        }
        Fault::CommDelay { min, max } => {
            *max = (i64::from(*max) + step).clamp(0, i64::from(MAX_DELAY_TICKS)) as u32;
            *min = (*min).min(*max);
            true
        }
        Fault::GpsNoise { max_mm } => {
            *max_mm = if below(rng, 2) == 0 {
                (*max_mm / 2).max(1)
            } else {
                max_mm.saturating_mul(2).min(MAX_NOISE_MM)
            };
            true
        }
        Fault::GpsDropoutRate { permille: p } | Fault::PacketLossRate { permille: p } => {
            *p = rate(rng);
            true
        }
        Fault::ActuatorLost { permille: p, .. } | Fault::ActuatorContinued { permille: p, .. } => {
            *p = permille(rng);
            true
        }
        _ => false,
    }
}
