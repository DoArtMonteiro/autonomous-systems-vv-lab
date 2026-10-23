//! Átomos de falha tipados e a sua aplicação a cenário e atuador.
//!
//! Só a configuração de falhas é gerada; a geometria e `safety.*` nunca mudam.
//! Falhas já presentes na base ficam como fundo fixo (cortadas ao horizonte).

use autonomous_systems_vv_lab::actuator::{ActuatorConfig, ActuatorFault, ActuatorFaultWindow};
use autonomous_systems_vv_lab::model::{Scenario, TickWindow};
use serde::Serialize;

pub const ID_PREFIX: &str = "adv-";

#[derive(Clone, Debug, Eq, Ord, PartialEq, PartialOrd, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Fault {
    GpsDropout {
        start: u32,
        end: u32,
    },
    PacketLoss {
        start: u32,
        end: u32,
    },
    GpsDropoutRate {
        permille: u16,
    },
    PacketLossRate {
        permille: u16,
    },
    CommDelay {
        min: u32,
        max: u32,
    },
    /// Proxy de entradas em conflito: a observação discorda da verdade.
    GpsNoise {
        max_mm: i32,
    },
    ActuatorDelay {
        start: u32,
        end: u32,
        delay_ticks: u32,
        permille: u16,
    },
    ActuatorLost {
        start: u32,
        end: u32,
        permille: u16,
    },
    ActuatorContinued {
        start: u32,
        end: u32,
        permille: u16,
    },
}

impl Fault {
    pub fn window(&self) -> Option<(u32, u32)> {
        match self {
            Self::GpsDropout { start, end }
            | Self::PacketLoss { start, end }
            | Self::ActuatorDelay { start, end, .. }
            | Self::ActuatorLost { start, end, .. }
            | Self::ActuatorContinued { start, end, .. } => Some((*start, *end)),
            _ => None,
        }
    }

    pub fn with_window(&self, start: u32, end: u32) -> Self {
        let mut copy = self.clone();
        match &mut copy {
            Self::GpsDropout { start: s, end: e }
            | Self::PacketLoss { start: s, end: e }
            | Self::ActuatorDelay {
                start: s, end: e, ..
            }
            | Self::ActuatorLost {
                start: s, end: e, ..
            }
            | Self::ActuatorContinued {
                start: s, end: e, ..
            } => {
                *s = start;
                *e = end;
            }
            _ => {}
        }
        copy
    }

    /// Ticks de falha ativa: comprimento da janela (+ atraso do atuador);
    /// falhas globais contam `steps` (+ atraso máximo das comunicações).
    pub fn active_ticks(&self, steps: u32) -> u64 {
        let length = |s: u32, e: u32| u64::from(e - s + 1);
        match self {
            Self::GpsDropout { start, end }
            | Self::PacketLoss { start, end }
            | Self::ActuatorLost { start, end, .. }
            | Self::ActuatorContinued { start, end, .. } => length(*start, *end),
            Self::ActuatorDelay {
                start,
                end,
                delay_ticks,
                ..
            } => length(*start, *end) + u64::from(*delay_ticks),
            Self::GpsDropoutRate { .. } | Self::PacketLossRate { .. } | Self::GpsNoise { .. } => {
                u64::from(steps)
            }
            Self::CommDelay { max, .. } => u64::from(steps) + u64::from(*max),
        }
    }

    pub fn describe(&self) -> String {
        match self {
            Self::GpsDropout { start, end } => format!("gps_dropout[{start}..{end}]"),
            Self::PacketLoss { start, end } => format!("packet_loss[{start}..{end}]"),
            Self::GpsDropoutRate { permille } => format!("gps_dropout_rate({permille}/1000)"),
            Self::PacketLossRate { permille } => format!("packet_loss_rate({permille}/1000)"),
            Self::CommDelay { min, max } => format!("comm_delay[{min}..{max}]"),
            Self::GpsNoise { max_mm } => format!("gps_noise({max_mm}mm)"),
            Self::ActuatorDelay {
                start,
                end,
                delay_ticks,
                permille,
            } => format!("actuator_delay[{start}..{end}] +{delay_ticks}t p={permille}/1000"),
            Self::ActuatorLost {
                start,
                end,
                permille,
            } => format!("actuator_lost[{start}..{end}] p={permille}/1000"),
            Self::ActuatorContinued {
                start,
                end,
                permille,
            } => format!("actuator_continued[{start}..{end}] p={permille}/1000"),
        }
    }
}

#[derive(Clone, Debug, Eq, Ord, PartialEq, PartialOrd, Serialize)]
pub struct Atom {
    /// Identificador estável: remover outros átomos não o renumera.
    pub uid: u32,
    #[serde(flatten)]
    pub fault: Fault,
}

