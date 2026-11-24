r"""Surfaces of the M19.1 honesty branch that earlier captures never showed, from a development Studio.

    python docs/evidence/m19/honesty/journeys-rerun/surfaces.py --exe <dev vv-studio.exe> --out <folder>

Started through desktop/studio/tests/studio_launch.py: scratch library, configuration, modules and WebView2 profile,
and a development identifier, so nothing of the installed application is read or written. The domain hosts, the
engine, the claims and the environment packs are the ones staged in this worktree (desktop/build.ps1).
Surfaces: the Flight console held rows, the Experiment Lab comparison table with its safety cells, the Runs page,
the Discover list and tiles after an investigation, and the keyboard focus ring of a run pill.
These are scripted observations of what the screen shows, not an assessment by people.
"""

import argparse
import json
import os
import sys
import tempfile
import time

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "desktop", "studio", "tests"))
import studio_launch  # noqa: E402
from m15_journeys import S, errors  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""), flush=True)


def open_mission(s, exp_id):
    s.page.evaluate("(id) => document.dispatchEvent(new CustomEvent('vv-open-mission', { detail: id }))", exp_id)
    s.wait(f"(() => {{ const p = window.__studio.player(); return p && p.experience === '{exp_id}' && (document.querySelector('.pl-head') || document.querySelector('.mc')); }})()", 90, f"player {exp_id}")
    if s.js("!!document.querySelector('.mc')"):
        s.page.click(".mc-back")
        s.wait("document.querySelector('.pl-head')", 20, "player head")
    time.sleep(1.0)


def pick_run(s, index):
    s.page.click(f".pl-runs .pl-run:nth-child({index + 1})")
    time.sleep(0.6)


