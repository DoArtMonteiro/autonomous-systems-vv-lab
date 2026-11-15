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
import subprocess
import sys
import tempfile
import time

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import installed_spotcheck as spot  # noqa: E402
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


def at_sizes(s, tag, rebuild, pairs, reopen):
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
        side = s.js("""() => { const v = document.getElementById('view-mission'); const out = [...document.querySelectorAll('.pl-head button, .pl-head select, .pl-transport button, .pl-hud')].filter((e) => e.offsetParent !== null && (e.getBoundingClientRect().right > innerWidth + 1 || e.getBoundingClientRect().left < -1)).map((e) => (e.textContent || e.className).trim().slice(0, 30)); return { over: v.scrollWidth - v.clientWidth, out }; }""")
        check(f"{tag} {w}x{h}: the player does not scroll sideways and its header, transport and readout are inside the window", side["over"] <= 1 and not side["out"], json.dumps(side))
        ph = s.js("[...document.querySelectorAll('.pl-viewport canvas')].filter((e) => e.offsetParent !== null).map((e) => Math.round(e.getBoundingClientRect().height))")
        check(f"{tag} {w}x{h}: the scene or plot is at least 200 px tall", bool(ph) and max(ph) >= 200, json.dumps(ph))
        s.shot(f"ux4-{tag}-{w}x{h}-dark")
    # The light theme: the theme switch goes through Settings, so the player is opened again afterwards.
    s.resize(1440, 900)
    s.theme("light")
    reopen()
    time.sleep(1.0)
    s.shot(f"ux4-{tag}-1440x900-light")
    s.theme("dark")
    s.resize(1440, 900)


