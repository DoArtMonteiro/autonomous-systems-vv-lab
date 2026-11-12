"""Independent 1D reference for a booster landing burn (order of magnitude, not the simulator's code).

A vertical point mass, uniform gravity, no drag, thrust along the vertical at sea-level performance
of the bundled first stage, 50 Hz control (the 20 ms logical step of `vv-ascent`). The controller is
the simplest one a boost-back-free landing needs: it sees only a noisy altitude and a noisy vertical
speed, lights the engine when the altitude estimate reaches the stopping height at the plan
deceleration, then commands the deceleration that brings the speed estimate to zero at the ground
(`a = v^2 / (2 h) + g`) within the throttle limits, and cuts when the speed estimate is no longer
downward. It answers two things:

1. the ideal bound: with exact knowledge, what touchdown speed does the throttle floor and the 20 ms
   quantisation leave (the stage cannot hover: its lowest thrust is a multiple of its weight);
2. how the touchdown speed grows with the altitude noise of the navigation solution (the ascent
   cases use 10 m per axis), which decides whether a landing needs its own altimeter.

Noise is drawn from `random.Random(seed)` with an explicit seed, so the output is reproducible. The
numbers are for the small bundled booster at a landing mass of its dry mass plus 600 kg (of the 810 kg the case keeps at MECO).

    python scripts/m18_booster_landing_1d.py
"""

import json
import math
import os
import random

G = 9.80665
DT = 0.02
HERE = os.path.dirname(os.path.abspath(__file__))
CASE = os.path.join(HERE, "..", "crates", "vv-ascent", "cases", "small-leo.json")


def load():
    with open(CASE, encoding="utf-8") as f:
        s = json.load(f)["vehicle"]["stages"][0]
    return s


def land(stage, landing_prop_kg, v0, h_alt_sigma, v_sigma, seed, h_start_extra=200.0):
    """One landing; returns (touchdown speed m/s or None, burn start altitude, propellant used kg, note)."""
    rng = random.Random(seed)
    isp, isp_sl = stage["isp_vac_s"], stage["isp_sl_s"]
    mdot_max = stage["thrust_vac_n"] / (isp * G)
    thrust_full = mdot_max * G * isp_sl  # sea level
    tmin, tmax = stage["throttle_min"], stage["throttle_max"]
    mass = stage["dry_mass_kg"] + landing_prop_kg
    prop = landing_prop_kg
    a_plan_throttle = 0.5 * (tmin + tmax)
    # Start high enough that the engine is lit by the controller, falling at v0.
    h = v0 * v0 / (2.0 * (a_plan_throttle * thrust_full / mass - G)) + h_start_extra
    v = -v0
    lit = False
    start_h = None
    used = 0.0
    while h > 0.0:
        h_est = h + rng.gauss(0.0, h_alt_sigma) if h_alt_sigma else h
        v_est = v + rng.gauss(0.0, v_sigma) if v_sigma else v
        throttle = 0.0
        if not lit and v_est < 0.0:
            a_plan = a_plan_throttle * thrust_full / mass - G
            if h_est <= v_est * v_est / (2.0 * a_plan):
                lit = True
                start_h = h
        if lit:
            if v_est >= -0.1 or prop <= 0.0:
                lit = False
            else:
                hh = max(h_est, 0.5)
                a_cmd = v_est * v_est / (2.0 * hh) + G
                throttle = min(max(a_cmd * mass / thrust_full, tmin), tmax)
        thrust = throttle * thrust_full if prop > 0.0 else 0.0
        a = thrust / mass - G
        h_next = h + v * DT + 0.5 * a * DT * DT
        v_next = v + a * DT
        if throttle > 0.0 and prop > 0.0:
            dm = throttle * mdot_max * DT
            prop = max(prop - dm, 0.0)
            used += dm
            mass = stage["dry_mass_kg"] + prop
        if h_next <= 0.0:
            f = h / (h - h_next) if h != h_next else 1.0
            return -(v + f * (v_next - v)), start_h, used, "touchdown"
        if lit is False and start_h is not None and v_next >= 0.0:
            # Stopped above the ground with the engine cut: the rest is a free fall from h_next.
            vt = math.sqrt(2.0 * G * h_next)
            return vt, start_h, used, f"stopped {h_next:.1f} m above the ground, free fall"
        h, v = h_next, v_next
    return 0.0, start_h, used, "touchdown"


def summarise(stage, label, **kw):
    runs = [land(stage, seed=1000 + i, **kw) for i in range(200)]
    speeds = sorted(r[0] for r in runs)
    stopped = sum(1 for r in runs if r[3] != "touchdown")
    print(f"  {label}: touchdown speed median {speeds[100]:.1f} m/s, 90th percentile {speeds[180]:.1f} m/s, worst {speeds[-1]:.1f} m/s; stopped above the ground in {stopped} of 200")


def main():
    s = load()
    dry = s["dry_mass_kg"]
    landing_prop = 600.0
    mass = dry + landing_prop
    t_min = s["throttle_min"] * s["thrust_vac_n"] * s["isp_sl_s"] / s["isp_vac_s"]
    t_max = s["throttle_max"] * s["thrust_vac_n"] * s["isp_sl_s"] / s["isp_vac_s"]
    print(f"small-leo first stage, landing mass {mass:.0f} kg: sea-level thrust {t_min / 1000:.0f} to {t_max / 1000:.0f} kN, i.e. {t_min / (mass * G):.1f} to {t_max / (mass * G):.1f} times its weight; it cannot hover")
    print("  net deceleration range: %.0f to %.0f m/s^2; one 20 ms tick changes the speed by %.1f to %.1f m/s" % (
        t_min / mass - G, t_max / mass - G, (t_min / mass - G) * DT, (t_max / mass - G) * DT))
    v0 = 300.0
    print(f"  from {v0:.0f} m/s downward:")
    summarise(s, "exact altitude and speed", landing_prop_kg=landing_prop, v0=v0, h_alt_sigma=0.0, v_sigma=0.0)
    for sigma in (0.1, 0.5, 2.0, 10.0):
        summarise(s, f"altitude noise {sigma:>4} m, speed noise 0.1 m/s", landing_prop_kg=landing_prop, v0=v0, h_alt_sigma=sigma, v_sigma=0.1)
    ideal = land(s, landing_prop_kg=landing_prop, v0=v0, h_alt_sigma=0.0, v_sigma=0.0, seed=1)
    print(f"  propellant of the ideal burn: {ideal[2]:.0f} kg for {v0:.0f} m/s (Tsiolkovsky for {v0:.0f} m/s at sea-level Isp from the landing mass: {mass * (1 - math.exp(-v0 / (s['isp_sl_s'] * G))):.0f} kg, gravity loss excluded)")


if __name__ == "__main__":
    main()
