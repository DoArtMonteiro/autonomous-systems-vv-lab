"""Checks of the Belief vs Truth prototype (spikes/m19-belief-truth).

What is checked, independently of the extractor's own code:

* the input files are the pinned ones (sha256), agree with the hashes the run declares, and are
  unchanged in git;
* data.json is exactly what a fresh extraction gives;
* every value in the view's data model resolves to a record pointer or to a named derivation that
  this test recomputes from the fixture with its own arithmetic;
* observations are not interpolated: the O series are exactly the recorded non-null points at the
  recorded times, and the line routine of the view refuses them;
* the rust source facts the view cites are at the lines it states;
* optionally, with a headless browser: every number in the rendered page belongs to a value button
  whose text is the data-model value formatted as declared, or is an axis scale label.

No simulation is run and no seed is used.
"""

from __future__ import annotations

import hashlib
import http.server
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPIKE = ROOT / "spikes" / "m19-belief-truth"
FIXTURE_REL = "desktop/domain-rocket/tests/fixtures/stored-by-0.15.0"
FIXTURE = ROOT / FIXTURE_REL

PINNED = {
    "case.json": "dc1301dd57ee4c9844e5fddeccf3ce4b2b288957fcad366b8833ee6d32219f94",
    "record.json": "69df6920f2cf957dcee591f872c305b7ae5b40c2d8a691bfd541f123cfdb0d44",
    "run.json": "b2d810736373fddf526f0e351a1815b3aaab3ff3c55350890e12acd8d98fd081",
    "trace.json": "97783cfc791b52f67fd86c28f03a3c6c10d678ca2e1a6a8f1813d2bca6529d06",
    "verification.json": "3d6f543e417e78a211af335e093b11765dd7f7517b19388c7657b010be1a4e6d",
}
CLASSES = {"T", "E", "O", "D-host", "D-view", "S", "C", "K"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pointer(docs: dict, ptr: str, null_parent: bool = False):
    name, _, path = ptr.partition("#")
    node = docs[name]
    for part in path.split("/")[1:]:
        if node is None and null_parent:
            return None
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


def x_axis_z(q):
    w, x, y, z = q
    return 2 * (x * z - w * y)


def x_axis(q):
    w, x, y, z = q
    return (1 - 2 * (y * y + z * z), 2 * (x * y + w * z), 2 * (x * z - w * y))


class Fixture:
    def __init__(self):
        self.docs = {n: json.loads((FIXTURE / n).read_text(encoding="utf-8")) for n in PINNED}
        self.docs["domain.json"] = json.loads((ROOT / "desktop/domain-rocket/domain.json").read_text(encoding="utf-8"))
        t = self.docs["trace.json"]
        self.samples = t["samples"]
        self.n = len(self.samples)
        self.case = self.docs["case.json"]
        veh = self.case["vehicle"]
        self.s_cm = [
            (veh["dry_mass_kg"] * veh["dry_cm_station_m"] + s["truth"]["propellant_kg"] * veh["propellant_cm_station_m"])
            / (veh["dry_mass_kg"] + s["truth"]["propellant_kg"])
            for s in self.samples
        ]


FX = Fixture()
DATA = json.loads((SPIKE / "data.json").read_text(encoding="utf-8"))


def approx(a, b, tol=1e-9):
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= tol * max(1.0, abs(b))


class Inputs(unittest.TestCase):
    def test_inputs_are_the_pinned_files(self):
        for name, h in PINNED.items():
            self.assertEqual(sha(FIXTURE / name), h, name)
            self.assertEqual(DATA["inputs"][name]["sha256"], h, name)

    def test_hashes_agree_with_what_the_run_declares(self):
        run = FX.docs["run.json"]
        self.assertEqual(run["case"]["sha256"], PINNED["case.json"])
        self.assertEqual(run["trace"]["sha256"], PINNED["trace.json"])
        self.assertEqual(run["verification"]["sha256"], PINNED["verification.json"])
        arts = {a["path"]: a for a in FX.docs["record.json"]["provenance"]["artifacts"]}
        for name in ("case.json", "run.json", "trace.json", "verification.json"):
            self.assertEqual(arts[name]["sha256"], PINNED[name], name)
            self.assertEqual(arts[name]["bytes"], (FIXTURE / name).stat().st_size, name)
        # record.json declares no hash of itself: it is pinned here, and the data says so.
        self.assertTrue(DATA["inputs"]["record.json"]["pinned_only"])
        self.assertNotIn("record.json", arts)

    def test_committed_fixture_is_unchanged(self):
        if shutil.which("git") is None:
            self.skipTest("git not available")
        out = subprocess.run(
            ["git", "status", "--porcelain", "--", FIXTURE_REL], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout
        self.assertEqual(out.strip(), "", "the fixture differs from the committed one")
        diff = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", FIXTURE_REL], cwd=ROOT)
        self.assertEqual(diff.returncode, 0)

    def test_data_json_is_a_fresh_extraction(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "data.json"
            subprocess.run(
                [sys.executable, "-I", str(SPIKE / "extract.py"), "--output", str(out)], check=True, capture_output=True
            )
            self.assertEqual(
                out.read_bytes(), (SPIKE / "data.json").read_bytes(),
                "data.json is stale: rerun python spikes/m19-belief-truth/extract.py and commit the result",
            )
        self.assertNotIn(b"\r", (SPIKE / "data.json").read_bytes())

    def test_source_files_are_the_ones_the_facts_were_read_from(self):
        for rel, h in DATA["source_files"].items():
            text_hash = hashlib.sha256((ROOT / rel).read_bytes().replace(bytes([13, 10]), bytes([10]))).hexdigest()
            self.assertEqual(
                text_hash, h,
                f"{rel} changed since data.json was extracted: rerun python spikes/m19-belief-truth/extract.py "
                "and review the source facts (the view cites line ranges of this file).",
            )


class Provenance(unittest.TestCase):
    def test_every_entry_has_a_class_and_exactly_one_origin(self):
        entries = list(DATA["series"].items()) + list(DATA["scalars"].items())
        self.assertGreater(len(entries), 100)
        for sid, e in entries:
            self.assertIn(e["cls"], CLASSES, sid)
            self.assertEqual(("ptr" in e) + ("derivation" in e), 1, f"{sid}: pointer xor derivation")
            for over in e.get("cls_by_index", {}).values():
                self.assertIn(over, CLASSES)

    def test_recorded_entries_resolve_to_the_record(self):
        for sid, e in DATA["series"].items():
            if "ptr" not in e:
                continue
            self.assertEqual(len(e["values"]), FX.n, sid)
            for i in range(FX.n):
                want = pointer(FX.docs, e["ptr"].format(i=i), e.get("null_parent", False))
                self.assertEqual(e["values"][i], want, f"{sid}[{i}]")
        for sid, e in DATA["scalars"].items():
            if "ptr" in e:
                want = pointer(FX.docs, e["ptr"])
                if e.get("reduce") == "len":
                    want = len(want)
                self.assertEqual(e["v"], want, sid)

    def test_pointer_files_are_declared_inputs(self):
        for e in list(DATA["series"].values()) + list(DATA["scalars"].values()):
            if "ptr" in e:
                name = e["ptr"].split("#")[0]
                self.assertTrue(name in DATA["inputs"] or name in DATA["extra_inputs"], name)

    def test_the_touchdown_sample_is_tagged_as_host_interpolated(self):
        last = FX.n - 1
        self.assertEqual(FX.samples[last]["kind"], "touchdown")
        for sid in ("t_s", "truth_x", "truth_z", "base_x", "base_z", "prop_kg"):
            self.assertEqual(DATA["series"][sid]["cls_by_index"][str(last)], "D-host", sid)
        for sid in ("est_x", "gnss_x", "altimeter", "err_est_x", "err_est_y", "cmd_throttle", "engine"):
            self.assertNotIn("cls_by_index", DATA["series"][sid], sid)
        # View-derived errors stay D-view at every sample, including the touchdown one.
        for sid in ("err_est_x", "err_est_y", "err_gnss_x", "err_altimeter"):
            self.assertEqual(DATA["series"][sid]["cls"], "D-view", sid)
        self.assertEqual(DATA["scalars"]["td.err_est_x"]["cls"], "D-view")

    def test_derivation_inputs_exist_and_every_derivation_is_registered(self):
        names = set()
        for e in list(DATA["series"].values()) + list(DATA["scalars"].values()):
            d = e.get("derivation")
            if not d:
                continue
            names.add(d["name"])
            self.assertIn(d["name"], DATA["derivations"])
            for sid in d["series_inputs"]:
                self.assertIn(sid, DATA["series"], sid)
            for sid in d["scalar_inputs"]:
                self.assertIn(sid, DATA["scalars"], sid)
            for f in e.get("source_facts", []):
                self.assertIn(f, DATA["source_facts"])
        self.assertEqual(names, IMPLEMENTED, "a derivation without an independent check in this test")

    def test_source_facts_are_where_they_say(self):
        for fid, f in DATA["source_facts"].items():
            lines = (ROOT / f["file"]).read_text(encoding="utf-8").splitlines()
            a, b = f["lines"]
            window = "\n".join(lines[a - 1 : b])
            for anchor in f["anchors"]:
                self.assertIn(
                    anchor, window,
                    f"{fid}: {anchor!r} is no longer at the recorded lines of {f['file']}. The sources changed: "
                    "rerun python spikes/m19-belief-truth/extract.py and review the source facts and the doc.",
                )
            self.assertEqual(f["cls"], "S")


# Names of derivations this test recomputes. Equality with the names in data.json is asserted above.
IMPLEMENTED = {
    "est_minus_truth",
    "obs_minus_truth",
    "altimeter_minus_truth_nozzle",
    "s_cm_proxy",
    "body_axis_z_from_imu",
    "est_nozzle_altitude",
    "altimeter_residual",
    "believed_nozzle_xy",
    "believed_pad_distance",
    "guidance_rule_from_flag",
    "lower_altitude_source",
    "max_abs_before_fault",
    "s_cm_station_bound",
    "max_offset_check",
    "control_period",
    "touchdown_sample_value",
    "touchdown_gap",
    "ratio_of_steps",
    "gnss_period",
    "count_where",
    "null_only_at_touchdown",
    "flags_identical",
    "none_true",
    "before",
    "fault_active_at_last_sample",
    "first_sample_above",
    "first_inside_radius",
    "last_inside_radius",
    "inside_radius_runs",
    "min_over_samples",
    "inside_radius_at_touchdown",
    "nozzle_reference_check",
    "equals_check",
    "first_fix_jump",
    "source_tree_sha256",
    "pinned_recording_commit",
    "source_tree_diff",
    "cited_sources_identical",
    "evidence_file_line",
    "first_sample_where",
    "first_over_threshold",
    "horizontal_speed_at_touchdown",
    "velocity_difference_at_touchdown",
    "angular_rate_times_lever",
    "product_check",
}


class Derivations(unittest.TestCase):
    """Recompute every derived series and scalar from the fixture, without the extractor's code."""

    def setUp(self):
        S = FX.samples
        self.S = S
        self.est = [s["estimate"]["position_m"] for s in S]
        self.tru = [s["truth"]["position_m"] for s in S]
        self.base = [s["truth"]["base_position_m"] for s in S]
        self.gn = [s["observation"]["gnss_position_m"] for s in S]
        self.alt = [s["observation"]["altimeter_m"] for s in S]
        self.q = [s["observation"]["imu"]["attitude"] for s in S]
        self.nz = [x_axis_z(q) for q in self.q]
        self.est_noz = [self.est[i][2] - FX.s_cm[i] * self.nz[i] for i in range(FX.n)]
        self.resid = [self.alt[i] - self.est_noz[i] for i in range(FX.n)]
        pad = FX.case["requirements"]["pad_position_m"]
        self.pad = pad
        self.bel = []
        for i in range(FX.n):
            rx, ry, _ = x_axis(self.q[i])
            self.bel.append((self.est[i][0] - FX.s_cm[i] * rx, self.est[i][1] - FX.s_cm[i] * ry))

    def series(self, sid):
        return DATA["series"][sid]["values"]

    def check(self, sid, expected):
        got = self.series(sid)
        self.assertEqual(len(got), FX.n, sid)
        for i, (g, w) in enumerate(zip(got, expected)):
            if isinstance(w, str) or w is None or isinstance(w, bool):
                self.assertEqual(g, w, f"{sid}[{i}]")
            else:
                self.assertTrue(approx(g, w), f"{sid}[{i}]: {g} vs {w}")

    def test_error_series(self):
        for k, ax in enumerate("xy"):
            self.check(f"err_est_{ax}", [self.est[i][k] - self.tru[i][k] for i in range(FX.n)])
        for k, ax in enumerate("xyz"):
            self.check(
                f"err_gnss_{ax}",
                [None if self.gn[i] is None else self.gn[i][k] - self.tru[i][k] for i in range(FX.n)],
            )
        self.check("err_altimeter", [self.alt[i] - self.base[i][2] for i in range(FX.n)])

    def test_host_vertical_error_equals_the_views_own_subtraction(self):
        host = self.series("err_z_host")
        for i in range(FX.n):
            self.assertTrue(approx(host[i], self.est[i][2] - self.tru[i][2]), i)

    def test_nozzle_reference_series(self):
        self.check("s_cm", FX.s_cm)
        self.check("imu_nz", self.nz)
        self.check("est_nozzle_alt", self.est_noz)
        self.check("alt_residual", self.resid)

    def test_proxy_geometry_matches_the_true_offset(self):
        # centre of mass minus nozzle plane equals s_cm * n_z with the TRUTH attitude, to rounding.
        for i, s in enumerate(self.S):
            nz = x_axis_z(s["truth"]["attitude"])
            off = s["truth"]["position_m"][2] - s["truth"]["base_position_m"][2]
            self.assertTrue(abs(off - FX.s_cm[i] * nz) < 1e-9, i)

    def test_believed_nozzle_and_pad_distance(self):
        self.check("believed_nozzle_x", [b[0] for b in self.bel])
        self.check("believed_nozzle_y", [b[1] for b in self.bel])
        self.check(
            "believed_pad_distance",
            [math.hypot(b[0] - self.pad[0], b[1] - self.pad[1]) for b in self.bel],
        )

    def test_lane_series_follow_the_recorded_flag_only(self):
        flags = [s["estimate"]["altimeter_rejected"] for s in self.S]
        self.check("guidance_rule", ["min(estimator, altimeter)" if f else "estimator" for f in flags])
        self.check(
            "lower_source",
            [(("altimeter" if self.alt[i] < self.est_noz[i] else "estimator") if flags[i] else None) for i in range(FX.n)],
        )
        # The switch is taken from the recorded flag: first flagged sample and the recorded time.
        first = flags.index(True)
        self.assertEqual(DATA["index"]["flag_first_sample"], first)
        ver = FX.docs["verification.json"]["controller_flags"]["altimeter_rejected_first"]
        self.assertEqual(DATA["scalars"]["run.reject_first_t_s"]["v"], ver["t_s"])
        self.assertLess(FX.samples[first - 1]["t_s"], ver["t_s"])
        self.assertLessEqual(ver["t_s"], FX.samples[first]["t_s"])
        self.assertTrue(all(flags[first:]))

    def test_scalars(self):
        sc = DATA["scalars"]
        t0 = FX.case["faults"][0]["start_s"]
        pre = [i for i in range(FX.n) if self.S[i]["t_s"] < t0]
        ex = [self.est[i][0] - self.tru[i][0] for i in range(FX.n)]
        self.assertTrue(approx(sc["pre.max_abs_err_x"]["v"], max(abs(ex[i]) for i in pre)))
        self.assertTrue(approx(sc["pre.max_abs_residual"]["v"], max(abs(self.resid[i]) for i in pre)))
        veh = FX.case["vehicle"]
        full = (veh["dry_mass_kg"] * veh["dry_cm_station_m"] + veh["propellant_mass_kg"] * veh["propellant_cm_station_m"]) / (
            veh["dry_mass_kg"] + veh["propellant_mass_kg"]
        )
        self.assertTrue(approx(sc["s_cm.full_tanks_m"]["v"], full))
        self.assertTrue(approx(sc["s_cm.empty_tanks_m"]["v"], veh["dry_cm_station_m"]))
        self.assertTrue(approx(sc["case.control_period_s"]["v"], FX.case["sensors"]["control_period_steps"] * FX.case["dt_s"]))
        last = FX.n - 1
        self.assertTrue(approx(sc["td.true_nozzle_x"]["v"], self.base[last][0]))
        self.assertTrue(approx(sc["td.true_nozzle_y"]["v"], self.base[last][1]))
        self.assertTrue(approx(sc["td.true_cm_x"]["v"], self.tru[last][0]))
        self.assertTrue(approx(sc["td.est_cm_x"]["v"], self.est[last][0]))
        self.assertTrue(approx(sc["td.believed_nozzle_x"]["v"], self.bel[last][0]))
        self.assertTrue(approx(sc["td.believed_nozzle_y"]["v"], self.bel[last][1]))
        self.assertTrue(approx(sc["td.believed_pad_distance"]["v"], math.hypot(*self.bel[last])))
        self.assertTrue(approx(sc["td.err_est_x"]["v"], ex[last]))
        self.assertTrue(approx(sc["td.altimeter"]["v"], self.alt[last]))
        self.assertTrue(approx(sc["td.est_nozzle_alt"]["v"], self.est_noz[last]))
        gap = math.hypot(self.base[last][0] - self.bel[last][0], self.base[last][1] - self.bel[last][1])
        self.assertTrue(approx(sc["td.gap_m"]["v"], gap))
        off = max(
            abs((self.tru[i][2] - self.base[i][2]) - FX.s_cm[i] * x_axis_z(self.S[i]["truth"]["attitude"]))
            for i in range(FX.n)
        )
        self.assertTrue(abs(sc["check.offset_geometry_m"]["v"] - off) < 1e-9)

    def test_r5_is_the_nozzle_point_distance_to_the_pad(self):
        last = FX.n - 1
        r5 = [r for r in FX.docs["verification.json"]["requirements"] if r["id"] == "R5_position"][0]
        d = math.hypot(self.base[last][0] - self.pad[0], self.base[last][1] - self.pad[1])
        self.assertTrue(approx(d, r5["value"]))
        self.assertTrue(approx(DATA["scalars"]["req.R5_position.value"]["v"], r5["value"]))
        self.assertFalse(r5["pass"])
        # R5 is outside, the believed point inside the R5 circle: the story the view tells.
        self.assertGreater(d, FX.case["requirements"]["r5_position_m"])
        self.assertLess(math.hypot(*self.bel[last]), FX.case["requirements"]["r5_position_m"])

    def test_verification_entries_mirror_the_record(self):
        ver = FX.docs["verification.json"]
        self.assertEqual([r["id"] for r in ver["requirements"]], [r["id"] for r in DATA["requirements"]])
        self.assertEqual([r["id"] for r in ver["invariants"]], [r["id"] for r in DATA["invariants"]])
        for row in DATA["invariants"]:
            self.assertNotIn("t_s", {k for k in row["fields"]}, "invariants carry no time")
        for inv in ver["invariants"]:
            self.assertNotIn("t_s", inv)


class NoInterpolation(unittest.TestCase):
    def test_observation_series_are_exactly_the_recorded_points(self):
        times = [s["t_s"] for s in FX.samples]
        self.assertEqual(DATA["series"]["t_s"]["values"], times)
        checked = 0
        for sid, e in DATA["series"].items():
            if e["cls"] != "O":
                continue
            checked += 1
            if e["render"] == "none":
                continue
            self.assertEqual(e["render"], "points", sid)
            self.assertEqual(len(e["values"]), FX.n)
            for i in range(FX.n):
                want = pointer(FX.docs, e["ptr"].format(i=i), e.get("null_parent", False))
                self.assertEqual(e["values"][i], want, f"{sid}[{i}]")
        self.assertGreaterEqual(checked, 5)
        # GNSS delivered nothing at the touchdown sample: that stays null, not filled in.
        self.assertIsNone(DATA["series"]["gnss_x"]["values"][-1])
        self.assertIsNone(DATA["series"]["err_gnss_x"]["values"][-1])

    def test_series_built_from_observations_are_points_too(self):
        for sid, e in DATA["series"].items():
            d = e.get("derivation")
            if not d or e["render"] == "none":
                continue
            uses_obs = any(
                DATA["series"][i]["cls"] == "O" and DATA["series"][i]["render"] != "none" for i in d["series_inputs"]
            )
            if uses_obs and e["render"] not in ("lane",):
                self.assertEqual(e["render"], "points", sid)

    def test_only_estimates_and_host_metrics_are_lines(self):
        for sid, e in DATA["series"].items():
            if e["render"] == "line":
                self.assertIn(e["cls"], {"T", "E", "D-host", "D-view"}, sid)
                d = e.get("derivation")
                if d:
                    self.assertFalse(
                        any(DATA["series"][i]["cls"] == "O" and DATA["series"][i]["render"] != "none" for i in d["series_inputs"]),
                        sid,
                    )

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_view_refuses_to_join_observations(self):
        script = """
import { Model, lineRuns, pointList } from './js/model.js';
import fs from 'node:fs';
const data = JSON.parse(fs.readFileSync('data.json', 'utf8'));
const m = new Model(data);
let refused = 0, points = 0;
for (const [id, s] of Object.entries(data.series)) {
  if (s.render === 'points') {
    let threw = false;
    try { lineRuns(s, m.t); } catch (e) { threw = true; }
    if (!threw) throw new Error('line drawn for ' + id);
    refused++;
    const pts = pointList(s, m.t);
    const nonNull = s.values.filter((v) => v !== null).length;
    if (pts.length !== nonNull) throw new Error('points differ for ' + id);
    for (const [t, y, i] of pts) if (t !== m.t[i] || y !== s.values[i]) throw new Error('moved point ' + id);
    points++;
  }
}
for (const id of ['err_est_x', 'err_z_host']) {
  const runs = lineRuns(data.series[id], m.t);
  if (runs.length !== 1) throw new Error('estimate line should be one run');
}
if (m.nearestSample(8.18) !== 82 && m.nearestSample(8.18) !== 81) throw new Error('snap');
const ign = data.events.find((e) => e.id === 'ignition').nav_index;
if (m.eventJump(0, 1) !== ign) throw new Error('event jump');
console.log(JSON.stringify({ refused, points }));
"""
        res = subprocess.run(
            ["node", "--input-type=module", "-e", script], cwd=SPIKE, capture_output=True, text=True
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        out = json.loads(res.stdout)
        self.assertGreaterEqual(out["points"], 8)

    def test_javascript_has_no_stray_number_formatting_or_rounding(self):
        for name in ("app.js", "charts.js", "model.js"):
            src = (SPIKE / "js" / name).read_text(encoding="utf-8")
            for banned in ("toLocaleString", "Intl.NumberFormat", "Math.round(", "toPrecision"):
                if name == "charts.js" and banned == "Math.round(":
                    continue  # whole-second tick test in the axis, a layout question
                self.assertNotIn(banned, src, f"{name}: {banned}")
            if name != "model.js":
                self.assertNotIn(".toFixed(", src.replace("X(t).toFixed(1)", "").replace("Y(y).toFixed(1)", "")
                                 .replace("px(x - padX).toFixed(1)", "").replace("py(y - padY).toFixed(1)", "")
                                 .replace("t.toFixed(6)", "").replace("v.toFixed(6)", ""), name)

    def test_every_id_the_view_names_exists_in_the_data(self):
        ids = set(DATA["series"]) | set(DATA["scalars"])
        html = (SPIKE / "index.html").read_text(encoding="utf-8")
        found = set(re.findall(r'data-v="([^"]+)"', html))
        src = "\n".join((SPIKE / "js" / n).read_text(encoding="utf-8") for n in ("app.js", "charts.js"))
        found |= set(re.findall(r'\bV\("([^"]+)"', src))
        found |= set(re.findall(r'model\.(?:scalar|series|value|text|cls)\("([^"]+)"', src))
        found |= set(re.findall(r'series: "([^"]+)"', src))
        found |= set(re.findall(r'(?:legendItem\([^,]+,[^,]+,[^,]+,\s*)"([^"]+)"', src))
        found |= {s for s in re.findall(r'"((?:td|pre|req|inv|run|case|check|s_cm)\.[A-Za-z0-9_.]+)"', src)}
        self.assertGreater(len(found), 40)
        self.assertEqual(sorted(f for f in found if f not in ids), [])
        for sf in re.findall(r'data-fact="([^"]+)"', html) + re.findall(r'factButton\("([^"]+)"', src):
            self.assertIn(sf, DATA["source_facts"])


# ---------------------------------------------------------------------------------------------
# Rendered page (needs a headless browser)

BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "/usr/bin/chromium",
    "/usr/bin/google-chrome",
]


def find_browser():
    for b in BROWSERS:
        if os.path.exists(b):
            return b
    for name in ("msedge", "chrome", "chromium", "google-chrome"):
        p = shutil.which(name)
        if p:
            return p
    return None


class DomAudit(HTMLParser):
    VOID = {"br", "img", "input", "meta", "link", "hr", "line", "circle", "rect", "polygon", "polyline", "path"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.bad = []
        self.values = []  # (attrs, text)
        self._cur = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style", "title"):
            self.stack.append((tag, a))
            return
        if tag not in self.VOID:
            self.stack.append((tag, a))
        if "data-ref" in a and tag in ("button", "td"):
            self._cur = [a, ""]

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        if tag in self.VOID or tag not in [t for t, _ in self.stack]:
            return
        while self.stack and self.stack[-1][0] != tag:
            self.stack.pop()
        if self.stack:
            _, a = self.stack.pop()
            if self._cur is not None and self._cur[0] is a:
                self.values.append(tuple(self._cur))
                self._cur = None

    def handle_data(self, data):
        if any(t in ("script", "style", "title") for t, _ in self.stack):
            return
        if self._cur is not None:
            self._cur[1] += data
        if not re.search(r"\d", data):
            return
        for _, a in self.stack:
            if "data-ref" in a or "data-layout" in a:
                return
        cleaned = re.sub(r"\b[RS][1-6]\b", "", data)
        cleaned = re.sub(r"\bS1 to S5\b|\bR1 to R6\b", "", cleaned)
        if re.search(r"\d", cleaned):
            self.bad.append(data.strip())


def expected_text(e, i, digits):
    v = e["values"][i] if "values" in e else e["v"]
    if v is None:
        return e.get("null_text") or "none"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, list):
        return ", ".join(str(x) for x in v) if v else "none"
    if isinstance(v, (int, float)):
        s = str(v) if digits in (None, "") else f"{v:.{int(digits)}f}"
        return s.replace("-", "\u2212")
    return str(v)


@unittest.skipUnless(find_browser(), "no headless Chromium-based browser found")
class RenderedPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class Quiet(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *a, **k):
                super().__init__(*a, directory=str(SPIKE), **k)

            def log_message(self, *a, **k):
                pass

        cls.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Quiet)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        port = cls.httpd.server_address[1]
        res = subprocess.run(
            [find_browser(), "--headless=new", "--disable-gpu", "--virtual-time-budget=10000", "--dump-dom",
             f"http://127.0.0.1:{port}/index.html"],
            capture_output=True, timeout=120,
        )
        cls.dom = res.stdout.decode("utf-8", "replace")

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def test_view_started(self):
        self.assertIn('data-ready="1"', self.dom)
        self.assertNotIn('class="fatal"', self.dom)

    def test_every_number_in_the_page_is_a_data_value_or_an_axis_label(self):
        audit = DomAudit()
        audit.feed(self.dom)
        self.assertEqual(audit.bad, [])
        self.assertGreater(len(audit.values), 600)

    def test_value_buttons_show_the_data_model_value(self):
        audit = DomAudit()
        audit.feed(self.dom)
        n = 0
        for attrs, txt in audit.values:
            ref = attrs["data-ref"]
            i = int(attrs.get("data-i", "0") or 0)
            if attrs.get("data-display") == "label" or "data-legend" in attrs:
                continue
            e = DATA["series"].get(ref) or DATA["scalars"][ref]
            want = expected_text(e, i, attrs.get("data-digits"))
            got = txt.strip()
            # the button text is number + unit + tag; the cell text is the number only
            self.assertTrue(got.startswith(want), f"{ref}[{i}]: shows {got!r}, data says {want!r}")
            n += 1
        self.assertGreater(n, 500)

    def test_no_observation_is_joined_in_the_drawn_svg(self):
        # Observation markers have their own classes; a polyline may only carry estimate classes.
        for cls in re.findall(r'<polyline[^>]*class="([^"]+)"', self.dom):
            self.assertIn(cls, {"connector", "plan-trail-truth", "plan-trail-belief"})


class Iteration2Data(unittest.TestCase):
    """Values added in iteration 2, recomputed from the fixture and the sources without the extractor."""

    def setUp(self):
        self.S = FX.samples
        self.sc = DATA["scalars"]
        self.t = [s["t_s"] for s in self.S]

    def test_host_velocity_and_distance_metrics_equal_the_subtraction_at_every_sample(self):
        ch = {c["id"]: c["values"] for c in FX.docs["record.json"]["channels"]}
        pad = FX.case["requirements"]["pad_position_m"]
        for i, s in enumerate(self.S):
            tv, ev = s["truth"]["velocity_mps"], s["estimate"]["velocity_mps"]
            tp, ep = s["truth"]["position_m"], s["estimate"]["position_m"]
            self.assertTrue(approx(ch["err_vz"][i], ev[2] - tv[2]), i)
            self.assertTrue(approx(ch["err_vh"][i], math.hypot(ev[0] - tv[0], ev[1] - tv[1])), i)
            self.assertTrue(approx(ch["err_h"][i], math.hypot(ep[0] - tp[0], ep[1] - tp[1])), i)
            bp = s["truth"]["base_position_m"]
            self.assertTrue(approx(ch["pad_distance"][i], math.hypot(bp[0] - pad[0], bp[1] - pad[1])), i)
        self.assertEqual(DATA["series"]["err_vz_host"]["values"], ch["err_vz"])
        self.assertEqual(DATA["series"]["err_vh_host"]["values"], ch["err_vh"])
        self.assertEqual(DATA["series"]["err_vz_host"]["cls"], "D-host")

    def test_commands_are_their_own_class_and_the_two_flags_are_one_condition(self):
        for sid in ("cmd_throttle", "cmd_gimbal_y", "cmd_gimbal_z"):
            self.assertEqual(DATA["series"][sid]["cls"], "K")
            self.assertTrue(DATA["series"][sid]["ptr"].split("#/")[1].split("/")[2] == "command")
        flags = [s["estimate"]["altimeter_rejected"] for s in self.S]
        dis = [s["estimate"]["sensor_disagreement"] for s in self.S]
        self.assertEqual(flags, dis)
        self.assertTrue(self.sc["check.detection_flags_identical"]["v"])
        fl = FX.docs["verification.json"]["controller_flags"]
        self.assertEqual(fl["altimeter_rejected_first"], fl["sensor_disagreement_first"])
        # One detection in the event list, not two.
        self.assertEqual([e["id"] for e in DATA["events"]].count("altimeter_rejected"), 1)
        self.assertNotIn("sensor_disagreement", [e["id"] for e in DATA["events"]])

    def test_no_cutoff_abort_or_relight(self):
        run = FX.docs["run.json"]["summary"]
        self.assertIsNone(self.sc["run.cutoff_t_s"]["v"])
        self.assertIsNone(run["cutoff_t_s"])
        self.assertIsNone(run["flameout_t_s"])
        self.assertIsNone(self.sc["run.ascent_abort_first"]["v"])
        self.assertTrue(self.sc["check.no_ascent_abort_flag"]["v"])
        self.assertFalse(any(s["estimate"]["ascent_abort"] for s in self.S))
        self.assertEqual(self.sc["inv.S4_no_relight.worst_value"]["v"], 1.0)
        ign = [e for e in FX.docs["trace.json"]["events"] if e["kind"] == "ignition"]
        self.assertEqual(len(ign), 1)
        self.assertEqual(self.sc["run.ignition_command_t_s"]["v"], ign[0]["detail"]["command_t_s"])
        self.assertTrue(self.sc["check.ignition_before_fault"]["v"])

    def test_cadence_matches_the_case_and_the_trace(self):
        sens = FX.case["sensors"]
        ctl = sens["control_period_steps"] * FX.case["dt_s"]
        self.assertTrue(approx(self.sc["case.control_period_s"]["v"], ctl))
        self.assertTrue(approx(self.sc["cad.gnss_period_s"]["v"], sens["gnss_period_cycles"] * ctl))
        self.assertEqual(self.sc["cad.samples_per_cycle"]["v"], FX.case["record_every"] / sens["control_period_steps"])
        self.assertTrue(approx(self.sc["cad.gnss_period_s"]["v"], FX.docs["record.json"]["scene"]["sample_interval_s"]))
        periodic = [s for s in self.S if s["kind"] == "periodic"]
        self.assertTrue(all(s["observation"]["gnss_position_m"] is not None for s in periodic))
        no_fix = [i for i, s in enumerate(self.S) if s["observation"]["gnss_position_m"] is None]
        self.assertEqual(no_fix, [FX.n - 1])
        self.assertEqual(self.sc["gnss.no_fix_samples"]["v"], 1)
        self.assertEqual(self.sc["gnss.fix_samples"]["v"], FX.n - 1)
        self.assertEqual(DATA["series"]["gnss_x"]["null_text"], "no fix on this cycle")
        # step spacing of the periodic samples is the trace sampling
        steps = [s["step"] for s in periodic]
        self.assertTrue(all(b - a == FX.case["record_every"] for a, b in zip(steps, steps[1:])))

    def test_divergence_thresholds_are_first_recorded_samples(self):
        ch = {c["id"]: c["values"] for c in FX.docs["record.json"]["channels"]}
        self.assertEqual(DATA["divergence"]["thresholds"], [1, 3, 5, 10])
        for m in DATA["divergence"]["metrics"]:
            vals = ch["err_h"] if m["series"] == "err_h_host" else ch["err_z"]
            for th, sid in m["scalars"].items():
                first = next((i for i, x in enumerate(vals) if abs(x) > float(th)), None)
                e = self.sc[sid]
                self.assertEqual(e["v"], None if first is None else self.t[first], sid)
                if first is not None:
                    self.assertEqual(e["derivation"]["at_index"], first)
                    self.assertIn(self.t[first], self.t)  # a recorded sample time, never an interpolation
        self.assertEqual(DATA["index"]["pre_fault_last"], DATA["index"]["fault_first_sample"] - 1)
        t0 = FX.case["faults"][0]["start_s"]
        self.assertLess(self.t[DATA["index"]["pre_fault_last"]], t0)
        self.assertTrue(abs(self.t[DATA["index"]["fault_first_sample"]] - t0) < 1e-9)
        jump = FX.case["controller"]["gains"]["gnss_position_gain"] * FX.case["faults"][0]["magnitude"]
        self.assertTrue(approx(self.sc["lane.expected_first_fix_jump_m"]["v"], jump))

    def test_r5_windows_are_first_and_last_recorded_samples_inside(self):
        r5 = FX.case["requirements"]["r5_position_m"]
        ch = {c["id"]: c["values"] for c in FX.docs["record.json"]["channels"]}
        bel = DATA["series"]["believed_pad_distance"]["values"]
        for key, vals in (("true", ch["pad_distance"]), ("believed", bel)):
            inside = [i for i, d in enumerate(vals) if d <= r5]
            self.assertEqual(self.sc[f"win.{key}.first_t"]["v"], self.t[inside[0]])
            self.assertEqual(self.sc[f"win.{key}.last_t"]["v"], self.t[inside[-1]])
            runs = sum(1 for i in range(FX.n) if vals[i] <= r5 and (i == 0 or vals[i - 1] > r5))
            self.assertEqual(self.sc[f"win.{key}.runs"]["v"], runs)
            self.assertTrue(approx(self.sc[f"win.{key}.min_m"]["v"], min(vals)))
        self.assertFalse(self.sc["td.true_inside_r5"]["v"])
        self.assertTrue(self.sc["td.believed_inside_r5"]["v"])
        r5_row = [r for r in FX.docs["verification.json"]["requirements"] if r["id"] == "R5_position"][0]
        self.assertEqual(self.sc["td.true_inside_r5"]["v"], r5_row["pass"])

    def test_lane_counts(self):
        flags = [s["estimate"]["altimeter_rejected"] for s in self.S]
        self.assertEqual(self.sc["lane.flagged_samples"]["v"], sum(flags))
        lower = DATA["series"]["lower_source"]["values"]
        self.assertEqual(self.sc["lane.altimeter_lower_samples"]["v"], sum(1 for x in lower if x == "altimeter"))

    def test_requirement_reference_and_s2(self):
        ver = FX.docs["verification.json"]
        bv = ver["touchdown"]["truth"]["base_velocity_mps"]
        bp = ver["touchdown"]["truth"]["base_position_m"]
        req = {r["id"]: r for r in ver["requirements"]}
        self.assertTrue(approx(abs(bv[2]), req["R1_vertical_speed"]["value"]))
        self.assertTrue(approx(math.hypot(bv[0], bv[1]), req["R2_horizontal_speed"]["value"]))
        self.assertTrue(approx(math.hypot(bp[0], bp[1]), req["R5_position"]["value"]))
        for rid in ("R1", "R2", "R5"):
            self.assertTrue(self.sc[f"check.{rid}_nozzle"]["v"])
        rows = {r["short"]: r for r in DATA["requirements"]}
        self.assertEqual({k for k, r in rows.items() if r.get("reference")}, {"R1", "R2", "R5"})
        s2 = [i for i in ver["invariants"] if i["id"] == "S2_keep_out"][0]
        self.assertEqual(s2["worst_value"], req["R5_position"]["value"])
        self.assertTrue(self.sc["check.s2_equals_r5"]["v"])

    def test_initial_state_and_frame(self):
        rec = FX.docs["record.json"]["scene"]
        for k, ax in enumerate("xyz"):
            self.assertEqual(self.sc[f"init.nominal_p{ax}"]["v"], FX.case["initial"]["position_m"][k])
            self.assertEqual(self.sc[f"init.disp_p{ax}"]["v"], rec["initial"]["position_m"][k])
            self.assertEqual(self.sc[f"init.disp_p{ax}"]["v"], self.S[0]["truth"]["position_m"][k])
            self.assertEqual(self.sc[f"init.range_v{ax}"]["v"], FX.case["dispersion"]["velocity_mps"][k])
            self.assertEqual(self.sc[f"frame.{ax}"]["v"], rec["frame"]["axes"][ax])
        self.assertEqual((self.sc["frame.x"]["v"], self.sc["frame.y"]["v"]), ("east", "north"))
        last_faults = self.S[-1]["active_faults"]
        self.assertEqual(self.sc["fault.active_at_last_sample"]["v"], FX.case["faults"][0]["kind"] in last_faults)
        self.assertTrue(self.sc["fault.active_at_last_sample"]["v"])
        self.assertFalse(self.sc["fault.ended_before_touchdown"]["v"])

    def test_approximation_propagates_to_everything_derived_from_an_approximate_value(self):
        regs = DATA["derivations"]

        def approx_flag(e):
            return bool(e.get("approx") or (e.get("derivation") and regs[e["derivation"]["name"]]["approx"]))

        for e in list(DATA["series"].values()) + list(DATA["scalars"].values()):
            d = e.get("derivation")
            if not d:
                continue
            ins = [DATA["series"][i] for i in d["series_inputs"]] + [DATA["scalars"][i] for i in d["scalar_inputs"]]
            if any(approx_flag(x) for x in ins):
                self.assertTrue(approx_flag(e), e["label"])
        self.assertTrue(DATA["scalars"]["td.believed_inside_r5"]["approx"])
        self.assertFalse(approx_flag(DATA["scalars"]["td.err_est_x"]))

    def test_r2_centre_of_mass_and_nozzle_speeds(self):
        last = self.S[-1]["truth"]
        cm = math.hypot(last["velocity_mps"][0], last["velocity_mps"][1])
        bv = math.hypot(last["base_velocity_mps"][0], last["base_velocity_mps"][1])
        r2 = [r for r in FX.docs["verification.json"]["requirements"] if r["id"] == "R2_horizontal_speed"][0]["value"]
        self.assertTrue(approx(bv, r2))
        self.assertTrue(approx(self.sc["td.cm_horizontal_speed"]["v"], cm))
        self.assertGreater(abs(r2 - cm), 0.05)
        diff = math.hypot(last["base_velocity_mps"][0] - last["velocity_mps"][0], last["base_velocity_mps"][1] - last["velocity_mps"][1])
        self.assertTrue(approx(self.sc["td.nozzle_minus_cm_speed"]["v"], diff))
        r4 = [r for r in FX.docs["verification.json"]["requirements"] if r["id"] == "R4_angular_rate"][0]["value"]
        self.assertTrue(approx(self.sc["td.angular_rate_times_lever"]["v"], r4 * FX.s_cm[-1]))
        self.assertLess(abs(diff - r4 * FX.s_cm[-1]), 0.01 * max(1.0, diff))

    def test_ignition_first_samples_and_r6_limit(self):
        eng = [s["applied"]["engine"] for s in self.S]
        thr = [s["command"]["throttle"] for s in self.S]
        self.assertEqual(self.sc["ign.first_engine_on_t"]["v"], self.t[next(i for i, e in enumerate(eng) if e != "off")])
        self.assertEqual(self.sc["ign.first_command_t"]["v"], self.t[next(i for i, x in enumerate(thr) if x > 0)])
        ev = [e for e in FX.docs["trace.json"]["events"] if e["kind"] == "ignition"][0]
        self.assertEqual(ev["detail"]["command_step"], ev["step"])  # no delay: the command and the event coincide
        r6 = [r for r in FX.docs["verification.json"]["requirements"] if r["id"] == "R6_propellant_margin"][0]
        init = self.S[0]["truth"]["propellant_kg"]
        self.assertEqual(self.sc["init.propellant_kg"]["v"], init)
        self.assertTrue(approx(FX.case["requirements"]["r6_propellant_margin_fraction"] * init, r6["limit"]))
        self.assertTrue(self.sc["check.r6_limit_is_fraction_of_initial"]["v"])

    def test_gnss_velocity_observations(self):
        for k, ax in enumerate("xyz"):
            e = DATA["series"][f"gnss_v{ax}"]
            self.assertEqual((e["cls"], e["render"]), ("O", "points"))
            for i, s in enumerate(self.S):
                g = s["observation"]["gnss_velocity_mps"]
                self.assertEqual(e["values"][i], None if g is None else g[k])
        want = [None if s["observation"]["gnss_velocity_mps"] is None else s["observation"]["gnss_velocity_mps"][2] - s["truth"]["velocity_mps"][2] for s in self.S]
        for a, b in zip(DATA["series"]["err_gnss_vz"]["values"], want):
            self.assertTrue(approx(a, b))

    def test_first_over_threshold_sample(self):
        thr = FX.case["controller"]["gains"]["altimeter_residual_threshold_m"]
        resid = DATA["series"]["alt_residual"]["values"]
        first = next(i for i, x in enumerate(resid) if abs(x) > thr)
        self.assertEqual(self.sc["lane.first_over_threshold_t"]["v"], self.t[first])
        self.assertLess(self.sc["lane.first_over_threshold_t"]["v"], self.sc["run.reject_first_t_s"]["v"])

    def test_every_new_class_tag_is_declared(self):
        self.assertIn("K", DATA["classes"])
        for e in list(DATA["series"].values()) + list(DATA["scalars"].values()):
            self.assertIn(e["cls"], DATA["classes"])


class BuildProvenance(unittest.TestCase):
    """The recorded source hash against the current tree, checked with git when the commit is reachable."""

    P = DATA["provenance"]

    def git_show(self, rev, rel):
        return subprocess.run(
            ["git", "show", f"{rev}:crates/vv-rocket/{rel}"], cwd=ROOT, capture_output=True, check=True
        ).stdout

    def aggregate(self, files):
        d = hashlib.sha256()
        for rel in self.P["hashed_files"]:
            d.update(rel.encode())
            d.update(bytes([0]))
            d.update(files[rel].replace(bytes([13, 10]), bytes([10])))
            d.update(bytes([0]))
        return d.hexdigest()

    def test_current_tree_hash_and_differences(self):
        files = {rel: (ROOT / "crates/vv-rocket" / rel).read_bytes() for rel in self.P["hashed_files"]}
        self.assertEqual(len(files), 20)
        cur = self.aggregate(files)
        self.assertEqual(DATA["scalars"]["prov.current_sha"]["v"], cur)
        recorded = FX.docs["run.json"]["source_sha256"]
        self.assertEqual(DATA["scalars"]["run.hash.source"]["v"], recorded)
        self.assertEqual(DATA["scalars"]["prov.hash_matches"]["v"], cur == recorded)
        self.assertNotEqual(cur, recorded, "the current tree is expected to differ from the recording tree")
        differing = [
            rel for rel in self.P["hashed_files"]
            if hashlib.sha256(files[rel].replace(bytes([13, 10]), bytes([10]))).hexdigest() != self.P["recording_file_sha256"][rel]
        ]
        self.assertEqual(differing, self.P["differing"])
        self.assertEqual(differing, ["src/landing_model.rs"])
        self.assertEqual(DATA["scalars"]["prov.differing_files"]["v"], "src/landing_model.rs")
        self.assertTrue(DATA["scalars"]["prov.cited_sources_identical"]["v"])
        for fid, f in DATA["source_facts"].items():
            if f["identical_to_recording"] is not None:
                self.assertTrue(f["identical_to_recording"], f"{fid}: a cited source differs from the recording tree")

    def test_the_pinned_recording_tree_reproduces_the_recorded_hash(self):
        if shutil.which("git") is None:
            self.skipTest("git not available")
        commit = self.P["recording_commit"]
        if subprocess.run(["git", "cat-file", "-e", commit + "^{commit}"], cwd=ROOT, capture_output=True).returncode != 0:
            self.skipTest(f"commit {commit} is not reachable in this clone")
        files = {rel: self.git_show(commit, rel) for rel in self.P["hashed_files"]}
        for rel, content in files.items():
            h = hashlib.sha256(content.replace(bytes([13, 10]), bytes([10]))).hexdigest()
            self.assertEqual(h, self.P["recording_file_sha256"][rel], f"pin of {rel} does not match git")
        self.assertEqual(self.aggregate(files), FX.docs["run.json"]["source_sha256"])
        self.assertEqual(DATA["scalars"]["prov.recording_commit"]["v"], commit)

    def test_the_version_string_alone_does_not_identify_the_build(self):
        self.assertEqual(DATA["scalars"]["run.version"]["v"], "0.15.0")
        self.assertEqual(DATA["scalars"]["prov.current_domain_version"]["v"], FX.docs["domain.json"]["version"])
        self.assertEqual(DATA["scalars"]["run.version"]["v"], DATA["scalars"]["prov.current_domain_version"]["v"])
        self.assertEqual(DATA["scalars"]["prov.stored_parameters"]["v"], 6)
        self.assertEqual(DATA["scalars"]["prov.stored_parameters"]["v"], len(FX.docs["record.json"]["request"]["parameters"]))

    def test_the_replay_evidence_is_the_committed_result(self):
        ev = ROOT / "docs/evidence/m19/belief-truth/iteration-2/cargo-earlier-build.txt"
        text = ev.read_text(encoding="utf-8")
        self.assertIn("a_run_written_by_the_0_15_0_host_verifies_against_its_record_under_the_current_host ... ok", text)
        line = DATA["scalars"]["prov.earlier_build_result"]["v"]
        self.assertTrue(line.startswith("test result: ok. 1 passed; 0 failed"))
        self.assertIn(line, text.splitlines())
        for fid in self.P["facts"]:
            self.assertIn(fid, DATA["source_facts"])


class WordsFromData(unittest.TestCase):
    """No verdict word is typed into the page: it is chosen from a boolean in the data."""

    FREE_WORD = re.compile(r"(?<![.\w-])(passed|failed|pass|fail|FAIL)(?![\w-])")
    LITERAL_SCOPE = re.compile(r"\b(inside|outside)\b[^.<>]{0,24}\bR5\b|\bonly R5\b|\bR5 (passed|failed)\b")

    def test_no_verdict_word_literals_in_the_page_sources(self):
        for name in ("index.html", "js/app.js", "js/charts.js"):
            src = (SPIKE / name).read_text(encoding="utf-8")
            for m in self.FREE_WORD.finditer(src):
                self.fail(f"{name}: literal verdict word {m.group(0)!r} near {src[max(0, m.start() - 40):m.end() + 20]!r}")
            self.assertIsNone(self.LITERAL_SCOPE.search(src), f"{name}: inside/outside R5 or 'only R5' typed as text")

    def test_the_words_are_defined_in_one_place_and_follow_the_booleans(self):
        script = """
import { word } from './js/model.js';
const out = [word('verdict', true), word('verdict', false), word('inside', true), word('inside', false)];
console.log(JSON.stringify(out));
"""
        if not shutil.which("node"):
            self.skipTest("node not available")
        res = subprocess.run(["node", "--input-type=module", "-e", script], cwd=SPIKE, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(json.loads(res.stdout), ["passed", "failed", "inside", "outside"])

    def test_the_story_words_come_from_placeholders_bound_to_data(self):
        html = (SPIKE / "index.html").read_text(encoding="utf-8")
        for m in re.finditer(r'data-word="([a-z_]+)" data-v="([^"]+)"', html):
            self.assertIn(m.group(1), ("verdict", "inside"))
            e = DATA["scalars"][m.group(2)]
            self.assertIsInstance(e["v"], bool, m.group(2))
        for name in re.findall(r'data-at="([^"]+)"', html):
            self.assertTrue(name.isdigit() or name in DATA["index"], name)


class StaticPage(unittest.TestCase):
    def test_estimate_strip_and_text_requirements(self):
        html = (SPIKE / "index.html").read_text(encoding="utf-8")
        app = (SPIKE / "js" / "app.js").read_text(encoding="utf-8")
        charts = (SPIKE / "js" / "charts.js").read_text(encoding="utf-8")
        self.assertIn("Markers are recorded values; the thin connector is a reading aid.", html)
        self.assertIn("connector between recorded samples, not data", app)
        self.assertIn("Estimates are recorded every", html)
        self.assertIn("not a gradual rise", app)
        self.assertIn("No divergence instant is recorded.", html)
        self.assertIn("touch-action: pan-y", (SPIKE / "css" / "style.css").read_text(encoding="utf-8"))
        self.assertIn("requestAnimationFrame", app)
        # the connector is drawn thin and every sample gets a marker
        self.assertIn('class: "connector"', charts)
        self.assertIn('data-sample', charts)

    def test_numeric_cells_do_not_wrap(self):
        css = (SPIKE / "css" / "style.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"\.val[^{]*\.rt td[^{]*\{[^}]*white-space: nowrap[^}]*font-variant-numeric: tabular-nums")
        self.assertIn("#readout-body { overflow-x: auto; }", css)

    def test_events_are_looked_up_by_kind(self):
        ids = [e["id"] for e in DATA["events"]]
        self.assertEqual(sorted(ids), ["altimeter_rejected", "fault_start", "ignition", "touchdown"])
        by_kind = {e["id"]: e for e in DATA["events"]}
        self.assertEqual(by_kind["touchdown"]["nav_index"], FX.n - 1)
        for kind in ("ignition", "fault_start", "touchdown"):
            ptr = DATA["scalars"][{"ignition": "run.ignition_t_s", "fault_start": "run.fault_start_event_t_s", "touchdown": "run.touchdown_t_s"}[kind]]["ptr"]
            k = int(ptr.split("/")[2])
            self.assertEqual(FX.docs["trace.json"]["events"][k]["kind"], kind)


@unittest.skipUnless(find_browser(), "no headless Chromium-based browser found")
class RenderedPageIteration2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class Quiet(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *a, **k):
                super().__init__(*a, directory=str(SPIKE), **k)

            def log_message(self, *a, **k):
                pass

        cls.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Quiet)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        port = cls.httpd.server_address[1]

        def dump(query):
            res = subprocess.run(
                [find_browser(), "--headless=new", "--disable-gpu", "--virtual-time-budget=15000", "--dump-dom",
                 f"http://127.0.0.1:{port}/index.html{query}"],
                capture_output=True, timeout=120,
            )
            return res.stdout.decode("utf-8", "replace")

        cls.full = dump("")
        cls.td = dump("?sample=230")
        cls.track = dump("?plan=track&sample=230")

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def svg_block(self, dom, sid):
        m = re.search(r'<svg id="' + sid + r'".*?</svg>', dom, re.S)
        self.assertIsNotNone(m, sid)
        return m.group(0)

    def test_an_estimate_marker_exists_for_every_recorded_sample(self):
        for sid, series_cls in (("svg-x", "ln-est"), ("svg-y", "ln-est"), ("svg-z", "ln-est")):
            block = self.svg_block(self.full, sid)
            idxs = [int(x) for x in re.findall(r'class="' + series_cls + r'" data-sample="(\d+)"', block)]
            self.assertEqual(sorted(idxs), list(range(FX.n)), sid)
        # observations are separate markers with their own class and never a polyline
        block = self.svg_block(self.full, "svg-x")
        gnss = re.findall(r'class="pt-gnss"', block)
        self.assertEqual(len(gnss), FX.n - 1)
        self.assertNotRegex(block, r'<polyline[^>]*class="pt-gnss"')
        # the connector is a thin separate element, one polyline per unbroken run of the estimate
        # ... and it is broken before the first faulted sample: no connector crosses the fault start
        polys = re.findall(r'<polyline points="([^"]*)" class="connector"', block)
        self.assertEqual([len(p.split()) for p in polys], [DATA["index"]["fault_first_sample"], FX.n - DATA["index"]["fault_first_sample"]])

    def test_whole_track_plan_has_no_labels_over_the_track(self):
        self.assertGreaterEqual(self.svg_block(self.full, "svg-plan").count('class="plan-label"'), 2)
        self.assertEqual(self.svg_block(self.track, "svg-plan").count('class="plan-label"'), 0)

    def test_the_touchdown_errors_are_tagged_d_view_not_d_host(self):
        for dom in (self.td,):
            for ref in ("err_est_x", "err_est_y"):
                m = re.search(r'<button[^>]*data-ref="' + ref + r'"[^>]*data-i="230"[^>]*>(.*?)</button>', dom, re.S)
                self.assertIsNotNone(m, ref)
                self.assertIn("tag-Dview", m.group(1), ref)
                self.assertNotIn("tag-Dhost", m.group(1), ref)
            m = re.search(r'<button[^>]*data-ref="err_z_host"[^>]*data-i="230"[^>]*>(.*?)</button>', dom, re.S)
            self.assertIsNotNone(m)
            self.assertIn("tag-Dhost", m.group(1))
            # the true position at the touchdown sample keeps the host-interpolated tag
            self.assertIn('Truth <span class="tag tag-Dhost"', dom)

    def test_no_fix_is_labelled_at_the_touchdown_sample(self):
        m = re.search(r'<button[^>]*data-ref="gnss_x"[^>]*data-i="230"[^>]*>(.*?)</button>', self.td, re.S)
        self.assertIsNotNone(m)
        self.assertIn("no fix on this cycle", m.group(1))

    def test_sample_table_cells_are_buttons_with_one_tab_stop(self):
        table = re.search(r'<table id="sample-table".*?</table>', self.full, re.S).group(0)
        self.assertEqual(table.count('class="cell"'), FX.n * 13)
        self.assertEqual(len(re.findall(r'tabindex="0"', table)), 1)
        self.assertNotRegex(table, r"<td[^>]*data-ref")

    def test_cursor_starts_at_the_start_of_the_run_and_says_so(self):
        self.assertIn("Cursor at recorded sample index 0 (last index 230, 231 samples): t = 0.000 s, start of the run.", self.full)
        self.assertNotIn("sample 0 of 230", self.full)

    def test_the_touchdown_dump_obeys_the_same_number_audit(self):
        audit = DomAudit()
        audit.feed(self.td)
        self.assertEqual(audit.bad, [])
        for attrs, txt in audit.values:
            ref = attrs["data-ref"]
            if attrs.get("data-display") == "label" or "data-legend" in attrs:
                continue
            e = DATA["series"].get(ref) or DATA["scalars"][ref]
            want = expected_text(e, int(attrs.get("data-i", "0") or 0), attrs.get("data-digits"))
            self.assertTrue(txt.strip().startswith(want), f"{ref}: {txt!r} vs {want!r}")

    def test_run_hashes_are_shown_in_provenance(self):
        for ref in ("run.hash.case", "run.hash.trace", "run.hash.verification", "run.hash.source"):
            self.assertIn(f'data-ref="{ref}"', self.full)

    def test_approximate_values_carry_the_approx_tag_at_the_point_of_use(self):
        for ref in ("td.believed_pad_distance", "td.believed_inside_r5", "td.gap_m", "win.believed.first_t", "win.believed.last_t"):
            m = re.search(r'<button[^>]*data-ref="' + re.escape(ref) + r'"[^>]*>(.*?)</button>', self.full, re.S)
            self.assertIsNotNone(m, ref)
            self.assertIn("tag-approx", m.group(1), ref)
        m = re.search(r'<li id="card-2">.*?</li>', self.full, re.S).group(0)
        self.assertEqual(m.count("tag-approx"), 2)

    def test_every_chart_svg_is_an_image_with_a_label(self):
        ids = re.findall(r'<svg id="(axis|svg-[a-z]+)"([^>]*)>', self.full)
        self.assertEqual(sorted(i for i, _ in ids), sorted(["axis", "svg-x", "svg-y", "svg-z", "svg-v", "svg-d", "svg-a", "svg-r", "svg-l", "svg-plan"]))
        for sid, attrs in ids:
            self.assertIn('role="img"', attrs, sid)
            m = re.search(r'aria-label="([^"]+)"', attrs)
            self.assertIsNotNone(m, sid)
            self.assertGreater(len(m.group(1)), 30, sid)

    def test_each_strip_has_its_own_time_labels(self):
        for sid in ("svg-x", "svg-y", "svg-z", "svg-v", "svg-d", "svg-a", "svg-r"):
            block = self.svg_block(self.full, sid)
            labels = re.findall(r'class="ax-label" text-anchor="middle" data-layout="1"', block)
            self.assertGreaterEqual(len(labels), 4, sid)

    def test_provenance_lead_line_and_card_wording(self):
        self.assertIn("Verdicts shown are stored, not recomputed by this view; the build that wrote the run is not the current tree.", self.full)
        card1 = re.search(r'<li id="card-1">.*?</li>', self.full, re.S).group(0)
        self.assertIn("(the point R5 judges)", card1)
        self.assertIn("then left", card1)
        card4 = re.search(r'<li id="card-4">.*?</li>', self.full, re.S).group(0)
        self.assertIn('data-fact="S_gnss_ungated"', card4)
        self.assertIn('data-ref="lane.first_over_threshold_t"', card4)
        self.assertEqual(len(re.findall(r"[.;] ", re.sub(r"<[^>]+>", "", card4))) >= 2, True)

    def test_r2_and_r6_notes_are_rendered_from_data(self):
        notes = re.search(r'<div id="req-notes">.*?</div>', self.full, re.S).group(0)
        for ref in ("req.R2_horizontal_speed.value", "td.cm_horizontal_speed", "td.nozzle_minus_cm_speed",
                    "td.angular_rate_times_lever", "init.propellant_kg", "req.R6_propellant_margin.limit", "req.R6.explanation"):
            self.assertIn(f'data-ref="{ref}"', notes, ref)

    def test_ignition_wording_is_a_truth_event_with_first_samples(self):
        dec = re.search(r'<section id="decisions".*?</section>', self.full, re.S).group(0)
        text = re.sub(r"<[^>]+>", "", dec)
        self.assertIn("Engine ignition recorded (truth event) at", text)
        self.assertIn('data-ref="ign.first_engine_on_t"', dec)
        self.assertIn('data-ref="ign.first_command_t"', dec)

    def test_gnss_velocity_is_shown_as_separate_markers(self):
        block = self.svg_block(self.full, "svg-v")
        self.assertEqual(len(re.findall(r'class="pt-gnss"', block)), FX.n - 1)
        self.assertNotRegex(block, r'<polyline[^>]*class="pt-gnss"')
        self.assertIn('data-ref="gnss_vz"', self.full)

    def test_threshold_options_and_the_divergence_statement(self):
        self.assertIn("No divergence instant is recorded.", self.full)
        for th in (1, 3, 5, 10):
            self.assertIn(f'<option value="{th}"', self.full)


class Hygiene(unittest.TestCase):
    FILES = [
        SPIKE / "extract.py",
        SPIKE / "index.html",
        SPIKE / "css" / "style.css",
        SPIKE / "js" / "app.js",
        SPIKE / "js" / "charts.js",
        SPIKE / "js" / "model.js",
        ROOT / "docs" / "m19-2-belief-truth.md",
        Path(__file__),
    ]

    def test_no_em_dash_in_the_prototype_files(self):
        for f in self.FILES:
            if f.exists():
                self.assertNotIn("\u2014", f.read_text(encoding="utf-8"), str(f))

    def test_no_third_party_or_remote_resources(self):
        for f in (SPIKE / "index.html", SPIKE / "css" / "style.css", *(SPIKE / "js").glob("*.js")):
            text = f.read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"https?://(?!127\.0\.0\.1|localhost|www\.w3\.org/)", text), str(f))
        self.assertFalse(re.search(r"\bthree\b", (SPIKE / "index.html").read_text(encoding="utf-8"), re.I))


if __name__ == "__main__":
    unittest.main()
