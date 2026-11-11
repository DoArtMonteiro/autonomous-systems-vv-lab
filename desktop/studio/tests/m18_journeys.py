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
import re
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
    chosen = s.js("[...document.querySelectorAll('.at-card.is-current')].map((e) => e.dataset.env)")
    check("Environments: Wallops Island is the one chosen environment", chosen == ["wallops-island"], json.dumps(chosen))
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
    labels = s.js("[...document.querySelectorAll('.run-legend .key-label')].map((e) => ({ text: e.textContent.trim(), cut: e.scrollWidth > e.clientWidth + 1 }))")
    texts = [x["text"] for x in labels]
    check("Compare: the two runs have different labels", len(texts) == 2 and texts[0] != texts[1], json.dumps(texts))
    check("Compare: the labels name the changed parameter and its value, not the whole configuration", len(texts) == 2 and all("thrust" in t.lower() for t in texts) and "0.7" in texts[1] and "0.7" not in texts[0], json.dumps(texts))
    check("Compare: no label is truncated", len(labels) == 2 and not any(x["cut"] for x in labels), json.dumps(labels))
    s.shot("m18-compare-dark")
    s.nav("lab")
    s.wait("document.querySelector('#lab-watch')", 20, "lab result")


def reveal_in_place(s):
    """D8: nothing the viewer has not reached is drawn; the result arrives in a live region that was
    already there, and focus follows the button that asked for it."""
    if s.player()["playing"]:
        s.page.click(".pl-play")
    s.page.evaluate("(() => { const r = document.querySelector('.pl-range'); r.value = String(Number(r.min) + 0.25 * (Number(r.max) - Number(r.min))); r.dispatchEvent(new Event('input', { bubbles: true })); })()")
    time.sleep(0.4)
    p = s.player()
    drawn = s.js("[...document.querySelectorAll('.pl-mark[data-gated]')].map((b) => Number(b.dataset.t))")
    check("Player: the run holds findings later than the playback time", p["findings"] > p["findingsDrawn"], f"{p['findings']} findings, {p['findingsDrawn']} drawn at t = {p['t']:.2f}")
    check("Player: no finding marker later than the playback time is in the page", all(t <= p["t"] + 1e-6 for t in drawn), json.dumps(drawn))
    check("Player: the live region exists and holds no result before it is asked for", s.js("(() => { const l = document.querySelector('.pl-live'); window.__live = l; return !!l && l.getAttribute('aria-live') === 'polite' && !l.querySelector('.pl-result') && !!l.querySelector(\"[data-action='reveal']\"); })()"))
    s.page.focus("[data-action='reveal']")
    s.page.keyboard.press("Enter")
    s.wait("document.querySelector('.pl-result')", 10, "result card")
    check("Player: the result fills the live region that was there, which is not replaced", s.js("document.querySelector('.pl-live') === window.__live && window.__live.contains(document.querySelector('.pl-result'))"))
    check("Player: focus moves to the Result heading when its button goes away", s.js("!!document.activeElement && document.activeElement.id === 'pl-result-h' && document.activeElement.textContent === 'Result'"))
    check("Player: once the result is shown, every finding marker is drawn", s.player()["findingsDrawn"] == s.player()["findings"], json.dumps([s.player()["findings"], s.player()["findingsDrawn"]]))


def watch(s, base_id, exp_id):
    s.page.click("#lab-watch")
    s.wait("(() => { const p = window.__studio.player(); return p && p.experience.startsWith('runs:') && document.querySelector('.pl-hud dl'); })()", 120, "player")
    p = s.player()
    check("Player: plays the baseline and the experiment from their records", p["runs"] == [base_id, exp_id], json.dumps(p["runs"]))
    reveal_in_place(s)
    s.page.click(".pl-views [data-view='engineering']")
    s.wait("(() => { const p = window.__studio.player(); return p && p.view === 'engineering' && p.renderer === 'engineering'; })()", 60, "engineering scene")
    check("Player: the same two records play in the engineering scene", s.player()["runs"] == [base_id, exp_id])
    time.sleep(1.5)
    s.shot("m18-player-engineering-dark")
    s.page.click(".pl-views [data-view='geospatial']")
    s.wait("(() => { const p = window.__studio.player(); return p && p.renderer === 'geospatial'; })()", 90, "geospatial")
    p = s.player()
    check("Player: the geospatial view uses the chosen environment", p["environment"] == "wallops-island", str(p["environment"]))
    time.sleep(6)
    s.shot("m18-player-geospatial-wallops-dark")
    views = s.js("[...document.querySelectorAll('.pl-views [data-view]')].map((b) => [b.dataset.view, b.textContent.trim()])")
    check("Flight console: the player's operations layout is called Flight console", views == [["engineering", "Engineering"], ["geospatial", "Geospatial"], ["control", "Flight console"]], json.dumps(views))
    check("Flight console: the player does not use the name of the home page", "Mission Control" not in s.js("document.querySelector('#view-mission').innerText"))
    player_header(s)
    b = s.js("(() => { const b = document.querySelector(\"[data-action='cinematic']\"); return b ? { disabled: b.disabled, title: b.title } : null; })()")
    NUMBERS["cinematic_button"] = b
    status = s.page.evaluate("() => window.__TAURI__.core.invoke('cinematic_status')")
    NUMBERS["cinematic_status"] = {k: status.get(k) for k in ("installed", "verified", "version")}
    should_open = bool(status.get("installed") and status.get("verified"))
    check("Cinematic: the button is enabled exactly when the module is installed and verified", bool(b) and (not b["disabled"]) == should_open, f"{json.dumps(b)} status {json.dumps(NUMBERS['cinematic_status'])}")
    if should_open and b and not b["disabled"]:
        check("Cinematic: the enabled button says which module version opens this record", str(status.get("version", "")) in b["title"], b["title"])
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
        reason = status.get("reason") or ""
        check("Cinematic: not available here, and the button gives the module's reason", bool(b) and b["disabled"] and bool(reason) and reason in b["title"], f"{json.dumps(b)} reason {reason!r}")


