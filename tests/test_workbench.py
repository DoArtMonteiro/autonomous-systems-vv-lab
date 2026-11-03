"""M10 workbench: multi-fault requests, the seed guard, compare, replay, evidence export, journeys and the page."""

from __future__ import annotations

import hashlib
import http.client
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import landing_adapter as la  # noqa: E402
import m10_campaign  # noqa: E402
import mission_control as mc  # noqa: E402
import rocket_adapter as ra  # noqa: E402
import sim_adapter as sa  # noqa: E402
import workbench as wb  # noqa: E402
import workbench_view as wv  # noqa: E402

ROCKET = ra.default_rocket_binary()
BIAS = {"kind": "altimeter_bias", "magnitude": 20.0, "start_s": 0.0, "end_s": 40.0}
DROPOUT = {"kind": "gnss_dropout", "magnitude": 0.0, "start_s": 8.0, "end_s": 14.0}
STUCK = {"kind": "altimeter_stuck", "magnitude": 0.0, "start_s": 8.0, "end_s": 12.0}
PROTECTED = (3000, 3050, 3099, 6000, 6099)


def compare(policies, seed=5000, faults=()):
    return {"schema": wb.COMPARE_SCHEMA, "policies": list(policies), "seed": seed, "faults": list(faults)}


class MultiFaultTests(unittest.TestCase):
    def setUp(self):
        self.adapter = la.LandingAdapter()

    def test_two_faults_are_validated_each_and_kept_in_order(self):
        req = self.adapter.validate(la.request_for_faults("m10_b_plus", 5000, [BIAS, DROPOUT]))
        self.assertEqual(req["faults"], [BIAS, DROPOUT])
        case = self.adapter.case_for(req)
        self.assertEqual(case["faults"], [BIAS, DROPOUT])
        self.assertLessEqual(len(case["name"]), 80)
        swapped = self.adapter.validate(la.request_for_faults("m10_b_plus", 5000, [DROPOUT, BIAS]))
        self.assertNotEqual(self.adapter.run_id(req, "0" * 64), self.adapter.run_id(swapped, "0" * 64))

    def test_the_single_fault_form_is_the_same_request_as_a_list_of_one(self):
        one = self.adapter.validate(la.request_for("robust", 5000, BIAS))
        listed = self.adapter.validate(la.request_for_faults("robust", 5000, [BIAS]))
        self.assertEqual(one, listed)
        self.assertEqual(self.adapter.validate(la.request_for("robust", 5000, None))["faults"], [])
        self.assertEqual(self.adapter.validate(la.request_for_faults("robust", 5000, []))["faults"], [])

    def test_invalid_fault_lists_are_refused_with_the_entry_named(self):
        both = {**la.request_for("robust", 5000, BIAS), "faults": [BIAS]}
        cases = [
            (both, "send either fault or faults, not both"),
            (la.request_for_faults("robust", 5000, [BIAS, DROPOUT, {**BIAS, "kind": "gnss_bias", "magnitude": 10}]),
             "faults must have at most 2 entries"),
            ({**la.request_for("robust", 5000, None), "faults": "x"}, "send either fault or faults"),
            ({**la.request_for_faults("robust", 5000, []), "faults": BIAS}, "faults must be a list"),
            (la.request_for_faults("robust", 5000, [BIAS, None]), r"faults\[1\] must be an object"),
            (la.request_for_faults("robust", 5000, [BIAS, {**BIAS, "magnitude": 10.0}]), "faults must not repeat a kind"),
            (la.request_for_faults("robust", 5000, [BIAS, {**DROPOUT, "end_s": 30.0}]),
             r"faults\[1\]\.end_s must make the gnss_dropout window last"),
            (la.request_for_faults("robust", 5000, [{**BIAS, "magnitude": 99.0}]), r"faults\[0\]\.magnitude must be in"),
            (la.request_for_faults("robust", 5000, [BIAS, {**DROPOUT, "extra": 1}]), r"unknown field in faults\[1\]: extra"),
            (la.request_for_faults("robust", 5000, [BIAS, STUCK]), r"faults\[1\]\.kind altimeter_stuck exists only in case "
                                                                   "schema v2"),
            (la.request_for("guarded", 5000, STUCK), r"fault\.kind altimeter_stuck exists only in case schema v2"),
        ]
        for body, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(sa.AdapterError, message):
                self.adapter.validate(body)
        # The same M10-only fault is valid for every M10 policy the adapter declares.
        for policy in sorted(la.M10_POLICIES):
            self.adapter.validate(la.request_for_faults(policy, 5000, [BIAS, STUCK]))


