"""The must-not-change set of M19.1, captured by one command so that the same code measures before and after.

    python docs/evidence/m19/honesty/hash_set.py capture OUT.json
    python docs/evidence/m19/honesty/hash_set.py compare BEFORE.json AFTER.json OUT.json

What it records (all of it read from this checkout, nothing from the installed application):
  - source_sha256 of vv-rocket and vv-ascent, recomputed with the same file list and the same newline
    normalisation as `source_sha256()` in crates/*/src/lib.rs (the lists are parsed from those files);
  - the SHA-256 of every tracked file under docs/evidence/ (except this folder) and under exec/claims/;
  - the SHA-256 of the M1 scenario files, of scenarios/sha256.json and canonical-seed-42.json, and of every
    golden and fixture used by the Rust and Python tests;
  - the SHA-256 of the staged domain hosts and of vv-lab and vv-exec, when they have been built
    (desktop/build.ps1 -StageOnly), which are the "host hash" that the run identifiers depend on;
  - the run identifier and the SHA-256 of the record of every demonstration run of the four domain hosts
    (the seeds are the demonstration seeds the hosts accept), and the native M1 artefacts of the basic mission
    at seed 42 (vv-lab run), which are the canonical M1 output.
Nothing here runs a protected seed: the demonstrations are the ones shipped with the product.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
SELF_DIR = os.path.relpath(os.path.dirname(os.path.abspath(__file__)), REPO).replace(os.sep, "/")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def tracked(prefixes):
    out = subprocess.run(["git", "-C", REPO, "ls-files", "-z"], capture_output=True, check=True).stdout.decode()
    return sorted(p for p in out.split("\0") if p and any(p.startswith(x) for x in prefixes))


def file_hashes(paths):
    res = {}
    for p in paths:
        with open(os.path.join(REPO, p), "rb") as f:
            res[p] = sha(f.read())
    return res


def source_sha256(crate):
    """Same as `source_sha256()` of the crate: the (path, contents) pairs in the order of its list."""
    lib = open(os.path.join(REPO, "crates", crate, "src", "lib.rs"), encoding="utf-8").read()
    body = lib[lib.index("pub fn source_sha256"):]
    body = body[:body.index("let mut digest")]
    entries = re.findall(r'\(\s*"([^"]+)"\s*,\s*include_str!\("([^"]+)"\)\s*,?\s*\)', body)
    d = hashlib.sha256()
    for name, inc in entries:
        text = open(os.path.normpath(os.path.join(REPO, "crates", crate, "src", inc)), "rb").read().decode("utf-8")
        d.update(name.encode())
        d.update(b"\0")
        d.update(text.replace("\r\n", "\n").encode())
        d.update(b"\0")
    return {"files": len(entries), "sha256": d.hexdigest()}


def run_host(host, args, **kw):
    env = dict(os.environ)
    env["VV_LAB_BINARY"] = os.path.join(REPO, "desktop", "target", "root-static", "release", "vv-lab.exe")
    return subprocess.run([host] + args, capture_output=True, env=env, **kw)


def demos():
    root = os.path.join(REPO, "desktop", "target", "release", "domains")
    hosts = {
        "ground-vehicle": "vv-domain-ground.exe", "rocket-landing": "vv-domain-rocket.exe",
        "launch-ascent": "vv-domain-ascent.exe", "reference-oscillator": "vv-domain-reference.exe",
    }
    res = {}
    with tempfile.TemporaryDirectory(prefix="vv-m191-") as tmp:
        for dom, exe in hosts.items():
            host = os.path.join(root, dom, exe)
            if not os.path.isfile(host):
                continue
            cat = json.loads(run_host(host, ["describe"], check=True).stdout)
            for demo in cat.get("demos", []):
                for i, req in enumerate(demo["requests"]):
                    rf = os.path.join(tmp, "req.json")
                    out = os.path.join(tmp, f"{dom}-{demo['id']}-{i}")
                    with open(rf, "w", encoding="utf-8") as f:
                        json.dump(req, f)
                    r = run_host(host, ["run", rf, "--output", out])
                    key = f"{dom}/{demo['id']}/{i}"
                    if r.returncode != 0:
                        res[key] = {"error": r.stderr.decode()[:200]}
                        continue
                    raw = open(os.path.join(out, "record.json"), "rb").read()
                    rec = json.loads(raw)
                    res[key] = {"run_id": rec.get("run_id") or rec.get("id"), "record_sha256": sha(raw), "seed": req["seed"],
                                "native": {n: sha(open(os.path.join(out, "native", n), "rb").read()) for n in sorted(os.listdir(os.path.join(out, "native")))} if os.path.isdir(os.path.join(out, "native")) else {}}
    return res


def m1():
    lab = os.path.join(REPO, "desktop", "target", "root-static", "release", "vv-lab.exe")
    if not os.path.isfile(lab):
        return {}
    with tempfile.TemporaryDirectory(prefix="vv-m191-m1-") as tmp:
        out = os.path.join(tmp, "basic")
        r = subprocess.run([lab, "run", os.path.join(REPO, "scenarios", "basic-mission.json"), "--seed", "42", "--output", out], capture_output=True)
        res = {"exit": r.returncode}
        for n in sorted(os.listdir(out)) if os.path.isdir(out) else []:
            p = os.path.join(out, n)
            if os.path.isfile(p):
                res[n] = sha(open(p, "rb").read())
        return res


def capture():
    fixtures = tracked(["scenarios/", "tests/fixtures/", "crates/vv-ascent/tests/golden/", "crates/vv-rocket/tests/", "desktop/domain-ground/tests/golden/", "desktop/domain-rocket/tests/", "desktop/domain-ascent/tests/", "desktop/domain-reference/tests/"])
    bins = {}
    for name, rel in {"vv-lab": "desktop/target/root-static/release/vv-lab.exe", "vv-exec": "desktop/target/exec-static/release/vv-exec.exe",
                      "vv-domain-ground": "desktop/target/release/domains/ground-vehicle/vv-domain-ground.exe",
                      "vv-domain-rocket": "desktop/target/release/domains/rocket-landing/vv-domain-rocket.exe",
                      "vv-domain-ascent": "desktop/target/release/domains/launch-ascent/vv-domain-ascent.exe",
                      "vv-domain-reference": "desktop/target/release/domains/reference-oscillator/vv-domain-reference.exe"}.items():
        p = os.path.join(REPO, rel)
        if os.path.isfile(p):
            bins[name] = sha(open(p, "rb").read())
    return {
        "git_head": subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True).stdout.decode().strip(),
        "source_sha256": {"vv-rocket": source_sha256("vv-rocket"), "vv-ascent": source_sha256("vv-ascent")},
        "evidence_files": file_hashes([p for p in tracked(["docs/evidence/", "exec/claims/"]) if not p.startswith(SELF_DIR + "/")]),
        "m1_and_test_fixtures": file_hashes(fixtures),
        "staged_binaries": bins,
        "m1_basic_mission_seed42": m1(),
        "demonstration_runs": demos(),
    }


def flat(d, prefix=""):
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out.update(flat(v, f"{prefix}{k}/"))
        else:
            out[f"{prefix}{k}"] = v
    return out


def compare(a, b):
    fa, fb = flat(a), flat(b)
    keys = sorted(set(fa) | set(fb))
    same = [k for k in keys if fa.get(k) == fb.get(k) and k != "git_head"]
    diff = [{"key": k, "before": fa.get(k), "after": fb.get(k)} for k in keys if fa.get(k) != fb.get(k) and k != "git_head"]
    return {"before_head": a["git_head"], "after_head": b["git_head"], "compared": len(same) + len(diff), "identical": len(same), "different": diff}


if __name__ == "__main__":
    if sys.argv[1] == "capture":
        with open(sys.argv[2], "w", encoding="utf-8") as f:
            json.dump(capture(), f, indent=1, sort_keys=True)
            f.write("\n")
    else:
        res = compare(json.load(open(sys.argv[2], encoding="utf-8")), json.load(open(sys.argv[3], encoding="utf-8")))
        with open(sys.argv[4], "w", encoding="utf-8") as f:
            json.dump(res, f, indent=1, sort_keys=True)
            f.write("\n")
        print(f"{res['identical']} identical, {len(res['different'])} different of {res['compared']}")
        sys.exit(1 if res["different"] else 0)
