"""Build a read-only replay workbench (one self-contained HTML file) for an M6 run.

The page shows stored evidence only: per-tick positions and actions from
`events.json`, violations from `verification.json`, configured faults from
`actuator.json`, paired rows from `evidence.json` and verdicts from
`analysis.json`. Nothing is simulated or interpolated here.

Two validation tiers, kept apart in the page:

* integrity: artifact bytes match the sha256 values in `m4.json`, `m4.json`
  matches `evidence.json`, the event hash chain links, and run-level hashes agree;
* verified: `vv-lab replay-m4` recomputes the case with the given build and exits 0.

Only the second tier is called "verified". The output must sit outside
`<root>/run/`, because `vv-repair replay` rejects unexpected files there.

Exit status: 0 page written (problems are shown in the page), 1 the run root
cannot be read, 2 usage error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from adversarial_campaign import default_binary
from m6_report import CSS

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "vv-workbench.payload.v1"
EVIDENCE_SCHEMA = "vv-repair.evidence.v1"
MAX_JSON_BYTES = 64 * 1024 * 1024
REPLAY_TIMEOUT_SECONDS = 30
# Known library revisions, from docs/m4-results.md and docs/m6-controller-repair.md.
KNOWN_SOURCES = {
    "38039c255f6f60c8b1a5d50332c2280665df469a1a00ad43b06f5df47bf643cb": "M4/M5 library (main d491b4a)",
    "620f76031548075a66a2e4117956a29d1b63d846263b4aed224b74e2e2501f6b": "M6 library (commit efad24e, opt-in cancel_pending_on_fallback)",
}
ARTIFACT_KEYS = ("event_artifact", "report_artifact", "mission_artifact", "verification_artifact")


class WorkbenchError(RuntimeError):
    """The run root cannot be read or the output path is unsafe."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> tuple[Any, str | None]:
    """(data, problem); exactly one is None."""
    if not path.is_file():
        return None, f"{path.name} missing"
    if path.stat().st_size > MAX_JSON_BYTES:
        return None, f"{path.name} exceeds {MAX_JSON_BYTES} bytes"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        return None, f"{path.name} is not valid JSON: {error}"


