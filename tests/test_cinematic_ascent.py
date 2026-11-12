"""Parity and refusal tests of the Cinematic View's launch ascent reader (vv-run.v2).

The renderer is run headless with --pose-dump on a reduced real record (tests/fixtures/cinematic/
ascent-run/record.json: the small-leo launcher, seed 5000, three entities: stack, booster, upper) and
what it prints is compared with an independent Python reimplementation of the rule of the Studio's
ascent view (desktop/studio/ui/js/scenes/ascent.js and dom.js):

- an entity exists from its first to its last sample, so the stack disappears at separation and the
  booster and the upper stage appear at their t_start, as recorded;
- its position is the curved plane of the record's altitude and downrange (x = rho sin(theta),
  y = rho cos(theta) - R, theta = downrange / R) of the two samples around t, interpolated linearly;
  a null at either sample returns the earlier sample (dom.js sampleAt);
- the body axis is along the recorded velocity (speed and radial velocity), vertical below 1 m/s.

Tolerances: 64-bit position 1e-6 m (kilometres to metres), axis 1e-8 (the axis of a nearly vertical body divides by a small difference of squares); the node read back from the
scene (32-bit vectors, no floating origin) 0.3 m at up to 2.5e6 m from the origin and 2e-5 for the axis.
Needs Godot 4.7.2: set VV_GODOT to the console executable; without it the tests are skipped.
"""

import copy
import json
import math
import os
import shutil
import subprocess
import tempfile
import unittest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PROJECT = os.path.join(REPO, "desktop", "cinematic")
RUN = os.path.join(REPO, "tests", "fixtures", "cinematic", "ascent-run")
V1_RUN = os.path.join(REPO, "tests", "fixtures", "cinematic", "landing-run")


def lower_index(times, t):
    lo, hi = 0, len(times) - 1
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
    f = (t - times[i]) / ((times[i + 1] - times[i]) or 1)
    return a + (b - a) * f


def reference(rec, t):
    """Per entity: None when not existing, else (position_enu, axis_enu, throttle)."""
    R = rec["scene"]["earth_radius_km"]
    ch = {c["id"]: c["values"] for c in rec["channels"]}
    out = {}
    for se in rec["scene"]["entities"]:
        tms = rec["timebases"][se["timebase"]]
        if not (tms[0] <= t <= tms[-1]):
            out[se["id"]] = None
            continue
        alt, dr = ch[se["altitude"]], ch[se["downrange"]]
        px, py = [], []
        for a, d in zip(alt, dr):
            if a is None or d is None:
                px.append(None)
                py.append(None)
            else:
                th = d / R
                rho = R + a
                px.append(rho * math.sin(th))
                py.append(rho * math.cos(th) - R)
        x, y = sample_at(tms, px, t), sample_at(tms, py, t)
        if x is None or y is None:
            out[se["id"]] = None
            continue
        sp = sample_at(tms, ch[se["id"] + "_speed_m_s"], t)
        vr = sample_at(tms, ch[se["id"] + "_radial_velocity_m_s"], t)
        d_t = sample_at(tms, dr, t)
        th = d_t / R if d_t is not None else 0.0
        if sp is None or vr is None or sp < 1.0:
            ax = (math.sin(th), math.cos(th))
        else:
            vr = max(-sp, min(sp, vr))
            h = math.sqrt(max(sp * sp - vr * vr, 0.0))
            ax = ((vr * math.sin(th) + h * math.cos(th)) / sp, (vr * math.cos(th) - h * math.sin(th)) / sp)
        thr = sample_at(tms, ch[se["id"] + "_throttle"], t)
        out[se["id"]] = ([x * 1000.0, 0.0, y * 1000.0], [ax[0], 0.0, ax[1]], thr)
    return out


