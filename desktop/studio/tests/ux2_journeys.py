r"""Second UX journeys of the installed Studio, written for the second independent review of 0.18.1:
the run names and one label per run, the Runs page, what Analyse says without cutting it, the Lab
result table (no number broken, value and margin on one line), the player at 1024x640 and 820 px (objective
folded, verdicts on the run pills once the result is shown), the Flight console end sentence and camera
row, the Home statistics block, an unsafe run and a thrust consistency check read from a record. It
uses a scratch library; page screenshots (dark and light) go to --shots and show the Studio window, so
they stay out of the repository.

    python desktop/studio/tests/ux2_journeys.py --exe "%LOCALAPPDATA%\VV Lab Studio\vv-studio.exe" --shots <scratch folder>

Scripted checks of what the screen shows, not observations of people.
"""

import argparse
import json
import os
import re
import sys
import tempfile
import time

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import m18_journeys as m18  # noqa: E402
import ux_journeys as ux1  # noqa: E402
from m15_journeys import check, errors, results  # noqa: E402
from m16_journeys import launch, open_mission, session  # noqa: E402

FACTS = {}


def home_stats(s):
    s.nav("home")
    s.wait("document.querySelector('.hm-stats')", 20, "home")
    for w, h in ((1440, 900), (1024, 640), (820, 900)):
        s.resize(w, h)
        time.sleep(0.4)
        r = s.js("""() => {
          const cells = [...document.querySelectorAll('.hm-stats > div')];
          const box = (e) => e.getBoundingClientRect();
          const clash = [];
          for (let i = 0; i < cells.length; i++) for (let j = i + 1; j < cells.length; j++) {
            const a = box(cells[i]); const b = box(cells[j]);
            if (Math.min(a.right, b.right) - Math.max(a.left, b.left) > 1 && Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 1) clash.push(i + ' x ' + j);
          }
          const cut = [...document.querySelectorAll('.hm-stats dt')].filter((e) => e.scrollWidth > e.clientWidth + 1).length;
          return { n: cells.length, clash, cut };
        }""")
        check(f"Home {w}x{h}: the four statistics do not overlap and no label is cut", r["n"] == 4 and not r["clash"] and r["cut"] == 0, json.dumps(r))
    s.resize(1440, 900)
    open_btn = s.js("[...document.querySelectorAll('.hm-path .btn-primary')].map((b) => b.textContent.trim())")
    check("Home: the missions card says Open the missions", "Open the missions" in open_btn, json.dumps(open_btn))
    nav = s.js("document.querySelector(\".nav-btn[data-view='library']\").textContent.trim()")
    check("Nav: the stored runs are Runs, in the nav, the More menu and the page title", nav == "Runs" and s.js("document.querySelector('.nav-more-item[data-view=\"library\"]').textContent.trim()") == "Runs", nav)