def to_end(s):
    s.page.click(".pl-reveal")
    s.wait("document.querySelector('.pl-result')", 20, "result")
    time.sleep(1.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--port", type=int, default=9521)
    studio_launch.add_arguments(ap)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    stage = os.path.join(REPO, "desktop", "target", "release")
    env = dict(os.environ)
    for k in ("VVLAB_DOMAINS", "VVLAB_EXTRA_DOMAINS", "VVLAB_EXEC", "VVLAB_CLAIMS", "VVLAB_ENVIRONMENTS", "VVLAB_MODULES"):
        env.pop(k, None)
    env["VVLAB_DOMAINS"] = os.path.join(stage, "domains")
    env["VVLAB_EXEC"] = os.path.join(stage, "engines", "vv-exec.exe")
    env["VVLAB_CLAIMS"] = os.path.join(stage, "discovery", "claims")
    env["VVLAB_ENVIRONMENTS"] = os.path.join(REPO, "desktop", "environments")
    env["VVLAB_LIBRARY"] = tempfile.mkdtemp(prefix="vv-surf-lib-")
    env["VVLAB_CONFIG"] = tempfile.mkdtemp(prefix="vv-surf-cfg-")
    env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"--remote-debugging-port={a.port}"
    exe = os.path.abspath(a.exe)
    proc = studio_launch.launch(exe, env, a.port, allow_release=a.owner_allow_release_exe)
    facts = {"exe": os.path.basename(exe)}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{a.port}")
            page = browser.contexts[0].pages[0]
            page.on("pageerror", lambda e: errors.append(str(e)))
            s = S(page, a.out)
            s.wait("window.__TAURI__ && window.__studio", 30, "studio script")
            page.evaluate("() => window.__TAURI__.core.invoke('set_prefs', { prefs: { theme: 'dark' } })")
            page.reload()
            s.wait("window.__studio && document.getElementById('startup').hidden", 90, "platform ready")
            s.resize(1440, 900)

            # 1. Flight console: held safety rows.
            open_mission(s, "late-gnss")
            pick_run(s, 0)
            s.page.click(".pl-views [data-view='control']")
            s.wait("document.querySelector('.mc')", 30, "flight console")
            s.js("(() => { const r = document.querySelector('.pl-range, .mc-range, input[type=range]'); if (r) { r.value = r.max; r.dispatchEvent(new Event('input', { bubbles: true })); } })()")
            time.sleep(1.5)
            facts["flight_console_rows"] = s.js("[...document.querySelectorAll('.mc-v')].map((li) => ({ cls: li.className, state: li.dataset.state, text: li.innerText.replace(/\\s+/g, ' ').trim(), title: li.title }))")
            s.shot("surf-1-flight-console-held-1440x900")
            held = [r for r in facts["flight_console_rows"] if "v-held" in r["cls"]]
            check("Flight console: the safety rules not broken are held (neutral)", bool(held) and all(r["state"] == "held" for r in held), json.dumps(facts["flight_console_rows"])[:300])
            check("Flight console: no safety row is drawn as met (green)", not [r for r in facts["flight_console_rows"] if "v-ok" in r["cls"] and "afety" in r["text"]])
            s.resize(1024, 640)
            time.sleep(0.8)
            s.shot("surf-1-flight-console-held-1024x640")
            s.resize(1440, 900)

            # 2. Experiment Lab: comparison table after changing the controller.
            open_mission(s, "lying-altimeter")
            pick_run(s, 0)
            s.page.click(".pl-head [data-action='configure']")
            s.wait("window.__studio.view() === 'lab'", 60, "lab")
            time.sleep(1.5)
            before = (s.js("window.__studio.lab()") or {}).get("exp")
            s.page.select_option("#lab-ctl", "robust")
            time.sleep(0.4)
            s.page.click("#lab-run")
            s.wait(f"(() => {{ const l = window.__studio.lab(); return l && !l.busy && l.exp && l.exp !== {json.dumps(before)}; }})()", 180, "experiment run")
            time.sleep(1.0)
            facts["lab_table_cells"] = s.js("[...document.querySelectorAll('.lab-table tbody tr')].map((tr) => ({ req: tr.dataset.req || tr.innerText.slice(0, 40).replace(/\\s+/g, ' '), cells: [...tr.querySelectorAll('td[class*=st-], .lab-comp-line')].map((c) => ({ cls: c.className, text: c.innerText.replace(/\\s+/g, ' ').trim().slice(0, 50) })) }))")
            s.js("document.querySelector('.lab-table').scrollIntoView({ block: 'center' })")
            time.sleep(0.5)
            s.shot("surf-2-lab-comparison-table-1440x900")
            held_cells = [c for r in facts["lab_table_cells"] for c in r["cells"] if "st-held" in c["cls"]]
            green_safety = [r for r in facts["lab_table_cells"] if "afety" in r["req"] and any("st-pass" in c["cls"] for c in r["cells"])]
            check("Lab table: the invariant cells are held (neutral)", bool(held_cells), json.dumps(facts["lab_table_cells"])[:300])
            check("Lab table: no safety row is drawn as a requirement that passed", not green_safety)

            # 3. The Runs page (library).
            s.nav("library")
            time.sleep(1.2)
            facts["runs_page_cells"] = s.js("[...document.querySelectorAll('#view-library td .cell')].map((c) => ({ text: c.innerText.replace(/\\s+/g, ' ').trim(), cls: c.className }))")
            facts["runs_page_rows"] = s.js("document.querySelectorAll('#view-library tbody tr').length")
            s.shot("surf-3-runs-page-1440x900")
            check("Runs page: the runs of this session are listed", facts["runs_page_rows"] >= 3, str(facts["runs_page_rows"]))
            check("Runs page: 'None broken' is neutral, never green", all("v-pass" not in c["cls"] for c in facts["runs_page_cells"] if c["text"] == "None broken") and any(c["text"] == "None broken" for c in facts["runs_page_cells"]))
            s.resize(1024, 640)
            time.sleep(0.8)
            s.shot("surf-3-runs-page-1024x640")
            check("Runs page: no horizontal scroll at 1024x640", s.no_hscroll())
            s.resize(1440, 900)

            # 4. Discover: list and tiles after an investigation (the shipped corridor claim, recomputed in the app).
            s.nav("discover")
            s.wait("document.querySelectorAll('#view-discover .dl-item').length >= 2", 60, "claim list")
            s.page.click("#view-discover .dl-list[aria-label='Claims'] .dl-item:has-text('Corridor safety under GPS noise')")
            s.wait("document.querySelector('#view-discover .dl-cta')", 60, "claim view")
            s.page.click("#view-discover .dl-cta")
            s.wait("document.querySelector('#view-discover .dl-tiles') && /Recomputed|A check failed/.test(document.querySelector('#view-discover .dl-tiles').innerText)", 300, "investigation")
            time.sleep(1.0)
            facts["discover_tiles"] = s.js("document.querySelector('#view-discover .dl-tiles').innerText.replace(/\\s+/g, ' ').trim()")
            facts["discover_chips"] = s.js("[...document.querySelectorAll('#view-discover .dl-chip')].map((c) => ({ cls: c.className, text: c.innerText.replace(/\\s+/g, ' ').trim() }))")
            facts["discover_list"] = s.js("[...document.querySelectorAll('#view-discover .dl-list[aria-label=Investigations] .dl-item')].map((c) => c.innerText.replace(/\\s+/g, ' ').trim())")
            s.shot("surf-4-discover-investigation-1440x900")
            check("Discover: the Investigations list has the package", bool(facts["discover_list"]), json.dumps(facts["discover_list"]))
            check("Discover: evidence integrity is a neutral (held) chip, not a verdict on the claim", any("held" in c["cls"] and "Evidence integrity" in c["text"] for c in facts["discover_chips"]), json.dumps(facts["discover_chips"])[:300])
            check("Discover: the tiles say the evidence was recomputed", "Recomputed, every check passed" in facts["discover_tiles"], facts["discover_tiles"][:200])

            # 5. Keyboard focus ring of a run pill.
            s.resize(1024, 640)
            open_mission(s, "corridor")
            s.page.focus(".pl-views [data-view='geospatial'], .pl-views button")
            for _ in range(12):
                page.keyboard.press("Tab")
                if s.js("document.activeElement && document.activeElement.classList.contains('pl-run')"):
                    break
            facts["pill_focus"] = s.js("""(() => { const e = document.activeElement; if (!e || !e.classList.contains('pl-run')) return null;
              const c = getComputedStyle(e); const r = e.getBoundingClientRect(); const row = e.parentElement.getBoundingClientRect();
              return { text: e.innerText.replace(/\\s+/g, ' ').trim().slice(0, 60), outline: c.outlineStyle + ' ' + c.outlineWidth + ' ' + c.outlineColor, offset: c.outlineOffset, boxShadow: c.boxShadow,
                focusVisible: e.matches(':focus-visible'), insideRow: r.left >= row.left - 0.5 && r.right <= row.right + 0.5 && r.top >= row.top - 0.5 }; })()""")
            s.shot("surf-5-pill-focus-ring-1024x640")
            pf = facts["pill_focus"]
            check("Pill focus: a run pill takes keyboard focus", pf is not None)
            check("Pill focus: :focus-visible matches and the ring is drawn", bool(pf) and pf["focusVisible"] and (("none" not in pf["outline"].split(" ")[0]) or pf["boxShadow"] != "none"), json.dumps(pf))
            check("Pill focus: the ring is not clipped by the pill row", bool(pf) and pf["insideRow"], json.dumps(pf))
            s.resize(1440, 900)

            facts["errors"] = [e for e in errors if "Failed to load resource" not in e]
            check("No page error or console error", not facts["errors"], "; ".join(facts["errors"])[:200])
            browser.close()
    finally:
        studio_launch.stop(proc)
    with open(os.path.join(a.out, "surfaces-facts.json"), "w", encoding="utf-8") as f:
        json.dump(facts, f, indent=1, sort_keys=True)
        f.write("\n")
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed; output in {a.out}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