class SeedGuardTests(unittest.TestCase):
    def test_the_ranges_are_those_of_the_m10_campaign(self):
        self.assertEqual(la.EVALUATION_SEEDS, m10_campaign.EVALUATION_SEEDS)
        self.assertEqual(la.RESERVE_SEEDS, m10_campaign.RESERVE_SEEDS)

    def test_protected_seeds_are_refused_and_their_neighbours_are_not(self):
        adapter = la.LandingAdapter()
        for seed in PROTECTED:
            with self.subTest(seed=seed):
                self.assertTrue(la.protected_seed(seed))
                with self.assertRaisesRegex(sa.AdapterError, f"seed {seed} is an M10 (evaluation|reserve)"):
                    wb.guard_seed(seed)
                with self.assertRaisesRegex(sa.AdapterError, "never run"):
                    adapter.validate(la.request_for("m10_b_plus", seed, None))
        for seed in (2999, 3100, 5999, 6100, 0, 5000, True, "3000", 3000.0):
            with self.subTest(seed=seed):
                self.assertFalse(la.protected_seed(seed))
                wb.guard_seed(seed)  # not protected; the adapter checks the type and range itself
        caps = adapter.describe()["capabilities"]
        self.assertEqual([(p["min"], p["max"]) for p in caps["seed"]["protected"]], [(3000, 3099), (6000, 6099)])


