r"""Benchmark of the Cinematic View, one graphics profile per process, run one after the other.

    python scripts/cinematic/bench.py --godot <Godot_v4.7.2-stable_win64_console.exe> --run <run dir>
        --env <pack dir> --out <dir> [--profiles performance,balanced,high,ultra] [--seconds 12]

For each profile it starts the renderer at 1440x900 with --bench (vsync off, the record replayed
from its first to its last sample over --seconds of wall time with the Auto camera, after 120
warm-up frames), and measures outside the renderer:
- wall time from process start to the FIRST_FRAME line (first frame of the built scene);
- peak working set and peak private bytes of the Godot process (psutil, sampled every 100 ms);
and records what the renderer reports: frame-time percentiles from the wall time between frames,
video memory in use (RenderingServer RENDERING_INFO_VIDEO_MEM_USED, texture and buffer parts).

The console executable starts the GUI executable as a child; memory is that of the child.
Requires psutil. These are measurements of one machine; they are not a model of other machines.
"""

import argparse
import json
import os
import platform
import subprocess
import sys
import threading
import time

import psutil

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PROJECT = os.path.join(REPO, "desktop", "cinematic")


def godot_process(proc):
    """The process that renders: the GUI child of the console wrapper, or the process itself."""
    p = psutil.Process(proc.pid)
    for _ in range(100):
        kids = [c for c in p.children(recursive=True) if c.name().lower().startswith("godot")]
        if kids:
            return kids[0]
        time.sleep(0.05)
    return p


def run_one(a, profile):
    out_json = os.path.join(a.out, f"bench-{profile}.json")
    cmd = [a.godot, "--path", PROJECT, "--resolution", "1440x900", "--", "--run", a.run, "--env", a.env,
           "--profile", profile, "--camera", "director", "--bench", out_json, "--bench-seconds", str(a.seconds)]
    t0 = time.perf_counter()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    gp = godot_process(proc)
    peak = {"rss": 0, "private": 0}
    done = threading.Event()

    def sample():
        while not done.is_set():
            try:
                m = gp.memory_info()
                peak["rss"] = max(peak["rss"], m.rss)
                peak["private"] = max(peak["private"], getattr(m, "private", 0))
            except psutil.Error:
                pass
            time.sleep(0.1)

    th = threading.Thread(target=sample, daemon=True)
    th.start()
    first = None
    lines = []
    for line in proc.stdout:
        lines.append(line.rstrip())
        if line.startswith("FIRST_FRAME") and first is None:
            first = time.perf_counter() - t0
    proc.wait(timeout=600)
    done.set()
    th.join()
    with open(out_json, encoding="utf-8") as f:
        r = json.load(f)
    r["harness"] = {
        "command": " ".join(cmd[1:]).replace(REPO, "<repo>"),
        "wall_s_to_first_frame": round(first, 3) if first is not None else None,
        "engine_ms_to_first_frame": next((int(l.split()[1]) for l in lines if l.startswith("FIRST_FRAME")), None),
        "peak_working_set_bytes": peak["rss"],
        "peak_private_bytes": peak["private"],
        "exit": proc.returncode,
        "log_tail": [l for l in lines if l.startswith("cinematic")][-3:],
    }
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(r, f, indent=1)
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--godot", required=True)
    ap.add_argument("--run", required=True)
    ap.add_argument("--env", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--profiles", default="performance,balanced,high,ultra")
    ap.add_argument("--seconds", type=float, default=12.0)
    a = ap.parse_args()
    # Godot resolves relative paths against its own working directory: pass absolute ones.
    a.out, a.run, a.env = (os.path.abspath(x) for x in (a.out, a.run, a.env))
    os.makedirs(a.out, exist_ok=True)
    rows = []
    for p in a.profiles.split(","):
        r = run_one(a, p)
        h = r["harness"]
        rows.append({"profile": p, "first_frame_s": h["wall_s_to_first_frame"], "p50_ms": round(r["frame_ms_p50"], 2), "p99_ms": round(r["frame_ms_p99"], 2),
                     "frames": r["frames"], "vram_used_mb": round(r["video_mem_used_bytes"] / 1048576), "working_set_mb": round(h["peak_working_set_bytes"] / 1048576),
                     "private_mb": round(h["peak_private_bytes"] / 1048576)})
        print(json.dumps(rows[-1]), flush=True)
    summary = {"machine": {"platform": platform.platform(), "processor": platform.processor(), "python": sys.version.split()[0]}, "rows": rows}
    with open(os.path.join(a.out, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=1)


if __name__ == "__main__":
    main()
