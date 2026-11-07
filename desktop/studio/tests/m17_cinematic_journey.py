r"""M17 Cinematic View lifecycle in the installed Studio: install the module from its zip through
the real file dialog, read its verified status, launch it on a stored run from the player, see
its window and process, close it, uninstall it and check the player falls back. The native dialog
is answered with keystrokes. Screenshots go to --shots.

    python desktop/studio/tests/m17_cinematic_journey.py --exe "%LOCALAPPDATA%\VV Lab Studio\vv-studio.exe" --zip <vv-cinematic-x.y.z.zip>

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
from m15_journeys import check, errors, results  # noqa: E402
from m16_journeys import launch, open_mission, session  # noqa: E402

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def send_keys(text):
    """Answers the native file dialog by UI Automation (uia_file_dialog.ps1)."""
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uia_file_dialog.ps1")
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script, "-Title", "Choose a Cinematic View module", "-Path", text], capture_output=True, text=True)
    check("Cinematic: the native file dialog is answered", r.stdout.strip() == "ok", (r.stdout + r.stderr).strip()[:200])


def godot_running():
    out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout.lower()
    return "godot" in out


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
                t0 = time.time()
                st = None
                while time.time() - t0 < 180:
                    st = status(s)
                    if st.get("installed"):
                        break
                    time.sleep(1)
                check("Cinematic: the module installs from its zip and every file verifies", bool(st and st.get("installed") and st.get("verified")), json.dumps(st)[:240])
                s.page.evaluate("() => document.querySelector(\".nav-btn[data-view='home']\").click()")
                s.nav("settings")
                time.sleep(1.0)
                s.shot("m17-settings-cinematic-installed-dark")
                open_mission(s, "lying-altimeter")
                s.wait("document.querySelector('.pl-head [data-action=\"cinematic\"]:not([disabled])')", 30, "cinematic button enabled")
                s.page.click(".pl-head [data-action='cinematic']")
                t0 = time.time()
                while time.time() - t0 < 40 and not godot_running():
                    time.sleep(0.5)
                check("Cinematic: the player opens the module window on the shown run", godot_running())
                time.sleep(12)
                try:
                    from PIL import ImageGrab
                    ImageGrab.grab().save(os.path.join(a.shots, "m17-cinematic-window-from-studio.png"))
                except Exception as e:  # noqa: BLE001
                    print("screen grab failed", e)
                subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Process | Where-Object { $_.ProcessName -like 'Godot*' } | Stop-Process -Force"], capture_output=True)
                time.sleep(1)
                after = s.page.evaluate("() => window.__TAURI__.core.invoke('cinematic_uninstall')")
                check("Cinematic: uninstall removes the module", not after.get("installed"), json.dumps(after)[:200])
                s.page.evaluate("() => document.querySelector(\".nav-btn[data-view='home']\").click()")
                open_mission(s, "first-landing")
                time.sleep(1.5)
                off = s.js("(() => { const b = document.querySelector('.pl-head [data-action=\"cinematic\"]'); return b ? { d: b.disabled, t: b.title } : null; })()")
                check("Cinematic: without the module the button is disabled and says why", bool(off) and off["d"], json.dumps(off))
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
