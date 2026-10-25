"""Cross-process behaviour of GroundVehicleAdapter.run: locking, publication and recovery."""

from __future__ import annotations

import http.client
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import sim_adapter as sa  # noqa: E402
from adversarial_campaign import default_binary  # noqa: E402

LAB = default_binary("vv-lab")

# Runs one request in a fresh process and prints a one-line summary.
RUN_CHILD = """
import json, sys
sys.path.insert(0, sys.argv[1])
import sim_adapter as sa
req = json.loads(sys.argv[3])
try:
    r = sa.GroundVehicleAdapter().run(req, sys.argv[2], reuse=True)
    print(json.dumps({"run_id": r["run_id"], "reused": r["reused"], "verdict": r["verdict"]["status"],
                      "problems": r["integrity"]["problems"]}))
except sa.AdapterError as error:
    print(json.dumps({"error": str(error)}))
"""

# Takes the run lock, starts a partial directory as a real run would, then waits to be killed.
HOLD_CHILD = """
import sys, time
sys.path.insert(0, sys.argv[1])
from pathlib import Path
import sim_adapter as sa
root = Path(sys.argv[2])
with sa.run_lock(root, sys.argv[3], timeout=5):
    (root / f".partial-{sys.argv[3]}-held-0000" / "inputs").mkdir(parents=True)
    print("held", flush=True)
    time.sleep(60)
"""


def request(**changes):
    base = {"schema": sa.REQUEST_SCHEMA, "model": "ground-vehicle-2d", "mission": "delayed_after_fallback",
            "seed": 42, "controller": "dominant_axis", "overrides": {}}
    base.update(changes)
    return base


@unittest.skipUnless(LAB.exists(), "release vv-lab binary not built")
class ConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "runs"
        self.adapter = sa.GroundVehicleAdapter()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def spawn(self, code, *args):
        return subprocess.Popen([sys.executable, "-c", code, str(ROOT / "scripts"), str(self.root), *args],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def gather(self, procs):
        out = []
        for proc in procs:
            stdout, stderr = proc.communicate(timeout=120)
            self.assertEqual(proc.returncode, 0, stderr)
            out.append(json.loads(stdout.strip().splitlines()[-1]))
        return out

    def entries(self):
        return sorted(p.name for p in self.root.iterdir() if p.name != ".locks")

    def test_identical_concurrent_requests_publish_one_run_and_all_verify(self):
        body = json.dumps(request())
        results = self.gather([self.spawn(RUN_CHILD, body) for _ in range(4)])
        self.assertEqual({r.get("error") for r in results}, {None})
        self.assertEqual(len({r["run_id"] for r in results}), 1)
        self.assertEqual(sorted(r["reused"] for r in results), [False, True, True, True])
        self.assertEqual({r["verdict"] for r in results}, {"verified"})
        self.assertEqual(self.entries(), [results[0]["run_id"]])

    def test_different_concurrent_requests_do_not_interfere(self):
        bodies = [json.dumps(request(mission=m)) for m in ("nominal_stop", "x_first_overshoot", "delayed_after_fallback")]
        results = self.gather([self.spawn(RUN_CHILD, b) for b in bodies])
        self.assertEqual({r["verdict"] for r in results}, {"verified"})
        self.assertEqual(self.entries(), sorted(r["run_id"] for r in results))

    def test_a_killed_lock_holder_releases_the_lock_and_its_partial_is_discarded(self):
        run_id = self.adapter.run_id(self.adapter.validate(request()))
        holder = self.spawn(HOLD_CHILD, run_id)
        try:
            self.assertEqual(holder.stdout.readline().strip(), "held")
            busy = sa.GroundVehicleAdapter()
            busy.lock_timeout = 0.5
            with self.assertRaisesRegex(sa.AdapterError, "busy"):
                busy.run(request(), self.root)
        finally:
            holder.kill()
            holder.communicate()
        result = self.adapter.run(request(), self.root)
        self.assertEqual(result["verdict"]["status"], "verified")
        self.assertFalse(result["reused"])
        self.assertEqual(self.entries(), [run_id])


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def post(port, body):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=120)
    conn.request("POST", "/api/run", body=body, headers={"Host": f"127.0.0.1:{port}", "Content-Type": "application/json"})
    resp = conn.getresponse()
    data = json.loads(resp.read())
    conn.close()
    return resp.status, data


@unittest.skipUnless(LAB.exists(), "release vv-lab binary not built")
class TwoServersTests(unittest.TestCase):
    def test_two_servers_on_one_run_directory_publish_each_run_once(self):
        tmp = Path(tempfile.mkdtemp())
        servers = []
        try:
            ports = [free_port(), free_port()]
            for port in ports:
                proc = subprocess.Popen([sys.executable, "-u", str(ROOT / "scripts/mission_control.py"), "--port", str(port),
                                         "--output-root", str(tmp)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                servers.append(proc)
                self.assertIn("Mission Control on", proc.stdout.readline())
            bodies = [json.dumps(request()), json.dumps(request(mission="nominal_stop"))]
            jobs = [(port, body) for port in ports for body in bodies for _ in range(3)]
            with ThreadPoolExecutor(len(jobs)) as pool:
                answers = list(pool.map(lambda job: post(*job), jobs))
            self.assertEqual({status for status, _ in answers}, {200}, answers)
            self.assertEqual({data["verdict"]["status"] for _, data in answers}, {"verified"})
            ids = sorted({data["run_id"] for _, data in answers})
            self.assertEqual(len(ids), 2)
            for run_id in ids:
                fresh = [d for _, d in answers if d["run_id"] == run_id and not d["reused"]]
                self.assertEqual(len(fresh), 1, run_id)
            self.assertEqual(sorted(p.name for p in tmp.iterdir() if p.name != ".locks"), ids)
        finally:
            for proc in servers:
                proc.kill()
                proc.communicate()
            shutil.rmtree(tmp, ignore_errors=True)


class ResultContractTests(unittest.TestCase):
    def good(self):
        return {"schema": sa.RESULT_SCHEMA, "adapter": sa.ADAPTER_SCHEMA, "run_id": "0123456789abcdef",
                "request": {"schema": sa.REQUEST_SCHEMA, "model": sa.MODEL_ID}, "reused": False, "model": {"id": sa.MODEL_ID}, "provenance": {}, "inputs": {},
                "states": [], "replay": {"status": "verified"}, "integrity": {"problems": []},
                "verdict": {"status": "verified", "reasons": []}}

    def test_accepts_a_consistent_result(self):
        sa.check_result(self.good())

    def test_rejects_missing_or_malformed_fields(self):
        for change in ({"run_id": None}, {"run_id": "../x"}, {"schema": "x"}, {"reused": "no"},
                       {"verdict": {"status": "maybe", "reasons": []}}, {"integrity": {"problems": "none"}}):
            with self.subTest(change=change), self.assertRaises(sa.AdapterError):
                sa.check_result({**self.good(), **change})
        missing = self.good()
        del missing["run_id"]
        with self.assertRaisesRegex(sa.AdapterError, "run_id"):
            sa.check_result(missing)

    def test_rejects_a_verified_verdict_that_the_evidence_does_not_support(self):
        for change in ({"replay": {"status": "failed"}}, {"integrity": {"problems": ["events.json differs"]}}):
            with self.subTest(change=change), self.assertRaisesRegex(sa.AdapterError, "verdict"):
                sa.check_result({**self.good(), **change})


if __name__ == "__main__":
    unittest.main()