def run_godot(godot, run_dir, extra, timeout=300):
    return subprocess.run([godot, "--headless", "--path", PROJECT, "--", "--run", run_dir, *extra],
                          capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")


def dump(godot, run_dir, times):
    rows = []
    for i in range(0, len(times), 200):
        chunk = times[i:i + 200]
        out = run_godot(godot, run_dir, ["--pose-dump", ",".join(repr(t) for t in chunk)])
        assert out.returncode == 0, out.stderr[-1500:]
        for line in out.stdout.splitlines():
            if line.startswith("POSE2 "):
                rows.append(json.loads(line[6:]))
    return rows


class AscentRecord(unittest.TestCase):
    def setUp(self):
        self.godot = os.environ.get("VV_GODOT", "")
        if not self.godot or not os.path.isfile(self.godot):
            self.skipTest("VV_GODOT is not set to a Godot 4.7.2 console executable")
        with open(os.path.join(RUN, "record.json"), encoding="utf-8") as f:
            self.rec = json.load(f)

    def times_to_check(self, rec):
        ts = set()
        for tms in rec["timebases"].values():
            if len(tms) < 1500:
                for a, b in zip(tms, tms[1:]):
                    ts.add(a)
                    ts.add((a + b) / 2.0)
                ts.add(tms[-1])
        ts.update([-5.0, 1.0e5])
        for e in rec["entities"]:
            ts.update([e["t_start"] - 1e-6, e["t_start"] + 1e-6, e["t_end"] - 1e-6, e["t_end"] + 1e-6])
        return sorted(ts)

    def check(self, rec, run_dir):
        times = self.times_to_check(rec)
        rows = dump(self.godot, run_dir, times)
        self.assertEqual(len(rows), len(times))
        seen = {"stack": 0, "booster": 0, "upper": 0}
        for t, row in zip(times, rows):
            ref = reference(rec, t)
            got = {e["id"]: e for e in row["entities"]}
            for eid, r in ref.items():
                g = got[eid]
                if r is None:
                    self.assertFalse(g["active"], f"{eid} at t={t} must not exist")
                    continue
                self.assertTrue(g["active"], f"{eid} at t={t} must exist")
                seen[eid] += 1
                for k in range(3):
                    self.assertAlmostEqual(g["position_enu"][k], r[0][k], delta=1e-6, msg=f"{eid} position {k} at t={t}")
                    self.assertAlmostEqual(g["axis_enu"][k], r[1][k], delta=1e-8, msg=f"{eid} axis {k} at t={t}")
                    self.assertAlmostEqual(g["drawn_position_enu"][k], r[0][k], delta=0.3, msg=f"{eid} drawn position {k} at t={t}")
                    self.assertAlmostEqual(g["drawn_axis_enu"][k], r[1][k], delta=2e-5, msg=f"{eid} drawn axis {k} at t={t}")
        return seen

    def test_every_entity_pose_is_the_recorded_pose(self):
        seen = self.check(self.rec, RUN)
        self.assertTrue(all(n > 100 for n in seen.values()), seen)

    def test_entities_exist_only_between_their_first_and_last_sample(self):
        rows = dump(self.godot, RUN, [0.0, 100.0, 152.7, 152.8, 153.0, 700.0, 1036.0, 1037.0])
        on = lambda i: {e["id"] for e in rows[i]["entities"] if e["active"]}
        self.assertEqual(on(0), {"stack"})
        self.assertEqual(on(1), {"stack"})
        self.assertEqual(on(2), {"stack"})          # the children start at 152.70000000000002
        self.assertEqual(on(3), {"booster", "upper"})  # the stack is gone at separation
        self.assertEqual(on(4), {"booster", "upper"})
        self.assertEqual(on(5), {"upper"})          # the booster ended at its impact
        self.assertEqual(on(6), {"upper"})
        self.assertEqual(on(7), set())

    def test_null_samples_follow_the_gap_rule(self):
        rec = copy.deepcopy(self.rec)
        for c in rec["channels"]:
            if c["id"] == "upper_altitude_km":
                for i in (10, 11, 40):
                    c["values"][i] = None
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "run"))
            with open(os.path.join(tmp, "run", "record.json"), "w", encoding="utf-8") as f:
                json.dump(rec, f)
            times = []
            tms = rec["timebases"]["upper"]
            for i in (9, 10, 11, 12, 39, 40, 41):
                times += [tms[i], (tms[i] + tms[i + 1]) / 2.0]
            rows = dump(self.godot, os.path.join(tmp, "run"), times)
            for t, row in zip(times, rows):
                ref = reference(rec, t)["upper"]
                got = {e["id"]: e for e in row["entities"]}["upper"]
                if ref is None:
                    self.assertFalse(got["active"], t)
                else:
                    self.assertTrue(got["active"], t)
                    for k in range(3):
                        self.assertAlmostEqual(got["position_enu"][k], ref[0][k], delta=1e-6, msg=f"t={t}")


class MalformedAscentRecords(unittest.TestCase):
    def setUp(self):
        self.godot = os.environ.get("VV_GODOT", "")
        if not self.godot or not os.path.isfile(self.godot):
            self.skipTest("VV_GODOT is not set to a Godot 4.7.2 console executable")
        with open(os.path.join(RUN, "record.json"), encoding="utf-8") as f:
            self.rec = json.load(f)

    def refused(self, mutate, needle, base=None):
        rec = copy.deepcopy(base or self.rec)
        mutate(rec)
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "record.json"), "w", encoding="utf-8") as f:
                json.dump(rec, f)
            out = run_godot(self.godot, tmp, ["--pose-dump", "1.0"], timeout=120)
        self.assertEqual(out.returncode, 3, out.stderr[-800:])
        self.assertIn(needle, out.stderr)
        self.assertNotIn("POSE2", out.stdout)

    def test_unknown_entity(self):
        def m(r):
            r["scene"]["entities"][1]["id"] = "ghost"
        self.refused(m, "unknown entity")

    def test_short_channel(self):
        def m(r):
            for c in r["channels"]:
                if c["id"] == "booster_altitude_km":
                    c["values"].pop()
        self.refused(m, "values for the")

    def test_channel_value_that_is_not_a_number(self):
        def m(r):
            for c in r["channels"]:
                if c["id"] == "booster_speed_m_s":
                    c["values"][3] = "fast"
        self.refused(m, "neither a number nor null")

    def test_position_channel_value_that_is_not_a_number(self):
        def m(r):
            for c in r["channels"]:
                if c["id"] == "stack_altitude_km":
                    c["values"][2] = True
        self.refused(m, "neither a number nor null")

    def test_unknown_timebase(self):
        def m(r):
            r["scene"]["entities"][2]["timebase"] = "nowhere"
        self.refused(m, "unknown timebase")

    def test_parent_not_declared_before(self):
        def m(r):
            r["scene"]["entities"][1]["parent"] = "upper"
        self.refused(m, "parent")

    def test_missing_entities(self):
        def m(r):
            del r["entities"]
        self.refused(m, "needs entities")

    def test_missing_channel_of_an_entity(self):
        def m(r):
            r["channels"] = [c for c in r["channels"] if c["id"] != "stack_downrange_km"]
        self.refused(m, "needs channel")

    def test_decreasing_timebase(self):
        def m(r):
            r["timebases"]["stack"][5] = 0.0
        self.refused(m, "strictly increasing")

    def test_v1_record_with_entities(self):
        with open(os.path.join(V1_RUN, "record.json"), encoding="utf-8") as f:
            v1 = json.load(f)

        def m(r):
            r["entities"] = []
        self.refused(m, "cannot have entities", base=v1)


if __name__ == "__main__":
    unittest.main()
