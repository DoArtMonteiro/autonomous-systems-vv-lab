from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import sim_adapter as sa  # noqa: E402
from adversarial_campaign import default_binary  # noqa: E402

LAB = default_binary("vv-lab")


def request(**changes):
    base = {
        "schema": sa.REQUEST_SCHEMA,
        "model": "ground-vehicle-2d",
        "mission": "delayed_after_fallback",
        "seed": 42,
        "controller": "dominant_axis",
        "overrides": {},
    }
    base.update(changes)
    return base


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class DescribeTests(unittest.TestCase):
    def test_declares_identity_physics_and_capabilities(self):
        d = sa.GroundVehicleAdapter(binary=None).describe()
        self.assertEqual(d["schema"], sa.ADAPTER_SCHEMA)
        self.assertEqual(d["model"]["id"], "ground-vehicle-2d")
        self.assertEqual(d["model"]["dimensions"], 2)
        self.assertIn("2D", d["model"]["physics"])
        self.assertFalse(d["model"]["six_dof"])
        caps = d["capabilities"]
        self.assertEqual(sorted(m["id"] for m in caps["missions"]), ["delayed_after_fallback", "nominal_stop", "x_first_overshoot"])
        self.assertEqual(caps["controllers"], ["dominant_axis", "x_first"])
        self.assertEqual(caps["actuator_fault_kinds"], ["continued_movement", "delayed_movement", "lost_movement"])
        self.assertTrue(caps["deterministic"])
        self.assertTrue(caps["replay"])
        for m in caps["missions"]:
            self.assertTrue(m["description"])
            self.assertGreater(m["steps"], 0)


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.adapter = sa.GroundVehicleAdapter(binary=None)

    def rejects(self, req, fragment):
        with self.assertRaises(sa.AdapterError) as ctx:
            self.adapter.validate(req)
        self.assertIn(fragment, str(ctx.exception))

    def test_accepts_a_default_request(self):
        norm = self.adapter.validate(request())
        self.assertEqual(norm["mission"], "delayed_after_fallback")
        self.assertEqual(norm["overrides"], {"gps_dropout": None, "actuator_fault": None})

    def test_rejects_malformed_requests(self):
        self.rejects(request(extra=1), "unknown field")
        self.rejects(request(schema="x"), "schema")
        self.rejects(request(model="rocket"), "model")
        self.rejects(request(mission="../m3/x"), "mission")
        self.rejects(request(controller="pid"), "controller")
        self.rejects(request(seed=-1), "seed")
        self.rejects(request(seed=True), "seed")
        self.rejects(request(seed=2**63), "seed")
        self.rejects(request(overrides={"wind": 3}), "unknown override")

    def test_rejects_out_of_range_fault_windows(self):
        self.rejects(request(overrides={"gps_dropout": {"start_tick": 5, "end_tick": 4}}), "start_tick")
        self.rejects(request(overrides={"gps_dropout": {"start_tick": 1, "end_tick": 999}}), "end_tick")
        self.rejects(request(overrides={"gps_dropout": {"start_tick": 1, "end_tick": 2, "x": 1}}), "unknown field")
        bad = {"kind": "delayed_movement", "start_tick": 2, "end_tick": 2, "probability_permille": 1000}
        self.rejects(request(overrides={"actuator_fault": bad}), "delay_ticks")
        self.rejects(request(overrides={"actuator_fault": dict(bad, delay_ticks=2, probability_permille=1001)}), "probability_permille")
        self.rejects(request(overrides={"actuator_fault": dict(bad, kind="teleport", delay_ticks=1)}), "kind")


