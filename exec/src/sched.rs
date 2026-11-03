//! Adaptive scheduling. The number of workers is a pure function of the memory available, the
//! logical processors and the declared limits; the engine re-evaluates it while it runs and parks
//! workers when memory falls. Scheduling changes wall time only: records are ordered by plan
//! index, never by completion.

/// Planned peak of one worker, in MB. Measured peak of one landing worker in the audit: below
/// 10 MB (trace about 0,5 MB plus the verification and its parse); four times that for margin.
pub const PER_WORKER_MB: u64 = 40;
/// Memory left to the rest of the machine, in MB.
pub const RESERVE_MB: u64 = 1024;

pub trait MemoryProbe: Sync {
    /// Memory that can be committed now, in MB; `None` when unknown.
    fn available_mb(&self) -> Option<u64>;
}

/// Workers for the current state: `min(logical, cap, (available - reserve) / per_worker)`, at
/// least 1. `budget_mb`, when declared, caps the available memory.
pub fn workers_for(
    available_mb: Option<u64>,
    budget_mb: Option<u64>,
    logical: usize,
    cap: usize,
    per_worker_mb: u64,
    reserve_mb: u64,
) -> usize {
    let ceiling = logical.min(cap).max(1);
    let available = match (available_mb, budget_mb) {
        (Some(a), Some(b)) => Some(a.min(b)),
        (a, b) => a.or(b),
    };
    match available {
        None => ceiling,
        Some(a) => {
            let by_memory = a.saturating_sub(reserve_mb) / per_worker_mb.max(1);
            (by_memory as usize).clamp(1, ceiling)
        }
    }
}

/// Physical and commit memory available on this machine.
pub struct SystemProbe;

#[cfg(windows)]
mod os {
    #[repr(C)]
    struct MemoryStatusEx {
        length: u32,
        memory_load: u32,
        total_phys: u64,
        avail_phys: u64,
        total_page_file: u64,
        avail_page_file: u64,
        total_virtual: u64,
        avail_virtual: u64,
        avail_extended_virtual: u64,
    }

    #[link(name = "kernel32")]
    unsafe extern "system" {
        fn GlobalMemoryStatusEx(buffer: *mut MemoryStatusEx) -> i32;
    }

    pub fn available_mb() -> Option<u64> {
        let mut s = MemoryStatusEx {
            length: std::mem::size_of::<MemoryStatusEx>() as u32,
            memory_load: 0,
            total_phys: 0,
            avail_phys: 0,
            total_page_file: 0,
            avail_page_file: 0,
            total_virtual: 0,
            avail_virtual: 0,
            avail_extended_virtual: 0,
        };
        // SAFETY: the buffer is a properly sized and initialised MEMORYSTATUSEX whose length
        // field is set, as the API requires; the call writes only inside it.
        let ok = unsafe { GlobalMemoryStatusEx(&mut s) };
        (ok != 0).then(|| s.avail_phys.min(s.avail_page_file) / (1024 * 1024))
    }
}

#[cfg(not(windows))]
mod os {
    pub fn available_mb() -> Option<u64> {
        let text = std::fs::read_to_string("/proc/meminfo").ok()?;
        let line = text.lines().find(|l| l.starts_with("MemAvailable:"))?;
        let kb: u64 = line.split_whitespace().nth(1)?.parse().ok()?;
        Some(kb / 1024)
    }
}

impl MemoryProbe for SystemProbe {
    fn available_mb(&self) -> Option<u64> {
        os::available_mb()
    }
}

/// A probe that reports fixed values in turn, then repeats the last one. For tests.
pub struct ScriptedProbe {
    values: Vec<Option<u64>>,
    calls: std::sync::atomic::AtomicUsize,
}

impl ScriptedProbe {
    pub fn new(values: Vec<Option<u64>>) -> Self {
        Self {
            values,
            calls: std::sync::atomic::AtomicUsize::new(0),
        }
    }
}

impl MemoryProbe for ScriptedProbe {
    fn available_mb(&self) -> Option<u64> {
        let i = self
            .calls
            .fetch_add(1, std::sync::atomic::Ordering::Relaxed);
        self.values
            .get(i.min(self.values.len().saturating_sub(1)))
            .copied()
            .flatten()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn workers_follow_the_smallest_of_processors_cap_and_memory() {
        assert_eq!(workers_for(Some(64_000), None, 16, 64, 40, 1024), 16);
        assert_eq!(workers_for(Some(64_000), None, 16, 4, 40, 1024), 4);
        // 1024 + 5 x 40 MB available: five workers.
        assert_eq!(workers_for(Some(1224), None, 16, 64, 40, 1024), 5);
        // Below the reserve: one worker, never zero.
        assert_eq!(workers_for(Some(500), None, 16, 64, 40, 1024), 1);
        // Unknown memory: processors and cap only.
        assert_eq!(workers_for(None, None, 8, 64, 40, 1024), 8);
        // A declared budget caps what the machine reports.
        assert_eq!(workers_for(Some(64_000), Some(1104), 16, 64, 40, 1024), 2);
        assert_eq!(workers_for(None, Some(1104), 16, 64, 40, 1024), 2);
    }

    #[test]
    fn the_system_probe_reports_a_plausible_value() {
        if let Some(mb) = SystemProbe.available_mb() {
            assert!(mb > 0 && mb < 1 << 24);
        }
    }
}
