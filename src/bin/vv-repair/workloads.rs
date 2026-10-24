//! Cargas emparelhadas: conjuntos de átomos amostrados por semente e as suas
//! projeções por família de falha. Dependem só da base, nunca da candidata.

use std::collections::BTreeSet;

use autonomous_systems_vv_lab::prng::XorShift64Star;
use serde::Serialize;

use crate::atoms::{Atom, Fault, Spec};
use crate::experiment::Experiment;
use crate::sampling::{Refs, fresh_set};
use crate::search::splitmix64;

/// "M6-REPAI": domínio próprio, para não repetir as cargas do `vv-adversary`.
pub const M6_SEED_DOMAIN: u64 = 0x4d36_2d52_4550_4149;

#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Split {
    /// Carga sem átomos, partilhada pelas duas partições.
    Control,
    Tuning,
    Heldout,
}

#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Family {
    Nominal,
    Sensor,
    Timing,
    Actuator,
    Mixed,
}

impl Family {
    /// As famílias de um único tipo de falha, pela ordem das projeções.
    pub const PURE: [Family; 3] = [Family::Sensor, Family::Timing, Family::Actuator];

    pub fn of(fault: &Fault) -> Family {
        match fault {
            Fault::GpsDropout { .. } | Fault::GpsDropoutRate { .. } | Fault::GpsNoise { .. } => {
                Family::Sensor
            }
            Fault::PacketLoss { .. } | Fault::PacketLossRate { .. } | Fault::CommDelay { .. } => {
                Family::Timing
            }
            Fault::ActuatorDelay { .. }
            | Fault::ActuatorLost { .. }
            | Fault::ActuatorContinued { .. } => Family::Actuator,
        }
    }
}

#[derive(Clone, Serialize)]
pub struct Workload {
    pub index: usize,
    pub split: Split,
    pub seed: Option<u64>,
    pub draw: u32,
    pub family: Family,
    pub atoms: Vec<Atom>,
}

fn seeded(seed: u64) -> XorShift64Star {
    XorShift64Star::new(splitmix64(seed ^ splitmix64(M6_SEED_DOMAIN)))
}

/// O conjunto amostrado inteiro e, se tiver mais de uma família, cada projeção.
fn variants(atoms: Vec<Atom>) -> Vec<(Family, Vec<Atom>)> {
    let families: BTreeSet<Family> = atoms.iter().map(|atom| Family::of(&atom.fault)).collect();
    let whole = match families.first() {
        Some(family) if families.len() == 1 => *family,
        _ => Family::Mixed,
    };
    let mut out = Vec::new();
    for family in Family::PURE {
        let subset: Vec<Atom> = atoms
            .iter()
            .filter(|atom| Family::of(&atom.fault) == family)
            .cloned()
            .collect();
        if !subset.is_empty() && subset.len() < atoms.len() {
            out.push((family, subset));
        }
    }
    out.insert(0, (whole, atoms));
    out
}

/// Cargas da suite: controlo sem átomos e, por semente, cada conjunto amostrado
/// e as suas projeções por família. Duplicados (mesma chave) ficam de fora.
pub fn workloads(experiment: &Experiment, refs: &Refs) -> Vec<Workload> {
    let key = |atoms: &[Atom]| {
        Spec {
            atoms: atoms.to_vec(),
            steps: refs.steps,
        }
        .key()
    };
    let mut out = vec![Workload {
        index: 0,
        split: Split::Control,
        seed: None,
        draw: 0,
        family: Family::Nominal,
        atoms: Vec::new(),
    }];
    let mut seen = BTreeSet::from([key(&[])]);
    let splits = [
        (Split::Tuning, &experiment.tuning_seeds),
        (Split::Heldout, &experiment.heldout_seeds),
    ];
    for (split, seeds) in splits {
        for seed in seeds {
            let mut rng = seeded(*seed);
            for draw in 0..experiment.workloads_per_seed {
                for (family, atoms) in variants(fresh_set(&mut rng, refs)) {
                    if seen.insert(key(&atoms)) {
                        out.push(Workload {
                            index: out.len(),
                            split,
                            seed: Some(*seed),
                            draw,
                            family,
                            atoms,
                        });
                    }
                }
            }
        }
    }
    out
}