def lab_compare_runs(s):
    s.nav("vehicles")
    s.page.click(".hg-card[data-vehicle='heavy-return-stage'] [data-action='design']")
    s.wait("window.__studio.view() === 'lab' && document.querySelector('.lab-base') && window.__studio.lab()", 180, "baseline run")
    base = m18.lab(s)["base"]
    rec = m18.record(s, base)
    ch = {c["id"]: c["values"] for c in rec["channels"]}
    ratios = [t / a for t, a in zip(ch["thrust_n"], ch["act_throttle"]) if t and a and a > 0.3]
    spread = (max(ratios) - min(ratios)) / max(ratios)
    FACTS["thrust_over_applied_throttle_kN"] = round(ratios[0] / 1000, 3)
    FACTS["thrust_ratio_relative_spread"] = spread
    check("Thrust: thrust divided by applied throttle is the same at every sample of the record (the record's own maximum thrust, not two instants)", spread < 1e-6, f"{ratios[0] / 1000:.3f} kN, spread {spread:.2e}")
    m18.set_param(s, "vehicle_thrust_scale", 0.7)
    exp = m18.run_and_wait(s)
    # Lab result table
    r = s.js("""() => {
      const col = document.querySelector('.lab-result').getBoundingClientRect().width;
      const cells = [...document.querySelectorAll('.lab-table .lab-cell-v, .lab-table .lab-cell-m')];
      const tall = cells.filter((e) => e.getBoundingClientRect().height > 22).length;
      return { col: Math.round(col), cells: cells.length, tall };
    }""")
    check("Lab: the result column is wide and every value and margin sits on one line", r["col"] >= 460 and r["cells"] > 10 and r["tall"] == 0, json.dumps(r))
    s.js("document.querySelector('.lab-result').scrollIntoView()")
    s.shot("ux2-lab-result-dark")
    # Compare with the Lab's labels
    s.page.click(".lab-result .btn:has-text('Compare signals in detail')")
    s.wait("window.__studio.view() === 'compare' && document.querySelector('.matrix')", 30, "compare")
    time.sleep(2)
    heads = s.js("[...document.querySelectorAll('.matrix thead th')].slice(1).map((e) => e.textContent.trim())")
    check("Compare: the column heads are the run labels, not Run 1 and Run 2", len(heads) == 2 and heads[0] == "Baseline" and "thrust" in heads[1].lower(), json.dumps(heads))
    cards = s.js("[...document.querySelectorAll('.run-key .key-count')].map((e) => e.textContent.trim())")
    check("Compare: each run card says how many requirements failed", cards == ["1 of 6 requirements failed", "2 of 6 requirements failed"], json.dumps(cards))
    first = s.js("(() => { const rows = [...document.querySelectorAll('.matrix tbody tr')]; const sep = rows.findIndex((r) => r.classList.contains('sep') && /Verdict changes/.test(r.textContent)); return sep < 0 ? null : { sep, next: rows[sep + 1] && rows[sep + 1].dataset.row, count: rows.filter((r, i) => i > sep && !r.classList.contains('sep')).slice(0, 1).length }; })()")
    check("Compare: the rows whose verdict changes come first, in their own group", bool(first) and first["next"] == "R1_vertical_speed", json.dumps(first))
    s.shot("ux2-compare-dark")
    # Runs page
    s.nav("library")
    s.wait("document.querySelectorAll('tbody tr[data-run]').length >= 2", 30, "runs rows")
    title = s.js("document.querySelector('#view-library h1').textContent.trim()")
    heads = s.js("[...document.querySelectorAll('#view-library thead th')].map((e) => e.textContent.trim())")
    failed = s.js("[...document.querySelectorAll('tbody tr[data-run] td.failed')].map((e) => e.textContent.trim())")
    check("Runs page: the title is Runs and the column is Safety rules", title == "Runs" and "Safety rules" in heads, f"{title} {heads}")
    check("Runs page: the Failed column uses plain names, not ids", bool(failed) and all(not re.search(r"R\d_", x) for x in failed) and any("Horizontal speed at contact" in x for x in failed), json.dumps(failed))
    s.shot("ux2-runs-dark")
    # Analyse
    s.page.dblclick(f"tbody tr[data-run='{exp}']")
    s.wait("window.__studio.view() === 'run' && document.querySelector('.verdict')", 30, "analyse")
    time.sleep(1.0)
    sent = s.js("document.querySelector(\".verdict[aria-label='Mission outcome'] .verdict-x\").innerText.replace(/\\s+/g, ' ')")
    check("Analyse: the outcome sentence names the failed requirements in plain words", "2 mission requirements failed: Vertical speed at contact, Horizontal speed at contact." in sent and not re.search(r"R\d_", sent), sent[:200])
    cut = s.js("[...document.querySelectorAll('.verdict-x, .validity-strip .vtext, .verdict-v span')].filter((e) => e.scrollWidth > e.clientWidth + 1 || e.scrollHeight > e.clientHeight + 2).length")
    check("Analyse: the outcome, the safety line and the model validity wrap and are not cut", cut == 0, f"{cut} cut")
    tilt = s.js("(() => { const r = document.querySelector(\".req[data-id='S1_tilt_envelope'] .req-eo\"); return r ? r.innerText.replace(/\\s+/g, ' ') : null; })()")
    check("Analyse: the tilt rows are in degrees (derived from the stored cosine)", bool(tilt) and "°" in tilt and " cos" not in tilt, str(tilt))
    s.shot("ux2-analyse-dark")
    return base, exp


