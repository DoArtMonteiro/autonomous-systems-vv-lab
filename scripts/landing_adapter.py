"""Adapter `vv-sim-adapter.v3` for the `rocket-landing` model (M9 closed-loop powered landing).

Wraps `vv-rocket land` / `replay` (crates/vv-rocket). A request names a controller policy,
a seed and at most one fault; the adapter validates them against the pre-registered ranges
(docs/m9-powered-landing.md), builds the landing case from the nominal template and runs it.

Contract v3 exists because the request has categorical inputs (policy, fault kind) that the
numeric overrides of v2 cannot express. v1 and v2, their models and their results are unchanged.

Three statements stay apart and are never merged: the mission outcome (requirements R1 to R6 at
contact), the flight-safety invariants S1 to S5, and the evidence verdict (integrity and replay).
`vv-rocket land` exits 2 when a requirement or invariant fails; that is a result, not an error.
Publication, locking, run-id binding and tamper checks are those of the rocket adapter, which
this class reuses; the verification of a run is per run, so `replay` recomputes it byte for byte.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from replay_workbench import sha256_file
from rocket_adapter import (
    CRATE,
    EXPECTED_FILES,
    LOCK_TIMEOUT_SECONDS,
    OUTPUT_FILES,
    RUN_TIMEOUT_SECONDS,
    RocketAdapter,
    _number,
    default_rocket_binary,
)
from sim_adapter import (
    ADAPTER_SCHEMA_V3,
    REQUEST_SCHEMA_V3,
    RESULT_SCHEMA_V3,
    AdapterError,
    _canonical,
    _files,
    _int,
    _only,
    _verdict,
)

ROOT = Path(__file__).resolve().parents[1]
MODEL_ID = "rocket-landing"
TEMPLATE = CRATE / "landing" / "nominal.json"
# The case model of the M9.1 policies (adds the two optional ascent-abort gains at their defaults); the
# baseline and robust cases keep the frozen M9 template byte for byte.
TEMPLATE_M91 = CRATE / "landing" / "m91-nominal.json"
M91_POLICIES = frozenset({"guarded", "baseline_guarded"})
PHYSICS = ("closed-loop powered landing of a 22 t rocket stage: the 6-DOF rigid body of the rocket-rigid-body model, "
           "a throttle and thrust-vector actuator, noisy radar altimeter, GNSS and IMU, and a deterministic controller "
           "that sees only the observations; fixed step 0.01 s, control at 50 Hz")
MODEL_VALIDITY = ("Idealized demonstrator; not flight software and not validated against flight data. "
                  "No contact dynamics: touchdown is the instant the nozzle exit plane reaches the ground. "
                  "Requirements, dispersions and sensor noise are assumed values, not those of a real vehicle.")
DT_S = 0.01
DURATION_S = 40.0
MAX_SEED = 2**32 - 1  # one run per seed; the campaign uses 1000 to 1029

POLICIES = {
    "baseline": "Uses the latest reading of each sensor and trusts the radar altimeter for height.",
    "robust": "Runs its own navigation filter and rejects an altimeter that disagrees with the GNSS and inertial estimate.",
    "guarded": "The robust estimator plus two rules: when altimeter and estimate disagree it guides on the lower altitude "
               "and reports sensor_disagreement, and it cuts the engine when it climbs under power (ascent_abort).",
    "baseline_guarded": "The baseline policy unchanged plus the ascent-abort rule only (M9.1 test of that rule).",
}

# Pre-registered magnitude and window-length ranges (docs/m9-powered-landing.md, Falhas e gamas pré-registadas)
# and the demonstration values of crates/vv-rocket/landing/*.json. The Rust library enforces the same ranges.
# kind: (label, description, magnitude (low, high, unit) or None, window length (low, high) in s or None,
#        default magnitude, default start_s, default end_s)
FAULTS: dict[str, tuple[str, str, tuple[float, float, str] | None, tuple[float, float] | None, float, float, float]] = {
    "thrust_loss": (
        "Thrust loss", "The engine delivers less thrust than commanded: real thrust is multiplied by 1 minus the magnitude.",
        (0.05, 0.30, "fraction"), None, 0.15, 5.26, 40.0),
    "ignition_delay": (
        "Ignition delay", "The engine lights later than commanded. The window must be open when the controller commands "
        "ignition (about 4.2 s).", (0.1, 1.0, "s"), None, 0.5, 3.0, 8.0),
    "gimbal_stuck": (
        "Stuck gimbal", "The thrust-vector nozzle freezes at the deflection it had when the window starts (zero before "
        "ignition). There is no other attitude actuator.", None, (0.5, 3.0), 0.0, 10.0, 12.0),
    "altimeter_bias": (
        "Altimeter bias", "The radar altimeter reads too high by the magnitude.", (5.0, 50.0, "m"), None, 20.0, 10.0, 40.0),
    "altimeter_dropout": (
        "Altimeter dropout", "The radar altimeter delivers no measurement during the window.", None, (2.0, 10.0), 0.0, 18.0, 24.0),
    "gnss_dropout": (
        "GNSS dropout", "The GNSS delivers no position or velocity during the window.", None, (2.0, 10.0), 0.0, 8.0, 14.0),
    "gnss_bias": (
        "GNSS bias", "The GNSS position is shifted by the magnitude along x and z.", (5.0, 30.0, "m"), None, 15.0, 8.0, 40.0),
    "imu_accel_bias": (
        "IMU acceleration bias", "The IMU adds the magnitude to the specific force along the body axis x_B.",
        (0.05, 0.5, "m/s²"), None, 0.25, 5.0, 40.0),
    "altimeter_bias_low": (
        "Altimeter bias, low reading", "The radar altimeter reads too low by the magnitude (M9.1).",
        (5.0, 50.0, "m"), None, 27.5, 10.0, 40.0),
    "gnss_bias_low": (
        "GNSS bias, low reading", "The GNSS position is shifted down by the magnitude along x and z (M9.1).",
        (5.0, 30.0, "m"), None, 17.5, 8.0, 40.0),
}

LABELS = {
    "R1_vertical_speed": "Vertical speed at contact", "R2_horizontal_speed": "Horizontal speed at contact",
    "R3_tilt": "Tilt at contact", "R4_angular_rate": "Angular rate at contact", "R5_position": "Distance from pad centre",
    "R6_propellant_margin": "Propellant margin", "S1_tilt_envelope": "Tilt envelope while thrusting",
    "S2_keep_out": "Keep-out radius at contact", "S3_axial_load": "Axial load", "S4_no_relight": "No relight",
    "S5_no_powered_ascent": "Climb under power",
}


def _seconds(value: Any, name: str) -> int:
    """A time that is a multiple of the 0.01 s step, as whole steps."""
    value = _number(value, name, 0.0, DURATION_S, None)
    steps = round(value / DT_S)
    if abs(value / DT_S - steps) > 1e-9:
        raise AdapterError(f"{name} must be a multiple of {DT_S} s")
    return steps


class LandingAdapter(RocketAdapter):
    """Reuses the rocket adapter's run publication, identity binding and input binding checks."""

    def __init__(self, binary: Path | str | None = "default", root: Path = ROOT) -> None:
        self.binary = default_rocket_binary() if binary == "default" else (Path(binary) if binary else None)
        self.root = Path(root)
        self.lock_timeout = LOCK_TIMEOUT_SECONDS
        self.template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
        self.template_m91 = json.loads(TEMPLATE_M91.read_text(encoding="utf-8"))

    # ------------------------------------------------------------ contract

    def describe(self) -> dict[str, Any]:
        t = self.template
        return {
            "schema": ADAPTER_SCHEMA_V3,
            "model": {"id": MODEL_ID, "physics": PHYSICS, "dimensions": 3, "six_dof": True,
                      "frames": {"inertial": "local flat non-rotating ENU, z up, origin at the pad centre on the ground",
                                 "body": "x_B along the axis from the nozzle to the nose",
                                 "contact point": "centre of the nozzle exit plane"},
                      "units": {"length": "m", "time": "s", "mass": "kg", "force": "N", "angle": "rad"},
                      "validity": MODEL_VALIDITY},
            "capabilities": {
                "policies": [{"id": p, "description": d} for p, d in POLICIES.items()],
                "faults": [{"kind": k, "label": label, "description": text,
                            "magnitude": None if mag is None else {"min": mag[0], "max": mag[1], "unit": mag[2], "default": dm},
                            "window_length_s": None if win is None else {"min": win[0], "max": win[1]},
                            "default_start_s": start, "default_end_s": end}
                           for k, (label, text, mag, win, dm, start, end) in FAULTS.items()],
                "seed": {"min": 0, "max": MAX_SEED,
                         "note": "0 is the nominal case without dispersions; sensor noise stays on. Other seeds also disperse "
                                 "the initial state, propellant, thrust and Isp."},
                "time": {"step_s": DT_S, "duration_s": DURATION_S},
                "labels": LABELS,
                "requirements": {"pad_radius_m": t["requirements"]["r5_position_m"],
                                 "keep_out_radius_m": t["requirements"]["s2_keep_out_m"],
                                 "r1_vertical_speed_mps": t["requirements"]["r1_vertical_speed_mps"],
                                 "note": "Assumed demonstrator requirements, not specifications of a real vehicle."},
                "deterministic": True,
                "replay": True,
                "limits": {"timeout_seconds": RUN_TIMEOUT_SECONDS},
            },
        }

    def validate(self, request: Any) -> dict[str, Any]:
        req = _only(request, {"schema", "model", "policy", "seed", "fault"}, "request")
        if req.get("schema") != REQUEST_SCHEMA_V3:
            raise AdapterError(f"schema must be {REQUEST_SCHEMA_V3}")
        if req.get("model") != MODEL_ID:
            raise AdapterError(f"model must be {MODEL_ID}")
        if req.get("policy") not in POLICIES:
            raise AdapterError(f"policy must be one of {sorted(POLICIES)}")
        return {"schema": REQUEST_SCHEMA_V3, "model": MODEL_ID, "policy": req["policy"],
                "seed": _int(req.get("seed"), "seed", 0, MAX_SEED), "fault": self._fault(req.get("fault"))}

    @staticmethod
    def _fault(value: Any) -> dict[str, Any] | None:
        if value is None:
            return None
        obj = _only(value, {"kind", "magnitude", "start_s", "end_s"}, "fault")
        kind = obj.get("kind")
        if not isinstance(kind, str) or kind not in FAULTS:
            raise AdapterError(f"fault.kind must be one of {list(FAULTS)}")
        _, _, magnitude, window, *_ = FAULTS[kind]
        if magnitude is None:
            given = obj.get("magnitude", 0)
            if isinstance(given, bool) or not isinstance(given, (int, float)) or given != 0:
                raise AdapterError(f"fault.magnitude does not apply to {kind}; omit it or use 0")
            size = 0.0
        else:
            size = _number(obj.get("magnitude"), "fault.magnitude", magnitude[0], magnitude[1], None)
        start, end = _seconds(obj.get("start_s"), "fault.start_s"), _seconds(obj.get("end_s"), "fault.end_s")
        if end <= start:
            raise AdapterError("fault.end_s must be after fault.start_s")
        if window is not None and not round(window[0] / DT_S) <= end - start <= round(window[1] / DT_S):
            raise AdapterError(f"fault.end_s must make the {kind} window last between {window[0]:g} and {window[1]:g} s")
        return {"kind": kind, "magnitude": size, "start_s": start / 100, "end_s": end / 100}

    def case_for(self, req: dict) -> dict:
        case = json.loads(json.dumps(self.template_m91 if req["policy"] in M91_POLICIES else self.template))
        fault = req["fault"]
        case["controller"]["policy"] = req["policy"]
        case["faults"] = [] if fault is None else [dict(fault)]
        text = "nominal" if fault is None else (f"{fault['kind']} {fault['magnitude']:g} from {fault['start_s']:g} s "
                                                 f"to {fault['end_s']:g} s")
        name = f"Mission Control landing: {text}, {req['policy']} policy"
        if len(name) > 80:  # the simulator limits names to 80 characters; the longer M9.1 names need the short form
            name = f"Landing: {text}, {req['policy']}"
        case["name"] = name[:80]
        return case

    # ------------------------------------------------------------ execution

    def _execute(self, req: dict, out: Path) -> None:
        (out / "inputs").mkdir(parents=True)
        (out / "inputs" / "request.json").write_bytes(_canonical(req))
        (out / "inputs" / "case.json").write_bytes(_canonical(self.case_for(req)))
        done = self._call("land", str(out / "inputs" / "case.json"), "--seed", str(req["seed"]), "--output", str(out))
        # Exit 2 means a requirement or invariant failed or the vehicle did not land: artifacts are valid.
        if done.returncode not in (0, 2) or not all((out / n).is_file() for n in OUTPUT_FILES):
            raise AdapterError(f"vv-rocket land refused the case (exit {done.returncode}): {done.stderr.strip()[-400:]}")

    def verify(self, run_dir: Path) -> dict[str, Any]:
        """Typed view of a stored run: replay by this build plus integrity and identity checks."""
        run_dir = Path(run_dir)
        problems: list[str] = []
        done = self._call("replay", str(run_dir))
        try:
            report = json.loads(done.stdout) if done.returncode in (0, 1) else None
        except json.JSONDecodeError:
            report = None
        if not (isinstance(report, dict) and isinstance(report.get("status"), str)
                and isinstance(report.get("checks"), list)):
            report = None
        replay = ({"status": "error", "detail": done.stderr.strip()[-400:]} if report is None
                  else {"status": report["status"], "checks": report["checks"]})

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

        trace, manifest, verification = load("trace.json"), load("run.json"), load("verification.json")
        problems.extend(self._input_binding_problems(run_dir))
        problems.extend(f"{name} is not produced by this adapter" for name in sorted(set(_files(run_dir)) - EXPECTED_FILES))
        binary_sha = self._binary_sha()
        problems.extend(self._identity_problems(run_dir, binary_sha))
        problems.extend(self._seed_policy_problems(run_dir, manifest))
        files = {n: sha256_file(run_dir / n) for n in OUTPUT_FILES if (run_dir / n).is_file()}
        inputs = {n: sha256_file(run_dir / "inputs" / n) for n in ("request.json", "case.json")
                  if (run_dir / "inputs" / n).is_file()}
        return {
            "schema": RESULT_SCHEMA_V3,
            "adapter": ADAPTER_SCHEMA_V3,
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
            "verification": verification if isinstance(verification, dict) else {},
            "model_validity": MODEL_VALIDITY,
            "verdict": _verdict(replay, problems),
        }

    def _seed_policy_problems(self, run_dir: Path, manifest: Any) -> list[str]:
        """`replay` recomputes the run from the stored seed, so the seed and policy must be those of the request."""
        try:
            req = self.validate(json.loads((run_dir / "inputs" / "request.json").read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return []  # reported by _input_binding_problems
        if not isinstance(manifest, dict):
            return []
        return [f"run.json {name} differs from the request" for name in ("seed", "policy")
                if manifest.get(name) != req[name]]


def request_for(policy: str, seed: int, fault: dict | None) -> dict:
    """A v3 request body; the adapter validates it."""
    return {"schema": REQUEST_SCHEMA_V3, "model": MODEL_ID, "policy": policy, "seed": seed, "fault": fault}

