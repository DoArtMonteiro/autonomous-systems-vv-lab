"""The CC0 assets shipped with the Cinematic View are exactly the files recorded in assets/cc0/PROVENANCE.json.

For every entry: the licence is CC0, the source page and author are given, each file exists with the recorded
size and SHA-256, and no other file is in assets/cc0 besides PROVENANCE.json and NOTICE-cc0.md. When the staging
directory of the asset agent is present (CINEMATIC_CC0_STAGING, default D:\\vvwt\\cc0\\out) the recorded hashes are
also compared with the ones in its own PROVENANCE.json, so a changed copy is caught. The module's size limits
(desktop/studio/src/modules.rs: 512 files, 512 MiB per file, 1 GiB) are checked on the project directory.
"""

import hashlib
import json
import os
import unittest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ASSETS = os.path.join(REPO, "desktop", "cinematic", "assets")
CC0 = os.path.join(ASSETS, "cc0")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Cc0Assets(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(CC0, "PROVENANCE.json"), encoding="utf-8") as f:
            self.prov = json.load(f)

    def test_every_entry_is_cc0_with_its_source(self):
        self.assertGreaterEqual(len(self.prov), 20)
        for a in self.prov:
            self.assertIn("CC0", a["licence"], a["id"])
            self.assertTrue(a["licence_evidence_url"].startswith("https://"), a["id"])
            self.assertTrue(a["page_url"].startswith("https://"), a["id"])
            self.assertIn(a["source"], ("Poly Haven", "ambientCG"), a["id"])
            self.assertTrue(a["files"], a["id"])

    def test_files_match_the_recorded_sha256_and_nothing_else_ships(self):
        listed = set()
        for a in self.prov:
            for e in a["files"]:
                path = os.path.join(ASSETS, *e["path"].split("/"))
                self.assertTrue(os.path.isfile(path), e["path"])
                self.assertEqual(os.path.getsize(path), e["bytes"], e["path"])
                self.assertEqual(sha256(path), e["sha256"], e["path"])
                listed.add(os.path.normcase(os.path.abspath(path)))
        on_disk = set()
        for d, _, names in os.walk(CC0):
            for n in names:
                if n in ("PROVENANCE.json", "NOTICE-cc0.md"):
                    continue
                on_disk.add(os.path.normcase(os.path.abspath(os.path.join(d, n))))
        self.assertEqual(on_disk, listed)
        self.assertTrue(os.path.isfile(os.path.join(CC0, "NOTICE-cc0.md")))

    def test_hashes_agree_with_the_staging_provenance(self):
        staging = os.environ.get("CINEMATIC_CC0_STAGING", r"D:\vvwt\cc0\out")
        p = os.path.join(staging, "PROVENANCE.json")
        if not os.path.isfile(p):
            self.skipTest("the staging directory is not present")
        with open(p, encoding="utf-8") as f:
            theirs = {a["id"]: {os.path.basename(e["path"]): e["sha256"] for e in a["files"]} for a in json.load(f)}
        for a in self.prov:
            for e in a["files"]:
                self.assertEqual(theirs[a["id"]][os.path.basename(e["path"])], e["sha256"], e["path"])

    def test_project_directory_is_within_the_install_limits(self):
        files = 0
        total = 0
        for d, dirs, names in os.walk(os.path.join(REPO, "desktop", "cinematic")):
            dirs[:] = [x for x in dirs if x not in (".godot", "assets-src", "tools")]
            for n in names:
                if n.endswith((".import", ".uid")):
                    continue
                size = os.path.getsize(os.path.join(d, n))
                self.assertLess(size, 512 * 2 ** 20, n)
                files += 1
                total += size
        # The module adds the two Godot binaries (about 181 MB), the licences and the manifest.
        self.assertLess(files + 12, 512)
        self.assertLess(total + 200 * 10 ** 6, 2 ** 30)


if __name__ == "__main__":
    unittest.main()