def check(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def check_output(root: Path, output: Path) -> None:
    run = (root / "run").resolve()
    target = output.resolve()
    if target == run or run in target.parents:
        raise WorkbenchError(f"output {output} is inside {root / 'run'}; vv-repair replay would reject it")


# ---------------------------------------------------------------- paired rows


def recount(evidence: dict, candidate: str) -> tuple[list[dict], dict[str, dict[str, int]]]:
    """Broken pairs and per-suite fixed/broken counts, recomputed from the rows.

    Held-out split plus the shared no-fault control, as in the analysis.
    """
    baseline = evidence["experiment"]["baseline"]["id"]
    broken: list[dict] = []
    counts: dict[str, dict[str, int]] = {}
    for suite, by_config in evidence["results"].items():
        workloads = evidence["workloads"][suite]
        tally = counts.setdefault(suite, {"fixed": 0, "broken": 0})
        for sim_seed, base_rows in by_config[baseline].items():
            for index, (base, cand) in enumerate(zip(base_rows, by_config[candidate][sim_seed])):
                workload = workloads[index]
                if workload["split"] not in ("heldout", "control"):
                    continue
                if base["violations"] and not cand["violations"]:
                    tally["fixed"] += 1
                elif cand["violations"] and not base["violations"]:
                    tally["broken"] += 1
                    broken.append(
                        {
                            "suite": suite,
                            "sim_seed": sim_seed,
                            "workload": index,
                            "split": workload["split"],
                            "family": workload["family"],
                            "generator_seed": workload["seed"],
                            "draw": workload["draw"],
                            "atoms": workload["atoms"],
                            "baseline_violations": base["violations"],
                            "candidate_violations": cand["violations"],
                            "baseline_mission": base["mission"],
                            "candidate_mission": cand["mission"],
                        }
                    )
    return broken, counts


def candidate_view(cand: dict) -> dict[str, Any]:
    held = cand.get("summary", {}).get("heldout", {})
    keep = (
        "pairs",
        "fixed",
        "fixed_vacuous",
        "broken",
        "completion_lost",
        "completion_gained",
        "baseline_completed",
        "risk_difference_strict",
        "distance_increase_mm",
    )
    return {
        "id": cand["id"],
        "role": cand.get("role"),
        "overrides": cand.get("overrides", {}),
        "verdict": cand.get("verdict", {}),
        "gates": cand.get("gates", {}),
        "heldout": {k: held[k] for k in keep if k in held},
        "suites": {
            s: {k: b["heldout"].get(k) for k in ("fixed", "broken", "risk_difference_strict", "risk_difference", "mcnemar_p")}
            for s, b in cand.get("suites", {}).items()
        },
    }


# ---------------------------------------------------------------- one case


def chain_problem(events: list[dict]) -> str | None:
    previous = "0" * 64
    for event in events:
        if event.get("previous_hash") != previous:
            return f"event hash chain breaks at sequence {event.get('sequence')}"
        previous = event.get("hash")
    return None


def case_integrity(case_dir: Path, item: dict, source_sha256: str) -> tuple[list[str], dict | None]:
    problems: list[str] = []
    manifest, problem = read_json(case_dir / "m4.json")
    if problem:
        return [problem], None
    if sha256_file(case_dir / "m4.json") != item.get("m4_sha256"):
        problems.append("m4.json sha256 differs from evidence.json m4_sha256")
    if manifest.get("source_sha256") != source_sha256:
        problems.append(
            f"m4.json source_sha256 {str(manifest.get('source_sha256'))[:12]} differs from evidence source_sha256 {source_sha256[:12]}"
        )
    for key in ARTIFACT_KEYS:
        artifact = manifest.get(key) or {}
        name = str(artifact.get("path", ""))
        if not name or any(c in name for c in "/\\:") or name.startswith("."):
            problems.append(f"{key} has an unsafe or empty path")
            continue
        path = case_dir / name
        if not path.is_file():
            problems.append(f"{name} missing")
        elif (actual := sha256_file(path)) != artifact.get("sha256"):
            problems.append(f"{name} sha256 mismatch: manifest {str(artifact.get('sha256'))[:12]}, file {actual[:12]}")
    events, _ = read_json(case_dir / "events.json")
    if isinstance(events, dict) and isinstance(events.get("events"), list) and (broken := chain_problem(events["events"])):
        problems.append(broken)
    # The page draws geometry and fault windows from the hash-covered copies; the side files must agree.
    verification, _ = read_json(case_dir / "verification.json")
    for name, embedded in (
        ("scenario.json", events.get("scenario") if isinstance(events, dict) else None),
        ("actuator.json", verification.get("actuator_config") if isinstance(verification, dict) else None),
    ):
        side, problem = read_json(case_dir / name)
        if problem is None and embedded is not None and side != embedded:
            problems.append(f"{name} differs from the copy embedded in the hashed artifacts")
    return problems, manifest


def replay_check(binary: Path | None, m4_path: Path) -> dict[str, Any]:
    if binary is None:
        return {"status": "not_run", "detail": "no vv-lab binary given; nothing on this page is verified by replay"}
    if not binary.is_file():
        return {"status": "not_run", "detail": f"vv-lab binary not found: {binary.name}"}
    try:
        done = subprocess.run(
            [str(binary), "replay-m4", str(m4_path)],
            capture_output=True,
            text=True,
            timeout=REPLAY_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {"status": "failed", "rc": None, "stdout": "", "stderr": f"timed out after {REPLAY_TIMEOUT_SECONDS} s"}
    except OSError as error:
        return {"status": "failed", "rc": None, "stdout": "", "stderr": f"could not run vv-lab: {error}"}
    return {
        "status": "verified" if done.returncode == 0 else "failed",
        "rc": done.returncode,
        "stdout": done.stdout.strip()[-2000:],
        "stderr": done.stderr.strip().splitlines()[0] if done.stderr.strip() else "",
    }


def trace(case_dir: Path) -> dict[str, Any] | None:
    """Per-tick view built from recorded artifacts only; None without events.json."""
    events_doc, problem = read_json(case_dir / "events.json")
    if problem or not isinstance(events_doc, dict):
        return None
    ticks: list[dict] = []
    gps: dict[int, dict[str, bool]] = {}
    transitions, invariant_failures = [], []
    for event in events_doc.get("events", []):
        body, tick = event["event"], event["tick"]
        flags = gps.setdefault(tick, {"gps_dropped": False, "packet_lost": False})
        kind = body["kind"]
        if kind == "gps_sample" and body.get("dropped"):
            flags["gps_dropped"] = True
        elif kind == "packet_outcome" and body.get("delivered") is False:
            flags["packet_lost"] = True
        elif kind == "transition":
            transitions.append({k: body.get(k) for k in ("subsystem", "from", "to", "reason")} | {"tick": tick})
        elif kind == "invariant_check" and not body.get("passed"):
            invariant_failures.append({"tick": tick, "name": body.get("name"), "detail": body.get("detail")})
        elif kind == "tick_result":
            ticks.append(
                {
                    "tick": tick,
                    "truth_from": body["truth_from"],
                    "truth": body["truth_position"],
                    "observed": body.get("observed"),
                    "action": body.get("action"),
                    "heading": body.get("heading"),
                    "safety_state": body.get("safety_state"),
                    "mission_state": body.get("mission_state"),
                    "waypoint_index": body.get("waypoint_index"),
                    "event_sequence": event["sequence"],
                    "event_hash": event["hash"],
                }
            )
    for row in ticks:
        row |= gps.get(row["tick"], {"gps_dropped": False, "packet_lost": False})

    # Scenario and actuator configuration come from the copies inside hashed artifacts.
    scenario = events_doc.get("scenario") if isinstance(events_doc.get("scenario"), dict) else None
    verification, _ = read_json(case_dir / "verification.json")
    actuator = (verification or {}).get("actuator_config")
    mission, _ = read_json(case_dir / "mission.json")
    failures = {f["contract_id"]: f for f in (verification or {}).get("failures", []) if "contract_id" in f}
    contracts = []
    for c in (verification or {}).get("contract_results", []):
        # For a failure, the violated instance is in failures[]; contract_results keeps the first trigger ever.
        f = failures.get(c["contract_id"], {})
        contracts.append(
            {
                "id": c["contract_id"],
                "type": c.get("property_type"),
                "outcome": c.get("outcome"),
                "trigger_tick": f.get("first_trigger_tick") if f else c.get("first_trigger_tick"),
                "deadline_tick": f.get("applicable_deadline_tick") if f else c.get("deadline_tick"),
                "violation_tick": c.get("first_violation_tick"),
                "trigger_sequence": (f.get("trigger_command") or {}).get("event_sequence"),
                "violation_sequence": (f.get("violation_command") or {}).get("event_sequence"),
                "detail": f.get("detail"),
                "expected": f.get("expected_condition"),
                "actual": f.get("actual_condition"),
            }
        )
    # Actuator events recorded inside each failure window (the full actuator trace is only hashed).
    seen, actuator_events = set(), []
    for f in (verification or {}).get("failures", []):
        for item in f.get("fault_events", []):
            body = item.get("event", {})
            key = (body.get("kind"), body.get("tick"), body.get("source_command_tick"), item.get("observed_event_sequence"))
            if key in seen:
                continue
            seen.add(key)
            actuator_events.append(
                {k: body.get(k) for k in ("tick", "kind", "source_command_tick", "due_tick", "execution_tick")}
                | {k: item.get(k) for k in ("observed_event_sequence", "source_command_event_sequence")}
            )
    actuator_events.sort(key=lambda e: (e["tick"] or 0, e["observed_event_sequence"] or 0))
    # Requested vs realized action per tick, recorded only for ticks inside a failure window.
    actuation: dict[int, dict] = {}
    for f in (verification or {}).get("failures", []):
        for row in f.get("counterexample_ticks", []):
            entry = {k: row.get(k) for k in ("requested_action", "realized_action", "actuator_behavior")}
            previous = actuation.setdefault(row.get("tick"), entry)
            if {k: previous.get(k) for k in entry} != entry:
                previous["conflict"] = True
    for row in ticks:
        row["actuation"] = actuation.get(row["tick"])
    faults = [
        {
            "kind": f.get("kind"),
            "id": f.get("id"),
            "windows": f.get("windows", []),
            "delay_ticks": f.get("delay_ticks"),
            "probability_permille": f.get("probability_permille"),
            "source": "verification.json actuator_config (configured)",
        }
        for f in (actuator or {}).get("faults", [])
    ]
    geometry = None
    if scenario:
        geometry = {
            "bounds": scenario.get("bounds"),
            "restricted_zone": (scenario.get("restricted_zone") or {}).get("vertices", []),
            "waypoints": (scenario.get("mission") or {}).get("waypoints", []),
            "arrival_radius_mm": (scenario.get("mission") or {}).get("arrival_radius_mm"),
            "start": (scenario.get("vehicle") or {}).get("start"),
        }
    mission_keys = ("outcome", "reason", "completion_tick", "fallback_ticks", "distance_to_next_waypoint_mm")
    return {
        "seed": events_doc.get("seed"),
        "tick_ms": (scenario or {}).get("tick_ms"),
        "ticks": ticks,
        "transitions": transitions,
        "invariant_failures": invariant_failures,
        "contracts": contracts,
        "actuator_faults": faults,
        "actuator_events": actuator_events,
        "geometry": geometry,
        "mission": {k: (mission or {}).get(k) for k in mission_keys},
        "summary": (verification or {}).get("summary"),
    }


def case_view(root: Path, item: dict, source_sha256: str, binary: Path | None) -> dict[str, Any]:
    rel = str(item.get("case_dir", ""))
    case_dir = root / "run" / rel
    run = (root / "run").resolve()
    unsafe = not rel or ":" in rel or not case_dir.resolve().is_relative_to(run) or case_dir.resolve() == run
    problems, manifest = (["case_dir is unsafe"], None) if unsafe else case_integrity(case_dir, item, source_sha256)
    if manifest is None:
        replay = {"status": "not_run", "detail": "m4.json unreadable; replay skipped"}
    else:
        replay = replay_check(binary, case_dir / "m4.json")
    artifacts = {}
    if manifest:
        artifacts = {(manifest.get(k) or {}).get("path", k): (manifest.get(k) or {}).get("sha256") for k in ARTIFACT_KEYS}
    manifest_keys = ("controller_id", "source_sha256", "seed", "manifest_sha256", "provenance")
    return {
        "id": item["id"],
        "kind": "corpus" if item["id"].startswith("corpus/") else "introduced",
        "suite": item.get("suite"),
        "class": item.get("class"),
        "found_on": item.get("found_on"),
        "sim_seed": item.get("sim_seed"),
        "steps": item.get("steps"),
        "atoms": item.get("atoms", []),
        "replay": item.get("replay", {}),
        "case_dir": "run/" + rel,
        "m4_sha256": item.get("m4_sha256"),
        "manifest": {k: manifest.get(k) for k in manifest_keys} if manifest else None,
        "artifacts": artifacts,
        "integrity": {"problems": problems},
        "replay_check": replay,
        "trace": None if unsafe else trace(case_dir),
    }


# ---------------------------------------------------------------- whole run


def git_head() -> str | None:
    try:
        done = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout.strip() or None


def run_checks(evidence: dict, analysis: dict | None, summary: dict | None, payload: dict) -> None:
    checks = payload["checks"]
    source = evidence.get("source_sha256", "")
    experiment = evidence.get("experiment", {})
    checks.append(check("evidence schema", evidence.get("schema") == EVIDENCE_SCHEMA, str(evidence.get("schema"))))
    if summary is not None:
        checks.append(
            check(
                "evidence_sha256 matches summary.json",
                summary.get("evidence_sha256") == evidence.get("evidence_sha256"),
                f"summary {str(summary.get('evidence_sha256'))[:12]}, evidence {str(evidence.get('evidence_sha256'))[:12]}",
            )
        )
        if "source_sha256" in summary:
            checks.append(check("source_sha256 matches summary.json", summary["source_sha256"] == source, source[:12]))
    if analysis is None:
        return
    if analysis.get("acceptance") is not None:
        checks.append(
            check(
                "acceptance gates identical in evidence and analysis",
                analysis["acceptance"] == experiment.get("acceptance"),
                json.dumps(experiment.get("acceptance")),
            )
        )
    mismatches = []
    for cand in analysis.get("candidates", []):
        payload["candidates"].append(candidate_view(cand))
        broken, counts = recount(evidence, cand["id"])
        payload["broken_pairs"][cand["id"]] = broken
        for suite, tally in counts.items():
            held = cand.get("suites", {}).get(suite, {}).get("heldout", {})
            if (held.get("fixed"), held.get("broken")) != (tally["fixed"], tally["broken"]):
                mismatches.append(f"{cand['id']}/{suite}")
    checks.append(
        check(
            "broken pairs recounted from rows match analysis.json",
            not mismatches,
            "all candidates and suites" if not mismatches else "differs: " + ", ".join(mismatches),
        )
    )


def build_payload(root: Path, binary: Path | None) -> dict[str, Any]:
    root = Path(root)
    if not root.is_dir():
        raise WorkbenchError(f"run root {root} is not a directory")
    evidence, ev_problem = read_json(root / "run" / "evidence.json")
    analysis, an_problem = read_json(root / "analysis.json")
    summary, su_problem = read_json(root / "summary.json")
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "generated": {
            "utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "workbench_git_head": git_head(),
            "binary": binary.name if binary else None,
            "binary_sha256": sha256_file(binary) if binary and binary.is_file() else None,
        },
        "run": {"name": root.name},
        "checks": [
            check("evidence.json readable", ev_problem is None, ev_problem or "run/evidence.json"),
            check("analysis.json readable", an_problem is None, an_problem or "analysis.json"),
            check("summary.json readable", su_problem is None, su_problem or "summary.json"),
        ],
        "candidates": [],
        "broken_pairs": {},
        "cases": [],
    }
    if evidence is None:
        return payload
    source = evidence.get("source_sha256", "")
    experiment = evidence.get("experiment", {})
    payload["run"] |= {
        "experiment_name": experiment.get("name"),
        "evidence_sha256": evidence.get("evidence_sha256"),
        "experiment_sha256": evidence.get("experiment_sha256"),
        "source_sha256": source,
        "source_known_as": KNOWN_SOURCES.get(source, "unknown revision"),
        "baseline": experiment.get("baseline", {}).get("id"),
        "sim_seeds": experiment.get("sim_seeds"),
        "tuning_seeds": experiment.get("tuning_seeds"),
        "heldout_seeds": experiment.get("heldout_seeds"),
        "acceptance": experiment.get("acceptance"),
        "suites": {s.get("id"): s.get("description") for s in evidence.get("suites", [])},
    }
    run_checks(evidence, analysis, summary, payload)
    items = evidence.get("corpus", []) + evidence.get("introduced", [])
    payload["cases"] = [case_view(root, item, source, binary) for item in items]
    return payload


# ---------------------------------------------------------------- page


def _script_json(value: Any) -> str:
    """JSON safe inside a <script> element: no evidence string can close it."""
    text = json.dumps(value, sort_keys=True)
    return text.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")


def render(payload: dict[str, Any], focus_case: str | None = None, focus_candidate: str | None = None) -> str:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Replay workbench</title>
<style>{CSS}{WB_CSS}</style></head>
<body><main id="app"><noscript>This page needs JavaScript to draw the stored trace.</noscript></main>
<script type="application/json" id="payload">{_script_json(payload)}</script>
<script type="application/json" id="focus">{_script_json({"case": focus_case, "candidate": focus_candidate})}</script>
<script>{APP_JS}</script>
</body></html>
"""


def write_workbench(
    root: Path, output: Path, binary: Path | None, focus_case: str | None, focus_candidate: str | None = None
) -> dict:
    check_output(root, output)
    payload = build_payload(root, binary)
    output.write_text(render(payload, focus_case, focus_candidate), encoding="utf-8", newline="\n")
    return payload


WB_CSS = """
main{max-width:1200px}
.banner{border:2px solid var(--bad);border-radius:10px;padding:12px 16px;margin:12px 0}
.banner b.big{font-size:20px;color:var(--bad)}
.banner.acceptbox{border-color:var(--good)}.banner.acceptbox b.big{color:var(--good)}
.grid2{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px}
@media (max-width:820px){.grid2{grid-template-columns:minmax(0,1fr)}}
.controls{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:8px 0}
.controls label{display:flex;align-items:center;gap:6px;min-width:0;max-width:100%}
.controls select{min-width:0;max-width:100%;text-overflow:ellipsis}
button,select{font:inherit;font-size:14px;padding:6px 10px;border:1px solid var(--line);border-radius:8px;
background:var(--surface);color:var(--text);min-height:36px}
button:focus-visible,select:focus-visible,input:focus-visible{outline:2px solid var(--s1);outline-offset:2px}
input[type=range]{flex:1;min-width:140px}
.ok{color:var(--good)}.bad{color:var(--bad)}.warn{color:var(--warn)}
svg .lane-label{font-size:11px;fill:var(--text2)}
.cell-on{fill:var(--s2)}.cell-fb{fill:var(--warn)}.cell-move{fill:var(--s1)}.cell-viol{fill:var(--bad)}
.cursor{stroke:var(--text);stroke-width:2}
.zone{fill:var(--bad);fill-opacity:.12;stroke:var(--bad)}
.wp{fill:none;stroke:var(--good);stroke-width:2}
.seg{stroke:var(--s1);stroke-width:3;stroke-linecap:round}
.seg.fb{stroke:var(--s2);stroke-dasharray:6 4}
.stale{stroke:var(--text2);stroke-width:1;stroke-dasharray:3 3}
.heading{stroke:var(--text);stroke-width:2}
.zoombox{fill:none;stroke:var(--text2);stroke-width:1;stroke-dasharray:4 3}
.fbbg{fill:var(--warn);fill-opacity:.10}
svg .fbtext{fill:var(--warn);font-weight:700;font-size:12px}
svg .gpsx{fill:var(--s2);font-weight:700}
.ribbon{display:inline-block;font-weight:700;border:2px solid var(--text2);border-radius:6px;padding:2px 10px;margin:4px 0}
.chip{border-left:4px solid var(--warn);padding:4px 10px;background:var(--panel);overflow-wrap:anywhere}
.lede{max-width:80ch}
.truth{fill:var(--s1)}.obs{fill:none;stroke:var(--text2);stroke-width:2}
.tick-btn{cursor:pointer}.tick-btn:focus-visible{outline:2px solid var(--s1);outline-offset:1px}
svg.zoom{overflow:visible}
dl.kv{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:4px 12px;margin:0}
dl.kv dt{color:var(--muted)}dl.kv dd{margin:0;overflow-wrap:anywhere}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.4 ui-monospace,Consolas,monospace;margin:4px 0}
@media (max-width:480px){dl.kv{grid-template-columns:minmax(0,1fr)}dl.kv dt{margin-top:6px}}
"""

APP_JS = r"""
const P = JSON.parse(document.getElementById('payload').textContent);
const F = JSON.parse(document.getElementById('focus').textContent);
const app = document.getElementById('app');
function el(tag, attrs, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === 'class') n.className = v; else if (k.startsWith('on')) n.addEventListener(k.slice(2), v); else n.setAttribute(k, v);
  }
  for (const k of kids.flat()) if (k !== null && k !== undefined) n.append(k instanceof Node ? k : String(k));
  return n;
}
const SVGNS = 'http://www.w3.org/2000/svg';
function sv(tag, attrs, ...kids) {
  const n = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, v);
  for (const k of kids) n.append(k instanceof Node ? k : String(k));
  return n;
}
const code = t => el('code', {}, t);
const short = h => h ? String(h).slice(0, 12) + '…' : 'n/a';
const pt = p => p ? `(${p.x_mm}, ${p.y_mm})` : 'none';
const act = a => !a ? 'none' : (a.distance_mm === 0 ? 'hold (0 mm)' : `${a.heading || 'no heading'} ${a.distance_mm} mm`);
const moved = t => t.truth.x_mm !== t.truth_from.x_mm || t.truth.y_mm !== t.truth_from.y_mm;
const disp = t => Math.round(Math.hypot(t.truth.x_mm - t.truth_from.x_mm, t.truth.y_mm - t.truth_from.y_mm));
function table(head, rows) {
  return el('div', {class: 'scroll'}, el('table', {}, el('thead', {}, el('tr', {}, head.map(h => el('th', {}, h)))),
    el('tbody', {}, rows.map(r => el('tr', {}, r.map(c => el('td', {}, c)))))));
}
const badge = (text, cls) => el('span', {class: 'badge ' + cls}, text);

