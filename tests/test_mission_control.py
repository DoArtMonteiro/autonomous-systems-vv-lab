from __future__ import annotations

import http.client
import json
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import mission_control as mc  # noqa: E402
import sim_adapter as sa  # noqa: E402
from adversarial_campaign import default_binary  # noqa: E402

LAB = default_binary("vv-lab")


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.server = mc.make_server(0, self.tmp, sa.GroundVehicleAdapter())
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def call(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)
        hdrs = {"Host": f"127.0.0.1:{self.port}"}
        if body is not None:
            hdrs["Content-Type"] = "application/json"
        hdrs.update(headers or {})
        data = json.dumps(body).encode() if isinstance(body, (dict, list)) else body
        conn.request(method, path, body=data, headers=hdrs)
        resp = conn.getresponse()
        payload = resp.read()
        conn.close()
        return resp, payload

    def run_body(self, **overrides):
        body = {"schema": sa.REQUEST_SCHEMA, "model": "ground-vehicle-2d", "mission": "delayed_after_fallback",
                "seed": 42, "controller": "dominant_axis", "overrides": {}}
        body.update(overrides)
        return body

    def test_page_shell_declares_modes_physics_and_security_headers(self):
        resp, html = self.call("GET", "/")
        self.assertEqual(resp.status, 200)
        text = html.decode()
        for label in ("Simple", "Advanced", "Research", "2D kinematic", "/app.js"):
            self.assertIn(label, text)
        self.assertIn("script-src 'self'", resp.getheader("Content-Security-Policy"))
        self.assertEqual(resp.getheader("X-Content-Type-Options"), "nosniff")
        resp, js = self.call("GET", "/app.js")
        self.assertEqual(resp.status, 200)
        self.assertNotIn(b"innerHTML", js)

    def test_describe_returns_the_adapter_contract(self):
        resp, body = self.call("GET", "/api/describe")
        self.assertEqual(resp.status, 200)
        self.assertEqual(json.loads(body)["schema"], sa.ADAPTER_SCHEMA)

    def test_unknown_path_is_404(self):
        resp, _ = self.call("GET", "/etc/passwd")
        self.assertEqual(resp.status, 404)

    @unittest.skipUnless(LAB.exists(), "release vv-lab binary not built")
    def test_run_returns_a_verified_result_without_absolute_paths(self):
        resp, body = self.call("POST", "/api/run", self.run_body())
        self.assertEqual(resp.status, 200, body)
        result = json.loads(body)
        self.assertEqual(result["replay"]["status"], "verified")
        self.assertNotIn("run_dir", result)
        for place in (self.tmp, ROOT, LAB):
            self.assertNotIn(str(place.resolve()), body.decode())
            self.assertNotIn(json.dumps(str(place.resolve()))[1:-1], body.decode())
        self.assertTrue(result["states"])
        # The same request again reuses the stored run and re-verifies it.
        resp, again = self.call("POST", "/api/run", self.run_body())
        self.assertEqual(resp.status, 200)
        again = json.loads(again)
        self.assertEqual(again["run_id"], result["run_id"])
        self.assertTrue(again["reused"])
        self.assertEqual(again["verdict"]["status"], "verified")

    def test_invalid_request_is_400_with_message(self):
        resp, body = self.call("POST", "/api/run", self.run_body(seed=-1))
        self.assertEqual(resp.status, 400)
        self.assertIn("seed", json.loads(body)["error"])

    def test_non_json_and_oversized_and_foreign_requests_are_refused(self):
        resp, _ = self.call("POST", "/api/run", b"seed=1", {"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(resp.status, 415)
        resp, _ = self.call("POST", "/api/run", b"{" + b" " * (mc.MAX_BODY_BYTES + 1) + b"}")
        self.assertEqual(resp.status, 413)
        resp, _ = self.call("POST", "/api/run", self.run_body(), {"Host": "evil.example:80"})
        self.assertEqual(resp.status, 403)
        resp, _ = self.call("POST", "/api/run", self.run_body(), {"Origin": "http://evil.example"})
        self.assertEqual(resp.status, 403)
        resp, _ = self.call("POST", "/api/run", b"{not json")
        self.assertEqual(resp.status, 400)

    def test_second_server_cannot_share_the_port(self):
        # On Windows SO_REUSEADDR lets a second socket bind a listening port and steal requests.
        with self.assertRaises(OSError):
            mc.make_server(self.port, self.tmp, sa.GroundVehicleAdapter()).server_close()

    def test_result_that_breaks_the_contract_is_never_sent_as_a_success(self):
        adapter = self.server.adapter
        good = {"schema": sa.RESULT_SCHEMA, "adapter": sa.ADAPTER_SCHEMA, "request": {}, "reused": False,
                "model": {}, "provenance": {}, "inputs": {}, "states": [], "replay": {"status": "verified"},
                "integrity": {"problems": []}, "verdict": {"status": "verified", "reasons": []}}
        original = adapter.run
        adapter.run = lambda *a, **k: dict(good)  # no run_id
        try:
            resp, body = self.call("POST", "/api/run", self.run_body())
        finally:
            adapter.run = original
        self.assertEqual(resp.status, 500)
        self.assertIn("run_id", json.loads(body)["error"])
        self.assertNotIn("run_id", json.loads(body))

    def test_page_refuses_a_success_without_run_id(self):
        _, js = self.call("GET", "/app.js")
        self.assertIn(b"typeof data.run_id !== 'string'", js)
        # A rejected run never shows its stored outcome as a result.
        self.assertIn(b"withheld: stored files differ from regeneration", js)
        self.assertIn(b"UNVERIFIED stored data, shown for diagnosis only", js)


if __name__ == "__main__":
    unittest.main()
