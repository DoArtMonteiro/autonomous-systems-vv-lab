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
    check("Compare: each run card gives the failure count first and the safety rules held after it", cards == ["1 of 6 requirements failed · 5 of 5 safety rules held", "2 of 6 requirements failed · 5 of 5 safety rules held"], json.dumps(cards))
    first = s.js("(() => { const rows = [...document.querySelectorAll('.matrix tbody tr')]; const sep = rows.findIndex((r) => r.classList.contains('sep') && /Verdict changes/.test(r.textContent)); return sep < 0 ? null : { sep, next: rows[sep + 1] && rows[sep + 1].dataset.row, count: rows.filter((r, i) => i > sep && !r.classList.contains('sep')).slice(0, 1).length }; })()")
    check("Compare: the rows whose verdict changes come first, in their own group", bool(first) and first["next"] == "R1_vertical_speed", json.dumps(first))
    over = s.js("(() => { const w = document.querySelector('.cmp-matrix'); return w.scrollWidth - w.clientWidth; })()")
    check("Compare: the table fits its pane, every run column is in view", over <= 1, str(over))
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
    s.page.click(f"tbody tr[data-run='{exp}']")
    time.sleep(0.6)
    over = s.js("(() => { const w = document.querySelector('.lib-table-wrap'); return { table: w.scrollWidth - w.clientWidth, page: document.documentElement.scrollWidth - innerWidth }; })()")
    check("Runs: with the detail panel open there is no horizontal scroll", over["table"] <= 1 and over["page"] <= 0, json.dumps(over))
    s.shot("ux3-runs-detail-dark")
    # Analyse
    s.page.dblclick(f"tbody tr[data-run='{exp}']")
    s.wait("window.__studio.view() === 'run' && document.querySelector('.verdict')", 30, "analyse")
    time.sleep(1.0)
    sent = s.js("document.querySelector(\".verdict[aria-label='Mission outcome'] .verdict-x\").innerText.replace(/\\s+/g, ' ')")
    check("Analyse: the outcome sentence names the failed requirements in plain words", "2 mission requirements failed: Vertical speed at contact, Horizontal speed at contact." in sent and not re.search(r"R\d_", sent), sent[:200])
    cut = s.js("[...document.querySelectorAll('.verdict-x, .validity-strip .vtext, .verdict-v span')].filter((e) => e.scrollWidth > e.clientWidth + 1 || e.scrollHeight > e.clientHeight + 2).length")
    check("Analyse: the outcome, the safety line and the model validity wrap and are not cut", cut == 0, f"{cut} cut")
    tilt = s.js("(() => { const r = document.querySelector(\".req[data-id='S1_tilt_envelope'] .req-eo\"); return r ? r.innerText.replace(/\\s+/g, ' ') : null; })()")
    check("Analyse: the tilt rows are in degrees, with the recorded cosine in parentheses", bool(tilt) and re.search(r"worst [\d.]+ ° \([\d.]+ cos\)", tilt) is not None, str(tilt))
    s.shot("ux2-analyse-dark")
    return base, exp


PILLS_JS = """(sel) => {
  const pills = [...document.querySelectorAll(sel)].filter((e) => e.offsetParent !== null);
  const bad = pills.filter((e) => {
    const c = getComputedStyle(e);
    const cut = e.scrollHeight > e.clientHeight + 1 || e.scrollWidth > e.clientWidth + 1 || (c.textOverflow === 'ellipsis' && e.scrollWidth > e.clientWidth);
    const r = e.getBoundingClientRect();
    return cut || r.left < -0.5 || r.right > innerWidth + 0.5 || r.bottom > innerHeight + 0.5;
  }).map((e) => e.textContent.trim().slice(0, 60));
  return { n: pills.length, bad };
}"""