const state = {
  candidate: (P.candidates.find(c => c.id === F.candidate) || P.candidates.find(c => c.role !== 'control') || P.candidates[0] || {}).id,
  case: (P.cases.find(c => c.id === F.case) || P.cases[0] || {}).id,
  tick: null, timer: null,
};

function header() {
  const r = P.run;
  const failed = P.checks.filter(c => !c.ok);
  return el('section', {},
    el('p', {class: 'meta'}, 'V&V lab · replay workbench · read-only view of stored simulation evidence'),
    el('h1', {}, `Run ${r.name}${r.experiment_name ? ' (' + r.experiment_name + ')' : ''}`),
    el('p', {class: failed.length ? 'bad' : 'ok'}, failed.length
      ? `${failed.length} run-level check(s) FAILED. Do not trust the numbers below until they pass.`
      : `All ${P.checks.length} run-level checks passed.`),
    (() => {
      const bad = P.cases.filter(c => c.integrity.problems.length);
      const ver = P.cases.filter(c => !c.integrity.problems.length && c.replay_check.status === 'verified').length;
      const ok = !bad.length && ver === P.cases.length;
      return el('p', {class: ok ? 'ok' : 'bad'}, `Cases: ${ver} of ${P.cases.length} verified by vv-lab replay-m4` +
        (bad.length ? `; ${bad.length} with integrity problems: ${bad.map(c => c.id).join(', ')}` : '') + '.');
    })(),
    el('p', {class: 'meta'}, `Page built ${P.generated.utc} with ${P.generated.binary || 'no binary'} (sha256 ${short(P.generated.binary_sha256)}). The evidence files carry no run timestamp.`),
    el('details', {}, el('summary', {}, 'Run-level checks'),
      el('ul', {}, P.checks.map(c => el('li', {}, el('span', {class: c.ok ? 'ok' : 'bad'}, c.ok ? 'pass ' : 'FAIL '), c.name, ': ', code(c.detail))))));
}

