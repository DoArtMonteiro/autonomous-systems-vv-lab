"""Mission Control /landing: routes, origin checks, page contract, campaign reader and v3 runs through the server."""

from __future__ import annotations

import hashlib
import http.client
import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import landing_adapter as la  # noqa: E402
import landing_view as lv  # noqa: E402
import mission_control as mc  # noqa: E402
import rocket_adapter as ra  # noqa: E402
import sim_adapter as sa  # noqa: E402

ROCKET = ra.default_rocket_binary()
BIAS = {"kind": "altimeter_bias", "magnitude": 20.0, "start_s": 10.0, "end_s": 40.0}


def run_body(policy="baseline", seed=0, fault=BIAS):
    return la.request_for(policy, seed, fault)


def FIXTURE_CAMPAIGN() -> dict:
    """A synthetic campaign summary in the vv-m9-campaign.v1 shape. NOT produced by scripts/m9_campaign.py."""
    cell = lambda fault, policy, landed: {
        "fault": fault, "policy": policy, "runs": 3, "landed": landed, "landed_with_invariant_failure": 0,
        "hard_landing": 3 - landed, "no_contact": 0, "invariant_failure_runs": 0,
        "requirement_failures": {"R1": 3 - landed, "R2": 0, "R3": 0, "R4": 0, "R5": 0, "R6": 0}}
    runs = [{"fault": "altimeter_bias", "policy": p, "seed": 1000 + i, "group": "matrix", "magnitude": 20.0,
             "window": [10.0, 40.0], "outcome": "hard_landing" if p == "baseline" else "landed",
             "failed": ["R1"] if p == "baseline" else [], "exit_code": 2 if p == "baseline" else 0, "replay": "verified",
             "dir": f"matrix/altimeter_bias/{p}/seed-{1000 + i}"} for p in ("baseline", "robust") for i in range(3)]
    runs.append({"fault": "nominal", "policy": "robust", "seed": 1000, "group": "matrix", "magnitude": None, "window": None,
                 "outcome": "landed", "failed": [], "exit_code": 0, "replay": "verified", "dir": "matrix/nominal/robust/seed-1000"})
    return {
        "schema": "vv-m9-campaign.v1", "preregistered": False, "seeds": [1000, 1001, 1002], "boundary_seeds": [],
        "binary_sha256": "b" * 64, "source_sha256": "s" * 64, "template_sha256": "t" * 64, "command": "python scripts/m9_campaign.py",
        "machine": "fixture machine", "duration_s": 1.5, "resummarized": False, "total_runs": len(runs), "determinism_check": None,
        "cells": [cell("altimeter_bias", "baseline", 0), cell("altimeter_bias", "robust", 3), cell("nominal", "robust", 3)],
        "pairs": [{"fault": "altimeter_bias", "pairs": 3, "both_land": 0, "only_baseline": 0, "only_robust": 3, "neither": 0}],
        "hypotheses": [{"id": "H1", "statement": "<img src=x onerror=alert(1)> robust cumpre", "criterion": "criterio", "observed": {},
                        "complete": False, "verdict": "not_evaluated", "evidence": "fixture"}],
        "boundaries": [], "boundary_findings": [], "runs": runs, "limitations": ["fixture limitation"],
        "path_on_disk": "C:\\Users\\someone\\secret",  # a top-level key the page must not forward
    }


class Base(unittest.TestCase):
    summary: Path | None = None

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.server = mc.make_server(0, self.tmp / "runs", {sa.MODEL_ID: sa.GroundVehicleAdapter(), ra.MODEL_ID: ra.RocketAdapter(),
                                                             la.MODEL_ID: la.LandingAdapter()}, self.summary_path(),
                                     self.tmp / "m91-campaign" / "summary.json")
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def summary_path(self):
        return self.tmp / "m9-campaign" / "summary.json"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def call(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=120)
        hdrs = {"Host": f"127.0.0.1:{self.port}"}
        if body is not None:
            hdrs["Content-Type"] = "application/json"
        hdrs.update(headers or {})
        conn.request(method, path, body=json.dumps(body).encode() if body is not None else None, headers=hdrs)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp, data