def header_overlaps(s):
    """Bounding boxes of the player header's controls, and the pairs that overlap or leave the window."""
    return s.js("""() => {
        const els = [...document.querySelectorAll('.pl-head button, .pl-head select, .pl-head h1, .pl-head .grade, .pl-head .pl-env-none')].filter((e) => e.offsetParent !== null);
        const box = (e) => { const r = e.getBoundingClientRect(); return { left: r.left, right: r.right, top: r.top, bottom: r.bottom }; };
        const label = (e) => (e.dataset.action || e.dataset.view || e.className || e.tagName).toString().slice(0, 30);
        const boxes = els.map((e) => ({ name: label(e), ...box(e) }));
        const clash = [];
        for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {
            const a = boxes[i], b = boxes[j];
            const w = Math.min(a.right, b.right) - Math.max(a.left, b.left);
            const h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
            if (w > 1 && h > 1) clash.push(a.name + ' x ' + b.name);
        }
        const outside = boxes.filter((b) => b.left < -0.5 || b.right > innerWidth + 0.5).map((b) => b.name);
        const head = document.querySelector('.pl-head').getBoundingClientRect();
        return { count: boxes.length, clash, outside, headHeight: Math.round(head.height), actions: [...document.querySelectorAll('.pl-head-actions .btn')].map((b) => b.textContent.trim()) };
    }""")


def player_header(s):
    """D2: with two runs, the header's controls never overlap and never leave the window."""
    for w, hgt in ((1024, 640), (1440, 900), (1920, 1080)):
        s.resize(w, hgt)
        # The geospatial scene can keep the window busy for a while: give the resize time to land.
        try:
            s.wait(f"innerWidth === {w} && innerHeight === {hgt}", 25, f"window {w}x{hgt}")
        except TimeoutError:
            pass
        time.sleep(0.8)
        got = s.js("[innerWidth, innerHeight]")
        r = header_overlaps(s)
        NUMBERS[f"player_header_{w}x{hgt}"] = r
        check(f"Player header {w}x{hgt}: the window has the size asked for", abs(got[0] - w) <= 1 and abs(got[1] - hgt) <= 1, json.dumps(got))
        check(f"Player header {w}x{hgt}: Analyse, Compare in detail, Cinematic view and Change the conditions are all there", r["actions"] == ["Analyse", "Compare in detail", "Cinematic view", "Change the conditions"], json.dumps(r["actions"]))
        check(f"Player header {w}x{hgt}: no two controls overlap", not r["clash"], "; ".join(r["clash"])[:300])
        check(f"Player header {w}x{hgt}: every control is inside the window", not r["outside"], ", ".join(r["outside"]))
        check(f"Player header {w}x{hgt}: the header stays compact", r["headHeight"] <= 150, f"{r['headHeight']} px")
        check(f"Player header {w}x{hgt}: no horizontal scroll", s.no_hscroll())
    s.resize(1440, 900)


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
    published = sorted(m["id"] for m in exp["metrics"] if m["id"].startswith("requirement_margin."))
    check("Ascent: the record publishes a numeric margin for the single-bound requirements", len(published) >= 6, ", ".join(published))
    check("Ascent: composite requirements publish none", not any(k in " ".join(published) for k in ("R1_separation_window", "R7_phase_sequence", "R8_orbit_insertion")))
    cells = s.js("[...document.querySelectorAll('.lab-table tbody tr')].map((tr) => [tr.cells[0].textContent.trim(), tr.cells[tr.cells.length - 1].textContent.trim()])")
    numeric = [c for c in cells if re.fullmatch(r"[+-]?[\d.e+-]+ (km|kg|Pa|g)", c[1])]
    check("Ascent: the Lab shows a numeric margin change for the requirements that have one", len(numeric) >= 4, json.dumps(cells)[:400])
    with_numbers = {req_map(exp)[k]["label"] for k in req_map(exp) if f"requirement_margin.{k}" in published}
    empty = [c[0] for c in cells if any(c[0].startswith(lbl) for lbl in with_numbers) and c[1] in ("–", "")]
    check("Ascent: no requirement that has numbers shows an empty margin", not empty, ", ".join(empty))
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
