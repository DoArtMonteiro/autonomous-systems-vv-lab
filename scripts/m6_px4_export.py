"""Export M6 counterexamples as PX4 replay requests (dry run, no simulator).

The output, `vv-repair.px4-replay-request.v1`, is a proposal for the separate,
governed PX4/MAVSDK Gate 1A workstream. It is not an `m5.experiment.v1`: that
schema needs a handoff hash, run identifiers and caps that only Gate 1A assigns.
This script never launches PX4, WSL or Docker, and nothing it writes is SITL
evidence.

Each counterexample gets a mapping status:

* `mappable`: every fault atom has a Gate 1A fault with the same meaning.
* `partial`: every atom maps, but some timing or strength cannot be kept.
* `not_mappable`: at least one atom has no Gate 1A equivalent. The 2D ground
  model's communication delay, packet loss, GPS noise and actuator delay or
  continuation have no injection in `m5.experiment.v1`.

Geometry: lab x/y in mm become east/north offsets from the start; every item is
flown at `CRUISE_REL_ALT_MM` (the Gate 1A `rb1.target_rel_alt_mm`). The tick
length converts ticks to microseconds only as a trigger hint.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SCHEMA = "vv-repair.px4-replay-request.v1"
SUITE_ID = re.compile(r"[a-z0-9_]{1,32}")  # same rule as `vv-repair`, so ids never leave `inputs/suites`
CRUISE_REL_ALT_MM = 10_000
MAX_INPUT_BYTES = 64 * 1024 * 1024
# Gate 1A property that observes the same requirement, when one exists.
PROPERTY_MAP = {
    "fallback_response": "hf1 (nav_state change within hf1.nav_state_within_us after the fault)",
    "no_motion_in_fallback": "ef1b (displacement after the fault within ef1b.displacement_max_mm)",
    "safe_fallback": "ef1b (displacement after the fault within ef1b.displacement_max_mm)",
    "world_bounds": "none in m5.thresholds.v1 (needs a geofence property)",
    "restricted_zone": "none in m5.thresholds.v1 (needs a geofence property)",
}
UNMAPPABLE = {
    "gps_dropout_rate": "random per-tick GPS loss has no Gate 1A injection",
    "gps_noise": "GPS noise injection is not in m5.experiment.v1",
    "packet_loss": "telemetry link faults are not in m5.experiment.v1",
    "packet_loss_rate": "telemetry link faults are not in m5.experiment.v1",
    "comm_delay": "observation delay is not in m5.experiment.v1",
    "actuator_delay": "delayed ground-vehicle actuation has no multicopter equivalent",
    "actuator_lost": "a lost ground command is not a motor failure (motor1_off)",
    "actuator_continued": "continued ground motion after a stop has no multicopter equivalent",
}


def map_atom(atom: dict[str, Any], tick_us: int) -> dict[str, Any]:
    if atom["kind"] == "gps_dropout":
        return {
            "atom": atom,
            "status": "partial",
            "channel": "inject",
            "fault": "gps_inject_off",
            "trigger": "hover_elapsed",
            "trigger_after_us_hint": (atom["start"] - 1) * tick_us,
            "loss": "Gate 1A turns GPS off and does not restore it, so the window end is lost",
        }
    return {"atom": atom, "status": "not_mappable", "reason": UNMAPPABLE.get(atom["kind"], "unknown fault kind")}


def request(item: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
    tick_us = int(scenario["tick_ms"]) * 1000
    start = scenario["vehicle"]["start"]
    mission = scenario["mission"]
    atoms = [map_atom(atom, tick_us) for atom in item["atoms"]]
    statuses = {entry["status"] for entry in atoms}
    if "not_mappable" in statuses or not atoms:
        status = "not_mappable"
    else:
        status = "partial" if "partial" in statuses else "mappable"
    return {
        "counterexample": item["id"],
        "suite": item["suite"],
        "class": item["class"],
        "found_on": item["found_on"],
        "m4_sha256": item["m4_sha256"],
        "status": status,
        "mission_items": [
            {
                "index": index,
                "north_mm": point["y_mm"] - start["y_mm"],
                "east_mm": point["x_mm"] - start["x_mm"],
                "rel_alt_mm": CRUISE_REL_ALT_MM,
                "acceptance_radius_mm": mission["arrival_radius_mm"],
            }
            for index, point in enumerate(mission["waypoints"])
        ],
        "atoms": atoms,
        "gate1a_property": PROPERTY_MAP.get(item["identity"]["property"], "none (lab-specific contract)"),
        "expected_lab_violation_tick": item["identity"]["violation_tick"],
    }


def export(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "evidence.json"
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("evidence.json exceeds the read limit")
    evidence = json.loads(path.read_text(encoding="utf-8"))
    scenarios = {}
    for suite in evidence["experiment"]["suites"]:
        if not SUITE_ID.fullmatch(str(suite["id"])):
            raise ValueError(f"invalid suite id {suite['id']!r}")
        scenario = json.loads((run_dir / "inputs" / "suites" / suite["id"] / "scenario.json").read_text(encoding="utf-8"))
        scenario.setdefault("tick_ms", 100)  # the library default when the scenario omits it
        scenarios[suite["id"]] = scenario
    requests = [request(item, scenarios[item["suite"]]) for item in evidence["corpus"] + evidence["introduced"]]
    counts: dict[str, int] = {}
    for entry in requests:
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    return {
        "schema": SCHEMA,
        "evidence_sha256": evidence["evidence_sha256"],
        "target": "m5.experiment.v1 (PX4/MAVSDK Gate 1A); conversion and execution belong to that workstream",
        "sitl_validated": False,
        "counts": dict(sorted(counts.items())),
        "requests": requests,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_dir", help="a vv-repair run directory (contains evidence.json)")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        result = export(Path(args.run_dir))
    except (OSError, ValueError, KeyError) as error:
        print(f"export failed: {error}", file=sys.stderr)
        return 1
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    Path(args.output).write_text(text, encoding="utf-8", newline="\n")
    print(f"px4 replay requests: {result['counts']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
