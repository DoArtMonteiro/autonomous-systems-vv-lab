"""Gate for a downrange powered landing of the vv-ascent booster: a Python 2D point-mass reference.

Not the simulator's code. The thresholds, the zone, the noise and the seed sets are frozen in
`scripts/data/m18_booster_gate_frozen.json` (committed before any tuning); this script reads them and
refuses to run if they are edited after the freeze hash printed below was recorded in the report.

The true vehicle is the first stage with the dispersion factors recorded from real `vv-ascent` runs,
starting from the recorded true separation state. The guidance sees only a noisy navigation solution
(and, if declared, a noisy landing altimeter) and the nominal vehicle: it predicts the landing point
with the model atmosphere, trims it onto the zone centre with a short horizontal burn of one engine,
coasts, then lands with a constant-deceleration vertical law and a quadratic lateral law (the lit
number of engines follows the thrust it needs).

    python scripts/m18_booster_gate.py --vehicle small-leo --seeds tuning
    python scripts/m18_booster_gate.py --vehicle small-leo --seeds held-out        (once)
"""

import argparse
import hashlib
import json
import math
import os
import random

MU = 3.986004418e14
R = 6_371_000.0
G0 = 9.80665
RHO0 = 1.225
H = 8500.0

HERE = os.path.dirname(os.path.abspath(__file__))
FROZEN = os.path.join(HERE, "data", "m18_booster_gate_frozen.json")
STATES = os.path.join(HERE, "data", "m18_booster_gate_states.json")
CASES = {
    "small-leo": os.path.join(HERE, "..", "crates", "vv-ascent", "cases", "small-leo.json"),
    "medium-leo": os.path.join(HERE, "..", "crates", "vv-ascent", "cases", "medium-leo.json"),
}
DT_FINE = 0.02
DT_COARSE = 0.5
DEBUG = False


# ---------------------------------------------------------------- dynamics

def isp_of(vac, sl, pr):
    return vac - (vac - sl) * pr


def deriv(s, mdot, dx, dz, isp_vac, isp_sl, cdA):
    x, z, vx, vz, m = s
    r = math.hypot(x, z)
    alt = max(r - R, 0.0)
    pr = math.exp(-alt / H)
    g = -MU / (r * r * r)
    v = math.hypot(vx, vz)
    kd = -0.5 * RHO0 * pr * v * cdA / m
    kt = mdot * G0 * isp_of(isp_vac, isp_sl, pr) / m
    return (vx, vz, g * x + kd * vx + kt * dx, g * z + kd * vz + kt * dz, -mdot)


def rk4(s, mdot, dx, dz, isp_vac, isp_sl, cdA, dt):
    k1 = deriv(s, mdot, dx, dz, isp_vac, isp_sl, cdA)
    s2 = tuple(a + 0.5 * dt * b for a, b in zip(s, k1))
    k2 = deriv(s2, mdot, dx, dz, isp_vac, isp_sl, cdA)
    s3 = tuple(a + 0.5 * dt * b for a, b in zip(s, k2))
    k3 = deriv(s3, mdot, dx, dz, isp_vac, isp_sl, cdA)
    s4 = tuple(a + dt * b for a, b in zip(s, k3))
    k4 = deriv(s4, mdot, dx, dz, isp_vac, isp_sl, cdA)
    w = dt / 6.0
    return tuple(a + w * (b + 2 * c + 2 * d + e) for a, b, c, d, e in zip(s, k1, k2, k3, k4))


def altitude(x, z):
    return math.hypot(x, z) - R


def downrange(x, z):
    return R * math.atan2(x, z)


# ---------------------------------------------------------------- vehicle and guidance parameters

class Params:
    """Guidance and declared case parameters: the only things tuning may change."""

    def __init__(self, **kw):
        self.n_engines = 9
        self.altimeter_sigma_m = None  # None: no landing altimeter
        self.flip_delay_s = 10.0
        self.trim_tolerance_m = 300.0
        self.trim_throttle_min = True
        self.plan_share = 0.6  # share of the full thrust of all engines assumed for the ignition height
        self.ignition_margin = 1.0
        self.touchdown_target_m_s = 1.0
        self.tilt_tan_max = 3.0
        self.ignition_max_alt_m = 6000.0
        self.lateral_hold_s = 2.0
        self.terminal_alt_m = 10.0
        self.terminal_gain = 3.0
        self.terminal_position_gain = 0.1
        self.t_go_min_s = 0.5
        self.cut_speed_m_s = 0.2
        for k, v in kw.items():
            if not hasattr(self, k):
                raise KeyError(k)
            setattr(self, k, v)


