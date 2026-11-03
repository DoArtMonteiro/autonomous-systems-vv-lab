//! Out-of-process execution of a domain host. One call is one process with stdin closed, piped and
//! capped stdout and stderr, a wall-clock timeout (measured here, outside the simulation) and no
//! console window. A host that overruns either limit is stopped and the call fails.

use std::ffi::OsString;
use std::io::Read;
use std::path::Path;
use std::process::{Child, Command, Stdio};
use std::thread;
use std::time::{Duration, Instant};

const MAX_STDERR_BYTES: u64 = 64 * 1024;

#[derive(Debug)]
pub struct HostOutput {
    pub code: i32,
    pub stdout: Vec<u8>,
    pub stderr: String,
}

#[derive(Debug)]
pub enum HostFailure {
    Spawn(String),
    Timeout(u32),
    OutputTooLarge(u64),
    NoExitCode,
}

impl std::fmt::Display for HostFailure {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            HostFailure::Spawn(e) => write!(f, "the domain host could not start: {e}"),
            HostFailure::Timeout(s) => write!(f, "the domain host did not finish within {s} s"),
            HostFailure::OutputTooLarge(n) => {
                write!(f, "the domain host wrote more than {n} bytes to stdout")
            }
            HostFailure::NoExitCode => write!(f, "the domain host ended without an exit code"),
        }
    }
}

fn capped_reader<R: Read + Send + 'static>(
    mut reader: R,
    cap: u64,
) -> thread::JoinHandle<(Vec<u8>, bool)> {
    thread::spawn(move || {
        let mut buf = Vec::new();
        let mut limited = (&mut reader).take(cap + 1);
        let _ = limited.read_to_end(&mut buf);
        let over = buf.len() as u64 > cap;
        if over {
            buf.truncate(cap as usize);
            // Drain so the child never blocks on a full pipe before it is stopped.
            let _ = std::io::copy(&mut reader, &mut std::io::sink());
        }
        (buf, over)
    })
}

fn no_window(cmd: &mut Command) {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }
    #[cfg(not(windows))]
    let _ = cmd;
}

fn stop(child: &mut Child) {
    let _ = child.kill();
    let _ = child.wait();
}

pub fn call(
    executable: &Path,
    args: &[OsString],
    timeout_s: u32,
    max_stdout: u64,
) -> Result<HostOutput, HostFailure> {
    let mut cmd = Command::new(executable);
    cmd.args(args)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    if let Some(dir) = executable.parent() {
        cmd.current_dir(dir);
    }
    no_window(&mut cmd);
    let mut child = cmd.spawn().map_err(|e| HostFailure::Spawn(e.to_string()))?;
    let out = capped_reader(child.stdout.take().expect("piped stdout"), max_stdout);
    let err = capped_reader(child.stderr.take().expect("piped stderr"), MAX_STDERR_BYTES);
    let deadline = Instant::now() + Duration::from_secs(u64::from(timeout_s));
    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break status,
            Ok(None) if Instant::now() >= deadline => {
                stop(&mut child);
                return Err(HostFailure::Timeout(timeout_s));
            }
            Ok(None) => thread::sleep(Duration::from_millis(10)),
            Err(e) => {
                stop(&mut child);
                return Err(HostFailure::Spawn(e.to_string()));
            }
        }
    };
    let (stdout, over) = out.join().unwrap_or_default();
    let (stderr, _) = err.join().unwrap_or_default();
    if over {
        return Err(HostFailure::OutputTooLarge(max_stdout));
    }
    let code = status.code().ok_or(HostFailure::NoExitCode)?;
    Ok(HostOutput {
        code,
        stdout,
        stderr: String::from_utf8_lossy(&stderr).trim().to_owned(),
    })
}
