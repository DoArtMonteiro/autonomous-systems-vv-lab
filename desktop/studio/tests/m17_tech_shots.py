r"""Technical-view screenshots for the M17 comparison with the Cinematic View: the installed Studio's
geospatial view of the mission "A sensor that lies" on one environment, at given playback times and
camera presets, 1440x900. Unlike m16_journeys.launch, it does not kill other Studio processes; it
refuses to start if one is running (the single-instance plugin would hand the launch to it).

    python desktop/studio/tests/m17_tech_shots.py --exe "%LOCALAPPDATA%\VV Lab Studio\vv-studio.exe" --out docs/evidence/m17/cinematic --shots follow:7.31,follow:16.29,closeup:23.336

Also writes the run's record to --record-out (when given), so the Cinematic View can be shown the
same record (by default the robust run, which lands). These are pictures, not measurements.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from m16_journeys import open_mission  # noqa: E402
from m15_journeys import S  # noqa: E402

MISSION = "lying-altimeter"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--env", default="cape-canaveral")
    ap.add_argument("--shots", required=True, help="camera:t,camera:t,...")
    ap.add_argument("--port", type=int, default=9251)
    ap.add_argument("--record-out", default="")
    ap.add_argument("--run-index", type=int, default=1, help="run of the mission shown (1: robust controller)")
    a = ap.parse_args()
    exe = os.path.abspath(os.path.expandvars(a.exe))
    running = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {os.path.basename(exe)}", "/NH"], capture_output=True, text=True).stdout
    if os.path.basename(exe).lower() in running.lower():
        sys.exit("a Studio is already running; close it first (this script does not kill it)")
    os.makedirs(a.out, exist_ok=True)
    env = dict(os.environ)
    for k in ("VVLAB_DOMAINS", "VVLAB_EXTRA_DOMAINS", "VVLAB_EXEC", "VVLAB_CLAIMS", "VVLAB_ENVIRONMENTS", "VVLAB_MODULES"):
        env.pop(k, None)
    env["VVLAB_LIBRARY"] = tempfile.mkdtemp(prefix="vv-m17-lib-")
    env["VVLAB_CONFIG"] = tempfile.mkdtemp(prefix="vv-m17-cfg-")
    env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"--remote-debugging-port={a.port}"
    proc = subprocess.Popen([exe], env=env)
    meta = {"exe": os.path.basename(exe), "mission": MISSION, "environment": a.env, "shots": []}
    try:
        for _ in range(400):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{a.port}/json/version", timeout=1)
                break
            except Exception:  # noqa: BLE001
                time.sleep(0.05)
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{a.port}")
            page = browser.contexts[0].pages[0]
            s = S(page, a.out)
            s.wait("window.__TAURI__ && window.__studio", 30, "studio script")
            meta["version"] = page.evaluate("() => window.__TAURI__.app ? window.__TAURI__.app.getVersion() : null")
            page.evaluate("(e) => window.__TAURI__.core.invoke('set_prefs', { prefs: { theme: 'dark', missionView: 'geospatial', missionEnvironment: e, missionSpeed: 1 } })", a.env)
            page.reload()
            s.wait("window.__studio && document.getElementById('startup').hidden", 90, "platform ready")
            s.resize(1440, 900)
            open_mission(s, MISSION)
            s.wait("(() => { const p = window.__studio.player(); return p && p.renderer === 'geospatial'; })()", 60, "geospatial renderer")
            time.sleep(2.0)
            page.click(f".pl-runs [data-run='{a.run_index}']")
            s.wait(f"(() => {{ const p = window.__studio.player(); return p && p.active === {a.run_index} && p.renderer === 'geospatial'; }})()", 60, "run shown")
            time.sleep(2.0)
            p = page.evaluate("() => window.__studio.player()")
            run_id = p["runs"][p["active"]]
            meta["run_id"] = run_id
            if a.record_out:
                rec = page.evaluate("(id) => window.__TAURI__.core.invoke('record', { runId: id })", run_id)
                with open(a.record_out, "w", encoding="utf-8") as f:
                    json.dump(rec, f)
            for spec in a.shots.split(","):
                cam, t = spec.split(":")
                page.click(f".pl-cams [data-cam='{cam}']")
                page.evaluate("""(t) => {
                    const r = document.querySelector('.pl-range');
                    r.value = String(t);
                    r.dispatchEvent(new Event('input', { bubbles: true }));
                }""", float(t))
                time.sleep(1.5)
                name = f"technical-{a.env}-{cam}-{t}-1440x900"
                page.screenshot(path=os.path.join(a.out, name + ".jpg"), type="jpeg", quality=88)
                st = page.evaluate("() => window.__studio.player()")
                meta["shots"].append({"file": name + ".jpg", "camera": cam, "t": st.get("t"), "geo": st.get("geoStats")})
                print("shot", name, st.get("t"), flush=True)
            browser.close()
    finally:
        proc.kill()
    with open(os.path.join(a.out, "technical-shots.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1)


if __name__ == "__main__":
    main()
