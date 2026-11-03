"""Build the M14 ground-vehicle cases for vv-exec from the existing scenario files.

A `vv-ground-case.v1` case bundles what `vv-lab run-m4` reads from separate files: the scenario,
the contract set, the optional actuator configuration and the controller. The scenario files in
`scenarios/` are read, never changed; `sources.json` records the sha256 of every source.

    python scripts/m14_cases.py            # writes exec/cases/m14/*.json
    python scripts/m14_cases.py --check    # fails if a written case differs from its sources
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "exec" / "cases" / "m14"

# name: (scenario, contracts, actuator or None, controller)
CASES = {
    "ground-zone-corridor": (
        "scenarios/m2/f-zone-nominal.json",
        "scenarios/m3/contracts-nominal.json",
        None,
        "dominant_axis",
    ),
    "ground-nominal-stop": (
        "scenarios/m3/nominal-stop.json",
        "scenarios/m3/contracts-stop.json",
        "scenarios/m3/actuator-none.json",
        "dominant_axis",
    ),
    "ground-x-first-overshoot": (
        "scenarios/m4/x-first-overshoot.json",
        "scenarios/m3/contracts-nominal.json",
        None,
        "x_first",
    ),
}


def load(rel: str) -> tuple[object, str]:
    data = (ROOT / rel).read_bytes()
    return json.loads(data), hashlib.sha256(data).hexdigest()


def build(name: str) -> tuple[bytes, dict[str, str]]:
    scenario, contracts, actuator, controller = CASES[name]
    case: dict[str, object] = {"schema": "vv-ground-case.v1", "controller": controller}
    sources = {}
    for key, rel in (("scenario", scenario), ("contracts", contracts), ("actuator", actuator)):
        if rel is None:
            continue
        case[key], sources[rel] = load(rel)
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
        manifest[name] = {"case_sha256": hashlib.sha256(data).hexdigest(), "sources": sources}
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
