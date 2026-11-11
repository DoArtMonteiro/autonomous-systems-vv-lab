import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import compare_investigation as ci  # noqa: E402

OLD = "a" * 64
NEW = "b" * 64


def run_bytes(src: str, seed: int = 7) -> bytes:
    return json.dumps({"schema": "x", "source_sha256": src, "seed": seed}, indent=2).encode()


def investigation(src: str, run_digest: str, trace: str = "c" * 64) -> dict:
    return {
        "source_sha256": src,
        "probes": 3,
        "artifacts": {"twin": {"seed": 7, "files": {"run.json": run_digest, "trace.json": trace}}},
    }


class CompareInvestigation(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.committed = self.tmp / "committed.json"
        old_digest = hashlib.sha256(run_bytes(OLD)).hexdigest()
        self.committed.write_text(json.dumps(investigation(OLD, old_digest)), encoding="utf-8")
        self.regen = self.tmp / "regen"
        (self.regen / "artifacts" / "twin").mkdir(parents=True)

    def write(self, doc: dict, run: bytes) -> None:
        (self.regen / "investigation.json").write_text(json.dumps(doc), encoding="utf-8")
        (self.regen / "artifacts" / "twin" / "run.json").write_bytes(run)

    def test_identical_bytes_pass(self):
        self.write(json.loads(self.committed.read_text()), run_bytes(OLD))
        (self.regen / "investigation.json").write_bytes(self.committed.read_bytes())
        self.assertEqual(ci.compare(self.regen, self.committed), (True, ["byte-identical"]))

    def test_only_the_source_hash_changed_passes(self):
        run = run_bytes(NEW)
        self.write(investigation(NEW, hashlib.sha256(run).hexdigest()), run)
        ok, notes = ci.compare(self.regen, self.committed)
        self.assertTrue(ok, notes)

    def test_a_changed_trace_digest_fails(self):
        run = run_bytes(NEW)
        self.write(investigation(NEW, hashlib.sha256(run).hexdigest(), trace="d" * 64), run)
        self.assertFalse(ci.compare(self.regen, self.committed)[0])

    def test_a_run_manifest_that_changed_beyond_the_hash_fails(self):
        run = run_bytes(NEW, seed=8)
        self.write(investigation(NEW, hashlib.sha256(run).hexdigest()), run)
        self.assertFalse(ci.compare(self.regen, self.committed)[0])

    def test_a_changed_result_field_fails(self):
        run = run_bytes(NEW)
        doc = investigation(NEW, hashlib.sha256(run).hexdigest())
        doc["probes"] = 4
        self.write(doc, run)
        self.assertFalse(ci.compare(self.regen, self.committed)[0])


if __name__ == "__main__":
    unittest.main()