def player_checks(s, ids):
    s.nav("lab")
    s.wait("document.querySelector('#lab-watch')", 20, "lab result")
    s.page.click("#lab-watch")
    s.wait("(() => { const p = window.__studio.player(); return p && p.experience.startsWith('runs:') && document.querySelector('.pl-hud dl'); })()", 120, "player")
    s.page.click(".pl-views [data-view='engineering']")
    s.wait("(() => { const p = window.__studio.player(); return p && p.view === 'engineering'; })()", 60, "engineering")
    pills = s.js("[...document.querySelectorAll('.pl-run-v')].map((e) => e.textContent.trim())")
    check("Player: before the result is shown the run pills carry no verdict", all(x == "" for x in pills), json.dumps(pills))
    labels = s.js("({ toggle: document.querySelector('[data-action=analysis]').textContent.trim(), cine: document.querySelector('[data-action=cinematic]').textContent.trim(), run: (document.querySelector('.pl-cin-run-box') || {}).innerText })")
    check("Player: the controls say what they do: Show all findings now, Open Cinematic View, Run:", labels["toggle"] == "Show all findings now" and labels["cine"] == "Open Cinematic View" and (labels["run"] or "").startswith("Run:"), json.dumps(labels))
    for w, h in ((1024, 640), (820, 900)):
        s.resize(w, h)
        # A rebuild at this size: the objective starts folded on a short window.
        s.page.click(".pl-views [data-view='geospatial']")
        s.wait("window.__studio.player().renderer === 'geospatial'", 90, "geospatial")
        s.page.click(".pl-views [data-view='engineering']")
        s.wait("(() => { const p = window.__studio.player(); return p && p.view === 'engineering'; })()", 60, "engineering")
        time.sleep(0.8)
        brief = s.js("document.querySelector('details.pl-brief').open")
        if h < 700:
            check(f"Player {w}x{h}: the objective starts folded on a short window", brief is False, str(brief))
        if s.js("!!document.querySelector(\"[data-action='reveal']\")"):
            s.page.click("[data-action='reveal']")
        s.wait("document.querySelector('.pl-result')", 10, "result")
        time.sleep(0.6)
        r = s.js("""() => {
          const pills = [...document.querySelectorAll('.pl-run-v')].map((e) => e.textContent.trim());
          const bar = document.querySelector('.pl-runs').getBoundingClientRect();
          return { pills, inView: bar.top >= 0 && bar.bottom <= innerHeight };
        }""")
        check(f"Player {w}x{h}: after the result each run pill carries its mission and safety verdicts, in view without scrolling", len(r["pills"]) == 2 and "1 of 6 requirements failed" in r["pills"][0] and "2 of 6 requirements failed" in r["pills"][1] and all("No safety rule broken (5 checked)" in x for x in r["pills"]) and r["inView"], json.dumps(r))
        o = s.js(ux1.OVERLAP_JS, [[".pl-cams", ".pl-hud"], [".pl-cams", ".pl-runs"], [".pl-scene-note", ".pl-cams"]])
        check(f"Player {w}x{h}: the camera row does not cover the readout card, the run pills or the note", not o["clash"], json.dumps(o))
        s.shot(f"ux2-player-engineering-{w}x{h}-dark")
        if h < 700:
            s.page.click(".pl-views [data-view='control']")
            s.wait("document.querySelector('.mc')", 30, "flight console")
            time.sleep(2.5)
            bg = s.js("(() => { const e = document.querySelector('.mc-phase'); const c = getComputedStyle(e); return { bg: c.backgroundColor, op: c.opacity, text: e.textContent.slice(0, 40) }; })()")
            alpha = re.findall(r"[\d.]+", bg["bg"])
            a = float(alpha[3]) if len(alpha) > 3 else 1.0
            check("Flight console: the end sentence sits on a backing and is not dimmed", a >= 0.6 and float(bg["op"]) == 1.0 and bg["text"].startswith("Not met"), json.dumps(bg))
            o = s.js(ux1.OVERLAP_JS, [[".mc-cams", ".mc-bottom"], [".mc-cams", ".mc-right"], [".mc-cams", ".mc-strip"]])
            check("Flight console 1024x640: the camera row does not cover the timeline or the panels", not o["clash"], json.dumps(o))
            s.shot("ux2-flight-console-1024x640-dark")
            s.page.click(".mc-back")
            s.wait("document.querySelector('.pl-head')", 20, "player")
        s.resize(1440, 900)
    s.page.click(".pl-views [data-view='engineering']")
    time.sleep(0.5)
    s.shot("ux2-player-end-dark")
    m = s.js("[...document.querySelectorAll('.pl-failed li')].map((e) => e.innerText.replace(/\\s+/g, ' '))")
    check("Player: the failed rows give limit and observed value to four figures, no raw 1.583657", bool(m) and not any(re.search(r"\d\.\d{5,}", x) for x in m), json.dumps(m)[:240])