class Vehicle:
    def __init__(self, case, state, p):
        s1 = case["vehicle"]["stages"][0]
        self.n = p.n_engines
        self.nom = dict(dry=s1["dry_mass_kg"], thrust_vac=s1["thrust_vac_n"], isp_vac=s1["isp_vac_s"], isp_sl=s1["isp_sl_s"],
                        tmin=s1["throttle_min"], tmax=s1["throttle_max"], cdA=s1["drag_coefficient"] * s1["reference_area_m2"],
                        load=s1["propellant_kg"], reserve=s1["reserve_fraction"])
        f = state["stage1_factors"]
        self.true = dict(dry=state["mass_kg"] - state["propellant_kg"], thrust_vac=s1["thrust_vac_n"] * f["thrust"],
                         isp_vac=s1["isp_vac_s"] * f["isp"], isp_sl=s1["isp_sl_s"] * f["isp"])


# ---------------------------------------------------------------- guidance

class Guidance:
    ALPHA_R = 0.02
    ALPHA_V = 0.1
    ALPHA_ALT = 0.5

    def __init__(self, veh, p, target_m, t0):
        self.veh, self.p, self.target = veh, p, target_m
        n = veh.nom
        self.unit_mdot = n["thrust_vac"] / (veh.n * n["isp_vac"] * G0)
        self.prop_est = n["load"] * n["reserve"]
        self.est = None
        self.mode = "wait"
        self.t0 = t0
        self.cmd = (0, 0.0, 0.0, 0.0)  # engines, throttle, dx, dz
        self.trims = 0
        self.trim_dir = 0.0
        self.trim_s = 0.0
        self.trim_e0 = 0.0
        self.trim_dv = 0.0
        self.log = []

    # nominal model
    def mass(self):
        return self.veh.nom["dry"] + self.prop_est

    def mdot_of(self, cmd):
        k, thr = cmd[0], cmd[1]
        return k * thr * self.unit_mdot if thr > 0.0 else 0.0

    def propagate(self, est, cmd, dt):
        n = self.veh.nom
        s = (est[0], est[1], est[2], est[3], self.mass())
        s = rk4(s, self.mdot_of(cmd), cmd[2], cmd[3], n["isp_vac"], n["isp_sl"], n["cdA"], dt)
        return s[:4]

    def filter(self, obs, dt, alt_meas):
        if self.est is None:
            self.est = list(obs)
            return
        e = self.propagate(self.est, self.cmd, dt)
        ar = 1.0 - (1.0 - self.ALPHA_R) ** (dt / DT_FINE)
        av = 1.0 - (1.0 - self.ALPHA_V) ** (dt / DT_FINE)
        e = [e[0] + (obs[0] - e[0]) * ar, e[1] + (obs[1] - e[1]) * ar, e[2] + (obs[2] - e[2]) * av, e[3] + (obs[3] - e[3]) * av]
        if alt_meas is not None:
            aa = 1.0 - (1.0 - self.ALPHA_ALT) ** (dt / DT_FINE)
            rn = math.hypot(e[0], e[1])
            d = (alt_meas - (rn - R)) * aa
            e[0] += e[0] / rn * d
            e[1] += e[1] / rn * d
        self.est = e

    def t_full(self, alt):
        n = self.veh.nom
        pr = math.exp(-max(alt, 0.0) / H)
        return self.veh.n * self.unit_mdot * G0 * isp_of(n["isp_vac"], n["isp_sl"], pr) * n["tmax"]

    def law(self, x, z, vx, vz, target):
        """Landing thrust acceleration (up, horizontal) by the polynomial (E-guidance) law per axis,
        a = 6 (pT - p) / t^2 - 4 v / t - 2 vT / t, with the vertical stop time t = 2 h / (vd + vt).
        `target` None: the horizontal speed is only brought to zero (no position term)."""
        p = self.p
        r = math.hypot(x, z)
        alt = r - R
        up = (x / r, z / r)
        vr = vx * up[0] + vz * up[1]
        vh = vx * up[1] - vz * up[0]
        vd, vt = -vr, p.touchdown_target_m_s
        g = MU / (r * r)
        if alt <= p.terminal_alt_m:
            # terminal descent: hold the descent speed and null the horizontal speed
            a_up = max(g + p.terminal_gain * (-vt - vr), 0.0)
            v_cmd = min(max(p.terminal_position_gain * (target - downrange(x, z)), -0.5), 0.5) if target is not None else 0.0
            return a_up, p.terminal_gain * (v_cmd - vh), 1.0
        h = max(alt - p.terminal_alt_m, 0.3)
        t_go = max(2.0 * h / max(vd + vt, 0.1), p.t_go_min_s)
        a_up = max(6.0 * (0.0 - h) / (t_go * t_go) - 4.0 * vr / t_go + 2.0 * vt / t_go + g, 0.0)
        if target is None:
            a_x = -vh / t_go
        elif t_go > p.lateral_hold_s:
            a_x = 6.0 * (target - downrange(x, z)) / (t_go * t_go) - 4.0 * vh / t_go
        else:
            a_x = -2.0 * vh / t_go
        lim = p.tilt_tan_max * max(a_up, 1e-3)
        return a_up, min(max(a_x, -lim), lim), t_go

    def plan_burn(self, s):
        """Nominal simulation of the landing burn from state s=(x, z, vx, vz, m) with the landing law:
        (peak share of the full thrust of all engines, landing point arc distance, propellant, ok)."""
        n = self.veh.nom
        peak = 0.0
        used = 0.0
        dt = 0.05
        for _ in range(1200):
            x, z, vx, vz, m = s
            r = math.hypot(x, z)
            alt = r - R
            up = (x / r, z / r)
            vr = vx * up[0] + vz * up[1]
            if vr >= -self.p.cut_speed_m_s or alt < 0.0:
                break
            a_up, a_x, _ = self.law(x, z, vx, vz, None)
            a = math.hypot(a_up, a_x)
            peak = max(peak, a * m / self.t_full(alt))
            pr = math.exp(-max(alt, 0.0) / H)
            mdot = a * m / (G0 * isp_of(n["isp_vac"], n["isp_sl"], pr))
            dxv = (up[0] * a_up + up[1] * a_x) / a if a > 0 else 0.0
            dzv = (up[1] * a_up - up[0] * a_x) / a if a > 0 else 0.0
            s = rk4(s, mdot, dxv, dzv, n["isp_vac"], n["isp_sl"], n["cdA"], dt)
            used += mdot * dt
        return peak, downrange(s[0], s[1]), used

    def ignite(self, s):
        """The landing burn starts when the planned burn from the estimated state would need the plan
        share of the full thrust of all engines (drag included, nominal vehicle)."""
        x, z, vx, vz, m = s
        r = math.hypot(x, z)
        alt = r - R
        if (vx * x + vz * z) / r >= 0.0 or alt > self.p.ignition_max_alt_m:
            return False, 0.0
        peak, land, used = self.plan_burn(s)
        return peak >= self.p.plan_share, land

    def predict(self, est):
        """Landing point (arc distance, m) of the estimated state: ballistic descent until the landing
        burn would start, then the planned burn."""
        n = self.veh.nom
        mass = self.mass()
        s = (est[0], est[1], est[2], est[3], mass)
        for _ in range(4000):
            alt = altitude(s[0], s[1])
            go, land = self.ignite(s)
            if go:
                return land
            dt = 2.0 if alt > 30000.0 else (0.25 if alt > self.p.ignition_max_alt_m else 0.1)
            s = rk4(s, 0.0, 0.0, 0.0, n["isp_vac"], n["isp_sl"], n["cdA"], dt)
            if altitude(s[0], s[1]) < 0.0:
                return downrange(s[0], s[1])
        return downrange(s[0], s[1])
    def thrust_command(self, a_vec_up, a_vec_hz, up, hz, alt):
        """Engines and throttle for a thrust acceleration (components along up and hz)."""
        n = self.veh.nom
        a = math.hypot(a_vec_up, a_vec_hz)
        t_req = a * self.mass()
        pr = math.exp(-max(alt, 0.0) / H)
        tu = self.unit_mdot * G0 * isp_of(n["isp_vac"], n["isp_sl"], pr)
        k = min(max(math.ceil(t_req / (tu * n["tmax"])), 1), self.veh.n)
        thr = min(max(t_req / (k * tu), n["tmin"]), n["tmax"])
        dx = up[0] * a_vec_up + hz[0] * a_vec_hz
        dz = up[1] * a_vec_up + hz[1] * a_vec_hz
        nn = math.hypot(dx, dz)
        return (k, thr, dx / nn, dz / nn)

    def step(self, t, obs, dt, alt_meas):
        p, n = self.p, self.veh.nom
        self.filter(obs, dt, alt_meas)
        x, z, vx, vz = self.est
        r = math.hypot(x, z)
        alt = r - R
        up = (x / r, z / r)
        hz = (up[1], -up[0])
        vr = vx * up[0] + vz * up[1]
        vh = vx * hz[0] + vz * hz[1]
        cmd = (0, 0.0, 0.0, 0.0)
        if self.mode == "wait" and t >= self.t0 + p.flip_delay_s:
            self.mode = "trim_plan"
        if self.mode == "trim_plan":
            e0 = self.predict(self.est) - self.target
            if abs(e0) <= p.trim_tolerance_m or self.trims >= 2:
                self.mode = "coast"
            else:
                probe = 5.0
                e1 = self.predict((x + 0.0, z, vx + probe * hz[0], vz + probe * hz[1])) - self.target
                s_per_ms = (e1 - e0) / probe  # metres of landing point per m/s of horizontal speed
                self.trim_dir = -1.0 if e0 > 0.0 else 1.0
                self.trim_e0, self.trim_s, self.trim_dv = e0, s_per_ms, 0.0
                self.trims += 1
                self.mode = "trim"
                self.log.append(("trim_start", t, e0, s_per_ms))
        if self.mode == "trim":
            # one engine at its throttle floor, horizontal, until the linear prediction crosses the target
            unit_thrust = self.unit_mdot * G0 * isp_of(n["isp_vac"], n["isp_sl"], math.exp(-max(alt, 0.0) / H))
            thr = n["tmin"]
            a = thr * unit_thrust / self.mass()
            # moving horizontal speed by dv along trim_dir changes the landing point by s * dv * trim_dir
            e_now = self.trim_e0 + self.trim_s * self.trim_dv * self.trim_dir
            crossed = (self.trim_e0 > 0.0 and e_now <= 0.0) or (self.trim_e0 < 0.0 and e_now >= 0.0)
            if crossed or abs(e_now) <= p.trim_tolerance_m * 0.2 or self.prop_est <= 0.0:
                self.mode = "trim_check"
                self.t_check = t + 3.0
                self.log.append(("trim_end", t, e_now, self.trim_dv))
            else:
                cmd = (1, thr, hz[0] * self.trim_dir, hz[1] * self.trim_dir)
                self.trim_dv += a * dt
        if self.mode == "trim_check":
            if t >= self.t_check:
                self.mode = "trim_plan"
        if self.mode == "coast" and self.ignite((x, z, vx, vz, self.mass()))[0]:
            self.mode = "landing"
            self.log.append(("landing_start", t, alt, -vr, vh))
        if self.mode == "landing":
            if vr >= -p.cut_speed_m_s or self.prop_est <= 0.0:
                self.mode = "done"
                self.log.append(("landing_end", t, alt, -vr, vh))
            else:
                a_up, a_x, _ = self.law(x, z, vx, vz, self.target)
                cmd = self.thrust_command(a_up, a_x, up, hz, alt)
        mdot = self.mdot_of(cmd)
        self.prop_est = max(self.prop_est - mdot * dt, 0.0)
        self.cmd = cmd
        return cmd


