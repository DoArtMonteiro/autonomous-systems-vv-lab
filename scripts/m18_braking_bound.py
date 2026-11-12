"""Order-of-magnitude cross-check for the M18 vehicle-design runs (not the simulator's code, and not a bound).

A vertical point mass falls from the heavy return stage template's initial state and brakes at FULL
thrust from the first instant, with the stage's own drag (exponential atmosphere, Cd and area of the
template) and no attitude losses. This is not the best braking any controller could achieve (full
thrust from t = 0 is not optimal: it burns propellant early and can run out before the ground), it
ignores the seed's initial dispersion and the height of the centre of mass, and it uses a fixed
time step. It is only a check that the simulator's touchdown speed and propellant use are of the
right order and move the right way when the thrust changes. It does not prove anything about the
simulator.

The vehicle, the environment and the initial state are read from the template the host simulates
(`desktop/domain-rocket/cases/heavy-return.json`), not typed here. If the propellant is exhausted
before the stop or the ground, the script says so: the numbers after that are free fall and must
not be read as braking.

    python scripts/m18_braking_bound.py
"""

import json
import math
import os
import sys

TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "desktop", "domain-rocket", "cases", "heavy-return.json")
DT = 0.001


def load_template(path=TEMPLATE):
    with open(path, encoding="utf-8") as f:
        c = json.load(f)
    v = c["vehicle"]
    env = c["environment"]
    return {
        "dry_kg": v["dry_mass_kg"],
        "prop_kg": v["propellant_mass_kg"],
        "thrust_n": v["max_thrust_n"],
        "isp_s": v["isp_s"],
        "cd": v["drag_coefficient"],
        "area_m2": v["reference_area_m2"],
        "g0": env["gravity_mps2"],
        "rho0": env["atmosphere"]["density_kgpm3"],
        "scale_height_m": env["atmosphere"]["scale_height_m"],
        "h0": c["initial"]["position_m"][2],
        "v0": c["initial"]["velocity_mps"][2],
    }


def ideal_touchdown(dry_kg, prop_kg, thrust_n, isp_s, cd, area_m2, g0, rho0, scale_height_m, h0, v0):
    m, h, v, t = dry_kg + prop_kg, h0, v0, 0.0
    prop = prop_kg
    mdot = thrust_n / (isp_s * g0)
    exhausted_at = None
    while h > 0.0:
        f = thrust_n if prop > 0.0 else 0.0
        if f == 0.0 and exhausted_at is None:
            exhausted_at = {"t_s": round(t, 2), "altitude_m": round(h, 1), "speed_mps": round(-v, 1)}
        drag = 0.5 * rho0 * math.exp(-h / scale_height_m) * v * v * cd * area_m2
        a = (f + drag) / m - g0
        if v + a * DT >= 0.0 and f > 0.0:
            return {"stops_above_ground_m": round(h, 1), "t_s": round(t, 2), "propellant_left_kg": round(prop, 1)}
        h += v * DT + 0.5 * a * DT * DT
        v += a * DT
        if f > 0.0:
            m -= mdot * DT
            prop -= mdot * DT
        t += DT
    out = {"touchdown_speed_mps": round(-v, 2), "t_s": round(t, 2), "propellant_left_kg": round(max(prop, 0.0), 1)}
    if exhausted_at:
        out["WARNING"] = f"propellant exhausted at {exhausted_at}; the rest is free fall, not braking"
    return out


if __name__ == "__main__":
    heavy = load_template()
    for k in (1.0, 0.85, 0.75, 0.7):
        p = dict(heavy, thrust_n=heavy["thrust_n"] * k)
        tw = p["thrust_n"] / ((p["dry_kg"] + p["prop_kg"]) * p["g0"])
        result = ideal_touchdown(**p)
        print(f"thrust x{k:<4} T/W {tw:.2f}: {result}")
        if "WARNING" in result:
            print("  warning: " + result["WARNING"], file=sys.stderr)
