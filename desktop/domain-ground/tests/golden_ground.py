"""Generates the golden fixtures of the ground-vehicle domain host from the Python adapter.

For every case below it runs scripts/sim_adapter.GroundVehicleAdapter with the equivalent Python
request and stores what the adapter wrote: the three input files (byte for byte) and the sha256 of
every native output of `vv-lab run-m4`. The Rust test `tests/host.rs` runs the host on the desktop
request of the same case and asserts byte equality.

    cargo build --release                       (repository root; builds vv-lab)
    python desktop/domain-ground/tests/golden_ground.py [--binary target/release/vv-lab.exe]

Rerun after a change of the simulator sources: m4.json records a hash of them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from sim_adapter import GroundVehicleAdapter  # noqa: E402

DOMAIN = "ground-vehicle"
NATIVE = ("events.json", "report.json", "mission.json", "verification.json", "m4.json")


def gps(start: int, end: int) -> dict:
    return {"kind": "gps_dropout", "magnitude": None, "start": start, "end": end}


def actuator(kind: str, start: int, end: int, magnitude: float | None = None) -> dict:
    return {"kind": kind, "magnitude": magnitude, "start": start, "end": end}


def case(name, mission, controller, seed, faults=(), params=None, gps_override="keep", act_override="keep"):
    """Desktop request plus the Python request that must write the same inputs."""
    desktop = {
        "schema": "vv-run-request.v1",
        "domain": DOMAIN,
        "scenario": mission,
        "controller": controller,
        "seed": seed,
        "faults": list(faults),
        "parameters": params or {},
    }
    overrides: dict = {}
    for fault in faults:
        if fault["kind"] == "gps_dropout":
            gps_override = {"start_tick": fault["start"], "end_tick": fault["end"]}
        else:
            act_override = {
                "kind": fault["kind"],
                "start_tick": fault["start"],
                "end_tick": fault["end"],
                "probability_permille": 1000,
            }
            if fault["kind"] == "delayed_movement":
                act_override["delay_ticks"] = int(fault["magnitude"])
    if gps_override != "keep":
        overrides["gps_dropout"] = gps_override
    if act_override != "keep":
        overrides["actuator_fault"] = act_override
    python = {
        "schema": "vv-sim-run-request.v1",
        "model": "ground-vehicle-2d",
        "mission": mission,
        "seed": seed,
        "controller": controller,
        "overrides": overrides,
    }
    return name, desktop, python


CASES = [
    case("nominal_stop", "nominal_stop", "dominant_axis", 42),
    case("x_first_overshoot_dominant", "x_first_overshoot", "dominant_axis", 42),
    case("x_first_overshoot_x_first", "x_first_overshoot", "x_first", 1337),
    case("delayed_after_fallback_builtin", "delayed_after_fallback", "dominant_axis", 42),
    case("nominal_gps_dropout", "nominal_stop", "dominant_axis", 42, [gps(3, 6)]),
    case("nominal_continued", "nominal_stop", "dominant_axis", 7, [actuator("continued_movement", 5, 8)]),
    case("overshoot_lost", "x_first_overshoot", "dominant_axis", 42, [actuator("lost_movement", 2, 3)]),
    case(
        "nominal_x_first_delayed_and_gps",
        "nominal_stop",
        "x_first",
        2026,
        [gps(5, 6), actuator("delayed_movement", 2, 2, 4.0)],
    ),
    case(
        "delayed_after_fallback_cleared",
        "delayed_after_fallback",
        "dominant_axis",
        42,
        params={"clear_builtin_faults": 1.0},
        gps_override="none",
        act_override="none",
    ),
    case("delayed_after_fallback_gps_replaced", "delayed_after_fallback", "x_first", 99, [gps(2, 5)]),
    case(
        "delayed_after_fallback_actuator_replaced",
        "delayed_after_fallback",
        "dominant_axis",
        42,
        [actuator("delayed_movement", 3, 3, 1.0)],
    ),
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", default=str(ROOT / "target" / "release" / ("vv-lab.exe" if sys.platform == "win32" else "vv-lab")))
    args = parser.parse_args()
    adapter = GroundVehicleAdapter(Path(args.binary))
    golden = HERE / "golden"
    shutil.rmtree(golden, ignore_errors=True)
    names = []
    with tempfile.TemporaryDirectory() as scratch:
        for name, desktop, python in CASES:
            result = adapter.run(python, Path(scratch))
            if result["verdict"]["status"] != "verified":
                raise SystemExit(f"{name}: the Python adapter did not verify its own run: {result['verdict']}")
            run_dir = Path(scratch) / result["run_id"]
            target = golden / name
            (target / "inputs").mkdir(parents=True)
            for file in ("scenario.json", "actuator.json", "contracts.json"):
                shutil.copyfile(run_dir / "inputs" / file, target / "inputs" / file)
            (target / "request.json").write_text(json.dumps(desktop, indent=2) + "\n", encoding="utf-8", newline="\n")
            native = {file: sha256(run_dir / file) for file in NATIVE}
            (target / "native.json").write_text(json.dumps(native, indent=2) + "\n", encoding="utf-8", newline="\n")
            names.append(name)
    (golden / "cases.json").write_text(json.dumps(names, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {len(names)} golden cases to {golden}")


if __name__ == "__main__":
    main()