# ---------------------------------------------------------------- one run

def run_one(case, case_name, state, seed, p, target_m):
    veh = Vehicle(case, state, p)
    tr = veh.true
    cdA = veh.nom["cdA"]
    rng = random.Random(seed * 7919 + (1 if case_name == "small-leo" else 2))
    sp, sv = 10.0, 0.1
    s = (state["x_m"], state["z_m"], state["vx_m_s"], state["vz_m_s"], state["mass_kg"])
    prop = state["propellant_kg"]
    unit_mdot_true = tr["thrust_vac"] / (veh.n * tr["isp_vac"] * G0)
    g = Guidance(veh, p, target_m, 0.0)
    t = 0.0
    peak_q = 0.0
    prop_used = 0.0
    depleted = False
    contact = None
    while t < 2000.0:
        alt_true = altitude(s[0], s[1])
        fine = g.mode not in ("wait", "coast") or alt_true < 40000.0 or g.cmd[1] > 0.0
        dt = DT_FINE if fine else DT_COARSE
        obs = (s[0] + rng.gauss(0, sp), s[1] + rng.gauss(0, sp), s[2] + rng.gauss(0, sv), s[3] + rng.gauss(0, sv))
        alt_meas = None
        if p.altimeter_sigma_m is not None and alt_true < 5000.0:
            alt_meas = alt_true + rng.gauss(0, p.altimeter_sigma_m)
        k, thr, dx, dz = g.step(t, obs, dt, alt_meas)
        if DEBUG and g.mode == "landing" and int(t / dt) % 25 == 0:
            rr = math.hypot(s[0], s[1])
            print(f"      t {t:.2f} alt {rr - R:.1f} vr {(s[2] * s[0] + s[3] * s[1]) / rr:.1f} vh {(s[2] * s[1] - s[3] * s[0]) / rr:.1f} k {k} thr {thr:.2f} est_alt {math.hypot(g.est[0], g.est[1]) - R:.1f} prop {prop:.0f}")
        mdot = 0.0
        if thr > 0.0 and prop > 0.0:
            mdot = min(k * thr * unit_mdot_true, prop / dt)
        v2 = s[2] * s[2] + s[3] * s[3]
        peak_q = max(peak_q, 0.5 * RHO0 * math.exp(-max(alt_true, 0.0) / H) * v2)
        prev = s
        s = rk4(s, mdot, dx, dz, tr["isp_vac"], tr["isp_sl"], cdA, dt)
        prop = max(prop - mdot * dt, 0.0)
        prop_used += mdot * dt
        if thr > 0.0 and prop <= 0.0:
            depleted = True
        t += dt
        if altitude(s[0], s[1]) < 0.0:
            a0 = altitude(prev[0], prev[1])
            f = a0 / (a0 - altitude(s[0], s[1]))
            xi = prev[0] + f * (s[0] - prev[0])
            zi = prev[1] + f * (s[1] - prev[1])
            vxi = prev[2] + f * (s[2] - prev[2])
            vzi = prev[3] + f * (s[3] - prev[3])
            r = math.hypot(xi, zi)
            up = (xi / r, zi / r)
            contact = dict(vertical=-(vxi * up[0] + vzi * up[1]), horizontal=abs(vxi * up[1] - vzi * up[0]),
                           error_m=downrange(xi, zi) - target_m, t_s=t)
            break
    if contact is None:
        raise RuntimeError("no contact")
    return dict(seed=seed, **contact, peak_q_pa=peak_q, prop_used_kg=prop_used, prop_left_kg=prop, depleted=depleted,
                trim_dv=g.trim_dv, trims=g.trims, log=g.log, outcome=state["outcome"])


