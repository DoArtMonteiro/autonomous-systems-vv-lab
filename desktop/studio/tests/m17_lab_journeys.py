r"""M17 journeys of the Experiment Lab in the real WebView2 window: open a failed mission run in the
Lab, change the controller, run a new simulation and read the comparison, check the change on
other seeds, sweep one parameter, switch to an exploratory vehicle preset, move a judging-only
requirement limit, and the layout at a narrow window. Every new run is replayed by the platform to
show it is a recomputable record. Screenshots go to --shots. It uses a scratch library.

    python desktop/studio/tests/m17_lab_journeys.py --exe desktop/target/release/vv-studio.exe --domains desktop/target/release/domains
    python desktop/studio/tests/m17_lab_journeys.py --exe "%LOCALAPPDATA%\VV Lab Studio\vv-studio.exe" --domains ""

These are scripted checks of what the screen shows. They are not observations of people using it.
"""

import argparse
import json
import os
import sys
import tempfile
import time

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from m15_journeys import check, errors, results  # noqa: E402
from m16_journeys import launch, open_mission, session  # noqa: E402

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def lab(s):
    return s.js("window.__studio.lab()")


def record(s, rid):
    return s.page.evaluate("(id) => window.__TAURI__.core.invoke('record', { runId: id })", rid)


def replay_ok(s, rid):
    out = s.page.evaluate("(id) => window.__TAURI__.core.invoke('replay', { runId: id }).then((r) => r, (e) => ({ error: e }))", rid)
    return out, isinstance(out, dict) and not out.get("error") and out.get("verified", out.get("ok", True)) is not False


def run_and_wait(s, timeout=120):
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


def pad_fix(s):
    """The owner's case: a soft touchdown that misses the pad, fixed by a real new simulation."""
    open_mission(s, "off-the-pad")
    s.wait("document.querySelector('.pl-head [data-action=\"configure\"]')", 30, "change the conditions")
    s.page.click(".pl-head [data-action='configure']")
    s.wait("window.__studio.view() === 'lab' && document.querySelector('.lab-base')", 30, "lab")
    base_id = lab(s)["base"]
    base = record(s, base_id)
    failed = [r["id"] for r in base["requirements"] if r["status"] == "fail"]
    check("Off the pad: only R5 fails in the baseline", failed == ["R5_position"], ", ".join(failed))
    hinted = s.js("[...document.querySelectorAll('.lab-field.is-hint')].map((e) => e.dataset.param)")
    check("Off the pad: the lateral gain is among the listed parameters", "lateral_position_gain" in hinted, ", ".join(hinted))
    check("Off the pad: no requirement limit is suggested as a fix", not any(p in hinted for p in ("landing_zone_radius_m", "contact_vertical_speed_limit_mps")))
    s.shot("m17-lab-off-the-pad-baseline-dark")
    set_param(s, "lateral_position_gain", 0.12)
    exp_id = run_and_wait(s)
    exp = record(s, exp_id)
    r5 = next(r for r in exp["requirements"] if r["id"] == "R5_position")
    check("Off the pad: the new run lands on the pad", exp["outcome"]["status"] == "success" and r5["status"] == "pass", f"{exp['outcome']['label']}, R5 {r5['observed']}")
    check("Off the pad: the new run is a different, recomputed record", exp_id != base_id and exp["request"]["parameters"].get("lateral_position_gain") in (None, 0.12))
    s.shot("m17-lab-off-the-pad-fixed-dark")
    s.page.click(".lab-box [data-seeds='8']")
    s.wait("(() => { const l = window.__studio.lab(); return l && !l.busy && l.gen; })()", 240, "seed check")
    g = lab(s)["gen"]
    check("Off the pad: the fix is checked on 8 seeds and reported as counts", g["n"] == 8 and g["exp"] >= g["base"], json.dumps(g))
    s.shot("m17-lab-off-the-pad-seeds-dark")


