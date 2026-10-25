"""rocket-rigid-body adapter (contract v2): validation, runs, reuse, tamper rejection, server routing."""

from __future__ import annotations

import http.client
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import mission_control as mc  # noqa: E402
import rocket_adapter as ra  # noqa: E402
import sim_adapter as sa  # noqa: E402

ROCKET = ra.default_rocket_binary()
LAB_ADAPTER = sa.GroundVehicleAdapter()


def request(mission="propulsive_descent", **overrides):
    return {"schema": sa.REQUEST_SCHEMA_V2, "model": ra.MODEL_ID, "mission": mission, "overrides": overrides}


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.adapter = ra.RocketAdapter()

    def test_defaults_are_resolved_so_equal_requests_have_one_identity(self):
        explicit = self.adapter.validate(request(ignition_time_s=7.15, throttle=0.8))
        self.assertEqual(self.adapter.validate(request()), explicit)
        self.assertEqual(explicit["overrides"], {"ignition_time_s": 7.15, "throttle": 0.8})

    def test_invalid_requests_are_refused_with_the_field_name(self):
        cases = [
            ({**request(), "seed": 1}, "unknown field in request: seed"),
            ({**request(), "schema": sa.REQUEST_SCHEMA}, "schema must be"),
            ({**request(), "model": sa.MODEL_ID}, "model must be rocket-rigid-body"),
            (request(mission="orbit"), "mission must be one of"),
            (request(ignition_time_s=7.155), "overrides.ignition_time_s must be a multiple of 0.01"),
            (request(ignition_time_s=25.0), "overrides.ignition_time_s must be in"),
            (request(throttle=True), "overrides.throttle must be a number"),
            (request(throttle="0.5"), "overrides.throttle must be a number"),
            (request("ballistic", launch_speed_mps=float("inf")), "overrides.launch_speed_mps must be a number"),
            (request("ballistic", ignition_time_s=1.0), "unknown field in overrides: ignition_time_s"),
        ]
        for body, message in cases:
            with self.subTest(body=body), self.assertRaisesRegex(sa.AdapterError, message.replace(".", r"\.")):
                self.adapter.validate(body)

    def test_overrides_change_only_their_parameter_in_the_case(self):
        base = self.adapter.cases["attitude_dynamics"]
        case = self.adapter.case_for(self.adapter.validate(request("attitude_dynamics", roll_rate_radps=-2.0)))
        self.assertEqual(case["initial"]["angular_velocity_radps"], [-2.0, *base["initial"]["angular_velocity_radps"][1:]])
        self.assertEqual(case["vehicle"], base["vehicle"])
        fast = self.adapter.case_for(self.adapter.validate(request("ballistic", launch_speed_mps=400.0)))
        self.assertAlmostEqual(sum(v * v for v in fast["initial"]["velocity_mps"]) ** 0.5, 400.0, places=9)

    def test_v2_result_contract(self):
        good = {"schema": sa.RESULT_SCHEMA_V2, "adapter": sa.ADAPTER_SCHEMA_V2, "run_id": "0123456789abcdef",
                "request": {"schema": sa.REQUEST_SCHEMA_V2, "model": ra.MODEL_ID}, "reused": False,
                "model": {"id": ra.MODEL_ID}, "provenance": {},
                "inputs": {}, "states": [], "events": [], "summary": {}, "replay": {"status": "verified"},
                "integrity": {"problems": []}, "verdict": {"status": "verified", "reasons": []},
                "physics_reference": {"all_pass": False}, "model_validity": "idealized"}
        sa.check_result(good)
        for change in ({"adapter": sa.ADAPTER_SCHEMA}, {"model": {"id": sa.MODEL_ID}}, {"physics_reference": {}},
                       {"events": None}, {"model_validity": None}, {"request": {"model": ra.MODEL_ID}},
                       {"request": {"schema": sa.REQUEST_SCHEMA, "model": ra.MODEL_ID}},
                       {"schema": sa.RESULT_SCHEMA, "adapter": sa.ADAPTER_SCHEMA}):
            with self.subTest(change=change), self.assertRaises(sa.AdapterError):
                sa.check_result({**good, **change})


