r"""M17 Cinematic View lifecycle in the installed Studio: install the module from its zip through
the real file dialog, read its verified status, launch it on a stored run from the player, see
its window and process, close it, uninstall it and check the player falls back. The native dialog
is answered with keystrokes. Screenshots go to --shots.

    python desktop/studio/tests/m17_cinematic_journey.py --exe "%LOCALAPPDATA%\VV Lab Studio\vv-studio.exe" --zip <vv-cinematic-x.y.z.zip>

Scripted checks of what the screen and the process list show, not observations of people.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from m15_journeys import check, errors, results  # noqa: E402
from m16_journeys import launch, open_mission, session  # noqa: E402

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def send_keys(text):
    """Answers the native file dialog by UI Automation (uia_file_dialog.ps1)."""
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uia_file_dialog.ps1")
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script, "-Title", "Choose a Cinematic View module", "-Path", text], capture_output=True, text=True)
    check("Cinematic: the native file dialog is answered", r.stdout.strip() == "ok", (r.stdout + r.stderr).strip()[:200])


CONFIRM_SCRIPT = r"""
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root = [System.Windows.Automation.AutomationElement]::RootElement
$name = [System.Windows.Automation.AutomationElement]::NameProperty
$isWindow = New-Object System.Windows.Automation.PropertyCondition ([System.Windows.Automation.AutomationElement]::ControlTypeProperty), ([System.Windows.Automation.ControlType]::Window)
$deadline = (Get-Date).AddSeconds(40)
while ((Get-Date) -lt $deadline) {
    $w = $null
    foreach ($c in $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $isWindow)) {
        if ($c.Current.Name -like 'Install the Cinematic View module*') { $w = $c; break }
    }
    if ($w) {
        $texts = ($w.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition) | ForEach-Object { $_.Current.Name }) -join ' '
        $b = $w.FindFirst([System.Windows.Automation.TreeScope]::Descendants, (New-Object System.Windows.Automation.PropertyCondition $name, 'Install'))
        if ($b) {
            $b.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
            Write-Output "ok $texts"
            exit 0
        }
    }
    Start-Sleep -Milliseconds 250
}
Write-Output 'no dialog'
exit 1
"""


def confirm_install(zip_path):
    """Answers Studio's confirmation (it shows the zip's SHA-256) with its Install button."""
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", CONFIRM_SCRIPT], capture_output=True, text=True)
    sha = hashlib.sha256(open(zip_path, "rb").read()).hexdigest()
    check("Cinematic: Studio asks for confirmation and shows the zip's SHA-256", r.stdout.startswith("ok") and sha in r.stdout, (r.stdout + r.stderr).strip()[:300])


def godot_pids(parent_pid):
    """Godot processes started by the Studio process `parent_pid` (never other Godot instances)."""
    ps = f"Get-CimInstance Win32_Process -Filter 'ParentProcessId={int(parent_pid)}' | Where-Object {{ $_.Name -like 'Godot*' }} | ForEach-Object {{ $_.ProcessId }}"
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True).stdout
    return [int(x) for x in out.split() if x.isdigit()]


def status(s):
    return s.page.evaluate("() => window.__TAURI__.core.invoke('cinematic_status')")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", required=True)
    ap.add_argument("--zip", required=True)
    ap.add_argument("--shots", default=os.path.join(REPO, "docs", "images", "m17-studio"))
    ap.add_argument("--port", type=int, default=9291)
    ap.add_argument("--preinstalled", action="store_true", help="the module was installed by the Studio's install code (modules.rs test with VV_CINEMATIC_INSTALL_TO); skip the native dialog")
    a = ap.parse_args()
    os.makedirs(a.shots, exist_ok=True)
    env = dict(os.environ)
    for k in ("VVLAB_DOMAINS", "VVLAB_EXTRA_DOMAINS", "VVLAB_EXEC", "VVLAB_CLAIMS", "VVLAB_ENVIRONMENTS"):
        env.pop(k, None)
    env["VVLAB_LIBRARY"] = tempfile.mkdtemp(prefix="vv-m17c-lib-")
    env["VVLAB_CONFIG"] = tempfile.mkdtemp(prefix="vv-m17c-cfg-")
    env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"--remote-debugging-port={a.port}"
    proc = launch(os.path.abspath(os.path.expandvars(a.exe)), env, a.port)
    try:
        with sync_playwright() as pw:
            browser, s = session(pw, a.port, a.shots)
            try:
                before = status(s)
                if not a.preinstalled:
                    if before.get("installed"):
                        s.page.evaluate("() => window.__TAURI__.core.invoke('cinematic_uninstall')")
                    s.nav("settings")
                    s.wait("[...document.querySelectorAll('button')].some((b) => /Install from a module zip/.test(b.textContent))", 20, "install button")
                    s.page.evaluate("() => [...document.querySelectorAll('button')].find((b) => /Install from a module zip/.test(b.textContent)).click()")
                    send_keys(os.path.abspath(a.zip))
                    confirm_install(os.path.abspath(a.zip))
                t0 = time.time()
                st = None
                while time.time() - t0 < 180:
                    st = status(s)
                    if st.get("installed"):
                        break
                    time.sleep(1)
                check("Cinematic: the module installs from its zip and its files match the manifest", bool(st and st.get("installed") and st.get("verified")), json.dumps(st)[:240])
                s.page.evaluate("() => document.querySelector(\".nav-btn[data-view='home']\").click()")
                s.nav("settings")
                time.sleep(1.0)
                s.shot("m17-settings-cinematic-installed-dark")
                open_mission(s, "lying-altimeter")
                s.wait("document.querySelector('.pl-head [data-action=\"cinematic\"]:not([aria-disabled=\"true\"])')", 30, "cinematic button enabled")
                t_click = time.time()
                s.page.click(".pl-head [data-action='cinematic']")
                t0 = time.time()
                launched = []
                while time.time() - t0 < 40 and not launched:
                    launched = godot_pids(proc.pid)
                    time.sleep(0.5)
                check("Cinematic: the player opens the module window on the shown run", bool(launched))
                # The module's own log says whether it verified the pack, drew a first frame and
                # rendered without errors. (No desktop screenshot: it would capture other windows.)
                # The first frame takes about 12 to 15 s after the click on the reference PC (the module
                # decodes its CC0 assets at start), so wait for it instead of sleeping a fixed time.
                # Only a log written after the click counts: an older one may hold an earlier FIRST_FRAME.
                logs = os.path.join(os.environ.get("APPDATA", ""), "VV Lab Cinematic", "logs")
                text = ""
                newest = None
                t0 = time.time()
                while time.time() - t0 < 90:
                    fresh = [os.path.join(logs, f) for f in os.listdir(logs)] if os.path.isdir(logs) else []
                    fresh = [f for f in fresh if os.path.getmtime(f) >= t_click - 1]
                    newest = max(fresh, key=os.path.getmtime) if fresh else None
                    text = open(newest, encoding="utf-8", errors="replace").read() if newest else ""
                    if "FIRST_FRAME" in text:
                        break
                    time.sleep(1)
                time.sleep(2)
                text = open(newest, encoding="utf-8", errors="replace").read() if newest else text
                check("Cinematic: the module verified the pack and drew its first frame", "verified" in text and "FIRST_FRAME" in text, text[:300].replace("\n", " "))
                check("Cinematic: the module renders without errors", "ERROR" not in text, f"{text.count('ERROR')} errors; " + text.splitlines()[1][:120] if text else "no log")
                # Only the Godot process this Studio started; any other Godot instance is left alone.
                for pid in godot_pids(proc.pid):
                    subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
                time.sleep(1)
                # Godot wrote its cache inside the module folder. Only a launch runs the full integrity
                # check (the status is cached), so open the view a second time: it must still start.
                s.page.click(".pl-head [data-action='cinematic']")
                t0 = time.time()
                relaunched = []
                while time.time() - t0 < 40 and not relaunched:
                    relaunched = godot_pids(proc.pid)
                    time.sleep(0.5)
                check("Cinematic: a second launch passes the full integrity check after Godot wrote its cache", bool(relaunched), json.dumps(status(s))[:200])
                for pid in relaunched:
                    subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
                time.sleep(1)
                after = s.page.evaluate("() => window.__TAURI__.core.invoke('cinematic_uninstall')")
                check("Cinematic: uninstall removes the module", not after.get("installed"), json.dumps(after)[:200])
                s.page.evaluate("() => document.querySelector(\".nav-btn[data-view='home']\").click()")
                open_mission(s, "first-landing")
                time.sleep(1.5)
                off = s.js("(() => { const b = document.querySelector('.pl-head [data-action=\"cinematic\"]'); return b ? { d: b.getAttribute('aria-disabled') === 'true', t: b.title, described: !!document.getElementById(b.getAttribute('aria-describedby')) } : null; })()")
                check("Cinematic: without the module the button is aria-disabled, focusable and says why", bool(off) and off["d"] and off["described"] and bool(off["t"]), json.dumps(off))
                check("Cinematic: the technical view still plays", s.js("window.__studio.player().scene") is not None)
            except Exception as e:  # noqa: BLE001
                check("Cinematic journey completed", False, repr(e)[:300])
            check("No page error or console error", not errors, "; ".join(errors)[:300])
            browser.close()
    finally:
        proc.kill()
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
