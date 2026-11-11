r"""Packages the Cinematic View (M17) as a separately installable Studio module.

    python scripts/cinematic/package_module.py --godot-dir <dir with Godot_v4.7.2-stable_win64.exe> --out <dir>

The module runs the official Godot 4.7.2 Windows binary on the project directory
(`godot --path project`), so no export templates are needed. The zip holds:

    vv-cinematic-module.json      manifest (schema vv-cinematic-module.v1)
    godot/Godot_v4.7.2-stable_win64.exe, godot/Godot_v4.7.2-stable_win64_console.exe
    project/                      desktop/cinematic without generated caches
    LICENSES/                     Godot MIT licence and third-party notices (dumped from the
                                  binary itself), the module's MIT licence

The manifest lists every other file with its size and SHA-256; Studio verifies the zip's SHA-256
(given in <zip>.sha256), the manifest and every file before it installs anything. Nothing is
downloaded here: the Godot binary must already be on disk, extracted from the official release
zip whose SHA-512 (verified against the release's SHA512-SUMS.txt when it was downloaded) is
recorded below and in the manifest; the binary's own SHA-256 is in the file list.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PROJECT = os.path.join(REPO, "desktop", "cinematic")
MODULE_VERSION = "0.2.0"
GODOT_VERSION = "4.7.2-stable"
GODOT_EXE = "Godot_v4.7.2-stable_win64.exe"
GODOT_CONSOLE = "Godot_v4.7.2-stable_win64_console.exe"
# Official release asset and its SHA-512 from SHA512-SUMS.txt of the 4.7.2-stable release.
GODOT_ZIP_URL = "https://github.com/godotengine/godot/releases/download/4.7.2-stable/Godot_v4.7.2-stable_win64.exe.zip"
GODOT_ZIP_SHA512 = "83decd58fdf67b9d657958a1ae6bf1929c20785315a81effe245874cdc57acb709bf868e00778a96984338c1b29dafdb453c6847747694621c6ecf5da2259993"
MIN_VRAM_BYTES = 2 * 1000 ** 3
STUDIO_CONTRACT = {"interface": "vv-cinematic-launch.v1", "studio_min": "0.16.2"}
PROJECT_FILES = ("project.godot", "main.tscn")
PROJECT_DIRS = ("scripts", "shaders", "assets")

MODULE_LICENCE = """MIT License

