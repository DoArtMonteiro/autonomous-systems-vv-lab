"""Build the M14 benchmark base cases for vv-exec from existing scenario and case files.

Ground: a `vv-ground-case.v1` case bundles what `vv-lab run-m4` reads from separate files: the
scenario, the contract set, the optional actuator configuration and the controller.
Rocket: an M9.1 landing case (`crates/vv-rocket/landing/m91-nominal.json`) with one fault.

Sources are read, never changed. Each case may apply a few JSON-pointer overrides, listed below
and recorded with the sha256 of every source in `sources.json`.

    python scripts/m14_cases.py            # writes exec/cases/m14/*.json
    python scripts/m14_cases.py --check    # fails if a written case differs from its sources
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "exec" / "cases" / "m14"
M91 = "crates/vv-rocket/landing/m91-nominal.json"

# name: (kind, sources, overrides). Ground sources: scenario, contracts, actuator or None,
# controller. Rocket sources: the M9.1 case. Overrides: (JSON pointer, value) on the output.
CASES: dict[str, tuple[str, tuple, list]] = {
    "ground-zone-corridor": (
        "ground",
        ("scenarios/m2/f-zone-nominal.json", "scenarios/m3/contracts-nominal.json", None, "dominant_axis"),
        [],
    ),
    "ground-nominal-stop": (
        "ground",
        ("scenarios/m3/nominal-stop.json", "scenarios/m3/contracts-stop.json", "scenarios/m3/actuator-none.json", "dominant_axis"),
        [],
    ),
    "ground-x-first-overshoot": (
        "ground",
        ("scenarios/m4/x-first-overshoot.json", "scenarios/m3/contracts-nominal.json", None, "x_first"),
        [],
    ),
    # Held-out ground mechanism 1: delayed actuation on the stop mission. The window covers the
    # whole mission so that start_tick in [1, 16] is always valid.
    "ground-stop-actuator-delay": (
        "ground",
        ("scenarios/m3/nominal-stop.json", "scenarios/m3/contracts-stop.json", "scenarios/m3/actuator-delayed.json", "dominant_axis"),
        [("/actuator/faults/0/windows", [{"start_tick": 1, "end_tick": 16}]),
         ("/actuator/faults/0/delay_ticks", 1),
         ("/actuator/faults/0/probability_permille", 0)],
    ),
    # Held-out ground mechanism 2: lost actuation on the x-first overshoot mission.
    "ground-overshoot-actuator-loss": (
        "ground",
        ("scenarios/m4/x-first-overshoot.json", "scenarios/m3/contracts-nominal.json", "scenarios/m3/actuator-intermittent.json", "x_first"),
        [("/actuator/faults/0/windows", [{"start_tick": 1, "end_tick": 12}]),
         ("/actuator/faults/0/probability_permille", 0)],
    ),
    # Rocket: one fault at the bottom of its registered magnitude range, from 5 s to the end.
    "rocket-thrust-loss": (
        "rocket",
        (M91,),
        [("/faults", [{"kind": "thrust_loss", "start_s": 5.0, "end_s": 40.0, "magnitude": 0.05}])],
    ),
    "rocket-gnss-bias": (
        "rocket",
        (M91,),
        [("/faults", [{"kind": "gnss_bias", "start_s": 5.0, "end_s": 40.0, "magnitude": 5.0}])],
    ),
    "rocket-imu-accel-bias": (
        "rocket",
        (M91,),
        [("/faults", [{"kind": "imu_accel_bias", "start_s": 5.0, "end_s": 40.0, "magnitude": 0.05}])],
    ),
}


def load(rel: str) -> tuple[object, str]:
    data = (ROOT / rel).read_bytes()
    return json.loads(data), hashlib.sha256(data).hexdigest()


def set_pointer(doc: object, pointer: str, value: object) -> None:
    parts = [p.replace("~1", "/").replace("~0", "~") for p in pointer.split("/")[1:]]
    node = doc
    for p in parts[:-1]:
        node = node[int(p)] if isinstance(node, list) else node[p]
    last = parts[-1]
    if isinstance(node, list):
        node[int(last)] = value
    else:
        if last not in node:
            raise KeyError(f"{pointer} does not exist in the source")
        node[last] = value


def build(name: str) -> tuple[bytes, dict[str, str]]:
    kind, src, overrides = CASES[name]
    sources = {}
    if kind == "ground":
        scenario, contracts, actuator, controller = src
        case: object = {"schema": "vv-ground-case.v1", "controller": controller}
        for key, rel in (("scenario", scenario), ("contracts", contracts), ("actuator", actuator)):
            if rel is not None:
                case[key], sources[rel] = load(rel)
    else:
        case, sources[src[0]] = load(src[0])
        case = copy.deepcopy(case)
    for pointer, value in overrides:
        set_pointer(case, pointer, value)
    text = json.dumps(case, indent=2, ensure_ascii=True) + "\n"
    return text.encode("ascii"), sources


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {}
    bad = []
    for name in CASES:
        data, sources = build(name)
        path = OUT / f"{name}.json"
        if args.check:
            if not path.exists() or path.read_bytes() != data:
                bad.append(name)
        else:
            path.write_bytes(data)
        manifest[name] = {
            "case_sha256": hashlib.sha256(data).hexdigest(),
            "sources": sources,
            "overrides": [[p, v] for p, v in CASES[name][2]],
        }
    text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    if args.check:
        sources_path = OUT / "sources.json"
        if not sources_path.exists() or sources_path.read_text(encoding="ascii") != text:
            bad.append("sources.json")
        if bad:
            print("stale:", ", ".join(bad), file=sys.stderr)
            return 1
        print(f"{len(CASES)} cases match their sources")
        return 0
    (OUT / "sources.json").write_text(text, encoding="ascii", newline="\n")
    print(f"wrote {len(CASES)} cases to {OUT.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