function verdictPanel() {
  const cand = P.candidates.find(c => c.id === state.candidate);
  if (!cand) return el('p', {class: 'warn'}, 'analysis.json has no candidates.');
  const v = cand.verdict || {};
  const decision = (v.decision || 'unknown').toUpperCase();
  const pick = el('select', {'aria-label': 'Candidate', onchange: e => { state.candidate = e.target.value; draw(); }},
    P.candidates.map(c => {
      const o = el('option', {value: c.id}, `${c.id}${c.role === 'control' ? ' (control)' : ''}: ${(c.verdict.decision || '').toUpperCase()}`);
      if (c.id === state.candidate) o.selected = true;
      return o;
    }));
  const h = cand.heldout || {};
  const a = P.run.acceptance || {};
  const lostPm = h.baseline_completed ? (1000 * (h.completion_lost || 0) / h.baseline_completed).toFixed(1) : 'n/a';
  const rd = h.risk_difference_strict;
  const pp = x => (100 * x).toFixed(2);
  const shown = P.cases.find(c => c.id === state.case);
  const tickMs = ((shown && shown.trace) || {}).tick_ms;
  const overrides = Object.entries(cand.overrides || {}).map(([k, x]) => `${k} = ${x}`).join(', ') || 'no parameter overrides';
  // The reason comes from the failing gates; a note is added only when it names one of them.
  const failing = Object.entries(cand.gates || {}).filter(([, ok]) => !ok).map(([g]) => g);
  const note = (v.notes || []).find(n => failing.some(g => n.includes(g)));
  const reason = failing.length ? `failed gate${failing.length > 1 ? 's' : ''}: ${failing.join(', ')}${note ? '; ' + note : ''}` : ((v.notes || [])[0] || 'see notes');
  // Plain-language summary; every number is read from analysis.json or the trace.
  const lede = el('p', {class: 'lede'},
    `Simulated ground vehicle (2D integer kinematics${tickMs ? `, ${tickMs} ms ticks` : ''}). Tested change for ${cand.id}: ${overrides}. ` +
    `On ${h.pairs} held-out and control pairs it fixed ${h.fixed}${h.fixed_vacuous ? ` (${h.fixed_vacuous} of them vacuous)` : ''} and broke ${h.broken}. Decision: ${decision} (${reason}).` +
    (shown ? ` Below: the stored trace of one reduced counterexample, run on the ${String(shown.found_on).toUpperCase()} configuration.` : ''));
  const safetyBadge = (cand.gates || {}).safety && v.safety === 'regressed' ? 'safety regressed (suite level)' : 'safety ' + (v.safety || '?');
  return el('section', {},
    el('h2', {}, 'Verdict (from analysis.json)'),
    lede,
    el('div', {class: 'controls'}, el('label', {}, 'Candidate ', pick), el('span', {class: 'meta'}, `baseline: ${P.run.baseline}`)),
    el('div', {class: 'banner' + (v.decision === 'accept' ? ' acceptbox' : ''), role: 'status'},
      el('b', {class: 'big'}, `${cand.id}: ${decision}`), ' ',
      badge(safetyBadge, v.safety || ''), ' ', badge('progress ' + (v.progress || '?'), v.progress || ''),
      el('ul', {}, (v.notes || []).map(n => el('li', {}, n)))),
    el('div', {class: 'grid2'},
      el('div', {class: 'panel'}, el('b', {}, 'Fixed gates (registered in the experiment file)'),
        table(['gate', 'result'], Object.entries(cand.gates || {}).map(([g, ok]) => [code(g === 'safety' ? 'safety (pooled strict RD)' : g), el('span', {class: ok ? 'ok' : 'bad'}, ok ? 'pass' : 'FAIL')])),
        el('p', {class: 'meta'}, `alpha ${a.alpha_permille}‰; completion loss ≤ ${a.max_completion_loss_permille} per 1000 baseline completions; mean distance increase ≤ ${a.max_mean_distance_increase_mm} mm; ≥ ${a.min_heldout_pairs} held-out pairs per suite.`)),
      el('div', {class: 'panel'}, el('b', {}, 'Held-out and control pairs: safety and completion'),
        el('dl', {class: 'kv'},
          el('dt', {}, 'pairs'), el('dd', {}, h.pairs),
          el('dt', {}, 'fixed (of which vacuous) / broken'), el('dd', {}, `${h.fixed} (${h.fixed_vacuous ?? 'n/a'}) / ${h.broken}`),
          el('dt', {}, 'strict risk difference'), el('dd', {}, rd ? `${pp(rd.estimate)} pp [${pp(rd.low)}; ${pp(rd.high)}]` : 'n/a'),
          el('dt', {}, 'missions lost / gained'), el('dd', {}, `${h.completion_lost} / ${h.completion_gained} of ${h.baseline_completed} baseline completions (${lostPm} per 1000)`),
          el('dt', {}, 'mean distance increase'), el('dd', {}, h.distance_increase_mm ? `${h.distance_increase_mm.mean.toFixed(1)} mm` : 'n/a')),
        table(['suite', 'fixed', 'broken', 'strict RD [95% CI]', 'exact p'], Object.entries(cand.suites).map(([s, b]) => {
          const r = b.risk_difference_strict, low = b.risk_difference && b.risk_difference.low;
          const failsGate = low != null && low > 0;
          return [code(s), b.fixed, b.broken,
            el('span', {class: failsGate ? 'bad' : ''}, (r ? `${pp(r.estimate)} pp [${pp(r.low)}; ${pp(r.high)}]` : 'n/a') + (failsGate ? ' (fails gate)' : '')),
            b.mcnemar_p == null ? 'n/a' : (b.mcnemar_p < 1e-6 ? '<1e-6' : b.mcnemar_p.toPrecision(3))];
        })),
        el('p', {class: 'meta'}, 'no_suite_regression fails when a suite\'s non-strict risk-difference lower bound is above 0 (marked "fails gate"). The aggregate can improve while one suite regresses.'))));
}

