"""Both Belief vs Truth artifacts are frozen (M19.2). Any change to their files fails this test.

* spikes/m19-belief-truth: iteration 2, the primary experimental candidate (owner decision 2026-11-25).
* spikes/m19-belief-truth-iteration3: iteration 3, an exploratory artifact preserved with its history
  (it exceeded the two-iteration limit; that breach is declared, not redefined).
"""
import hashlib
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

ARTIFACTS = {
    "m19-belief-truth": {
        "iteration": 2,
        "iterations": 2,
        "frozen_on": "2026-11-25",
        "status_has": ["primary experimental candidate", "iteration 2", "frozen 2026-11-25", "pending human testing",
                       "not an accepted usability improvement"],
    },
    "m19-belief-truth-iteration3": {
        "iteration": 3,
        "iterations": 3,
        "frozen_on": "2026-11-24",
        "status_has": ["exploratory artifact", "iteration 3 exceeded the two-iteration limit", "preserved"],
    },
}


class FrozenArtifacts(unittest.TestCase):
    def check(self, dirname):
        spike = ROOT / "spikes" / dirname
        manifest = json.loads((spike / "FROZEN.json").read_text(encoding="utf-8"))
        want = ARTIFACTS[dirname]
        self.assertEqual(manifest["iteration"], want["iteration"])
        self.assertEqual(manifest["iterations"], want["iterations"])
        self.assertEqual(manifest["iteration_limit"], 2)
        self.assertEqual(manifest["frozen_on"], want["frozen_on"])
        for phrase in want["status_has"]:
            self.assertIn(phrase, manifest["status"])
        present = sorted(
            p.relative_to(ROOT).as_posix()
            for p in spike.rglob("*")
            if p.is_file() and p.name != "FROZEN.json" and "__pycache__" not in p.parts
        )
        self.assertEqual(present, sorted(manifest["files"]), "files added or removed after the freeze")
        for rel, digest in manifest["files"].items():
            self.assertTrue(rel.startswith(f"spikes/{dirname}/"), rel)
            data = (ROOT / rel).read_bytes().replace(b"\r\n", b"\n")
            self.assertEqual(hashlib.sha256(data).hexdigest(), digest,
                             f"{rel} changed after the freeze; the artifact is frozen pending human testing")

    def test_iteration_2_primary_candidate_is_frozen(self):
        self.check("m19-belief-truth")

    def test_iteration_3_exploratory_artifact_is_preserved(self):
        self.check("m19-belief-truth-iteration3")

    def test_the_primary_candidate_is_the_iteration_2_commit(self):
        manifest = json.loads((ROOT / "spikes" / "m19-belief-truth" / "FROZEN.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["restored_from_commit"], "dae67fa")


if __name__ == "__main__":
    unittest.main()