def from_player(s):
    open_mission(s, "lying-altimeter")
    s.wait("document.querySelector('.pl-head [data-action=\"configure\"]')", 30, "change the conditions")
    shown = s.js("window.__studio.player()")
    base_id = shown["runs"][shown["active"]]
    s.page.click(".pl-head [data-action='configure']")
    s.wait("window.__studio.view() === 'lab' && window.__studio.lab() && document.querySelector('.lab-base')", 30, "lab")
    st = lab(s)
    check("Change the conditions opens the shown run as the Lab baseline", st["base"] == base_id, f"{st['base']} vs {base_id}")
    fails = s.js("[...document.querySelectorAll('.lab-req')].map((b) => b.querySelector('.lab-req-l').textContent)")
    check("The baseline lists its failed requirements with margins", len(fails) >= 1 and s.js("document.querySelectorAll('.lab-req .lab-mbar').length") >= 1, ", ".join(fails))
    hinted = s.js("[...document.querySelectorAll('.lab-field.is-hint')].map((e) => e.dataset.param)")
    check("Parameters the domain lists for the failure are highlighted", len(hinted) >= 1, ", ".join(hinted))
    check("Run experiment is disabled until something changes", s.js("document.getElementById('lab-run').disabled"))
    s.shot("m17-lab-baseline-dark")
    return base_id


def change_controller(s, base_id):
    base = record(s, base_id)
    s.page.select_option("#lab-ctl", "robust")
    time.sleep(0.3)
    check("One change is counted", "1 change" in s.js("document.querySelector('.lab-run-bar').innerText"))
    exp_id = run_and_wait(s)
    exp = record(s, exp_id)
    check("The experiment is a new run with its own record", exp_id != base_id and exp["request"]["controller"] == "robust" and exp["request"]["seed"] == base["request"]["seed"])
    check("The outcome changed through a new simulation", exp["outcome"]["status"] != base["outcome"]["status"], f"{base['outcome']['label']} -> {exp['outcome']['label']}")
    why = s.js("document.querySelector('.lab-why').innerText")
    check("The Lab says which requirements changed", "now meets" in why, why[:160])
    diff = s.js("document.querySelector('.lab-diff').innerText")
    check("The Lab lists what was changed", "Controller" in diff, diff.replace("\n", " ")[:160])
    out, ok = replay_ok(s, exp_id)
    check("The experiment replays by recomputation", ok, json.dumps(out)[:200])
    check("The baseline record is unchanged", json.dumps(record(s, base_id), sort_keys=True) == json.dumps(base, sort_keys=True))
    s.shot("m17-lab-experiment-dark")
    return exp_id


def seeds(s):
    s.page.click(".lab-box [data-seeds='8']")
    s.wait("(() => { const l = window.__studio.lab(); return l && !l.busy && l.gen; })()", 240, "seed check")
    g = lab(s)["gen"]
    check("The seed check runs both conditions on 8 development seeds", g["n"] == 8, json.dumps(g))
    check("The robust controller meets everything on more seeds than the baseline", g["exp"] > g["base"], json.dumps(g))
    txt = s.js("document.querySelector('.lab-gen').innerText")
    check("The seed check states counts with an interval", "95 % interval" in txt, txt.replace("\n", " ")[:200])
    s.shot("m17-lab-seeds-dark")
    return g


def sweep(s):
    s.page.select_option("#lab-sweep-param", "altimeter_residual_threshold_m")
    s.page.select_option(".lab-sweep-ctl select[aria-label='Number of values']", "5")
    s.page.click("#lab-sweep-run")
    s.wait("(() => { const l = window.__studio.lab(); return l && !l.busy && l.sweep; })()", 240, "sweep")
    rows = s.js("(() => { const b = document.getElementById('lab-sweep-run').closest('.lab-box'); return b.querySelectorAll('.lab-table tbody tr').length; })()")
    check("The sweep runs one simulation per value", lab(s)["sweep"] == 5 and rows >= 5, f"{lab(s)['sweep']} values, {rows} rows")
    check("The sweep draws the margin against the parameter", s.js("!!document.querySelector('.lab-chart')"))
    s.shot("m17-lab-sweep-dark")


def vehicle(s):
    s.page.select_option("#lab-scenario", "heavy-return-landing")
    time.sleep(0.3)
    exp_id = run_and_wait(s)
    exp = record(s, exp_id)
    check("A vehicle preset runs as an exploratory case", exp["request"]["scenario"] == "heavy-return-landing" and any(n.startswith("Exploratory case") for n in exp["notes"]))
    check("The Lab marks the experiment exploratory", s.js("!!document.querySelector('.lab-tag-exp')"))
    out, ok = replay_ok(s, exp_id)
    check("The vehicle preset replays by recomputation", ok, json.dumps(out)[:200])
    s.shot("m17-lab-vehicle-dark")
    return exp_id


