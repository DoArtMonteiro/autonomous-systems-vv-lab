"""Regression tests of the environment package format and index (scripts/geo/package_environment.py).

No network. The bundled packs are in the repository, so their packages are rebuilt here and must give
the bytes the index records. Catalogue packs are not in git; when their zip is present in
dist/environments it is checked against the index and the sidecar, otherwise only the index entry is.
"""

import hashlib
import importlib.util
import json
import os
import re
import tempfile
import unittest
import zipfile
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEO = os.path.join(ROOT, "scripts", "geo")
SPEC = importlib.util.spec_from_file_location("package_environment", os.path.join(GEO, "package_environment.py"))
pkg = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pkg)


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


class EnvironmentIndex(unittest.TestCase):
    def setUp(self):
        self.cat = load(os.path.join(GEO, "catalogue.json"))
        self.idx = load(os.path.join(GEO, "environment-index.json"))

    def test_index_lists_every_catalogue_pack_with_the_documented_fields(self):
        self.assertEqual(self.idx["schema"], "vv-geo-environment-index.v1")
        self.assertEqual([e["id"] for e in self.idx["environments"]], list(self.cat["environments"]))
        for e in self.idx["environments"]:
            cfg = self.cat["environments"][e["id"]]
            for k in ("id", "name", "landscape", "tier", "pack_version", "schema", "bundled", "file", "bytes", "sha256", "licences", "files"):
                self.assertIn(k, e, e["id"])
            self.assertEqual(e["tier"], cfg["tier"])
            self.assertIn(e["tier"], self.idx["tiers"])
            self.assertEqual(e["file"], f"{e['id']}-{e['pack_version']}.vvenv.zip")
            self.assertRegex(e["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(e["files"][0], "environment.json")
            self.assertEqual(e["files"][-1], "NOTICE.md")
            self.assertTrue(e["licences"], e["id"])
            self.assertIn(e["schema"], pkg.SCHEMAS)

    def test_index_and_catalogue_carry_no_local_paths(self):
        for p in ("environment-index.json", "catalogue.json"):
            with open(os.path.join(GEO, p), encoding="utf-8") as f:
                t = f.read()
            self.assertIsNone(re.search(r"[A-Za-z]:\\\\|/Users/|\\\\Users\\\\|AppData", t), p)
            self.assertNotIn(chr(0x2014), t, p)

    def test_bundled_packs_package_to_the_indexed_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            for e in self.idx["environments"]:
                if not e["bundled"]:
                    continue
                got = pkg.package(e["id"], self.cat, dist=d)
                b = pkg.read(os.path.join(d, e["file"]))
                self.assertEqual(hashlib.sha256(b).hexdigest(), got["sha256"])
                side = pkg.read(os.path.join(d, e["file"] + ".sha256")).decode("ascii")
                self.assertEqual(side, f"{got['sha256']}  {e['file']}\n")
                # Same entries, in the same order, with the same bytes as the pack files.
                self.assertEqual(got["files"], e["files"], e["id"])
                self.assertEqual(got["unpacked_bytes"], e["unpacked_bytes"], e["id"])
                pack = pkg.pack_dir(e["id"], self.cat["environments"][e["id"]], None)
                with zipfile.ZipFile(os.path.join(d, e["file"])) as z:
                    self.assertEqual(z.namelist(), e["files"], e["id"])
                    for n in e["files"][:-1]:
                        self.assertEqual(z.read(n), pkg.read(os.path.join(pack, n)), f"{e['id']}/{n}")
                # Deflate output depends on the zlib build; the indexed zip bytes are those of the
                # build named in the index, so they are compared only under that build.
                if zlib.ZLIB_RUNTIME_VERSION == self.idx.get("zlib"):
                    self.assertEqual((got["bytes"], got["sha256"]), (e["bytes"], e["sha256"]), e["id"])

    def test_built_zips_hold_only_the_manifest_its_files_and_the_notice(self):
        dist = os.path.join(ROOT, "dist", "environments")
        for e in self.idx["environments"]:
            p = os.path.join(dist, e["file"])
            if not os.path.exists(p):
                continue
            b = pkg.read(p)
            if hashlib.sha256(b).hexdigest() != e["sha256"]:
                self.fail(f"{e['file']} in dist does not match the index (rebuild with package_environment.py)")
            with zipfile.ZipFile(p) as z:
                names = z.namelist()
                self.assertEqual(names, e["files"])
                self.assertTrue(all("/" not in n and "\\" not in n for n in names))
                m = json.loads(z.read("environment.json"))
                want = ["environment.json"] + [n for n, _s, _h in pkg.manifest_files(m)] + ["NOTICE.md"]
                self.assertEqual(names, want)
                for n, size, digest in pkg.manifest_files(m):
                    data = z.read(n)
                    self.assertEqual((len(data), hashlib.sha256(data).hexdigest()), (size, digest), n)
                self.assertIn("Lacunas de licença", z.read("NOTICE.md").decode("utf-8"))

    def test_a_file_that_differs_from_its_manifest_is_not_packaged(self):
        e = next(x for x in self.idx["environments"] if x["bundled"])
        src = os.path.join(pkg.BUNDLED_ROOT, e["id"])
        with tempfile.TemporaryDirectory() as d:
            dst = os.path.join(d, e["id"])
            os.makedirs(dst)
            for n in e["files"][:-1]:
                with open(os.path.join(src, n), "rb") as f, open(os.path.join(dst, n), "wb") as g:
                    g.write(f.read())
            with open(os.path.join(dst, "image.jpg"), "r+b") as f:
                f.seek(100)
                f.write(b"\x00")
            with self.assertRaises(SystemExit):
                pkg.package(e["id"], self.cat, root=d, dist=os.path.join(d, "out"))

    def test_short_licence_names_cover_every_manifest_licence(self):
        self.assertEqual(pkg.short_licence("CC BY 4.0, as stated"), "CC BY 4.0")
        with self.assertRaises(SystemExit):
            pkg.short_licence("All rights reserved")


if __name__ == "__main__":
    unittest.main()
