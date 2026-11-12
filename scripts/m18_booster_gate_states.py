"""Records the booster separation states of the bundled `vv-ascent` cases for the booster-return gate.

For each case and seed it runs `vv-ascent run` and keeps only what the gate needs from `trace.json`:
the first sample of the booster (true state at separation, true mass and propellant), the dispersion
factors of the first stage (thrust, Isp, propellant, dry mass) and the simulator's own ballistic
impact (downrange, speed), which the gate's integrator must reproduce.

    python scripts/m18_booster_gate_states.py --exe <vv-ascent executable> --output scripts/data/m18_booster_gate_states.json
"""

import argparse
import json
import os
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CASES = {
    "small-leo": os.path.join(HERE, "..", "crates", "vv-ascent", "cases", "small-leo.json"),
    "medium-leo": os.path.join(HERE, "..", "crates", "vv-ascent", "cases", "medium-leo.json"),
}
SEEDS = list(range(5000, 5020))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    out = {"schema": "vv-ascent-gate-states.v1", "seeds": SEEDS, "states": {}}
    for case, path in CASES.items():
        out["states"][case] = {}
        for seed in SEEDS:
            with tempfile.TemporaryDirectory() as d:
                subprocess.run([a.exe, "run", path, "--seed", str(seed), "--output", d], check=True, capture_output=True, timeout=300)
                with open(os.path.join(d, "trace.json"), encoding="utf-8") as f:
                    t = json.load(f)
                with open(os.path.join(d, "verification.json"), encoding="utf-8") as f:
                    v = json.load(f)
            b = next(e for e in t["entities"] if e["id"] == "booster")["samples"][0]
            imp = next(e for e in t["events"] if e["entity"] == "booster" and e["kind"] == "impact")["detail"]
            out["states"][case][str(seed)] = {
                "tick": b["tick"],
                "x_m": b["x_m"], "z_m": b["z_m"], "vx_m_s": b["vx_m_s"], "vz_m_s": b["vz_m_s"],
                "mass_kg": b["mass_kg"], "propellant_kg": b["propellant_kg"],
                "stage1_factors": {"thrust": t["dispersion_factors"][0][0], "isp": t["dispersion_factors"][0][1],
                                   "propellant": t["dispersion_factors"][0][2], "dry_mass": t["dispersion_factors"][0][3]},
                "sim_impact_downrange_m": imp["downrange_m"], "sim_impact_speed_m_s": imp["speed_m_s"],
                "outcome": v["outcome"],
            }
    os.makedirs(os.path.dirname(os.path.abspath(a.output)), exist_ok=True)
    with open(a.output, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
        f.write("\n")


if __name__ == "__main__":
    main()