class CompareAndJourneyTests(unittest.TestCase):
    def setUp(self):
        self.adapter = la.LandingAdapter()

    def test_compare_validates_every_policy_before_anything_runs(self):
        reqs = wb.compare_requests(compare(["m10_b_plus", "m10_a"], faults=[BIAS, DROPOUT]), self.adapter)
        self.assertEqual([r["policy"] for r in reqs], ["m10_b_plus", "m10_a"])
        self.assertTrue(all(r["seed"] == 5000 and r["faults"] == [BIAS, DROPOUT] for r in reqs))
        cases = [
            (compare([]), "policies must be a non-empty list"),
            (compare(["robust"] * 2), "policies must not repeat"),
            (compare(["robust", "guarded", "baseline", "m10_a", "m10_b"]), "at most 4 entries"),
            (compare(["m10_b_plus", "robust"], faults=[STUCK]), "robust: fault"),
            (compare(["m10_b_plus"], seed=3000), "seed 3000 is an M10 evaluation seed"),
            (compare(["m10_b_plus"], seed=6050), "seed 6050 is an M10 reserve seed"),
            ({**compare(["robust"]), "schema": "x"}, "schema must be"),
            ({**compare(["robust"]), "extra": 1}, "unknown field in request: extra"),
            (compare(["robust"], seed=-1), "seed must be an integer"),
        ]
        for body, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(sa.AdapterError, message):
                wb.compare_requests(body, self.adapter)

    def test_the_committed_journeys_are_well_formed_and_valid_requests(self):
        data = json.loads(wb.JOURNEYS.read_text(encoding="utf-8"))
        self.assertEqual(data["schema"], wb.JOURNEYS_SCHEMA)
        journeys = wb.load_journeys(self.adapter)["journeys"]
        self.assertGreaterEqual(len(journeys), 3)
        policies = {p["id"] for p in self.adapter.describe()["capabilities"]["policies"]}
        fault_counts = set()
        for j in journeys:
            with self.subTest(journey=j["id"]):
                for name in ("title", "narrative", "expectation"):
                    self.assertTrue(j[name].strip())
                self.assertTrue(1 <= len(j["policies"]) <= wb.MAX_COMPARE)
                self.assertTrue(set(j["policies"]) <= policies)
                self.assertIn(j["seed"], range(5000, 5100))
                self.assertFalse(la.protected_seed(j["seed"]))
                self.assertLessEqual(len(j["faults"]), la.MAX_FAULTS)
                self.assertTrue(j["look_at"] and all(isinstance(x, str) and x for x in j["look_at"]))
                fault_counts.add(len(j["faults"]))
        self.assertEqual(fault_counts, {0, 1, 2}, "a nominal, a single-fault and a two-fault journey")

    def test_a_journey_outside_the_development_seeds_or_with_a_refused_policy_is_refused(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            base = json.loads(wb.JOURNEYS.read_text(encoding="utf-8"))
            for change, message in ((lambda j: j.update(seed=3000), "development seed"),
                                    (lambda j: j.update(policies=["robust"], faults=[STUCK]), "robust: fault"),
                                    (lambda j: j.update(look_at=[]), "look_at"),
                                    (lambda j: j.pop("narrative"), "narrative")):
                data = json.loads(json.dumps(base))
                change(data["journeys"][0])
                (tmp / "j.json").write_text(json.dumps(data), encoding="utf-8")
                with self.subTest(message=message), self.assertRaisesRegex(sa.AdapterError, message):
                    wb.load_journeys(self.adapter, tmp / "j.json")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.runs = self.tmp / "runs"
        self.server = mc.make_server(0, self.runs, {la.MODEL_ID: la.LandingAdapter()}, self.tmp / "none.json",
                                     self.tmp / "none-m91.json")
        self.landing = self.server.adapters[la.MODEL_ID]
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def call(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=180)
        hdrs = {"Host": f"127.0.0.1:{self.port}"}
        if body is not None:
            hdrs["Content-Type"] = "application/json"
        hdrs.update(headers or {})
        data = body if isinstance(body, bytes) else (json.dumps(body).encode() if body is not None else None)
        conn.request(method, path, body=data, headers=hdrs)
        resp = conn.getresponse()
        payload = resp.read()
        conn.close()
        return resp, payload

    def assert_no_paths(self, text: str):
        for place in (self.tmp, self.runs, ROOT, ROCKET):
            resolved = place.resolve()
            for form in (str(resolved), resolved.as_posix(), json.dumps(str(resolved))[1:-1]):
                self.assertNotIn(form.lower(), text.lower())


class PageTests(Base):
    def test_page_and_script_keep_the_security_headers_and_build_the_dom_without_markup(self):
        resp, html = self.call("GET", "/workbench")
        self.assertEqual(resp.status, 200)
        csp = resp.getheader("Content-Security-Policy")
        self.assertIn("script-src 'self'", csp)
        self.assertIn("default-src 'none'", csp)
        self.assertEqual(resp.getheader("X-Content-Type-Options"), "nosniff")
        text = html.decode()
        self.assertIn('<script src="/workbench.js"></script>', text)
        self.assertEqual(re.findall(r"https?://", text), [], "the page loads nothing from the network")
        resp, js = self.call("GET", "/workbench.js")
        self.assertEqual(resp.status, 200)
        self.assertIn("script-src 'self'", resp.getheader("Content-Security-Policy"))
        code = js.decode()
        for banned in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
            self.assertNotIn(banned, code)
        self.assertEqual(set(re.findall(r"https?://[^'\"\s)]+", code)), {"http://www.w3.org/2000/svg"})
        self.assertIn(b'href="/workbench"', self.call("GET", "/")[1])

    def test_routes_refuse_foreign_hosts_and_origins_and_bad_bodies(self):
        for path in ("/workbench", "/workbench.js", "/api/workbench", "/api/workbench/evidence/0123456789abcdef"):
            with self.subTest(path=path):
                self.assertEqual(self.call("GET", path, headers={"Host": "evil.example:80"})[0].status, 403)
                self.assertEqual(self.call("GET", path, headers={"Origin": "http://evil.example"})[0].status, 403)
        for path in ("/api/workbench/compare", "/api/workbench/replay"):
            with self.subTest(path=path):
                self.assertEqual(self.call("POST", path, compare(["robust"]), {"Origin": "http://evil.example"})[0].status, 403)
                self.assertEqual(self.call("POST", path, b"x=1", {"Content-Type": "text/plain"})[0].status, 415)
                self.assertEqual(self.call("POST", path, b"{" + b" " * (mc.MAX_BODY_BYTES + 1) + b"}")[0].status, 413)
                self.assertEqual(self.call("POST", path, b"{not json")[0].status, 400)
        self.assertEqual(self.call("GET", "/api/workbench/evidence/../../etc")[0].status, 404)
        self.assertEqual(self.call("GET", "/api/workbench/evidence/0123456789ABCDEF")[0].status, 404)
        self.assertEqual(self.call("GET", "/api/workbench/evidence/0123456789abcdef")[0].status, 404)
        resp, body = self.call("POST", "/api/workbench/replay", {"run_id": "../x"})
        self.assertEqual(resp.status, 400)
        self.assertIn("16 lowercase hex", json.loads(body)["error"])

    def test_describe_lists_policies_from_the_adapter_and_the_journeys(self):
        resp, body = self.call("GET", "/api/workbench")
        self.assertEqual(resp.status, 200)
        data = json.loads(body)
        self.assertEqual(data["landing"], json.loads(json.dumps(self.landing.describe())))
        self.assertEqual(data["compare_max"], 4)
        self.assertEqual([j["id"] for j in data["journeys"]], [j["id"] for j in wb.load_journeys(self.landing)["journeys"]])
        self.assert_no_paths(body.decode())

    def test_protected_seeds_are_refused_before_the_simulator_runs(self):
        calls = []
        original = self.landing.run
        self.landing.run = lambda *a, **k: calls.append(a) or original(*a, **k)
        try:
            for seed in PROTECTED:
                with self.subTest(seed=seed):
                    resp, body = self.call("POST", "/api/workbench/compare", compare(["m10_b_plus"], seed=seed))
                    self.assertEqual(resp.status, 400)
                    self.assertIn(f"seed {seed} is an M10", json.loads(body)["error"])
                    resp, body = self.call("POST", "/api/run", la.request_for("m10_b_plus", seed, None))
                    self.assertEqual(resp.status, 400)
                    self.assertIn("never run", json.loads(body)["error"])
        finally:
            self.landing.run = original
        self.assertEqual(calls, [])
        self.assertEqual(list(self.runs.iterdir()) if self.runs.exists() else [], [])

    def test_a_compare_with_one_refused_policy_runs_nothing(self):
        calls = []
        self.landing.run = lambda *a, **k: calls.append(a)
        resp, body = self.call("POST", "/api/workbench/compare", compare(["m10_b_plus", "robust"], faults=[STUCK]))
        self.assertEqual(resp.status, 400)
        self.assertIn("robust: faults[0].kind altimeter_stuck", json.loads(body)["error"])
        resp, _ = self.call("POST", "/api/workbench/compare", compare(["robust", "guarded", "baseline", "m10_a", "m10_b"]))
        self.assertEqual(resp.status, 400)
        self.assertEqual(calls, [])

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_the_script_parses(self):
        _, js = self.call("GET", "/workbench.js")
        path = self.tmp / "workbench.js"
        path.write_bytes(js)
        done = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)


