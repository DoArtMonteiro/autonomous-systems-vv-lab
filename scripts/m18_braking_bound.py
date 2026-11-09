"""Independent bound for the M18 vehicle-design check (not the simulator's code).

A vertical point mass falls from the M9 initial state (3000 m, 200 m/s down) and brakes at FULL
thrust from the first instant, with the stage's own drag (exponential atmosphere, Cd and area of
the template) and no attitude losses. That is close to the best braking any controller could achieve (the
seed's initial dispersion and the centre-of-mass height are ignored), so its touchdown speed
should not exceed the simulated one: if even this braking cannot stop the stage, the simulator
must report a hard touchdown.

    python scripts/m18_braking_bound.py
"""

import math

G0 = 9.80665
DT = 0.001


def ideal_touchdown(dry_kg, prop_kg, thrust_n, isp_s, cd=0.8, area_m2=12.0, h0=3000.0, v0=-200.0):
    m, h, v, t = dry_kg + prop_kg, h0, v0, 0.0
    prop = prop_kg
    mdot = thrust_n / (isp_s * G0)
    while h > 0.0:
        f = thrust_n if prop > 0.0 else 0.0
        drag = 0.5 * 1.225 * math.exp(-h / 8500.0) * v * v * cd * area_m2
        a = (f + drag) / m - G0
        if v + a * DT >= 0.0 and f > 0.0:
            return {"stops_above_ground_m": round(h, 1), "t_s": round(t, 2)}
        h += v * DT + 0.5 * a * DT * DT
        v += a * DT
        if f > 0.0:
            m -= mdot * DT
            prop -= mdot * DT
        t += DT
    return {"touchdown_speed_mps": round(-v, 2), "t_s": round(t, 2), "propellant_left_kg": round(max(prop, 0.0), 1)}


if __name__ == "__main__":
    heavy = {"dry_kg": 30000.0, "prop_kg": 11000.0, "thrust_n": 760000.0, "isp_s": 300.0}
    for k in (1.0, 0.85, 0.75, 0.7):
        p = dict(heavy, thrust_n=heavy["thrust_n"] * k)
        tw = p["thrust_n"] / ((p["dry_kg"] + p["prop_kg"]) * G0)
        print(f"thrust x{k:<4} T/W {tw:.2f}: {ideal_touchdown(**p)}")