def unsafe_case(s):
    s.resize(1440, 900)
    open_mission(s, "corridor")
    s.page.click("[data-action='reveal']")
    s.wait("document.querySelector('.pl-result')", 30, "result")
    time.sleep(0.6)
    chips = s.js("[...document.querySelectorAll('.pl-run-result .vchip')].map((e) => [e.className, e.innerText.replace(/\\s+/g, ' ').trim()]).filter((x) => /SAFETY/i.test(x[1]))")
    texts = [c[1] for c in chips]
    bad = [c for c in chips if "safety rules broken" in c[1] or "A safety rule was broken" in c[1]]
    good = [c for c in chips if "No safety rule broken" in c[1]]
    check("Unsafe case: a run with a broken safety rule says how many were broken and is drawn as unsafe", bool(bad) and all("v-bad" in c[0] for c in bad), json.dumps(texts))
    check("Unsafe case: the safe runs of the same mission still say No safety rule broken", bool(good), json.dumps(texts))
    s.nav("library")
    s.wait("document.querySelectorAll('tbody tr[data-run]').length >= 3", 30, "runs")
    col = s.js("[...document.querySelectorAll('tbody tr[data-run]')].map((tr) => tr.innerText.replace(/\\s+/g, ' ')).filter((x) => /Ground|ground/.test(x))")
    check("Unsafe case: the Runs page shows A rule broken for it", any("A rule broken" in x for x in col), json.dumps(col)[:200])


def light_theme(s):
    s.resize(1440, 900)
    s.theme("light")
    for view, name in (("home", "home"), ("vehicles", "hangar"), ("library", "runs")):
        s.nav(view)
        time.sleep(0.8)
        s.shot(f"ux2-{name}-light")
    s.nav("compare")
    time.sleep(1.5)
    s.shot("ux2-compare-light")
    s.nav("lab")
    time.sleep(1.0)
    s.js("document.querySelector('.lab-result') && document.querySelector('.lab-result').scrollIntoView()")
    s.shot("ux2-lab-result-light")
    s.resize(820, 900)
    s.nav("home")
    s.shot("ux2-home-820-light")
    s.resize(1440, 900)
    s.theme("dark")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", required=True)
    ap.add_argument("--shots", required=True)
    ap.add_argument("--port", type=int, default=9271)
    ap.add_argument("--domains", default="")
    ap.add_argument("--environments", default="")
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
    env["VVLAB_LIBRARY"] = tempfile.mkdtemp(prefix="vv-ux2-lib-")
    env["VVLAB_CONFIG"] = tempfile.mkdtemp(prefix="vv-ux2-cfg-")
    env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"--remote-debugging-port={a.port}"
    proc = launch(os.path.abspath(os.path.expandvars(a.exe)), env, a.port)
    try:
        with sync_playwright() as pw:
            browser, s = session(pw, a.port, a.shots)
            ids = None
            try:
                home_stats(s)
            except Exception as e:  # noqa: BLE001
                check("home completed", False, repr(e)[:300])
            try:
                ids = lab_compare_runs(s)
                player_checks(s, ids)
            except Exception as e:  # noqa: BLE001
                check("lab, compare, runs, analyse and player completed", False, repr(e)[:400])
                s.shot("ux2-failure")
            for name, fn in (("unsafe", unsafe_case), ("light", light_theme)):
                try:
                    fn(s)
                except Exception as e:  # noqa: BLE001
                    check(f"{name} completed", False, repr(e)[:300])
            check("No page error or console error", not errors, "; ".join(errors)[:300])
            browser.close()
    finally:
        proc.kill()
    with open(os.path.join(a.shots, "ux2-facts.json"), "w", encoding="utf-8") as f:
        json.dump(FACTS, f, indent=1, sort_keys=True)
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