class PageTests(Base):
    def test_landing_page_declares_the_workflow_and_keeps_the_three_statements_apart(self):
        resp, body = self.call("GET", "/landing")
        self.assertEqual(resp.status, 200)
        html = body.decode()
        self.assertIn("script-src 'self'", resp.getheader("Content-Security-Policy"))
        self.assertEqual(resp.getheader("X-Content-Type-Options"), "nosniff")
        for text in ("Powered landing", "Run", "Campaign evidence", "What is claimed", "Research", "/landing.js", 'lang="en"',
                     "not validated against flight data", "no contact model", "prefers-color-scheme:dark", "focus-visible",
                     "viewport", 'role="tablist"', 'aria-live="polite"', 'role="alert"'):
            self.assertIn(text, html)
        self.assertEqual(re.findall(r"https?://", html), [], "the page loads nothing from the network")
        resp, js = self.call("GET", "/landing.js")
        self.assertEqual(resp.status, 200)
        text = js.decode()
        self.assertNotIn("innerHTML", text)
        self.assertNotIn("eval(", text)
        # The only absolute URL in the script is the SVG namespace, which is not fetched.
        self.assertEqual(set(re.findall(r"https?://[^'\"\s)]+", text)), {"http://www.w3.org/2000/svg"})
        for marker in (
            "typeof data.run_id !== 'string'",  # a success without a run id is refused
            "!data.verification",
            "Mission outcome", "Safety invariants", "Evidence (integrity and replay)",  # three separate statements
            "withheld: this run is not verified evidence", "UNVERIFIED stored data, shown for diagnosis only",
            "Compare policies on this case", "Requirements at contact (R1 to R6)", "Safety invariants (${invRange(r)})", "Controller-reported flags (what the controller says; not a verdict)",
            "The verifier never reads these flags", "ascent_abort", "e.ascent_abort !== undefined",
            "Assumed demonstrator requirements", "R1 limit at contact", "keep-out", "Read from disk, not recomputed here",
            "No verified run to plot", "Not claimed", "Verified", "Assumed", "pad_radius_m", "/api/campaign",
            "estimate minus truth", "Gaps are sensor dropouts", "The fault never acted",
            "/api/campaign-m91", "M9.1 acceptance campaign", "Contained (S1 to S5 hold)", "Recovered (landed, R1 to R6, S1 to S5)",
            "Three separate statements", "compositionText9",
        ):
            self.assertIn(marker, text)

    def test_other_pages_link_to_the_landing_page_and_models_are_declared(self):
        for path in ("/", "/rocket"):
            self.assertIn(b'href="/landing"', self.call("GET", path)[1], path)
        resp, body = self.call("GET", "/api/models")
        models = json.loads(body)
        self.assertEqual(models["schema"], sa.ADAPTER_SCHEMA_V2, "the v2 listing is unchanged")
        self.assertEqual(models["models"][la.MODEL_ID]["schema"], sa.ADAPTER_SCHEMA_V3)
        self.assertEqual(json.loads(self.call("GET", "/api/describe")[1])["schema"], sa.ADAPTER_SCHEMA)

    def test_routes_refuse_foreign_hosts_and_origins(self):
        for path in ("/landing", "/landing.js", "/api/campaign", "/api/campaign-m91"):
            with self.subTest(path=path):
                self.assertEqual(self.call("GET", path, headers={"Host": "evil.example:80"})[0].status, 403)
                self.assertEqual(self.call("GET", path, headers={"Origin": "http://evil.example"})[0].status, 403)
                self.assertEqual(self.call("GET", path, headers={"Origin": f"http://127.0.0.1:{self.port}"})[0].status, 200)
        self.assertEqual(self.call("POST", "/api/campaign", run_body())[0].status, 404)
        self.assertEqual(self.call("POST", "/api/campaign-m91", run_body())[0].status, 404)
        self.assertEqual(self.call("POST", "/api/run", run_body(), {"Origin": "http://evil.example"})[0].status, 403)

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_the_script_parses(self):
        _, js = self.call("GET", "/landing.js")
        path = self.tmp / "landing.js"
        path.write_bytes(js)
        done = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)


