r"""Extra screenshots for the review of the installed Studio: the end state of the 60 m/s run (the
experiment, shown in the player at the end) and the corridor mission, which has a run with a broken
safety rule, each as the active run at three window sizes (1440x900, 1024x640, 820x900), in the dark
theme and in the light theme at 1440x900. It checks that the pills, the caption and the camera buttons do
not overlap and that no run pill is cut. It uses a scratch library; the pictures show the Studio window,
so they stay out of the repository.

    python desktop/studio/tests/review_captures.py --exe "%LOCALAPPDATA%\VV Lab Studio\vv-studio.exe" --shots <scratch folder>
"""

import argparse
import json
import os
import sys
import tempfile
import time

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import m18_journeys as m18  # noqa: E402
import ux_journeys as ux1  # noqa: E402
from m15_journeys import check, errors, results  # noqa: E402
from m16_journeys import launch, open_mission, session  # noqa: E402

SIZES = ((1440, 900), (1024, 640), (820, 900))
PILLS_JS = """() => {
  const pills = [...document.querySelectorAll('.pl-run')].filter((e) => e.offsetParent !== null);
  const bad = pills.filter((e) => {
    const r = e.getBoundingClientRect();
    return e.scrollHeight > e.clientHeight + 1 || e.scrollWidth > e.clientWidth + 1 || r.left < -0.5 || r.right > innerWidth + 0.5 || r.bottom > innerHeight + 0.5;
  }).map((e) => e.textContent.trim().slice(0, 60));
  return { n: pills.length, bad };
}"""
UNSAFE_PILL = "[...document.querySelectorAll('.pl-run')].findIndex((e) => e.classList.contains('is-unsafe'))"


