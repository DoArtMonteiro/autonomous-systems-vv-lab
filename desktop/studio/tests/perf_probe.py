r"""Measures V&V Lab Studio from the outside: cold start, the path to the first rocket landing on screen,
3D playback frame times and the memory of the studio process tree.

Nothing here runs inside the simulation; every number is wall-clock time or operating-system memory
of the desktop shell on the machine that runs the script. The script prints one JSON document.

    python desktop/studio/tests/perf_probe.py --exe "%LOCALAPPDATA%\VV Lab Studio\vv-studio.exe" --flow m11
    python desktop/studio/tests/perf_probe.py --exe desktop/target/release/vv-studio.exe --domains desktop/target/release/domains --flow m15

`--flow m11` drives the 0.11 interface (Prepare, rocket domain, nominal demonstration). `--flow m15`
drives the M15 home screen (one click on the first showcase mission). Each click is counted.
`--flow m16` runs the m15 path, then measures the M16 views: time to the geospatial scene, its frame
times and CPU load, Mission Control on the landscape, memory after the player is left, a 180 s
looping session, GPU memory and 3D engine utilisation (Windows performance counters) and every
request the web view makes, to show that none leaves the machine.
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
    "m16": [
        "#view-home [data-experience='first-landing'] [data-action='launch']",
    ],
}

READY = "window.__studio && document.getElementById('startup') && document.getElementById('startup').hidden"
RUN_SHOWN = {
    "m16": "window.__studio && window.__studio.player && window.__studio.player() && window.__studio.player().scene === 'rocket-3d' && document.querySelector('.pl-viewport canvas')",
    "m11": "window.__studio && window.__studio.run() && window.__studio.run().scene === 'rocket-3d' && document.querySelector('.r3d canvas')",
    "m15": "window.__studio && window.__studio.player && window.__studio.player() && window.__studio.player().scene === 'rocket-3d' && document.querySelector('.pl-viewport canvas')",
}
PLAY = {
    "m16": "() => { const p = document.querySelector('.pl-tbtn'); if (p) p.click(); }",
    "m11": "() => { const b = document.querySelector('.tbtn'); if (b) b.click(); const p = document.querySelector('.tbtn-main'); if (p && !p.getAttribute('aria-label').startsWith('Pause')) p.click(); }",
    "m15": "() => { const p = document.querySelector('.pl-tbtn'); if (p) p.click(); }",
}
PLAYING = {
    "m16": "() => window.__studio.player().playing",
    "m11": "() => { const p = document.querySelector('.tbtn-main'); return !!p && p.getAttribute('aria-label').startsWith('Pause'); }",
    "m15": "() => window.__studio.player().playing",
}


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


def ps_tree(root_pid):
    return (
        "$all = Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,KernelModeTime,UserModeTime;"
        f"$ids = @({root_pid}); $more = $true; while ($more) {{ $more = $false; foreach ($p in $all) {{ if ($ids -contains $p.ParentProcessId -and -not ($ids -contains $p.ProcessId)) {{ $ids += $p.ProcessId; $more = $true }} }} }};"
    )


def gpu_counters(root_pid):
    """Dedicated GPU memory and 3D engine utilisation of the process tree, from Windows counters."""
    ps = ps_tree(root_pid) + (
        "$mem = 0; $util = 0;"
        "try { (Get-Counter '\\GPU Process Memory(*)\\Dedicated Usage' -ErrorAction Stop).CounterSamples | ForEach-Object { $n = $_.InstanceName; foreach ($i in $ids) { if ($n -like ('pid_' + $i + '_*')) { $mem += $_.CookedValue } } } } catch {};"
        "try { (Get-Counter '\\GPU Engine(*engtype_3D)\\Utilization Percentage' -ErrorAction Stop).CounterSamples | ForEach-Object { $n = $_.InstanceName; foreach ($i in $ids) { if ($n -like ('pid_' + $i + '_*')) { $util += $_.CookedValue } } } } catch {};"
        "@{ gpu_dedicated_mb = [math]::Round($mem / 1MB, 1); gpu_3d_utilisation_percent = [math]::Round($util, 1) } | ConvertTo-Json -Compress"
    )
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True).stdout.strip()
    try:
        return json.loads(out)
    except ValueError:
        return {"error": out[:200]}


def cpu_seconds(root_pid):
    ps = ps_tree(root_pid) + "$t = 0; foreach ($p in $all) { if ($ids -contains $p.ProcessId) { $t += $p.KernelModeTime + $p.UserModeTime } }; $t / 1e7"
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return None


def cpu_load(root_pid, page, ms):
    """Process-tree CPU time over a window of frames, as a share of one core."""
    c0, t0 = cpu_seconds(root_pid), time.time()
    frames = frame_stats(page, ms)
    c1, t1 = cpu_seconds(root_pid), time.time()
    load = round(100 * (c1 - c0) / (t1 - t0), 1) if c0 is not None and c1 is not None else None
    return frames, load


def m16_flow(page, proc, report, requests):
    def W(js, t=60):
        return wait(page, js, timeout=t)

    def renderer(name):
        return f"window.__studio.player() && window.__studio.player().renderer === '{name}'"

    page.evaluate("() => { window.__studio.player(); const b = document.querySelector('.pl-play'); if (b && !window.__studio.player().playing) b.click(); }")
    time.sleep(0.3)
    frames, load = cpu_load(proc.pid, page, 5000)
    report["engineering_playback_cpu_percent_of_one_core"] = load
    report["engineering_gpu"] = gpu_counters(proc.pid)
    page.evaluate("() => { const b = document.querySelector('.pl-play'); if (b && window.__studio.player().playing) b.click(); }")
    t0 = time.time()
    page.click(".pl-views [data-view='geospatial']")
    W(renderer("geospatial"))
    W("window.__studio.player().geoStats && window.__studio.player().geoStats.textures >= 1")
    report["geo_switch_to_terrain_on_gpu_s"] = round(time.time() - t0, 3)
    page.evaluate("() => { if (!window.__studio.player().playing) document.querySelector('.pl-play').click(); }")
    time.sleep(0.3)
    frames, load = cpu_load(proc.pid, page, 5000)
    report["geo_playback_frames"] = frames
    report["geo_playback_cpu_percent_of_one_core"] = load
    report["geo_playback_memory"] = tree_memory(proc.pid)
    report["geo_gpu"] = gpu_counters(proc.pid)
    report["geo_scene"] = page.evaluate("() => window.__studio.player().geoStats")
    t0 = time.time()
    page.click(".pl-views [data-view='control']")
    W("document.querySelector('.mc')")
    W(renderer("geospatial"))
    report["switch_to_control_s"] = round(time.time() - t0, 3)
    page.evaluate("() => { if (!window.__studio.player().playing) document.querySelector('.mct-play').click(); }")
    time.sleep(0.3)
    frames, load = cpu_load(proc.pid, page, 5000)
    report["control_playback_frames"] = frames
    report["control_playback_cpu_percent_of_one_core"] = load
    report["control_memory"] = tree_memory(proc.pid)
    # Leave the player: the geospatial scene is disposed.
    page.click(".nav-btn[data-view='library']")
    W("window.__studio.view() === 'library' && window.__studio.player().renderer === 'suspended'")
    time.sleep(3.0)
    report["after_leaving_memory"] = tree_memory(proc.pid)
    report["after_leaving_gpu"] = gpu_counters(proc.pid)
    # Back to the player, then a long looping session in the geospatial view.
    page.evaluate("() => document.dispatchEvent(new CustomEvent('vv-open-mission', { detail: 'first-landing' }))")
    W(renderer("geospatial"))
    page.click(".mc-tools .pl-views [data-view='geospatial']")
    W(renderer("geospatial"))
    W("window.__studio.player().geoStats && window.__studio.player().geoStats.textures >= 1")
    report["long_session_start_memory"] = tree_memory(proc.pid)
    page.evaluate("() => { window.__loop = setInterval(() => { const p = window.__studio.player(); if (p && !p.playing) document.querySelector('.pl-play').click(); }, 500); }")
    loops = []
    t_end = time.time() + 180
    while time.time() < t_end:
        f = frame_stats(page, 3000)
        loops.append(f["p99_ms"] if f else None)
        time.sleep(7)
    page.evaluate("() => clearInterval(window.__loop)")
    report["long_session_s"] = 180
    report["long_session_p99_ms_samples"] = loops
    report["long_session_end_memory"] = tree_memory(proc.pid)
    local = ("http://tauri.localhost", "http://ipc.localhost", "ipc:", "data:", "blob:")
    report["webview_requests"] = len(requests)
    report["webview_requests_leaving_the_machine"] = [u for u in requests if not u.startswith(local)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", required=True)
    ap.add_argument("--domains", default="")
    ap.add_argument("--flow", choices=sorted(FLOWS), required=True)
    ap.add_argument("--port", type=int, default=9333)
    ap.add_argument("--size", default="1440x900")
    ap.add_argument("--environments", default="", help="packs folder for a build-folder run; empty uses the installed packs")
    a = ap.parse_args()
    exe = os.path.abspath(os.path.expandvars(a.exe))
    w, h = (int(x) for x in a.size.split("x"))
    env = dict(os.environ)
    for k in ("VVLAB_DOMAINS", "VVLAB_EXTRA_DOMAINS", "VVLAB_EXEC", "VVLAB_CLAIMS", "VVLAB_ENVIRONMENTS"):
        env.pop(k, None)
    if a.environments:
        env["VVLAB_ENVIRONMENTS"] = os.path.abspath(a.environments)
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
            requests = []
            page.on("request", lambda r: requests.append(r.url))
            t_ready = wait(page, READY)
            report["cold_start_to_ready_s"] = round(t_ready - t_launch, 2)
            page.evaluate("([w, h]) => window.__TAURI__.window.getCurrentWindow().setSize(new window.__TAURI__.window.LogicalSize(w, h))", [w, h])
            time.sleep(1.0)
            report["idle_memory"] = tree_memory(proc.pid)
            report["idle_frames"] = frame_stats(page, 2000)
            t0 = time.time()
            for sel in FLOWS[a.flow]:
                page.click(sel)
            t_shown = wait(page, RUN_SHOWN[a.flow], timeout=120)
            report["clicks_to_landing"] = len(FLOWS[a.flow])
            report["click_to_landing_on_screen_s"] = round(t_shown - t0, 2)
            report["machine_time_to_landing_s"] = round(report["cold_start_to_ready_s"] + report["click_to_landing_on_screen_s"], 2)
            time.sleep(1.0)
            # Playback from the start at 1x: frame times while the 3D view animates.
            page.evaluate(PLAY[a.flow])
            time.sleep(0.2)
            playing = page.evaluate(PLAYING[a.flow])
            report["playback_detected"] = playing
            report["playback_frames"] = frame_stats(page, 5000)
            report["playback_memory"] = tree_memory(proc.pid)
            report["webgl"] = page.evaluate("""() => { const c = document.querySelector('.r3d canvas, .pl-viewport canvas'); if (!c) return null; const g = c.getContext('webgl2') || c.getContext('webgl'); if (!g) return 'none'; const e = g.getExtension('WEBGL_debug_renderer_info'); return e ? g.getParameter(e.UNMASKED_RENDERER_WEBGL) : 'masked'; }""")
            report["window_inner"] = page.evaluate("[innerWidth, innerHeight, devicePixelRatio]")
            if a.flow == "m16":
                m16_flow(page, proc, report, requests)
    finally:
        proc.kill()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
