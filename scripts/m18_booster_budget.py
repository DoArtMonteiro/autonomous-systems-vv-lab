"""Independent propellant budget for a powered return of the launch-ascent booster (order of
magnitude, not the simulator's code, not a bound, not a validation).

With the propellant a bundled `vv-ascent` case keeps in the first stage at MECO (`reserve_fraction`),
how much velocity change can the booster make, and what do a landing burn and a boost-back to the
launch site need?

Inputs: the case file (booster dry mass, reserve, Isp, drag) and the `trace.json` of a nominal run
(`vv-ascent run <case> --seed <n> --output <dir>`), from which only the first sample of the booster
(the separation state) and the impact event are read. The ballistic descent is then integrated here,
with this script's own drag-and-gravity point-mass integrator, from that state to the surface, and
compared with the impact the simulator reports (distance and speed): a cross-check of the simulator's
ballistic booster, and the source of the impact speed used for the landing figure.

    cargo run --release --manifest-path crates/vv-ascent/Cargo.toml -- run crates/vv-ascent/cases/small-leo.json --seed 5000 --output runs/ascent-small
    python scripts/m18_booster_budget.py --case crates/vv-ascent/cases/small-leo.json --trace runs/ascent-small/trace.json

The figures are estimates, not bounds: the horizontal speed to cancel is a necessary part of a
boost-back (the return itself needs more, and the stage must fall back over the distance already
flown), the impact speed is the speed of the ballistic descent at the surface (a real landing burn
starts above it, loses speed to drag first and pays gravity loss), and Tsiolkovsky is taken at vacuum
Isp (sea-level Isp gives less). They can show that a goal is far out of reach with a given reserve,
not that it is reachable.
"""

import argparse
import json
import math
import os

MU = 3.986004418e14
R = 6_371_000.0
G0 = 9.80665
RHO0 = 1.225
H_SCALE = 8500.0

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CASE = os.path.join(HERE, "..", "crates", "vv-ascent", "cases", "small-leo.json")


def ballistic(x, z, vx, vz, mass, cd, area, dt=0.02):
    """Drag and inverse-square gravity to the surface from a state: (downrange_m, impact speed)."""

    def f(s):
        r = math.hypot(s[0], s[1])
        rho = RHO0 * math.exp(-max(r - R, 0.0) / H_SCALE)
        v = math.hypot(s[2], s[3])
        k = -0.5 * rho * v * cd * area / mass
        return (s[2], s[3], -MU * s[0] / r**3 + k * s[2], -MU * s[1] / r**3 + k * s[3])

    s = (x, z, vx, vz)
    for _ in range(2_000_000):
        k1 = f(s)
        k2 = f(tuple(a + 0.5 * dt * b for a, b in zip(s, k1)))
        k3 = f(tuple(a + 0.5 * dt * b for a, b in zip(s, k2)))
        k4 = f(tuple(a + dt * b for a, b in zip(s, k3)))
        n = tuple(a + dt / 6 * (b + 2 * c + 2 * d + e) for a, b, c, d, e in zip(s, k1, k2, k3, k4))
        if math.hypot(n[0], n[1]) < R:
            r0 = math.hypot(s[0], s[1])
            fr = (r0 - R) / (r0 - math.hypot(n[0], n[1]))
            xi, zi = s[0] + fr * (n[0] - s[0]), s[1] + fr * (n[1] - s[1])
            vxi, vzi = s[2] + fr * (n[2] - s[2]), s[3] + fr * (n[3] - s[3])
            return R * math.atan2(xi, zi), math.hypot(vxi, vzi)
        s = n
    raise RuntimeError("no impact")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", default=DEFAULT_CASE)
    ap.add_argument("--trace", required=True, help="trace.json of a vv-ascent run of that case")
    a = ap.parse_args()
    with open(a.case, encoding="utf-8") as f:
        case = json.load(f)
    with open(a.trace, encoding="utf-8") as f:
        trace = json.load(f)
    s1 = case["vehicle"]["stages"][0]
    dry = s1["dry_mass_kg"]
    booster = next(e for e in trace["entities"] if e["id"] == "booster")
    s0 = booster["samples"][0]
    impact = next(e for e in trace["events"] if e["entity"] == "booster" and e["kind"] == "impact")["detail"]
    mass = s0["mass_kg"]
    reserve = mass - dry
    ve = s1["isp_vac_s"] * G0
    print(f"{case['name']}")
    print(f"  booster at separation: altitude {s0['altitude_m'] / 1000:.1f} km, downrange {s0['downrange_m'] / 1000:.1f} km, speed {s0['speed_m_s']:.0f} m/s; dry {dry:.0f} kg, propellant on board {reserve:.0f} kg ({100 * reserve / s1['propellant_kg']:.1f} % of the load of {s1['propellant_kg']:.0f} kg)")

    rng, vimp = ballistic(s0["x_m"], s0["z_m"], s0["vx_m_s"], s0["vz_m_s"], mass, s1["drag_coefficient"], s1["reference_area_m2"])
    print(f"  ballistic impact: this integrator {rng / 1000:.2f} km at {vimp:.1f} m/s; the simulator {impact['downrange_m'] / 1000:.2f} km at {impact['speed_m_s']:.1f} m/s (differences {abs(rng - impact['downrange_m']):.1f} m and {abs(vimp - impact['speed_m_s']):.2f} m/s)")

    up = (s0["x_m"] / math.hypot(s0["x_m"], s0["z_m"]), s0["z_m"] / math.hypot(s0["x_m"], s0["z_m"]))
    hz = (up[1], -up[0])
    vh = s0["vx_m_s"] * hz[0] + s0["vz_m_s"] * hz[1]
    vr = s0["vx_m_s"] * up[0] + s0["vz_m_s"] * up[1]
    print(f"  separation velocity: horizontal {vh:.0f} m/s, vertical {vr:.0f} m/s; booster is {s0['downrange_m'] / 1000:.0f} km downrange")

    dv_avail = ve * math.log(mass / dry)
    land = vimp
    back = vh
    need = land + back
    prop = lambda dv: dry * (math.exp(dv / ve) - 1.0)
    print(f"  Tsiolkovsky with all the propellant on board at vacuum Isp {s1['isp_vac_s']:.0f} s: {dv_avail:.0f} m/s")
    print(f"  landing burn from the ballistic impact speed: about {land:.0f} m/s, {prop(land):.0f} kg ({100 * prop(land) / s1['propellant_kg']:.1f} % of the load)")
    print(f"  cancelling the horizontal speed alone (boost-back to the launch site needs more than this): about {back:.0f} m/s, {prop(back):.0f} kg")
    print(f"  both: about {need:.0f} m/s, {prop(need):.0f} kg, {100 * prop(need) / s1['propellant_kg']:.1f} % of the first-stage load (the case keeps {100 * s1['reserve_fraction']:.1f} %)")
    print(f"  with the propellant of the case: landing burn {'within' if dv_avail >= land else 'beyond'} reach, boost-back to the launch site {'within' if dv_avail >= need else 'beyond'} reach")
    print("  a larger reserve means less first-stage burn: the upper stage separates slower, so every extra kilogram kept here has to be paid for in orbit insertion (not computed here).")


if __name__ == "__main__":
    main()
