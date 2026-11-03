r"""Automated UI smoke test of V&V Lab Studio, driving the real WebView2 window.

It launches a studio executable with a scratch library and a scratch configuration folder
(VVLAB_LIBRARY, VVLAB_CONFIG), so it never reads or writes the user's own preferences or library,
connects Playwright to the WebView2
DevTools endpoint (no browser download), waits for the platform, runs the product journeys and
asserts what is visible on screen. Screenshots of each journey (dark and light, and a small window)
are written to docs/images/m11-studio/.

Usage (from the repository root, after `cargo build -p vv-studio` in desktop/):

    python desktop/studio/tests/ui_smoke.py [--exe PATH] [--domains DIR] [--shots DIR] [--port N]

Against the installed application, using the domain hosts installed next to it:

    python desktop/studio/tests/ui_smoke.py --exe "%LOCALAPPDATA%\VV Lab Studio\vv-studio.exe" --domains ""

`--domains ""` leaves VVLAB_DOMAINS unset, so the studio uses its own resource directory.
Window sizes are set on the real window (Tauri setSize); DevTools viewport emulation is used only
if the window does not reach the requested inner size, and the report says which was used.
Requires `pip install playwright` (only the Python package; CDP needs no browser download).
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.request

from playwright.sync_api import sync_playwright

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

results = []
console_errors = []
sizing = []  # (requested, method, inner size reached)


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""), flush=True)
    return bool(cond)


class Studio:
    def __init__(self, page, shots):
        self.page = page
        self.shots = shots

    # The CSP forbids eval, so Playwright's wait_for_function cannot run in this page; poll instead.
    def wait(self, js, timeout=40.0, what=None):
        t0 = time.time()
        last = None
        while time.time() - t0 < timeout:
            try:
                if self.page.evaluate(js):
                    return True
            except Exception as e:  # page navigating or element missing
                last = e
            time.sleep(0.1)
        raise TimeoutError(f"timed out waiting for {what or js} ({last})")

    def js(self, expr, arg=None):
        return self.page.evaluate(expr, arg) if arg is not None else self.page.evaluate(expr)

    def invoke(self, name, args=None):
        return self.page.evaluate("([n, a]) => window.__TAURI__.core.invoke(n, a)", [name, args or {}])

    def shot(self, name):
        path = os.path.join(self.shots, name + ".png")
        # Transient notifications from earlier steps would hide part of the documented state.
        self.page.evaluate("document.querySelectorAll('#toasts .toast').forEach((t) => t.remove())")
        self.page.screenshot(path=path)
        return path

    def nav(self, view):
        self.page.click(f".nav-btn[data-view='{view}']")
        self.wait(f"window.__studio.view() === '{view}'")

    def theme(self, name):
        back = self.js("window.__studio.view()")
        self.nav("settings")
        self.page.click(f"#theme-seg [data-theme='{name}']")
        self.wait(f"document.documentElement.dataset.theme === '{name}'")
        if back != "settings":
            self.nav(back)
        time.sleep(0.6)

    def both(self, name):
        """Screenshot the current state in dark and in light, ending in dark."""
        self.theme("dark")
        self.shot(f"{name}-dark")
        self.theme("light")
        self.shot(f"{name}-light")
        self.theme("dark")

    def domain(self, domain_id):
        self.nav("prepare")
        self.page.click(f"button[data-domain='{domain_id}']")
        self.wait(f"document.querySelector(\"button[data-domain='{domain_id}']\").getAttribute('aria-checked') === 'true'")

    def demo(self, domain_id, demo_id, multi):
        self.domain(domain_id)
        self.page.click(f"button[data-demo='{demo_id}']")
        if multi:
            self.wait("window.__studio.view() === 'compare' && document.querySelector('.matrix')", what="comparison")
        else:
            self.wait("window.__studio.view() === 'run' && window.__studio.run() && document.querySelector('.verdict')", what="run")
        time.sleep(0.8)

    def open_compared(self, index):
        self.page.click(f".run-key >> nth={index} >> text=Open")
        self.wait("window.__studio.view() === 'run' && window.__studio.run() && document.querySelector('.verdict')")
        time.sleep(0.8)

    def verdict(self, which):
        return self.page.inner_text(f".verdict[aria-label='{which}'] .verdict-v").strip()

    def resize(self, w, h):
        """Sets the inner size of the real window; falls back to viewport emulation if it is not reached."""
        try:
            self.cdp().send("Emulation.clearDeviceMetricsOverride")
        except Exception:
            pass
        err = None
        try:
            self.page.evaluate("([w, h]) => window.__TAURI__.window.getCurrentWindow().setSize(new window.__TAURI__.window.LogicalSize(w, h))", [w, h])
        except Exception as e:
            err = str(e)
        got = None
        t0 = time.time()
        while time.time() - t0 < 3:
            got = self.js("[innerWidth, innerHeight]")
            if abs(got[0] - w) <= 1 and abs(got[1] - h) <= 1:
                break
            time.sleep(0.1)
        if err is None and abs(got[0] - w) <= 1 and abs(got[1] - h) <= 1:
            sizing.append((f"{w}x{h}", "real window", f"{got[0]}x{got[1]}"))
        else:
            self.page.set_viewport_size({"width": w, "height": h})
            sizing.append((f"{w}x{h}", "emulation fallback", f"window reached {got[0]}x{got[1]}" + (f"; setSize error {err}" if err else "")))
        time.sleep(0.6)

    def cdp(self):
        if not hasattr(self, "_cdp"):
            self._cdp = self.page.context.new_cdp_session(self.page)
        return self._cdp

    def no_private_text(self):
        """True when no visible text shows the user name or the profile folder."""
        user = os.environ.get("USERNAME", "")
        profile = os.environ.get("USERPROFILE", "")
        text = self.js("document.body.innerText")
        bad = [x for x in (user, profile) if x and x.lower() in text.lower()]
        return not bad, bad

    def no_hscroll(self):
        return self.js("""() => {
            const v = [...document.querySelectorAll('.view')].find((x) => !x.hidden);
            return document.documentElement.scrollWidth <= innerWidth && document.body.scrollWidth <= innerWidth
                && (!v || v.scrollWidth <= v.clientWidth + 1);
        }""")


def journeys(s):
    p = s.page

    # Developer domains are hidden by default.
    s.nav("prepare")
    check("developer domain hidden by default", p.locator("button[data-domain='reference-oscillator']").count() == 0)
    check("user-facing domains listed", p.locator("button[data-domain='rocket-landing']").count() == 1 and p.locator("button[data-domain='ground-vehicle']").count() == 1)

    # (1) Nominal ground mission demonstration.
    s.demo("ground-vehicle", "nominal-drive", multi=False)
    check("J1 ground nominal: outcome completed", "Mission completed" in s.verdict("Mission outcome"), s.verdict("Mission outcome"))
    check("J1 ground nominal: safety safe", s.verdict("Safety").startswith("Safe"), s.verdict("Safety"))
    check("J1 ground nominal: demonstration expectation shown", "Expected" in p.inner_text(".demo-banner"))
    check("J1 ground nominal: 2D scene drawn", p.locator(".scene-pane canvas").count() >= 1 and s.js("window.__studio.run().scene") == "ground-2d" and p.locator(".scene-pane .error-text").count() == 0)
    p.keyboard.press("End")
    time.sleep(0.4)
    s.both("journey-1-ground-nominal")

    # (2) Ground mission with injected faults, prepared in the form: GPS dropout and a delayed command.
    s.domain("ground-vehicle")
    p.select_option("#f-scenario", "nominal_stop")
    p.select_option(".add-fault select", "gps_dropout")
    p.click(".add-fault button")
    p.fill(".unit-input[data-field='fault0-end'] input", "10")
    p.select_option(".add-fault select", "delayed_movement")
    p.click(".add-fault button")
    s.wait("document.querySelectorAll('.fault-row').length === 2")
    s.wait("document.querySelector('.valid-state.ok')", what="platform validation")
    check("J2 form: request accepted by the platform before running", p.locator(".valid-state.ok").count() == 1)
    p.click("#f-seed")
    p.keyboard.press("Control+Enter")
    s.wait("window.__studio.view() === 'run' && window.__studio.run() && document.querySelector('.verdict')")
    time.sleep(0.8)
    check("J2 injected failure: mission outcome still completed", "Mission completed" in s.verdict("Mission outcome"), s.verdict("Mission outcome"))
    check("J2 injected failure: safety unsafe, shown separately", s.verdict("Safety").startswith("Unsafe"), s.verdict("Safety"))
    check("J2 injected failure: safe_fallback invariant failed", p.locator(".req.v-unsafe[data-id='safe_fallback']").count() == 1)
    # Failed requirement click moves the time cursor.
    t_req = p.inner_text(".req[data-id='safe_fallback'] .req-t")
    p.click(".req[data-id='safe_fallback'] .req-t")
    time.sleep(0.4)
    check("failed requirement click moves the time cursor", abs(s.js("window.__studio.run().t") - 7) < 1e-9 and "tick 7" in p.inner_text(".time-now"), f"{t_req} -> {s.js('window.__studio.run()')}")
    s.both("journey-2-ground-injected-failure")
    j2_run = s.js("window.__studio.run().runId")

    # Replay verified (recomputation in the domain host).
    p.click(".run-actions button:has-text('Replay')")
    s.wait("document.querySelector('.replay-verdict')", what="replay verdict")
    check("replay verified", "Verified" in p.inner_text(".replay-verdict"), p.inner_text(".replay-verdict"))
    check("replay lists its checks", p.locator(".checks li").count() >= 3)
    p.evaluate("document.querySelector('.replay-verdict').scrollIntoView({ block: 'start' })")
    time.sleep(0.2)
    s.shot("replay-verified-dark")

    # Matched comparison from the form: the same seed and faults on two controllers.
    s.domain("ground-vehicle")
    p.select_option("#f-scenario", "x_first_overshoot")
    s.wait("document.querySelector('.valid-state.ok')")
    p.check(".ctl:has(#ctl-x_first) .ctl-cmp input[type='checkbox']")
    p.click("#compare-controllers")
    s.wait("window.__studio.view() === 'compare' && document.querySelectorAll('.run-key').length === 2", what="matched comparison")
    check("matched comparison of two controllers from the form", p.locator(".run-key").count() == 2)
    p.click("#view-compare button:has-text('Save comparison')")
    p.fill("#modal-root input[type='text']", "Axis policies, seed 42")
    p.click("#modal-root .btn-primary")
    time.sleep(0.4)
    # Save the mission as a scenario and reopen it from the sidebar.
    s.domain("ground-vehicle")
    p.select_option("#f-scenario", "x_first_overshoot")
    p.check(".ctl:has(#ctl-x_first) .ctl-cmp input[type='checkbox']")
    s.wait("document.querySelector('.valid-state.ok')")
    p.click(".actionbar button:has-text('Save scenario')")
    p.fill("#modal-root input[type='text']", "Overshoot, both policies")
    p.click("#modal-root .btn-primary")
    s.wait("[...document.querySelectorAll('.saved-item .name')].some((n) => n.textContent === 'Overshoot, both policies')", what="saved scenario listed")
    p.select_option("#f-scenario", "nominal_stop")
    p.click(".saved-item:has-text('Overshoot, both policies') button:has-text('Open')")
    time.sleep(0.4)
    check("saved scenario reopens into the form", p.input_value("#f-scenario") == "x_first_overshoot" and p.is_checked(".ctl:has(#ctl-x_first) .ctl-cmp input[type='checkbox']"))
    s.nav("library")
    p.click(".lib-head .tab:has-text('Saved comparisons')")
    p.click(".lib-row:has-text('Axis policies, seed 42') button:has-text('Open comparison')")
    s.wait("window.__studio.view() === 'compare' && document.querySelectorAll('.run-key').length === 2", what="saved comparison")
    check("saved comparison reopens from the library", "Axis policies, seed 42" in p.inner_text(".cmp-head h1"))
    s.nav("library")
    p.click(".lib-head .tab:has-text('Runs')")
    s.wait("document.querySelector('.lib-table tbody tr[data-run]')")
    boxes = p.locator(".lib-table tbody tr[data-run] input[type='checkbox']")
    boxes.nth(0).check()
    boxes.nth(1).check()
    p.click("#lib-compare")
    s.wait("window.__studio.view() === 'compare' && document.querySelectorAll('.run-key').length === 2", what="library comparison")
    check("library multi-select opens a comparison", p.locator(".run-key").count() == 2)
    s.domain("ground-vehicle")
    p.click("#view-prepare [role='radio']:has-text('Advanced (all)')")
    check("advanced view shows every parameter with its description", p.locator(".param").count() == 2 and "Range" in p.inner_text(".param .field-hint"))
    p.click("#view-prepare [role='radio']:has-text('Essential')")

    # Protected seed refused inline, before the backend is asked.
    s.domain("rocket-landing")
    p.fill("#f-seed", "3050")
    s.wait("document.querySelector('#e-seed').textContent.includes('protected')")
    check("protected seed refused inline with the reason", "M10 evaluation seeds" in p.inner_text("#e-seed"), p.inner_text("#e-seed"))
    check("run disabled while the seed is protected", p.is_disabled("#run-mission"))
    s.shot("protected-seed-dark")
    p.fill("#f-seed", "5000")
    s.wait("!document.querySelector('#e-seed').textContent")

    # (3) Nominal rocket landing demonstration (two controllers on the same seed).
    s.demo("rocket-landing", "nominal-landing", multi=True)
    check("J3 rocket nominal: comparison shows both runs", p.locator(".run-key").count() == 2)
    check("J3 rocket nominal: both landed", p.locator(".run-key .mini.v-pass:has-text('Landed')").count() == 2)
    s.both("journey-3-rocket-nominal-compare")
    s.open_compared(1)
    check("J3 rocket nominal: 3D scene present", s.js("window.__studio.run().scene") == "rocket-3d" and p.locator("#view-run .r3d canvas").count() == 1 and p.locator(".scene-pane .error-text").count() == 0)
    check("J3 rocket nominal: top and profile views drawn", p.locator("#view-run .pane-top canvas").count() == 2 and p.locator("#view-run .pane-prof canvas").count() == 2)
    check("J3 rocket nominal: class R", "class R" in s.verdict("Safety"))
    p.keyboard.press("End")
    time.sleep(0.2)
    for _ in range(30):
        p.keyboard.press("ArrowLeft")
    time.sleep(0.5)
    s.both("journey-3-rocket-nominal-run")

    # (4) Rocket sensor fault with fault management: radar altimeter stuck.
    s.demo("rocket-landing", "altimeter-stuck", multi=True)
    check("J4 altimeter stuck: three arms compared", p.locator(".run-key").count() == 3)
    check("J4 altimeter stuck: matrix marks disagreements", p.locator(".matrix tr.differs").count() >= 1)
    s.both("journey-4-altimeter-stuck-compare")
    s.open_compared(0)
    check("J4 altimeter stuck B+: landed, class R", "Landed" in s.verdict("Mission outcome") and "class R" in s.verdict("Safety"))
    marks = p.locator(".tl-mark")
    check("J4 altimeter stuck B+: events on the timeline", marks.count() >= 5)
    # Jump through events with ] until the isolation event is selected.
    found = False
    for _ in range(12):
        p.keyboard.press("]")
        time.sleep(0.1)
        if "isolates the radar group" in p.inner_text(".tl-detail"):
            found = True
            break
    check("J4 altimeter stuck B+: radar isolation event reached with ]", found)
    check("J4 altimeter stuck B+: D3 isolation declaration passes", p.locator(".req.v-pass[data-id='D3_isolation']").count() == 1)
    s.both("journey-4-altimeter-stuck-run")
    j4_run = s.js("window.__studio.run().runId")
    # Playback frame pacing with the 3D scene, 70 channels and the timeline all following the cursor.
    # Measured in the page (requestAnimationFrame intervals), outside the simulation; informational.
    p.keyboard.press("Home")
    p.click("#timeline-pane .tl-scrub")
    p.keyboard.press("Home")
    p.click("#timeline-pane .tbtn-main")
    frames = p.evaluate("""() => new Promise((done) => {
        const d = []; let last = 0; const t0 = performance.now();
        const f = (now) => { if (last) d.push(now - last); last = now;
            if (now - t0 < 2500) requestAnimationFrame(f); else done(d); };
        requestAnimationFrame(f); })""")
    p.click("#timeline-pane .tbtn-main")
    frames.sort()
    p50 = frames[len(frames) // 2]
    p95 = frames[int(len(frames) * 0.95)]
    moved = s.js("window.__studio.run().t") > 0
    print(f"  playback frame interval over 2.5 s: n={len(frames)} p50={p50:.1f} ms p95={p95:.1f} ms")
    check("playback advances the cursor and keeps a median frame interval under 20 ms", moved and p50 < 20, f"p50={p50:.1f} ms p95={p95:.1f} ms")
    # Uncertainty bands: the vertical estimation error inside 0 +- k sigma_z.
    p.click("#view-run .tele-head button:has-text('Signals')")
    p.fill("#view-run .picker input[type='search']", "err_z")
    time.sleep(0.2)
    p.click("#view-run .picker button:has-text('Clear')")
    p.check("#view-run .picker .pick-row input[type='checkbox']")
    p.click("#view-run .picker button:has-text('Done')")
    time.sleep(0.3)
    check("signal picker narrows the charts to one signal", p.locator("#view-run .chart").count() == 1)
    check("estimation error drawn with the declared sigma band around zero", "err_z: 0 ±" in p.inner_text("#view-run .chart .chart-head"), p.inner_text("#view-run .chart .chart-head"))
    s.shot("uncertainty-band-err-z-dark")
    p.click("#view-run .tele-head button:has-text('Signals')")
    p.click("#view-run .picker button:has-text('Select all')")
    p.click("#view-run .picker button:has-text('Done')")
    p.click("#view-run .tele-head [role='radio']:has-text('By unit')")
    time.sleep(0.2)
    heads = p.locator("#view-run .chart-head h3").all_inner_texts()
    check("telemetry arranged by unit", "Unit: m/s" in heads and "Unit: m" in heads, "; ".join(heads))
    p.click("#view-run .tele-head [role='radio']:has-text('By group')")
    for name in ["Pad", "Side", "Follow"]:
        p.click(f"#view-run [aria-label='Camera preset'] [role='radio']:has-text('{name}')")
        time.sleep(0.15)
    for name in ["Top", "Profile", "3D", "3D + plots"]:
        p.click(f"#view-run [aria-label='Scene layout'] [role='radio']:text-is('{name}')")
        time.sleep(0.15)
    p.click("#view-run [aria-label='Top view extent'] [role='radio']:has-text('Pad')")
    for tab in ["metrics", "prov", "notes", "verify"]:
        p.click(f"#view-run .tab[data-tab='{tab}']")
        time.sleep(0.15)
    check("metrics, provenance, notes and verification tabs render", p.locator("#view-run .req").count() >= 10)
    p.click("#view-run .tab[data-tab='prov']")
    check("provenance lists artifacts with hashes and reproduce commands", p.locator("#view-run .prov .grid-table tbody tr").count() >= 1 and p.locator("#view-run .cmds code").count() >= 1)
    p.click("#view-run .tab[data-tab='verify']")

    # (5) Two faults and an unsafe outcome, honestly explained.
    s.demo("rocket-landing", "bias-and-outage-unsafe", multi=True)
    check("J5 unsafe: compare view shows all four runs", p.locator(".run-key").count() == 4)
    check("J5 unsafe: one run unsafe in the legend", p.locator(".run-key .mini.v-unsafe").count() == 1)
    s.both("journey-5-two-faults-compare")
    idx = s.js("[...document.querySelectorAll('.run-key')].findIndex((k) => k.querySelector('.mini.v-unsafe'))")
    s.open_compared(idx)
    check("J5 unsafe baseline: safety unsafe", s.verdict("Safety").startswith("Unsafe"), s.verdict("Safety"))
    check("J5 unsafe baseline: outcome reported separately from safety", s.verdict("Mission outcome") != s.verdict("Safety"))
    check("J5 unsafe baseline: S5 no powered ascent failed", p.locator(".req.v-unsafe[data-id='S5_no_powered_ascent']").count() == 1)
    check("J5 unsafe baseline: model validity shown", "not flight software" in p.inner_text(".validity-strip"))
    s5 = p.locator(".req[data-id='S5_no_powered_ascent'] button.req-t")
    if s5.count():
        s5.click()
        time.sleep(0.4)
    s.both("journey-5-two-faults-unsafe-run")
    p.click(".tab[data-tab='notes']")
    time.sleep(0.2)
    check("J5 notes tab lists the domain notes", p.locator(".note-list li").count() >= 3)
    s.shot("journey-5-notes-dark")

    # Library search finds a run, and label editing works.
    s.nav("library")
    s.wait("document.querySelector('.lib-table tbody tr[data-run]')")
    p.fill("#lib-search", j2_run)
    time.sleep(0.3)
    rows = p.locator(".lib-table tbody tr[data-run]")
    check("library search finds the injected-failure run by id", rows.count() == 1 and rows.first.get_attribute("data-run") == j2_run)
    rows.first.click()
    p.fill("#lib-label", "GPS dropout and delayed command")
    p.click(".lib-detail button:has-text('Save label and notes')")
    s.wait("document.querySelector('.lib-detail [aria-live]').textContent.includes('Saved')")
    p.fill("#lib-search", "delayed command")
    time.sleep(0.3)
    check("library search finds the run by its new label", p.locator(".lib-table tbody tr[data-run]").count() == 1)
    p.fill("#lib-search", "")
    time.sleep(0.3)
    ok, bad = s.no_private_text()
    check("library shows no user name or profile path", ok, ", ".join(bad))
    s.both("library")

    # Keyboard help and the command palette.
    p.keyboard.press("Escape")
    p.locator("body").press("?")
    s.wait("!document.getElementById('modal-root').hidden && document.querySelector('.shortcuts')", what="shortcut help")
    check("? opens the keyboard shortcut help", p.locator(".shortcuts tr").count() >= 8)
    p.keyboard.press("Escape")
    s.wait("document.getElementById('modal-root').hidden")
    p.keyboard.press("Control+k")
    s.wait("document.querySelector('.palette-input')", what="palette")
    p.keyboard.type("altimeter")
    time.sleep(0.4)
    check("Ctrl+K palette finds demonstrations and runs", p.locator(".palette-list li[role='option']").count() >= 2)
    s.shot("palette-dark")
    p.keyboard.press("Escape")
    s.wait("document.getElementById('modal-root').hidden")

    # Evidence export through the shell command (the Save dialog itself is not automated).
    exported = s.invoke("export_evidence", {"runId": j2_run, "choose": False})
    exported_file = os.path.expandvars(str(exported).replace("%USERPROFILE%", os.environ.get("USERPROFILE", ""))) if exported else ""
    check("evidence package exported to the library", bool(exported) and str(exported).endswith(".zip") and os.path.isfile(exported_file), str(exported))

    # Theme switch.
    s.theme("light")
    check("theme switch to light", s.js("document.documentElement.dataset.theme") == "light")
    s.theme("dark")
    check("theme switch to dark", s.js("document.documentElement.dataset.theme") == "dark")

    # Developer domain usable through the same screens when enabled.
    s.nav("settings")
    p.click("#pref-dev")
    s.nav("prepare")
    s.wait("document.querySelector(\"button[data-domain='reference-oscillator']\")")
    check("developer domain listed when enabled", p.locator("button[data-domain='reference-oscillator'] .tag-dev").count() == 1)
    s.domain("reference-oscillator")
    p.fill("#f-seed", "950")
    s.wait("document.querySelector('#e-seed').textContent.includes('protected')")
    check("reference domain: protected seed refused inline", "900 to 999" in p.inner_text("#e-seed") and p.is_disabled("#run-mission"))
    p.fill("#f-seed", "7")
    p.select_option(".add-fault select", "sensor_bias")
    p.click(".add-fault button")
    s.wait("document.querySelector('.valid-state.ok')")
    p.click("#run-mission")
    s.wait("window.__studio.view() === 'run' && window.__studio.run() && window.__studio.run().scene === 'none'")
    time.sleep(0.6)
    check("reference domain: run opens with no scene and full verification", p.locator(".req").count() == 2 and p.locator(".chart").count() >= 1)
    check("reference domain: outcome and safety shown", p.locator(".verdict").count() == 2)
    s.both("developer-reference-domain")
    s.nav("settings")
    time.sleep(0.3)
    ok, bad = s.no_private_text()
    check("settings show no user name or profile path", ok, ", ".join(bad))
    s.shot("settings-dark")

    # Minimum window: 1024 x 640 without horizontal page scroll, in every workspace.
    s.resize(1024, 640)
    ok = True
    for v in ["prepare", "run", "compare", "library", "settings"]:
        s.nav(v)
        time.sleep(0.5)
        this = s.no_hscroll()
        ok &= this
        if not this:
            print(f"  horizontal scroll in {v}")
    check("1024x640: no horizontal scroll in any workspace", ok)
    s.nav("compare")
    time.sleep(0.4)
    s.shot("small-1024x640-compare-dark")
    s.nav("prepare")
    time.sleep(0.3)
    s.shot("small-1024x640-prepare-dark")
    # Reopen the altimeter-stuck B+ run from the library (double-click).
    s.nav("library")
    p.fill("#lib-search", j4_run)
    time.sleep(0.3)
    p.dblclick(f".lib-table tbody tr[data-run='{j4_run}']")
    s.wait(f"window.__studio.run() && window.__studio.run().runId === '{j4_run}'")
    time.sleep(0.8)
    check("library opens a stored run in the workspace", s.js("window.__studio.run().scene") == "rocket-3d")
    p.keyboard.press("End")
    for _ in range(40):
        p.keyboard.press("ArrowLeft")
    time.sleep(0.6)
    check("1024x640: rocket run workspace without horizontal scroll", s.no_hscroll())
    s.shot("small-1024x640-run-dark")
    for w, h in [(1366, 768), (1920, 1080)]:
        s.resize(w, h)
        check(f"{w}x{h}: no horizontal scroll in the run workspace", s.no_hscroll())
        s.shot(f"run-{w}x{h}-dark")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=os.path.join(REPO, "desktop", "target", "debug", "vv-studio.exe"))
    ap.add_argument("--domains", default=os.path.join(REPO, "desktop", "target", "release", "domains"),
                    help='domain hosts folder; "" leaves VVLAB_DOMAINS unset (installed resource directory)')
    ap.add_argument("--shots", default=os.path.join(REPO, "docs", "images", "m11-studio"))
    ap.add_argument("--port", type=int, default=9222)
    ap.add_argument("--keep-library", action="store_true")
    a = ap.parse_args()
    a.exe = os.path.expandvars(a.exe)
    if not os.path.isfile(a.exe):
        print(f"studio executable not found: {a.exe} (build it with `cargo build -p vv-studio` in desktop/)")
        return 2
    os.makedirs(a.shots, exist_ok=True)
    library = tempfile.mkdtemp(prefix="vv-studio-ui-")
    config = tempfile.mkdtemp(prefix="vv-studio-ui-config-")
    env = dict(os.environ)
    env.pop("VVLAB_DOMAINS", None)
    env.pop("VVLAB_EXTRA_DOMAINS", None)
    if a.domains:
        env["VVLAB_DOMAINS"] = a.domains
    env["VVLAB_LIBRARY"] = library
    env["VVLAB_CONFIG"] = config
    print(f"exe {a.exe}\ndomains {a.domains or '(installed resource directory)'}\nlibrary {library}\nconfig {config}")
    env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"--remote-debugging-port={a.port}"
    # A running instance would swallow the launch (single-instance plugin) and keep its own library.
    subprocess.run(["taskkill", "/F", "/IM", os.path.basename(a.exe)], capture_output=True)
    proc = subprocess.Popen([a.exe], env=env)
    page = None
    try:
        for _ in range(120):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{a.port}/json/version", timeout=1)
                break
            except Exception:
                time.sleep(0.25)
        else:
            # Say why there is nothing to drive: the studio exited, or WebView2 never opened the port.
            state = "running" if proc.poll() is None else f"exited with code {proc.returncode}"
            check("WebView2 DevTools endpoint opened", False, f"studio {state}; no endpoint on port {a.port}")
            return 1
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{a.port}")
            page = browser.contexts[0].pages[0]
            page.on("pageerror", lambda e: console_errors.append(str(e)))
            page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
            s = Studio(page, a.shots)
            s.wait("window.__TAURI__ && window.__studio", what="studio script")
            # Preferences live in the scratch VVLAB_CONFIG folder; start from the defaults plus dark.
            check("preferences start empty in the scratch configuration", s.invoke("get_prefs") == {})
            try:
                s.invoke("set_prefs", {"prefs": {"theme": "dark"}})
                s.resize(1440, 900)
                page.reload()
                t0 = time.time()
                s.wait("window.__studio && document.getElementById('startup').hidden", timeout=90, what="platform ready")
                check("startup reaches ready", True, f"{time.time() - t0:.1f} s")
                info = s.invoke("app_info")
                check("platform ready with three domains and none rejected", info["ready"] and info["start"]["domains"] == 3 and not info["start"]["rejected"], json.dumps(info.get("start")))
                journeys(s)
            except Exception as e:
                traceback.print_exc()
                check("journeys completed without an exception", False, repr(e))
                try:
                    s.shot("failure-state")
                except Exception:
                    pass
            check("no script error in the page", not console_errors, "; ".join(console_errors[:5]))
    finally:
        proc.kill()
        proc.wait(timeout=10)
        if not a.keep_library:
            shutil.rmtree(library, ignore_errors=True)
            shutil.rmtree(config, ignore_errors=True)
    for req, method, reached in sizing:
        print(f"window {req}: {method} ({reached})")
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)} of {len(results)} checks passed; screenshots in {a.shots}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