def studio_panel(s, proc, tag, shots, expect, at="100"):
    """Opens the Cinematic View from the player, as a person does, reads the command line the Studio gave the module,
    stops that window, and draws the end of the run with the same arguments (--t late, --shot): the panel carries the
    identity the player shows. `expect` is {label, conditions, exploratory}."""
    s.wait("document.querySelector('.pl-head [data-action=\"cinematic\"]:not([aria-disabled=\"true\"])')", 40, "cinematic button enabled")
    s.page.click(".pl-head [data-action='cinematic']")
    t0 = time.time()
    kids = []
    while time.time() - t0 < 40 and not kids:
        kids = spot.godot_children(proc.pid)
        time.sleep(0.25)
    check(f"Cinematic {tag}: the Studio started the module", bool(kids))
    if not kids:
        return
    cmd = kids[0]["cmd"] or ""
    args = spot.module_args(cmd)
    pick = lambda k: args[args.index(k) + 1] if k in args else None  # noqa: E731
    check(f"Cinematic {tag}: the arguments carry the player's label, conditions and exploratory flag", pick("--run-label") == expect["label"] and pick("--conditions") == expect["conditions"] and (expect["exploratory"] is None or ("--exploratory" in args) == expect["exploratory"]), json.dumps({k: pick(k) for k in ("--run-label", "--conditions", "--vehicle", "--seed")}) + (" --exploratory" if "--exploratory" in args else ""))
    for k in kids:
        subprocess.run(["taskkill", "/F", "/PID", str(k["pid"])], capture_output=True)
    time.sleep(1.5)
    exe = cmd.split('"')[1] if cmd.startswith('"') else cmd.split()[0]
    console = os.path.join(os.path.dirname(exe), "Godot_v4.7.2-stable_win64_console.exe")
    out = os.path.join(shots, f"cinematic-panel-{tag}.png")
    r = subprocess.run([console] + args + ["--t", at, "--shot", out], capture_output=True, text=True, timeout=300)
    check(f"Cinematic {tag}: the module's own --shot drew the panel of this run", os.path.isfile(out) and os.path.getsize(out) > 10000, f"{os.path.isfile(out) and os.path.getsize(out)} bytes, exit {r.returncode}")


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
                def reopen_60():
                    s.nav("lab")
                    s.wait("document.querySelector('#lab-watch')", 30, "lab result")
                    s.page.click("#lab-watch")
                    s.wait("(() => { const p = window.__studio.player(); return p && p.experience.startsWith('runs:') && document.querySelector('.pl-hud dl'); })()", 120, "player")
                    s.page.click(".pl-views [data-view='engineering']")
                    s.wait("(() => { const p = window.__studio.player(); return p && p.view === 'engineering'; })()", 60, "engineering")
                    s.page.click(".pl-run[data-run='1']")
                    if s.js("!!document.querySelector(\"[data-action='reveal']\")"):
                        s.page.click("[data-action='reveal']")
                    s.wait("document.querySelector('.pl-result')", 10, "result")

                info60 = s.js("(() => { const r = [...document.querySelectorAll('.pl-run')][1]; return { label: r.querySelector('.pl-run-l').textContent, id: (r.querySelector('.pl-run-id').title || '').replace('Run ', '') }; })()")
                studio_panel(s, proc, "60ms-run", a.shots, {"label": info60["label"], "conditions": s.js("(id) => document.querySelector(`.pl-run-cond[data-run='${id}']`).dataset.conditions", info60["id"]), "exploratory": True})
                at_sizes(s, "end-state-60ms-run", to_engineering,
                         [[".pl-cams", ".pl-hud"], [".pl-cams", ".pl-runs"], [".pl-scene-note", ".pl-cams"], [".pl-scene-note", ".pl-runs"]], reopen_60)

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
                shapes = s.js("[...document.querySelectorAll('.pl-mark.sev-violation')].map((e) => [e.classList.contains('is-rule') ? 'rule' : e.classList.contains('is-req') ? 'requirement' : '?', e.style.background])")
                check("Corridor: a violation marker has a shape (safety rule or requirement) and the colour of its run", bool(shapes) and all(x[0] != '?' and x[1] for x in shapes), json.dumps(shapes))
                chip = s.js("document.querySelector('.pl-phase-name') && document.querySelector('.pl-phase-name').textContent")
                check("Corridor: the end chip says how the run ended and names the broken safety rule, not only End of run", bool(chip) and chip.startswith("End of run: Mission incomplete") and "safety rule broken: Truth stays outside the restricted zone" in chip, str(chip))

                def rebuild_corridor():
                    # The scene follows the window; the run with the broken rule stays the active one.
                    s.js("window.dispatchEvent(new Event('resize'))")
                    time.sleep(0.8)
                    idx = s.js(UNSAFE_PILL)
                    if idx is not None and idx >= 0:
                        s.page.click(f".pl-run[data-run='{idx}']")

                def reopen_corridor():
                    open_mission(s, "corridor")
                    if s.js("!!document.querySelector(\"[data-action='reveal']\")"):
                        s.page.click("[data-action='reveal']")
                    s.wait("document.querySelector('.pl-result')", 30, "result")
                    rebuild_corridor()

                at_sizes(s, "corridor-broken-rule-run", rebuild_corridor,
                         [[".pl-cams", ".pl-hud"], [".pl-cams", ".pl-runs"], [".pl-scene-note", ".pl-runs"]], reopen_corridor)

                # A rocket landing with a broken safety rule: its record is kept in the scratch library so
                # that the Cinematic View panel can be captured from it (the corridor is a ground vehicle,
                # which the Cinematic View does not draw).
                open_mission(s, "threshold-trade-off")
                s.page.click("[data-action='reveal']")
                s.wait("document.querySelector('.pl-result')", 60, "result")
                time.sleep(1.0)
                s.shot("ux4-threshold-trade-off-player-dark")
                # The same mission on a short window: the run pills keep their conditions and short id.
                s.resize(1024, 640)
                s.js("window.dispatchEvent(new Event('resize'))")
                time.sleep(1.2)
                pills_t = s.js("[...document.querySelectorAll('.pl-run')].map((b) => ({ id: /[0-9a-f]{8}/.test(b.innerText), cond: /GNSS bias|Threshold|default conditions/.test(b.innerText), text: b.innerText.replace(/\\s+/g, ' ').slice(0, 90) }))")
                check("Threshold mission 1024x640: every run pill keeps its conditions and an 8-hex id", len(pills_t) >= 2 and all(x["id"] and x["cond"] for x in pills_t), json.dumps(pills_t))
                s.shot("ux4-threshold-trade-off-player-1024x640-dark")
                s.resize(1440, 900)
                s.js("window.dispatchEvent(new Event('resize'))")
                time.sleep(0.8)
                chip2 = s.js("document.querySelector('.pl-phase-name') && document.querySelector('.pl-phase-name').textContent")
                check("Threshold landing: the end chip names the failed requirement and the broken safety rule", bool(chip2) and chip2.startswith("Not met: Vertical speed at contact") and "; safety rule broken: Climb under power; impact not modelled" in chip2, str(chip2))
                info_t = s.js("(() => { const r = document.querySelector('.pl-run[aria-checked=\"true\"]'); return { label: r.querySelector('.pl-run-l').textContent, id: (r.querySelector('.pl-run-id').title || '').replace('Run ', '') }; })()")
                studio_panel(s, proc, "broken-rule-landing", a.shots, {"label": info_t["label"], "conditions": s.js("(id) => document.querySelector(`.pl-run-cond[data-run='${id}']`).dataset.conditions", info_t["id"]), "exploratory": None})

                # The launch ascent (a second kind of record): its panel too, from the Studio-launched process.
                open_mission(s, "to-orbit")
                if s.js("!!document.querySelector(\"[data-action='reveal']\")"):
                    s.page.click("[data-action='reveal']")
                s.wait("document.querySelector('.pl-result')", 120, "result")
                info_a = s.js("(() => { const c = document.querySelector('.pl-run-cond'); const n = c && c.parentElement.querySelector('.pl-run-name'); return c ? { label: n.textContent.trim(), conditions: c.dataset.conditions } : null; })()")
                if info_a:
                    studio_panel(s, proc, "ascent-launch", a.shots, {"label": info_a["label"], "conditions": info_a["conditions"], "exploratory": None}, at="99999")
                else:
                    check("Launch ascent: the result shows the run's conditions line", False, "no conditions line")
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
