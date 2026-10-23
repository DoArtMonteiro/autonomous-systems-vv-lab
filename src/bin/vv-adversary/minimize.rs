//! Minimização com identidade completa preservada (incluindo ticks).
//!
//! Fases: `ddmin` sobre átomos, `truncate` do horizonte (binário, janelas
//! cortadas), `determinize` (taxa -> janelas realizadas, sem exceder o número
//! original de átomos), novo `ddmin`, `simplify` por átomo (janelas, atrasos,
//! ruído, taxas), novo `truncate` e `final_atoms` (verifica 1-minimalidade). Só
//! se aceita um passo se o candidato reproduzir exatamente a identidade alvo com
//! a mesma semente de simulação. O número de avaliações é limitado; resultados
//! repetidos vêm de uma cache e não contam.

use std::collections::BTreeMap;

use autonomous_systems_vv_lab::controller::ControllerPolicyV1;
use serde::Serialize;

use crate::atoms::{Atom, Fault, Spec};
use crate::eval::Ctx;
use crate::identity::{self, Identity};
use crate::simplify::{dropped_runs, simpler};

#[derive(Clone, Debug, Serialize)]
pub struct Step {
    pub phase: &'static str,
    pub description: String,
    pub atoms: usize,
    pub active_fault_ticks: u64,
    pub steps: u32,
}

pub struct Minimized {
    pub spec: Spec,
    pub log: Vec<Step>,
    pub evaluations: u32,
    pub exhausted: bool,
    pub one_minimal_verified: bool,
}

enum Stop {
    Exhausted,
    Fatal(String),
}

struct Min<'a> {
    ctx: &'a Ctx,
    policy: ControllerPolicyV1,
    target: &'a Identity,
    best: Spec,
    original_atoms: usize,
    log: Vec<Step>,
    used: u32,
    limit: u32,
    cache: BTreeMap<String, bool>,
}

pub fn minimize(
    ctx: &Ctx,
    policy: ControllerPolicyV1,
    original: &Spec,
    target: &Identity,
) -> Result<Minimized, String> {
    let mut min = Min {
        ctx,
        policy,
        target,
        best: original.clone(),
        original_atoms: original.atoms.len(),
        log: Vec::new(),
        used: 0,
        limit: ctx.params.minimize_budget,
        cache: BTreeMap::new(),
    };
    let mut exhausted = false;
    let mut verified = false;
    match min.run_all() {
        Ok(done) => verified = done,
        Err(Stop::Exhausted) => exhausted = true,
        Err(Stop::Fatal(message)) => return Err(message),
    }
    Ok(Minimized {
        spec: min.best,
        log: min.log,
        evaluations: min.used,
        exhausted,
        one_minimal_verified: verified && !exhausted,
    })
}

