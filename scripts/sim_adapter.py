"""Versioned simulator adapter contract and the ground-vehicle implementation.

The contract (`vv-sim-adapter.v1`) is deliberately small: model identity and
declared capabilities, a validated run request, bounded deterministic
execution, typed states and events with provenance, and replay verification.
It does not try to describe physics generically; each model declares what it
supports and rejects everything else.

`GroundVehicleAdapter` wraps the existing `vv-lab run-m4` / `replay-m4` CLI.
Missions are the three M6 suites; supported overrides are the seed, the
controller policy, one GPS dropout window and one actuator fault. Inputs are
copied into the run directory and modified there; source scenarios are never
written.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from adversarial_campaign import default_binary
from replay_workbench import case_integrity, replay_check, sha256_file, trace

ROOT = Path(__file__).resolve().parents[1]
ADAPTER_SCHEMA = "vv-sim-adapter.v1"
REQUEST_SCHEMA = "vv-sim-run-request.v1"
RESULT_SCHEMA = "vv-sim-run-result.v1"
MODEL_ID = "ground-vehicle-2d"
PHYSICS = "2D kinematic model with integer millimetre positions and fixed ticks; no dynamics, no environment model"
CONTROLLERS = ("dominant_axis", "x_first")
FAULT_KINDS = ("continued_movement", "delayed_movement", "lost_movement")
MAX_SEED = 2**63 - 1
MAX_STEPS = 200
RUN_TIMEOUT_SECONDS = 30
MAX_OUTPUT_BYTES = 16 * 1024 * 1024
# run-m4 exits 2 when the mission violates properties; that is a result, not an error.
OK_EXIT_CODES = (0, 2)
# Long enough for one run, its replay and a regeneration by the process holding the lock.
LOCK_TIMEOUT_SECONDS = 3 * RUN_TIMEOUT_SECONDS
RUN_ID = re.compile(r"[0-9a-f]{16}")


class AdapterError(ValueError):
    """The request is invalid or the simulator could not produce a result."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _int(value: Any, name: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise AdapterError(f"{name} must be an integer in [{low}, {high}]")
    return value


def _only(obj: Any, allowed: set[str], what: str) -> dict:
    if not isinstance(obj, dict):
        raise AdapterError(f"{what} must be an object")
    extra = sorted(set(obj) - allowed)
    if extra:
        raise AdapterError(f"unknown field in {what}: {extra[0]}")
    return obj


def _window(value: Any, steps: int, what: str) -> dict[str, int]:
    obj = _only(value, {"start_tick", "end_tick"}, what)
    start = _int(obj.get("start_tick"), f"{what}.start_tick", 0, steps)
    end = _int(obj.get("end_tick"), f"{what}.end_tick", 0, steps)
    if start > end:
        raise AdapterError(f"{what}.start_tick must not exceed end_tick")
    return {"start_tick": start, "end_tick": end}


def _lock_fd(fd: int) -> None:
    if sys.platform == "win32":
        import msvcrt

        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


@contextlib.contextmanager
def run_lock(output_root: Path, run_id: str, timeout: float) -> Iterator[None]:
    """Exclusive, cross-process lock for one run id. The OS drops it if the holder dies.

    Only for a local disk: on network shares flock and msvcrt.locking may not exclude other hosts.
    """
    locks = Path(output_root) / ".locks"
    locks.mkdir(parents=True, exist_ok=True)
    fd = os.open(locks / f"{run_id}.lock", os.O_RDWR | os.O_CREAT, 0o600)
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                _lock_fd(fd)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise AdapterError(f"run {run_id} is busy in another process; try again") from None
                time.sleep(0.05)
        yield
    finally:
        os.close(fd)  # closing the descriptor releases the lock on both platforms


def _publish(partial: Path, run_dir: Path) -> None:
    # Windows refuses a directory rename while a scanner or indexer briefly holds a file in it.
    for attempt in range(20):
        try:
            partial.rename(run_dir)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.1)


def _files(directory: Path) -> dict[str, str]:
    # A link is never what vv-lab writes; hashing its target could make a foreign file look regenerated.
    return {p.relative_to(directory).as_posix(): "symlink" if p.is_symlink() else sha256_file(p)
            for p in directory.rglob("*") if p.is_symlink() or p.is_file()}


def _regeneration_problems(stored: Path, regenerated: Path) -> list[str]:
    """Every byte of a stored run must equal a fresh run of the same request with the same binary."""
    have, want = _files(stored), _files(regenerated)
    problems = [f"{name} missing from the stored run" for name in sorted(set(want) - set(have))]
    problems += [f"{name} is not produced by this request" for name in sorted(set(have) - set(want))]
    problems += [f"{name} differs from the regenerated run" for name in sorted(set(have) & set(want))
                 if have[name] != want[name]]
    return problems


