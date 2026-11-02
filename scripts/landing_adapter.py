"""Adapter `vv-sim-adapter.v3` for the `rocket-landing` model (M9 closed-loop powered landing).

Wraps `vv-rocket land` / `replay` (crates/vv-rocket). A request names a controller policy,
a seed and up to two faults (`faults`, or the single-fault form `fault`); the adapter validates them against the pre-registered ranges
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
    LANDING_M10_POLICIES,
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
# The M10 arms run on case schema v2 (`controller.nav`) and are judged by verification v3, which adds the
# `navigation` block; the M9 and M9.1 templates are schema v1 and refuse these policies.
TEMPLATE_M10 = CRATE / "landing" / "m10-nominal.json"
M10_POLICIES = LANDING_M10_POLICIES
PHYSICS = ("closed-loop powered landing of a 22 t rocket stage: the 6-DOF rigid body of the rocket-rigid-body model, "
           "a throttle and thrust-vector actuator, noisy radar altimeter, GNSS and IMU, and a deterministic controller "
           "that sees only the observations; fixed step 0.01 s, control at 50 Hz")
MODEL_VALIDITY = ("Idealized demonstrator; not flight software and not validated against flight data. "
                  "No contact dynamics: touchdown is the instant the nozzle exit plane reaches the ground. "
                  "Requirements, dispersions and sensor noise are assumed values, not those of a real vehicle.")
DT_S = 0.01
DURATION_S = 40.0
MAX_SEED = 2**32 - 1  # one run per seed; the campaign uses 1000 to 1029
MAX_FAULTS = 2  # the M10 campaign pairs (F3) are the largest combination the design studies
# Seeds held back for the M10 evaluation and its reserve (docs/m10-resilient-navigation.md, 10.1). Nothing
# behind this adapter may run them: a run would be a look at the evaluation before the configuration is frozen.
EVALUATION_SEEDS = range(3000, 3100)
RESERVE_SEEDS = range(6000, 6100)


def protected_seed(seed: Any) -> bool:
    return isinstance(seed, int) and not isinstance(seed, bool) and (seed in EVALUATION_SEEDS or seed in RESERVE_SEEDS)


def seed_refusal(seed: int) -> str:
    which = "evaluation seed (3000 to 3099)" if seed in EVALUATION_SEEDS else "reserve seed (6000 to 6099)"
    return (f"seed {seed} is an M10 {which}; those seeds are never run before the evaluation configuration is "
            f"frozen. Use a development seed such as 5000 to 5099")

POLICIES = {
    "baseline": "Uses the latest reading of each sensor and trusts the radar altimeter for height.",
    "robust": "Runs its own navigation filter and rejects an altimeter that disagrees with the GNSS and inertial estimate.",
    "guarded": "The robust estimator plus two rules: when altimeter and estimate disagree it guides on the lower altitude "
               "and reports sensor_disagreement, and it cuts the engine when it climbs under power (ascent_abort).",
    "baseline_guarded": "The baseline policy unchanged plus the ascent-abort rule only (M9.1 test of that rule).",
    "m10_a": "M10 comparison arm A: fixed-gain navigation with 2-of-3 altitude voting. Declares a navigation mode "
             "and channel integrity (development, not an evaluation).",
    "m10_b": "M10 comparison arm B: a 7-state Kalman filter that rejects a measurement on one epoch's NIS. Declares a "
             "navigation mode and channel integrity (development, not an evaluation).",
    "m10_b_plus": "M10 reference architecture B+: the same filter without rejection, per-source CUSUM, radar and GNSS "
                  "group health, a mode manager and an independent safety monitor (development, not an evaluation).",
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
    # M10, case schema v2 only (docs/m10-implementation.md, Esquema v2: falhas novas); M10 policies only.
    "altimeter_stuck": (
        "Altimeter stuck (M10)", "The radar altimeter repeats the value it delivered just before the window.",
        None, (1.0, 10.0), 0.0, 8.0, 12.0),
    "altimeter_delay": (
        "Altimeter delay (M10)", "The radar altimeter reports the altitude of the magnitude earlier, in whole control "
        "cycles.", (0.02, 0.2, "s"), None, 0.1, 6.0, 40.0),
    "altimeter_outliers": (
        "Altimeter outliers (M10)", "Each altimeter sample is an outlier of 5 to 50 sigma with probability the magnitude.",
        (0.001, 0.01, "probability"), None, 0.005, 0.0, 40.0),
    "altimeter_drift": (
        "Altimeter drift (M10)", "The radar altimeter reading drifts up at the magnitude from the window start.",
        (0.03, 0.3, "m/s"), None, 0.15, 6.0, 40.0),
    "gnss_horizontal_bias": (
        "GNSS horizontal bias (M10)", "The GNSS position is shifted by the magnitude along x and y (not z).",
        (5.0, 30.0, "m"), None, 15.0, 8.0, 40.0),
    "gnss_coherent_ramp": (
        "GNSS coherent ramp (M10)", "Coherent receiver fault: the GNSS position in x and z grows at the magnitude and "
        "the velocity in x and z is offset by the same magnitude.", (0.1, 3.0, "m/s"), None, 1.0, 8.0, 40.0),
    "imu_accel_drift": (
        "IMU acceleration drift (M10)", "The accelerometer bias along the body axis x_B grows at the magnitude per second.",
        (0.01, 0.1, "m/s² per s"), None, 0.05, 6.0, 40.0),
}
# Faults that exist only in case schema v2; the adapter accepts them only with an M10 policy, as the simulator does.
M10_FAULTS = frozenset({"altimeter_stuck", "altimeter_delay", "altimeter_outliers", "altimeter_drift",
                        "gnss_horizontal_bias", "gnss_coherent_ramp", "imu_accel_drift"})

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
        self.template_m10 = json.loads(TEMPLATE_M10.read_text(encoding="utf-8"))

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
                "policies": [{"id": p, "description": d, "template": self._template_path(p).name,
                              "navigation_declarations": p in M10_POLICIES} for p, d in POLICIES.items()],
                "faults": [{"kind": k, "label": label, "description": text,
                            "magnitude": None if mag is None else {"min": mag[0], "max": mag[1], "unit": mag[2], "default": dm},
                            "window_length_s": None if win is None else {"min": win[0], "max": win[1]},
                            "default_start_s": start, "default_end_s": end,
                            "policies": sorted(M10_POLICIES) if k in M10_FAULTS else None}
                           for k, (label, text, mag, win, dm, start, end) in FAULTS.items()],
                "max_faults": MAX_FAULTS,
                "seed": {"min": 0, "max": MAX_SEED,
                         "protected": [{"min": r.start, "max": r.stop - 1, "use": use}
                                       for r, use in ((EVALUATION_SEEDS, "M10 evaluation"), (RESERVE_SEEDS, "M10 reserve"))],
                         "development": {"min": 5000, "max": 5099},
                         "note": "0 is the nominal case without dispersions; sensor noise stays on. Other seeds also disperse "
                                 "the initial state, propellant, thrust and Isp. The M10 evaluation and reserve seeds are "
                                 "refused."},
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
        req = _only(request, {"schema", "model", "policy", "seed", "fault", "faults"}, "request")
        if req.get("schema") != REQUEST_SCHEMA_V3:
            raise AdapterError(f"schema must be {REQUEST_SCHEMA_V3}")
        if req.get("model") != MODEL_ID:
            raise AdapterError(f"model must be {MODEL_ID}")
        if req.get("policy") not in POLICIES:
            raise AdapterError(f"policy must be one of {sorted(POLICIES)}")
        seed = _int(req.get("seed"), "seed", 0, MAX_SEED)
        if protected_seed(seed):
            raise AdapterError(seed_refusal(seed))
        faults = self._faults(req)
        for index, fault in enumerate(faults):
            if fault["kind"] in M10_FAULTS and req["policy"] not in M10_POLICIES:
                name = "fault" if "fault" in req else f"faults[{index}]"
                raise AdapterError(f"{name}.kind {fault['kind']} exists only in case schema v2 and needs an M10 policy "
                                   f"({', '.join(sorted(M10_POLICIES))})")
        return {"schema": REQUEST_SCHEMA_V3, "model": MODEL_ID, "policy": req["policy"], "seed": seed, "faults": faults}

    @classmethod
    def _faults(cls, req: dict) -> list[dict[str, Any]]:
        """`faults` (a list of up to MAX_FAULTS) is canonical; `fault` (one object or null) is the single-fault form.

        The order is kept: the simulator applies the faults in list order and the run identity says what ran.
        """
        if "fault" in req and "faults" in req:
            raise AdapterError("send either fault or faults, not both")
        if "faults" not in req:
            single = cls._fault(req.get("fault"))
            return [] if single is None else [single]
        given = req["faults"]
        if not isinstance(given, list):
            raise AdapterError("faults must be a list")
        if len(given) > MAX_FAULTS:
            raise AdapterError(f"faults must have at most {MAX_FAULTS} entries")
        faults = []
        for index, value in enumerate(given):
            if value is None:
                raise AdapterError(f"faults[{index}] must be an object")
            faults.append(cls._fault(value, f"faults[{index}]"))
        kinds = [f["kind"] for f in faults]
        if len(set(kinds)) != len(kinds):
            raise AdapterError(f"faults must not repeat a kind ({kinds[0]} twice)")
        return faults

    @staticmethod
    def _fault(value: Any, name: str = "fault") -> dict[str, Any] | None:
        if value is None:
            return None
        obj = _only(value, {"kind", "magnitude", "start_s", "end_s"}, name)
        kind = obj.get("kind")
        if not isinstance(kind, str) or kind not in FAULTS:
            raise AdapterError(f"{name}.kind must be one of {list(FAULTS)}")
        _, _, magnitude, window, *_ = FAULTS[kind]
        if magnitude is None:
            given = obj.get("magnitude", 0)
            if isinstance(given, bool) or not isinstance(given, (int, float)) or given != 0:
                raise AdapterError(f"{name}.magnitude does not apply to {kind}; omit it or use 0")
            size = 0.0
        else:
            size = _number(obj.get("magnitude"), f"{name}.magnitude", magnitude[0], magnitude[1], None)
        start, end = _seconds(obj.get("start_s"), f"{name}.start_s"), _seconds(obj.get("end_s"), f"{name}.end_s")
        if end <= start:
            raise AdapterError(f"{name}.end_s must be after {name}.start_s")
        if window is not None and not round(window[0] / DT_S) <= end - start <= round(window[1] / DT_S):
            raise AdapterError(f"{name}.end_s must make the {kind} window last between {window[0]:g} and {window[1]:g} s")
        return {"kind": kind, "magnitude": size, "start_s": start / 100, "end_s": end / 100}

    @staticmethod
    def _template_path(policy: str) -> Path:
        return TEMPLATE_M10 if policy in M10_POLICIES else TEMPLATE_M91 if policy in M91_POLICIES else TEMPLATE

    def case_for(self, req: dict) -> dict:
        policy = req["policy"]
        template = (self.template_m10 if policy in M10_POLICIES else self.template_m91 if policy in M91_POLICIES
                    else self.template)
        case = json.loads(json.dumps(template))
        faults = req["faults"]
        case["controller"]["policy"] = req["policy"]
        case["faults"] = [dict(f) for f in faults]
        text = " + ".join(f"{f['kind']} {f['magnitude']:g} from {f['start_s']:g} s to {f['end_s']:g} s"
                          for f in faults) or "nominal"
        name = f"Mission Control landing: {text}, {req['policy']} policy"
        if len(name) > 80:  # the simulator limits names to 80 characters; the longer names need the short form
            name = f"Landing: {text}, {req['policy']}"
        if len(name) > 80:  # two faults: name the kinds only; the faults themselves are in case.faults
            name = f"Landing: {' + '.join(f['kind'] for f in faults)}, {req['policy']}"
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

    def replay(self, run_dir: Path) -> dict[str, Any]:
        """`vv-rocket replay` of a stored run by this build: recomputes trace, verification and manifest."""
        done = self._call("replay", str(run_dir))
        try:
            report = json.loads(done.stdout) if done.returncode in (0, 1) else None
        except json.JSONDecodeError:
            report = None
        if not (isinstance(report, dict) and isinstance(report.get("status"), str)
                and isinstance(report.get("checks"), list)):
            return {"status": "error", "detail": done.stderr.strip()[-400:], "exit_code": done.returncode}
        return {"status": report["status"], "checks": report["checks"], "exit_code": done.returncode,
                "schema": report.get("schema"), "source_sha256": report.get("source_sha256")}

    def verify(self, run_dir: Path) -> dict[str, Any]:
        """Typed view of a stored run: replay by this build plus integrity and identity checks."""
        run_dir = Path(run_dir)
        problems: list[str] = []
        full = self.replay(run_dir)
        replay = {k: full[k] for k in ("status", "checks", "detail") if k in full}

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

        trace, manifest, verification, case = (load("trace.json"), load("run.json"), load("verification.json"),
                                               load("case.json"))
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
            # The case the simulator ran (k_ff, CUSUM threshold, alert limits), shown by the workbench; no verdict reads it.
            "case": case if isinstance(case, dict) else {},
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
    """A v3 request body in the single-fault form; the adapter validates it."""
    return {"schema": REQUEST_SCHEMA_V3, "model": MODEL_ID, "policy": policy, "seed": seed, "fault": fault}


def request_for_faults(policy: str, seed: int, faults: list[dict]) -> dict:
    """A v3 request body with up to MAX_FAULTS faults, in the order the simulator applies them."""
    return {"schema": REQUEST_SCHEMA_V3, "model": MODEL_ID, "policy": policy, "seed": seed, "faults": list(faults)}

