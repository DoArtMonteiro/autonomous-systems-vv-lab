"""M10 engineering workbench: server-side requests, journeys and evidence packages for Mission Control.

Everything here sits behind `mission_control.make_server`, which keeps the same boundary for these routes
as for the others: 127.0.0.1 only, Host and Origin checks, JSON bodies up to 16 KiB, one simulation at a
time, path hiding and the CSP. This module adds three things the landing adapter does not do:

- the seed guard at the server boundary (the M10 evaluation and reserve seeds are refused before the
  adapter or the simulator is reached; the adapter refuses them too);
- compare requests: up to four policies on the same seed and faults, validated together before any run;
- the evidence package of a stored run: its files, a fresh `vv-rocket replay`, a SHA-256 manifest and the
  commands that reproduce it from a clean checkout, as a bounded zip with relative names only.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import subprocess
import zipfile
from pathlib import Path
from typing import Any, Callable

import landing_adapter as la
from sim_adapter import AdapterError, _only

ROOT = Path(__file__).resolve().parents[1]
JOURNEYS = ROOT / "scenarios" / "m10" / "journeys.json"
JOURNEYS_SCHEMA = "vv-workbench-journeys.v1"
COMPARE_SCHEMA = "vv-workbench-compare.v1"
REPLAY_SCHEMA = "vv-workbench-replay.v1"
EVIDENCE_SCHEMA = "vv-workbench-evidence.v1"
MAX_COMPARE = 4
RUN_ID = re.compile(r"[0-9a-f]{16}")
RUN_FILES = ("case.json", "run.json", "trace.json", "verification.json")  # what `vv-rocket replay` reads
MAX_EVIDENCE_BYTES = 8 * 1024 * 1024  # a landing trace is about 0.5 MB; anything far larger is not a run of this model
ZIP_DATE = (1980, 1, 1, 0, 0, 0)  # fixed member dates: the same run exports the same bytes


def guard_seed(seed: Any) -> None:
    """Refuse the M10 evaluation and reserve seeds before anything runs."""
    if la.protected_seed(seed):
        raise AdapterError(la.seed_refusal(seed))


# ---------------------------------------------------------------- compare


def compare_requests(body: Any, adapter: la.LandingAdapter) -> list[dict[str, Any]]:
    """Validate a compare body into one landing request per policy; nothing runs if any of them is refused."""
    obj = _only(body, {"schema", "policies", "seed", "faults"}, "request")
    if obj.get("schema") != COMPARE_SCHEMA:
        raise AdapterError(f"schema must be {COMPARE_SCHEMA}")
    guard_seed(obj.get("seed"))
    policies = obj.get("policies")
    if not isinstance(policies, list) or not policies or not all(isinstance(p, str) for p in policies):
        raise AdapterError("policies must be a non-empty list of policy ids")
    if len(policies) > MAX_COMPARE:
        raise AdapterError(f"policies must have at most {MAX_COMPARE} entries")
    if len(set(policies)) != len(policies):
        raise AdapterError("policies must not repeat a policy")
    faults = obj.get("faults", [])
    requests = []
    for policy in policies:
        try:
            requests.append(adapter.validate(la.request_for_faults(policy, obj.get("seed"), faults)))
        except AdapterError as error:
            raise AdapterError(f"{policy}: {error}") from error
    return requests


# ---------------------------------------------------------------- journeys


def load_journeys(adapter: la.LandingAdapter, path: Path = JOURNEYS) -> dict[str, Any]:
    """The committed demonstration journeys, each checked against the adapter without running anything."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") != JOURNEYS_SCHEMA or not isinstance(data.get("journeys"), list):
        raise AdapterError(f"journeys file must be a {JOURNEYS_SCHEMA} object with a journeys list")
    seen = set()
    for index, journey in enumerate(data["journeys"]):
        where = f"journeys[{index}]"
        j = _only(journey, {"id", "title", "narrative", "policies", "seed", "faults", "look_at", "expectation"}, where)
        for name in ("id", "title", "narrative", "expectation"):
            if not isinstance(j.get(name), str) or not j[name].strip():
                raise AdapterError(f"{where}.{name} must be a non-empty string")
        if j["id"] in seen:
            raise AdapterError(f"{where}.id repeats {j['id']}")
        seen.add(j["id"])
        look = j.get("look_at")
        if not isinstance(look, list) or not look or not all(isinstance(x, str) and x.strip() for x in look):
            raise AdapterError(f"{where}.look_at must be a non-empty list of strings")
        seed = j.get("seed")
        if not isinstance(seed, int) or isinstance(seed, bool) or not 5000 <= seed <= 5099:
            raise AdapterError(f"{where}.seed must be a development seed (5000 to 5099)")
        try:
            compare_requests({"schema": COMPARE_SCHEMA, "policies": j.get("policies"), "seed": seed,
                              "faults": j.get("faults")}, adapter)
        except AdapterError as error:
            raise AdapterError(f"{where}: {error}") from error
    return data


