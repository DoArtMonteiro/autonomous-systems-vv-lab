"""Run one command inside a Windows Job Object and report measured resource use.

M12 performance audit tool. Outside the simulation: it only observes a process tree.

The job gives exact figures for the whole tree (children inherit the job): peak committed
memory (PeakJobMemoryUsed), total user and kernel CPU time, and the number of processes. A
memory cap (JOB_OBJECT_LIMIT_JOB_MEMORY) stops a runaway benchmark before it exhausts the
machine. A sampler thread records system-wide CPU utilisation (GetSystemTimes), available
physical memory and the job's peak commit every `--interval` seconds.

Usage:
    python spikes/m12-perf/jobrun.py --label build --cap-mb 8192 --out runs/m12-perf/x.json -- cargo build
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import platform
import subprocess
import sys
import threading
import time
from pathlib import Path

k32 = ctypes.WinDLL("kernel32", use_last_error=True)

JobObjectBasicAccountingInformation = 1
JobObjectExtendedLimitInformation = 9
JOB_OBJECT_LIMIT_JOB_MEMORY = 0x200
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
PROCESS_ALL_ACCESS = 0x1FFFFF
k32.CreateJobObjectW.restype = wt.HANDLE
k32.OpenProcess.restype = wt.HANDLE


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [(n, ctypes.c_ulonglong) for n in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class BASIC_LIMIT(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wt.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wt.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wt.DWORD),
        ("SchedulingClass", wt.DWORD),
    ]


class EXTENDED_LIMIT(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", BASIC_LIMIT),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class BASIC_ACCOUNTING(ctypes.Structure):
    _fields_ = [
        ("TotalUserTime", ctypes.c_longlong),
        ("TotalKernelTime", ctypes.c_longlong),
        ("ThisPeriodTotalUserTime", ctypes.c_longlong),
        ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
        ("TotalPageFaultCount", wt.DWORD),
        ("TotalProcesses", wt.DWORD),
        ("ActiveProcesses", wt.DWORD),
        ("TotalTerminatedProcesses", wt.DWORD),
    ]


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", wt.DWORD), ("dwMemoryLoad", wt.DWORD),
        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def mem_status() -> dict:
    m = MEMORYSTATUSEX()
    m.dwLength = ctypes.sizeof(m)
    k32.GlobalMemoryStatusEx(ctypes.byref(m))
    return {"avail_phys_mb": m.ullAvailPhys // 2**20, "total_phys_mb": m.ullTotalPhys // 2**20,
            "avail_commit_mb": m.ullAvailPageFile // 2**20, "commit_limit_mb": m.ullTotalPageFile // 2**20}


def system_times() -> tuple[int, int, int]:
    idle, kern, user = wt.FILETIME(), wt.FILETIME(), wt.FILETIME()
    k32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kern), ctypes.byref(user))

    def f(t: wt.FILETIME) -> int:
        return (t.dwHighDateTime << 32) | t.dwLowDateTime

    return f(idle), f(kern), f(user)


def query(job, cls, struct):
    s = struct()
    if not k32.QueryInformationJobObject(job, cls, ctypes.byref(s), ctypes.sizeof(s), None):
        raise OSError(ctypes.get_last_error())
    return s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--cap-mb", type=int, default=8192, help="job commit cap; the tree is killed above it")
    ap.add_argument("--interval", type=float, default=0.25)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--cwd", type=Path)
    ap.add_argument("--quiet", action="store_true", help="discard the command's stdout")
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    cmd = a.cmd[1:] if a.cmd and a.cmd[0] == "--" else a.cmd
    if not cmd:
        ap.error("missing command")

    job = k32.CreateJobObjectW(None, None)
    lim = EXTENDED_LIMIT()
    lim.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_JOB_MEMORY | JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    lim.JobMemoryLimit = a.cap_mb * 2**20
    if not k32.SetInformationJobObject(job, JobObjectExtendedLimitInformation, ctypes.byref(lim), ctypes.sizeof(lim)):
        raise OSError(ctypes.get_last_error())

    mem_before = mem_status()
    s0 = system_times()
    t0 = time.perf_counter()
    # The root is assigned right after spawn; its children start later and inherit the job.
    proc = subprocess.Popen(cmd, cwd=a.cwd, stdout=subprocess.DEVNULL if a.quiet else None)
    h = k32.OpenProcess(PROCESS_ALL_ACCESS, False, proc.pid)
    if not k32.AssignProcessToJobObject(wt.HANDLE(job), wt.HANDLE(h)):
        raise OSError(ctypes.get_last_error())

    samples: list[dict] = []
    stop = threading.Event()

    def sampler() -> None:
        prev = system_times()
        while not stop.wait(a.interval):
            cur = system_times()
            di, dk, du = (c - p for c, p in zip(cur, prev))
            busy = (dk + du - di) / (dk + du) if dk + du else 0.0
            ext = query(job, JobObjectExtendedLimitInformation, EXTENDED_LIMIT)
            acc = query(job, JobObjectBasicAccountingInformation, BASIC_ACCOUNTING)
            samples.append({"t": round(time.perf_counter() - t0, 3), "sys_cpu": round(busy, 4),
                            "job_cpu_s": (acc.TotalUserTime + acc.TotalKernelTime) / 1e7,
                            "active": acc.ActiveProcesses, "avail_phys_mb": mem_status()["avail_phys_mb"],
                            "job_peak_mb": ext.PeakJobMemoryUsed // 2**20})
            prev = cur

    th = threading.Thread(target=sampler, daemon=True)
    th.start()
    rc = proc.wait()
    wall = time.perf_counter() - t0
    # Give descendants a short grace period. MSVC link.exe leaves vctip.exe (telemetry) alive for
    # minutes; it is not part of the measured work, and closing the job kills it.
    grace_end = time.perf_counter() + 3.0
    while (query(job, JobObjectBasicAccountingInformation, BASIC_ACCOUNTING).ActiveProcesses
           and time.perf_counter() < grace_end):
        time.sleep(0.05)
    lingering = query(job, JobObjectBasicAccountingInformation, BASIC_ACCOUNTING).ActiveProcesses
    stop.set()
    th.join()
    s1 = system_times()
    ext = query(job, JobObjectExtendedLimitInformation, EXTENDED_LIMIT)
    acc = query(job, JobObjectBasicAccountingInformation, BASIC_ACCOUNTING)
    di, dk, du = (c - p for c, p in zip(s1, s0))
    cpu_s = (acc.TotalUserTime + acc.TotalKernelTime) / 1e7
    ncpu = os.cpu_count() or 1
    rep = {
        "label": a.label, "cmd": cmd, "exit": rc, "wall_s": round(wall, 3),
        "job_cpu_s": round(cpu_s, 3), "job_user_s": round(acc.TotalUserTime / 1e7, 3),
        "job_kernel_s": round(acc.TotalKernelTime / 1e7, 3),
        "avg_cores_busy": round(cpu_s / wall, 2), "job_cpu_util_of_machine": round(cpu_s / wall / ncpu, 4),
        "sys_cpu_util": round((dk + du - di) / (dk + du), 4) if dk + du else None,
        "peak_job_commit_mb": ext.PeakJobMemoryUsed // 2**20,
        "peak_process_commit_mb": ext.PeakProcessMemoryUsed // 2**20,
        "processes": acc.TotalProcesses, "lingering_after_root_exit": lingering, "page_faults": acc.TotalPageFaultCount,
        "io_read_mb": round(ext.IoInfo.ReadTransferCount / 2**20, 1),
        "io_write_mb": round(ext.IoInfo.WriteTransferCount / 2**20, 1),
        "cap_mb": a.cap_mb, "logical_cpus": ncpu, "mem_before": mem_before, "mem_after": mem_status(),
        "min_avail_phys_mb": min((s["avail_phys_mb"] for s in samples), default=None),
        "machine": platform.processor(), "samples": samples,
    }
    k32.CloseHandle(wt.HANDLE(h))
    k32.CloseHandle(wt.HANDLE(job))
    brief = {k: rep[k] for k in ("label", "exit", "wall_s", "job_cpu_s", "avg_cores_busy",
                                 "peak_job_commit_mb", "peak_process_commit_mb", "processes",
                                 "io_write_mb", "min_avail_phys_mb")}
    print("JOBRUN " + json.dumps(brief), file=sys.stderr)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(rep, indent=1), encoding="utf-8")
    return rc


if __name__ == "__main__":
    sys.exit(main())
