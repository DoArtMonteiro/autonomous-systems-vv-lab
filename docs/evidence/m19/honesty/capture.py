r"""Screenshots and DOM facts of the six M19.1 defects, from a Studio built from this worktree.

    python docs/evidence/m19/honesty/capture.py --exe <vv-studio copy> --out <folder> --tag before|after

The Studio is started with a scratch library, a scratch configuration folder (preferences and log) and a scratch
WebView2 profile, so nothing of the installed application is read or written; the domain hosts are the ones
staged in this worktree (desktop/build.ps1 -StageOnly). The executable should be a copy with its own name
(for example vv-studio-m191-after.exe): the harness of the older journeys stops every process called
vv-studio.exe, and this one never does. Only the demonstration runs shipped with the product are started.
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

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "desktop", "studio", "tests"))
from m15_journeys import S, errors  # noqa: E402


def start(exe, port):
    env = dict(os.environ)
    for k in ("VVLAB_DOMAINS", "VVLAB_EXTRA_DOMAINS", "VVLAB_EXEC", "VVLAB_CLAIMS", "VVLAB_ENVIRONMENTS", "VVLAB_MODULES"):
        env.pop(k, None)
    stage = os.path.join(REPO, "desktop", "target", "release")
    env["VVLAB_DOMAINS"] = os.path.join(stage, "domains")
    env["VVLAB_EXEC"] = os.path.join(stage, "engines", "vv-exec.exe")
    env["VVLAB_CLAIMS"] = os.path.join(stage, "discovery", "claims")
    env["VVLAB_LIBRARY"] = tempfile.mkdtemp(prefix="vv-m191-lib-")
    env["VVLAB_CONFIG"] = tempfile.mkdtemp(prefix="vv-m191-cfg-")
    env["WEBVIEW2_USER_DATA_FOLDER"] = tempfile.mkdtemp(prefix="vv-m191-wv-")
    env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"--remote-debugging-port={port}"
    proc = subprocess.Popen([exe], env=env)
    for _ in range(600):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1)
            break
        except Exception:  # noqa: BLE001
            time.sleep(0.05)
    return proc, env


def open_mission(s, exp_id):
    s.page.evaluate("(id) => document.dispatchEvent(new CustomEvent('vv-open-mission', { detail: id }))", exp_id)
    s.wait(f"(() => {{ const p = window.__studio.player(); return p && p.experience === '{exp_id}' && document.querySelector('.pl-head'); }})()", 90, f"player {exp_id}")
    time.sleep(1.0)


def pick_run(s, index):
    s.page.click(f".pl-runs .pl-run:nth-child({index + 1})")
    time.sleep(0.6)


def to_end(s):
    s.page.click(".pl-reveal")
    s.wait("document.querySelector('.pl-result')", 20, "result")
    time.sleep(1.2)


CHIPS_JS = """() => [...document.querySelectorAll('.pl-run-result')].map((r) => ({
  run: r.querySelector('.pl-run-name') ? r.querySelector('.pl-run-name').textContent.trim() : '',
  chips: [...r.querySelectorAll('.vchip')].map((c) => ({ text: c.innerText.replace(/\\s+/g, ' ').trim(), cls: c.className, colour: getComputedStyle(c).color, border: getComputedStyle(c).borderColor })),
  failed: [...r.querySelectorAll('.pl-failed li')].map((l) => l.innerText.replace(/\\s+/g, ' ').trim()),
  clause: r.querySelector('.pl-run-clause') ? r.querySelector('.pl-run-clause').innerText.replace(/\\s+/g, ' ').trim() : null,
  allMet: [...r.querySelectorAll('p')].map((p) => p.innerText.trim()).filter((t) => /Every requirement/.test(t)),
}))"""

PILLS_JS = """() => [...document.querySelectorAll('.pl-runs .pl-run')].filter((e) => e.offsetParent !== null).map((e) => ({
  checked: e.getAttribute('aria-checked'), text: e.innerText.replace(/\\s+/g, ' ').trim(), title: e.title || null, aria: e.getAttribute('aria-label'),
  clipped: [...e.querySelectorAll('span')].filter((x) => x.offsetParent !== null && x.clientWidth > 2 && x.scrollWidth > x.clientWidth + 1).map((x) => x.className),
  visible: [...e.querySelectorAll('span')].filter((x) => x.offsetParent !== null && x.clientWidth > 2 && !x.querySelector('span')).map((x) => x.textContent.replace(/\\s+/g, ' ').trim()).join('|'),
  width: Math.round(e.getBoundingClientRect().width),
}))"""

PLUME_JS = """() => { const p = window.__studio.player(); return { view: p && p.view, t: p && p.t, t1: p && p.t1, plumeM: p ? p.plumeM : null }; }"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--port", type=int, default=9391)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    exe = os.path.abspath(a.exe)
    proc, env = start(exe, a.port)
    facts = {"tag": a.tag, "exe": os.path.basename(exe)}
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

            # 1. The safety chip beside failed requirements (two runs of one mission, one of them a hard landing).
            open_mission(s, "lying-altimeter")
            pick_run(s, 0)
            to_end(s)
            facts["safety_chip"] = s.js(CHIPS_JS)
            s.shot(f"{a.tag}-1-safety-chip-1440x900")

            # 2. The plume at the end of a run that ended before the other one.
            open_mission(s, "late-gnss")
            pick_run(s, 0)
            to_end(s)
            facts["plume_past_end"] = {"run": s.js("window.__studio.player().runs[0]"), "state": s.js(PLUME_JS), "run_ended_at_s": s.js("window.__studio.player().t1")}
            s.shot(f"{a.tag}-2-plume-past-end-1440x900")
            # Just before the contact of the same run the plume is drawn, so it is not hidden everywhere.
            ended = s.js("(() => { const e = document.querySelector('.pl-ended'); const m = e && /at ([0-9.]+) s/.exec(e.textContent); return m ? Number(m[1]) : null; })()")
            facts["plume_before_contact"] = None
            if ended:
                s.js("(t) => { const r = document.querySelector('.pl-range'); r.value = String(t); r.dispatchEvent(new Event('input', { bubbles: true })); }", ended - 0.3)
                time.sleep(0.8)
                facts["plume_before_contact"] = {"t": s.js("window.__studio.player().t"), "plumeM": s.js("window.__studio.player().plumeM")}
                s.shot(f"{a.tag}-2-plume-before-contact-1440x900")
            s.resize(1024, 640)
            s.shot(f"{a.tag}-2-plume-past-end-1024x640")
            facts["pills_late_gnss_1024x640"] = s.js(PILLS_JS)
            s.resize(1440, 900)

            # 3. The corridor mission: Mission incomplete with the vehicle at the goal.
            open_mission(s, "corridor")
            pick_run(s, 1)
            to_end(s)
            facts["corridor_second_run"] = s.js(CHIPS_JS)
            facts["corridor_flight_readout"] = s.js("[...document.querySelectorAll('.pl-hud-row')].map((r) => ({ text: r.innerText.replace(/\\s+/g, ' ').trim(), title: r.title }))")
            s.shot(f"{a.tag}-3-corridor-completion-1440x900")
            s.resize(1024, 640)
            time.sleep(0.8)
            facts["pills_corridor_1024x640"] = s.js(PILLS_JS)
            s.shot(f"{a.tag}-3-corridor-pills-1024x640")
            pick_run(s, 0)
            s.shot(f"{a.tag}-3-corridor-pills-first-selected-1024x640")
            facts["pills_corridor_first_selected_1024x640"] = s.js(PILLS_JS)
            s.resize(1440, 900)

            # 4. The Library table and the comparison (the same verdict chips elsewhere).
            s.nav("library")
            time.sleep(1.0)
            s.shot(f"{a.tag}-4-library-1440x900")
            facts["library_safety_cells"] = s.js("[...document.querySelectorAll('td .cell')].map((c) => ({ text: c.innerText.replace(/\\s+/g, ' ').trim(), cls: c.className, colour: getComputedStyle(c).color }))")
            facts["errors"] = list(errors)
            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
    with open(os.path.join(a.out, f"{a.tag}-facts.json"), "w", encoding="utf-8") as f:
        json.dump(facts, f, indent=1, sort_keys=True)
        f.write("\n")
    print("done", a.out)
    if a.tag == "after":
        sys.exit(0 if evaluate(facts) else 1)