def check_pills(s, where, sel=".pl-run"):
    """No run pill is cut: its whole text is inside its own box and inside the window."""
    r = s.js(PILLS_JS, sel)
    check(f"{where}: no run pill is clipped", r["n"] >= 2 and not r["bad"], json.dumps(r))


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
          const shown = [...document.querySelectorAll('.pl-run')].map((b) => ({ active: b.getAttribute('aria-checked') === 'true', visible: b.querySelector('.pl-run-v').offsetParent !== null, hasId: !!b.querySelector('.pl-run-id') }));
          const bar = document.querySelector('.pl-runs').getBoundingClientRect();
          return { pills, shown, inView: bar.top >= 0 && bar.bottom <= innerHeight };
        }""")
        # On a short window the run pills are one row: the shown run in full, the others as their name (and the warning icon).
        short = h < 700
        vis_ok = all(x["visible"] == (x["active"] or not short) for x in r["shown"])
        check(f"Player {w}x{h}: after the result each run pill carries its mission and safety verdicts (the shown run in full on a short window), in view without scrolling", len(r["pills"]) == 2 and "1 of 6 requirements failed · 5 of 5 safety rules held" in r["pills"][0] and "2 of 6 requirements failed · 5 of 5 safety rules held" in r["pills"][1] and r["inView"] and vis_ok and all(x["hasId"] for x in r["shown"]), json.dumps(r))
        ident = s.js("""() => {
          const conds = Object.fromEntries([...document.querySelectorAll('.pl-run-cond')].map((e) => [e.dataset.run, e.dataset.conditions]));
          const pills = [...document.querySelectorAll('.pl-run')].map((b) => { const id = (b.querySelector('.pl-run-id').title || '').replace('Run ', ''); return { id, text: b.textContent.toLowerCase(), cond: (conds[id] || '').toLowerCase() }; });
          const opts = [...document.querySelectorAll('.pl-cin-run option')].map((o) => o.textContent.toLowerCase());
          return { pills, opts };
        }""")
        hexid = s.js("[...document.querySelectorAll('.pl-run')].map((b) => /[0-9a-f]{8}/.test(b.innerText))")
        check(f"Player {w}x{h}: the visible text of every run pill, shown or not, contains an 8-hex id", len(hexid) == 2 and all(hexid), json.dumps(hexid))
        check(f"Player {w}x{h}: each run pill and each Run option carries the run's conditions and its short id", len(ident["pills"]) == 2 and all(p["cond"] and p["cond"] in p["text"] and p["id"][:8] in p["text"] for p in ident["pills"]) and all(p["id"][:8] in o and p["cond"] in o for p, o in zip(ident["pills"], ident["opts"])), json.dumps(ident)[:400])
        area = s.js("(() => { const c = [...document.querySelectorAll('.pl-viewport canvas')].filter((e) => e.offsetParent !== null).map((e) => Math.round(e.getBoundingClientRect().height)); return c; })()")
        check(f"Player {w}x{h}: the scene is at least 200 px tall", bool(area) and max(area) >= 200, json.dumps(area))
        o = s.js(ux1.OVERLAP_JS, [[".pl-cams", ".pl-hud"], [".pl-cams", ".pl-runs"], [".pl-scene-note", ".pl-cams"]])
        check(f"Player {w}x{h}: the camera row does not cover the readout card, the run pills or the note", not o["clash"] and not o["unseen"], json.dumps(o))
        check_pills(s, f"Engineering {w}x{h}")
        s.shot(f"ux2-player-engineering-{w}x{h}-dark")
        # Geospatial: the same pills, stacked and wrapped, never cut in the middle of a clause.
        s.page.click(".pl-views [data-view='geospatial']")
        s.wait("window.__studio.player().renderer === 'geospatial'", 90, "geospatial")
        time.sleep(1.5)
        check_pills(s, f"Geospatial {w}x{h}")
        o = s.js(ux1.OVERLAP_JS, [[".pl-cams", ".pl-runs"]])
        check(f"Player {w}x{h} (geospatial): the camera row does not cover the run pills", not o["clash"] and not o["unseen"], json.dumps(o))
        s.shot(f"ux3-player-geospatial-{w}x{h}-dark")
        s.page.click(".pl-views [data-view='engineering']")
        s.wait("(() => { const p = window.__studio.player(); return p && p.view === 'engineering'; })()", 60, "engineering")
        if True:
            s.page.click(".pl-views [data-view='control']")
            s.wait("document.querySelector('.mc')", 30, "flight console")
            time.sleep(2.5)
            bg = s.js("(() => { const e = document.querySelector('.mc-phase'); const c = getComputedStyle(e); return { bg: c.backgroundColor, op: c.opacity, text: e.textContent.slice(0, 40) }; })()")
            alpha = re.findall(r"[\d.]+", bg["bg"])
            a = float(alpha[3]) if len(alpha) > 3 else 1.0
            check("Flight console: the end sentence sits on a backing and is not dimmed", a >= 0.6 and float(bg["op"]) == 1.0 and bg["text"].startswith("Not met"), json.dumps(bg))
            o = s.js(ux1.OVERLAP_JS, [[".mc-cams", ".mc-bottom"], [".mc-cams", ".mc-right"]])
            check(f"Flight console {w}x{h}: the camera row does not cover the timeline or the panels", not o["clash"] and not o["unseen"], json.dumps(o))
            check_pills(s, f"Flight console {w}x{h}", sel=".mc-run")
            o = s.js(ux1.OVERLAP_JS, [[".mc-id", ".mc-time"], [".mc-time", ".mc-tools"], [".mc-runs", ".mc-time"]])
            edge = s.js("(() => { const e = document.querySelector('.mc-tools'); return Math.round([...e.children].map((c) => c.getBoundingClientRect().right).reduce((a, b) => Math.max(a, b), 0)) - innerWidth; })()")
            check(f"Flight console {w}x{h}: the header does not crowd, the run pills sit under the end sentence and the tools stay in the window", not o["clash"] and not o["unseen"] and edge <= 0, json.dumps(o) + f" tools edge {edge}")
            chips = s.js("[...document.querySelectorAll('.mc-badges .grade, .mc-badges .pl-case')].map((e) => e.textContent.trim())")
            check(f"Flight console {w}x{h}: the Your experiment and Exploratory chips are shown under the title", any("experiment" in c.lower() for c in chips) and any("Exploratory" in c for c in chips), json.dumps(chips))
            s.shot(f"ux2-flight-console-{w}x{h}-dark")
            s.page.click(".mc-back")
            s.wait("document.querySelector('.pl-head')", 20, "player")
        s.resize(1440, 900)
    s.page.click(".pl-views [data-view='engineering']")
    time.sleep(0.5)
    o = s.js(ux1.OVERLAP_JS, [[".pl-cams", ".pl-hud"], [".pl-cams", ".pl-runs"], [".pl-scene-note", ".pl-cams"], [".pl-scene-note", ".pl-runs"]])
    check("Player 1440x900 (end state): pills, caption and camera buttons do not overlap one another or the readout card", not o["clash"] and not o["unseen"], json.dumps(o))
    check_pills(s, "Engineering 1440x900 (end state)")
    s.shot("ux2-player-end-dark")
    s.page.click(".pl-views [data-view='geospatial']")
    s.wait("window.__studio.player().renderer === 'geospatial'", 90, "geospatial")
    time.sleep(2.0)
    s.shot("ux3-player-geospatial-1440x900-dark")
    s.page.click(".pl-views [data-view='control']")
    s.wait("document.querySelector('.mc')", 30, "flight console")
    time.sleep(2.0)
    s.shot("ux3-flight-console-1440x900-dark")
    s.page.click(".mc-back")
    s.wait("document.querySelector('.pl-head')", 20, "player")
    m = s.js("[...document.querySelectorAll('.pl-failed li')].map((e) => e.innerText.replace(/\\s+/g, ' '))")
    check("Player: the failed rows give limit and observed value to four figures, no raw 1.583657", bool(m) and not any(re.search(r"\d\.\d{5,}", x) for x in m), json.dumps(m)[:240])


def go(s, view):
    """Opens a view whatever the window width (the secondary nav buttons are in the More menu when narrow)."""
    s.js(f"document.querySelector(\".nav-btn[data-view='{view}']\").click()")
    s.wait(f"window.__studio.view() === '{view}'", 30, view)
    time.sleep(1.2)


def capture_sizes(s):
    """The same screens at three sizes for the review: Lab, Compare, Analyse and Runs, then the player views."""
    for w, h in ((1440, 900), (1024, 640), (820, 900)):
        s.resize(w, h)
        go(s, "lab")
        s.js("document.querySelector('.lab-result') && document.querySelector('.lab-result').scrollIntoView()")
        lab_t = s.js("""() => { const wrap = document.querySelector('.lab-table-wrap'); if (!wrap) return null; const th = [...wrap.querySelectorAll('thead th')].find((e) => /Margin change/.test(e.textContent)); const foot = wrap.querySelector('tfoot td'); const r = th ? th.getBoundingClientRect() : null; const wr = wrap.getBoundingClientRect();
          return { over: wrap.scrollWidth - wrap.clientWidth, marginIn: !!r && r.right <= wr.right + 1 && r.left >= wr.left - 1, footCut: foot ? foot.scrollWidth - foot.clientWidth : 0 }; }""")
        if w != 1024:
            check(f"Lab {w}x{h}: Margin change is in view without sideways scrolling and the footnote is not clipped", bool(lab_t) and lab_t["over"] <= 1 and lab_t["marginIn"] and lab_t["footCut"] <= 1, json.dumps(lab_t))
        s.shot(f"ux3-lab-{w}x{h}-dark")
        go(s, "compare")
        s.shot(f"ux3-compare-{w}x{h}-dark")
        go(s, "run")
        panes = s.js("[...document.querySelectorAll('.scene-pane canvas')].filter((e) => e.offsetParent !== null).map((e) => Math.round(e.getBoundingClientRect().height))")
        if w < 1440:
            check(f"Analyse {w}x{h}: every plot of the scene (3D, profile, top view) is at least 200 px tall", len(panes) >= 3 and min(panes) >= 200, json.dumps(panes))
        if w <= 900:
            st = s.js("""() => { const a = document.querySelector('.scene-pane'); const b = document.querySelector('.tele'); if (!a || !b) return null; const ra = a.getBoundingClientRect(); const rb = b.getBoundingClientRect(); return { sceneBottom: Math.round(ra.bottom + scrollY), teleTop: Math.round(rb.top + scrollY), sameColumn: Math.abs(ra.left - rb.left) < 2 }; }""")
            check(f"Analyse {w}x{h}: the scene is above the telemetry and the two do not overlap", bool(st) and st["sameColumn"] and st["teleTop"] >= st["sceneBottom"] - 1, json.dumps(st))
            o = s.js(ux1.OVERLAP_JS, [[".scene-pane", ".tele"], [".scene-bar", ".tele-head"]])
            check(f"Analyse {w}x{h}: no overlap between the scene controls and the telemetry header", not o["clash"], json.dumps(o))
        s.shot(f"ux3-analyse-{w}x{h}-dark")
        go(s, "library")
        # With a run selected (its detail panel open) the Outcome, Safety rules and Failed columns are all in view.
        s.js("(() => { const r = document.querySelector('tbody tr[data-run]'); if (r) r.click(); })()")
        time.sleep(0.6)
        cols = s.js("""() => [...document.querySelectorAll('thead th')].filter((e) => e.offsetParent !== null && /Outcome|Safety rules|Failed/.test(e.textContent)).map((e) => { const r = e.getBoundingClientRect(); return { name: e.textContent.trim(), left: Math.round(r.left), right: Math.round(r.right), inside: r.left >= 0 && r.right <= innerWidth + 1 }; })""")
        check(f"Runs {w}x{h} with the detail panel open: Outcome, Safety rules and Failed are in view", len(cols) == 3 and all(c["inside"] for c in cols), json.dumps(cols))
        seeds = s.js("[...document.querySelectorAll('tbody tr[data-run] td:nth-child(6)')].filter((e) => e.offsetParent !== null).map((e) => { const r = document.createRange(); r.selectNodeContents(e); return [e.textContent.trim(), r.getClientRects().length]; })")
        check(f"Runs {w}x{h} with the detail panel open: a number (the seed) is never broken over two lines", bool(seeds) and all(x[1] <= 1 for x in seeds), json.dumps(seeds))
        s.shot(f"ux3-runs-{w}x{h}-dark")
        check(f"Layout {w}x{h}: the Lab, Compare, Analyse and Runs pages have no horizontal page scroll", s.no_hscroll())
    s.resize(1440, 900)
    s.js("document.querySelector(\".nav-btn[data-view='missions']\").click()")
    s.wait("window.__studio.view() === 'missions'", 20, "missions")
    s.js("window.__studio.player && null")
    open_mission(s, "first-landing")
    time.sleep(2)
    s.shot("ux3-player-first-landing-1440x900-dark")


def unsafe_case(s):
    s.resize(1440, 900)
    open_mission(s, "corridor")
    s.page.click("[data-action='reveal']")
    s.wait("document.querySelector('.pl-result')", 30, "result")
    time.sleep(0.6)
    chips = s.js("[...document.querySelectorAll('.pl-run-result .vchip')].map((e) => [e.className, e.innerText.replace(/\\s+/g, ' ').trim()]).filter((x) => /SAFETY/i.test(x[1]))")
    texts = [c[1] for c in chips]
    bad = [c for c in chips if re.search(r"\d+ of \d+ safety rules broken", c[1]) or "A safety rule was broken" in c[1]]
    good = [c for c in chips if "No safety rule broken" in c[1]]
    check("Unsafe case: a run with a broken safety rule says how many were broken and is drawn as unsafe", bool(bad) and all("v-bad" in c[0] for c in bad), json.dumps(texts))
    check("Unsafe case: the safe runs of the same mission still say No safety rule broken", bool(good), json.dumps(texts))
    # The corridor player at the two small sizes: the 2D plot is tall enough to read and every pill carries its short id.
    for w, h in ((1024, 640), (820, 900)):
        s.resize(w, h)
        s.js("window.dispatchEvent(new Event('resize'))")
        time.sleep(1.2)
        r = s.js("""() => ({
          plot: [...document.querySelectorAll('.pl-viewport canvas')].filter((e) => e.offsetParent !== null).map((e) => Math.round(e.getBoundingClientRect().height)),
          pills: [...document.querySelectorAll('.pl-run')].map((b) => ({ id: /[0-9a-f]{8}/.test(b.innerText), cond: /GPS noise|Arrival radius|default conditions/.test(b.innerText) })),
        })""")
        need = 220 if w == 820 else 200
        check(f"Corridor player {w}x{h}: the 2D plot is at least {need} px tall", bool(r["plot"]) and max(r["plot"]) >= need, json.dumps(r["plot"]))
        check(f"Corridor player {w}x{h}: every run pill, shown or not, keeps its conditions and an 8-hex id", len(r["pills"]) >= 2 and all(x["id"] and x["cond"] for x in r["pills"]), json.dumps(r["pills"]))
    s.resize(1440, 900)
    time.sleep(0.5)
    s.nav("library")
    s.wait("document.querySelectorAll('tbody tr[data-run]').length >= 3", 30, "runs")
    col = s.js("[...document.querySelectorAll('tbody tr[data-run]')].map((tr) => tr.innerText.replace(/\\s+/g, ' ')).filter((x) => /Corridor|corridor/.test(x))")
    check("Unsafe case: the Runs page says how many safety rules were broken (no total the summary does not carry)", any(re.search(r"\d+ safety rules? broken", x) and not re.search(r"\d+ of \d+ safety rules broken", x) for x in col), json.dumps(col)[:240])
    # The count must be the record's own: read the unsafe run's record and compare.
    row = s.js("""(() => { const tr = [...document.querySelectorAll('tbody tr[data-run]')].find((e) => /safety rules? broken/.test(e.innerText)); return tr ? { id: tr.dataset.run, text: tr.innerText.replace(/\\s+/g, ' ') } : null; })()""")
    if row:
        rec = m18.record(s, row["id"])
        inv = [q for q in rec["requirements"] if q["category"] == "invariant"]
        broken = [q for q in inv if q["status"] == "fail"]
        judged = [q for q in inv if q["status"] != "not_evaluated"]
        m = re.search(r"(\d+) safety rules? broken", row["text"])
        check("Unsafe case: the Runs page count equals the record's broken safety rules", bool(m) and int(m.group(1)) == len(broken), f"{row['text'][:120]} vs {len(broken)} broken")
        split = s.js(f"(() => {{ const td = document.querySelector(\"tbody tr[data-run='{row['id']}'] td.failed\"); return td ? td.innerText.replace(/\\s+/g, ' ') : ''; }})()")
        check("Unsafe case: the Failed cell separates Safety rules from Requirements", "Safety rules:" in split and "Requirements:" in split, split[:200])
        s.shot("ux3-runs-unsafe-dark")
        s.page.dblclick(f"tbody tr[data-run='{row['id']}']")
        s.wait("window.__studio.view() === 'run' && document.querySelector('.verdict')", 30, "analyse")
        time.sleep(1.0)
        sv = s.js("document.querySelector(\".verdict[aria-label='Safety'] .verdict-v\").innerText.replace(/\\s+/g, ' ')")
        check("Unsafe case: Analyse says the same count and draws the verdict as unsafe", f"{len(broken)} of {len(judged)} safety rules broken" in sv, sv)
        s.shot("ux3-analyse-unsafe-dark")
        s.nav("library")
        s.wait("document.querySelectorAll('tbody tr[data-run]').length >= 3", 30, "runs")
        ground = s.js("[...document.querySelectorAll('tbody tr[data-run]')].filter((e) => /Corridor/.test(e.innerText)).map((e) => e.dataset.run)")
        for rid in ground[:2]:
            s.page.check(f"tbody tr[data-run='{rid}'] input[type=checkbox]")
        s.page.click("#lib-compare")
        s.wait("window.__studio.view() === 'compare' && document.querySelector('.matrix')", 30, "compare")
        time.sleep(2)
        over = s.js("(() => { const w = document.querySelector('.cmp-matrix'); return w.scrollWidth - w.clientWidth; })()")
        check("Compare (unsafe case): the table fits its pane, every run column is in view", over <= 1, str(over))
        s.shot("ux3-compare-unsafe-dark")


BARE_SAFE_JS = """() => {
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const bad = [];
  for (let n = w.nextNode(); n; n = w.nextNode()) {
    const e = n.parentElement;
    if (!e || e.offsetParent === null) continue;
    if (/^\\s*safe\\s*$/i.test(n.textContent)) bad.push(e.className + ':' + n.textContent.trim());
  }
  return bad;
}"""


def identity_checks(s):
    """One display name per run id on every surface (Runs, Compare, Analyse, player), runs with different
    requests never share a visible label, and no visible text node is a bare "safe" or "Safe" verdict."""
    s.resize(1440, 900)
    s.nav("library")
    s.wait("document.querySelectorAll('tbody tr[data-run]').length >= 3", 30, "runs")
    s.wait("[...document.querySelectorAll('.run-cond')].every((e) => e.dataset.conditions)", 30, "conditions")
    rows = s.js("[...document.querySelectorAll('tbody tr[data-run]')].map((tr) => ({ id: tr.dataset.run, cond: (tr.querySelector('.run-cond') || {}).dataset ? tr.querySelector('.run-cond').dataset.conditions : '', text: tr.innerText.replace(/\\s+/g, ' ') }))")
    names = {r["id"]: r["cond"] for r in rows}
    check("Identity: every run on the Runs page shows its conditions", bool(rows) and all(r["cond"] for r in rows), json.dumps([r["cond"] for r in rows])[:300])
    # The catalog defaults, read from the Studio's own store: a parameter at its default is not a condition.
    defaults = s.js("""async () => { const m = await import('./js/store.js'); const out = {}; for (const d of m.state.domains) out[d.manifest.id] = Object.fromEntries((((d.catalog || {}).parameters) || []).map((p) => [p.id, p.default])); return out; }""")
    configured = []
    for r in rows:
        req = m18.record(s, r["id"])["request"]
        has = bool(req.get("faults")) or any(v != defaults.get(req["domain"], {}).get(k) for k, v in (req.get("parameters") or {}).items())
        configured.append((r["id"], req, has))
    wrong = [(i, names[i]) for i, req, has in configured if has and names[i] in ("default conditions", "no injected fault")]
    check("Identity: a run with a configured parameter or fault never reads as default conditions", not wrong, json.dumps(wrong)[:300])
    bad = s.js(BARE_SAFE_JS)
    check("Identity: the Runs page has no visible text that is a bare safe or Safe verdict", not bad, json.dumps(bad))
    # Same mission, controller and seed but different conditions must not share a name.
    groups = {}
    for i, req, _ in configured:
        groups.setdefault((req["scenario"], req["controller"], req["seed"]), []).append((i, json.dumps([req.get("parameters"), req.get("faults")], sort_keys=True)))
    clash = []
    for key, items in groups.items():
        by_name = {}
        for i, canon in items:
            by_name.setdefault(names[i], set()).add(canon)
        clash += [n for n, c in by_name.items() if len(c) > 1]
    check("Identity: two runs with different requests never share a visible name on the Runs page", not clash, json.dumps(clash)[:300])
    # Compare: the corridor runs, names distinct, the shared line present, every name equal to the Runs page name.
    ground = [r["id"] for r in rows if re.search("Corridor", r["text"])]
    if len(ground) >= 2:
        for rid in ground[:3]:
            s.page.check(f"tbody tr[data-run='{rid}'] input[type=checkbox]")
        s.page.click("#lib-compare")
        s.wait("window.__studio.view() === 'compare' && document.querySelector('.matrix')", 30, "compare")
        time.sleep(1.5)
        keys = s.js("[...document.querySelectorAll('.run-key')].map((k) => ({ id: k.dataset.run, label: (k.querySelector('.key-label') || {}).textContent, cond: (k.querySelector('.key-cond') || {}).dataset ? k.querySelector('.key-cond').dataset.conditions : '' }))")
        shared = s.js("(document.querySelector('.cmp-shared') || {}).textContent")
        check("Compare: each run has the same conditions as on the Runs page", bool(keys) and all(k["cond"] == names.get(k["id"]) for k in keys), json.dumps(keys)[:400])
        reqs = {k["id"]: json.dumps(m18.record(s, k["id"])["request"], sort_keys=True) for k in keys}
        labels = [k["label"] for k in keys]
        distinct = len(set(reqs.values())) == len(reqs)
        check("Compare: runs with different requests never share a visible label", not distinct or len(set(labels)) == len(labels), json.dumps(labels))
        check("Compare: the line says what the runs share and where they differ", bool(shared) and re.match(r"(Both runs|All \d+ runs): .+; (they differ only in .+|nothing in their conditions differs)\.$", shared), str(shared))
        bad = s.js(BARE_SAFE_JS)
        check("Identity: Compare has no visible text that is a bare safe or Safe verdict", not bad, json.dumps(bad))
        rows = s.js("[...document.querySelectorAll('.cmp-headline-row')].map((e) => e.innerText.replace(/\\s+/g, ' ').trim())")
        flips = [x for x in rows if "fails it;" in x or "passes it." in x]
        check("Compare: when a verdict flips, the sentence names the run that fails first", bool(flips) and all(x.index("fails it;") < x.index("passes it.") for x in flips), json.dumps(rows)[:400])
        s.shot("ux4-compare-identity-dark")
        # Two runs: GPS noise 1 mm, and the same with a 250 mm arrival radius. The line says exactly that.
        pair = [i for i, n in names.items() if n in ("GPS noise 1 mm", "Arrival radius 250 mm · GPS noise 1 mm")]
        if len(pair) == 2:
            s.nav("library")
            s.wait("document.querySelectorAll('tbody tr[data-run]').length >= 3", 30, "runs")
            s.js("document.querySelectorAll('tbody tr[data-run] input[type=checkbox]:checked').forEach((c) => c.click())")
            for rid2 in pair:
                s.page.check(f"tbody tr[data-run='{rid2}'] input[type=checkbox]")
            s.page.click("#lib-compare")
            s.wait("window.__studio.view() === 'compare' && document.querySelector('.matrix')", 30, "compare")
            time.sleep(1.5)
            shared2 = s.js("(document.querySelector('.cmp-shared') || {}).textContent")
            check("Compare (two runs): the line reads Both runs: GPS noise 1 mm; they differ only in Arrival radius", shared2 == "Both runs: GPS noise 1 mm; they differ only in Arrival radius.", str(shared2))
            s.shot("ux4-compare-two-runs-dark")
        # Analyse of the first of them, then the player: the same name for the same id.
        rid = keys[0]["id"]
        s.nav("library")
        s.wait("document.querySelectorAll('tbody tr[data-run]').length >= 3", 30, "runs")
        s.page.dblclick(f"tbody tr[data-run='{rid}']")
        s.wait("window.__studio.view() === 'run' && document.querySelector('.verdict')", 30, "analyse")
        time.sleep(0.8)
        cond = s.js("(document.querySelector('.run-cond-line') || {}).dataset ? document.querySelector('.run-cond-line').dataset.conditions : ''")
        check("Analyse: the run has the same conditions as on the Runs page", cond == names[rid], f"{cond} vs {names[rid]}")
        bad = s.js(BARE_SAFE_JS)
        check("Identity: Analyse has no visible text that is a bare safe or Safe verdict", not bad, json.dumps(bad))
    # Player: the Lab runs (baseline and experiment) carry the same names as on the Runs page.
    s.nav("lab")
    if s.js("!!document.querySelector('#lab-watch')"):
        s.page.click("#lab-watch")
        s.wait("(() => { const p = window.__studio.player(); return p && p.experience.startsWith('runs:') && document.querySelector('.pl-hud dl'); })()", 120, "player")
        time.sleep(1.0)
        if s.js("!!document.querySelector(\"[data-action='reveal']\")"):
            s.page.click("[data-action='reveal']")
        s.wait("document.querySelector('.pl-run-cond')", 10, "player conditions")
        pc = s.js("[...document.querySelectorAll('.pl-run-cond')].map((e) => ({ id: e.dataset.run, cond: e.dataset.conditions }))")
        check("Player: each run has the same conditions as on the Runs page", bool(pc) and all(c["cond"] == names.get(c["id"]) for c in pc if c["id"] in names), json.dumps(pc)[:300] + " vs " + json.dumps({c["id"]: names.get(c["id"]) for c in pc})[:300])
        bad = s.js(BARE_SAFE_JS)
        check("Identity: the player has no visible text that is a bare safe or Safe verdict", not bad, json.dumps(bad))


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
    s.nav("environments")
    time.sleep(2.0)
    s.shot("ux3-environments-light")
    s.nav("run")
    time.sleep(1.5)
    s.shot("ux3-analyse-light")
    open_mission(s, "first-landing")
    time.sleep(2.5)
    s.shot("ux3-player-light")
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
            for name, fn in (("capture", capture_sizes), ("unsafe", unsafe_case), ("identity", identity_checks), ("light", light_theme)):
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