@unittest.skipUnless(LAB.exists(), "release vv-lab binary not built")
class RunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.adapter = sa.GroundVehicleAdapter()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_run_is_deterministic_verified_and_does_not_touch_sources(self):
        source = ROOT / "scenarios/m3/delayed-after-fallback.json"
        before = sha(source)
        first = self.adapter.run(request(), self.tmp / "a")
        second = self.adapter.run(request(), self.tmp / "b")
        self.assertEqual(first["schema"], sa.RESULT_SCHEMA)
        self.assertEqual(first["run_id"], second["run_id"])
        self.assertEqual(first["provenance"]["artifacts"], second["provenance"]["artifacts"])
        self.assertEqual(first["replay"]["status"], "verified")
        self.assertEqual(first["integrity"]["problems"], [])
        self.assertEqual(sha(source), before)
        self.assertEqual(first["model"]["dimensions"], 2)

    def test_states_match_recorded_tick_results(self):
        result = self.adapter.run(request(), self.tmp / "a")
        events = json.loads((Path(result["run_dir"]) / "events.json").read_text(encoding="utf-8"))["events"]
        recorded = [e for e in events if e["event"]["kind"] == "tick_result"]
        self.assertEqual(len(result["states"]), len(recorded))
        for state, event in zip(result["states"], recorded):
            self.assertEqual(state["tick"], event["tick"])
            self.assertEqual(state["truth"], event["event"]["truth_position"])
            self.assertEqual(state["truth_from"], event["event"]["truth_from"])
            self.assertEqual(state["action"], event["event"]["action"])
            self.assertEqual(state["safety_state"], event["event"]["safety_state"])

    def test_overrides_change_inputs_and_outcome(self):
        default = self.adapter.run(request(), self.tmp / "a")
        clean = self.adapter.run(request(overrides={"gps_dropout": "none", "actuator_fault": "none"}), self.tmp / "b")
        self.assertNotEqual(default["run_id"], clean["run_id"])
        scenario = json.loads((Path(clean["run_dir"]) / "inputs/scenario.json").read_text(encoding="utf-8"))
        self.assertEqual(scenario["sensors"]["gps"]["dropout_windows"], [])
        actuator = json.loads((Path(clean["run_dir"]) / "inputs/actuator.json").read_text(encoding="utf-8"))
        self.assertEqual(actuator["faults"], [])
        self.assertNotIn("fallback", {s["safety_state"] for s in clean["states"]})
        self.assertIn("fallback", {s["safety_state"] for s in default["states"]})

    def test_tampered_run_is_flagged_and_fails_replay(self):
        result = self.adapter.run(request(), self.tmp / "a")
        run_dir = Path(result["run_dir"])
        events = run_dir / "events.json"
        data = bytearray(events.read_bytes())
        data[-5] = ord("0") if data[-5] != ord("0") else ord("1")
        events.write_bytes(bytes(data))
        check = self.adapter.verify(run_dir)
        self.assertTrue(any("events.json" in p for p in check["integrity"]["problems"]))
        self.assertEqual(check["replay"]["status"], "failed")

    def test_fresh_run_has_a_verified_verdict_and_passes_the_result_contract(self):
        result = self.adapter.run(request(), self.tmp / "a")
        self.assertEqual(result["verdict"], {"status": "verified", "reasons": []})
        sa.check_result(result)

    def assert_rejected(self, result, fragment):
        self.assertTrue(result["reused"])
        self.assertEqual(result["verdict"]["status"], "rejected")
        self.assertTrue(any(fragment in p for p in result["integrity"]["problems"]), result["integrity"]["problems"])
        sa.check_result(result)

    def test_reuse_rejects_edited_inputs(self):
        result = self.adapter.run(request(), self.tmp / "a")
        scenario = Path(result["run_dir"]) / "inputs" / "scenario.json"
        data = json.loads(scenario.read_text(encoding="utf-8"))
        data["sensors"]["gps"]["dropout_windows"] = []
        scenario.write_text(json.dumps(data), encoding="utf-8")
        self.assert_rejected(self.adapter.run(request(), self.tmp / "a", reuse=True), "inputs/scenario.json")

    def test_reuse_rejects_an_edited_implicit_default_even_with_consistent_manifest_hashes(self):
        # recovery_after_ticks is not in the input file: vv-lab inserts its default into events.json.
        req = request(mission="x_first_overshoot")
        result = self.adapter.run(req, self.tmp / "a")
        run_dir = Path(result["run_dir"])
        events = json.loads((run_dir / "events.json").read_text(encoding="utf-8"))
        self.assertNotIn("safety", json.loads((run_dir / "inputs/scenario.json").read_text(encoding="utf-8")))
        events["scenario"]["safety"]["recovery_after_ticks"] += 1
        (run_dir / "events.json").write_text(json.dumps(events), encoding="utf-8")
        m4 = json.loads((run_dir / "m4.json").read_text(encoding="utf-8"))
        m4["event_artifact"]["sha256"] = sha(run_dir / "events.json")
        (run_dir / "m4.json").write_text(json.dumps(m4), encoding="utf-8")
        self.assert_rejected(self.adapter.run(req, self.tmp / "a", reuse=True), "events.json")

    def test_reuse_rejects_an_artifact_from_another_run(self):
        other = self.adapter.run(request(mission="nominal_stop"), self.tmp / "b")
        result = self.adapter.run(request(), self.tmp / "a")
        run_dir = Path(result["run_dir"])
        shutil.copyfile(Path(other["run_dir"]) / "report.json", run_dir / "report.json")
        m4 = json.loads((run_dir / "m4.json").read_text(encoding="utf-8"))
        m4["report_artifact"]["sha256"] = sha(run_dir / "report.json")
        (run_dir / "m4.json").write_text(json.dumps(m4), encoding="utf-8")
        self.assert_rejected(self.adapter.run(request(), self.tmp / "a", reuse=True), "report.json")

    def test_reuse_rejects_files_the_request_does_not_produce(self):
        result = self.adapter.run(request(), self.tmp / "a")
        (Path(result["run_dir"]) / "extra.json").write_text("{}", encoding="utf-8")
        self.assert_rejected(self.adapter.run(request(), self.tmp / "a", reuse=True), "extra.json")

    def test_reuse_of_untouched_runs_is_verified_for_every_mission_and_fault(self):
        lost = {"kind": "lost_movement", "start_tick": 3, "end_tick": 4, "probability_permille": 1000}
        delayed = {"kind": "delayed_movement", "start_tick": 4, "end_tick": 4, "probability_permille": 1000, "delay_ticks": 3}
        cases = [request(mission=m) for m in ("nominal_stop", "x_first_overshoot", "delayed_after_fallback")]
        cases += [request(overrides=o) for o in ({"actuator_fault": lost}, {"actuator_fault": delayed},
                                                 {"gps_dropout": {"start_tick": 4, "end_tick": 7}},
                                                 {"gps_dropout": "none", "actuator_fault": "none"})]
        for req in cases:
            self.adapter.run(req, self.tmp / "a")
            again = self.adapter.run(req, self.tmp / "a", reuse=True)
            self.assertTrue(again["reused"])
            self.assertEqual(again["integrity"]["problems"], [], req)
            self.assertEqual(again["verdict"]["status"], "verified", req)
        self.assertEqual([p for p in (self.tmp / "a").iterdir() if p.name.startswith(".partial")], [])

    def test_failed_run_leaves_no_directory_to_reuse(self):
        # The Python interpreter is not vv-lab: run-m4 fails and must not leave a partial run behind.
        broken = sa.GroundVehicleAdapter(binary=sys.executable)
        with self.assertRaises(sa.AdapterError):
            broken.run(request(), self.tmp / "a")
        self.assertEqual([p.name for p in (self.tmp / "a").iterdir() if p.name != ".locks"], [])

    def test_stale_partial_directories_are_removed(self):
        run_id = self.adapter.run_id(self.adapter.validate(request()))
        stale = self.tmp / "a" / f".partial-{run_id}-99999-dead"
        (stale / "inputs").mkdir(parents=True)
        (stale / "m4.json").write_text("{}", encoding="utf-8")
        result = self.adapter.run(request(), self.tmp / "a")
        self.assertEqual(result["verdict"]["status"], "verified")
        self.assertFalse(stale.exists())

    def test_missing_binary_is_an_adapter_error(self):
        adapter = sa.GroundVehicleAdapter(binary=self.tmp / "no-such-binary.exe")
        with self.assertRaises(sa.AdapterError):
            adapter.run(request(), self.tmp / "a")


if __name__ == "__main__":
    unittest.main()