def evaluate(facts):
    """The assertions of the corrected Studio on the facts collected above (the 0.18.1 facts fail the same ones)."""
    green = "rgb(61, 191, 152)"
    first = facts["safety_chip"][0]
    safety = next(c for c in first["chips"] if c["text"].startswith("SAFETY"))
    mission = next(c for c in first["chips"] if c["text"].startswith("MISSION"))
    corridor = facts["corridor_second_run"][1]
    unselected = [p for p in facts["pills_corridor_1024x640"] if p["checked"] == "false"]
    checks = [
        ("the safety chip beside failed requirements is neutral, not green", "v-held" in safety["cls"] and safety["colour"] != green),
        ("the failed mission chip keeps its failure class", "v-warn" in mission["cls"] and "failed" in mission["text"]),
        ("no 'Every requirement' sentence beside a failed requirement", not first["allMet"]),
        ("the plume is not drawn after the last sample", facts["plume_past_end"]["state"]["plumeM"] == 0),
        ("the plume is still drawn just before the contact", bool(facts.get("plume_before_contact")) and (facts["plume_before_contact"]["plumeM"] or 0) > 0),
        ("the failed mission completion says what the record says and does not say", bool(corridor["clause"]) and "does not say which part" in corridor["clause"]),
        ("the goal distance readout says it is not completion", any(r["text"].startswith("D To goal") and "Mission completion requirement" in r["title"] for r in facts["corridor_flight_readout"])),
        ("1024x640: no pill has clipped text", all(not p["clipped"] for p in facts["pills_corridor_1024x640"] + facts["pills_corridor_first_selected_1024x640"])),
        ("1024x640: an unselected pill gives an exact count of conditions", bool(unselected) and all("condition" in p["text"] for p in unselected)),
        ("1024x640: the tooltip of every pill has the whole identity", all(p["title"] for p in facts["pills_corridor_1024x640"])),
        ("no script error", not facts["errors"]),
    ]
    ok = True
    for name, passed in checks:
        print(("PASS " if passed else "FAIL ") + name)
        ok = ok and passed
    return ok


if __name__ == "__main__":
    main()
