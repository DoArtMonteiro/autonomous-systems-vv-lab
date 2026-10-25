"""Export one real adapter run as a compact trace for the rendering spikes.

Runs the ground-vehicle adapter on a stored mission and writes
spikes/out/trace.json with the recorded per-tick positions, safety state and
geometry. The spikes render only these recorded values; they do not simulate.

Usage: python spikes/export_trace.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from sim_adapter import REQUEST_SCHEMA, GroundVehicleAdapter  # noqa: E402

OUT = ROOT / "spikes" / "out"


def export(mission: str = "delayed_after_fallback") -> dict:
    request = {"schema": REQUEST_SCHEMA, "model": "ground-vehicle-2d", "mission": mission,
               "seed": 42, "controller": "dominant_axis", "overrides": {}}
    result = GroundVehicleAdapter().run(request, ROOT / "runs" / "spike-trace", reuse=True)
    trace = {
        "schema": "vv-spike-trace.v1",
        "run_id": result["run_id"],
        "source_sha256": result["provenance"]["source_sha256"],
        "replay": result["replay"]["status"],
        "physics": result["model"]["physics"],
        "geometry": result["geometry"],
        "states": [
            {"tick": s["tick"], "from_x_mm": s["truth_from"]["x_mm"], "from_y_mm": s["truth_from"]["y_mm"],
             "x_mm": s["truth"]["x_mm"], "y_mm": s["truth"]["y_mm"], "heading": s["heading"],
             "safety_state": s["safety_state"]}
            for s in result["states"]
        ],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "trace.json").write_text(json.dumps(trace, indent=1), encoding="utf-8", newline="\n")
    return trace


if __name__ == "__main__":
    t = export()
    print(f"wrote spikes/out/trace.json: run {t['run_id']}, {len(t['states'])} ticks, replay {t['replay']}")