@unittest.skipUnless(ROCKET.exists(), "release vv-rocket binary not built")
class RunTests(Base):
    """Two real runs (one compare of two policies), then replay and evidence export of the stored run."""

    def test_compare_replay_and_evidence_of_a_two_fault_case(self):
        resp, body = self.call("POST", "/api/workbench/compare", compare(["m10_b_plus", "robust"], faults=[BIAS, DROPOUT]))
        self.assertEqual(resp.status, 200, body[:400])
        text = body.decode()
        self.assert_no_paths(text)
        data = json.loads(text)
        self.assertEqual(data["schema"], wb.COMPARE_SCHEMA)
        runs = data["runs"]
        self.assertEqual([r["request"]["policy"] for r in runs], ["m10_b_plus", "robust"])
        for r in runs:
            sa.check_result(r)
            self.assertNotIn("run_dir", r)
            self.assertEqual(r["verdict"]["status"], "verified")
            self.assertEqual(r["request"]["faults"], [BIAS, DROPOUT])
            self.assertEqual(r["request"]["seed"], 5000)
            self.assertEqual(r["case"]["faults"], [BIAS, DROPOUT])
            self.assertEqual([f["kind"] for f in r["verification"]["faults"]], ["altimeter_bias", "gnss_dropout"])
        self.assertIn("navigation", runs[0]["verification"])
        self.assertNotIn("navigation", runs[1]["verification"])
        run_id = runs[0]["run_id"]

        resp, body = self.call("POST", "/api/workbench/replay", {"run_id": run_id})
        self.assertEqual(resp.status, 200, body[:400])
        self.assert_no_paths(body.decode())
        replay = json.loads(body)
        self.assertEqual(replay["schema"], wb.REPLAY_SCHEMA)
        self.assertEqual(replay["replay"]["status"], "verified")
        self.assertTrue(replay["all_checks_pass"])
        self.assertTrue(all(c["pass"] for c in replay["replay"]["checks"]))
        self.assertEqual(replay["artifacts"], {n: sa.sha256_file(self.runs / run_id / n) for n in wb.RUN_FILES})

        resp, data = self.call("GET", f"/api/workbench/evidence/{run_id}")
        self.assertEqual(resp.status, 200, data[:400])
        self.assertEqual(resp.getheader("Content-Type"), "application/zip")
        self.assertEqual(resp.getheader("Content-Disposition"), f'attachment; filename="vv-m10-evidence-{run_id}.zip"')
        self.assertIn("script-src 'self'", resp.getheader("Content-Security-Policy"))
        archive = zipfile.ZipFile(io.BytesIO(data))
        names = sorted(archive.namelist())
        expected = sorted(f"{run_id}/{n}" for n in ("README.txt", "manifest.json", "request.json", "replay.json",
                                                    "run/case.json", "run/run.json", "run/trace.json",
                                                    "run/verification.json"))
        self.assertEqual(names, expected)
        self.assertTrue(all(not n.startswith("/") and ".." not in n and ":" not in n for n in names))
        manifest = json.loads(archive.read(f"{run_id}/manifest.json"))
        self.assertEqual(manifest["schema"], wb.EVIDENCE_SCHEMA)
        self.assertEqual(manifest["binary_sha256"], sa.sha256_file(ROCKET))
        self.assertEqual(manifest["source_sha256"], json.loads(archive.read(f"{run_id}/run/run.json"))["source_sha256"])
        self.assertEqual(manifest["replay_status"], "verified")
        self.assertEqual(manifest["request"], runs[0]["request"])
        listed = set(manifest["files"])
        self.assertEqual(listed, {n.split("/", 1)[1] for n in names} - {"manifest.json", "README.txt"})
        for name, digest in manifest["files"].items():
            self.assertEqual(hashlib.sha256(archive.read(f"{run_id}/{name}")).hexdigest(), digest, name)
        for name in ("case.json", "trace.json", "verification.json", "run.json"):
            self.assertEqual(archive.read(f"{run_id}/run/{name}"), (self.runs / run_id / name).read_bytes())
        readme = archive.read(f"{run_id}/README.txt").decode()
        for command in ("cargo build --release --manifest-path crates/vv-rocket/Cargo.toml",
                        f"vv-rocket replay runs/evidence/{run_id}/run", "--seed 5000"):
            self.assertIn(command, readme)
        self.assertIn("not validated against flight data", readme)
        for name in names:
            self.assert_no_paths(archive.read(name).decode("utf-8"))
        # The export is byte-reproducible: the same stored run gives the same zip.
        self.assertEqual(self.call("GET", f"/api/workbench/evidence/{run_id}")[1], data)

        # The extracted package replays as it stands.
        out = self.tmp / "evidence"
        archive.extractall(out)
        done = subprocess.run([str(ROCKET), "replay", str(out / run_id / "run")], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout)["status"], "verified")

    def test_a_stored_run_of_another_model_or_a_tampered_request_is_not_exported(self):
        fake = self.runs / "0123456789abcdef"
        (fake / "inputs").mkdir(parents=True)
        (fake / "inputs" / "request.json").write_text(json.dumps({"schema": sa.REQUEST_SCHEMA, "model": "ground-vehicle-2d"}))
        resp, body = self.call("GET", "/api/workbench/evidence/0123456789abcdef")
        self.assertEqual(resp.status, 400)
        self.assertIn("not a landing run", json.loads(body)["error"])
        (fake / "inputs" / "request.json").write_text(json.dumps(la.request_for("m10_b_plus", 3000, None)))
        resp, body = self.call("POST", "/api/workbench/replay", {"run_id": "0123456789abcdef"})
        self.assertEqual(resp.status, 400)
        self.assertIn("seed 3000", json.loads(body)["error"])


if __name__ == "__main__":
    unittest.main()