def verdict(r, th):
    reasons = []
    if r["vertical"] > th["touchdown_vertical_speed_m_s_max"]:
        reasons.append(f"vertical {r['vertical']:.2f}")
    if r["horizontal"] > th["touchdown_horizontal_speed_m_s_max"]:
        reasons.append(f"horizontal {r['horizontal']:.2f}")
    if abs(r["error_m"]) > th["landing_zone_radius_m"]:
        reasons.append(f"position {r['error_m']:+.0f} m")
    if r["depleted"] or r["prop_left_kg"] <= 0.0:
        reasons.append("propellant depleted")
    return reasons


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vehicle", required=True, choices=sorted(CASES))
    ap.add_argument("--seeds", choices=["tuning", "held-out"], default="tuning")
    ap.add_argument("--set", action="append", default=[], help="Params override, name=value (value parsed as JSON)")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    with open(FROZEN, "rb") as f:
        raw = f.read()
    frozen = json.loads(raw)
    digest = hashlib.sha256(raw.replace(b'\r\n', b'\n')).hexdigest()[:16]
    print(f"frozen file sha256 {digest}")
    with open(CASES[a.vehicle], encoding="utf-8") as f:
        case = json.load(f)
    with open(STATES, encoding="utf-8") as f:
        states = json.load(f)["states"][a.vehicle]
    kw = {}
    for item in a.set:
        k, v = item.split("=", 1)
        kw[k] = json.loads(v)
    p = Params(**kw)
    global DEBUG
    DEBUG = a.verbose
    seeds = frozen["inputs"]["tuning_seeds" if a.seeds == "tuning" else "held_out_seeds"]
    target = frozen["landing_zone"]["centre_downrange_km"][a.vehicle] * 1000.0
    th = frozen["thresholds"]
    print(f"{a.vehicle}, {a.seeds} seeds, params {kw or 'default'}, zone centre {target / 1000:.0f} km radius {th['landing_zone_radius_m']:.0f} m")
    passed = 0
    for seed in seeds:
        r = run_one(case, a.vehicle, states[str(seed)], seed, p, target)
        why = verdict(r, th)
        passed += not why
        print(f"  seed {seed}: vertical {r['vertical']:.2f} m/s, horizontal {r['horizontal']:.2f} m/s, position {r['error_m']:+.1f} m, "
              f"propellant used {r['prop_used_kg']:.0f} kg left {r['prop_left_kg']:.0f} kg, peak q {r['peak_q_pa'] / 1000:.0f} kPa, trim dv {r['trim_dv']:.0f} m/s "
              f"-> {'PASS' if not why else 'FAIL ' + ', '.join(why)}")
        if a.verbose:
            for entry in r["log"]:
                print("     ", entry)
    print(f"  {passed} of {len(seeds)} seeds meet every threshold")


if __name__ == "__main__":
    main()