# ---------------------------------------------------------------- stored runs


def stored_run(output_root: Path, run_id: Any, adapter: la.LandingAdapter) -> tuple[Path, dict[str, Any]]:
    """The directory and validated request of a stored landing run; refuses anything else under the root."""
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        raise AdapterError("run_id must be 16 lowercase hex characters")
    run_dir = Path(output_root) / run_id
    if run_dir.is_symlink() or not run_dir.is_dir():
        raise FileNotFoundError(run_id)
    request_path = run_dir / "inputs" / "request.json"
    try:
        raw = json.loads(request_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise AdapterError(f"run {run_id} has no readable landing request") from error
    if isinstance(raw, dict):
        guard_seed(raw.get("seed"))
    try:
        request = adapter.validate(raw)
    except AdapterError as error:
        raise AdapterError(f"run {run_id} is not a landing run of this adapter: {error}") from error
    return run_dir, request


def replay_run(run_dir: Path, adapter: la.LandingAdapter) -> dict[str, Any]:
    """A fresh `vv-rocket replay` of the stored run plus the SHA-256 of each artifact it covered."""
    report = adapter.replay(run_dir)
    files = {n: _sha256(run_dir / n) for n in RUN_FILES if (run_dir / n).is_file()}
    return {"schema": REPLAY_SCHEMA, "run_id": run_dir.name, "replay": report, "artifacts": files,
            "binary_sha256": adapter._binary_sha(),
            "all_checks_pass": report.get("status") == "verified" and all(c.get("pass") for c in report.get("checks", []))}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_commit() -> dict[str, Any]:
    """Informative only: the commit of the serving checkout. `source_sha256` is the binding source identity."""
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=5)
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, capture_output=True,
                               text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return {"commit": None, "tracked_changes": None}
    commit = head.stdout.strip() if head.returncode == 0 else None
    return {"commit": commit if commit and re.fullmatch(r"[0-9a-f]{40}", commit) else None,
            "tracked_changes": bool(dirty.stdout.strip()) if dirty.returncode == 0 else None}