class CampaignTests(Base):
    def write(self, value=None, raw=None):
        path = self.summary_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw if raw is not None else json.dumps(value).encode())
        return path

    def campaign(self):
        resp, body = self.call("GET", "/api/campaign")
        self.assertEqual(resp.status, 200)
        return json.loads(body)

    def test_missing_summary_says_how_to_make_it(self):
        out = self.campaign()
        self.assertFalse(out["found"])
        self.assertIn("run `python scripts/m9_campaign.py`", out["message"])

    def test_fixture_summary_is_forwarded_without_paths_or_unknown_fields(self):
        path = self.write(FIXTURE_CAMPAIGN())
        out = self.campaign()
        self.assertTrue(out["found"])
        self.assertEqual(out["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        summary = out["summary"]
        self.assertEqual(len(summary["runs"]), 7)
        self.assertNotIn("dir", summary["runs"][0])
        self.assertNotIn("path_on_disk", summary)
        self.assertNotIn("secret", json.dumps(out))
        self.assertEqual(summary["cells"][0]["fault"], "altimeter_bias")
        self.assertEqual(summary["hypotheses"][0]["verdict"], "not_evaluated")
        self.assertFalse(summary["preregistered"])

    def test_unusable_summaries_are_reported_as_not_found(self):
        broken = {**FIXTURE_CAMPAIGN()}
        cases = {
            "not json": dict(raw=b"{not json"),
            "not utf-8": dict(raw=b"\xff\xfe"),
            "a list": dict(value=[]),
            "wrong schema": dict(value={**broken, "schema": "vv-m9-campaign.v2"}),
            "cells not a list": dict(value={**broken, "cells": {}}),
            "a row that is not an object": dict(value={**broken, "runs": [1]}),
            "limitations not strings": dict(value={**broken, "limitations": [1]}),
        }
        for name, kwargs in cases.items():
            with self.subTest(name=name):
                self.write(**kwargs)
                out = self.campaign()
                self.assertFalse(out["found"])
                self.assertIn("m9_campaign.py", out["message"])

    def test_oversized_summary_is_refused(self):
        self.write(FIXTURE_CAMPAIGN())
        original = lv.MAX_CAMPAIGN_BYTES
        lv.MAX_CAMPAIGN_BYTES = 100
        try:
            out = self.campaign()
        finally:
            lv.MAX_CAMPAIGN_BYTES = original
        self.assertFalse(out["found"])
        self.assertIn("larger than the limit", out["reason"])

    def test_a_summary_that_is_a_symlink_is_not_followed(self):
        target = self.tmp / "elsewhere.json"
        target.write_text(json.dumps(FIXTURE_CAMPAIGN()), encoding="utf-8")
        path = self.summary_path()
        path.parent.mkdir(parents=True)
        try:
            path.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are not available")
        self.assertFalse(self.campaign()["found"])

    def test_the_m9_summary_forwards_the_composition_when_present(self):
        composition = {"matrix": {"scenarios": 9, "policies": 2, "seeds": 30, "runs": 540},
                       "boundary": {"faults": 2, "magnitudes": 6, "policies": 2, "seeds": 10, "runs": 240},
                       "total": 780, "repeat_runs_not_counted": 2}
        self.write({**FIXTURE_CAMPAIGN(), "composition": composition})
        self.assertEqual(self.campaign()["summary"]["composition"], composition)
        self.write(FIXTURE_CAMPAIGN())
        self.assertIsNone(self.campaign()["summary"]["composition"], "a summary from before the field is still readable")

    def test_the_default_summary_location_is_the_campaign_output_directory(self):
        self.assertEqual(mc.DEFAULT_CAMPAIGN_SUMMARY, ROOT / "runs" / "m9-campaign" / "summary.json")


@unittest.skipUnless(ROCKET.exists(), "release vv-rocket binary not built")
class RunTests(Base):
    def test_flagship_altimeter_bias_baseline_hits_hard_and_robust_lands(self):
        results = {}
        for policy in ("baseline", "robust"):  # one after the other, as the page does
            resp, body = self.call("POST", "/api/run", run_body(policy))
            self.assertEqual(resp.status, 200, body)
            result = json.loads(body)
            sa.check_result(result)
            self.assertEqual(result["schema"], sa.RESULT_SCHEMA_V3)
            self.assertEqual(result["verdict"]["status"], "verified")
            self.assertNotIn("run_dir", result)
            for place in (self.tmp, ROOT, ROCKET):
                self.assertNotIn(str(place.resolve()), body.decode())
                self.assertNotIn(json.dumps(str(place.resolve()))[1:-1], body.decode())
            results[policy] = result
        base, robust = results["baseline"]["verification"], results["robust"]["verification"]
        self.assertEqual((base["outcome"], robust["outcome"]), ("hard_landing", "landed"))
        r1 = next(r for r in base["requirements"] if r["id"].startswith("R1"))
        self.assertAlmostEqual(r1["value"], 20.4, delta=0.1)
        # The mission outcome is separate from the invariants and from the evidence verdict.
        self.assertTrue(base["invariants_pass"])
        self.assertFalse(base["requirements_pass"])
        self.assertNotEqual(results["baseline"]["run_id"], results["robust"]["run_id"])
        again = json.loads(self.call("POST", "/api/run", run_body("baseline"))[1])
        self.assertTrue(again["reused"])
        self.assertEqual(again["verdict"]["status"], "verified")

    def test_invalid_v3_requests_are_400_with_the_field_in_the_message(self):
        for body, prefix in ((run_body(fault={**BIAS, "magnitude": 99}), "fault.magnitude"),
                             (run_body(fault={**BIAS, "start_s": 10.001}), "fault.start_s"),
                             (run_body(seed=-3), "seed"),
                             ({**run_body(), "schema": sa.REQUEST_SCHEMA_V2}, "schema"),
                             ({**run_body(), "policy": "greedy"}, "policy")):
            with self.subTest(prefix=prefix):
                resp, out = self.call("POST", "/api/run", body)
                self.assertEqual(resp.status, 400)
                self.assertTrue(json.loads(out)["error"].startswith(prefix), out)
        # A v2 rocket request is not a landing request and the other way round.
        resp, out = self.call("POST", "/api/run", {"schema": sa.REQUEST_SCHEMA_V2, "model": la.MODEL_ID, "mission": "ballistic"})
        self.assertEqual(resp.status, 400)
        resp, out = self.call("POST", "/api/run", {**run_body(), "model": ra.MODEL_ID})
        self.assertEqual(resp.status, 400)

    def test_a_tampered_stored_run_is_served_as_rejected_never_as_verified(self):
        first = json.loads(self.call("POST", "/api/run", run_body())[1])
        stored = self.tmp / "runs" / first["run_id"] / "verification.json"
        stored.write_bytes(stored.read_bytes().replace(b'"outcome":"hard_landing"', b'"outcome":"landed"'))
        resp, body = self.call("POST", "/api/run", run_body())
        self.assertEqual(resp.status, 200)
        result = json.loads(body)
        self.assertEqual(result["verdict"]["status"], "rejected")
        self.assertIn("verification.json differs from the regenerated run", result["verdict"]["reasons"])

    def test_nominal_run_and_campaign_run_can_be_reconstructed_from_a_summary_row(self):
        # What the page sends for a campaign row: the row's fault, magnitude and window, and the policy under test.
        row = [r for r in FIXTURE_CAMPAIGN()["runs"] if r["policy"] == "baseline"][0]
        fault = {"kind": row["fault"], "magnitude": row["magnitude"], "start_s": row["window"][0], "end_s": row["window"][1]}
        resp, body = self.call("POST", "/api/run", run_body("baseline", row["seed"], fault))
        self.assertEqual(resp.status, 200, body)
        self.assertEqual(json.loads(body)["verdict"]["status"], "verified")
        resp, body = self.call("POST", "/api/run", run_body("robust", 1000, None))
        self.assertEqual(json.loads(body)["request"]["fault"], None)


if __name__ == "__main__":
    unittest.main()


def FIXTURE_M91():
    """A synthetic summary in the vv-m91-campaign.v1 shape. NOT produced by scripts/m91_campaign.py."""
    flags = {"sensor_disagreement": 0, "altimeter_rejected": 0, "ascent_abort": 0}
    cell = {"scenario": "gnss_bias", "policy": "guarded", "runs": 30, "outcome_landed": 3, "recovered": 3, "hard_landing": 27,
            "no_contact": 0, "detection": {**flags, "sensor_disagreement": 30}, "containment": 30, "r1_met": 30,
            "invariant_failures": {"S1": 0, "S2": 0, "S3": 0, "S4": 0, "S5": 0},
            "requirement_failures": {"R1": 0, "R2": 0, "R3": 0, "R4": 0, "R5": 27, "R6": 0}}
    return {"schema": "vv-m91-campaign.v1", "preregistered": False, "seeds": [2000], "total_runs": 1, "command": "python scripts/m91_campaign.py",
            "machine": "fixture", "duration_s": 1.0, "binary_sha256": "b" * 64, "source_sha256": "s" * 64, "template_sha256": "t" * 64,
            "determinism_check": None, "composition": None, "command_identity": None, "cells": [cell],
            "false_alarms": [{"scenario": "nominal", "runs": 30, "flags": flags, "within_limit": True}],
            "regressions": [{"scenario": "gnss_bias_low", "robust_recovered": 20, "guarded_recovered": 10, "difference": -10,
                             "within_g4_tolerance": False}],
            "hypotheses": [{"id": "G1", "statement": "<img src=x onerror=alert(1)>", "criterion": "c", "observed": {},
                            "verdict": "not_evaluated", "evidence": "fixture", "complete": False}],
            "runs": [{"scenario": "gnss_bias", "dir": "runs/x"}] * 5, "limitations": ["fixture limitation"],
            "path_on_disk": "C:\\Users\\someone\\secret"}


class M91CampaignReaderTests(Base):
    def m91(self):
        resp, body = self.call("GET", "/api/campaign-m91")
        self.assertEqual(resp.status, 200)
        return json.loads(body)

    def write91(self, value=None, raw=None):
        path = self.tmp / "m91-campaign" / "summary.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw if raw is not None else json.dumps(value).encode())

    def test_missing_summary_says_how_to_make_it(self):
        out = self.m91()
        self.assertFalse(out["found"])
        self.assertIn("run `python scripts/m91_campaign.py`", out["message"])

    def test_fixture_is_forwarded_without_the_per_run_rows_or_unknown_fields(self):
        self.write91(FIXTURE_M91())
        out = self.m91()
        self.assertTrue(out["found"])
        summary = out["summary"]
        self.assertEqual(out["schema"], "vv-m91-campaign.v1")
        self.assertEqual(summary["cells"][0]["detection"]["sensor_disagreement"], 30)
        self.assertEqual(summary["regressions"][0]["scenario"], "gnss_bias_low")
        self.assertNotIn("runs", summary)
        self.assertNotIn("path_on_disk", summary)
        self.assertNotIn("secret", json.dumps(out))

    def test_the_m9_summary_is_not_accepted_as_an_m91_one_and_the_reverse(self):
        self.write91(FIXTURE_CAMPAIGN())
        self.assertFalse(self.m91()["found"])
        path = self.summary_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(FIXTURE_M91()), encoding="utf-8")
        self.assertFalse(self.campaign_m9()["found"])

    def campaign_m9(self):
        return json.loads(self.call("GET", "/api/campaign")[1])

    def test_unusable_m91_summaries_are_reported_as_not_found(self):
        for name, kwargs in {"not json": dict(raw=b"{no"), "a list": dict(value=[]),
                             "cells not a list": dict(value={**FIXTURE_M91(), "cells": {}}),
                             "limitations not strings": dict(value={**FIXTURE_M91(), "limitations": [1]})}.items():
            with self.subTest(name=name):
                self.write91(**kwargs)
                self.assertFalse(self.m91()["found"])
