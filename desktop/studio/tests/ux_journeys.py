r"""UX journeys of the installed Studio, written for the independent UX review of 0.18.1: the safety
wording, what changed between two runs (headline, value and margin in every cell), the failing
requirement named in the player, the Cinematic View's run, vehicle, seed and environment, the
narrow-window navigation (More menu, keyboard), the Lab's run bar, numbers and tilt, the
environments page, one colour for Exploratory, text size and the 1024x640 player. It uses a scratch
library; page screenshots go to --shots (they show the Studio window, keep them out of the repository).

    python desktop/studio/tests/ux_journeys.py --exe "%LOCALAPPDATA%\VV Lab Studio\vv-studio.exe" --shots <scratch folder>

Scripted checks of what the screen and the process list show, not observations of people.
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
import m18_journeys as m18  # noqa: E402
from installed_spotcheck import godot_children, module_args, newest_log  # noqa: E402
from m15_journeys import check, errors, results  # noqa: E402
from m16_journeys import launch, session  # noqa: E402

FACTS = {}

SMALL_TEXT_JS = """() => {
  const out = [];
  const view = [...document.querySelectorAll('.view')].find((x) => !x.hidden) || document.body;
  const walker = document.createTreeWalker(view, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = walker.nextNode())) {
    if (!n.textContent.trim()) continue;
    const el = n.parentElement;
    if (!el || el.closest('script, style, svg, canvas, .sr-only')) continue;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    const px = parseFloat(cs.fontSize);
    if (px < 11.95) out.push(`${px}px ${el.className || el.tagName}: ${n.textContent.trim().slice(0, 30)}`);
  }
  return [...new Set(out)].slice(0, 12);
}"""


def small_text(s, where):
    bad = s.js(SMALL_TEXT_JS)
    check(f"Text size: nothing on {where} is below 12 px", not bad, "; ".join(bad[:4]))


def nav_narrow(s):
    """Item 6: at 820 px the secondary workspaces are in a More menu that works from the keyboard."""
    s.resize(820, 900)
    s.nav("home")
    info = s.js("""() => {
      const nav = document.querySelector('.nav');
      const more = document.getElementById('nav-more');
      const vis = (e) => !!e && e.offsetParent !== null;
      return { scroll: nav.scrollWidth > nav.clientWidth + 1, moreVisible: vis(more),
        workHidden: [...document.querySelectorAll('.nav-work')].every((e) => !vis(e)),
        primary: [...document.querySelectorAll('.nav > .nav-btn:not(.nav-work)')].filter(vis).map((e) => e.textContent.trim()),
        cut: [...document.querySelectorAll('.nav > .nav-btn:not(.nav-work)')].filter(vis).some((e) => { const r = e.getBoundingClientRect(); return r.right > innerWidth; }) };
    }""")
    check("Nav 820 px: the primary workspaces fit without a scrollbar", not info["scroll"] and not info["cut"], json.dumps(info))
    check("Nav 820 px: Configure, Analyse, Compare and Records are in a More menu", info["moreVisible"] and info["workHidden"], json.dumps(info))
    s.shot("ux-nav-820-dark")
    s.page.focus("#nav-more")
    s.page.keyboard.press("Enter")
    time.sleep(0.2)
    st = s.js("({ open: !document.getElementById('nav-more-menu').hidden, expanded: document.getElementById('nav-more').getAttribute('aria-expanded'), focus: document.activeElement.textContent.trim() })")
    check("More menu: Enter opens it and focus moves to its first item", st["open"] and st["expanded"] == "true" and st["focus"] == "Configure", json.dumps(st))
    s.shot("ux-nav-more-open-820-dark")
    s.page.keyboard.press("ArrowDown")
    s.page.keyboard.press("End")
    st = s.js("document.activeElement.textContent.trim()")
    check("More menu: the arrow keys and End move through the items", st == "Records", st)
    s.page.keyboard.press("Escape")
    st = s.js("({ open: !document.getElementById('nav-more-menu').hidden, focus: document.activeElement.id })")
    check("More menu: Escape closes it and returns focus to the button", not st["open"] and st["focus"] == "nav-more", json.dumps(st))
    s.page.keyboard.press("Enter")
    s.page.keyboard.press("End")
    s.page.keyboard.press("Enter")
    s.wait("window.__studio.view() === 'library'", 10, "records opened from the More menu")
    check("More menu: choosing Records opens the Library and More is the current item", s.js("document.getElementById('nav-more').getAttribute('aria-current')") == "page")
    s.resize(1440, 900)
    check("Nav 1440 px: the More menu is not shown", not s.js("document.getElementById('nav-more').offsetParent !== null"))


def home_and_hangar(s):
    s.nav("home")
    s.wait("document.querySelector('.hm-paths')", 20, "home")
    t = s.js("document.querySelector('.hm-disclaimer') && document.querySelector('.hm-disclaimer').innerText")
    check("Home: says exploratory models, not real vehicles, nothing validated against flight data", bool(t) and "Exploratory models, not real vehicles; nothing is validated against flight data." in t, str(t)[:100])
    check("Home: no environment text says validated offline", "validated offline" not in s.js("document.querySelector('#view-home').innerText"))
    small_text(s, "Mission Control")
    s.shot("ux-home-dark")
    s.nav("vehicles")
    s.wait("document.querySelector('.hg-card')", 20, "hangar")
    t = s.js("document.querySelector('.hg-disclaimer') && document.querySelector('.hg-disclaimer').innerText")
    check("Hangar: says exploratory models, not real vehicles, nothing validated against flight data", bool(t) and "not real vehicles" in t, str(t)[:100])
    legend = s.js("document.querySelector('.hg-legend').innerText")
    check("Hangar: the legend says recomputed model behaviour, not verified", "recomputed model behaviour" in legend and "verified model behaviour" not in legend, legend[:120])
    labels = s.js("[...new Set([...document.querySelectorAll('.hg-card .hg-actions .btn-primary')].map((b) => b.textContent.trim()))]")
    check("Hangar: one label for the way into the Lab", labels == ["Open in Experiment Lab"], json.dumps(labels))
    small_text(s, "the hangar")
    s.shot("ux-hangar-dark")
    FACTS["explore_chip_hangar"] = s.js("(() => { const e = document.querySelector('.hg-ev-explore'); return e ? getComputedStyle(e).color : null; })()")


def environments_page(s):
    s.nav("environments")
    s.wait("document.querySelectorAll('.at-card').length === 8", 30, "eight environments")
    clip = s.js("[...document.querySelectorAll('.at-sum')].filter((e) => e.scrollHeight > e.clientHeight + 1).length")
    check("Environments: every description is shown in full (nothing clipped)", clip == 0, f"{clip} clipped")
    chips = s.js("[...document.querySelectorAll('.at-card .at-ctx')].map((e) => e.textContent.trim())")
    check("Environments: every card says Terrain is context only", len(chips) == 8 and set(chips) == {"Terrain is context only"}, json.dumps(chips)[:120])
    t0 = time.time()
    try:
        s.wait("!/^(Checking|Still checking)/.test(document.querySelector('.at-cine-status').textContent)", 90, "module status")
    except TimeoutError:
        pass
    text = s.js("document.querySelector('.at-cine-status').textContent")
    check("Environments: the module status resolves (it does not stay at Checking)", not re.match(r"^(Checking|Still checking)", text), f"{time.time() - t0:.1f} s: {text[:90]}")
    check("Environments: no text says validated offline", "validated offline" not in s.js("document.querySelector('#view-environments').innerText"))
    small_text(s, "Environments")
    s.shot("ux-environments-dark")
    s.page.click(".at-card[data-env='wallops-island'] [data-action='use']")
    s.wait("document.querySelector(\".at-card[data-env='wallops-island']\").classList.contains('is-current')", 10, "chosen")


def lab_and_compare(s):
    s.nav("vehicles")
    s.page.click(".hg-card[data-vehicle='heavy-return-stage'] [data-action='design']")
    s.wait("window.__studio.view() === 'lab' && document.querySelector('.lab-base') && window.__studio.lab()", 180, "baseline run")
    st = s.js("""() => { const b = document.getElementById('lab-run'); const w = document.getElementById('lab-run-why'); const e = document.querySelector('.lab-edit');
      const r = b.getBoundingClientRect(); return { disabled: b.disabled, why: w && w.textContent.trim(), describedby: b.getAttribute('aria-describedby'),
        visible: r.bottom <= innerHeight + 1 && r.top >= 0, overflow: getComputedStyle(e).overflowY, maxHeight: getComputedStyle(e).maxHeight }; }""")
    check("Lab: Run experiment is visible from the start and says why it is off", st["disabled"] and st["why"] == "Change one condition first" and st["describedby"] == "lab-run-why" and st["visible"], json.dumps(st))
    check("Lab: the conditions column has no scroll of its own", st["overflow"] == "visible" and st["maxHeight"] == "none", json.dumps(st))
    s.js("document.querySelector('.lab-edit').scrollIntoView()")
    seeds = s.js("[...document.querySelectorAll('.lab-box [data-seeds]')].map((b) => b.disabled)")
    why = s.js("document.getElementById('lab-seeds-why') && document.getElementById('lab-seeds-why').textContent")
    check("Lab: the seed buttons are off and say Run an experiment first", seeds and all(seeds) and why == "Run an experiment first.", f"{seeds} {why}")
    small_text(s, "the Lab")
    s.shot("ux-lab-baseline-dark")
    base = m18.lab(s)["base"]
    m18.set_param(s, "vehicle_thrust_scale", 0.7)
    st = s.js("({ disabled: document.getElementById('lab-run').disabled, why: document.getElementById('lab-run-why').textContent })")
    check("Lab: after one change the button is on and the bar counts the change", not st["disabled"] and st["why"].startswith("1 change"), json.dumps(st))
    exp = m18.run_and_wait(s)
    rows = s.js("""() => [...document.querySelectorAll('.lab-table tbody tr')].map((tr) => ({ req: tr.dataset.req, text: tr.innerText.replace(/\\s+/g, ' ').trim(), failA: !!tr.cells[2] && tr.cells[2].className.includes('st-fail'), failB: !!tr.cells[3] && tr.cells[3].className.includes('st-fail') }))""")
    head = s.js("document.getElementById('lab-headline') && document.getElementById('lab-headline').innerText")
    check("Lab: the headline names the largest change with its numbers and limit", bool(head) and "Vertical speed at contact" in head and "→" in head and "60.08" in head and "limit <= 3" in head, str(head))
    r1 = next((r for r in rows if r["req"] == "R1_vertical_speed"), None)
    check("Lab: a cell shows the observed value, the margin and 4 significant figures", bool(r1) and "1.658" in r1["text"] and "60.08" in r1["text"] and "margin" in r1["text"] and "1.654537" not in r1["text"], r1["text"] if r1 else "no row")
    flags = [r["failA"] or r["failB"] for r in rows]
    check("Lab: failed rows come first", flags == sorted(flags, reverse=True) and flags[0], json.dumps(flags))
    tilt = next((r for r in rows if r["req"] == "R3_tilt"), None)
    check("Lab: tilt is shown in degrees", bool(tilt) and "°" in tilt["text"] and " cos" not in tilt["text"], tilt["text"] if tilt else "no tilt row")
    s.js("document.querySelector('.lab-result').scrollIntoView()")
    s.shot("ux-lab-result-dark")
    ids = (base, exp)
    # Compare
    s.page.click(".lab-result .btn:has-text('Compare signals in detail')")
    s.wait("window.__studio.view() === 'compare' && document.querySelector('.matrix')", 30, "compare")
    time.sleep(2)
    legend = s.js("[...document.querySelectorAll('.run-key .key-verdicts')].map((e) => e.innerText.replace(/\\s+/g, ' ').trim())")
    check("Compare: no run is labelled with a bare safe", all("No safety rule broken (" in x and not re.search(r"\bsafe\b", x.replace("No safety rule broken", "")) for x in legend), json.dumps(legend))
    cells = s.js("[...document.querySelectorAll('.matrix tbody tr[data-row=\"Safety rules\"] td')].map((e) => e.innerText.replace(/\\s+/g, ' ').trim())")
    check("Compare: the Safety rules row says how many were checked", len(cells) == 2 and all(c.endswith("No safety rule broken (5 checked)") or "No safety rule broken (" in c for c in cells), json.dumps(cells))
    note = s.js("document.querySelector('.cmp-safety-note') && document.querySelector('.cmp-safety-note').innerText")
    check("Compare: a note says contact speed is a mission requirement", bool(note) and "mission requirements" in note and "hard landing" in note, str(note)[:100])
    hl = s.js("document.querySelector('.cmp-headline') && document.querySelector('.cmp-headline').innerText")
    check("Compare: the headline reads Vertical speed at contact 1.658 -> 60.08 m/s (limit 3)", bool(hl) and "Vertical speed at contact" in hl and "1.658" in hl and "60.08" in hl and "limit <= 3" in hl, str(hl))
    row = s.js("(() => { const r = document.querySelector(\".matrix tbody tr[data-row='R1_vertical_speed']\"); return r ? [...r.cells].map((c) => c.innerText.replace(/\\s+/g, ' ').trim()) : null; })()")
    check("Compare: each cell shows the observed value and the margin, not only Pass or Fail", bool(row) and len(row) == 3 and all("margin" in c and re.search(r"\d", c) for c in row[1:]) and "limit" in row[0], json.dumps(row))
    summ = s.js("document.querySelector('.cmp-matrix p[aria-live]').textContent")
    check("Compare: the count of differing rows is grammatical", bool(re.match(r"^(1 row differs|\d+ rows differ) between the runs", summ)), summ)
    small_text(s, "the comparison")
    s.shot("ux-compare-dark")
    FACTS["compare_headline"] = hl
    return ids


def player_and_cinematic(s, ids, shots):
    s.nav("lab")
    s.wait("document.querySelector('#lab-watch')", 20, "lab result")
    s.page.click("#lab-watch")
    s.wait("(() => { const p = window.__studio.player(); return p && p.experience.startsWith('runs:') && document.querySelector('.pl-hud dl'); })()", 120, "player")
    s.page.click(".pl-views [data-view='engineering']")
    s.wait("(() => { const p = window.__studio.player(); return p && p.view === 'engineering'; })()", 60, "engineering")
    chips = s.js("[...document.querySelectorAll('.pl-cases .pl-case')].map((e) => e.textContent.trim())")
    check("Player: the run chips say Reference case or Exploratory for each held run", bool(chips), json.dumps(chips))
    s.page.click("[data-action='reveal']")
    s.wait("document.querySelector('.pl-result')", 10, "result")
    time.sleep(0.5)
    chip0 = s.js("document.querySelector('.pl-phase-name') && document.querySelector('.pl-phase-name').textContent")
    check("Player: the baseline's end chip names the failing requirement with its value and limit", bool(chip0) and chip0.startswith("Not met: Horizontal speed at contact") and "limit <= 1 m/s" in chip0 and "impact not modelled" in chip0 and not chip0.startswith("Contact at"), str(chip0))
    s.page.click(".pl-run[data-run='1']")
    time.sleep(0.8)
    s.page.keyboard.press("End")
    time.sleep(0.5)
    chip1 = s.js("document.querySelector('.pl-phase-name') && document.querySelector('.pl-phase-name').textContent")
    check("Player: the experiment's end chip names Vertical speed at contact 60.08 m/s, limit 3", bool(chip1) and "Vertical speed at contact 60.08" in chip1 and "limit <= 3 m/s" in chip1 and "impact not modelled" in chip1, str(chip1))
    s.page.click(".pl-run[data-run='0']")
    time.sleep(0.5)
    safety = s.js("[...document.querySelectorAll('.pl-run-result .vchip')].map((e) => e.innerText.replace(/\\s+/g, ' ').trim())")
    check("Player: the result chips say No safety rule broken (5 checked)", any("No safety rule broken (5 checked)" in x for x in safety), json.dumps(safety))
    p = s.player()
    check("Player: the player holds the environment chosen in Environments", p["environment"] == "wallops-island", str(p["environment"]))
    s.shot("ux-player-end-dark")
    small_text(s, "the player")
    # Cinematic View: choose the run, check what the module was given.
    chooser = s.js("(() => { const c = document.querySelector('.pl-cin-run'); return c ? [...c.options].map((o) => o.textContent.trim()) : null; })()")
    check("Cinematic: with two runs held the person chooses which one opens", bool(chooser) and len(chooser) == 2 and chooser[0] == "Baseline", json.dumps(chooser))
    return chooser


def cinematic_checks(s, studio_pid, ids, shots):
    base, exp = ids
    out = {}
    for index, (name, rid) in enumerate((("experiment", exp), ("baseline", base))):
        s.page.select_option(".pl-cin-run", str(1 if name == "experiment" else 0))
        s.wait("document.querySelector('.pl-head [data-action=\"cinematic\"]:not([aria-disabled=\"true\"])')", 30, "cinematic button")
        t0 = time.time()
        s.page.click(".pl-head [data-action='cinematic']")
        kids = []
        while time.time() - t0 < 40 and not kids:
            kids = godot_children(studio_pid)
            time.sleep(0.25)
        check(f"Cinematic ({name}): the module started", bool(kids))
        if not kids:
            continue
        cmd = kids[0]["cmd"] or ""
        args = module_args(cmd)
        get = lambda k: args[args.index(k) + 1] if k in args else None  # noqa: E731
        run_dir = get("--run") or ""
        check(f"Cinematic ({name}): it opens the run that was chosen", os.path.basename(run_dir.rstrip("\\/")) == rid, os.path.basename(run_dir.rstrip("\\/")))
        check(f"Cinematic ({name}): it uses the player's environment (Wallops Island)", os.path.basename((get("--env") or "").rstrip("\\/")) == "wallops-island", os.path.basename((get("--env") or "").rstrip("\\/")))
        check(f"Cinematic ({name}): it is given the run label, the vehicle, the seed and the exploratory flag", (get("--run-label") == "Baseline") if name == "baseline" else bool(get("--run-label") and "Engine thrust" in get("--run-label")), json.dumps({k: get(k) for k in ("--run-label", "--vehicle", "--seed")}))
        check(f"Cinematic ({name}): the vehicle is named and the seed is the run's", "heavy return stage" in (get("--vehicle") or "").lower() and get("--seed") == "5000", json.dumps({k: get(k) for k in ("--vehicle", "--seed")}))
        check(f"Cinematic ({name}): the exploratory flag is passed", "--exploratory" in args)
        out[name] = {"label": get("--run-label"), "vehicle": get("--vehicle"), "seed": get("--seed"), "env": os.path.basename((get("--env") or "").rstrip("\\/"))}
        if name == "experiment":
            first = None
            text = ""
            while time.time() - t0 < 90:
                log = newest_log()
                text = open(log, encoding="utf-8", errors="replace").read() if log and os.path.getmtime(log) >= t0 - 1 else ""
                if "FIRST_FRAME" in text:
                    first = time.time() - t0
                    break
                time.sleep(0.5)
            check("Cinematic (experiment): the first frame was drawn and Direct3D 12 is the renderer", first is not None and "D3D12" in text and "ERROR" not in text, f"{first and round(first, 1)} s")
            for k in godot_children(studio_pid):
                subprocess.run(["taskkill", "/F", "/PID", str(k["pid"])], capture_output=True)
            time.sleep(1.5)
            exe = cmd.split('"')[1] if cmd.startswith('"') else cmd.split()[0]
            console = os.path.join(os.path.dirname(exe), "Godot_v4.7.2-stable_win64_console.exe")
            shot = os.path.join(shots, "cinematic-hud-experiment.png")
            rec = json.load(open(os.path.join(run_dir, "record.json"), encoding="utf-8"))
            span = max((tb[-1] for tb in rec["timebases"].values() if tb), default=10.0)
            r = subprocess.run([console] + args + ["--t", f"{0.55 * span:.1f}", "--shot", shot], capture_output=True, text=True, timeout=240)
            check("Cinematic (experiment): the module's own --shot wrote the picture with those arguments", os.path.isfile(shot) and os.path.getsize(shot) > 50_000 and "SHOT" in r.stdout, f"{os.path.getsize(shot) if os.path.isfile(shot) else 0} bytes")
        else:
            for k in godot_children(studio_pid):
                subprocess.run(["taskkill", "/F", "/PID", str(k["pid"])], capture_output=True)
            time.sleep(1.5)
    FACTS["cinematic_args"] = out


def geo_1024(s):
    """Item 10: at 1024x640 the attribution and the camera bar do not collide."""
    s.resize(1024, 640)
    s.page.click(".pl-views [data-view='geospatial']")
    s.wait("window.__studio.player().renderer === 'geospatial'", 90, "geospatial")
    time.sleep(3)
    r = s.js("""() => {
      const box = (e) => { const r = e.getBoundingClientRect(); return { l: r.left, r: r.right, t: r.top, b: r.bottom }; };
      const a = [...document.querySelectorAll('.si-credit, .si-btn, .pl-scene-note.is-geo button')].filter((e) => e.offsetParent !== null).map((e) => ({ n: e.className, ...box(e) }));
      const c = [...document.querySelectorAll('.pl-cams, .pl-runs')].filter((e) => e.offsetParent !== null).map((e) => ({ n: e.className, ...box(e) }));
      const clash = [];
      for (const x of a) for (const y of c) { const w = Math.min(x.r, y.r) - Math.max(x.l, y.l); const h = Math.min(x.b, y.b) - Math.max(x.t, y.t); if (w > 1 && h > 1) clash.push(x.n + ' x ' + y.n); }
      return { clash, credits: a.length, bars: c.length };
    }""")
    check("Player 1024x640: the attribution does not overlap the camera bar", not r["clash"] and r["credits"] > 0, json.dumps(r))
    s.shot("ux-player-geo-1024x640-dark")
    small_text(s, "the 1024x640 player")
    s.resize(1440, 900)


def lab_ascent(s):
    m18.ascent(s)
    labels = s.js("[...document.querySelectorAll('.lab-table tbody tr td:first-child')].map((e) => e.textContent.trim())")
    dup = sorted({x for x in labels if labels.count(x) > 1})
    check("Lab (ascent): no two requirement rows have the same name (stage names added)", not dup and any("Upper stage" in x for x in labels) and any("Stack" in x for x in labels), json.dumps(dup) or f"{len(labels)} rows")
    s.shot("ux-lab-ascent-dark")


def colours(s):
    s.nav("lab")
    lab = s.js("(() => { const e = document.querySelector('.lab-tag-exp'); return e ? getComputedStyle(e).color : null; })()")
    FACTS["explore_chip_lab"] = lab
    check("Exploratory chip: the Lab and the hangar use the same colour", bool(lab) and lab == FACTS.get("explore_chip_hangar"), f"{lab} vs {FACTS.get('explore_chip_hangar')}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", required=True)
    ap.add_argument("--shots", required=True)
    ap.add_argument("--port", type=int, default=9267)
    ap.add_argument("--no-cinematic", action="store_true")
    ap.add_argument("--domains", default="", help="domain folder of a build-folder run; empty uses the installed ones")
    ap.add_argument("--environments", default="", help="packs folder of a build-folder run; empty uses the installed ones")
    a = ap.parse_args()
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
    env["VVLAB_LIBRARY"] = tempfile.mkdtemp(prefix="vv-ux-lib-")
    env["VVLAB_CONFIG"] = tempfile.mkdtemp(prefix="vv-ux-cfg-")
    env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"--remote-debugging-port={a.port}"
    proc = launch(os.path.abspath(os.path.expandvars(a.exe)), env, a.port)
    try:
        with sync_playwright() as pw:
            browser, s = session(pw, a.port, a.shots)
            ids = None
            for name, fn in (("nav", nav_narrow), ("home", home_and_hangar), ("environments", environments_page)):
                try:
                    fn(s)
                except Exception as e:  # noqa: BLE001
                    check(f"{name} completed", False, repr(e)[:300])
            try:
                ids = lab_and_compare(s)
                player_and_cinematic(s, ids, a.shots)
                if not a.no_cinematic:
                    cinematic_checks(s, proc.pid, ids, a.shots)
                geo_1024(s)
            except Exception as e:  # noqa: BLE001
                check("lab, compare and player completed", False, repr(e)[:400])
            for name, fn in (("ascent", lab_ascent), ("colours", colours)):
                try:
                    fn(s)
                except Exception as e:  # noqa: BLE001
                    check(f"{name} completed", False, repr(e)[:300])
            check("No page error or console error", not errors, "; ".join(errors)[:300])
            browser.close()
    finally:
        for k in godot_children(proc.pid):
            subprocess.run(["taskkill", "/F", "/PID", str(k["pid"])], capture_output=True)
        proc.kill()
    with open(os.path.join(a.shots, "ux-facts.json"), "w", encoding="utf-8") as f:
        json.dump(FACTS, f, indent=1, sort_keys=True)
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
