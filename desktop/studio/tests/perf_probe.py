r"""Measures V&V Lab Studio from the outside: cold start, the path to the first rocket landing on screen,
3D playback frame times and the memory of the studio process tree.

Nothing here runs inside the simulation; every number is wall-clock time or operating-system memory
of the desktop shell on the machine that runs the script. The script prints one JSON document.

    python desktop/studio/tests/perf_probe.py --exe "%LOCALAPPDATA%\VV Lab Studio\vv-studio.exe" --flow m11
    python desktop/studio/tests/perf_probe.py --exe desktop/target/release/vv-studio.exe --domains desktop/target/release/domains --flow m15

`--flow m11` drives the 0.11 interface (Prepare, rocket domain, nominal demonstration). `--flow m15`
drives the M15 home screen (one click on the first showcase mission). Each click is counted.
"""

import argparse
import json
import os
import platform
import statistics
import subprocess
import tempfile
import time
import urllib.request

from playwright.sync_api import sync_playwright

FLOWS = {
    # Selectors clicked, in order, from the first ready screen to a playing rocket landing.
    "m11": [
        ".nav-btn[data-view='prepare']",
        "button[data-domain='rocket-landing']",
        "button[data-demo='nominal-landing']",
    ],
    "m15": [
        "#view-home [data-experience='first-landing'] [data-action='launch']",
    ],
}

READY = "window.__studio && document.getElementById('startup') && document.getElementById('startup').hidden"
RUN_SHOWN = "window.__studio && window.__studio.run() && window.__studio.run().scene === 'rocket-3d' && document.querySelector('.r3d canvas')"


def wait(page, js, timeout=90.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if page.evaluate(js):
                return time.time()
        except Exception:
            pass
        time.sleep(0.02)
    raise TimeoutError(js)


def tree_memory(root_pid):
    """Working set and private bytes of the studio process and all its descendants (WebView2)."""
    ps = (
        "$all = Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name,WorkingSetSize,PrivatePageCount;"
        "$all | ConvertTo-Json -Compress"
    )
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True).stdout
    rows = json.loads(out)
    kids = {}
    for r in rows:
        kids.setdefault(r["ParentProcessId"], []).append(r)
    by_pid = {r["ProcessId"]: r for r in rows}
    todo, seen = [root_pid], []
    while todo:
        p = todo.pop()
        if p in by_pid:
            seen.append(by_pid[p])
        todo.extend(r["ProcessId"] for r in kids.get(p, []))
    return {
        "processes": len(seen),
        "working_set_mb": round(sum(r["WorkingSetSize"] for r in seen) / 2**20, 1),
        "private_mb": round(sum(r["PrivatePageCount"] for r in seen) / 2**20, 1),
        "by_name": sorted({r["Name"] for r in seen}),
    }


FRAMES_JS = """async (ms) => {
  const d = [];
  let last = performance.now();
  const t0 = last;
  await new Promise((res) => {
    const f = (t) => { d.push(t - last); last = t; if (t - t0 < ms) requestAnimationFrame(f); else res(); };
    requestAnimationFrame(f);
  });
  d.shift();
  return d;
}"""


def frame_stats(page, ms=5000):
    d = sorted(page.evaluate(FRAMES_JS, ms))
    if not d:
        return None
    pct = lambda q: round(d[min(len(d) - 1, int(q * len(d)))], 2)
    return {"frames": len(d), "mean_ms": round(statistics.fmean(d), 2), "p50_ms": pct(0.5), "p95_ms": pct(0.95), "p99_ms": pct(0.99), "max_ms": round(d[-1], 2), "over_33ms": sum(1 for x in d if x > 33.4)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", required=True)
    ap.add_argument("--domains", default="")
    ap.add_argument("--flow", choices=sorted(FLOWS), required=True)
    ap.add_argument("--port", type=int, default=9333)
    ap.add_argument("--size", default="1440x900")
    a = ap.parse_args()
    exe = os.path.abspath(os.path.expandvars(a.exe))
    w, h = (int(x) for x in a.size.split("x"))
    env = dict(os.environ)
    for k in ("VVLAB_DOMAINS", "VVLAB_EXTRA_DOMAINS", "VVLAB_EXEC", "VVLAB_CLAIMS"):
        env.pop(k, None)
    if a.domains:
        root = os.path.dirname(os.path.abspath(a.domains))
        env["VVLAB_DOMAINS"] = os.path.abspath(a.domains)
        env["VVLAB_EXEC"] = os.path.join(root, "engines", "vv-exec.exe")
        env["VVLAB_CLAIMS"] = os.path.join(root, "discovery", "claims")
    env["VVLAB_LIBRARY"] = tempfile.mkdtemp(prefix="vv-perf-lib-")
    env["VVLAB_CONFIG"] = tempfile.mkdtemp(prefix="vv-perf-cfg-")
    env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"--remote-debugging-port={a.port}"
    subprocess.run(["taskkill", "/F", "/IM", os.path.basename(exe)], capture_output=True)
    time.sleep(0.5)
    report = {"flow": a.flow, "exe": os.path.basename(exe), "machine": {"cpu": platform.processor(), "os": platform.platform(), "python": platform.python_version()}}
    t_launch = time.time()
    proc = subprocess.Popen([exe], env=env)
    try:
        for _ in range(400):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{a.port}/json/version", timeout=1)
                break
            except Exception:
                time.sleep(0.05)
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{a.port}")
            page = browser.contexts[0].pages[0]
            t_ready = wait(page, READY)
            report["cold_start_to_ready_s"] = round(t_ready - t_launch, 2)
            page.evaluate("([w, h]) => window.__TAURI__.window.getCurrentWindow().setSize(new window.__TAURI__.window.LogicalSize(w, h))", [w, h])
            time.sleep(1.0)
            report["idle_memory"] = tree_memory(proc.pid)
            report["idle_frames"] = frame_stats(page, 2000)
            t0 = time.time()
            for sel in FLOWS[a.flow]:
                page.click(sel)
            t_shown = wait(page, RUN_SHOWN, timeout=120)
            report["clicks_to_landing"] = len(FLOWS[a.flow])
            report["click_to_landing_on_screen_s"] = round(t_shown - t0, 2)
            report["machine_time_to_landing_s"] = round(report["cold_start_to_ready_s"] + report["click_to_landing_on_screen_s"], 2)
            time.sleep(1.0)
            # Playback from the start at 1x: frame times while the 3D view animates.
            page.evaluate("() => { const b = document.querySelector('.tbtn'); if (b) b.click(); const p = document.querySelector('.tbtn-main'); if (p && !p.getAttribute('aria-label').startsWith('Pause')) p.click(); }")
            time.sleep(0.2)
            playing = page.evaluate("() => { const p = document.querySelector('.tbtn-main'); return !!p && p.getAttribute('aria-label').startsWith('Pause'); }")
            report["playback_detected"] = playing
            report["playback_frames"] = frame_stats(page, 5000)
            report["playback_memory"] = tree_memory(proc.pid)
            report["webgl"] = page.evaluate("""() => { const c = document.querySelector('.r3d canvas'); if (!c) return null; const g = c.getContext('webgl2') || c.getContext('webgl'); if (!g) return 'none'; const e = g.getExtension('WEBGL_debug_renderer_info'); return e ? g.getParameter(e.UNMASKED_RENDERER_WEBGL) : 'masked'; }""")
            report["window_inner"] = page.evaluate("[innerWidth, innerHeight, devicePixelRatio]")
    finally:
        proc.kill()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