def _verdict(replay: dict, problems: list[str]) -> dict[str, Any]:
    reasons = list(problems)
    if replay.get("status") != "verified":
        reasons.insert(0, f"replay {replay.get('status')}")
    return {"status": "rejected" if reasons else "verified", "reasons": reasons}


RESULT_FIELDS = {"schema": str, "adapter": str, "run_id": str, "request": dict, "reused": bool, "model": dict,
                 "provenance": dict, "inputs": dict, "states": list, "replay": dict, "integrity": dict, "verdict": dict}


def check_result(result: Any) -> None:
    """Response contract of a successful run; raises AdapterError naming the first broken field."""
    if not isinstance(result, dict):
        raise AdapterError("result must be an object")
    for name, kind in RESULT_FIELDS.items():
        if not isinstance(result.get(name), kind):
            raise AdapterError(f"result.{name} missing or not {kind.__name__}")
    if result["schema"] != RESULT_SCHEMA or result["adapter"] != ADAPTER_SCHEMA:
        raise AdapterError("result schema or adapter version is wrong")
    if not RUN_ID.fullmatch(result["run_id"]):
        raise AdapterError("result.run_id is not 16 lowercase hex characters")
    problems = result["integrity"].get("problems")
    if not isinstance(problems, list) or not all(isinstance(p, str) for p in problems):
        raise AdapterError("result.integrity.problems must be a list of strings")
    verdict = result["verdict"]
    if verdict.get("status") not in ("verified", "rejected") or not isinstance(verdict.get("reasons"), list):
        raise AdapterError("result.verdict must be verified or rejected with reasons")
    if verdict != _verdict(result["replay"], problems):
        raise AdapterError("result.verdict does not follow from the replay and integrity results")