function brokenPanel() {
  const rows = P.broken_pairs[state.candidate] || [];
  return el('section', {},
    el('h2', {}, `Pairs broken by ${state.candidate} (${rows.length})`),
    el('p', {}, 'Baseline row clean, candidate row violated, on held-out or control workloads; recounted from evidence.json rows. ',
      el('b', {}, 'No per-tick trace is stored for these pairs'), '; only the reduced cases above have traces.'),
    rows.length
      ? table(['suite', 'sim seed', 'workload', 'family', 'generator seed / draw', 'candidate violations', 'mission (baseline → candidate)'],
        rows.map(r => [code(r.suite), r.sim_seed, r.workload, r.family, `${r.generator_seed ?? 'none'} / ${r.draw}`,
          el('span', {}, r.candidate_violations.map(v => el('div', {}, code(v)))), `${r.baseline_mission} → ${r.candidate_mission}`]))
      : el('p', {class: 'meta'}, 'None.'));
}

function caseStatus(c) {
  const r = c.replay_check;
  if (c.integrity.problems.length) return el('span', {class: 'bad'}, 'INTEGRITY PROBLEMS: ' + c.integrity.problems.join('; '));
  if (r.status === 'verified') return el('span', {class: 'ok'}, 'Verified by recomputation: vv-lab replay-m4 re-ran this case with the build below and exited 0. Integrity: file hashes also match.');
  if (r.status === 'failed') return el('span', {class: 'bad'}, 'Replay FAILED: ' + (r.stderr || 'exit ' + r.rc));
  return el('span', {class: 'warn'}, 'Not verified by replay (' + (r.detail || 'not run') + '). File hashes match.');
}

const HEADING = {east: [1, 0], west: [-1, 0], north: [0, 1], south: [0, -1]};

// Bounding box of the recorded positions plus the waypoints and start, padded.
function dataBox(t) {
  const g = t.geometry;
  const pts = t.ticks.flatMap(k => [k.truth_from, k.truth, k.observed && k.observed.position].filter(Boolean));
  if (g) { pts.push(...g.waypoints); if (g.start) pts.push(g.start); }
  const xs = pts.map(p => p.x_mm), ys = pts.map(p => p.y_mm), pad = 600;
  const box = {x0: Math.min(...xs) - pad, y0: Math.min(...ys) - pad, x1: Math.max(...xs) + pad, y1: Math.max(...ys) + pad};
  // Keep the view at least 0.4 as tall as wide (and vice versa) so labels fit; this only adds empty margin.
  const w = box.x1 - box.x0, h = box.y1 - box.y0;
  if (h < 0.4 * w) { const e = (0.4 * w - h) / 2; box.y0 -= e; box.y1 += e; }
  if (w < 0.4 * h) { const e = (0.4 * h - w) / 2; box.x0 -= e; box.x1 += e; }
  return box;
}

// mode 'arena': the whole recorded world (bounds, zone, waypoints) with the zoom box; mode 'zoom': the data box.
function mapSvg(t, upto, mode) {
  const g = t.geometry, b = g && g.bounds, box = dataBox(t);
  const v = mode === 'arena' && b ? {x0: b.min_x_mm, y0: b.min_y_mm, x1: b.max_x_mm, y1: b.max_y_mm} : box;
  const spanX = v.x1 - v.x0, spanY = v.y1 - v.y0;
  const s = mode === 'arena' ? Math.min(360 / spanX, 360 / spanY) : Math.min(400 / spanX, 200 / spanY);
  const W = spanX * s, H = spanY * s;
  const X = p => ((p.x_mm - v.x0) * s).toFixed(1), Y = p => (H - (p.y_mm - v.y0) * s).toFixed(1);
  const cur = t.ticks.find(k => k.tick === upto);
  const label = mode === 'arena'
    ? `Arena ${spanX / 1000} by ${spanY / 1000} m: start, waypoint, restricted zone and recorded path up to tick ${upto}`
    : `Zoomed view at tick ${upto}: true position ${cur ? pt(cur.truth) : 'none'}, observation ${cur && cur.observed ? pt(cur.observed.position) : 'none'}`;
  const svg = sv('svg', {viewBox: `0 0 ${W.toFixed(0)} ${H.toFixed(0)}`, role: 'img', 'aria-label': label,
    class: mode === 'arena' ? 'arena' : 'zoom', style: `max-width:${Math.ceil(W)}px`});
  const fb = cur && cur.safety_state === 'fallback';
  svg.append(sv('rect', {x: 0, y: 0, width: W, height: H, class: fb && mode !== 'arena' ? 'fbbg' : '', fill: fb && mode !== 'arena' ? '' : 'none', stroke: 'var(--line)'}));
  if (g && g.restricted_zone.length) {
    svg.append(sv('polygon', {class: 'zone', points: g.restricted_zone.map(p => `${X(p)},${Y(p)}`).join(' ')}));
    const z = g.restricted_zone[0];
    if (mode === 'arena') svg.append(sv('text', {x: +X(z) + 4, y: +Y(z) - 6, class: 'axis'}, 'restricted zone'));
  }
  if (g) for (const w of g.waypoints) {
    svg.append(sv('circle', {class: 'wp', cx: X(w), cy: Y(w), r: Math.max(4, (g.arrival_radius_mm || 0) * s)}));
    svg.append(sv('text', {x: +X(w) - 24, y: +Y(w) - 10, class: 'axis'}, 'waypoint'));
  }
  if (g && g.start) svg.append(sv('text', {x: +X(g.start) - 12, y: +Y(g.start) + 18, class: 'axis'}, 'start'));
  if (mode === 'arena') {
    svg.append(sv('rect', {class: 'zoombox', x: X({x_mm: box.x0}), y: Y({y_mm: box.y1}), width: ((box.x1 - box.x0) * s).toFixed(1), height: ((box.y1 - box.y0) * s).toFixed(1)}));
    svg.append(sv('text', {x: 6, y: H - 6, class: 'axis'}, `${spanX / 1000} m wide; dashed box = zoomed view; y up`));
  }
  for (const k of t.ticks.filter(k => k.tick <= upto))
    if (moved(k)) svg.append(sv('line', {class: 'seg' + (k.safety_state === 'fallback' ? ' fb' : ''), x1: X(k.truth_from), y1: Y(k.truth_from), x2: X(k.truth), y2: Y(k.truth)}));
  if (cur) {
    const ob = cur.observed && cur.observed.position;
    if (ob && mode !== 'arena') {
      if (ob.x_mm !== cur.truth.x_mm || ob.y_mm !== cur.truth.y_mm)
        svg.append(sv('line', {class: 'stale', x1: X(ob), y1: Y(ob), x2: X(cur.truth), y2: Y(cur.truth)}));
      svg.append(sv('rect', {class: 'obs', x: +X(ob) - 6, y: +Y(ob) - 6, width: 12, height: 12}));
      svg.append(sv('text', {x: +X(ob) - 20, y: +Y(ob) + 22, class: 'axis'}, `observed (sample tick ${cur.observed.sample_tick})`));
    }
    const d = HEADING[cur.heading];
    if (d && mode !== 'arena') svg.append(sv('line', {class: 'heading', x1: X(cur.truth), y1: Y(cur.truth), x2: (+X(cur.truth) + d[0] * 22).toFixed(1), y2: (+Y(cur.truth) - d[1] * 22).toFixed(1)}));
    svg.append(sv('circle', {class: 'truth', cx: X(cur.truth), cy: Y(cur.truth), r: mode === 'arena' ? 5 : 7}));
    if (mode !== 'arena') {
      svg.append(sv('text', {x: +X(cur.truth) - 10, y: +Y(cur.truth) - 14, class: 'lab'}, 'true'));
      if (cur.gps_dropped) svg.append(sv('text', {x: +X(cur.truth) + 6, y: +Y(cur.truth) + 36, class: 'gpsx'}, '× GPS sample dropped'));
      if (fb) svg.append(sv('text', {x: 8, y: 16, class: 'fbtext'}, 'FALLBACK'));
      svg.append(sv('text', {x: 6, y: H - 6, class: 'axis'}, `view ${Math.round(spanX)} mm wide; y up`));
    }
  }
  return svg;
}

