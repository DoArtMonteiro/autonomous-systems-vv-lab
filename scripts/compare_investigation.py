"""Compare a regenerated M13 investigation with the committed evidence.

The committed `investigation.json` records `source_sha256`, the hash of the vv-rocket source the
runs were made with, and the SHA-256 of every artifact file. A later change to the vv-rocket source
that does not change any result still changes that hash, and with it each written `run.json`, which
copies it. This check accepts exactly that difference and nothing else:

1. byte-identical files pass;
2. otherwise the two files must be equal once the top-level `source_sha256` and the `run.json`
   digests are set aside, so every trace, verification, case and signal digest still matches;
3. each regenerated `run.json`, with the new source hash replaced by the committed one, must hash to
   the committed digest, so the run manifests differ only in that hash.

The committed evidence is never rewritten. Exit 0 on a pass, 1 on a difference, 2 on usage errors.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path


def _strip(doc: dict) -> dict:
    out = copy.deepcopy(doc)
    out.pop("source_sha256", None)
    for artifact in out.get("artifacts", {}).values():
        artifact.get("files", {}).pop("run.json", None)
    return out


def compare(regenerated_dir: Path, committed: Path) -> tuple[bool, list[str]]:
    new_bytes = (regenerated_dir / "investigation.json").read_bytes()
    old_bytes = committed.read_bytes()
    if new_bytes == old_bytes:
        return True, ["byte-identical"]
    new = json.loads(new_bytes)
    old = json.loads(old_bytes)
    if _strip(new) != _strip(old):
        return False, ["results differ beyond the source hash and the run.json digests"]
    new_src, old_src = new.get("source_sha256"), old.get("source_sha256")
    if not all(isinstance(s, str) and len(s) == 64 for s in (new_src, old_src)):
        return False, ["source_sha256 missing or malformed"]
    notes = [f"source_sha256 {old_src} -> {new_src}"]
    old_artifacts = old.get("artifacts", {})
    for name in new.get("artifacts", {}):
        want = old_artifacts.get(name, {}).get("files", {}).get("run.json")
        if want is None:
            return False, [f"artifact {name} has no committed run.json digest"]
        run_bytes = (regenerated_dir / "artifacts" / name / "run.json").read_bytes()
        if run_bytes.count(new_src.encode()) != 1:
            return False, [f"artifact {name}: run.json does not carry the source hash exactly once"]
        restored = run_bytes.replace(new_src.encode(), old_src.encode())
        if hashlib.sha256(restored).hexdigest() != want:
            return False, [f"artifact {name}: run.json differs beyond the source hash"]
        notes.append(f"artifact {name}: run.json equal apart from the source hash")
    return True, notes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("regenerated", type=Path, help="directory written by vv-exec investigate")
    ap.add_argument("committed", type=Path, help="committed investigation.json")
    args = ap.parse_args(argv)
    if not (args.regenerated / "investigation.json").is_file() or not args.committed.is_file():
        print("missing investigation.json", file=sys.stderr)
        return 2
    ok, notes = compare(args.regenerated, args.committed)
    for line in notes:
        print(line)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