@unittest.skipUnless(ROCKET.exists(), "release vv-rocket binary not built")
class RunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.adapter = ra.RocketAdapter()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_a_run_is_verified_and_reports_physics_reference_separately(self):
        result = self.adapter.run(request(), self.tmp)
        sa.check_result(result)
        self.assertEqual(result["verdict"]["status"], "verified")
        self.assertEqual(result["replay"]["status"], "verified")
        self.assertTrue(all(c["pass"] for c in result["replay"]["checks"]))
        reference = result["physics_reference"]
        # Every active criterion passes; the two first-run criteria stay visible as history and are not passes.
        self.assertTrue(reference["all_pass"])
        self.assertEqual(reference["failed_criteria"], [])
        self.assertEqual((reference["cases_passed"], reference["cases_failed"], reference["cases_invalid"]), (12, 0, 0))
        history = {(h["case"], h["status"], bool(h["superseded_by"])) for h in reference["criteria_history"]}
        self.assertEqual(history, {("4-quaternions-and-frames", "fail", True), ("8-gimbal-torque", "invalid", False)})
        self.assertTrue(all(h["diagnosis"] for h in reference["criteria_history"]))
        self.assertIn("12 of 12", reference["summary"])
        self.assertIn("not counted as passes", reference["summary"])
        self.assertIn("flight-data-validation", {g["id"] for g in reference["gaps"]})
        self.assertEqual(result["provenance"]["binary_sha256"], sa.sha256_file(ROCKET))
        self.assertIn("not validated against flight data", result["model_validity"])
        crossing = [e for e in result["events"] if e["kind"] == "ground_crossing"]
        self.assertEqual(len(crossing), 1)
        self.assertIn("no contact model", crossing[0]["detail"]["note"])
        self.assertAlmostEqual(crossing[0]["detail"]["estimated_velocity_mps"][2], -17.36, places=1)

    def test_reuse_regenerates_and_every_edit_is_rejected(self):
        first = self.adapter.run(request("attitude_dynamics"), self.tmp)
        again = self.adapter.run(request("attitude_dynamics"), self.tmp, reuse=True)
        self.assertTrue(again["reused"])
        self.assertEqual(again["verdict"]["status"], "verified")
        run_dir = self.tmp / first["run_id"]
        for name, edit in (("trace.json", lambda t: t.replace('"propellant_kg":300.0', '"propellant_kg":299.0', 1)),
                           ("verification.json", lambda t: t.replace('"all_pass": true', '"all_pass": false'))):
            with self.subTest(name=name):
                original = (run_dir / name).read_text(encoding="utf-8")
                edited = edit(original)
                self.assertNotEqual(edited, original)
                (run_dir / name).write_text(edited, encoding="utf-8")
                result = self.adapter.run(request("attitude_dynamics"), self.tmp, reuse=True)
                self.assertEqual(result["verdict"]["status"], "rejected")
                self.assertIn(f"{name} differs from the regenerated run", result["integrity"]["problems"])
                (run_dir / name).write_text(original, encoding="utf-8")

    def test_verify_of_a_stored_run_recomputes_and_rejects_edits(self):
        run_dir = self.tmp / self.adapter.run(request("ballistic"), self.tmp)["run_id"]
        self.assertEqual(self.adapter.verify(run_dir)["verdict"]["status"], "verified")

        def rejected(path, edit, problem):
            original = path.read_bytes()
            path.write_bytes(edit(original))
            try:
                view = self.adapter.verify(run_dir)
                self.assertEqual(view["verdict"]["status"], "rejected", path.name)
                self.assertTrue(any(problem in p for p in view["verdict"]["reasons"]), view["verdict"]["reasons"])
                # The physics reference shown comes from this build, not from the edited file.
                self.assertTrue(view["physics_reference"]["all_pass"])
            finally:
                path.write_bytes(original)

        rejected(run_dir / "verification.json", lambda b: b.replace(b'"all_pass": true', b'"all_pass": false'),
                 "verification.json differs")
        rejected(run_dir / "inputs" / "request.json", lambda b: b"{}", "inputs cannot be checked")
        # A manifest that claims another outcome, with every hash intact, fails the replay.
        rejected(run_dir / "run.json", lambda b: b.replace(b'"end_reason": "ground"', b'"end_reason": "landed"'),
                 "replay failed")
        extra = run_dir / "inputs" / "more.json"
        extra.write_bytes(b"{}")
        try:
            view = self.adapter.verify(run_dir)
            self.assertEqual(view["verdict"]["status"], "rejected")
            self.assertIn("inputs/more.json is not produced by this adapter", view["verdict"]["reasons"])
        finally:
            extra.unlink()
        # A self-consistent forgery: a different case run by vv-rocket itself, so replay alone passes.
        forged = json.loads((run_dir / "case.json").read_text(encoding="utf-8"))
        forged["vehicle"]["drag_coefficient"] = 0.5
        other = self.tmp / "forged"
        other.mkdir()
        (other / "case.json").write_text(json.dumps(forged), encoding="utf-8")
        subprocess.run([str(ROCKET), "run", str(other / "case.json"), "--output", str(other / "out")], check=True,
                       capture_output=True)
        saved = {n: (run_dir / n).read_bytes() for n in ("case.json", "trace.json", "run.json")}
        try:
            for n in saved:
                (run_dir / n).write_bytes((other / "out" / n).read_bytes())
            view = self.adapter.verify(run_dir)
            self.assertEqual(view["replay"]["status"], "verified", "replay alone cannot see this forgery")
            self.assertEqual(view["verdict"]["status"], "rejected")
            self.assertIn("case.json differs from inputs/case.json", view["verdict"]["reasons"])
        finally:
            for n, data in saved.items():
                (run_dir / n).write_bytes(data)
        self.assertEqual(self.adapter.verify(run_dir)["verdict"]["status"], "verified")

    def test_a_run_is_bound_to_its_id_request_and_binary(self):
        run_id = self.adapter.run(request("ballistic"), self.tmp)["run_id"]
        moved = self.tmp / "0123456789abcdef"
        shutil.copytree(self.tmp / run_id, moved)
        view = self.adapter.verify(moved)
        self.assertEqual(view["replay"]["status"], "verified", "replay alone cannot see a relocated run")
        self.assertEqual(view["verdict"]["status"], "rejected")
        self.assertTrue(any("is not the run id" in r for r in view["verdict"]["reasons"]), view["verdict"]["reasons"])
        # Another binary gives another identity, so a stored run is not accepted as its output.
        self.assertTrue(self.adapter._identity_problems(self.tmp / run_id, "0" * 64))
        self.assertEqual(self.adapter._identity_problems(self.tmp / run_id, sa.sha256_file(ROCKET)), [])
        # The defaults are part of the identity: a request that names them is the same run.
        explicit = self.adapter.run(request("ballistic", **self.adapter.defaults("ballistic")), self.tmp, reuse=True)
        self.assertEqual(explicit["run_id"], run_id)
        self.assertTrue(explicit["reused"])

    @unittest.skipUnless(LAB_ADAPTER.binary is not None and LAB_ADAPTER.binary.is_file(), "release vv-lab binary not built")
    def test_runs_and_results_of_one_model_are_rejected_by_the_other(self):
        rocket = self.adapter.run(request("ballistic"), self.tmp)
        ground_view = LAB_ADAPTER.verify(self.tmp / rocket["run_id"])
        self.assertEqual(sa._verdict(ground_view["replay"], ground_view["integrity"]["problems"])["status"], "rejected")
        ground = LAB_ADAPTER.run({"schema": sa.REQUEST_SCHEMA, "model": sa.MODEL_ID, "mission": "nominal_stop",
                                  "seed": 42, "controller": "dominant_axis"}, self.tmp)
        rocket_view = self.adapter.verify(self.tmp / ground["run_id"])
        self.assertEqual(rocket_view["verdict"]["status"], "rejected")
        # Swapping the model or the request of a result between contracts breaks the contract.
        sa.check_result(rocket)
        sa.check_result(ground)
        for forged in ({**rocket, "model": ground["model"]}, {**rocket, "request": ground["request"]},
                       {**ground, "model": rocket["model"]}, {**ground, "request": rocket["request"]},
                       {**ground, "schema": sa.RESULT_SCHEMA_V2, "adapter": sa.ADAPTER_SCHEMA_V2},
                       # A consistent swap of both sides to the ground model under v2.
                       {**rocket, "model": {**rocket["model"], "id": sa.MODEL_ID},
                        "request": {**rocket["request"], "model": sa.MODEL_ID}}):
            with self.subTest(forged=(forged["schema"], forged["model"]["id"], forged["request"].get("model"))):
                with self.assertRaises(sa.AdapterError):
                    sa.check_result(forged)

    def test_parameter_changes_have_the_expected_physical_effect(self):
        late = self.adapter.run(request(ignition_time_s=7.15), self.tmp)
        early = self.adapter.run(request(ignition_time_s=7.10), self.tmp)
        self.assertEqual(late["summary"]["end_reason"], "ground")
        # Igniting 0.05 s earlier stops the fall above the ground and the open-loop burn climbs back.
        self.assertEqual(early["summary"]["end_reason"], "duration")
        self.assertFalse([e for e in early["events"] if e["kind"] == "ground_crossing"])
        self.assertGreater(early["states"][-1]["velocity_mps"][2], 0)
        vacuum = self.adapter.run(request("ballistic", drag_coefficient=0.0), self.tmp)
        drag = self.adapter.run(request("ballistic"), self.tmp)
        self.assertGreater(vacuum["summary"]["max_altitude_m"], drag["summary"]["max_altitude_m"])
        # Vacuum apex is v_z² / 2g for v_z = 160 m/s.
        self.assertAlmostEqual(vacuum["summary"]["max_altitude_m"], 160.0 ** 2 / (2 * 9.80665), delta=0.2)

    def test_a_case_the_rust_library_refuses_is_an_adapter_error(self):
        with self.assertRaisesRegex(sa.AdapterError, "propellant"):
            self.adapter.run(request(ignition_time_s=0.0, throttle=1.0), self.tmp)
        self.assertEqual([p.name for p in self.tmp.iterdir() if p.name != ".locks"], [])

    def test_concurrent_identical_requests_publish_one_run(self):
        code = ("import json, sys; sys.path.insert(0, sys.argv[1]); import rocket_adapter as ra; "
                "r = ra.RocketAdapter().run(json.loads(sys.argv[3]), sys.argv[2], reuse=True); "
                "print(json.dumps([r['run_id'], r['reused'], r['verdict']['status']]))")
        body = json.dumps(request("ballistic"))
        procs = [subprocess.Popen([sys.executable, "-c", code, str(ROOT / "scripts"), str(self.tmp), body],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(3)]
        out = []
        for proc in procs:
            stdout, stderr = proc.communicate(timeout=120)
            self.assertEqual(proc.returncode, 0, stderr)
            out.append(json.loads(stdout.strip().splitlines()[-1]))
        self.assertEqual(len({o[0] for o in out}), 1)
        self.assertEqual(sorted(o[1] for o in out), [False, True, True])
        self.assertEqual({o[2] for o in out}, {"verified"})


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.server = mc.make_server(0, self.tmp, {sa.MODEL_ID: LAB_ADAPTER, ra.MODEL_ID: ra.RocketAdapter()})
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def call(self, method, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=120)
        headers = {"Host": f"127.0.0.1:{self.port}", "Content-Type": "application/json"}
        conn.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp, data

    def test_models_page_and_script(self):
        resp, body = self.call("GET", "/api/models")
        models = json.loads(body)
        self.assertEqual(models["schema"], sa.ADAPTER_SCHEMA_V2)
        self.assertEqual(sorted(models["models"]), [sa.MODEL_ID, ra.MODEL_ID])
        self.assertTrue(models["models"][ra.MODEL_ID]["model"]["six_dof"])
        resp, page = self.call("GET", "/rocket")
        self.assertEqual(resp.status, 200)
        self.assertIn(b"not a landing", page)
        self.assertIn("script-src 'self'", resp.getheader("Content-Security-Policy"))
        resp, js = self.call("GET", "/rocket.js")
        self.assertEqual(resp.status, 200)
        self.assertNotIn(b"innerHTML", js)
        self.assertIn(b"!data.physics_reference", js)
        resp, body = self.call("GET", "/api/describe")
        self.assertEqual(json.loads(body)["schema"], sa.ADAPTER_SCHEMA, "v1 describe is unchanged")

    def test_unknown_model_is_400(self):
        resp, body = self.call("POST", "/api/run", {**request(), "model": "warp-drive"})
        self.assertEqual(resp.status, 400)
        self.assertIn("model must be one of", json.loads(body)["error"])

    @unittest.skipUnless(ROCKET.exists(), "release vv-rocket binary not built")
    def test_rocket_run_through_the_server_passes_the_contract_without_paths(self):
        resp, body = self.call("POST", "/api/run", request("ballistic"))
        self.assertEqual(resp.status, 200, body)
        result = json.loads(body)
        self.assertEqual(result["schema"], sa.RESULT_SCHEMA_V2)
        self.assertNotIn("run_dir", result)
        for place in (self.tmp, ROOT, ROCKET):
            self.assertNotIn(str(place.resolve()), body.decode())
            self.assertNotIn(json.dumps(str(place.resolve()))[1:-1], body.decode())


if __name__ == "__main__":
    unittest.main()
