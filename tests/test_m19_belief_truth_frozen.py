"""The Belief vs Truth candidate is frozen (M19.2). Any change to its files fails this test."""
import hashlib
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPIKE = ROOT / "spikes" / "m19-belief-truth"


class FrozenCandidate(unittest.TestCase):
    def test_files_match_the_freeze_manifest(self):
        manifest = json.loads((SPIKE / "FROZEN.json").read_text(encoding="utf-8"))
        present = sorted(
            p.relative_to(ROOT).as_posix()
            for p in SPIKE.rglob("*")
            if p.is_file() and p.name != "FROZEN.json" and "__pycache__" not in p.parts
        )
        self.assertEqual(present, sorted(manifest["files"]), "files added or removed after the freeze")
        for rel, digest in manifest["files"].items():
            data = (ROOT / rel).read_bytes().replace(b"\r\n", b"\n")
            self.assertEqual(hashlib.sha256(data).hexdigest(), digest,
                             f"{rel} changed after the freeze; the candidate is frozen pending human testing")


if __name__ == "__main__":
    unittest.main()
