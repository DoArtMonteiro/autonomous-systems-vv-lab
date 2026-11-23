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
CLASSES = {"T", "E", "O", "D-host", "D-view", "S", "C"}


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
            self.assertEqual(out.read_bytes(), (SPIKE / "data.json").read_bytes())
        self.assertNotIn(b"\r", (SPIKE / "data.json").read_bytes())

    def test_source_files_are_the_ones_the_facts_were_read_from(self):
        for rel, h in DATA["source_files"].items():
            self.assertEqual(sha(ROOT / rel), h, rel)


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
                self.assertEqual(e["v"], pointer(FX.docs, e["ptr"]), sid)

    def test_pointer_files_are_declared_inputs(self):
        for e in list(DATA["series"].values()) + list(DATA["scalars"].values()):
            if "ptr" in e:
                self.assertIn(e["ptr"].split("#")[0], DATA["inputs"])

    def test_the_touchdown_sample_is_tagged_as_host_interpolated(self):
        last = FX.n - 1
        self.assertEqual(FX.samples[last]["kind"], "touchdown")
        for sid in ("t_s", "truth_x", "truth_z", "base_x", "base_z", "prop_kg"):
            self.assertEqual(DATA["series"][sid]["cls_by_index"][str(last)], "D-host", sid)
        for sid in ("est_x", "gnss_x", "altimeter"):
            self.assertNotIn("cls_by_index", DATA["series"][sid], sid)

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
                self.assertIn(anchor, window, f"{fid}: {anchor}")
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
if (m.eventJump(0, 1) !== 36) throw new Error('event jump');
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
        return "none"
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
            self.assertIn(cls, {"ln-est", "plan-trail-truth", "plan-trail-belief"})


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
