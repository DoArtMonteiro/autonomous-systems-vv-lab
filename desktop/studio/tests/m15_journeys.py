r"""M15 journeys of V&V Lab Studio in the real WebView2 window: the Explorer path from Home to a first
landing and its variations, the Analyst hand-offs, the Researcher path from a mission to the claim
behind it, the ground-vehicle mission, the library filters, keyboard playback and layout checks.
Screenshots go to --shots. It uses a scratch library and configuration (VVLAB_LIBRARY, VVLAB_CONFIG).

    python desktop/studio/tests/m15_journeys.py --exe desktop/target/release/vv-studio.exe --domains desktop/target/release/domains
    python desktop/studio/tests/m15_journeys.py --exe "%LOCALAPPDATA%\VV Lab Studio\vv-studio.exe" --domains ""

These are scripted checks of what the screen shows. They are not observations of people using it.
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

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
results = []
errors = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail else ""), flush=True)
    return bool(cond)


class S:
    def __init__(self, page, shots):
        self.page = page
        self.shots = shots

    def js(self, expr, arg=None):
        return self.page.evaluate(expr, arg) if arg is not None else self.page.evaluate(expr)

    def wait(self, js, timeout=60.0, what=None):
        t0 = time.time()
        last = None
        while time.time() - t0 < timeout:
            try:
                if self.page.evaluate(js):
                    return time.time() - t0
            except Exception as e:  # noqa: BLE001
                last = e
            time.sleep(0.05)
        raise TimeoutError(f"timed out waiting for {what or js} ({last})")

    def shot(self, name):
        self.page.evaluate("document.querySelectorAll('#toasts .toast').forEach((t) => t.remove())")
        self.page.screenshot(path=os.path.join(self.shots, name + ".png"))

    def nav(self, view):
        self.page.click(f".nav-btn[data-view='{view}']")
        self.wait(f"window.__studio.view() === '{view}'")

    def theme(self, name):
        back = self.js("window.__studio.view()")
        self.nav("settings")
        self.page.click(f"#theme-seg [data-theme='{name}']")
        self.wait(f"document.documentElement.dataset.theme === '{name}'")
        self.page.evaluate(f"document.querySelector(\".nav-btn[data-view='{back}']\") && document.querySelector(\".nav-btn[data-view='{back}']\").click()")
        time.sleep(0.5)

    def resize(self, w, h):
        self.page.evaluate("([w, h]) => window.__TAURI__.window.getCurrentWindow().setSize(new window.__TAURI__.window.LogicalSize(w, h))", [w, h])
        t0 = time.time()
        while time.time() - t0 < 3:
            got = self.js("[innerWidth, innerHeight]")
            if abs(got[0] - w) <= 1 and abs(got[1] - h) <= 1:
                break
            time.sleep(0.1)
        time.sleep(0.5)

    def player(self):
        return self.js("window.__studio.player()")

    def wait_player(self, exp_id, timeout=90):
        return self.wait(f"(() => {{ const p = window.__studio.player(); return p && p.experience === '{exp_id}' && document.querySelector('.pl-hud dl'); }})()", timeout, f"player {exp_id}")

    def reveal(self):
        self.page.click(".pl-reveal")
        self.wait("document.querySelector('.pl-result')", 10, "result card")
        time.sleep(0.4)

    def results(self):
        return self.js("[...document.querySelectorAll('.pl-run-result')].map((e) => [e.dataset.outcome, e.dataset.safety])")

    def no_hscroll(self):
        return self.js("""() => {
            const v = [...document.querySelectorAll('.view')].find((x) => !x.hidden);
            return document.documentElement.scrollWidth <= innerWidth && (!v || v.scrollWidth <= v.clientWidth + 1);
        }""")

    def unnamed_buttons(self):
        return self.js("""() => [...document.querySelectorAll('button, [role=radio], input, select')].filter((b) => {
            if (b.offsetParent === null) return false;
            const n = (b.getAttribute('aria-label') || b.textContent || b.title || (b.labels && b.labels[0] && b.labels[0].textContent) || '').trim();
            return !n;
        }).map((b) => b.outerHTML.slice(0, 80))""")


def explorer(s):
    s.wait("window.__studio.view() === 'home'", 10, "home is the first screen")
    check("Explorer: Home is the first screen", True)
    text = s.js("document.querySelector('.home-hero').innerText")
    check("Explorer: Home says what the product does", "fail" in text.lower() and "claim" in text.lower(), text[:90])
    check("Explorer: Home has one primary action to a first landing", s.js("!!document.querySelector(\"[data-experience='first-landing'] [data-action='launch']:not([disabled])\")"))
    s.shot("m15-home-dark")
    t0 = time.time()
    s.page.click("#view-home [data-experience='first-landing'] [data-action='launch']")
    s.wait_player("first-landing")
    check("Explorer: one click from Home to a landing on screen", s.player()["scene"] == "rocket-3d", f"{time.time() - t0:.1f} s")
    check("Explorer: the landing plays by itself", s.player()["playing"])
    time.sleep(4.0)
    hud = s.js("document.querySelector('.pl-hud').innerText")
    check("Explorer: readouts are labelled as true state, estimate or derived", "Altitude" in hud and s.js("document.querySelectorAll('.pl-hud .kind-T').length >= 4 && document.querySelectorAll('.pl-hud .kind-D').length >= 1"), hud.replace("\n", " ")[:120])
    check("Explorer: the phase is shown", s.js("document.querySelector('.pl-phase-name') && document.querySelector('.pl-phase-name').textContent.length > 0"), s.js("document.querySelector('.pl-phase-name') && document.querySelector('.pl-phase-name').textContent"))
    s.shot("m15-player-first-landing-flight-dark")
    for cam in ("pad", "wide"):
        s.page.click(f".pl-cams [data-cam='{cam}']")
        time.sleep(0.6)
        s.shot(f"m15-player-first-landing-{cam}-dark")
    s.page.click(".pl-cams [data-cam='follow']")
    check("Explorer: the result is hidden until the end", s.js("!document.querySelector('.pl-result')"))
    s.reveal()
    check("Explorer: the result says the stage landed safely", s.results() == [["landed", "safe"]], json.dumps(s.results()))
    check("Explorer: the result explains why", s.js("!!document.querySelector('.pl-why p')"))
    s.shot("m15-player-first-landing-result-dark")
    s.page.click(".pl-next")
    s.wait_player("lying-altimeter")
    check("Explorer: next mission is the faulted variation", s.player()["experience"] == "lying-altimeter")
    check("Explorer: the variation has two runs to compare", len(s.player()["runs"]) == 2)
    s.page.click(".pl-runs [data-run='1']")
    time.sleep(0.6)
    check("Explorer: the scene switches to the second run", s.player()["active"] == 1)
    s.page.click(".pl-runs [data-run='0']")
    s.reveal()
    res = s.results()
    check("Explorer: baseline lands hard, robust lands", res == [["hard_landing", "safe"], ["landed", "safe"]], json.dumps(res))
    check("Explorer: the difference is located in time", s.js("/departs from/.test(document.querySelector('.pl-side').innerText)") and s.js("!!document.querySelector('.pl-mark.sev-diverge')"))
    check("Explorer: a failed requirement names expected and observed", s.js("/expected .* observed /.test(document.querySelector('.pl-failed').innerText)"))
    s.shot("m15-player-lying-altimeter-result-dark")


def analyst(s):
    s.page.click(".pl-head-actions [data-action='analyse']")
    s.wait("window.__studio.view() === 'run' && window.__studio.run() && document.querySelector('.verdict')", 30, "analysis")
    check("Analyst: Analyse opens the shown run with full telemetry", s.js("window.__studio.run().scene") == "rocket-3d")
    s.page.go_back() if False else None
    s.nav("missions")
    s.page.click("#view-missions [data-experience='lying-altimeter'] [data-action='launch']")
    s.wait_player("lying-altimeter")
    s.page.click(".pl-head-actions [data-action='compare']")
    s.wait("window.__studio.view() === 'compare' && document.querySelector('.matrix')", 30, "comparison")
    check("Analyst: Compare in detail opens the matrix of both runs", s.js("document.querySelectorAll('.run-key').length") == 2)
    s.nav("missions")
    s.page.click("#view-missions [data-experience='lying-altimeter'] [data-action='launch']")
    s.wait_player("lying-altimeter")
    s.page.click(".pl-head-actions [data-action='configure']")
    s.wait("window.__studio.view() === 'prepare'", 10)
    txt = s.js("document.querySelector('#view-prepare').innerText")
    check("Analyst: Change the conditions opens the request in Configure", "Configure a run" in txt and "Altimeter bias" in txt and s.js("document.querySelector('#view-prepare input[type=text], #view-prepare input:not([type])') !== null"))
    s.shot("m15-configure-from-player-dark")


def researcher(s):
    s.nav("missions")
    s.page.click(".ml-chip[data-category='claims']")
    n = s.js("document.querySelectorAll('.ml-card').length")
    check("Library: the Challenge a claim filter shows the claim-backed missions", n == 3, str(n))
    s.shot("m15-missions-claims-dark")
    s.page.click(".ml-chip[data-category='all']")
    s.shot("m15-missions-dark")
    s.page.click("#view-missions [data-experience='late-gnss'] [data-action='launch']")
    s.wait_player("late-gnss")
    s.reveal()
    res = s.results()
    check("Researcher: registered bias fails R5 only, later smaller bias fails R1", res == [["hard_landing", "safe"], ["hard_landing", "safe"]] and s.js("[...document.querySelectorAll('.pl-run-result')].map((e) => [...e.querySelectorAll('.pl-failed li .link')].map((b) => b.textContent).join('|'))") == ["Distance from pad centre", "Vertical speed at contact"], json.dumps(res))
    check("Researcher: the finding is labelled exploratory", "Exploratory" in s.js("document.querySelector('.pl-head .grade').textContent"))
    s.wait("document.querySelector(\".pl-claim [data-action='challenge']\") || /cannot be challenged/.test(document.querySelector('.pl-claim').innerText)", 60, "claim card")
    check("Researcher: the claim behind the mission can be challenged", s.js("!!document.querySelector(\".pl-claim [data-action='challenge']\")"), s.js("document.querySelector('.pl-claim').innerText.slice(0, 160)"))
    s.shot("m15-player-late-gnss-result-dark")
    s.page.click(".pl-claim [data-action='challenge']")
    s.wait("window.__studio.view() === 'discover' && document.querySelector('.dl-head h1')", 30, "discover")
    title = s.js("document.querySelector('.dl-head h1').textContent")
    check("Researcher: Challenge this claim opens that claim in Investigate", title == "G3 under a late GNSS bias", title)
    check("Researcher: the claim page explains what a challenge does", s.js("document.querySelectorAll('.dl-howto li').length") == 4)
    s.shot("m15-investigate-claim-dark")
    s.nav("missions")
    s.page.click("#view-missions [data-experience='threshold-trade-off'] [data-action='launch']")
    s.wait_player("threshold-trade-off")
    s.reveal()
    res = s.results()
    check("Researcher: the mitigation trades an unsafe hard landing for an R5 failure", res == [["hard_landing", "unsafe"], ["hard_landing", "safe"]], json.dumps(res))
    s.shot("m15-player-threshold-result-dark")


def ground(s):
    s.nav("missions")
    s.page.click(".ml-chip[data-domain='ground-vehicle']")
    s.page.click("#view-missions [data-experience='corridor'] [data-action='launch']")
    s.wait_player("corridor")
    check("Ground: the corridor mission shows the top view", s.player()["scene"] == "ground-2d")
    time.sleep(1.5)
    s.reveal()
    res = s.results()
    check("Ground: exact GPS safe, 1 mm noise unsafe, radius 250 mm safe", res == [["completed", "safe"], ["incomplete", "unsafe"], ["completed", "safe"]], json.dumps(res))
    s.shot("m15-player-corridor-result-dark")
    s.nav("missions")
    s.page.click(".ml-chip[data-domain='all']")


def keyboard(s):
    s.nav("missions")
    s.page.click("#view-missions [data-experience='first-landing'] [data-action='launch']")
    s.wait_player("first-landing")
    s.page.focus(".pl-play")
    s.page.keyboard.press("Escape")
    s.js("document.activeElement && document.activeElement.blur()")
    was = s.player()["playing"]
    s.page.keyboard.press("Space")
    time.sleep(0.3)
    check("Keyboard: Space toggles playback", s.player()["playing"] != was)
    s.page.keyboard.press("End")
    time.sleep(0.4)
    check("Keyboard: End jumps to the end and reveals the result", s.player()["revealed"])
    s.page.keyboard.press("Home")
    time.sleep(0.3)
    check("Keyboard: Home returns to the start", s.player()["t"] == 0)
    s.page.keyboard.press("1")
    s.wait("window.__studio.view() === 'home'", 5)
    check("Keyboard: 1 goes Home", True)


def layout(s):
    for w, h in ((1024, 640), (1366, 768), (1920, 1080)):
        s.resize(w, h)
        for view in ("home", "missions"):
            s.nav(view)
            check(f"Layout {w}x{h}: {view} has no horizontal scroll", s.no_hscroll())
        s.page.click("#view-missions [data-experience='first-landing'] [data-action='launch']") if True else None
        s.wait_player("first-landing")
        check(f"Layout {w}x{h}: player has no horizontal scroll", s.no_hscroll())
        s.shot(f"m15-player-{w}x{h}-dark")
        bad = s.unnamed_buttons()
        check(f"Layout {w}x{h}: every visible control has a name", not bad, "; ".join(bad[:3]))
    s.resize(1440, 900)
    s.theme("light")
    s.nav("home")
    s.shot("m15-home-light")
    s.nav("missions")
    s.page.click("#view-missions [data-experience='lying-altimeter'] [data-action='launch']")
    s.wait_player("lying-altimeter")
    s.reveal()
    s.shot("m15-player-lying-altimeter-light")
    s.theme("dark")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=os.path.join(REPO, "desktop", "target", "release", "vv-studio.exe"))
    ap.add_argument("--domains", default=os.path.join(REPO, "desktop", "target", "release", "domains"))
    ap.add_argument("--shots", default=os.path.join(REPO, "docs", "images", "m15-studio"))
    ap.add_argument("--port", type=int, default=9241)
    a = ap.parse_args()
    exe = os.path.abspath(os.path.expandvars(a.exe))
    os.makedirs(a.shots, exist_ok=True)
    env = dict(os.environ)
    for k in ("VVLAB_DOMAINS", "VVLAB_EXTRA_DOMAINS", "VVLAB_EXEC", "VVLAB_CLAIMS"):
        env.pop(k, None)
    if a.domains:
        root = os.path.dirname(os.path.abspath(a.domains))
        env["VVLAB_DOMAINS"] = os.path.abspath(a.domains)
        env["VVLAB_EXEC"] = os.path.join(root, "engines", "vv-exec.exe")
        env["VVLAB_CLAIMS"] = os.path.join(root, "discovery", "claims")
    env["VVLAB_LIBRARY"] = tempfile.mkdtemp(prefix="vv-m15-lib-")
    env["VVLAB_CONFIG"] = tempfile.mkdtemp(prefix="vv-m15-cfg-")
    env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"--remote-debugging-port={a.port}"
    subprocess.run(["taskkill", "/F", "/IM", os.path.basename(exe)], capture_output=True)
    time.sleep(0.5)
    proc = subprocess.Popen([exe], env=env)
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
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            s = S(page, a.shots)
            s.wait("window.__TAURI__ && window.__studio", 30, "studio script")
            page.evaluate("() => window.__TAURI__.core.invoke('set_prefs', { prefs: { theme: 'dark' } })")
            page.reload()
            s.wait("window.__studio && document.getElementById('startup').hidden", 90, "platform ready")
            s.resize(1440, 900)
            for part in (explorer, analyst, researcher, ground, keyboard, layout):
                try:
                    part(s)
                except Exception as e:  # noqa: BLE001
                    check(f"{part.__name__} completed", False, repr(e)[:300])
                    try:
                        s.shot(f"m15-failure-{part.__name__}")
                    except Exception:  # noqa: BLE001
                        pass
            check("no script error or console error", not errors, "; ".join(errors[:3]))
    finally:
        proc.kill()
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)} of {len(results)} checks passed; screenshots in {a.shots}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