function timelineSvg(t, upto, onPick) {
  const n = t.ticks.length, L = 176, cw = Math.max(18, Math.min(44, 600 / Math.max(n, 1))), W = L + n * cw + 4;
  const violTicks = new Set([...t.contracts.filter(c => c.outcome === 'FAIL').map(c => c.violation_tick), ...t.invariant_failures.map(f => f.tick)]);
  const inFault = tk => t.actuator_faults.some(f => f.windows.some(w => tk >= w.start_tick && tk <= w.end_tick));
  const actTicks = new Set(t.actuator_events.filter(e => e.kind !== 'fault_window_active').map(e => e.tick));
  const lanes = [
    ['fallback state', k => k.safety_state === 'fallback', 'cell-fb'],
    ['GPS sample dropped', k => k.gps_dropped, 'cell-on'],
    ['packet lost', k => k.packet_lost, 'cell-on'],
    ['actuator window (configured)*', k => inFault(k.tick), 'cell-on'],
    ['actuator event (recorded)', k => actTicks.has(k.tick), 'cell-on'],
    ['commanded move', k => k.action && k.action.distance_mm > 0, 'cell-move'],
    ['vehicle moved', k => moved(k), 'cell-move'],
    ['violation', k => violTicks.has(k.tick), 'cell-viol'],
  ];
  const H = 20 + lanes.length * 22;
  const svg = sv('svg', {viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': 'Per-tick timeline of recorded states, faults and violations', style: `min-width:${Math.min(W, 560)}px;max-width:${Math.max(W, 560)}px`});
  t.ticks.forEach((k, i) => {
    const x = L + i * cw;
    svg.append(sv('text', {x: x + cw / 2 - 4, y: 12, class: 'axis'}, k.tick));
    lanes.forEach(([label, on, cls], j) => {
      const text = `tick ${k.tick}: ${label} ${on(k) ? 'yes' : 'no'}`;
      const r = sv('rect', {x: x + 1, y: 18 + j * 22, width: cw - 2, height: 18, rx: 3, class: (on(k) ? cls : '') + ' tick-btn',
        fill: on(k) ? '' : 'var(--surface)', tabindex: j === 0 ? 0 : -1, role: 'button', 'aria-label': text, 'data-fid': `cell-${k.tick}-${j}`});
      r.addEventListener('click', () => onPick(k.tick));
      r.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onPick(k.tick); } });
      r.append(sv('title', {}, text));
      svg.append(r);
    });
  });
  lanes.forEach(([label], j) => svg.append(sv('text', {x: 0, y: 31 + j * 22, class: 'lane-label'}, label)));
  const ci = t.ticks.findIndex(k => k.tick === upto);
  if (ci >= 0) svg.append(sv('line', {class: 'cursor', x1: L + ci * cw + cw / 2, x2: L + ci * cw + cw / 2, y1: 14, y2: H}));
  return svg;
}

function configTable(c) {
  return el('div', {class: 'panel'}, el('b', {}, 'Same reduced case replayed on every configuration (evidence.json)'),
    table(['configuration', 'status', 'violations', 'mission'], Object.entries(c.replay).map(([k, r]) => [code(k),
      el('span', {class: 'st st-' + r.status}, r.status), el('span', {}, (r.violations || []).map(v => el('div', {}, code(v)))), r.mission])),
    el('p', {class: 'meta'}, `"resolved" refers only to this case's own class (${c.class}); a configuration can resolve it and still violate other contracts, listed in the same row. No per-tick trace is stored for these rows.`));
}

function provenance(c) {
  const r = P.run, g = P.generated;
  return el('div', {class: 'panel'}, el('b', {}, 'Provenance and reproduction'),
    el('dl', {class: 'kv'},
      el('dt', {}, 'case directory'), el('dd', {}, code(`runs/${r.name}/${c.case_dir}`)),
      el('dt', {}, 'm4.json sha256'), el('dd', {}, code(c.m4_sha256 || 'n/a')),
      ...Object.entries(c.artifacts).flatMap(([n, h]) => [el('dt', {}, n), el('dd', {}, code(h || 'n/a'))]),
      el('dt', {}, 'library source_sha256'), el('dd', {}, code(r.source_sha256 || 'n/a'), ` (${r.source_known_as})`),
      el('dt', {}, 'evidence_sha256'), el('dd', {}, code(r.evidence_sha256 || 'n/a')),
      el('dt', {}, 'experiment_sha256'), el('dd', {}, code(r.experiment_sha256 || 'n/a')),
      el('dt', {}, 'seeds'), el('dd', {}, `simulation ${JSON.stringify(r.sim_seeds)}, tuning ${JSON.stringify(r.tuning_seeds)}, held-out ${JSON.stringify(r.heldout_seeds)}`),
      el('dt', {}, 'replay this case'), el('dd', {}, code(`target/release/vv-lab replay-m4 runs/${r.name}/${c.case_dir}/m4.json`)),
      el('dt', {}, 'regenerate the run'), el('dd', {}, code(`target/release/vv-repair replay runs/${r.name}/run`)),
      el('dt', {}, 'replay output'), el('dd', {}, el('pre', {}, c.replay_check.stdout || c.replay_check.stderr || c.replay_check.detail || '')),
      el('dt', {}, 'page built'), el('dd', {}, `${g.utc}, workbench commit ${short(g.workbench_git_head)}, binary ${g.binary || 'none'} sha256 ${short(g.binary_sha256)}`)));
}

