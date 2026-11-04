r"""Fixed-framing screenshots of the geospatial view, for a fair before-and-after comparison between
Studio versions: the same mission, environment, playback time, camera preset and window size.

    python desktop/studio/tests/m16_compare_shots.py --exe "%LOCALAPPDATA%\VV Lab Studio\vv-studio.exe" --out docs/evidence/m16/before
    python desktop/studio/tests/m16_compare_shots.py --exe desktop/target/release/vv-studio.exe --domains desktop/target/release/domains --environments desktop/environments --out docs/evidence/m16/after

Each shot is named <environment>-<camera>-<time>-<w>x<h>.jpg (JPEG quality 85). The script writes shots.json with
what each shot shows (version, environment, time, camera and, when the Studio exposes it, the
camera pose). It uses a scratch library and configuration. These are pictures, not measurements.
"""

import argparse
import json
import os
import sys
import tempfile
import time

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from m16_journeys import launch, open_mission  # noqa: E402
from m15_journeys import S  # noqa: E402

MISSION = "lying-altimeter"
CAMERAS = ["follow", "pad", "closeup", "wide", "overhead"]
SIZES = [(1440, 900), (1280, 720), (1024, 640)]


def set_time(s, frac):
    """Pause and move the playback to a fraction of the run (1 is the end)."""
    s.page.evaluate("""(f) => {
        const r = document.querySelector('.pl-range');
        const t = Number(r.min) + f * (Number(r.max) - Number(r.min));
        r.value = String(t);
        r.dispatchEvent(new Event('input', { bubbles: true }));
    }""", frac)
    time.sleep(0.4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", required=True)
    ap.add_argument("--domains", default="")
    ap.add_argument("--environments", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--port", type=int, default=9244)
    ap.add_argument("--envs", default="santa-maria-azores,cape-canaveral")
    ap.add_argument("--all-sizes-camera", default="follow", help="camera shot at every window size")
    a = ap.parse_args()
    exe = os.path.abspath(os.path.expandvars(a.exe))
    out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    env = dict(os.environ)
    for k in ("VVLAB_DOMAINS", "VVLAB_EXTRA_DOMAINS", "VVLAB_EXEC", "VVLAB_CLAIMS", "VVLAB_ENVIRONMENTS"):
        env.pop(k, None)
    if a.domains:
        root = os.path.dirname(os.path.abspath(a.domains))
        env["VVLAB_DOMAINS"] = os.path.abspath(a.domains)
        env["VVLAB_EXEC"] = os.path.join(root, "engines", "vv-exec.exe")
        env["VVLAB_CLAIMS"] = os.path.join(root, "discovery", "claims")
    if a.environments:
        env["VVLAB_ENVIRONMENTS"] = os.path.abspath(a.environments)
    env["VVLAB_LIBRARY"] = tempfile.mkdtemp(prefix="vv-shots-lib-")
    env["VVLAB_CONFIG"] = tempfile.mkdtemp(prefix="vv-shots-cfg-")
    env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"--remote-debugging-port={a.port}"
    meta = {"exe": os.path.basename(exe), "mission": MISSION, "shots": []}
    proc = launch(exe, env, a.port)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{a.port}")
            page = browser.contexts[0].pages[0]
            s = S(page, out)
            s.wait("window.__TAURI__ && window.__studio", 30, "studio script")
            meta["version"] = page.evaluate("() => window.__TAURI__.app ? window.__TAURI__.app.getVersion() : null")
            for env_id in [x for x in a.envs.split(",") if x]:
                page.evaluate("(e) => window.__TAURI__.core.invoke('set_prefs', { prefs: { theme: 'dark', missionView: 'geospatial', missionEnvironment: e, missionSpeed: 1 } })", env_id)
                page.reload()
                s.wait("window.__studio && document.getElementById('startup').hidden", 90, "platform ready")
                s.resize(1440, 900)
                open_mission(s, MISSION)
                s.wait("(() => { const p = window.__studio.player(); return p && p.renderer === 'geospatial'; })()", 60, "geospatial renderer")
                time.sleep(2.0)
                for frac, tname in ((1.0, "end"), (0.55, "mid")):
                    for cam in CAMERAS:
                        sizes = SIZES if (cam == a.all_sizes_camera and tname == "end") else SIZES[:1]
                        for w, h in sizes:
                            s.resize(w, h)
                            btn = page.query_selector(f".pl-cams [data-cam='{cam}']")
                            if not btn:
                                continue
                            btn.click()
                            set_time(s, frac)
                            time.sleep(0.8)
                            name = f"{env_id}-{cam}-{tname}-{w}x{h}"
                            page.screenshot(path=os.path.join(out, name + ".jpg"), type="jpeg", quality=85)
                            p = page.evaluate("() => window.__studio.player()")
                            meta["shots"].append({"file": name + ".jpg", "environment": env_id, "camera": cam, "t": p.get("t"), "size": [w, h], "geo": p.get("geoStats")})
                            print("shot", name, flush=True)
                s.resize(1440, 900)
            browser.close()
    finally:
        proc.kill()
    with open(os.path.join(out, "shots.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1)


if __name__ == "__main__":
    main()