def readme(run_id: str, request: dict[str, Any], manifest: dict[str, Any]) -> str:
    seed = request["seed"]
    lines = [
        f"V&V lab, M10 workbench evidence package for run {run_id}",
        "",
        "What this is",
        f"  One closed-loop powered-landing run of the rocket-landing model: policy {request['policy']}, seed {seed},",
        f"  faults {json.dumps(request['faults'])}.",
        "  Idealized demonstrator, development configuration (not frozen). Not flight software, not certified,",
        "  not validated against flight data or hardware. Requirements and sensor models are assumed values.",
        "",
        "Contents",
        "  request.json             the validated adapter request (vv-sim-run-request.v3)",
        "  run/case.json            the case the simulator ran (copied by vv-rocket land)",
        "  run/run.json             the run manifest (seed, policy, source_sha256, artifact hashes)",
        "  run/trace.json           samples every 0.1 s: simulator truth, observations, controller estimate",
        "  run/verification.json    requirements R1-R6, invariants S1-S5 and the navigation block, by the verifier",
        "  replay.json              the output of vv-rocket replay on run/ at export time",
        "  manifest.json            SHA-256 of every file above, the binary SHA-256 and source_sha256",
        "",
        "Reproduce from a clean checkout",
        f"  1. Check out the sources whose build reports source_sha256 {manifest['source_sha256']}",
        f"     (the serving checkout was at commit {manifest['git']['commit'] or 'unknown'};",
        "     vv-rocket replay prints the source_sha256 of the build it runs).",
        "  2. Build the simulator:",
        "       cargo build --release --manifest-path crates/vv-rocket/Cargo.toml",
        f"  3. Unzip this package into runs/evidence (it creates runs/evidence/{run_id}/).",
        "  4. Replay the stored run; it recomputes trace, verification and manifest and compares them byte for byte:",
        f"       crates/vv-rocket/target/release/vv-rocket replay runs/evidence/{run_id}/run",
        "  5. Or run the same case again from scratch and compare the hashes with manifest.json:",
        f"       crates/vv-rocket/target/release/vv-rocket land runs/evidence/{run_id}/run/case.json "
        f"--seed {seed} --output runs/evidence/{run_id}-again",
        "  6. Or send request.json through Mission Control (python scripts/mission_control.py, then the workbench at",
        "     http://127.0.0.1:8780/workbench); the run id is bound to the request, the case and the binary.",
        "",
        "On Windows the binary is crates/vv-rocket/target/release/vv-rocket.exe.",
        "A different binary SHA-256 is expected on another machine or toolchain; source_sha256 and the trace and",
        "verification hashes are the identity to compare.",
    ]
    return "\n".join(lines) + "\n"


def evidence_zip(run_dir: Path, request: dict[str, Any], adapter: la.LandingAdapter,
                 scrub: Callable[[str], str]) -> tuple[bytes, str]:
    """A bounded, byte-reproducible zip of a stored run with a fresh replay; returns (bytes, file name)."""
    run_id = run_dir.name
    members: dict[str, bytes] = {"request.json": (run_dir / "inputs" / "request.json").read_bytes()}
    total = 0
    for name in RUN_FILES:
        path = run_dir / name
        if path.is_symlink() or not path.is_file():
            raise AdapterError(f"run {run_id} is missing {name}")
        total += path.stat().st_size
        if total > MAX_EVIDENCE_BYTES:
            raise AdapterError(f"run {run_id} is larger than the {MAX_EVIDENCE_BYTES} byte evidence limit")
        members[f"run/{name}"] = path.read_bytes()
    replay = replay_run(run_dir, adapter)
    # The replay report is the only member produced here from process output; scrub it like any response.
    members["replay.json"] = scrub(json.dumps(replay, indent=2, sort_keys=True)).encode("utf-8")
    run_manifest = json.loads(members["run/run.json"].decode("utf-8"))
    manifest = {
        "schema": EVIDENCE_SCHEMA,
        "run_id": run_id,
        "request": request,
        "source_sha256": run_manifest.get("source_sha256"),
        "binary_sha256": replay["binary_sha256"],
        "replay_status": replay["replay"].get("status"),
        "git": _git_commit(),
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(members.items())},
        "note": "SHA-256 of every other member of this package; README.txt has the reproduction commands.",
    }
    members["manifest.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    members["README.txt"] = scrub(readme(run_id, request, manifest)).encode("utf-8")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in ("README.txt", "manifest.json", "request.json", "replay.json") + tuple(f"run/{n}" for n in RUN_FILES):
            info = zipfile.ZipInfo(f"{run_id}/{name}", ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, members[name])
    return buffer.getvalue(), f"vv-m10-evidence-{run_id}.zip"
