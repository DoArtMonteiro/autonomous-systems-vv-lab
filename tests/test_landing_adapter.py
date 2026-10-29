"""rocket-landing adapter (contract v3): validation, ranges, runs, replay, tamper rejection, id binding."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import landing_adapter as la  # noqa: E402
import rocket_adapter as ra  # noqa: E402
import sim_adapter as sa  # noqa: E402

ROCKET = ra.default_rocket_binary()
TEMPLATES = ROOT / "crates" / "vv-rocket" / "landing"


def fault(kind="altimeter_bias", magnitude=20.0, start_s=10.0, end_s=40.0):
    return {"kind": kind, "magnitude": magnitude, "start_s": start_s, "end_s": end_s}


def request(policy="baseline", seed=0, flt="default"):
    return la.request_for(policy, seed, fault() if flt == "default" else flt)


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.adapter = la.LandingAdapter()

    def test_equal_requests_have_one_identity(self):
        a = self.adapter.validate(request(flt=fault(magnitude=20, start_s=10, end_s=40)))
        b = self.adapter.validate(request(flt=fault(magnitude=20.0, start_s=10.0, end_s=40.0)))
        self.assertEqual(a, b)
        self.assertEqual(self.adapter.run_id(a, "0" * 64), self.adapter.run_id(b, "0" * 64))
        # A magnitude on a fault that has none is normalized to zero, so omitting it is the same request.
        dropout = fault("gnss_dropout", 0, 8, 14)
        omitted = {k: v for k, v in dropout.items() if k != "magnitude"}
        self.assertEqual(self.adapter.validate(request(flt=dropout)), self.adapter.validate(request(flt=omitted)))
        # Step-aligned times are stored as the nearest two-decimal float, so 5.26 stays 5.26.
        self.assertEqual(self.adapter.validate(request(flt=fault("thrust_loss", 0.15, 5.26, 40.0)))["fault"]["start_s"], 5.26)

    def test_invalid_requests_are_refused_with_the_field_path(self):
        cases = [
            ({**request(), "overrides": {}}, "unknown field in request: overrides"),
            ({**request(), "schema": sa.REQUEST_SCHEMA_V2}, "schema must be vv-sim-run-request.v3"),
            ({**request(), "model": ra.MODEL_ID}, "model must be rocket-landing"),
            (request("greedy"), "policy must be one of"),
            (request(seed=-1), "seed must be an integer"),
            (request(seed=True), "seed must be an integer"),
            (request(seed=1.5), "seed must be an integer"),
            (request(seed=la.MAX_SEED + 1), "seed must be an integer"),
            (request(flt="altimeter_bias"), "fault must be an object"),
            (request(flt={**fault(), "extra": 1}), "unknown field in fault: extra"),
            (request(flt=fault("teleport")), "fault.kind must be one of"),
            (request(flt=fault(magnitude=4.99)), "fault.magnitude must be in"),
            (request("guarded", flt=fault("altimeter_bias_low", 4.99)), "fault.magnitude must be in"),
            (request("guarded", flt=fault("altimeter_bias_low", 50.01)), "fault.magnitude must be in"),
            (request("guarded", flt=fault("gnss_bias_low", 4.99)), "fault.magnitude must be in"),
            (request("guarded", flt=fault("gnss_bias_low", 30.01)), "fault.magnitude must be in"),
            (request("baseline_guarded", flt=fault("gnss_bias_low", -10)), "fault.magnitude must be in"),
            (request(flt=fault(magnitude=50.01)), "fault.magnitude must be in"),
            (request(flt=fault(magnitude="20")), "fault.magnitude must be a number"),
            (request(flt=fault(magnitude=float("nan"))), "fault.magnitude must be a number"),
            (request(flt={k: v for k, v in fault().items() if k != "magnitude"}), "fault.magnitude must be a number"),
            (request(flt=fault("gimbal_stuck", 1.0, 10, 12)), "fault.magnitude does not apply to gimbal_stuck"),
            (request(flt=fault("gimbal_stuck", True, 10, 12)), "fault.magnitude does not apply to gimbal_stuck"),
            (request(flt=fault("gimbal_stuck", 0, 10, 13.01)), "fault.end_s must make the gimbal_stuck window last"),
            (request(flt=fault("gimbal_stuck", 0, 10, 10.49)), "fault.end_s must make the gimbal_stuck window last"),
            (request(flt=fault("altimeter_dropout", 0, 18, 19.99)), "fault.end_s must make the altimeter_dropout window"),
            (request(flt=fault("gnss_dropout", 0, 8, 18.01)), "fault.end_s must make the gnss_dropout window"),
            (request(flt=fault(start_s=-1)), "fault.start_s must be in"),
            (request(flt=fault(end_s=40.01)), "fault.end_s must be in"),
            (request(flt=fault(start_s=10.005)), "fault.start_s must be a multiple of 0.01"),
            (request(flt=fault(start_s=10, end_s=10)), "fault.end_s must be after fault.start_s"),
            (request(flt=fault(start_s=12, end_s=10)), "fault.end_s must be after fault.start_s"),
            (request(flt=fault(start_s="10")), "fault.start_s must be a number"),
        ]
        for body, message in cases:
            with self.subTest(body=body), self.assertRaisesRegex(sa.AdapterError, message.replace(".", r"\.")):
                self.adapter.validate(body)

    def test_pre_registered_range_edges_are_accepted(self):
        edges = [("thrust_loss", 0.05, 5.26, 40.0), ("thrust_loss", 0.30, 5.26, 40.0),
                 ("ignition_delay", 0.1, 3.0, 8.0), ("ignition_delay", 1.0, 3.0, 8.0),
                 ("gimbal_stuck", 0, 10.0, 10.5), ("gimbal_stuck", 0, 10.0, 13.0),
                 ("altimeter_bias", 5.0, 10.0, 40.0), ("altimeter_bias", 50.0, 10.0, 40.0),
                 ("altimeter_dropout", 0, 18.0, 20.0), ("altimeter_dropout", 0, 14.0, 24.0),
                 ("gnss_dropout", 0, 8.0, 10.0), ("gnss_dropout", 0, 8.0, 18.0),
                 ("gnss_bias", 5.0, 8.0, 40.0), ("gnss_bias", 30.0, 8.0, 40.0),
                 ("imu_accel_bias", 0.05, 5.0, 40.0), ("imu_accel_bias", 0.5, 5.0, 40.0),
                 ("altimeter_bias_low", 5.0, 10.0, 40.0), ("altimeter_bias_low", 50.0, 10.0, 40.0),
                 ("gnss_bias_low", 5.0, 8.0, 40.0), ("gnss_bias_low", 30.0, 8.0, 40.0)]
        for kind, magnitude, start, end in edges:
            with self.subTest(kind=kind, magnitude=magnitude, start=start, end=end):
                self.adapter.validate(request(flt=fault(kind, magnitude, start, end)))

    def test_case_differs_from_the_nominal_template_only_in_name_policy_and_faults(self):
        template = json.loads((TEMPLATES / "nominal.json").read_text(encoding="utf-8"))
        case = self.adapter.case_for(self.adapter.validate(request("robust", 7, fault("thrust_loss", 0.2, 5.26, 40))))
        self.assertEqual(case["faults"], [fault("thrust_loss", 0.2, 5.26, 40.0)])
        self.assertEqual(case["controller"]["policy"], "robust")
        same = lambda c: {k: v for k, v in c.items() if k not in ("name", "faults")} | {"controller": {
            **c["controller"], "policy": None}}
        self.assertEqual(same(case), same(template))
        self.assertEqual(self.adapter.case_for(self.adapter.validate(request(flt=None)))["faults"], [])
        # The seed is a run argument, not part of the case.
        self.assertEqual(self.adapter.case_for(self.adapter.validate(request(seed=1))),
                         self.adapter.case_for(self.adapter.validate(request(seed=2))))

    def test_declared_defaults_are_the_demonstration_cases(self):
        for entry in self.adapter.describe()["capabilities"]["faults"]:
            for policy, suffix in (("baseline", ""), ("robust", "-robust")):
                name = entry["kind"].replace("_", "-") + suffix
                if not (TEMPLATES / f"{name}.json").exists():
                    self.assertIn(entry["kind"], ("altimeter_bias_low", "gnss_bias_low"))  # M9.1 faults: guarded demos only
                    continue
                with self.subTest(case=name):
                    stored = json.loads((TEMPLATES / f"{name}.json").read_text(encoding="utf-8"))
                    magnitude = (entry["magnitude"] or {"default": 0.0})["default"]
                    flt = fault(entry["kind"], magnitude, entry["default_start_s"], entry["default_end_s"])
                    case = self.adapter.case_for(self.adapter.validate(request(policy, 0, flt)))
                    self.assertEqual(case["faults"], stored["faults"])
                    self.assertEqual({k: v for k, v in case.items() if k != "name"},
                                     {k: v for k, v in stored.items() if k != "name"})

    def test_m91_declared_defaults_are_the_guarded_demonstration_cases(self):
        entries = {e["kind"]: e for e in self.adapter.describe()["capabilities"]["faults"]}
        for name, policy, kind in (("gnss-bias-guarded", "guarded", "gnss_bias"),
                                   ("altimeter-bias-low-guarded", "guarded", "altimeter_bias_low"),
                                   ("gnss-dropout-baseline-guarded", "baseline_guarded", "gnss_dropout")):
            with self.subTest(case=name):
                stored = json.loads((TEMPLATES / f"{name}.json").read_text(encoding="utf-8"))
                entry = entries[kind]
                magnitude = (entry["magnitude"] or {"default": 0.0})["default"]
                flt = fault(kind, magnitude, entry["default_start_s"], entry["default_end_s"])
                case = self.adapter.case_for(self.adapter.validate(request(policy, 0, flt)))
                self.assertEqual({k: v for k, v in case.items() if k != "name"},
                                 {k: v for k, v in stored.items() if k != "name"})
        nominal = json.loads((TEMPLATES / "m91-nominal.json").read_text(encoding="utf-8"))
        case = self.adapter.case_for(self.adapter.validate(request("guarded", 0, None)))
        self.assertEqual({k: v for k, v in case.items() if k != "name"}, {k: v for k, v in nominal.items() if k != "name"})
        # baseline and robust keep the frozen M9 template (no M9.1 gains in their cases).
        for policy in ("baseline", "robust"):
            gains = self.adapter.case_for(self.adapter.validate(request(policy, 0, None)))["controller"]["gains"]
            self.assertNotIn("ascent_abort_vz_mps", gains)

    def test_m91_policies_and_faults_are_declared_with_their_ranges(self):
        caps = self.adapter.describe()["capabilities"]
        self.assertEqual([p["id"] for p in caps["policies"]], ["baseline", "robust", "guarded", "baseline_guarded"])
        faults = {f["kind"]: f for f in caps["faults"]}
        self.assertEqual(list(faults)[-2:], ["altimeter_bias_low", "gnss_bias_low"])
        low = faults["altimeter_bias_low"]["magnitude"]
        self.assertEqual((low["min"], low["max"]), (5.0, 50.0))
        low = faults["gnss_bias_low"]["magnitude"]
        self.assertEqual((low["min"], low["max"]), (5.0, 30.0))
        self.assertEqual(caps["labels"]["S5_no_powered_ascent"], "Climb under power")
        for policy in ("guarded", "baseline_guarded"):
            self.adapter.validate(request(policy, 3, fault("gnss_bias_low", 12.5, 8.0, 40.0)))

    def test_v2_verification_contract(self):
        flag = {"step": 818, "t_s": 8.18}
        flags = {"source": "x", "sensor_disagreement_first": flag, "ascent_abort_first": None, "altimeter_rejected_first": flag}
        ok = {"schema": sa.LANDING_VERIFICATION_V2, "outcome": "landed", "requirements": [],
              "invariants": [{"id": f"S{i}_x"} for i in range(1, 6)], "controller_flags": flags}
        self.assertIsNone(sa._check_landing_verification_schema(ok))
        v1 = {**ok, "schema": sa.LANDING_VERIFICATION_V1, "invariants": ok["invariants"][:4]}
        self.assertIsNone(sa._check_landing_verification_schema(v1))
        for change in ({"invariants": ok["invariants"][:4]}, {"controller_flags": None},
                       {"controller_flags": {k: v for k, v in flags.items() if k != "ascent_abort_first"}},
                       {"controller_flags": {**flags, "ascent_abort_first": {"step": "x"}}},
                       {"schema": "vv-rocket-landing-verification.v3"}):
            with self.subTest(change=change), self.assertRaises(sa.AdapterError):
                sa._check_landing_verification_schema({**ok, **change})

    def test_describe_declares_policies_faults_and_limits(self):
        d = self.adapter.describe()
        self.assertEqual(d["schema"], sa.ADAPTER_SCHEMA_V3)
        self.assertEqual(d["model"]["id"], la.MODEL_ID)
        caps = d["capabilities"]
        self.assertEqual([p["id"] for p in caps["policies"]], ["baseline", "robust", "guarded", "baseline_guarded"])
        self.assertEqual(len(caps["faults"]), 10)
        bias = next(f for f in caps["faults"] if f["kind"] == "altimeter_bias")
        self.assertEqual((bias["magnitude"]["min"], bias["magnitude"]["max"]), (5.0, 50.0))
        gimbal = next(f for f in caps["faults"] if f["kind"] == "gimbal_stuck")
        self.assertIsNone(gimbal["magnitude"])
        self.assertEqual(gimbal["window_length_s"], {"min": 0.5, "max": 3.0})
        self.assertEqual(caps["requirements"]["pad_radius_m"], 10.0)
        self.assertEqual(caps["requirements"]["keep_out_radius_m"], 50.0)
        self.assertIn("not validated against flight data", d["model"]["validity"])
        json.dumps(d)

    def test_v3_result_contract(self):
        good = {"schema": sa.RESULT_SCHEMA_V3, "adapter": sa.ADAPTER_SCHEMA_V3, "run_id": "0123456789abcdef",
                "request": {"schema": sa.REQUEST_SCHEMA_V3, "model": la.MODEL_ID}, "reused": False,
                "model": {"id": la.MODEL_ID}, "provenance": {}, "inputs": {}, "states": [], "events": [], "summary": {},
                "replay": {"status": "verified"}, "integrity": {"problems": []},
                "verdict": {"status": "verified", "reasons": []}, "model_validity": "idealized",
                "verification": {"outcome": "landed", "requirements": [], "invariants": []}}
        sa.check_result(good)
        for change in ({"adapter": sa.ADAPTER_SCHEMA_V2}, {"model": {"id": ra.MODEL_ID}}, {"model": {"id": sa.MODEL_ID}},
                       {"verification": None}, {"verification": {}}, {"verification": {**good["verification"], "outcome": "crashed"}},
                       {"verification": {**good["verification"], "requirements": None}},
                       {"events": None}, {"model_validity": None},
                       {"request": {"model": la.MODEL_ID}},
                       {"request": {"schema": sa.REQUEST_SCHEMA_V2, "model": la.MODEL_ID}},
                       {"request": {"schema": sa.REQUEST_SCHEMA_V3, "model": ra.MODEL_ID}},
                       {"schema": sa.RESULT_SCHEMA_V2, "adapter": sa.ADAPTER_SCHEMA_V2},
                       {"verdict": {"status": "verified", "reasons": ["x"]}}):
            with self.subTest(change=change), self.assertRaises(sa.AdapterError):
                sa.check_result({**good, **change})
        # A rejected run need not carry verdicts: the page withholds them.
        sa.check_result({**good, "verification": {}, "replay": {"status": "failed"},
                         "verdict": {"status": "rejected", "reasons": ["replay failed"]}})

    def test_v1_and_v2_contracts_do_not_accept_the_landing_model(self):
        v2 = {"schema": sa.RESULT_SCHEMA_V2, "adapter": sa.ADAPTER_SCHEMA_V2, "run_id": "0123456789abcdef",
              "request": {"schema": sa.REQUEST_SCHEMA_V2, "model": la.MODEL_ID}, "reused": False,
              "model": {"id": la.MODEL_ID}, "provenance": {}, "inputs": {}, "states": [], "events": [], "summary": {},
              "replay": {"status": "verified"}, "integrity": {"problems": []},
              "verdict": {"status": "verified", "reasons": []}, "physics_reference": {"all_pass": True},
              "model_validity": "idealized"}
        with self.assertRaises(sa.AdapterError):
            sa.check_result(v2)
        with self.assertRaises(sa.AdapterError):
            ra.RocketAdapter().validate(request())


@unittest.skipUnless(ROCKET.exists(), "release vv-rocket binary not built")
class RunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.adapter = la.LandingAdapter()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_view(self, req, **kw):
        result = self.adapter.run(req, self.tmp, **kw)
        sa.check_result({k: v for k, v in result.items() if k != "run_dir"})
        return result

    def test_nominal_run_lands_and_is_verified(self):
        result = self.run_view(request(flt=None))
        self.assertEqual(result["verdict"], {"status": "verified", "reasons": []})
        self.assertEqual(result["replay"]["status"], "verified")
        self.assertTrue(all(c["pass"] for c in result["replay"]["checks"]))
        v = result["verification"]
        self.assertEqual((v["outcome"], v["requirements_pass"], v["invariants_pass"]), ("landed", True, True))
        self.assertEqual([r["id"][:2] for r in v["requirements"]], ["R1", "R2", "R3", "R4", "R5", "R6"])
        self.assertEqual([i["id"][:2] for i in v["invariants"]], ["S1", "S2", "S3", "S4", "S5"])
        self.assertEqual(v["schema"], sa.LANDING_VERIFICATION_V2)
        self.assertEqual(set(v["controller_flags"]) - {"source"}, set(sa.LANDING_FLAGS))
        self.assertTrue(all(v["controller_flags"][n] is None for n in sa.LANDING_FLAGS))
        self.assertEqual(result["provenance"]["binary_sha256"], sa.sha256_file(ROCKET))
        self.assertEqual(result["summary"]["end_reason"], "touchdown")
        self.assertEqual(result["states"][-1]["kind"], "touchdown")
        self.assertIn("not validated against flight data", result["model_validity"])

    def test_guarded_run_reports_controller_flags_apart_from_the_verdict(self):
        result = self.run_view(request("guarded", 0, fault("gnss_bias", 15.0, 8.0, 40.0)))
        v = result["verification"]
        self.assertEqual(result["verdict"]["status"], "verified")
        self.assertEqual(v["controller_flags"]["sensor_disagreement_first"]["t_s"], 8.18)
        self.assertIn("controller-reported", v["controller_flags"]["source"])
        self.assertEqual(v["outcome"], "hard_landing")
        self.assertTrue(v["invariants_pass"])

    def test_exit_code_2_is_a_result_not_an_error(self):
        # The pre-registered flagship: a +20 m altimeter bias makes the baseline policy hit the ground at about 20 m/s.
        baseline = self.run_view(request("baseline"))
        v = baseline["verification"]
        self.assertEqual(baseline["verdict"]["status"], "verified")
        self.assertEqual(v["outcome"], "hard_landing")
        self.assertFalse(v["requirements_pass"])
        self.assertTrue(v["invariants_pass"], "safety invariants are separate from the mission outcome")
        r1 = next(r for r in v["requirements"] if r["id"] == "R1_vertical_speed")
        self.assertFalse(r1["pass"])
        self.assertAlmostEqual(r1["value"], 20.4, delta=0.1)
        self.assertEqual(r1["cause"], ["altimeter_bias"])
        # The same case under the robust policy lands.
        robust = self.run_view(request("robust"))
        self.assertEqual(robust["verification"]["outcome"], "landed")
        self.assertNotEqual(robust["run_id"], baseline["run_id"])

    def test_every_pre_registered_range_edge_is_accepted_by_the_simulator_too(self):
        edges = [("thrust_loss", 0.05, 5.26, 40.0), ("thrust_loss", 0.30, 5.26, 40.0),
                 ("ignition_delay", 0.1, 3.0, 8.0), ("ignition_delay", 1.0, 3.0, 8.0),
                 ("gimbal_stuck", 0, 10.0, 10.5), ("gimbal_stuck", 0, 10.0, 13.0),
                 ("altimeter_bias", 5.0, 10.0, 40.0), ("altimeter_bias", 50.0, 10.0, 40.0),
                 ("altimeter_dropout", 0, 18.0, 20.0), ("altimeter_dropout", 0, 14.0, 24.0),
                 ("gnss_dropout", 0, 8.0, 10.0), ("gnss_dropout", 0, 8.0, 18.0),
                 ("gnss_bias", 5.0, 8.0, 40.0), ("gnss_bias", 30.0, 8.0, 40.0),
                 ("imu_accel_bias", 0.05, 5.0, 40.0), ("imu_accel_bias", 0.5, 5.0, 40.0),
                 ("altimeter_bias_low", 5.0, 10.0, 40.0), ("altimeter_bias_low", 50.0, 10.0, 40.0),
                 ("gnss_bias_low", 5.0, 8.0, 40.0), ("gnss_bias_low", 30.0, 8.0, 40.0)]
        for kind, magnitude, start, end in edges:
            with self.subTest(kind=kind, magnitude=magnitude, start=start, end=end):
                result = self.run_view(request(flt=fault(kind, magnitude, start, end)))
                self.assertEqual(result["verdict"]["status"], "verified")
                self.assertIn(result["verification"]["outcome"], sa.LANDING_OUTCOMES)
        self.assertEqual(len(list(self.tmp.glob("*/run.json"))), len(edges))

    def test_seed_changes_the_run_and_seed_zero_is_the_nominal_dispersion(self):
        zero = self.run_view(request("baseline", 0, None))
        one = self.run_view(request("baseline", 1, None))
        self.assertNotEqual(zero["run_id"], one["run_id"])
        self.assertEqual(zero["states"][0]["truth"]["position_m"], [80.0, 0.0, 3000.0])
        self.assertNotEqual(one["states"][0]["truth"]["position_m"], [80.0, 0.0, 3000.0])

    def test_reuse_regenerates_and_every_edit_is_rejected(self):
        first = self.run_view(request())
        again = self.run_view(request(), reuse=True)
        self.assertTrue(again["reused"])
        self.assertEqual(again["verdict"]["status"], "verified")
        self.assertEqual(again["provenance"]["artifacts"], first["provenance"]["artifacts"])
        run_dir = self.tmp / first["run_id"]
        for name, edit in (("verification.json", lambda t: t.replace('"outcome":"hard_landing"', '"outcome":"landed"', 1)),
                           ("trace.json", lambda t: t.replace('"kind":"touchdown"', '"kind":"periodic"', 1))):
            with self.subTest(name=name):
                original = (run_dir / name).read_text(encoding="utf-8")
                edited = edit(original)
                self.assertNotEqual(edited, original)
                (run_dir / name).write_text(edited, encoding="utf-8")
                result = self.run_view(request(), reuse=True)
                self.assertEqual(result["verdict"]["status"], "rejected")
                self.assertIn(f"{name} differs from the regenerated run", result["integrity"]["problems"])
                (run_dir / name).write_text(original, encoding="utf-8")
        with self.assertRaisesRegex(sa.AdapterError, "already exists"):
            self.adapter.run(request(), self.tmp)

    def test_verify_recomputes_stored_conclusions_and_rejects_edits(self):
        run_dir = self.tmp / self.run_view(request())["run_id"]
        self.assertEqual(self.adapter.verify(run_dir)["verdict"]["status"], "verified")

        def rejected(path, edit, problem):
            original = path.read_bytes()
            path.write_bytes(edit(original))
            try:
                view = self.adapter.verify(run_dir)
                self.assertEqual(view["verdict"]["status"], "rejected", path.name)
                self.assertTrue(any(problem in p for p in view["verdict"]["reasons"]), view["verdict"]["reasons"])
            finally:
                path.write_bytes(original)

        # A stored verdict that says the vehicle landed, with the manifest and its hash left alone.
        rejected(run_dir / "verification.json", lambda b: b.replace(b'"outcome":"hard_landing"', b'"outcome":"landed"'),
                 "replay failed")
        rejected(run_dir / "run.json", lambda b: b.replace(b'"outcome": "hard_landing"', b'"outcome": "landed"'), "replay failed")
        rejected(run_dir / "trace.json", lambda b: b.replace(b'"kind":"touchdown"', b'"kind":"periodic"', 1), "replay failed")
        rejected(run_dir / "inputs" / "request.json", lambda b: b"{}", "inputs cannot be checked")
        extra = run_dir / "inputs" / "more.json"
        extra.write_bytes(b"{}")
        try:
            view = self.adapter.verify(run_dir)
            self.assertIn("inputs/more.json is not produced by this adapter", view["verdict"]["reasons"])
        finally:
            extra.unlink()
        stored = (run_dir / "verification.json").read_bytes()
        (run_dir / "verification.json").unlink()
        try:
            view = self.adapter.verify(run_dir)
            self.assertEqual(view["verdict"]["status"], "rejected")
            self.assertIn("verification.json missing", view["integrity"]["problems"])
            self.assertEqual(view["verification"], {})
        finally:
            (run_dir / "verification.json").write_bytes(stored)
        self.assertEqual(self.adapter.verify(run_dir)["verdict"]["status"], "verified")

    def test_a_malformed_replay_report_is_an_error_verdict_not_an_exception(self):
        run_dir = self.tmp / self.run_view(request())["run_id"]
        real = self.adapter._call
        for stdout in ("[]", "42", '{"status": "verified"}', '{"checks": []}', '{"status": 1, "checks": []}',
                       '{"status": "verified", "checks": {}}'):
            fake = subprocess.CompletedProcess([], 0, stdout=stdout, stderr="")
            self.adapter._call = lambda *a, _f=fake: _f
            try:
                view = self.adapter.verify(run_dir)
            finally:
                self.adapter._call = real
            self.assertEqual(view["replay"]["status"], "error", stdout)
            self.assertEqual(view["verdict"]["status"], "rejected", stdout)

    def test_self_consistent_forgeries_that_replay_alone_cannot_see(self):
        run_dir = self.tmp / self.run_view(request("baseline", 0))["run_id"]
        saved = {n: (run_dir / n).read_bytes() for n in OUTPUTS}

        def forge(case_bytes, seed):
            other = self.tmp / f"forged-{seed}-{len(case_bytes)}"
            (other / "in").mkdir(parents=True)
            (other / "in" / "case.json").write_bytes(case_bytes)
            done = subprocess.run([str(ROCKET), "land", str(other / "in" / "case.json"), "--seed", str(seed),
                                   "--output", str(other / "out")], capture_output=True)
            self.assertIn(done.returncode, (0, 2), done.stderr)
            for n in OUTPUTS:
                (run_dir / n).write_bytes((other / "out" / n).read_bytes())

        try:
            # A different seed, self-consistent: replay recomputes from the stored seed and passes.
            forge((run_dir / "inputs" / "case.json").read_bytes(), 5)
            view = self.adapter.verify(run_dir)
            self.assertEqual(view["replay"]["status"], "verified", "replay alone cannot see a swapped seed")
            self.assertEqual(view["verdict"]["status"], "rejected")
            self.assertIn("run.json seed differs from the request", view["verdict"]["reasons"])
            # A different case (robust policy, no fault), same seed.
            for n, data in saved.items():
                (run_dir / n).write_bytes(data)
            other_case = self.adapter.case_for(self.adapter.validate(request("robust", 0, None)))
            forge(json.dumps(other_case).encode(), 0)
            view = self.adapter.verify(run_dir)
            self.assertEqual(view["replay"]["status"], "verified")
            self.assertEqual(view["verdict"]["status"], "rejected")
            self.assertIn("case.json differs from inputs/case.json", view["verdict"]["reasons"])
            self.assertIn("run.json policy differs from the request", view["verdict"]["reasons"])
        finally:
            for n, data in saved.items():
                (run_dir / n).write_bytes(data)
        self.assertEqual(self.adapter.verify(run_dir)["verdict"]["status"], "verified")

    def test_a_run_is_bound_to_its_id_request_and_binary(self):
        run_id = self.run_view(request())["run_id"]
        moved = self.tmp / "0123456789abcdef"
        shutil.copytree(self.tmp / run_id, moved)
        view = self.adapter.verify(moved)
        self.assertEqual(view["replay"]["status"], "verified", "replay alone cannot see a relocated run")
        self.assertEqual(view["verdict"]["status"], "rejected")
        self.assertTrue(any("is not the run id" in r for r in view["verdict"]["reasons"]), view["verdict"]["reasons"])
        self.assertTrue(self.adapter._identity_problems(self.tmp / run_id, "0" * 64))
        self.assertEqual(self.adapter._identity_problems(self.tmp / run_id, sa.sha256_file(ROCKET)), [])
        # Changing the stored request to another valid one while keeping the files is also rejected.
        edited = self.tmp / run_id / "inputs" / "request.json"
        original = edited.read_bytes()
        edited.write_bytes(sa._canonical(request("robust")))
        try:
            reasons = self.adapter.verify(self.tmp / run_id)["verdict"]["reasons"]
            self.assertTrue(any("is not the run id" in r for r in reasons), reasons)
            self.assertIn("inputs/case.json is not the case this request produces", reasons)
        finally:
            edited.write_bytes(original)

    def test_runs_of_the_rocket_and_landing_models_are_rejected_by_each_other(self):
        landing = self.run_view(request())
        rocket = ra.RocketAdapter().run({"schema": sa.REQUEST_SCHEMA_V2, "model": ra.MODEL_ID, "mission": "ballistic",
                                         "overrides": {}}, self.tmp)
        self.assertEqual(ra.RocketAdapter().verify(self.tmp / landing["run_id"])["verdict"]["status"], "rejected")
        view = self.adapter.verify(self.tmp / rocket["run_id"])
        self.assertEqual(view["verdict"]["status"], "rejected")

    def test_rust_refusal_is_an_adapter_error_without_leftovers(self):
        broken = la.LandingAdapter()
        broken.template = {**broken.template, "schema": "vv-rocket-landing.v0"}
        with self.assertRaisesRegex(sa.AdapterError, "refused the case"):
            broken.run(request(), self.tmp)
        self.assertEqual([p.name for p in self.tmp.iterdir() if p.name != ".locks"], [])

    def test_a_missing_binary_is_an_adapter_error(self):
        with self.assertRaisesRegex(sa.AdapterError, "binary not found"):
            la.LandingAdapter(binary=self.tmp / "absent").run(request(), self.tmp)


OUTPUTS = ("case.json", "trace.json", "run.json", "verification.json")


if __name__ == "__main__":
    unittest.main()
