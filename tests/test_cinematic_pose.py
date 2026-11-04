"""Scientific parity of the Cinematic View (M17): the pose it draws must be the record's.

Runs the Godot project in desktop/cinematic headless with --pose-dump at every sample time of a
recorded landing, at every midpoint between samples and outside the run, and compares what it prints
with an independent reimplementation of the technical view's interpolation (dom.js sampleAt and
lowerIndex, rocket.js slerp between samples i and i + 1).

Tolerances:
- pose computed in 64-bit floats (position_enu, quaternion_wxyz, axis_enu): 1e-9;
- drawn stage node read back from the scene (32-bit engine vectors): position 2e-3 m over a 3 km
  descent (a float32 step at 3 km is 2.4e-4 m), stage axis 2e-5;
- tilt of the drawn axis against the recorded tilt_deg at sample times: 2e-3 degrees.

Needs Godot 4.7.2: set VV_GODOT to the console executable (Godot_v4.7.2-stable_win64_console.exe).
Without it the test is skipped.
"""

import json
import math
import os
import subprocess
import unittest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PROJECT = os.path.join(REPO, "desktop", "cinematic")
RUN = os.path.join(REPO, "tests", "fixtures", "cinematic", "landing-run")


def lower_index(times, t):
    lo, hi = 0, len(times) - 1
    if hi < 0:
        return -1
    if t <= times[0]:
        return 0
    if t >= times[hi]:
        return hi
    while hi - lo > 1:
        mid = (lo + hi) >> 1
        if times[mid] <= t:
            lo = mid
        else:
            hi = mid
    return lo


def sample_at(times, values, t):
    i = lower_index(times, t)
    a = values[i]
    if i >= len(times) - 1 or t <= times[i]:
        return a
    b = values[i + 1]
    if a is None or b is None:
        return a
    return a + (b - a) * (t - times[i]) / ((times[i + 1] - times[i]) or 1)


def normalise(q):
    n = math.sqrt(sum(c * c for c in q))
    return [c / n for c in q] if n else [1.0, 0.0, 0.0, 0.0]


def slerp(a, b, t):
    """three.js r170 Quaternion.slerp on [w, x, y, z]."""
    if t == 0:
        return list(a)
    if t == 1:
        return list(b)
    c = sum(x * y for x, y in zip(a, b))
    if c < 0:
        b = [-x for x in b]
        c = -c
    if c >= 1.0:
        return list(a)
    s2 = 1.0 - c * c
    if s2 <= 2.220446049250313e-16:
        return normalise([(1 - t) * x + t * y for x, y in zip(a, b)])
    s = math.sqrt(s2)
    h = math.atan2(s, c)
    ra, rb = math.sin((1 - t) * h) / s, math.sin(t * h) / s
    return [x * ra + y * rb for x, y in zip(a, b)]


def rotate(q, v):
    w, x, y, z = q
    tx, ty, tz = 2 * (y * v[2] - z * v[1]), 2 * (z * v[0] - x * v[2]), 2 * (x * v[1] - y * v[0])
    return [v[0] + w * tx + (y * tz - z * ty), v[1] + w * ty + (z * tx - x * tz), v[2] + w * tz + (x * ty - y * tx)]


def expected(times, ch, t):
    i = lower_index(times, t)
    pos = [sample_at(times, ch[k], t) for k in ("base_x", "base_y", "altitude")]
    qa = normalise([ch[k][i] for k in ("q_w", "q_x", "q_y", "q_z")])
    if i < len(times) - 1 and ch["q_w"][i + 1] is not None:
        qb = normalise([ch[k][i + 1] for k in ("q_w", "q_x", "q_y", "q_z")])
        f = min(1.0, max(0.0, (t - times[i]) / ((times[i + 1] - times[i]) or 1)))
        q = slerp(qa, qb, f)
    else:
        q = qa
    return i, pos, q


class CinematicPoseParity(unittest.TestCase):
    def setUp(self):
        self.godot = os.environ.get("VV_GODOT", "")
        if not self.godot or not os.path.isfile(self.godot):
            self.skipTest("VV_GODOT is not set to a Godot 4.7.2 console executable")

    def test_drawn_pose_is_the_recorded_pose(self):
        with open(os.path.join(RUN, "record.json"), encoding="utf-8") as f:
            rec = json.load(f)
        times = rec["timebases"]["trace"]
        ch = {c["id"]: c["values"] for c in rec["channels"]}
        ts = list(times) + [(a + b) / 2 for a, b in zip(times, times[1:])] + [times[0] - 1.0, times[-1] + 5.0]
        out = subprocess.run(
            [self.godot, "--headless", "--path", PROJECT, "--", "--run", RUN, "--pose-dump", ",".join(repr(t) for t in ts)],
            capture_output=True, text=True, timeout=180, encoding="utf-8", errors="replace",
        )
        self.assertEqual(out.returncode, 0, out.stderr[-2000:])
        poses = [json.loads(line[5:]) for line in out.stdout.splitlines() if line.startswith("POSE ")]
        self.assertEqual(len(poses), len(ts))
        samples = set(times)
        for t, p in zip(ts, poses):
            # Godot's String.to_float may differ from the decimal text in the last bit: compare the
            # pose at the instant Godot actually used.
            self.assertAlmostEqual(p["t"], t, delta=1e-12)
            t = p["t"]
            i, pos, q = expected(times, ch, t)
            self.assertEqual(p["index"], i)
            for a, b in zip(p["position_enu"], pos):
                self.assertAlmostEqual(a, b, delta=1e-9, msg=f"position at t={t}")
            for a, b in zip(p["quaternion_wxyz"], q):
                self.assertAlmostEqual(a, b, delta=1e-9, msg=f"attitude at t={t}")
            axis = rotate(q, [1.0, 0.0, 0.0])
            for a, b in zip(p["axis_enu"], axis):
                self.assertAlmostEqual(a, b, delta=1e-9, msg=f"axis at t={t}")
            for a, b in zip(p["drawn_position_enu"], pos):
                self.assertAlmostEqual(a, b, delta=2e-3, msg=f"drawn position at t={t}")
            for a, b in zip(p["drawn_axis_enu"], axis):
                self.assertAlmostEqual(a, b, delta=2e-5, msg=f"drawn axis at t={t}")
            if t in samples:
                # atan2 rather than acos: near vertical, acos of a 32-bit component is ill-conditioned.
                for key in ("axis_enu", "drawn_axis_enu"):
                    a = p[key]
                    tilt = math.degrees(math.atan2(math.hypot(a[0], a[1]), a[2]))
                    self.assertAlmostEqual(tilt, ch["tilt_deg"][i], delta=2e-3, msg=f"{key} tilt at t={t}")

    def test_bad_arguments_are_refused(self):
        out = subprocess.run([self.godot, "--headless", "--path", PROJECT, "--", "--run", RUN, "--pose-dump", "x"],
                             capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace")
        self.assertEqual(out.returncode, 2)
        self.assertNotIn("POSE ", out.stdout)


if __name__ == "__main__":
    unittest.main()
