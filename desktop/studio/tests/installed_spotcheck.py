r"""Spot-check of the INSTALLED Studio, the way a person would use it: Mission Control, the vehicle
hangar, design and fly a landing stage (change thrust), compare, watch both runs in the player, then
open the Cinematic View for that landing run; then the same for a launch vehicle (payload change)
and its ascent run. For each Cinematic View launch it records, from the operating system and the
module's own log, that the Godot process started with --rendering-driver d3d12 on the shown run and
how long its first frame took. The Studio does not pass --shot, so the picture is taken by a second,
separate run of the installed module on the same run and environment (the arguments read from the
Studio-started process), written to --shots. The page screenshots that the shared helpers take go to
--shots/desktop-not-committed (they show the Studio window; keep them out of the repository). It uses a
scratch library and configuration.

    python desktop/studio/tests/installed_spotcheck.py --exe "%LOCALAPPDATA%\VV Lab Studio\vv-studio.exe" --shots <scratch folder>

Scripted checks of what the screen and the process list show, not observations of people.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import m18_journeys as m18  # noqa: E402
from m15_journeys import check, errors, results  # noqa: E402
from m16_journeys import launch, session  # noqa: E402

FACTS = {}


def godot_children(parent_pid):
    ps = (
        f"Get-CimInstance Win32_Process -Filter 'ParentProcessId={int(parent_pid)}' | Where-Object {{ $_.Name -like 'Godot*' }} "
        "| ForEach-Object { [pscustomobject]@{ pid = $_.ProcessId; name = $_.Name; cmd = $_.CommandLine } } | ConvertTo-Json -Compress"
    )
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True).stdout.strip()
    if not out:
        return []
    data = json.loads(out)
    return data if isinstance(data, list) else [data]


def module_args(cmd):
    """Arguments after the executable path, split on the Windows rules."""
    import shlex

    parts = shlex.split(cmd, posix=False)
    return [p.strip('"') for p in parts[1:]]


def newest_log():
    logs = os.path.join(os.environ.get("APPDATA", ""), "VV Lab Cinematic", "logs")
    files = [os.path.join(logs, f) for f in os.listdir(logs)] if os.path.isdir(logs) else []
    return max(files, key=os.path.getmtime) if files else None


def cinematic(s, proc, tag, shots):
    """Open the Cinematic View from the player header and observe the module process."""
    s.wait("document.querySelector('.pl-head [data-action=\"cinematic\"]:not([aria-disabled=\"true\"])')", 30, "cinematic button enabled")
    t0 = time.time()
    s.page.click(".pl-head [data-action='cinematic']")
    kids = []
    while time.time() - t0 < 40 and not kids:
        kids = godot_children(proc.pid)
        time.sleep(0.25)
    check(f"Cinematic {tag}: the module process started", bool(kids))
    if not kids:
        return
    cmd = kids[0]["cmd"] or ""
    check(f"Cinematic {tag}: Godot was started with --rendering-driver d3d12", "--rendering-driver d3d12" in cmd, cmd[:140])
    first = None
    text = ""
    while time.time() - t0 < 90:
        log = newest_log()
        text = open(log, encoding="utf-8", errors="replace").read() if log else ""
        if "FIRST_FRAME" in text:
            first = time.time() - t0
            break
        time.sleep(0.5)
    check(f"Cinematic {tag}: the first frame was drawn", first is not None, f"{first and round(first, 1)} s after the click" if first else text[-200:])
    check(f"Cinematic {tag}: Direct3D 12 is the renderer in the module's own log", "D3D12" in text and "ERROR" not in text, text.splitlines()[1][:120] if len(text.splitlines()) > 1 else "no log")
    scene_line = next((ln for ln in text.splitlines() if "scene built" in ln), "")
    FACTS[tag] = {"seconds_click_to_first_frame": first and round(first, 1), "module_log_scene_line": scene_line, "driver_in_command_line": "d3d12" in cmd}
    for k in godot_children(proc.pid):
        subprocess.run(["taskkill", "/F", "/PID", str(k["pid"])], capture_output=True)
    time.sleep(1.5)
    # A separate run of the same module on the same run and environment draws the picture.
    args = module_args(cmd)
    exe = [a for a in [cmd.split('"')[1] if cmd.startswith('"') else cmd.split()[0]]][0]
    console = os.path.join(os.path.dirname(exe), "Godot_v4.7.2-stable_win64_console.exe")
    run_dir = args[args.index("--run") + 1]
    rec = json.load(open(os.path.join(run_dir, "record.json"), encoding="utf-8"))
    span = max((tb[-1] for tb in rec["timebases"].values() if tb), default=10.0)
    out = os.path.join(shots, f"cinematic-{tag}.png")
    r = subprocess.run([console] + args + ["--t", f"{0.55 * span:.1f}", "--shot", out], capture_output=True, text=True, timeout=240)
    shot_line = next((ln for ln in r.stdout.splitlines() if ln.startswith("SHOT")), "")
    ok = os.path.isfile(out) and os.path.getsize(out) > 50_000
    check(f"Cinematic {tag}: the module's own --shot wrote a picture of this run", ok, f"{os.path.getsize(out) if os.path.isfile(out) else 0} bytes at t = {0.55 * span:.1f} s")
    FACTS[tag]["shot_bytes"] = os.path.getsize(out) if os.path.isfile(out) else 0
    FACTS[tag]["shot_run"] = os.path.basename(run_dir)
    FACTS[tag]["shot_line"] = shot_line[:400]


def watch_lab(s, tag):
    s.page.click("#lab-watch")
    s.wait("(() => { const p = window.__studio.player(); return p && p.experience.startsWith('runs:') && document.querySelector('.pl-hud dl'); })()", 120, "player")
    p = s.player()
    FACTS[tag + "_player"] = {"scene": p.get("scene"), "view": p.get("view"), "runs": p.get("runs")}
    check(f"Player {tag}: plays both records of the Lab", len(p["runs"]) == 2)
    s.page.click(".pl-views [data-view='engineering']")
    s.wait("(() => { const p = window.__studio.player(); return p && p.view === 'engineering' && p.renderer === 'engineering'; })()", 60, "engineering scene")
    check(f"Player {tag}: Engineering view shows the scene", s.player()["view"] == "engineering", json.dumps({k: s.player()[k] for k in ("view", "renderer")}))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", required=True)
    ap.add_argument("--shots", required=True)
    ap.add_argument("--port", type=int, default=9265)
    a = ap.parse_args()
    os.makedirs(a.shots, exist_ok=True)
    m18.NUMBERS.clear()
    env = dict(os.environ)
    for k in ("VVLAB_DOMAINS", "VVLAB_EXTRA_DOMAINS", "VVLAB_EXEC", "VVLAB_CLAIMS", "VVLAB_ENVIRONMENTS"):
        env.pop(k, None)
    env["VVLAB_LIBRARY"] = tempfile.mkdtemp(prefix="vv-spot-lib-")
    env["VVLAB_CONFIG"] = tempfile.mkdtemp(prefix="vv-spot-cfg-")
    env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"--remote-debugging-port={a.port}"
    proc = launch(os.path.abspath(os.path.expandvars(a.exe)), env, a.port)
    try:
        with sync_playwright() as pw:
            browser, s = session(pw, a.port, os.path.join(a.shots, "desktop-not-committed"))
            try:
                m18.home(s)
                m18.hangar(s)
                base_id, exp_id = m18.vehicle_experiment(s)
                m18.compare(s, base_id, exp_id)
                st = s.page.evaluate("() => window.__TAURI__.core.invoke('cinematic_status')")
                check("Cinematic module is installed and verified", bool(st.get("installed") and st.get("verified")), json.dumps({k: st.get(k) for k in ("installed", "verified", "version")}))
                watch_lab(s, "landing")
                cinematic(s, proc, "landing", a.shots)
                m18.ascent(s)
                s.page.click("#lab-watch")
                s.wait("(() => { const p = window.__studio.player(); return p && p.experience.startsWith('runs:') && p.scene === 'ascent'; })()", 180, "ascent player")
                FACTS["ascent_player"] = {"scene": s.player().get("scene"), "runs": s.player().get("runs")}
                check("Player ascent: plays the launch records", len(s.player()["runs"]) == 2)
                cinematic(s, proc, "ascent", a.shots)
            except Exception as e:  # noqa: BLE001
                check("spot-check completed", False, repr(e)[:400])
            check("No page error or console error", not errors, "; ".join(errors)[:300])
            browser.close()
    finally:
        for k in godot_children(proc.pid):
            subprocess.run(["taskkill", "/F", "/PID", str(k["pid"])], capture_output=True)
        proc.kill()
    with open(os.path.join(a.shots, "spotcheck-facts.json"), "w", encoding="utf-8") as f:
        json.dump({"facts": FACTS, "numbers": m18.NUMBERS}, f, indent=1, sort_keys=True)
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
