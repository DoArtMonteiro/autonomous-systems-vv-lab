"""Adapter `vv-sim-adapter.v2` for the `rocket-rigid-body` model (M8).

Wraps the `vv-rocket` CLI (crates/vv-rocket): `run` integrates a stored case, `replay`
recomputes it and compares the trace byte for byte, and `verify` runs the reference
cases with their pre-registered tolerances. Missions are the three demo cases in
crates/vv-rocket/cases; each accepts a small set of validated parameter overrides.
Publication, locking and byte-for-byte reuse are the same as for the ground vehicle.

Three things are reported separately and never merged: the integrity and replay
verdict of the stored run, the physics reference verification of the build, and the
model's validity (idealized, not validated against flight data).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import secrets
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from replay_workbench import sha256_file
from sim_adapter import (
    ADAPTER_SCHEMA_V2,
    REQUEST_SCHEMA_V2,
    RESULT_SCHEMA_V2,
    AdapterError,
    _canonical,
    _files,
    _only,
    _publish,
    _regeneration_problems,
    _verdict,
    run_lock,
)

ROOT = Path(__file__).resolve().parents[1]
CRATE = ROOT / "crates" / "vv-rocket"
MODEL_ID = "rocket-rigid-body"
PHYSICS = ("6-DOF rigid body with variable mass: 3D position and velocity, attitude quaternion, angular velocity, "
           "propellant mass; idealized thrust with specific impulse, uniform gravity, exponential atmosphere drag at "
           "the centre of mass; fixed-step RK4")
MODEL_VALIDITY = ("Idealized model; not validated against flight data. "
                  "No aerodynamic moments, wind, Earth rotation, actuator dynamics or contact model: "
                  "a ground crossing is not a landing.")
RUN_TIMEOUT_SECONDS = 30
LOCK_TIMEOUT_SECONDS = 4 * RUN_TIMEOUT_SECONDS
OUTPUT_FILES = ("case.json", "trace.json", "run.json", "verification.json")
EXPECTED_FILES = frozenset(OUTPUT_FILES) | {"inputs/request.json", "inputs/case.json"}

# Each override: (description, low, high, step or None). Values outside are refused.
MISSIONS: dict[str, dict[str, Any]] = {
    "ballistic": {
        "case": "ballistic.json",
        "description": "Unpowered 50 kg body launched at 200 m/s, 53° elevation, through an exponential atmosphere until "
                       "its centre of mass crosses 0 m.",
        "overrides": {
            "launch_speed_mps": ("launch speed along the initial direction", 10.0, 600.0, None),
            "drag_coefficient": ("drag coefficient (0 gives vacuum flight)", 0.0, 2.0, None),
        },
    },
    "propulsive_descent": {
        "case": "propulsive_descent.json",
        "description": "Open-loop retro burn of a 30 t stage falling from 3000 m at 200 m/s; the burn runs until 32 s "
                       "or until the centre of mass crosses 0 m. There is no controller and no contact model.",
        "overrides": {
            "ignition_time_s": ("ignition time, a multiple of 0.01 s", 0.0, 20.0, 0.01),
            "throttle": ("throttle of the retro burn", 0.1, 1.0, None),
        },
    },
    "attitude_dynamics": {
        "case": "attitude_dynamics.json",
        "description": "Spinning stage in free flight (no gravity, no atmosphere) with a 4 s gimballed burn that applies "
                       "a transverse torque; shows gyroscopic coupling, nutation and propellant use.",
        "overrides": {
            "roll_rate_radps": ("initial roll rate about the body axis", -5.0, 5.0, None),
            "gimbal_lateral": ("lateral component of the thrust direction (z_B)", -0.2, 0.2, None),
        },
    },
}


def default_rocket_binary() -> Path:
    return CRATE / "target" / "release" / ("vv-rocket.exe" if os.name == "nt" else "vv-rocket")


def _number(value: Any, name: str, low: float, high: float, step: float | None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise AdapterError(f"{name} must be a number")
    value = float(value)
    if not low <= value <= high:
        raise AdapterError(f"{name} must be in [{low}, {high}]")
    if step is not None and abs(value / step - round(value / step)) > 1e-9:
        raise AdapterError(f"{name} must be a multiple of {step}")
    value = round(value / step) * step if step is not None else value
    return value + 0.0  # -0.0 and 0.0 are the same parameter and must have the same run id


def _summarize_reference(report: dict) -> dict[str, Any]:
    """What the UI may say about physics verification, derived from the report, never a bare PASS.

    Only active criteria decide a case. A superseded or invalid criterion is listed as history and
    is never counted as a pass.
    """
    cases = report.get("cases", [])

    def entry(c: dict, m: dict) -> dict[str, Any]:
        return {"case": c["id"], "metric": m["name"], "status": m.get("status"), "value": m["value"],
                "tolerance": m["tolerance"], "unit": m["unit"], "superseded_by": m.get("superseded_by"),
                "note": m.get("note"), "diagnosis": c.get("diagnosis")}

    metrics = [(c, m) for c in cases for m in c.get("metrics", [])]
    failed = [entry(c, m) for c, m in metrics if m.get("status") == "fail" and not m.get("superseded_by")]
    history = [entry(c, m) for c, m in metrics if m.get("status") == "invalid" or m.get("superseded_by")]
    counts = {s: sum(1 for c in cases if c.get("status") == s) for s in ("PASS", "FAIL", "INVALID")}
    text = (f"{counts['PASS']} of {len(cases)} reference cases PASS their active pre-registered criteria, "
            f"{counts['FAIL']} FAIL, {counts['INVALID']} INVALID")
    if failed:
        text += "; failing: " + "; ".join(f"{f['case']}: '{f['metric']}' is {f['value']:.3e}, limit {f['tolerance']:g}"
                                         for f in failed)
    if history:
        revised = sorted({h["case"] for h in history})
        text += (f"; {len(revised)} cases use criteria revised after the first run ({', '.join(revised)}; the case 4 "
                 "revision is not blind, see Research)")
        text += (f"; {len(history)} first-run criteria kept as history (not counted as passes): "
                 + "; ".join(f"{h['case']}: '{h['metric']}' {h['status']}"
                             + (f", superseded by '{h['superseded_by']}'" if h["superseded_by"] else "") for h in history))
    return {"all_pass": bool(report.get("all_pass")), "cases_total": len(cases), "cases_passed": counts["PASS"],
            "cases_failed": counts["FAIL"], "cases_invalid": counts["INVALID"], "failed_criteria": failed,
            "criteria_history": history, "gaps": report.get("gaps", []), "summary": text,
            "cases": [{"id": c["id"], "title": c["title"], "status": c.get("status"), "pass": c["pass"]} for c in cases]}


class RocketAdapter:
    def __init__(self, binary: Path | str | None = "default", root: Path = ROOT) -> None:
        self.binary = default_rocket_binary() if binary == "default" else (Path(binary) if binary else None)
        self.root = Path(root)
        self.lock_timeout = LOCK_TIMEOUT_SECONDS
        self.cases = {m: json.loads((CRATE / "cases" / spec["case"]).read_text(encoding="utf-8"))
                      for m, spec in MISSIONS.items()}

    # ------------------------------------------------------------ contract

    def defaults(self, mission: str) -> dict[str, float]:
        c = self.cases[mission]
        if mission == "ballistic":
            return {"launch_speed_mps": math.sqrt(sum(v * v for v in c["initial"]["velocity_mps"])),
                    "drag_coefficient": c["vehicle"]["drag_coefficient"]}
        if mission == "propulsive_descent":
            return {"ignition_time_s": c["burns"][0]["start_s"], "throttle": c["burns"][0]["throttle"]}
        return {"roll_rate_radps": c["initial"]["angular_velocity_radps"][0],
                "gimbal_lateral": c["burns"][0]["direction_body"][2]}

    def describe(self) -> dict[str, Any]:
        return {
            "schema": ADAPTER_SCHEMA_V2,
            "model": {"id": MODEL_ID, "physics": PHYSICS, "dimensions": 3, "six_dof": True,
                      "frames": {"inertial": "local flat non-rotating ENU, z up, origin on the ground",
                                 "body": "x_B along the axis from the nozzle to the nose; origin at the centre of mass",
                                 "attitude": "unit quaternion (w, x, y, z), Hamilton, body to inertial"},
                      "units": {"length": "m", "time": "s", "mass": "kg", "force": "N", "angle": "rad"},
                      "validity": MODEL_VALIDITY},
            "capabilities": {
                "missions": [{"id": m, "description": spec["description"], "defaults": self.defaults(m),
                              "overrides": {k: {"description": d, "min": lo, "max": hi, "step": st}
                                            for k, (d, lo, hi, st) in spec["overrides"].items()}}
                             for m, spec in MISSIONS.items()],
                "deterministic": True,
                "replay": True,
                "physics_reference": "vv-rocket verify: reference cases with pre-registered tolerances",
                "limits": {"timeout_seconds": RUN_TIMEOUT_SECONDS},
            },
        }

    def validate(self, request: Any) -> dict[str, Any]:
        req = _only(request, {"schema", "model", "mission", "overrides"}, "request")
        if req.get("schema") != REQUEST_SCHEMA_V2:
            raise AdapterError(f"schema must be {REQUEST_SCHEMA_V2}")
        if req.get("model") != MODEL_ID:
            raise AdapterError(f"model must be {MODEL_ID}")
        mission = req.get("mission")
        if not isinstance(mission, str) or mission not in MISSIONS:
            raise AdapterError(f"mission must be one of {sorted(MISSIONS)}")
        spec = MISSIONS[mission]["overrides"]
        given = _only(req.get("overrides", {}), set(spec), "overrides")
        values = self.defaults(mission)
        for key, (_, lo, hi, step) in spec.items():
            if key in given:
                values[key] = _number(given[key], f"overrides.{key}", lo, hi, step)
        return {"schema": REQUEST_SCHEMA_V2, "model": MODEL_ID, "mission": mission, "overrides": values}

    def case_for(self, req: dict) -> dict:
        case = json.loads(json.dumps(self.cases[req["mission"]]))
        o = req["overrides"]
        if req["mission"] == "ballistic":
            v = case["initial"]["velocity_mps"]
            scale = o["launch_speed_mps"] / math.sqrt(sum(x * x for x in v))
            case["initial"]["velocity_mps"] = [x * scale for x in v]
            case["vehicle"]["drag_coefficient"] = o["drag_coefficient"]
        elif req["mission"] == "propulsive_descent":
            case["burns"][0]["start_s"] = o["ignition_time_s"]
            case["burns"][0]["throttle"] = o["throttle"]
        else:
            case["initial"]["angular_velocity_radps"][0] = o["roll_rate_radps"]
            case["burns"][0]["direction_body"][2] = o["gimbal_lateral"]
        return case

    def _binary_sha(self) -> str:
        if self.binary is None or not self.binary.is_file():
            raise AdapterError("vv-rocket binary not found; build it with "
                               "cargo build --release --manifest-path crates/vv-rocket/Cargo.toml")
        return sha256_file(self.binary)

    def run_id(self, req: dict, binary_sha: str | None = None) -> str:
        if binary_sha is None:
            binary_sha = self._binary_sha()
        # The case template on disk also determines the output, so it is part of the identity.
        return hashlib.sha256(_canonical(req) + _canonical(self.case_for(req)) + binary_sha.encode()).hexdigest()[:16]

    # ------------------------------------------------------------ execution

    def _call(self, *args: str) -> subprocess.CompletedProcess:
        try:
            return subprocess.run([str(self.binary), *args], capture_output=True, text=True,
                                  timeout=RUN_TIMEOUT_SECONDS, encoding="utf-8")
        except subprocess.TimeoutExpired as error:
            raise AdapterError(f"vv-rocket exceeded {RUN_TIMEOUT_SECONDS} s") from error
        except OSError as error:
            raise AdapterError(f"could not start vv-rocket: {error}") from error

    def _execute(self, req: dict, out: Path) -> None:
        (out / "inputs").mkdir(parents=True)
        (out / "inputs" / "request.json").write_bytes(_canonical(req))
        (out / "inputs" / "case.json").write_bytes(_canonical(self.case_for(req)))
        done = self._call("run", str(out / "inputs" / "case.json"), "--output", str(out))
        if done.returncode != 0:
            raise AdapterError(f"vv-rocket run refused the case: {done.stderr.strip()[-400:]}")
        # Exit 1 means a reference criterion is not met: still a report, read from its content.
        done = self._call("verify", "--output", str(out / "verification.json"))
        if done.returncode not in (0, 1) or not (out / "verification.json").is_file():
            raise AdapterError(f"vv-rocket verify failed (exit {done.returncode}): {done.stderr.strip()[-400:]}")

    def run(self, request: Any, output_root: Path, reuse: bool = False) -> dict[str, Any]:
        """Same publication protocol as GroundVehicleAdapter.run."""
        req = self.validate(request)
        binary_sha = self._binary_sha()
        run_id = self.run_id(req, binary_sha)
        root = Path(output_root)
        run_dir = root / run_id
        with run_lock(root, run_id, self.lock_timeout):
            for stale in root.glob(f".partial-{run_id}-*"):
                shutil.rmtree(stale, ignore_errors=True)
            if run_dir.exists() and not reuse:
                raise AdapterError(f"run directory already exists: {run_id}")
            partial = root / f".partial-{run_id}-{os.getpid()}-{secrets.token_hex(4)}"
            try:
                self._execute(req, partial)
                reused = run_dir.exists()
                problems = _regeneration_problems(run_dir, partial) if reused else []
                if not reused:
                    _publish(partial, run_dir)
            finally:
                shutil.rmtree(partial, ignore_errors=True)
            result = self.verify(run_dir)
        result["integrity"]["problems"].extend(problems)
        result.update(run_id=run_id, request=req, reused=reused,
                      verdict=_verdict(result["replay"], result["integrity"]["problems"]))
        result["provenance"]["binary_sha256"] = binary_sha
        return result

    def verify(self, run_dir: Path) -> dict[str, Any]:
        """Typed view of a stored run: replay by this build, physics reference report, trace."""
        run_dir = Path(run_dir)
        problems: list[str] = []
        done = self._call("replay", str(run_dir))
        try:
            replay_report = json.loads(done.stdout) if done.returncode in (0, 1) else None
        except json.JSONDecodeError:
            replay_report = None
        if replay_report is None:
            replay = {"status": "error", "detail": done.stderr.strip()[-400:]}
        else:
            replay = {"status": replay_report["status"], "checks": replay_report["checks"]}

        def load(name: str) -> Any:
            path = run_dir / name
            if path.is_symlink() or not path.is_file():
                problems.append(f"{name} missing")
                return None
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                problems.append(f"{name} is not valid JSON")
                return None

        trace, manifest = load("trace.json"), load("run.json")
        problems.extend(self._input_binding_problems(run_dir))
        extra = sorted(set(_files(run_dir)) - EXPECTED_FILES)
        problems.extend(f"{name} is not produced by this adapter" for name in extra)
        binary_sha = self._binary_sha()
        problems.extend(self._identity_problems(run_dir, binary_sha))
        # The physics reference shown is always recomputed by this build, never read from the stored run.
        fresh = self._fresh_reference()
        report = json.loads(fresh.decode("utf-8"))
        stored = run_dir / "verification.json"
        if stored.is_symlink() or not stored.is_file():
            problems.append("verification.json missing")
        elif stored.read_bytes() != fresh:
            problems.append("verification.json differs from a fresh vv-rocket verify")
        files = {n: sha256_file(run_dir / n) for n in OUTPUT_FILES if (run_dir / n).is_file()}
        inputs = {n: sha256_file(run_dir / "inputs" / n) for n in ("request.json", "case.json")
                  if (run_dir / "inputs" / n).is_file()}
        return {
            "schema": RESULT_SCHEMA_V2,
            "adapter": ADAPTER_SCHEMA_V2,
            "model": {"id": MODEL_ID, "dimensions": 3, "six_dof": True, "physics": PHYSICS},
            "run_dir": str(run_dir),
            "provenance": {"source_sha256": (manifest or {}).get("source_sha256"), "binary_sha256": binary_sha,
                           "manifest_sha256": files.get("run.json"), "artifacts": files},
            "inputs": inputs,
            "integrity": {"problems": problems},
            "replay": replay,
            "states": (trace or {}).get("samples", []),
            "events": (trace or {}).get("events", []),
            "summary": (trace or {}).get("summary", {}),
            "physics_reference": _summarize_reference(report),
            "model_validity": MODEL_VALIDITY,
            "verdict": _verdict(replay, problems),
        }

    def _fresh_reference(self) -> bytes:
        """Bytes of `vv-rocket verify --output` from this build; exit 1 (a criterion not met) is still a report."""
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "verification.json"
            done = self._call("verify", "--output", str(out))
            if done.returncode not in (0, 1) or not out.is_file():
                raise AdapterError(f"vv-rocket verify failed (exit {done.returncode}): {done.stderr.strip()[-400:]}")
            return out.read_bytes()

    def _identity_problems(self, run_dir: Path, binary_sha: str) -> list[str]:
        """The directory name is the run id of the stored request, its case and this binary.

        This binds the stored files to the model, request, defaults and binary: a run copied under
        another id, made by another binary or by another model's adapter is rejected.
        """
        try:
            req = self.validate(json.loads((run_dir / "inputs" / "request.json").read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return []  # reported by _input_binding_problems
        expected = self.run_id(req, binary_sha)
        if run_dir.name != expected:
            return [f"run directory {run_dir.name} is not the run id {expected} of its request on this vv-rocket binary"]
        return []

    def _input_binding_problems(self, run_dir: Path) -> list[str]:
        """The stored request must validate and produce exactly the stored input case, which `vv-rocket run` copied."""
        inputs = run_dir / "inputs"
        try:
            req = self.validate(json.loads((inputs / "request.json").read_text(encoding="utf-8")))
            case = (inputs / "case.json").read_bytes()
            copied = (run_dir / "case.json").read_bytes()
        except (OSError, ValueError) as error:  # AdapterError and JSONDecodeError are ValueErrors
            return [f"inputs cannot be checked: {error}"]
        problems = []
        if _canonical(req) != (inputs / "request.json").read_bytes():
            problems.append("inputs/request.json is not the canonical validated request")
        if case != _canonical(self.case_for(req)):
            problems.append("inputs/case.json is not the case this request produces")
        if copied != case:
            problems.append("case.json differs from inputs/case.json")
        return problems