// One-paragraph account built only from recorded fields of this trace.
function story(t, verified) {
  const parts = [];
  for (const x of t.transitions) if (x.subsystem === 'safety') parts.push(`tick ${x.tick}: safety ${x.from} → ${x.to} (${x.reason})`);
  const dropped = t.ticks.filter(k => k.gps_dropped).map(k => k.tick);
  if (dropped.length) parts.push(`GPS samples dropped at ticks ${dropped.join(', ')}`);
  for (const e of t.actuator_events) if (e.kind !== 'fault_window_active')
    parts.push(`tick ${e.tick}: actuator ${e.kind.replaceAll('_', ' ')} (command from tick ${e.source_command_tick}` +
      (e.due_tick != null ? `, due tick ${e.due_tick}` : '') + `; events.json seq ${e.source_command_event_sequence} → ${e.observed_event_sequence})`);
  for (const k of t.ticks) if (k.safety_state === 'fallback' && moved(k))
    parts.push(`tick ${k.tick}: true position moved ${disp(k)} mm in fallback while the controller commanded ${act(k.action)}`);
  const failed = t.contracts.filter(x => x.outcome === 'FAIL').map(x => `${x.id} (tick ${x.violation_tick})`)
    .concat(t.invariant_failures.map(f => `invariant ${f.name} (tick ${f.tick})`));
  if (failed.length) parts.push('violated: ' + failed.join(', '));
  parts.push(`mission ${t.mission.outcome}`);
  return el('div', {class: 'panel'}, verified
      ? el('b', {}, 'What the stored trace shows')
      : el('b', {class: 'bad'}, 'What the files contain. NOT VERIFIED: integrity or replay failed, so this trace is not evidence.'),
    el('ol', {}, parts.map(p => el('li', {}, p))),
    el('p', {class: 'meta'}, 'Each line is computed only from transitions, tick_result and verification records of this case.'));
}

// Scenario picker: cases grouped by suite, labelled with the suite description recorded in evidence.json.
function casePicker() {
  const suites = [...new Set(P.cases.map(x => x.suite))];
  return el('select', {'aria-label': 'Scenario and counterexample', onchange: e => { state.case = e.target.value; state.tick = null; draw(); }},
    suites.map(s => el('optgroup', {label: `${s}: ${(P.run.suites || {})[s] || 'no description recorded'}`},
      P.cases.filter(x => x.suite === s).map(x => {
        const o = el('option', {value: x.id}, `${x.id.split('/').slice(-1)[0]} · ${x.class} (${x.steps} ticks)`);
        if (x.id === state.case) o.selected = true;
        return o;
      }))));
}

function candidateChip(c) {
  const r = c.replay[state.candidate];
  if (!r || c.found_on === state.candidate) return null;
  const others = (r.violations || []).filter(v => v !== c.class);
  return el('p', {class: 'chip'}, el('b', {}, `Candidate ${state.candidate} on this case: `),
    `${r.status} for the case's own class` + (others.length ? `; still violates ${others.join(', ')}` : '; no other violation listed') +
    `; mission ${r.mission}. No candidate trace is stored; this summary row is all the evidence holds for it.`);
}

function casePanel() {
  const c = P.cases.find(x => x.id === state.case);
  const head = el('div', {}, el('h2', {}, 'Stored counterexample trace'), el('div', {class: 'controls'}, el('label', {}, 'Scenario ', casePicker())));
  if (!c) return el('section', {}, head, el('p', {}, 'No cases in evidence.json.'));
  head.append(el('p', {class: 'meta'}, `Scenario ${c.suite}: ${(P.run.suites || {})[c.suite] || 'no description recorded'}`),
    el('p', {}, caseStatus(c)),
    el('p', {class: 'ribbon'}, `Trace shown: ${String(c.found_on).toUpperCase()} run (controller ${c.manifest ? c.manifest.controller_id : 'unknown'})`),
    candidateChip(c),
    c.found_on !== state.candidate ? el('p', {class: 'meta'},
      'The candidate verdict rests on the paired campaign rows, not on this trace; see the broken pairs section.') : null,
    el('p', {class: 'meta'}, `Class ${c.class}; suite ${c.suite}; simulation seed ${c.sim_seed}; ${c.steps} ticks; atoms beyond the suite base: ${c.atoms.length ? c.atoms.map(a => a.kind).join(', ') : 'none'}. The trace is the reduced case run under configuration `, code(c.found_on),
      ` (controller `, code(c.manifest ? c.manifest.controller_id : '?'), '). Other configurations have status rows only.'));
  const t = c.trace;
  if (!t || !t.ticks.length) {
    head.append(el('p', {class: 'bad'}, 'No trace: events.json is missing or unreadable. Nothing is drawn rather than guessing.'));
    return el('section', {}, head, configTable(c), provenance(c));
  }
  const ticks = t.ticks.map(k => k.tick);
  const failTicks = t.contracts.filter(x => x.outcome === 'FAIL').map(x => x.violation_tick)
    .concat(t.invariant_failures.map(f => f.tick)).filter(x => x != null);
  if (!ticks.includes(state.tick)) state.tick = failTicks.length ? Math.min(...failTicks) : ticks[0];
  head.append(story(t, !c.integrity.problems.length && c.replay_check.status === 'verified'));
  // Controls live outside the re-rendered view, so keyboard focus survives every tick change.
  const ui = {t, ticks, view: el('div', {id: 'trace-view'}), label: el('b', {id: 'tick-label'}),
    play: el('button', {'aria-pressed': 'false', onclick: () => (state.timer ? stop() : play())}, 'play')};
  ui.slider = el('input', {type: 'range', min: 0, max: ticks.length - 1, 'aria-label': 'Tick', 'aria-describedby': 'tick-label',
    oninput: e => setTick(ticks[+e.target.value])});
  state.ui = ui;
  const controls = el('div', {class: 'controls'},
    el('button', {onclick: () => stepBy(-1)}, '◀ step'), ui.play, el('button', {onclick: () => stepBy(1)}, 'step ▶'), ui.slider, ui.label);
  renderTrace();
  const legend = el('p', {class: 'meta'}, 'Arena: the recorded world (bounds, restricted zone, start, waypoint) from the scenario embedded in events.json. Zoomed view: blue segments are recorded per-tick displacements (truth_from → truth_position in tick_result), dashed orange while in fallback; filled dot = true position at this tick with its recorded heading; hollow square = observation the controller used; the thin dashed line joins those two recorded points. Steps are discrete; nothing is interpolated between ticks. *The configured lane shows the fault window from verification.json actuator_config. The recorded lane and the realized action come from verification.json failures[]; the complete actuator trace is stored only as a hash (actuator_trace_sha256).');
  const viol = t.contracts.filter(x => x.outcome !== 'PASS');
  const sum = t.summary;
  const violations = el('div', {class: 'panel'},
    el('b', {}, `Contract results recorded in verification.json (${sum ? `${sum.contracts_failed} failed, ${sum.contracts_inconclusive} inconclusive; safety ${sum.safety_status}; mission ${sum.mission_outcome}` : 'summary missing'})`),
    table(['property', 'outcome', 'trigger → deadline → violation tick', 'expected / actual (recorded text)'],
      viol.map(x => [el('button', {onclick: () => x.violation_tick && setTick(x.violation_tick)}, x.id), el('span', {class: x.outcome === 'FAIL' ? 'bad' : 'warn'}, x.outcome),
        el('span', {}, `${x.trigger_tick ?? 'none'} → ${x.deadline_tick ?? 'none'} → ${x.violation_tick ?? 'none'}`,
          x.trigger_sequence != null || x.violation_sequence != null ? el('div', {class: 'meta'}, `event seq ${x.trigger_sequence ?? 'none'} → ${x.violation_sequence ?? 'none'}`) : null,
          x.detail ? el('div', {class: 'meta'}, x.detail) : null),
        x.expected ? el('div', {}, el('pre', {}, 'expected: ' + x.expected), el('pre', {}, 'actual: ' + x.actual)) : ''])
      .concat(t.invariant_failures.map(f => [el('button', {onclick: () => setTick(f.tick)}, 'invariant ' + f.name), el('span', {class: 'bad'}, 'FAIL'), `tick ${f.tick}`, f.detail || '']))),
    el('p', {class: 'meta'}, `Transitions: ${t.transitions.map(x => `tick ${x.tick} ${x.subsystem} ${x.from} → ${x.to} (${x.reason})`).join('; ') || 'none'}. Mission: ${t.mission.outcome}${t.mission.reason ? ' (' + t.mission.reason + ')' : ''}, ${t.mission.distance_to_next_waypoint_mm} mm to the waypoint.`));
  return el('section', {}, head, controls, ui.view, legend, violations, configTable(c), provenance(c));
}

