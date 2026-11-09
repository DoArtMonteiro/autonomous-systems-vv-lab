r"""M18 end-to-end journey in the real WebView2 window: open Mission Control, choose a vehicle in the
hangar, choose an environment, run the vehicle as defined, change a physical design parameter, run
again, read the physically different result, compare the two runs, watch both in the mission player
(engineering and geospatial views) and check the Cinematic View entry for the same record. A second
part does the same with a launch vehicle (payload). Every number printed comes from the records the
platform wrote; the numbers go to <shots>/m18-numbers.json. It uses a scratch library.

    python desktop/studio/tests/m18_journeys.py --exe desktop/target/release/vv-studio.exe --domains desktop/target/release/domains
    python desktop/studio/tests/m18_journeys.py --exe "%LOCALAPPDATA%\VV Lab Studio\vv-studio.exe" --domains "" --environments ""

These are scripted checks of what the screen shows. They are not observations of people using it.
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
from m16_journeys import launch, session  # noqa: E402

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
NUMBERS = {}


def lab(s):
    return s.js("window.__studio.lab()")


def record(s, rid):
    return s.page.evaluate("(id) => window.__TAURI__.core.invoke('record', { runId: id })", rid)


def req_map(rec):
    return {r["id"]: r for r in rec["requirements"]}


def metric_map(rec):
    return {m.get("id", m.get("label")): m.get("value") for m in rec.get("metrics", [])}


def run_and_wait(s, timeout=180):
    before = (lab(s) or {}).get("exp")
    s.page.click("#lab-run")
    s.wait(f"(() => {{ const l = window.__studio.lab(); return l && !l.busy && l.exp && l.exp !== {json.dumps(before)}; }})()", timeout, "experiment run")
    time.sleep(0.3)
    return lab(s)["exp"]


def set_param(s, pid, value):
    s.js(f"(() => {{ const d = document.querySelector('[data-param=\"{pid}\"]').closest('details'); if (d) d.open = true; }})()")
    s.page.fill(f"#lab-p-{pid}", str(value))
    s.page.dispatch_event(f"#lab-p-{pid}", "change")
    time.sleep(0.2)


def kill_godot():
    subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Process | Where-Object { $_.ProcessName -like 'Godot*' } | Stop-Process -Force"], capture_output=True)


def home(s):
    s.nav("home")
    s.wait("document.querySelector('.hm-paths')", 20, "Mission Control")
    paths = s.js("[...document.querySelectorAll('.hm-path')].map((e) => e.dataset.path)")
    check("Mission Control: three paths (mission, vehicle, environments)", paths == ["mission", "vehicle", "environments"], ", ".join(paths))
    s.wait("Number(document.querySelector('.hm-stats div:nth-child(3) dd').textContent) > 0", 20, "environment count")
    stats = s.js("[...document.querySelectorAll('.hm-stats dd')].map((e) => e.textContent.trim())")
    check("Mission Control: eight environments counted", stats[2] == "8", json.dumps(stats))
    s.wait("document.querySelectorAll('.hm-mosaic img[src]').length >= 6", 20, "environment mosaic")
    check("Mission Control: the environment path shows real pack images", s.js("document.querySelectorAll('.hm-mosaic img[src]').length") >= 6)
    check("Mission Control: no horizontal scroll at 1440 px", s.no_hscroll())
    s.shot("m18-mission-control-dark")
    s.page.evaluate("document.querySelector('#view-home').scrollTop = 900")
    time.sleep(0.3)
    s.shot("m18-mission-control-lower-dark")
    s.page.evaluate("document.querySelector('#view-home').scrollTop = 0")


def hangar(s):
    s.page.click(".hm-path[data-path='vehicle'] [data-action='vehicles']")
    s.wait("window.__studio.view() === 'vehicles' && document.querySelector('.hg-card')", 20, "hangar")
    cards = s.js("[...document.querySelectorAll('.hg-card')].map((e) => e.dataset.vehicle)")
    check("Hangar: every vehicle of the installed domains is listed", len(cards) >= 6 and "heavy-return-stage" in cards and "small" in cards, ", ".join(cards))
    facts = s.js("[...document.querySelectorAll(\".hg-card[data-vehicle='heavy-return-stage'] .hg-facts div\")].map((d) => d.textContent)")
    check("Hangar: the heavy stage shows its template's attributes (30 t dry, 760 kN)", any("30" in f and "Dry mass" in f for f in facts) and any("760" in f for f in facts), "; ".join(facts))
    check("Hangar: exploratory and reference vehicles are labelled", s.js("document.querySelectorAll('.hg-card .hg-ev-explore').length >= 4 && document.querySelectorAll('.hg-card .hg-ev-ref').length >= 1"))
    s.shot("m18-hangar-dark")


def environments(s):
    s.nav("environments")
    s.wait("document.querySelectorAll('.at-card').length > 0", 30, "environments")
    ids = s.js("[...document.querySelectorAll('.at-card')].map((e) => e.dataset.env)")
    check("Environments: all eight packs are visible", len(ids) == 8, ", ".join(ids))
    s.wait("document.querySelectorAll('.at-card .at-img[src]').length === 8", 30, "thumbnails")
    s.page.click(".at-card[data-env='wallops-island'] [data-action='use']")
    s.wait("document.querySelector(\".at-card[data-env='wallops-island']\").classList.contains('is-current')", 10, "chosen")
    check("Environments: Wallops Island chosen for the missions", True)
    s.shot("m18-environments-dark")


def vehicle_experiment(s):
    s.nav("vehicles")
    s.page.click(".hg-card[data-vehicle='heavy-return-stage'] [data-action='design']")
    s.wait("window.__studio.view() === 'lab' && document.querySelector('.lab-base') && window.__studio.lab()", 120, "baseline run")
    open_group = s.js("(() => { const d = document.querySelector('[data-param=\"vehicle_thrust_scale\"]'); return d && d.closest('details').open; })()")
    check("Lab: the vehicle design parameters are open", bool(open_group))
    base_id = lab(s)["base"]
    base = record(s, base_id)
    check("Lab: the baseline flies the heavy stage", base["request"]["scenario"] == "heavy-return-landing")
    s.shot("m18-lab-heavy-baseline-dark")
    set_param(s, "vehicle_thrust_scale", 0.7)
    exp_id = run_and_wait(s)
    exp = record(s, exp_id)
    check("Lab: the experiment is a new record with the thrust factor", exp_id != base_id and exp["request"]["parameters"].get("vehicle_thrust_scale") == 0.7)
    ra, rb = req_map(base), req_map(exp)
    moved = {k: (ra[k]["observed"], rb[k]["observed"]) for k in ra if k in rb and ra[k]["observed"] != rb[k]["observed"]}
    check("Lab: a weaker engine changes the measured flight (requirement observations differ)", len(moved) >= 2, json.dumps(moved)[:300])
    check("Lab: the experiment is labelled exploratory", any(n.startswith("Exploratory case") for n in exp.get("notes", [])))
    NUMBERS["landing_thrust_0_7"] = {"base_run": base_id, "exp_run": exp_id, "seed": base["request"]["seed"],
                                    "base": {k: [v["status"], v["observed"]] for k, v in ra.items()},
                                    "exp": {k: [v["status"], v["observed"]] for k, v in rb.items()},
                                    "base_outcome": base["outcome"]["label"], "exp_outcome": exp["outcome"]["label"],
                                    "base_safety": base["safety"]["status"], "exp_safety": exp["safety"]["status"]}
    s.shot("m18-lab-heavy-thrust-dark")
    return base_id, exp_id


def compare(s, base_id, exp_id):
    s.page.click(".lab-result .btn:has-text('Compare signals in detail')")
    s.wait("window.__studio.view() === 'compare'", 30, "compare")
    time.sleep(2)
    text = s.js("document.querySelector('#view-compare').innerText")
    check("Compare: both runs are open", base_id[:8] in text and exp_id[:8] in text, " ".join(text[:200].split()))
    s.shot("m18-compare-dark")
    s.nav("lab")
    s.wait("document.querySelector('#lab-watch')", 20, "lab result")


def watch(s, base_id, exp_id):
    s.page.click("#lab-watch")
    s.wait("(() => { const p = window.__studio.player(); return p && p.experience.startsWith('runs:') && document.querySelector('.pl-hud dl'); })()", 120, "player")
    p = s.player()
    check("Player: plays the baseline and the experiment from their records", p["runs"] == [base_id, exp_id], json.dumps(p["runs"]))
    s.page.click(".pl-views [data-view='engineering']")
    s.wait("(() => { const p = window.__studio.player(); return p && p.view === 'engineering' && p.renderer === 'engineering'; })()", 60, "engineering scene")
    check("Player: the same two records play in the engineering scene", s.player()["runs"] == [base_id, exp_id])
    time.sleep(1.5)
    s.shot("m18-player-engineering-dark")
    s.page.click(".pl-views [data-view='geospatial']")
    s.wait("(() => { const p = window.__studio.player(); return p && p.renderer === 'geospatial'; })()", 90, "geospatial")
    p = s.player()
    check("Player: the geospatial view uses the chosen environment", p["environment"] == "wallops-island", str(p["environment"]))
    s.js("window.__studio.player() && document.querySelector('.pl-scrub input, input[type=range]') && 0")
    time.sleep(6)
    s.shot("m18-player-geospatial-wallops-dark")
    b = s.js("(() => { const b = document.querySelector(\"[data-action='cinematic']\"); return b ? { disabled: b.disabled, title: b.title } : null; })()")
    NUMBERS["cinematic_button"] = b
    if b and not b["disabled"]:
        check("Cinematic: the same record can open in the Cinematic View", True, b["title"])
        s.page.click("[data-action='cinematic']")
        running = False
        for _ in range(60):
            if "godot" in subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout.lower():
                running = True
                break
            time.sleep(0.5)
        check("Cinematic: the module process started for this run", running)
        time.sleep(6)
        kill_godot()
    else:
        check("Cinematic: not available here, and the button says why", bool(b) and bool(b["title"]), json.dumps(b))


def ascent(s):
    s.nav("vehicles")
    s.page.click(".hg-card[data-vehicle='small'] [data-action='design']")
    s.wait("window.__studio.view() === 'lab' && window.__studio.lab() && document.querySelector('.lab-base')", 180, "ascent baseline")
    base_id = lab(s)["base"]
    base = record(s, base_id)
    set_param(s, "small_payload_kg", 600)
    exp_id = run_and_wait(s, 240)
    exp = record(s, exp_id)
    ra, rb = req_map(base), req_map(exp)
    flipped = [k for k in ra if k in rb and ra[k]["status"] != rb[k]["status"]]
    check("Ascent: 600 kg payload changes which requirements pass", len(flipped) >= 1, ", ".join(flipped))
    NUMBERS["ascent_payload_600"] = {"base_run": base_id, "exp_run": exp_id,
                                     "base": {k: [v["status"], v["observed"]] for k, v in ra.items()},
                                     "exp": {k: [v["status"], v["observed"]] for k, v in rb.items()},
                                     "base_outcome": base["outcome"]["label"], "exp_outcome": exp["outcome"]["label"]}
    s.shot("m18-lab-ascent-payload-dark")


def layout(s):
    for w, hgt in ((1024, 700), (820, 900)):
        s.resize(w, hgt)
        for v in ("home", "vehicles", "environments"):
            s.nav(v)
            time.sleep(0.6)
            check(f"Layout {w}x{hgt}: {v} has no horizontal scroll", s.no_hscroll())
        s.nav("home")
        s.shot(f"m18-mission-control-{w}-dark")
    s.resize(1440, 900)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=os.path.join(REPO, "desktop", "target", "release", "vv-studio.exe"))
    ap.add_argument("--domains", default=os.path.join(REPO, "desktop", "target", "release", "domains"))
    ap.add_argument("--environments", default=os.path.join(REPO, "desktop", "environments"), help="packs folder; empty uses the installed ones")
    ap.add_argument("--shots", default=os.path.join(REPO, "docs", "images", "m18-studio"))
    ap.add_argument("--port", type=int, default=9261)
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
    env["VVLAB_LIBRARY"] = tempfile.mkdtemp(prefix="vv-m18-lib-")
    env["VVLAB_CONFIG"] = tempfile.mkdtemp(prefix="vv-m18-cfg-")
    env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"--remote-debugging-port={a.port}"
    proc = launch(exe, env, a.port)
    try:
        with sync_playwright() as pw:
            browser, s = session(pw, a.port, a.shots)
            for part in (home, hangar, environments):
                try:
                    part(s)
                except Exception as e:  # noqa: BLE001
                    check(f"{part.__name__} completed", False, repr(e)[:300])
                    s.shot(f"m18-failure-{part.__name__}")
            try:
                base_id, exp_id = vehicle_experiment(s)
                compare(s, base_id, exp_id)
                watch(s, base_id, exp_id)
            except Exception as e:  # noqa: BLE001
                check("vehicle experiment journey completed", False, repr(e)[:300])
                s.shot("m18-failure-vehicle")
            for part in (ascent, layout):
                try:
                    part(s)
                except Exception as e:  # noqa: BLE001
                    check(f"{part.__name__} completed", False, repr(e)[:300])
                    s.shot(f"m18-failure-{part.__name__}")
            check("No page error or console error", not errors, "; ".join(errors)[:300])
            browser.close()
    finally:
        proc.kill()
        kill_godot()
    with open(os.path.join(a.shots, "m18-numbers.json"), "w", encoding="utf-8") as f:
        json.dump(NUMBERS, f, indent=1, sort_keys=True)
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