def at_sizes(s, tag, rebuild, pairs):
    """The player (already showing its end state) at each size: rebuilt for the size, result shown, checked, captured."""
    for w, h in SIZES:
        s.resize(w, h)
        rebuild()
        if s.js("!!document.querySelector(\"[data-action='reveal']\")"):
            s.page.click("[data-action='reveal']")
        s.wait("document.querySelector('.pl-result')", 30, "result")
        time.sleep(1.0)
        o = s.js(ux1.OVERLAP_JS, pairs + [[".pl-viewport.is-2d", ".pl-runs"]] if s.js("!!document.querySelector('.pl-viewport.is-2d')") else pairs)
        check(f"{tag} {w}x{h}: pills, caption and camera buttons do not overlap one another or the readout card (nor the 2D plot with its axis labels)", not o["clash"], json.dumps(o))
        r = s.js(PILLS_JS)
        check(f"{tag} {w}x{h}: no run pill is clipped", not r["bad"], json.dumps(r))
        s.shot(f"ux4-{tag}-{w}x{h}-dark")
    s.resize(1440, 900)
    s.theme("light")
    time.sleep(0.8)
    s.shot(f"ux4-{tag}-1440x900-light")
    s.theme("dark")
    s.resize(1440, 900)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", required=True)
    ap.add_argument("--shots", required=True)
    ap.add_argument("--port", type=int, default=9272)
    a = ap.parse_args()
    os.makedirs(a.shots, exist_ok=True)
    env = dict(os.environ)
    for k in ("VVLAB_DOMAINS", "VVLAB_EXTRA_DOMAINS", "VVLAB_EXEC", "VVLAB_CLAIMS", "VVLAB_ENVIRONMENTS"):
        env.pop(k, None)
    env["VVLAB_LIBRARY"] = tempfile.mkdtemp(prefix="vv-cap-lib-")
    env["VVLAB_CONFIG"] = tempfile.mkdtemp(prefix="vv-cap-cfg-")
    env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"--remote-debugging-port={a.port}"
    print("scratch library:", env["VVLAB_LIBRARY"], flush=True)
    proc = launch(os.path.abspath(os.path.expandvars(a.exe)), env, a.port)
    try:
        with sync_playwright() as pw:
            browser, s = session(pw, a.port, a.shots)
            try:
                def to_engineering():
                    s.page.click(".pl-views [data-view='geospatial']")
                    s.wait("window.__studio.player().renderer === 'geospatial'", 90, "geospatial")
                    s.page.click(".pl-views [data-view='engineering']")
                    s.wait("(() => { const p = window.__studio.player(); return p && p.view === 'engineering'; })()", 60, "engineering")

                s.nav("vehicles")
                s.page.click(".hg-card[data-vehicle='heavy-return-stage'] [data-action='design']")
                s.wait("window.__studio.view() === 'lab' && document.querySelector('.lab-base') && window.__studio.lab()", 180, "baseline")
                m18.set_param(s, "vehicle_thrust_scale", 0.7)
                m18.run_and_wait(s)
                s.page.click("#lab-watch")
                s.wait("(() => { const p = window.__studio.player(); return p && p.experience.startsWith('runs:') && document.querySelector('.pl-hud dl'); })()", 120, "player")
                s.page.click(".pl-views [data-view='engineering']")
                s.wait("(() => { const p = window.__studio.player(); return p && p.view === 'engineering'; })()", 60, "engineering")
                s.page.click(".pl-run[data-run='1']")
                s.page.click("[data-action='reveal']")
                s.wait("document.querySelector('.pl-result')", 10, "result")
                time.sleep(1.0)
                chip = s.js("document.querySelector('.pl-phase-name') && document.querySelector('.pl-phase-name').textContent")
                check("The 60 m/s run at its end: the chip names the failing requirement", bool(chip) and "Vertical speed at contact 60.08" in chip, str(chip))
                at_sizes(s, "end-state-60ms-run", to_engineering,
                         [[".pl-cams", ".pl-hud"], [".pl-cams", ".pl-runs"], [".pl-scene-note", ".pl-cams"], [".pl-scene-note", ".pl-runs"]])

                open_mission(s, "corridor")
                s.page.click("[data-action='reveal']")
                s.wait("document.querySelector('.pl-result')", 30, "result")
                time.sleep(1.0)
                unsafe = s.js(UNSAFE_PILL)
                check("Corridor: the run with a broken safety rule has the warning pill", unsafe is not None and unsafe >= 0, str(unsafe))
                if unsafe is not None and unsafe >= 0:
                    s.page.click(f".pl-run[data-run='{unsafe}']")
                    time.sleep(0.8)
                marks = s.js("[...document.querySelectorAll('.pl-mark.sev-violation')].map((e) => e.getAttribute('aria-label'))")
                check("Corridor: a violation marker is on the timeline", bool(marks), json.dumps(marks))

                def rebuild_corridor():
                    # The scene follows the window; the run with the broken rule stays the active one.
                    s.js("window.dispatchEvent(new Event('resize'))")
                    time.sleep(0.8)
                    idx = s.js(UNSAFE_PILL)
                    if idx is not None and idx >= 0:
                        s.page.click(f".pl-run[data-run='{idx}']")

                at_sizes(s, "corridor-broken-rule-run", rebuild_corridor,
                         [[".pl-cams", ".pl-hud"], [".pl-cams", ".pl-runs"], [".pl-scene-note", ".pl-runs"]])

                # A rocket landing with a broken safety rule: its record is kept in the scratch library so
                # that the Cinematic View panel can be captured from it (the corridor is a ground vehicle,
                # which the Cinematic View does not draw).
                open_mission(s, "threshold-trade-off")
                s.page.click("[data-action='reveal']")
                s.wait("document.querySelector('.pl-result')", 60, "result")
                time.sleep(1.0)
                s.shot("ux4-threshold-trade-off-player-dark")
            except Exception as e:  # noqa: BLE001
                check("captures completed", False, repr(e)[:300])
            check("No page error or console error", not errors, "; ".join(errors)[:300])
            browser.close()
    finally:
        proc.kill()
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