function tickCard(t, k) {
  const firing = t.contracts.filter(x => x.outcome === 'FAIL' && x.violation_tick === k.tick).map(x => x.id)
    .concat(t.invariant_failures.filter(f => f.tick === k.tick).map(f => 'invariant ' + f.name));
  const ob = k.observed, a = k.actuation;
  const none = 'not recorded for this tick (outside the failure windows)';
  return el('dl', {class: 'kv'},
    el('dt', {}, 'safety / mission'), el('dd', {}, `${k.safety_state} / ${k.mission_state}`),
    el('dt', {}, 'commanded (controller)'), el('dd', {}, act(k.action)),
    el('dt', {}, 'realized (actuator)'), el('dd', {}, a ? act(a.realized_action) + (a.conflict ? ' (conflicting records)' : '') : none),
    el('dt', {}, 'actuator behaviour'), el('dd', {}, a ? String(a.actuator_behavior).replaceAll('_', ' ') : none),
    el('dt', {}, 'true position (truth_from → truth_position)'), el('dd', {}, `${pt(k.truth_from)} → ${pt(k.truth)} (${disp(k)} mm)`),
    el('dt', {}, 'observation used'), el('dd', {}, ob ? `${pt(ob.position)}, sample tick ${ob.sample_tick}, age ${ob.age_ticks}, confidence ${ob.confidence_permille}‰, ${ob.fresh ? 'fresh' : 'stale'}` : 'none'),
    el('dt', {}, 'GPS / packet'), el('dd', {}, `${k.gps_dropped ? 'sample dropped' : 'no drop recorded'} / ${k.packet_lost ? 'lost' : 'no loss recorded'}`),
    el('dt', {}, 'violations at this tick'), el('dd', {class: firing.length ? 'bad' : ''}, firing.length ? firing.join(', ') : 'none'),
    el('dt', {}, 'raw event'), el('dd', {}, code(`events.json sequence ${k.event_sequence}, hash ${short(k.event_hash)}`)));
}

// Re-render only the trace view and refresh the persistent controls in place.
function renderTrace() {
  const ui = state.ui;
  if (!ui) return;
  const {t, ticks} = ui;
  const idx = ticks.indexOf(state.tick), k = t.ticks[idx];
  if (!k) return;
  const fid = document.activeElement && document.activeElement.getAttribute && document.activeElement.getAttribute('data-fid');
  ui.slider.value = idx;
  ui.label.textContent = `tick ${state.tick} of ${ticks[ticks.length - 1]}`;
  ui.slider.setAttribute('aria-valuetext', `tick ${state.tick} of ${ticks[ticks.length - 1]}: ${k.safety_state}, commanded ${act(k.action)}, moved ${disp(k)} mm`);
  ui.play.textContent = state.timer ? 'pause' : 'play';
  ui.play.setAttribute('aria-pressed', state.timer ? 'true' : 'false');
  ui.view.replaceChildren(
    el('div', {class: 'grid2'},
      el('div', {class: 'panel'}, el('b', {}, 'Arena (recorded scenario)'), mapSvg(t, state.tick, 'arena')),
      el('div', {class: 'panel'}, el('b', {}, 'Zoomed view'), mapSvg(t, state.tick, 'zoom'), tickCard(t, k))),
    el('div', {class: 'panel scroll'}, timelineSvg(t, state.tick, setTick)));
  if (fid) { const n = ui.view.querySelector(`[data-fid="${fid}"]`); if (n) n.focus(); }
}

function setTick(tk) { state.tick = tk; renderTrace(); }
function stepBy(d) {
  const ticks = state.ui.ticks, i = ticks.indexOf(state.tick);
  setTick(ticks[Math.max(0, Math.min(ticks.length - 1, i + d))]);
}

function limits() {
  return el('section', {}, el('h2', {}, 'Limitations'), el('ul', {},
    el('li', {}, 'Simulation evidence from an integer 2D kinematic model. It is not evidence about a real vehicle. Nothing here ran in PX4/SITL; the separate PX4 Gate 1A track and its status are not represented here.'),
    el('li', {}, 'Per-tick traces exist only for reduced counterexamples (corpus and introduced cases), each run under one configuration. Paired campaign rows have no stored trace.'),
    el('li', {}, '"Verified" means vv-lab replay-m4 recomputed the case with the build named in the provenance. Integrity checks alone only prove the files match their recorded hashes.'),
    el('li', {}, 'The complete actuator event trace is stored only as a hash; only the actuator events inside each failure window are recorded, and the configured window is configuration, not observation. The story lines are computed from recorded fields (for example, displacement is the distance between truth_from and truth_position).')));
}

// Play advances one recorded tick at a time; there is no tween, so reduced-motion users see the same discrete steps.
function stop() { if (state.timer) clearInterval(state.timer); state.timer = null; renderTrace(); }
function play() {
  const ticks = state.ui.ticks;
  if (state.timer) clearInterval(state.timer);
  if (ticks.indexOf(state.tick) >= ticks.length - 1) state.tick = ticks[0];
  state.timer = setInterval(() => {
    const i = ticks.indexOf(state.tick);
    if (i >= ticks.length - 1) { stop(); return; }
    setTick(ticks[i + 1]);
  }, 700);
  renderTrace();
}
function draw() {
  const y = window.scrollY;
  // Keep focus on a picker that triggered the redraw (arrow keys fire change on each step).
  const fa = document.activeElement && document.activeElement.tagName === 'SELECT' ? document.activeElement.getAttribute('aria-label') : null;
  if (state.timer) clearInterval(state.timer);
  state.timer = null;
  state.ui = null;
  app.replaceChildren(header(), verdictPanel(), casePanel(), brokenPanel(), limits());
  window.scrollTo(0, y);
  if (fa) { const n = [...app.querySelectorAll('select')].find(s => s.getAttribute('aria-label') === fa); if (n) n.focus(); }
}
draw();
"""


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", required=True, help="M6 run root (holds summary.json, analysis.json and run/)")
    parser.add_argument("--binary", default=str(default_binary("vv-lab")), help="vv-lab build used for replay-m4")
    parser.add_argument("--no-replay", action="store_true", help="skip replay-m4; nothing is then called verified")
    parser.add_argument("--output", help="default: <run>/workbench.html")
    parser.add_argument("--case", help="case id shown first")
    parser.add_argument("--candidate", help="candidate shown first")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    root = Path(args.run)
    output = Path(args.output) if args.output else root / "workbench.html"
    binary = None if args.no_replay else Path(args.binary)
    try:
        payload = write_workbench(root, output, binary, args.case, args.candidate)
    except (WorkbenchError, OSError, KeyError, TypeError, ValueError, AttributeError) as error:
        print(f"workbench FAILED: {error}", file=sys.stderr)
        return 1
    failed = [c["name"] for c in payload["checks"] if not c["ok"]]
    statuses = ["integrity" if c["integrity"]["problems"] else c["replay_check"]["status"] for c in payload["cases"]]
    problems = sum(bool(c["integrity"]["problems"]) for c in payload["cases"])
    print(f"wrote {output}")
    print(f"run checks failed: {failed or 'none'}")
    print(
        f"cases: {len(statuses)}, verified {statuses.count('verified')}, failed {statuses.count('failed')}, "
        f"not run {statuses.count('not_run')}, with integrity problems (never counted as verified) {problems}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
