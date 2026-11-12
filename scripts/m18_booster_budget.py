"""Independent propellant budget for a powered return of the launch-ascent booster (order of
magnitude, not the simulator's code, not a bound, not a validation).

It answers one question with a Tsiolkovsky budget and a separate point-mass integrator: with the
propellant a bundled `vv-ascent` case keeps in the first stage at MECO (`reserve_fraction`), how much
velocity change can the booster make, and how much do a landing burn and a boost-back need?

Inputs: the case file (booster dry mass, reserve, Isp, thrust) and the separation state the simulator
reports for the nominal run (altitude, speed, and the downrange distance at which the ballistic
booster hits the surface). The flight-path angle and the downrange distance at separation are not
reported in the documentation, so they are not read from the simulator: the script tries several
assumed separation downrange distances and, for each, finds by bisection the flight-path angle at
which its own drag-and-gravity integration of the ballistic descent reproduces the stated impact
distance. The conclusions it prints are the ones that hold for all of them.

    python scripts/m18_booster_budget.py
    python scripts/m18_booster_budget.py --case crates/vv-ascent/cases/medium-leo.json --sep-alt-km 93.1 --sep-speed 2448 --impact-km 811.8

The figures are lower bounds on what a controller needs (no gravity loss in the stops, no steering
loss, no finite-thrust effects, drag on the descent included only in the ballistic integration):
they can show that a goal is out of reach, never that it is reachable.
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


def ballistic(alt_m, speed, gamma, mass, cd, area, dt=0.05):
    """Drag and inverse-square gravity from separation to the surface: (range_m, impact speed, trajectory).

    `gamma` is the flight-path angle above the local horizontal. Planar, non-rotating Earth.
    """
    x, z = 0.0, R + alt_m
    vx, vz = speed * math.cos(gamma), speed * math.sin(gamma)
    t = 0.0
    track = []

    def acc(x, z, vx, vz):
        r = math.hypot(x, z)
        rho = RHO0 * math.exp(-max(r - R, 0.0) / H_SCALE)
        v = math.hypot(vx, vz)
        k = -0.5 * rho * v * cd * area / mass
        return -MU * x / r**3 + k * vx, -MU * z / r**3 + k * vz

    while True:
        # classical RK4 on (x, z, vx, vz)
        def f(s):
            ax, az = acc(*s)
            return (s[2], s[3], ax, az)

        s = (x, z, vx, vz)
        k1 = f(s)
        k2 = f(tuple(a + 0.5 * dt * b for a, b in zip(s, k1)))
        k3 = f(tuple(a + 0.5 * dt * b for a, b in zip(s, k2)))
        k4 = f(tuple(a + dt * b for a, b in zip(s, k3)))
        n = tuple(a + dt / 6 * (b + 2 * c + 2 * d + e) for a, b, c, d, e in zip(s, k1, k2, k3, k4))
        r_next = math.hypot(n[0], n[1])
        if r_next < R:
            r0 = math.hypot(x, z)
            f_ = (r0 - R) / (r0 - r_next)
            xi = x + f_ * (n[0] - x)
            zi = z + f_ * (n[1] - z)
            vxi = vx + f_ * (n[2] - vx)
            vzi = vz + f_ * (n[3] - vz)
            return R * math.atan2(xi, zi), math.hypot(vxi, vzi), track
        x, z, vx, vz = n
        t += dt
        if int(t / dt) % 200 == 0:
            track.append((t, math.hypot(x, z) - R, math.hypot(vx, vz)))
        if t > 5000:
            raise RuntimeError("no impact")


def solve_angle(alt_m, speed, impact_m, mass, cd, area):
    """Flight-path angle (rad) whose ballistic range equals `impact_m`; the range grows with the angle
    up to about 45 degrees, so the search is on (0, 45 degrees]."""
    lo, hi = 0.0, math.radians(45.0)
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        rng, _, _ = ballistic(alt_m, speed, mid, mass, cd, area)
        if rng < impact_m:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", default=DEFAULT_CASE)
    ap.add_argument("--sep-alt-km", type=float, default=95.4)
    ap.add_argument("--sep-speed", type=float, default=2765.0)
    ap.add_argument("--impact-km", type=float, default=1023.5)
    a = ap.parse_args()
    with open(a.case, encoding="utf-8") as f:
        case = json.load(f)
    s1 = case["vehicle"]["stages"][0]
    dry = s1["dry_mass_kg"]
    reserve = s1["propellant_kg"] * s1["reserve_fraction"]
    m0 = dry + reserve
    isp = s1["isp_vac_s"]
    ve = isp * G0
    print(f"{case['name']}: booster dry {dry:.0f} kg, propellant kept at MECO {reserve:.0f} kg ({100 * s1['reserve_fraction']:.1f} % of {s1['propellant_kg']:.0f} kg)")
    dv_avail = ve * math.log(m0 / dry)
    print(f"  Tsiolkovsky, all the reserve at vacuum Isp {isp:.0f} s: {dv_avail:.0f} m/s (sea-level Isp gives less)")

    results = []
    for sep_range_km in (0.0, 50.0, 100.0, 150.0):
        remaining = (a.impact_km - sep_range_km) * 1000.0
        gamma = solve_angle(a.sep_alt_km * 1000.0, a.sep_speed, remaining, m0, s1["drag_coefficient"], s1["reference_area_m2"])
        rng, v_imp, _ = ballistic(a.sep_alt_km * 1000.0, a.sep_speed, gamma, m0, s1["drag_coefficient"], s1["reference_area_m2"])
        ok = abs(rng - remaining) < 500.0
        vx, vz = a.sep_speed * math.cos(gamma), a.sep_speed * math.sin(gamma)
        print(f"  assumed downrange at separation {sep_range_km:5.0f} km: " + (
            f"flight-path angle {math.degrees(gamma):.1f} deg, horizontal {vx:.0f} m/s, vertical {vz:.0f} m/s, ballistic impact speed {v_imp:.0f} m/s"
            if ok else f"no angle up to 45 deg reaches {remaining / 1000:.0f} km (best {rng / 1000:.0f} km): inconsistent with the stated impact"))
        if ok:
            results.append((vx, v_imp))
    if not results:
        raise SystemExit("none of the assumed separation downrange distances is consistent with the stated impact distance")

    # Lower bounds on the needs, over the consistent assumptions: the smallest of each.
    land = min(v for _, v in results)
    rtls = min(x for x, _ in results)
    print(f"  landing burn, impulsive stop from the ballistic impact speed (gravity loss ignored): at least about {land:.0f} m/s")
    print(f"  boost-back to the launch site, cancelling the horizontal velocity only (the return itself adds more): at least about {rtls:.0f} m/s")
    need = land + rtls
    m_needed = dry * math.exp(need / ve)
    print(f"  both: {need:.0f} m/s -> {m_needed - dry:.0f} kg of propellant, {100 * (m_needed - dry) / s1['propellant_kg']:.1f} % of the first-stage load (the case keeps {100 * s1['reserve_fraction']:.1f} %)")
    print(f"  landing burn alone: {dry * (math.exp(land / ve) - 1):.0f} kg ({100 * dry * (math.exp(land / ve) - 1) / s1['propellant_kg']:.1f} % of the load); the reserve is {reserve:.0f} kg")
    print(f"  with the reserve of the case the landing burn is {'within' if dv_avail >= land else 'beyond'} reach and the boost-back to the launch site is {'within' if dv_avail >= need else 'beyond'} reach")
    # How much the stack would have to carry less to the staging point: the propellant not burned in
    # stage 1 is mass the stage carries to MECO, which the rocket equation charges to the whole stack.
    print("  a larger reserve means less first-stage burn: the upper stage separates slower, so every extra kilogram kept here has to be paid for in orbit insertion (not computed here).")


if __name__ == "__main__":
    main()