impl Min<'_> {
    fn run_all(&mut self) -> Result<bool, Stop> {
        if !self.test(&self.best.clone())? {
            return Err(Stop::Fatal(format!(
                "original candidate does not reproduce {}",
                self.target.class_label()
            )));
        }
        self.ddmin()?;
        self.truncate()?;
        self.determinize()?;
        self.ddmin()?;
        self.simplify()?;
        self.truncate()?;
        self.final_atoms()
    }

    fn test(&mut self, spec: &Spec) -> Result<bool, Stop> {
        let key = serde_json::to_string(spec).map_err(|e| Stop::Fatal(e.to_string()))?;
        if let Some(known) = self.cache.get(&key) {
            return Ok(*known);
        }
        if self.used >= self.limit {
            return Err(Stop::Exhausted);
        }
        self.used += 1;
        // Montagem inválida nunca é aceite; erro do motor aborta a campanha.
        let preserved = match spec.apply(&self.ctx.base, &self.ctx.actuator) {
            Err(_) => false,
            Ok((scenario, actuator)) => {
                let outcome = self
                    .ctx
                    .evaluate(scenario, actuator, self.policy)
                    .map_err(Stop::Fatal)?;
                identity::violations(&self.target.policy, &outcome)
                    .iter()
                    .any(|found| found == self.target)
            }
        };
        self.cache.insert(key, preserved);
        Ok(preserved)
    }

    fn accept(&mut self, phase: &'static str, description: String, spec: Spec) {
        self.log.push(Step {
            phase,
            description,
            atoms: spec.atoms.len(),
            active_fault_ticks: spec.active_fault_ticks(),
            steps: spec.steps,
        });
        self.best = spec;
    }

    fn with_atoms(&self, atoms: Vec<Atom>) -> Spec {
        Spec {
            atoms,
            steps: self.best.steps,
        }
    }

    /// Troca cada taxa aleatória pelas janelas efetivamente realizadas: o
    /// calendário exógeno fica igual (o sorteio continua a ser consumido).
    fn determinize(&mut self) -> Result<(), Stop> {
        let rates: Vec<(u32, bool)> = self
            .best
            .atoms
            .iter()
            .filter_map(|atom| match atom.fault {
                Fault::GpsDropoutRate { .. } => Some((atom.uid, true)),
                Fault::PacketLossRate { .. } => Some((atom.uid, false)),
                _ => None,
            })
            .collect();
        for (uid, gps) in rates {
            if self.used >= self.limit {
                return Err(Stop::Exhausted);
            }
            self.used += 1;
            let outcome = self.ctx.run(&self.best, self.policy).map_err(Stop::Fatal)?;
            let Some(runs) = dropped_runs(&outcome, gps) else {
                continue;
            };
            let mut next_uid = self.best.atoms.iter().map(|a| a.uid).max().unwrap_or(0) + 1;
            let mut atoms: Vec<Atom> = Vec::new();
            for atom in &self.best.atoms {
                if atom.uid != uid {
                    atoms.push(atom.clone());
                    continue;
                }
                for (start, end) in &runs {
                    let (start, end) = (*start, *end);
                    atoms.push(Atom {
                        uid: next_uid,
                        fault: if gps {
                            Fault::GpsDropout { start, end }
                        } else {
                            Fault::PacketLoss { start, end }
                        },
                    });
                    next_uid += 1;
                }
            }
            let before = self
                .best
                .atoms
                .iter()
                .find(|a| a.uid == uid)
                .map(Atom::describe);
            let candidate = self.with_atoms(atoms);
            // Nunca aumenta o número de átomos acima do original.
            if candidate.atoms.len() > self.original_atoms {
                continue;
            }
            if self.test(&candidate)? {
                let text = format!(
                    "{} -> {} realized window(s)",
                    before.unwrap_or_default(),
                    runs.len()
                );
                self.accept("determinize", text, candidate);
            }
        }
        Ok(())
    }

    fn ddmin(&mut self) -> Result<(), Stop> {
        if !self.best.atoms.is_empty() {
            let empty = self.with_atoms(Vec::new());
            if self.test(&empty)? {
                let count = self.best.atoms.len();
                self.accept("ddmin", format!("removed all {count} atoms"), empty);
                return Ok(());
            }
        }
        let mut granularity = 2;
        loop {
            let atoms = self.best.atoms.clone();
            let len = atoms.len();
            if len < 2 {
                return Ok(());
            }
            granularity = granularity.min(len);
            let chunks: Vec<Vec<Atom>> = (0..granularity)
                .map(|i| atoms[i * len / granularity..(i + 1) * len / granularity].to_vec())
                .collect();
            let mut reduced = false;
            for chunk in &chunks {
                let candidate = self.with_atoms(chunk.clone());
                if self.test(&candidate)? {
                    self.accept("ddmin", format!("kept {}", uids(chunk)), candidate);
                    granularity = 2;
                    reduced = true;
                    break;
                }
            }
            if !reduced {
                for chunk in &chunks {
                    let rest: Vec<Atom> = atoms
                        .iter()
                        .filter(|atom| !chunk.contains(atom))
                        .cloned()
                        .collect();
                    let candidate = self.with_atoms(rest);
                    if self.test(&candidate)? {
                        self.accept("ddmin", format!("dropped {}", uids(chunk)), candidate);
                        granularity = granularity.saturating_sub(1).max(2);
                        reduced = true;
                        break;
                    }
                }
            }
            if !reduced {
                if granularity >= len {
                    return Ok(());
                }
                granularity = (granularity * 2).min(len);
            }
        }
    }

    fn simplify(&mut self) -> Result<(), Stop> {
        for _ in 0..3 {
            let mut progress = false;
            for index in 0..self.best.atoms.len() {
                while self.simplify_atom(index)? {
                    progress = true;
                }
            }
            if !progress {
                break;
            }
        }
        Ok(())
    }

    fn simplify_atom(&mut self, index: usize) -> Result<bool, Stop> {
        let atom = self.best.atoms[index].clone();
        for (label, fault) in simpler(&atom.fault) {
            let mut candidate = self.best.clone();
            candidate.atoms[index].fault = fault.clone();
            if self.test(&candidate)? {
                let text = format!(
                    "#{} {label}: {} -> {}",
                    atom.uid,
                    atom.fault.describe(),
                    fault.describe()
                );
                self.accept("simplify", text, candidate);
                return Ok(true);
            }
        }
        Ok(false)
    }

    fn truncate(&mut self) -> Result<(), Stop> {
        let deadline = self
            .target
            .deadline_tick
            .map_or(0, |tick| u32::try_from(tick).unwrap_or(u32::MAX));
        let floor = self.target.violation_tick.max(deadline).max(1);
        let current = self.best.steps;
        if floor >= current {
            return Ok(());
        }
        let first = self.best.truncate(floor);
        if self.test(&first)? {
            self.accept("truncate", format!("steps {current} -> {floor}"), first);
            return Ok(());
        }
        let (mut low, mut high) = (floor + 1, current - 1);
        let mut found = None;
        while low <= high {
            let middle = low + (high - low) / 2;
            if self.test(&self.best.truncate(middle))? {
                found = Some(middle);
                high = middle - 1;
            } else {
                low = middle + 1;
            }
        }
        if let Some(steps) = found {
            let candidate = self.best.truncate(steps);
            self.accept("truncate", format!("steps {current} -> {steps}"), candidate);
        }
        Ok(())
    }

    /// Passagem completa sem remoções aceites = 1-minimal em átomos.
    fn final_atoms(&mut self) -> Result<bool, Stop> {
        loop {
            let mut removed = false;
            for uid in self.best.atoms.iter().map(|a| a.uid).collect::<Vec<_>>() {
                let rest: Vec<Atom> = self
                    .best
                    .atoms
                    .iter()
                    .filter(|atom| atom.uid != uid)
                    .cloned()
                    .collect();
                let candidate = self.with_atoms(rest);
                if self.test(&candidate)? {
                    self.accept("final_atoms", format!("dropped #{uid}"), candidate);
                    removed = true;
                }
            }
            if !removed {
                return Ok(true);
            }
        }
    }
}

fn uids(atoms: &[Atom]) -> String {
    atoms
        .iter()
        .map(|atom| format!("#{}", atom.uid))
        .collect::<Vec<_>>()
        .join(",")
}