impl Atom {
    pub fn describe(&self) -> String {
        format!("#{} {}", self.uid, self.fault.describe())
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct Spec {
    pub atoms: Vec<Atom>,
    pub steps: u32,
}

impl Spec {
    pub fn active_fault_ticks(&self) -> u64 {
        self.atoms
            .iter()
            .map(|atom| atom.fault.active_ticks(self.steps))
            .sum()
    }

    /// Chave canónica (ignora a ordem e os `uid`).
    pub fn key(&self) -> String {
        let mut faults: Vec<&Fault> = self.atoms.iter().map(|atom| &atom.fault).collect();
        faults.sort();
        format!(
            "{}|{}",
            self.steps,
            serde_json::to_string(&faults).unwrap_or_default()
        )
    }

    /// Reduz o horizonte; janelas cortadas ou removidas se ficarem fora.
    pub fn truncate(&self, steps: u32) -> Spec {
        let atoms = self
            .atoms
            .iter()
            .filter_map(|atom| match atom.fault.window() {
                Some((start, _)) if start > steps => None,
                Some((start, end)) => Some(Atom {
                    uid: atom.uid,
                    fault: atom.fault.with_window(start, end.min(steps)),
                }),
                None => Some(atom.clone()),
            })
            .collect();
        Spec { atoms, steps }
    }

    /// Aplica os átomos à base e valida o resultado.
    pub fn apply(
        &self,
        base: &Scenario,
        actuator: &ActuatorConfig,
    ) -> Result<(Scenario, ActuatorConfig), String> {
        if self.steps == 0 || self.steps > base.steps {
            return Err("steps must be within 1..=base steps".into());
        }
        let mut scenario = base.clone();
        scenario.steps = self.steps;
        let mut config = actuator.clone();
        clip_windows(&mut scenario.sensors.gps.dropout_windows, self.steps);
        clip_windows(
            &mut scenario.sensors.communication.packet_loss_windows,
            self.steps,
        );
        for fault in &mut config.faults {
            let windows = fault_windows_mut(fault);
            windows.retain(|window| window.start_tick <= self.steps);
            for window in windows.iter_mut() {
                window.end_tick = window.end_tick.min(self.steps);
            }
        }
        config
            .faults
            .retain_mut(|fault| !fault_windows_mut(fault).is_empty());
        for atom in &self.atoms {
            apply_atom(atom, &mut scenario, &mut config);
        }
        scenario.validate().map_err(|error| error.to_string())?;
        config.validate(self.steps)?;
        Ok((scenario, config))
    }
}

fn apply_atom(atom: &Atom, scenario: &mut Scenario, config: &mut ActuatorConfig) {
    let id = format!("{ID_PREFIX}{:03}", atom.uid);
    let window = |start: u32, end: u32| {
        vec![ActuatorFaultWindow {
            start_tick: start,
            end_tick: end,
        }]
    };
    let sensors = &mut scenario.sensors;
    match &atom.fault {
        Fault::GpsDropout { start, end } => sensors.gps.dropout_windows.push(TickWindow {
            start_tick: *start,
            end_tick: *end,
        }),
        Fault::PacketLoss { start, end } => {
            sensors.communication.packet_loss_windows.push(TickWindow {
                start_tick: *start,
                end_tick: *end,
            })
        }
        Fault::GpsDropoutRate { permille } => {
            sensors.gps.dropout_permille = sensors.gps.dropout_permille.max(*permille)
        }
        Fault::PacketLossRate { permille } => {
            sensors.communication.packet_loss_permille =
                sensors.communication.packet_loss_permille.max(*permille)
        }
        Fault::CommDelay { min, max } => {
            let low = sensors.communication.delay_min_ticks.max(*min);
            sensors.communication.delay_min_ticks = low;
            sensors.communication.delay_max_ticks =
                sensors.communication.delay_max_ticks.max(*max).max(low);
        }
        Fault::GpsNoise { max_mm } => {
            sensors.gps.noise_max_mm = sensors.gps.noise_max_mm.max(*max_mm)
        }
        Fault::ActuatorDelay {
            start,
            end,
            delay_ticks,
            permille,
        } => config.faults.push(ActuatorFault::DelayedMovement {
            id,
            windows: window(*start, *end),
            probability_permille: *permille,
            delay_ticks: *delay_ticks,
        }),
        Fault::ActuatorLost {
            start,
            end,
            permille,
        } => config.faults.push(ActuatorFault::LostMovement {
            id,
            windows: window(*start, *end),
            probability_permille: *permille,
        }),
        Fault::ActuatorContinued {
            start,
            end,
            permille,
        } => config.faults.push(ActuatorFault::ContinuedMovement {
            id,
            windows: window(*start, *end),
            probability_permille: *permille,
        }),
    }
}

fn clip_windows(windows: &mut Vec<TickWindow>, steps: u32) {
    windows.retain(|window| window.start_tick <= steps);
    for window in windows.iter_mut() {
        window.end_tick = window.end_tick.min(steps);
    }
}

fn fault_windows_mut(fault: &mut ActuatorFault) -> &mut Vec<ActuatorFaultWindow> {
    match fault {
        ActuatorFault::LostMovement { windows, .. }
        | ActuatorFault::DelayedMovement { windows, .. }
        | ActuatorFault::ContinuedMovement { windows, .. } => windows,
    }
}

/// Os identificadores do fundo não podem colidir com os dos átomos.
pub fn background_ids_are_free(actuator: &ActuatorConfig) -> bool {
    actuator.faults.iter().all(|fault| {
        let id = match fault {
            ActuatorFault::LostMovement { id, .. }
            | ActuatorFault::DelayedMovement { id, .. }
            | ActuatorFault::ContinuedMovement { id, .. } => id,
        };
        !id.starts_with(ID_PREFIX)
    })
}
