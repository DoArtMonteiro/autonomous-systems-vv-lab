r"""M16 journeys of V&V Lab Studio in the real WebView2 window: the geospatial view of a rocket
landing on a validated environment, Flight console for the rocket and the ground vehicle, view
switching that keeps the replay, event selection and the hand-off to analysis, the release of the
geospatial renderer when the player is left, and the behaviour with no environment and with a
tampered one. Screenshots go to --shots. It uses a scratch library and configuration.

    python desktop/studio/tests/m16_journeys.py --exe desktop/target/release/vv-studio.exe --domains desktop/target/release/domains --environments desktop/environments
    python desktop/studio/tests/m16_journeys.py --exe "%LOCALAPPDATA%\VV Lab Studio\vv-studio.exe" --domains "" --environments ""

These are scripted checks of what the screen shows. They are not observations of people using it.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from m15_journeys import S, check, errors, results  # noqa: E402

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def player(s):
    return s.js("window.__studio.player()")


def wait_renderer(s, name, timeout=30):
    return s.wait(f"(() => {{ const p = window.__studio.player(); return p && p.renderer === '{name}'; }})()", timeout, f"renderer {name}")


def record_hashes(s, run_ids):
    out = {}
    for rid in run_ids:
        rec = s.page.evaluate("(id) => window.__TAURI__.core.invoke('record', { runId: id })", rid)
        out[rid] = hashlib.sha256(json.dumps(rec, sort_keys=True).encode()).hexdigest()
    return out


def open_mission(s, exp_id):
    s.page.evaluate("(id) => document.dispatchEvent(new CustomEvent('vv-open-mission', { detail: id }))", exp_id)
    s.wait(f"(() => {{ const p = window.__studio.player(); return p && p.experience === '{exp_id}' && (document.querySelector('.pl-head') || document.querySelector('.mc')); }})()", 90, f"player {exp_id}")


def geospatial(s):
    open_mission(s, "first-landing")
    s.wait("document.querySelector('.pl-views')", 20, "view switch")
    check("Geo: the player offers Engineering, Geospatial and Flight console", s.js("[...document.querySelectorAll('.pl-views [data-view]')].map((b) => b.dataset.view).join(',')") == "engineering,geospatial,control")
    runs = player(s)["runs"]
    before = record_hashes(s, runs)
    s.page.click(".pl-views [data-view='geospatial']")
    t0 = time.time()
    wait_renderer(s, "geospatial", 30)
    s.wait("window.__studio.player().geoStats && window.__studio.player().geoStats.textures >= 1", 20, "terrain image on the GPU")
    check("Geo: the geospatial view loads from the local pack", True, f"{time.time() - t0:.2f} s")
    p = player(s)
    check("Geo: an environment is selected", bool(p["environment"]), str(p["environment"]))
    check("Geo: switching view keeps the same runs", p["runs"] == runs)
    sources_control(s)
    s.page.keyboard.press("Home")
    time.sleep(0.3)
    s.page.keyboard.press("Space")
    time.sleep(5.0)
    s.shot("m16-geo-cape-follow-dark")
    for cam in ("pad", "wide", "overhead"):
        s.page.click(f".pl-cams [data-cam='{cam}']")
        time.sleep(0.8)
        s.shot(f"m16-geo-cape-{cam}-dark")
    # M16.2: the world layer (buildings, structures, lidar vegetation) and the cinematic camera.
    w = (player(s).get("geoStats") or {}).get("world") or {}
    check("World: the Cape pack draws OSM buildings and lidar vegetation", w.get("buildings", 0) > 100 and w.get("trees", 0) > 1000 and w.get("shrubs", 0) > 10000, json.dumps(w)[:200])
    s.page.click(".pl-cams [data-cam='closeup']")
    time.sleep(1.0)
    tiers = (player(s)["geoStats"]["world"] or {}).get("vegetation_tiers") or [0, 0, 0]
    check("World: vegetation near the pad camera is drawn in full detail", tiers[0] > 0, str(tiers))
    s.page.click(".pl-cams [data-cam='director']")
    time.sleep(1.2)
    cam_ = player(s)["geoStats"]["camera"]
    check("Auto camera: the camera picks a shot from the playback state", cam_["mode"] == "director" and cam_["shot"] in ("wide", "follow", "pad", "closeup"), str(cam_.get("shot")))
    s.shot("m16-geo-cape-cinematic-dark")
    s.page.click(".pl-cams [data-cam='follow']")
    if player(s)["playing"]:
        s.page.click(".pl-play")
    s.wait("!window.__studio.player().playing", 5, "paused")
    t_before = player(s)["t"]
    s.page.click(".pl-views [data-view='control']")
    s.wait("document.querySelector('.mc')", 20, "flight console")
    wait_renderer(s, "geospatial", 30)
    check("Geo to Flight console keeps the playback time", abs(player(s)["t"] - t_before) < 1e-6, f"{t_before} -> {player(s)['t']}")
    check("Flight console keeps the landscape", player(s)["renderer"] == "geospatial")
    s.page.click(".mc-tools .pl-views [data-view='engineering']")
    wait_renderer(s, "engineering", 20)
    check("Flight console to Engineering keeps the playback time", abs(player(s)["t"] - t_before) < 1e-6)
    after = record_hashes(s, runs)
    check("Geo: placing the run on a landscape changes no record", before == after)
    # Second environment: relief that breaks the flat-ground assumption must be stated.
    s.page.click(".pl-views [data-view='geospatial']")
    wait_renderer(s, "geospatial", 30)
    # The catalogue: one card per validated pack, with its resolution and credits; a card switches the scene.
    s.page.click(".pl-env-cat")
    s.wait("document.querySelector('.envc-modal .envc')", 10, "environment catalogue")
    time.sleep(1.0)
    cards = s.js("[...document.querySelectorAll('.envc-modal .envc')].map((c) => c.dataset.env)")
    envs = s.js("[...document.querySelectorAll('.pl-env option')].map((o) => o.value).filter(Boolean)")
    check("Catalogue: one card per installed environment", sorted(cards) == sorted(envs) and len(cards) >= 3, ",".join(cards))
    txt = s.js("document.querySelector('.envc-modal').innerText")
    check("Catalogue: cards state resolution, relief, size and credits", "image 0.5 m" in txt and "relief within 500 m" in txt and "offline" in txt and "Copernicus" in txt)
    check("Catalogue: the thumbnails load from the packs", s.js("[...document.querySelectorAll('.envc-modal .envc-img')].every((i) => i.complete && i.naturalWidth > 0)"))
    s.shot("m16-environment-catalogue-dark")
    s.page.click(".envc-modal [data-use='santa-maria-azores']")
    wait_renderer(s, "geospatial", 30)
    check("Catalogue: choosing a card switches the scene", player(s)["environment"] == "santa-maria-azores")
    s.page.select_option(".pl-env", "santa-maria-azores")
    wait_renderer(s, "geospatial", 30)
    time.sleep(1.0)
    s.page.click(".pl-cams [data-cam='wide']")
    time.sleep(0.8)
    s.shot("m16-geo-santa-maria-wide-dark")
    s.page.select_option(".pl-env", "cape-canaveral")
    wait_renderer(s, "geospatial", 30)


def panel_open(s):
    return s.js("(() => { const p = document.querySelector('.si-panel'); const b = document.querySelector('.si-btn'); return !!p && !p.hidden && b.getAttribute('aria-expanded') === 'true'; })()")


def tap(s):
    # Synthetic touch-type pointer event and click: the attached WebView2 has no touch screen.
    s.js("(() => { const b = document.querySelector('.si-btn'); b.dispatchEvent(new PointerEvent('pointerenter', { pointerType: 'touch' })); b.click(); })()")
    time.sleep(0.2)


def sources_control(s):
    """The compact sources control: visible short credit, full notices on hover, click, keyboard and touch-type pointers."""
    note = s.js("document.getElementById('pl-scene-note').innerText")
    # M17: only the credits a licence wants in view of the map stay visible (ODbL here); every other
    # notice is in the panel, one press away.
    panel = s.js("document.querySelector('#pl-scene-note .si-panel').textContent")
    check("Sources: the map keeps the ODbL credit and points to the rest", "OpenStreetMap" in note and "more in Sources" in note and "Copernicus" not in note, note[:160].replace("\n", " "))
    check("Sources: the panel holds every notice", "Copernicus" in panel and "Sentinel" in panel and "NGA" in panel)
    hgt = s.js("document.getElementById('pl-scene-note').getBoundingClientRect().height")
    check("Sources: the closed control takes little room (under 64 px tall)", hgt < 64, f"{hgt:.0f} px")
    check("Sources: the panel is closed by default", not panel_open(s))
    s.page.focus(".si-btn")
    s.page.keyboard.press("Enter")
    time.sleep(0.2)
    check("Sources: Enter opens the panel", panel_open(s))
    txt = s.js("document.querySelector('.si-panel').innerText")
    check("Sources: the panel says what is simulated, context and illustrative", all(w in txt.lower() for w in ("simulated", "context", "illustrative")))
    check("Sources: the panel carries the full Copernicus DEM notice and the Sentinel notice", "produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018" in txt and "Copernicus Sentinel data" in txt)
    check("Sources: the panel states the flat-ground limitation", "flat ground" in txt)
    check("Sources: the panel states where buildings, heights and vegetation come from", "on the ground" in txt.lower() and "OpenStreetMap" in txt and "lidar" in txt and "ODbL" in txt)
    s.shot("m16-geo-sources-panel-dark")
    s.page.keyboard.press("Escape")
    time.sleep(0.2)
    check("Sources: Escape closes the panel and keeps the focus on the button", not panel_open(s) and s.js("!!document.activeElement && document.activeElement.classList.contains('si-btn')"))
    s.page.keyboard.press("Space")
    time.sleep(0.2)
    check("Sources: Space on the button opens the panel", panel_open(s))
    s.page.keyboard.press("Space")
    time.sleep(0.2)
    check("Sources: Space again closes it", not panel_open(s))
    s.page.hover(".si-btn")
    time.sleep(0.3)
    check("Sources: hovering opens the panel", panel_open(s))
    s.page.mouse.move(900, 160)
    time.sleep(0.5)
    check("Sources: leaving closes an unpinned panel", not panel_open(s))
    s.page.hover(".si-btn")
    time.sleep(0.2)
    s.page.click(".si-btn")
    s.page.mouse.move(900, 160)
    time.sleep(0.5)
    check("Sources: a click pins the panel open", panel_open(s))
    s.page.mouse.click(900, 160)
    time.sleep(0.2)
    check("Sources: a press outside closes it", not panel_open(s))
    tap(s)
    check("Sources: a tap opens the panel", panel_open(s))
    tap(s)
    check("Sources: a second tap closes it", not panel_open(s))
    s.js("document.activeElement && document.activeElement.blur()")


def set_frac(s, frac):
    s.page.evaluate("(f) => { const r = document.querySelector('.pl-range'); r.value = String(Number(r.min) + f * (Number(r.max) - Number(r.min))); r.dispatchEvent(new Event('input', { bubbles: true })); }", frac)
    time.sleep(0.4)


def gating(s):
    """Ordinary playback never shows a finding before its time; analysis mode shows everything."""
    open_mission(s, "two-faults")
    if s.js("!!document.querySelector('.mc')"):
        s.page.click(".mc-back")
        s.wait("document.querySelector('.pl-head')", 10, "player")
    if player(s)["playing"]:
        s.page.click(".pl-play")
    set_frac(s, 0.3)
    t = player(s)["t"] + 1e-6
    # Findings later than the playback time are not drawn at all (not even hidden): the player state
    # counts what the record holds against what the page draws.
    later = "(() => { const p = window.__studio.player(); return p.findings - p.findingsDrawn; })()"
    ahead = f"[...document.querySelectorAll('.pl-mark[data-gated]')].filter((b) => Number(b.dataset.t) > {t} && !b.hidden).length"
    check("Gating: the run has findings later than the playback time", s.js(later) > 0, str(s.js(later)))
    check("Gating: no later finding is shown on the player timeline", s.js(ahead) == 0)
    check("Gating: the result is not shown yet", s.js("!!document.querySelector('.pl-pending') && !document.querySelector('.pl-result')"))
    s.shot("m16-gating-player-before-dark")
    s.page.click(".pl-tend [data-action='analysis']")
    time.sleep(0.4)
    check("Gating: analysis mode shows the later findings and the result", s.js(ahead) > 0 and s.js("!!document.querySelector('.pl-result')"))
    check("Gating: the analysis switch says it is on", s.js("document.querySelector(\".pl-tend [data-action='analysis']\").getAttribute('aria-pressed')") == "true")
    s.shot("m16-gating-player-analysis-dark")
    open_mission(s, "lying-altimeter")
    if not s.js("!!document.querySelector('.mc')"):
        s.page.click(".pl-views [data-view='control']")
        s.wait("document.querySelector('.mc')", 20, "flight console")
    if player(s)["playing"]:
        s.page.click(".mct-play")
    s.page.keyboard.press("Home")
    time.sleep(0.4)
    vis = "[...document.querySelectorAll('.mct-mark')].filter((b) => !b.hidden && /sev-(violation|warning|detection)/.test(b.className)).length"
    allv = "[...document.querySelectorAll('.mct-mark')].filter((b) => /sev-(violation|warning|detection)/.test(b.className)).length"
    check("Gating MC: findings exist in the run", s.js(allv) > 0, str(s.js(allv)))
    check("Gating MC: none is drawn at the start of the playback", s.js(vis) == 0)
    check("Gating MC: the event list does not list them either", s.js("[...document.querySelectorAll('.mc-evlist li')].filter((l) => !l.hidden && /sev-(violation|warning|detection)/.test(l.innerHTML)).length") == 0)
    s.page.click(".mc-bottom [data-action='analysis']")
    time.sleep(0.4)
    check("Gating MC: analysis mode draws them", s.js(vis) == s.js(allv))
    s.page.click(".mc-bottom [data-action='analysis']")


def control_rocket(s):
    open_mission(s, "late-gnss")
    if not s.js("!!document.querySelector('.mc')"):
        s.page.click(".pl-views [data-view='control']")
    s.wait("document.querySelector('.mc')", 20, "flight console")
    if s.js("!!document.querySelector('.mc-tools .pl-env')"):
        s.page.select_option(".mc-tools .pl-env", "cape-canaveral")
        wait_renderer(s, "geospatial", 30)
    s.page.click(".mc-density [data-density='technical']")
    s.page.keyboard.press("Home")
    time.sleep(0.5)
    groups = s.js("[...document.querySelectorAll('.mc-left .mc-group')].map((g) => g.dataset.group)")
    check("MC rocket: telemetry is grouped for a rocket landing", all(g in groups for g in ("motion", "propulsion", "navigation", "sensors")), ",".join(groups))
    check("MC rocket: propellant comes from a recorded true-state channel", s.js("!!document.querySelector(\".mc-row[data-channel='propellant_kg'] .kind-T\")"))
    check("MC rocket: estimated and true heights are both shown with their origin", s.js("!!document.querySelector(\".mc-row[data-channel='est_z'] .kind-E\") && !!document.querySelector(\".mc-row[data-channel='pos_z'] .kind-T\")"))
    check("MC rocket: geographic values are tagged G", s.js("document.querySelectorAll(\".mc-group[data-group='geo'] .kind-G\").length >= 3"))
    check("MC rocket: requirements are pending before contact", s.js("[...document.querySelectorAll('.mc-right .mc-v')].some((e) => e.dataset.state === 'pending')"))
    check("MC rocket: two runs on the timeline", s.js("document.querySelectorAll('.mct-lane').length") == 2)
    check("MC rocket: the timeline marks where the runs part", s.js("document.querySelectorAll('.mct-fork').length >= 1"))
    s.shot("m16-control-rocket-technical-dark")
    # Later findings are drawn only once reached or in analysis mode.
    s.page.click(".mc-bottom [data-action='analysis']")
    time.sleep(0.4)
    marks = s.js("[...document.querySelectorAll('.mct-mark')].map((b) => b.getAttribute('aria-label'))")
    det = next((i for i, m in enumerate(marks) if "Controller detection" in m), None)
    check("MC rocket: a controller detection is on the timeline", det is not None, "; ".join(marks[:6]))
    if det is not None:
        s.page.locator(".mct-mark").nth(det).click()
        s.wait("!document.querySelector('.mc-evidence').hidden", 5, "evidence card")
        check("MC rocket: clicking an event pauses at its instant", not player(s)["playing"])
        check("MC rocket: the event opens an evidence card with a way into analysis", "Analyse at this instant" in s.js("document.querySelector('.mc-evidence').innerText"))
        time.sleep(0.8)
        s.shot("m16-control-rocket-event-dark")
    onset = next((i for i, m in enumerate(marks) if "Fault injected" in m or "Fault starts" in m), None)
    check("MC rocket: the fault onset is on the timeline", onset is not None)
    s.page.click(".mc-density [data-density='cinematic']")
    time.sleep(0.6)
    check("MC rocket: cinematic mode hides the side panels", s.js("getComputedStyle(document.querySelector('.mc-left')).display === 'none'"))
    s.page.keyboard.press("End")
    time.sleep(0.8)
    s.shot("m16-control-rocket-cinematic-end-dark")
    s.page.click(".mc-density [data-density='technical']")
    time.sleep(0.6)
    states = s.js("[...document.querySelectorAll('.mc-right .mc-v')].map((e) => e.dataset.req + ':' + e.dataset.state)")
    check("MC rocket: at the end every requirement is judged", not any(x.endswith(":pending") for x in states), ", ".join(states))
    s.page.click(".mc-run[data-run='1']")
    wait_renderer(s, "geospatial", 30)
    time.sleep(1.0)
    s.shot("m16-control-rocket-compare-dark")
    t = player(s)["t"]
    s.page.click("[data-action='analyse-here']")
    s.wait("window.__studio.view() === 'run' && window.__studio.run()", 30, "analysis")
    check("MC rocket: Analyse opens at the same instant", abs(s.js("window.__studio.run().t") - t) < 1e-6, f"{t}")
    p = player(s)
    check("Leaving the player releases the geospatial renderer", p["renderer"] == "suspended" and p["scene"] is None, json.dumps({k: p[k] for k in ("renderer", "scene")}))
    s.nav("missions")
    open_mission(s, "late-gnss")
    wait_renderer(s, "geospatial", 30)
    check("Returning to the player restores the geospatial view at the same instant", abs(player(s)["t"] - t) < 1e-6)


def control_ground(s):
    open_mission(s, "corridor")
    if s.js("!!document.querySelector('.mc')"):
        s.page.click(".mc-back")
        s.wait("document.querySelector('.pl-head')", 10, "player")
    check("MC ground: Geospatial is unavailable for a millimetre grid, with the reason", s.js("(() => { const b = document.querySelector(\".pl-views [data-view='geospatial']\"); return !!b && b.getAttribute('aria-disabled') === 'true' && (b.title || '').includes('millimetre'); })()"))
    s.page.click(".pl-views [data-view='control']")
    s.wait("document.querySelector('.mc')", 20, "flight console")
    s.page.click(".mc-density [data-density='technical']")
    time.sleep(0.5)
    text = s.js("document.querySelector('.mc-left').innerText")
    check("MC ground: ground-vehicle telemetry, no aerospace metrics", "East" in text and "Confidence" in text and "Altitude" not in text and "Propellant" not in text, text.replace("\n", " ")[:120])
    check("MC ground: three runs on the timeline", s.js("document.querySelectorAll('.mct-lane').length") == 3)
    s.page.keyboard.press("End")
    time.sleep(0.8)
    s.shot("m16-control-ground-technical-dark")


def home_and_library(s):
    s.nav("home")
    time.sleep(0.5)
    s.shot("m16-home-dark")
    s.nav("missions")
    time.sleep(0.5)
    s.shot("m16-library-dark")
    s.nav("settings")
    s.wait("document.querySelector('#env-settings table, #env-settings .error-text')", 10, "environment settings")
    rows = s.js("[...document.querySelectorAll('#env-settings tr[data-env]')].map((r) => r.dataset.env)")
    check("Settings: the installed environments are listed with sources and size", "cape-canaveral" in rows and "santa-maria-azores" in rows, ",".join(rows))
    check("Settings: Studio says it makes no network request", "No network" in s.js("document.getElementById('env-settings').innerText"))
    s.shot("m16-settings-environments-dark")


def layout(s):
    open_mission(s, "late-gnss")
    if not s.js("!!document.querySelector('.mc')"):
        s.page.click(".pl-views [data-view='control']")
        s.wait("document.querySelector('.mc')", 20, "flight console")
    for w, h in ((1440, 900), (1280, 800), (1024, 640)):
        s.resize(w, h)
        check(f"Layout {w}x{h}: no horizontal scroll in Flight console", s.no_hscroll())
        bad = s.unnamed_buttons()
        check(f"Layout {w}x{h}: every control has a name", not bad, "; ".join(bad[:3]))
        s.shot(f"m16-control-{w}x{h}-dark")
    s.resize(1440, 900)


def launch(exe, env, port):
    subprocess.run(["taskkill", "/F", "/IM", os.path.basename(exe)], capture_output=True)
    time.sleep(0.5)
    proc = subprocess.Popen([exe], env=env)
    for _ in range(400):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1)
            break
        except Exception:  # noqa: BLE001
            time.sleep(0.05)
    return proc


def session(pw, port, shots):
    browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
    page = browser.contexts[0].pages[0]
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    s = S(page, shots)
    s.wait("window.__TAURI__ && window.__studio", 30, "studio script")
    page.evaluate("() => window.__TAURI__.core.invoke('set_prefs', { prefs: { theme: 'dark' } })")
    page.reload()
    s.wait("window.__studio && document.getElementById('startup').hidden", 90, "platform ready")
    s.resize(1440, 900)
    return browser, s


def fallback(s, label):
    open_mission(s, "first-landing")
    if s.js("!!document.querySelector('.mc')"):
        s.page.click(".mc-back")
        s.wait("document.querySelector('.pl-head')", 10, "player")
    b = s.js("(() => { const b = document.querySelector(\".pl-views [data-view='geospatial']\"); return b ? { off: b.getAttribute('aria-disabled'), title: b.title } : null; })()")
    check(f"{label}: Geospatial is disabled and says why", bool(b) and b["off"] == "true" and "environment" in (b["title"] or ""), json.dumps(b))
    check(f"{label}: the engineering scene plays offline", player(s)["renderer"] == "engineering" and player(s)["scene"] == "rocket-3d")
    s.page.click(".pl-views [data-view='control']")
    s.wait("document.querySelector('.mc')", 20, "flight console")
    check(f"{label}: Flight console works on the engineering scene", player(s)["renderer"] == "engineering")
    s.shot(f"m16-{label.lower().replace(' ', '-')}-control-dark")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=os.path.join(REPO, "desktop", "target", "release", "vv-studio.exe"))
    ap.add_argument("--domains", default=os.path.join(REPO, "desktop", "target", "release", "domains"))
    ap.add_argument("--environments", default=os.path.join(REPO, "desktop", "environments"), help="packs folder; empty uses the installed ones")
    ap.add_argument("--shots", default=os.path.join(REPO, "docs", "images", "m16-studio"))
    ap.add_argument("--port", type=int, default=9243)
    ap.add_argument("--only", default="", help="comma-separated parts, e.g. geospatial,fallback")
    a = ap.parse_args()
    exe = os.path.abspath(os.path.expandvars(a.exe))
    os.makedirs(a.shots, exist_ok=True)
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
    env["VVLAB_LIBRARY"] = tempfile.mkdtemp(prefix="vv-m16-lib-")
    env["VVLAB_CONFIG"] = tempfile.mkdtemp(prefix="vv-m16-cfg-")
    env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"--remote-debugging-port={a.port}"
    only = [x for x in a.only.split(",") if x]
    parts = [p for p in (home_and_library, geospatial, gating, control_rocket, control_ground, layout) if not only or p.__name__ in only]
    if parts:
        proc = launch(exe, env, a.port)
        try:
            with sync_playwright() as pw:
                browser, s = session(pw, a.port, a.shots)
                for part in parts:
                    try:
                        part(s)
                    except Exception as e:  # noqa: BLE001
                        check(f"{part.__name__} completed", False, repr(e)[:300])
                        try:
                            s.shot(f"m16-failure-{part.__name__}")
                        except Exception:  # noqa: BLE001
                            pass
                browser.close()
        finally:
            proc.kill()
    if not only or "fallback" in only:
        # Offline with no environment at all, and with a tampered pack: the Studio still works.
        empty = tempfile.mkdtemp(prefix="vv-m16-noenv-")
        tampered = tempfile.mkdtemp(prefix="vv-m16-bad-")
        src_root = os.path.abspath(a.environments) if a.environments else os.path.join(REPO, "desktop", "environments")
        src = os.path.join(src_root, "cape-canaveral")
        if os.path.isdir(src):
            dst = os.path.join(tampered, "cape-canaveral")
            shutil.copytree(src, dst)
            with open(os.path.join(dst, "height.u16"), "r+b") as f:
                f.seek(4096)
                byte = f.read(1)
                f.seek(4096)
                f.write(bytes([byte[0] ^ 1]))
        for label, folder in (("No environment", empty), ("Tampered pack", tampered)):
            env2 = dict(env)
            env2["VVLAB_ENVIRONMENTS"] = folder
            env2["VVLAB_CONFIG"] = tempfile.mkdtemp(prefix="vv-m16-cfg-")
            proc = launch(exe, env2, a.port)
            try:
                with sync_playwright() as pw:
                    browser, s = session(pw, a.port, a.shots)
                    try:
                        if label == "Tampered pack":
                            s.nav("settings")
                            s.wait("document.querySelector('#env-settings table, #env-settings .error-text')", 10, "environment settings")
                            txt = s.js("document.getElementById('env-settings').innerText")
                            check("Tampered pack: it is rejected with the reason", "Rejected packs" in txt and "SHA-256" in txt, txt[-160:].replace("\n", " "))
                            s.shot("m16-settings-tampered-pack-dark")
                        fallback(s, label)
                    except Exception as e:  # noqa: BLE001
                        check(f"{label} completed", False, repr(e)[:300])
                    browser.close()
            finally:
                proc.kill()
    real = [e for e in errors if "Failed to load resource" not in e]
    check("no script error or console error", not real, "; ".join(real[:3]))
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)} of {len(results)} checks passed; screenshots in {a.shots}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