class GroundVehicleAdapter:
    def __init__(self, binary: Path | str | None = "default", root: Path = ROOT) -> None:
        self.binary = default_binary("vv-lab") if binary == "default" else (Path(binary) if binary else None)
        self.root = Path(root)
        self.lock_timeout = LOCK_TIMEOUT_SECONDS
        base = root / "scenarios" / "m6"
        experiment = json.loads((base / "experiment.json").read_text(encoding="utf-8"))
        self.missions: dict[str, dict] = {}
        for suite in experiment["suites"]:
            scenario_path = (base / suite["scenario"]).resolve()
            scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
            self.missions[suite["id"]] = {
                "id": suite["id"],
                "description": suite.get("description", ""),
                "scenario": scenario_path,
                "contracts": (base / suite["contracts"]).resolve(),
                "actuator": (base / suite["actuator"]).resolve() if suite.get("actuator") else None,
                "steps": scenario["steps"],
                "tick_ms": scenario.get("tick_ms", 100),
            }

    # ------------------------------------------------------------ contract

    def describe(self) -> dict[str, Any]:
        return {
            "schema": ADAPTER_SCHEMA,
            "model": {"id": MODEL_ID, "physics": PHYSICS, "dimensions": 2, "six_dof": False,
                      "units": {"position": "mm", "time": "tick"}},
            "capabilities": {
                "missions": [{k: m[k] for k in ("id", "description", "steps", "tick_ms")} for m in self.missions.values()],
                "controllers": list(CONTROLLERS),
                "sensors": ["gps", "communication"],
                "overrides": {
                    "seed": f"integer in [0, {MAX_SEED}]",
                    "controller": list(CONTROLLERS),
                    "gps_dropout": "null (keep mission), \"none\" (clear) or {start_tick, end_tick}",
                    "actuator_fault": "null (keep mission), \"none\" (clear) or "
                    "{kind, start_tick, end_tick, probability_permille, delay_ticks (delayed_movement only)}",
                },
                "actuator_fault_kinds": list(FAULT_KINDS),
                "requirements": "temporal contracts of the mission's contract set plus safety invariants",
                "deterministic": True,
                "replay": True,
                "limits": {"max_steps": MAX_STEPS, "timeout_seconds": RUN_TIMEOUT_SECONDS,
                           "max_output_bytes": MAX_OUTPUT_BYTES},
            },
        }

    def validate(self, request: Any) -> dict[str, Any]:
        req = _only(request, {"schema", "model", "mission", "seed", "controller", "overrides"}, "request")
        if req.get("schema") != REQUEST_SCHEMA:
            raise AdapterError(f"schema must be {REQUEST_SCHEMA}")
        if req.get("model") != MODEL_ID:
            raise AdapterError(f"model must be {MODEL_ID}")
        mission = self.missions.get(req.get("mission")) if isinstance(req.get("mission"), str) else None
        if mission is None:
            raise AdapterError(f"mission must be one of {sorted(self.missions)}")
        if mission["steps"] > MAX_STEPS:
            raise AdapterError(f"mission exceeds the {MAX_STEPS}-tick bound")
        seed = _int(req.get("seed"), "seed", 0, MAX_SEED)
        if req.get("controller") not in CONTROLLERS:
            raise AdapterError(f"controller must be one of {list(CONTROLLERS)}")
        overrides = req.get("overrides", {})
        if not isinstance(overrides, dict):
            raise AdapterError("overrides must be an object")
        extra = sorted(set(overrides) - {"gps_dropout", "actuator_fault"})
        if extra:
            raise AdapterError(f"unknown override: {extra[0]}")
        gps = overrides.get("gps_dropout")
        steps = mission["steps"]
        return {
            "schema": REQUEST_SCHEMA,
            "model": MODEL_ID,
            "mission": mission["id"],
            "seed": seed,
            "controller": req["controller"],
            "overrides": {
                "gps_dropout": gps if gps in (None, "none") else _window(gps, steps, "gps_dropout"),
                "actuator_fault": self._fault(overrides.get("actuator_fault"), steps),
            },
        }

    @staticmethod
    def _fault(value: Any, steps: int) -> Any:
        if value is None or value == "none":
            return value
        obj = _only(value, {"kind", "start_tick", "end_tick", "probability_permille", "delay_ticks"}, "actuator_fault")
        if obj.get("kind") not in FAULT_KINDS:
            raise AdapterError(f"actuator_fault.kind must be one of {list(FAULT_KINDS)}")
        window = _window({k: obj.get(k) for k in ("start_tick", "end_tick")}, steps, "actuator_fault")
        fault = {"kind": obj["kind"], **window,
                 "probability_permille": _int(obj.get("probability_permille"), "actuator_fault.probability_permille", 0, 1000)}
        if obj["kind"] == "delayed_movement":
            fault["delay_ticks"] = _int(obj.get("delay_ticks"), "actuator_fault.delay_ticks", 1, steps)
        elif "delay_ticks" in obj:
            raise AdapterError("actuator_fault.delay_ticks applies only to delayed_movement")
        return fault

    # ------------------------------------------------------------ execution

    def _inputs(self, req: dict) -> tuple[dict, dict, bytes]:
        mission = self.missions[req["mission"]]
        scenario = json.loads(mission["scenario"].read_text(encoding="utf-8"))
        actuator = (json.loads(mission["actuator"].read_text(encoding="utf-8")) if mission["actuator"]
                    else {"schema_version": 1, "seed": 42, "faults": []})
        gps = req["overrides"]["gps_dropout"]
        if gps == "none":
            scenario["sensors"]["gps"]["dropout_windows"] = []
        elif gps:
            scenario["sensors"]["gps"]["dropout_windows"] = [gps]
        fault = req["overrides"]["actuator_fault"]
        if fault == "none":
            actuator["faults"] = []
        elif fault:
            spec = {"kind": fault["kind"], "id": "mission_control_override",
                    "windows": [{"start_tick": fault["start_tick"], "end_tick": fault["end_tick"]}],
                    "probability_permille": fault["probability_permille"]}
            if "delay_ticks" in fault:
                spec["delay_ticks"] = fault["delay_ticks"]
            actuator["faults"] = [spec]
        return scenario, actuator, mission["contracts"].read_bytes()

    def run_id(self, req: dict, binary_sha: str | None = None) -> str:
        """Identity of a validated request on this binary."""
        if binary_sha is None:
            binary_sha = self._binary_sha()
        return hashlib.sha256(_canonical(req) + binary_sha.encode()).hexdigest()[:16]

    def _binary_sha(self) -> str:
        if self.binary is None or not self.binary.is_file():
            raise AdapterError("vv-lab binary not found; build it with cargo build --release")
        return sha256_file(self.binary)

    def run(self, request: Any, output_root: Path, reuse: bool = False) -> dict[str, Any]:
        """Execute a validated request and publish it under its run id.

        Callers in this or other processes serialise on a per-run lock. Each execution
        writes to its own scratch directory. The first is renamed into place; with `reuse`,
        later ones are a regeneration that the stored run must match byte for byte.
        """
        req = self.validate(request)
        binary_sha = self._binary_sha()
        run_id = self.run_id(req, binary_sha)
        root = Path(output_root)
        run_dir = root / run_id
        with run_lock(root, run_id, self.lock_timeout):
            # With the lock held, no live process owns a scratch directory for this id.
            for stale in root.glob(f".partial-{run_id}-*"):
                shutil.rmtree(stale, ignore_errors=True)
            if run_dir.exists() and not reuse:
                raise AdapterError(f"run directory already exists: {run_id}")
            partial = root / f".partial-{run_id}-{os.getpid()}-{secrets.token_hex(4)}"
            try:
                done = self._execute(req, partial)
                reused = run_dir.exists()
                problems = _regeneration_problems(run_dir, partial) if reused else []
                if not reused:
                    _publish(partial, run_dir)
            finally:
                shutil.rmtree(partial, ignore_errors=True)
            result = self.verify(run_dir)
        result["integrity"]["problems"].extend(problems)
        inputs = run_dir / "inputs"
        result.update(
            run_id=run_id,
            request=req,
            reused=reused,
            simulator_exit_code=done.returncode,
            inputs={n: sha256_file(inputs / n) for n in ("scenario.json", "actuator.json", "contracts.json", "request.json")
                    if (inputs / n).is_file()},
            verdict=_verdict(result["replay"], result["integrity"]["problems"]),
        )
        result["provenance"]["binary_sha256"] = binary_sha
        return result

    def _execute(self, req: dict, out: Path) -> subprocess.CompletedProcess:
        (out / "inputs").mkdir(parents=True)
        scenario, actuator, contracts = self._inputs(req)
        (out / "inputs" / "request.json").write_bytes(_canonical(req))
        (out / "inputs" / "scenario.json").write_bytes(_canonical(scenario))
        (out / "inputs" / "actuator.json").write_bytes(_canonical(actuator))
        (out / "inputs" / "contracts.json").write_bytes(contracts)
        command = [str(self.binary), "run-m4", str(out / "inputs" / "scenario.json"), "--seed", str(req["seed"]),
                   "--controller", req["controller"], "--contracts", str(out / "inputs" / "contracts.json"),
                   "--actuator", str(out / "inputs" / "actuator.json"), "--output", str(out),
                   "--max-output-bytes", str(MAX_OUTPUT_BYTES)]
        try:
            done = subprocess.run(command, capture_output=True, text=True, timeout=RUN_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as error:
            raise AdapterError(f"simulation exceeded {RUN_TIMEOUT_SECONDS} s") from error
        except OSError as error:
            raise AdapterError(f"could not start vv-lab: {error}") from error
        if done.returncode not in OK_EXIT_CODES or not (out / "m4.json").is_file():
            raise AdapterError(f"vv-lab run-m4 failed (exit {done.returncode}): {done.stderr.strip()[-400:]}")
        return done

    def verify(self, run_dir: Path) -> dict[str, Any]:
        """Typed view of a stored run, with integrity checks and a replay by this adapter's build."""
        run_dir = Path(run_dir)
        m4 = run_dir / "m4.json"
        manifest = json.loads(m4.read_text(encoding="utf-8")) if m4.is_file() else {}
        source = manifest.get("source_sha256", "")
        problems, manifest = case_integrity(run_dir, {"m4_sha256": sha256_file(m4) if m4.is_file() else None}, source)
        replay = replay_check(self.binary, m4) if m4.is_file() else {"status": "not_run", "detail": "m4.json missing"}
        view = trace(run_dir) or {}
        artifacts = {}
        for key in ("event_artifact", "report_artifact", "mission_artifact", "verification_artifact"):
            entry = (manifest or {}).get(key) or {}
            if entry.get("path"):
                artifacts[entry["path"]] = entry.get("sha256")
        return {
            "schema": RESULT_SCHEMA,
            "adapter": ADAPTER_SCHEMA,
            "model": {"id": MODEL_ID, "dimensions": 2, "physics": PHYSICS},
            "run_dir": str(run_dir),
            "provenance": {
                "source_sha256": source,
                "manifest_sha256": (manifest or {}).get("manifest_sha256"),
                "controller_id": (manifest or {}).get("controller_id"),
                "artifacts": artifacts,
            },
            "integrity": {"problems": problems},
            "replay": replay,
            "geometry": view.get("geometry"),
            "tick_ms": view.get("tick_ms"),
            "states": view.get("ticks", []),
            "transitions": view.get("transitions", []),
            "contracts": view.get("contracts", []),
            "invariant_failures": view.get("invariant_failures", []),
            "actuator_events": view.get("actuator_events", []),
            "actuator_faults": view.get("actuator_faults", []),
            "mission": view.get("mission"),
            "summary": view.get("summary"),
        }
