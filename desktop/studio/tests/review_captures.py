r"""Extra screenshots for the review of the installed Studio: the end state of the 60 m/s run (the
experiment, shown in the player at the end) and the corridor mission, which has a run with a broken
safety rule, in the player once its result is shown. It uses a scratch library; the pictures show the
Studio window, so they stay out of the repository.

    python desktop/studio/tests/review_captures.py --exe "%LOCALAPPDATA%\VV Lab Studio\vv-studio.exe" --shots <scratch folder>
"""

import argparse
import os
import sys
import tempfile
import time

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import m18_journeys as m18  # noqa: E402
from m15_journeys import check, errors, results  # noqa: E402
from m16_journeys import launch, open_mission, session  # noqa: E402


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
    proc = launch(os.path.abspath(os.path.expandvars(a.exe)), env, a.port)
    try:
        with sync_playwright() as pw:
            browser, s = session(pw, a.port, a.shots)
            try:
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
                s.shot("ux3-end-state-60ms-run-dark")
                open_mission(s, "corridor")
                s.page.click("[data-action='reveal']")
                s.wait("document.querySelector('.pl-result')", 30, "result")
                time.sleep(1.0)
                s.shot("ux3-corridor-player-broken-safety-rule-dark")
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