def judging(s, base_id):
    s.page.click(".lab-run-bar .btn-quiet")  # Reset all
    time.sleep(0.3)
    s.js("document.querySelector('[data-param=\"landing_zone_radius_m\"]').closest('details').open = true")
    set_param(s, "landing_zone_radius_m", 30)
    exp_id = run_and_wait(s)
    base = record(s, base_id)
    exp = record(s, exp_id)
    same = all(c["values"] == next(x for x in exp["channels"] if x["id"] == c["id"])["values"] for c in base["channels"])
    check("A judging-only limit leaves every simulated channel identical", same)
    why = s.js("document.querySelector('.lab-why').innerText")
    check("The Lab says only the judgement moved", "only the judgement moved" in why, why[:200])


def ascent(s):
    """Multi-entity mission: the ascent plays in the player and its failure is fixed in the Lab."""
    open_mission(s, "to-orbit")
    s.wait("(() => { const p = window.__studio.player(); return p && p.renderer === 'ascent'; })()", 40, "ascent scene")
    time.sleep(1.0)
    shown = s.js("window.__studio.player()")
    rec = record(s, shown["runs"][shown["active"]])
    ents = [e["id"] for e in rec.get("entities", [])]
    check("Two stages to orbit: the record is vv-run.v2 with separate entities", rec["schema"] == "vv-run.v2" and len(ents) >= 2, ", ".join(ents))
    s.shot("m17-ascent-player-dark")
    s.page.click(".pl-views [data-view='control']")
    s.wait("document.querySelector('.mc')", 20, "flight console")
    time.sleep(1.0)
    check("Two stages to orbit: Flight console opens on the ascent", s.js("!!document.querySelector('.mc')") and not errors, "; ".join(errors)[:200])
    s.shot("m17-ascent-control-dark")
    s.page.click(".mc-back")
    s.wait("document.querySelector('.pl-head')", 10, "player")
    open_mission(s, "too-heavy")
    s.wait("document.querySelector('.pl-head [data-action=\"configure\"]')", 30, "change the conditions")
    s.page.click(".pl-head [data-action='configure']")
    s.wait("window.__studio.view() === 'lab' && document.querySelector('.lab-base')", 30, "lab")
    base = record(s, lab(s)["base"])
    check("One payload too many: the baseline does not reach orbit", base["outcome"]["status"] != "success", base["outcome"]["label"])
    set_param(s, "small_payload_kg", 300)
    exp_id = run_and_wait(s)
    exp = record(s, exp_id)
    check("One payload too many: a lighter payload reaches orbit in a new simulation", exp["outcome"]["status"] == "success", exp["outcome"]["label"])
    s.shot("m17-ascent-lab-dark")


def layout(s):
    s.resize(1024, 640)
    time.sleep(0.6)
    check("Lab at 1024x640 has no horizontal scroll", s.no_hscroll())
    check("Every visible control has a name", not s.unnamed_buttons(), json.dumps(s.unnamed_buttons())[:300])
    s.shot("m17-lab-1024x640-dark")
    s.resize(1440, 900)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=os.path.join(REPO, "desktop", "target", "release", "vv-studio.exe"))
    ap.add_argument("--domains", default=os.path.join(REPO, "desktop", "target", "release", "domains"))
    ap.add_argument("--environments", default=os.path.join(REPO, "desktop", "environments"))
    ap.add_argument("--shots", default=os.path.join(REPO, "docs", "images", "m17-studio"))
    ap.add_argument("--port", type=int, default=9247)
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
    env["VVLAB_LIBRARY"] = tempfile.mkdtemp(prefix="vv-m17-lib-")
    env["VVLAB_CONFIG"] = tempfile.mkdtemp(prefix="vv-m17-cfg-")
    env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"--remote-debugging-port={a.port}"
    proc = launch(exe, env, a.port)
    try:
        with sync_playwright() as pw:
            browser, s = session(pw, a.port, a.shots)
            try:
                pad_fix(s)
                base_id = from_player(s)
                change_controller(s, base_id)
                seeds(s)
                sweep(s)
                vehicle(s)
                judging(s, base_id)
                layout(s)
                if s.js("!!(window.__studio && document.querySelector('.nav-btn'))") and os.environ.get("VV_ASCENT", "1") == "1":
                    ascent(s)
            except Exception as e:  # noqa: BLE001
                check("Lab journeys completed", False, repr(e)[:300])
                try:
                    s.shot("m17-lab-failure")
                except Exception:  # noqa: BLE001
                    pass
            check("No page error or console error", not errors, "; ".join(errors)[:300])
            browser.close()
    finally:
        proc.kill()
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