Copyright (c) Autonomous Systems V&V Lab contributors

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
associated documentation files (the "Software"), to deal in the Software without restriction,
including without limitation the rights to use, copy, modify, merge, publish, distribute,
sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or
substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT
NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES
OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def stage(godot_dir, root):
    os.makedirs(os.path.join(root, "godot"))
    for name in (GODOT_EXE, GODOT_CONSOLE):
        shutil.copy2(os.path.join(godot_dir, name), os.path.join(root, "godot", name))
    proj = os.path.join(root, "project")
    os.makedirs(proj)
    for name in PROJECT_FILES:
        shutil.copy2(os.path.join(PROJECT, name), os.path.join(proj, name))
    for d in PROJECT_DIRS:
        shutil.copytree(os.path.join(PROJECT, d), os.path.join(proj, d), ignore=shutil.ignore_patterns("*.uid", "*.import"))
    lic = os.path.join(root, "LICENSES")
    os.makedirs(lic)
    console = os.path.join(godot_dir, GODOT_CONSOLE)
    out = subprocess.run([console, "--headless", "--path", PROJECT, "-s", "res://tools/licence_dump.gd", "--", lic],
                         capture_output=True, text=True, timeout=120)
    if out.returncode != 0 or not os.path.isfile(os.path.join(lic, "godot-LICENSE.txt")):
        sys.exit("could not dump the Godot licence texts: " + out.stderr[-500:])
    with open(os.path.join(lic, "vv-cinematic-LICENSE.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write(MODULE_LICENCE)
    notice = os.path.join(PROJECT, "assets", "cc0", "NOTICE-cc0.md")
    if os.path.isfile(notice):
        shutil.copy2(notice, os.path.join(lic, "NOTICE-cc0.md"))


def manifest(root):
    files = []
    total = 0
    for dirpath, _, names in os.walk(root):
        for n in sorted(names):
            p = os.path.join(dirpath, n)
            rel = os.path.relpath(p, root).replace(os.sep, "/")
            size = os.path.getsize(p)
            total += size
            files.append({"path": rel, "bytes": size, "sha256": sha256(p)})
    files.sort(key=lambda e: e["path"])
    # Third-party assets (CC0): provenance of every shipped file, with the sha256 of the file in the module.
    third_party = []
    prov = os.path.join(PROJECT, "assets", "cc0", "PROVENANCE.json")
    licences = [
        {"component": "Godot Engine 4.7.2-stable", "licence": "MIT", "file": "LICENSES/godot-LICENSE.txt"},
        {"component": "Third-party components of the Godot binary", "licence": "various (listed)", "file": "LICENSES/godot-COPYRIGHT.txt"},
        {"component": "VV Lab Cinematic View", "licence": "MIT", "file": "LICENSES/vv-cinematic-LICENSE.txt"},
    ]
    if os.path.isfile(prov):
        with open(prov, encoding="utf-8") as f:
            for a in json.load(f):
                third_party.append({
                    "id": a["id"], "title": a["title"], "category": a["category"], "source": a["source"],
                    "page_url": a["page_url"], "author": a.get("author"), "licence": "CC0 1.0",
                    "licence_evidence_url": a.get("licence_evidence_url"), "date_accessed": a.get("date_accessed"),
                    "processing": a.get("processing"),
                    "files": [{"path": "project/assets/" + e["path"], "bytes": e["bytes"], "sha256": e["sha256"]} for e in a["files"]],
                })
        licences.append({"component": "CC0 assets (Poly Haven, ambientCG): HDRI, ground, hull, rocks, shrubs, trees", "licence": "CC0 1.0", "file": "LICENSES/NOTICE-cc0.md"})
    return {
        "schema": "vv-cinematic-module.v1",
        "module": "cinematic",
        "name": "VV Lab Cinematic View",
        "version": MODULE_VERSION,
        "studio_contract": STUDIO_CONTRACT,
        "godot": {"version": GODOT_VERSION, "licence": "MIT", "source": GODOT_ZIP_URL, "zip_sha512": GODOT_ZIP_SHA512},
        "entry": {"exe": f"godot/{GODOT_EXE}", "project": "project"},
        "renderer": "Godot Forward+ (Vulkan); poses read from the run record, never simulated",
        "min_vram_bytes": MIN_VRAM_BYTES,
        "disk_bytes": total,
        "licences": licences,
        "third_party_assets": third_party,
        "files": files,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--godot-dir", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    exe = os.path.join(a.godot_dir, GODOT_EXE)
    if not os.path.isfile(exe) or not os.path.isfile(os.path.join(a.godot_dir, GODOT_CONSOLE)):
        sys.exit(f"{GODOT_EXE} and {GODOT_CONSOLE} must be in --godot-dir")
    os.makedirs(a.out, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="vv-cinematic-") as tmp:
        root = os.path.join(tmp, "module")
        os.makedirs(root)
        stage(a.godot_dir, root)
        m = manifest(root)
        zpath = os.path.join(a.out, f"vv-cinematic-{MODULE_VERSION}.zip")
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            z.writestr("vv-cinematic-module.json", json.dumps(m, indent=1) + "\n")
            for e in m["files"]:
                z.write(os.path.join(root, e["path"]), e["path"])
    digest = sha256(zpath)
    with open(zpath + ".sha256", "w", encoding="utf-8", newline="\n") as f:
        f.write(f"{digest}  {os.path.basename(zpath)}\n")
    print(json.dumps({"zip": zpath, "sha256": digest, "zip_bytes": os.path.getsize(zpath), "disk_bytes": m["disk_bytes"], "files": len(m["files"])}, indent=1))


if __name__ == "__main__":
    main()
