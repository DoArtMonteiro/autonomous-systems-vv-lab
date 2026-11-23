#!/usr/bin/env python3
"""Extract the data model of the Belief vs Truth view from the stored 0.15.0 run.

Reads only the committed fixture `desktop/domain-rocket/tests/fixtures/stored-by-0.15.0/` and
writes `data.json` next to this file. No simulation runs here and no seed is used.

Every value in `data.json` carries an evidence class and either

* a JSON pointer into one fixture file (`ptr`, with `{i}` standing for the sample index), or
* a named derivation (`derivation`) from other entries of the same file, or
* a source-code fact (`source_facts`) with the file and the lines that state it.

All derived arithmetic lives here. The view only scales and formats. The sha256 of every input is
recorded and verified against the hashes the run itself declares (`run.json`,
`record.json#/provenance`). `record.json` declares no hash for itself, so the observed one is
pinned.

Usage: python spikes/m19-belief-truth/extract.py [--output PATH] [--check]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FIXTURE_REL = "desktop/domain-rocket/tests/fixtures/stored-by-0.15.0"
FIXTURE = ROOT / FIXTURE_REL
INPUTS = ["case.json", "record.json", "run.json", "trace.json", "verification.json"]
SOURCES = [
    "crates/vv-rocket/src/landing_controller.rs",
    "crates/vv-rocket/src/landing_sensors.rs",
    "crates/vv-rocket/src/landing_sim.rs",
    "crates/vv-rocket/src/landing_truth.rs",
    "crates/vv-rocket/src/landing_verify.rs",
]
SCHEMA = "m19-belief-truth-data.v2"

# Provenance of the build. The run records the hash of the vv-rocket sources it was written by
# (algorithm: crates/vv-rocket/src/lib.rs, source_sha256). The tree at RECORDING_COMMIT reproduces
# that hash. The per-file hashes below (CRLF normalised to LF, as the algorithm does) are pinned so
# this extractor needs no git history; tests/test_m19_belief_truth.py proves the pins against git
# and that the aggregate at that commit equals run.json#/source_sha256.
RECORDING_COMMIT = "3962482"
HASHED_FILES = [
    "Cargo.lock", "Cargo.toml", "src/dynamics.rs", "src/landing_actuator.rs", "src/landing_controller.rs",
    "src/landing_model.rs", "src/landing_run.rs", "src/landing_sensors.rs", "src/landing_sim.rs",
    "src/landing_truth.rs", "src/landing_types.rs", "src/landing_verify.rs", "src/lib.rs", "src/main.rs",
    "src/math.rs", "src/model.rs", "src/prng.rs", "src/run.rs", "src/sim.rs", "src/verify.rs",
]
RECORDING_FILE_SHA256 = {
    "Cargo.lock": "9223df2abf54b706fc59f95b19a82c4a692259071e4a99c55b9ace0922781bec",
    "Cargo.toml": "e05e6087e014b54f27e3905c2aac8d15da985c63532e5341c67d2ea550f29fe8",
    "src/dynamics.rs": "153cb17755d3f4bc022990e661ea2d9b39090334a75185d674939e7da71ea016",
    "src/landing_actuator.rs": "2dca1b0fe735cbf55460e44c88420c7ecc9651c3130b3c9e175c920e931e5cbf",
    "src/landing_controller.rs": "03696a5c674bdd73ee3791a1ca6d7eacceb110514b7b1cc50988ebc399bb8c49",
    "src/landing_model.rs": "c4ce3d6b5779914e114715820dd566fbe1516f25334e7f39f36153d68fa24ad7",
    "src/landing_run.rs": "fed954e3ba2b1f225b369d107c183f624cbe14e5be58ca4b97efcb4402d2504e",
    "src/landing_sensors.rs": "46a26d176ff9b8340c6757ab6a05f9b1943de4b893397f690c54eada5bf36586",
    "src/landing_sim.rs": "33132e090e86d1c2e5aefaecbe8903829294967aa6ec1bc963064c6d3a6ffc9b",
    "src/landing_truth.rs": "f3676da6232569074a3320559b3bfea2318df680f34cc42ea73e63cc6be37e8b",
    "src/landing_types.rs": "bf129d71cb4eac42b10c955512c64de600f041300619be1c51e2744b3ca590f7",
    "src/landing_verify.rs": "3f7c314997950d458b44311e2e76585a75a7b654853f57e8715b73587c487ff7",
    "src/lib.rs": "e051578c10e445f7c027e54f7c056fb57d601acee75cb86c7630f9d03057dc4c",
    "src/main.rs": "ec54fef0d148e7ad66aa20f6e2fa76042de89c2db7a84d6be61e0e9acaf1e30b",
    "src/math.rs": "027316ae4cac9b191a9b1001a6576f82319f589683c8da9bbe97f33f16ec61a0",
    "src/model.rs": "95e97548e312fec3a34b4fc10d75e838d3f6cae6f790bc5f272f182b82bb7ace",
    "src/prng.rs": "8b4bb33aeb8d2d12bcbfe8b166a4d0c44fef0854e5c5226d30187b33a4d76cd6",
    "src/run.rs": "59307b3a336e6db83f1891a39bac18f7be9b3c85eebd6ae649addc855d83d13b",
    "src/sim.rs": "bccb4b2227ccf9fdeb70d0e14e30d639282128cc7539a5884cd9dfe4bd09fd4c",
    "src/verify.rs": "4f3ffc9296d71f2b7958743acfdf1cbc2e4d82ef476e73f90db402611865bb7a",
}
ROCKET_DIR = "crates/vv-rocket"
EXTRA_DOCS = {"domain.json": "desktop/domain-rocket/domain.json"}

CLASSES = {
    "T": "Truth, recorded: the simulator's true state, as stored in the trace.",
    "E": "Estimate, recorded: what the controller's estimator reported, as stored in the trace.",
    "O": "Observation, recorded: what a sensor delivered to the controller, as stored in the trace.",
    "D-host": "Derived by the recording host and stored in the run (verifier verdicts, host metrics, "
    "the interpolated contact sample).",
    "D-view": "Derived by this view's extractor from recorded values. Arithmetic is named in the "
    "derivation registry; nothing is simulated.",
    "S": "From source code, not recorded in the run: read in the Rust sources at the stated lines.",
    "C": "Mission configuration recorded in case.json (limits, gains, vehicle constants). "
    "Added to the requested classes because configuration is neither truth nor estimate.",
    "K": "Controller command, recorded: what the controller decided and sent (throttle, gimbal), "
    "as stored in the trace under command. Kept apart from truth, observation and estimate.",
}

# Source facts: the extractor locates the lines itself, so a line number is never typed by hand.
SOURCE_FACTS = [
    {
        "id": "S_guidance_min",
        "file": SOURCES[0],
        "anchors": ["Rule 1 (`guarded`)", "p_base.z.min(alt)"],
        "claim": "With the guarded policy, while the altimeter is rejected, guidance (only guidance; "
        "the estimator state is untouched) reads the lower of the estimated nozzle-plane altitude "
        "and the altimeter. A cycle without an altimeter sample uses the estimator's altitude. "
        "Which of the two was lower in a given cycle is not recorded.",
    },
    {
        "id": "S_rejection_rule",
        "file": SOURCES[0],
        "anchors": [
            "let residual = alt - (self.p.z - s_cm * nz);",
            "if self.exceed_cycles >= g.altimeter_rejection_cycles {",
        ],
        "claim": "The altimeter residual is the altimeter minus the estimated nozzle-plane altitude "
        "(estimated centre-of-mass z minus s_cm times the body-axis z component). The altimeter is "
        "rejected after the configured number of consecutive control cycles with a residual "
        "above the threshold. s_cm comes from the controller's own nominal propellant, which is not recorded.",
    },
    {
        "id": "S_estimator_fixed_gain",
        "file": SOURCES[0],
        "anchors": [
            "fn update_robust(",
            "self.v.z += g.altimeter_velocity_gain * residual / dt;",
        ],
        "claim": "The estimator is a fixed-gain blend of IMU propagation, GNSS and a gated altimeter. "
        "It holds a position and a velocity and no covariance, so it has no uncertainty to report. "
        "The estimated position is the centre of mass.",
    },
    {
        "id": "S_nozzle_from_cm",
        "file": SOURCES[0],
        "anchors": [
            "let r_e = Vec3::new(-s_cm, 0.0, 0.0);",
            "let p_base = p + q.rotate(r_e);",
        ],
        "claim": "Guidance converts the estimated centre-of-mass position to the nozzle plane with the "
        "attitude and s_cm, and steers that nozzle-plane point (horizontal offset to the pad, altitude).",
    },
    {
        "id": "S_gnss_bias",
        "file": SOURCES[1],
        "anchors": [
            "gnss_position_m = Some((s.r + np + bias).to_array());",
            "let bias = Vec3::new(faults.gnss_bias_m, 0.0, faults.gnss_bias_m);",
        ],
        "claim": "The gnss_bias fault adds its magnitude to the GNSS position x and z (not y). GNSS "
        "position observes the centre of mass. GNSS velocity carries no bias.",
    },
    {
        "id": "S_altimeter_nozzle",
        "file": SOURCES[1],
        "anchors": [
            "let (base, _) = base_kinematics(&truth.vehicle, s);",
            "Some(base.z + alt_noise + faults.altimeter_bias_m)",
        ],
        "claim": "The altimeter measures the height of the nozzle plane (base z), not of the centre of mass.",
    },
    {
        "id": "S_last_cycle_in_sample",
        "file": SOURCES[2],
        "anchors": ["let current = cycle.as_ref().ok_or(\"no control cycle at step 0\")?;"],
        "claim": "The estimate and the observation stored in a sample are those of the latest control "
        "cycle, which can be a step or more older than the sample's own step.",
    },
    {
        "id": "S_touchdown_sample",
        "file": SOURCES[2],
        "anchors": [
            "if let Some((u, state)) = contact(&truth.vehicle, &s, &next) {",
            "let t_touch = ((step - 1) as f64 + u) * dt;",
        ],
        "claim": "The touchdown sample is off the sampling grid. Its truth is the contact state "
        "interpolated by the host between two steps; its estimate and observation are those of the "
        "latest control cycle, not interpolated.",
    },
    {
        "id": "S_interpolate",
        "file": SOURCES[3],
        "anchors": ["pub fn interpolate(a: &State, b: &State, u: f64) -> State {"],
        "claim": "Interpolation of the contact is linear in every component of the true state.",
    },
    {
        "id": "S_outcome_rule",
        "file": SOURCES[4],
        "anchors": [
            "} else if reqs.iter().all(|r| r.pass) && s5_pass {",
            '"hard_landing"',
        ],
        "claim": "Outcome rule: no contact gives no_contact; contact with every requirement passing "
        "and S5 holding gives landed; every other contact gives hard_landing. The label therefore "
        "says that some requirement or S5 failed, not that the impact was hard.",
    },
    {
        "id": "S_invariant_limits",
        "file": SOURCES[4],
        "anchors": [
            'let mut s1 = Tally::new("S1_tilt_envelope"',
            'let mut s5 = Tally::new("S5_no_powered_ascent"',
        ],
        "claim": "S1 is a lower bound (cosine of tilt at least the limit); S2 to S5 are upper bounds. "
        "S2 is evaluated at the contact only. Invariants keep a worst value and a first failure "
        "(null when none), not a time series.",
    },
    {
        "id": "S_ignition_rule",
        "file": SOURCES[0],
        "anchors": [
            "let f_ign = g.ignition_fraction * cfg.max_thrust_n / m_hat;",
            "self.phase = Phase::Burn;",
        ],
        "claim": "While coasting, the controller lights the engine when it is descending faster than the "
        "target contact speed and the deceleration it needs (from the estimated nozzle altitude and "
        "velocity) reaches the ignition fraction of the available thrust-to-mass.",
    },
    {
        "id": "S_rejection_not_fused",
        "file": SOURCES[0],
        "anchors": [
            "if residual.abs() > g.altimeter_residual_threshold_m {",
            "self.p.z += g.altimeter_position_gain * residual;",
        ],
        "claim": "In every control cycle whose residual exceeds the threshold, the altimeter is not fused "
        "into the estimate. This starts before the flag: the flag is raised on the configured number of "
        "consecutive such cycles. A residual within the threshold clears the counter and the flag and fuses "
        "the altimeter again. The only test of the altimeter is the residual against the estimate: the "
        "logic cannot tell which of the two is wrong.",
    },
    {
        "id": "S_detection_same",
        "file": SOURCES[0],
        "anchors": ["sensor_disagreement: cfg.policy.handles_disagreement().then_some(self.rejected),"],
        "claim": "For the guarded policy the sensor_disagreement flag is the altimeter_rejected condition: "
        "the two flags are one detection reported twice.",
    },
    {
        "id": "S_cadence",
        "file": SOURCES[2],
        "anchors": [
            "if step % period == 0 {",
            "let gnss_cycle = (step / period).is_multiple_of(prep.sensors.gnss_period_cycles);",
        ],
        "claim": "The controller runs once every control period (a fixed number of steps) and observes the "
        "altimeter and the IMU each time. GNSS is delivered only on every configured n-th control cycle. "
        "The trace stores a sample every record_every steps.",
    },
    {
        "id": "S_requirements_nozzle",
        "file": SOURCES[4],
        "anchors": [
            "let (bp, bv) = base_kinematics(vehicle, &t.state);",
            "horizontal(bp, req.pad_position_m),",
        ],
        "claim": "R1 and R2 are evaluated on the nozzle-plane velocity at contact and R5 on the nozzle-plane "
        "horizontal position against the pad.",
    },
    {
        "id": "S_cause_active_faults",
        "file": SOURCES[4],
        "anchors": [".map(|s| kinds(&s.active_faults))"],
        "claim": "The cause field of a requirement result is the list of faults active at the contact step. "
        "It is filled in whether the requirement passed or failed, so it is not an attribution.",
    },
    {
        "id": "S_replay_host_sdk",
        "file": "desktop/platform/src/host_sdk.rs",
        "anchors": [
            "/// Recomputes a stored run from its request and compares every file byte for byte.",
            "pub const EARLIER_BUILD_AGREEMENT_CHECK: &str =",
            "pub fn replay_earlier_build<H: DomainHost>(host: &H, dir: &Path) -> ReplayReport {",
        ],
        "claim": "The strict replay requires the stored request to be canonical under the current catalogue "
        "and then compares every recomputed file byte for byte. A run stored by an earlier build is "
        "rejected there when the current catalogue adds parameters. The earlier-build replay completes the "
        "request with the current defaults, re-simulates, and compares outcome, safety, requirement "
        "verdicts, telemetry channels, events and metrics; texts, the scene and the native files are not compared.",
    },
    {
        "id": "S_earlier_build_test",
        "file": "desktop/domain-rocket/tests/earlier_build.rs",
        "anchors": [
            "fn a_run_written_by_the_0_15_0_host_verifies_against_its_record_under_the_current_host() {",
            'assert_eq!(strict.status, "rejected");',
        ],
        "claim": "The test stores this run's fixture, asserts that the strict replay is rejected at the "
        "canonical-request check (the stored request predates later parameters), and that the earlier-build "
        "replay is verified with its agreement check passing.",
    },
]

DERIVATIONS = {
    "est_minus_truth": {
        "formula": "estimate_k - truth_k, both centre of mass, same axis k.",
        "approx": False,
    },
    "obs_minus_truth": {
        "formula": "gnss_k - truth_k: GNSS position is a centre-of-mass observation, same axis k.",
        "approx": False,
    },
    "altimeter_minus_truth_nozzle": {
        "formula": "altimeter - truth nozzle-plane z (base_position_m[2]). Both refer to the nozzle plane.",
        "approx": False,
    },
    "s_cm_proxy": {
        "formula": "s_cm = (dry_mass*dry_cm_station + propellant*propellant_cm_station) / "
        "(dry_mass + propellant), with the recorded TRUTH propellant as a proxy for the controller's "
        "unrecorded nominal propellant.",
        "approx": True,
    },
    "body_axis_z_from_imu": {
        "formula": "z component of the body x axis rotated by the IMU attitude quaternion [w,x,y,z]: "
        "2*(x*z - w*y).",
        "approx": False,
    },
    "est_nozzle_altitude": {
        "formula": "estimated centre-of-mass z - s_cm * body_axis_z (nozzle-plane altitude believed by "
        "the estimator). Uses the s_cm proxy.",
        "approx": True,
    },
    "altimeter_residual": {
        "formula": "altimeter - estimated nozzle altitude, from the recorded post-update estimate at "
        "the sample. Approximate: the controller's own residual (S_rejection_rule) is evaluated every "
        "0.02 s on a pre-update estimate with an unrecorded s_cm; the recorded estimate already "
        "includes the update of that cycle.",
        "approx": True,
    },
    "believed_nozzle_xy": {
        "formula": "estimated centre-of-mass x,y + horizontal part of rotate(IMU attitude, (-s_cm,0,0)). "
        "The nozzle-plane point guidance steers (S_nozzle_from_cm). Uses the s_cm proxy.",
        "approx": True,
    },
    "believed_pad_distance": {
        "formula": "hypot(believed nozzle x - pad x, believed nozzle y - pad y), pad from case.json.",
        "approx": True,
    },
    "guidance_rule_from_flag": {
        "formula": "'min(estimator, altimeter)' while the recorded altimeter_rejected flag is true, "
        "'estimator' otherwise (S_guidance_min, guarded policy). Says which rule was active, not "
        "which value won.",
        "approx": False,
    },
    "lower_altitude_source": {
        "formula": "While the rule is active: 'altimeter' if altimeter < estimated nozzle altitude, "
        "else 'estimator'. The altitude the min() of S_guidance_min would pick. Approximate "
        "(same limits as altimeter_residual); null while the rule is inactive.",
        "approx": True,
    },
    "control_period": {
        "formula": "control_period_steps * dt_s: how often the controller runs.",
        "approx": False,
    },
    "max_abs_before_fault": {
        "formula": "Largest absolute value of the named series over the samples before the fault start.",
        "approx": False,
    },
    "s_cm_station_bound": {
        "formula": "s_cm with full propellant and with empty tanks, from case.json vehicle constants.",
        "approx": False,
    },
    "max_offset_check": {
        "formula": "Largest |(truth cm z - truth nozzle z) - s_cm*n_z| over the samples, using the "
        "truth attitude. A check of the proxy geometry, not a measure of the controller's s_cm.",
        "approx": False,
    },
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalise_eol(data: bytes) -> bytes:
    return data.replace(bytes([13, 10]), bytes([10]))


def sha256_text_file(path: Path) -> str:
    """sha256 of a text file with CRLF read as LF, so data.json does not depend on checkout endings."""
    return sha256_bytes(normalise_eol(path.read_bytes()))


def vv_rocket_source_sha256() -> str:
    """The algorithm of crates/vv-rocket/src/lib.rs source_sha256, over the working tree."""
    d = hashlib.sha256()
    for rel in HASHED_FILES:
        d.update(rel.encode())
        d.update(bytes([0]))
        d.update(normalise_eol((ROOT / ROCKET_DIR / rel).read_bytes()))
        d.update(bytes([0]))
    return d.hexdigest()


def resolve(docs: dict, ptr: str, null_parent: bool = False):
    """Resolve 'file.json#/a/0/b' against the loaded fixture documents.

    With `null_parent`, a null met on the way (a whole sensor vector that is null in the trace)
    makes the value null instead of an error.
    """
    name, _, path = ptr.partition("#")
    node = docs[name]
    for part in path.split("/")[1:]:
        if node is None and null_parent:
            return None
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


def line_range(rel: str, anchors: list[str]) -> list[int]:
    lines = (ROOT / rel).read_text(encoding="utf-8").splitlines()
    found = []
    for a in anchors:
        hits = [n + 1 for n, ln in enumerate(lines) if a in ln]
        if not hits:
            raise SystemExit(f"anchor not found in {rel}: {a}")
        found.append(hits[0])
    return [min(found), max(found)]


def quat_x_axis(q):
    """Rotate (1,0,0) by quaternion [w,x,y,z]."""
    w, x, y, z = q
    return (1 - 2 * (y * y + z * z), 2 * (x * y + w * z), 2 * (x * z - w * y))


class Builder:
    def __init__(self, docs: dict):
        self.docs = docs
        self.series: dict = {}
        self.scalars: dict = {}
        self.n = len(docs["trace.json"]["samples"])

    # -- recorded series ------------------------------------------------------------------
    def rec_series(self, sid, label, unit, cls, ptr, *, ref=None, render="line", cls_by_index=None, note=None,
                   null_parent=False):
        values = [resolve(self.docs, ptr.format(i=i), null_parent) for i in range(self.n)]
        entry = {"label": label, "unit": unit, "cls": cls, "ptr": ptr, "render": render, "values": values}
        if null_parent:
            entry["null_parent"] = True
        if ref:
            entry["reference"] = ref
        if cls_by_index:
            entry["cls_by_index"] = cls_by_index
        if note:
            entry["note"] = note
        self.series[sid] = entry

    def der_series(self, sid, label, unit, name, inputs, values, *, ref=None, render="line", cls="D-view",
                   source_facts=None, note=None, cls_by_index=None):
        entry = {
            "label": label,
            "unit": unit,
            "cls": cls,
            "derivation": {"name": name, "series_inputs": inputs, "scalar_inputs": []},
            "render": render,
            "values": values,
        }
        if source_facts:
            entry["source_facts"] = source_facts
        if ref:
            entry["reference"] = ref
        if note:
            entry["note"] = note
        if cls_by_index:
            entry["cls_by_index"] = cls_by_index
        self.series[sid] = entry

    # -- scalars --------------------------------------------------------------------------
    def rec_scalar(self, sid, label, unit, cls, ptr, *, digits=None, note=None, reduce=None):
        value = resolve(self.docs, ptr)
        entry = {"label": label, "unit": unit, "cls": cls, "ptr": ptr, "v": value}
        if reduce == "len":
            entry["v"] = len(value)
            entry["reduce"] = "len"
        if digits is not None:
            entry["digits"] = digits
        if note:
            entry["note"] = note
        self.scalars[sid] = entry

    def der_scalar(self, sid, label, unit, name, v, *, series_inputs=(), scalar_inputs=(), cls="D-view",
                   digits=None, note=None, source_facts=None, at=None, params=None):
        entry = {
            "label": label,
            "unit": unit,
            "cls": cls,
            "v": v,
            "derivation": {
                "name": name,
                "series_inputs": list(series_inputs),
                "scalar_inputs": list(scalar_inputs),
            },
        }
        if at is not None:
            entry["derivation"]["at_index"] = at
        if params:
            entry["derivation"]["params"] = params
        if digits is not None:
            entry["digits"] = digits
        if note:
            entry["note"] = note
        if source_facts:
            entry["source_facts"] = source_facts
        self.scalars[sid] = entry


def build() -> dict:
    raw = {n: (FIXTURE / n).read_bytes() for n in INPUTS}
    docs = {n: json.loads(b) for n, b in raw.items()}
    for dname, drel in EXTRA_DOCS.items():
        docs[dname] = json.loads((ROOT / drel).read_text(encoding="utf-8"))
    run, case, trace, ver, rec = (docs[k] for k in ("run.json", "case.json", "trace.json", "verification.json", "record.json"))
    samples = trace["samples"]
    n = len(samples)
    last = n - 1
    b = Builder(docs)

    # ---- inputs and hash verification ------------------------------------------------------
    declared = {
        "case.json": [("run.json#/case/sha256", run["case"]["sha256"])],
        "trace.json": [("run.json#/trace/sha256", run["trace"]["sha256"])],
        "verification.json": [("run.json#/verification/sha256", run["verification"]["sha256"])],
    }
    for k, art in enumerate(rec["provenance"]["artifacts"]):
        declared.setdefault(art["path"], []).append((f"record.json#/provenance/artifacts/{k}/sha256", art["sha256"]))
        if art["bytes"] != len(raw[art["path"]]):
            raise SystemExit(f"declared size differs for {art['path']}")
    inputs = {}
    for name in INPUTS:
        actual = sha256_bytes(raw[name])
        decl = []
        for where, h in declared.get(name, []):
            if h != actual:
                raise SystemExit(f"hash declared at {where} does not match {name}")
            decl.append(where)
        inputs[name] = {
            "path": f"{FIXTURE_REL}/{name}",
            "sha256": actual,
            "bytes": len(raw[name]),
            "declared_by": decl,
            "pinned_only": not decl,
        }
    source_files = {rel: sha256_text_file(ROOT / rel) for rel in sorted({f["file"] for f in SOURCE_FACTS})}
    extra_inputs = {
        dname: {"path": drel, "sha256": sha256_text_file(ROOT / drel)} for dname, drel in EXTRA_DOCS.items()
    }

    facts = {}
    for f in SOURCE_FACTS:
        facts[f["id"]] = {
            "file": f["file"],
            "lines": line_range(f["file"], f["anchors"]),
            "anchors": f["anchors"],
            "claim": f["claim"],
            "cls": "S",
        }
        rel = f["file"]
        if rel.startswith(ROCKET_DIR + "/"):
            inner = rel[len(ROCKET_DIR) + 1:]
            facts[f["id"]]["identical_to_recording"] = (
                sha256_text_file(ROOT / rel) == RECORDING_FILE_SHA256[inner] if inner in HASHED_FILES else None
            )
        else:
            facts[f["id"]]["identical_to_recording"] = None

    # ---- constants from case.json ----------------------------------------------------------
    veh = case["vehicle"]
    gains = case["controller"]["gains"]
    pad = case["requirements"]["pad_position_m"]
    fault = case["faults"][0]
    fault_t0 = fault["start_s"]

    def csc(sid, label, unit, ptr, digits=None, note=None):
        b.rec_scalar(sid, label, unit, "C", ptr, digits=digits, note=note)

    csc("case.dry_mass_kg", "Dry mass", "kg", "case.json#/vehicle/dry_mass_kg", 0)
    csc("case.dry_cm_station_m", "Dry centre-of-mass station", "m", "case.json#/vehicle/dry_cm_station_m", 1)
    csc("case.propellant_cm_station_m", "Propellant centre-of-mass station", "m", "case.json#/vehicle/propellant_cm_station_m", 1)
    csc("case.altimeter_threshold_m", "Altimeter rejection threshold", "m", "case.json#/controller/gains/altimeter_residual_threshold_m", 1)
    csc("case.altimeter_rejection_cycles", "Consecutive cycles to reject", "cycles", "case.json#/controller/gains/altimeter_rejection_cycles", 0)
    csc("case.gnss_sigma_m", "GNSS position noise (1 sigma, per axis)", "m", "case.json#/sensors/gnss_position_sigma_m", 1)
    csc("case.pad_x_m", "Pad centre x", "m", "case.json#/requirements/pad_position_m/0", 0)
    csc("case.pad_y_m", "Pad centre y", "m", "case.json#/requirements/pad_position_m/1", 0)
    csc("case.r5_radius_m", "R5 landing radius", "m", "case.json#/requirements/r5_position_m", 0)
    csc("case.keep_out_m", "S2 keep-out radius", "m", "case.json#/requirements/s2_keep_out_m", 0)
    csc("case.fault_magnitude_m", "GNSS bias magnitude", "m", "case.json#/faults/0/magnitude", 0)
    csc("case.fault_start_s", "Fault start", "s", "case.json#/faults/0/start_s", 1)
    csc("case.fault_end_s", "Fault end", "s", "case.json#/faults/0/end_s", 1)
    csc("case.dt_s", "Simulation step", "s", "case.json#/dt_s", 2)
    csc("case.control_period_steps", "Control period", "steps", "case.json#/sensors/control_period_steps", 0)

    b.der_scalar("case.control_period_s", "Control period", "s", "control_period",
                 case["sensors"]["control_period_steps"] * case["dt_s"],
                 scalar_inputs=["case.control_period_steps", "case.dt_s"], digits=2)

    # ---- run identity ----------------------------------------------------------------------
    b.rec_scalar("run.seed", "Seed", "", "C", "run.json#/seed", digits=0)
    b.rec_scalar("run.policy", "Controller policy", "", "C", "run.json#/policy")
    b.rec_scalar("run.fault_kind", "Fault kind", "", "C", "case.json#/faults/0/kind")
    b.rec_scalar("run.domain", "Domain", "", "D-host", "record.json#/domain/id")
    b.rec_scalar("run.version", "Recording domain build", "", "D-host", "record.json#/domain/version")
    b.rec_scalar("run.sample_interval_s", "Trace sampling interval", "s", "D-host", "record.json#/scene/sample_interval_s", digits=1)
    b.rec_scalar("run.verdict_note", "Host note on sampling and verdicts", "", "D-host", "record.json#/notes/2")
    b.rec_scalar("run.model_validity", "Model validity statement", "", "D-host", "record.json#/model_validity")
    b.rec_scalar("run.hash.source", "run.json source_sha256", "", "D-host", "run.json#/source_sha256")
    b.rec_scalar("run.hash.case", "run.json case sha256", "", "D-host", "run.json#/case/sha256")
    b.rec_scalar("run.hash.trace", "run.json trace sha256", "", "D-host", "run.json#/trace/sha256")
    b.rec_scalar("run.hash.verification", "run.json verification sha256", "", "D-host", "run.json#/verification/sha256")
    b.rec_scalar("run.outcome_code", "Outcome code", "", "D-host", "verification.json#/outcome")
    b.rec_scalar("run.outcome_label", "Outcome label", "", "D-host", "record.json#/outcome/label")
    b.rec_scalar("run.outcome_explanation", "Outcome explanation", "", "D-host", "record.json#/outcome/explanation")
    b.rec_scalar("run.requirements_pass", "Mission requirements pass", "", "D-host", "verification.json#/requirements_pass")
    b.rec_scalar("run.invariants_pass", "Safety invariants pass", "", "D-host", "verification.json#/invariants_pass")
    b.rec_scalar("run.steps", "Steps simulated", "", "T", "run.json#/summary/steps", digits=0)
    evk = {e["kind"]: k for k, e in enumerate(trace["events"])}
    b.rec_scalar("run.ignition_t_s", "Ignition", "s", "T", f"trace.json#/events/{evk['ignition']}/t_s", digits=1)
    b.rec_scalar("run.fault_start_event_t_s", "Fault start event", "s", "T",
                 f"trace.json#/events/{evk['fault_start']}/t_s", digits=1)
    b.rec_scalar("run.touchdown_t_s", "Touchdown time", "s", "D-host", f"trace.json#/events/{evk['touchdown']}/t_s", digits=3,
                 note="Interpolated by the host between two steps (S_touchdown_sample).")
    b.rec_scalar("run.touchdown_step", "Touchdown step", "", "D-host", f"trace.json#/events/{evk['touchdown']}/step", digits=0)
    b.rec_scalar("run.reject_first_t_s", "Altimeter first rejected (controller flag)", "s", "E",
                 "verification.json#/controller_flags/altimeter_rejected_first/t_s", digits=2,
                 note="Controller-reported; not used for any verdict.")
    b.rec_scalar("run.reject_first_step", "Altimeter first rejected, step", "", "E",
                 "verification.json#/controller_flags/altimeter_rejected_first/step", digits=0)
    b.rec_scalar("run.disagreement_first_t_s", "Sensor disagreement first reported (controller flag)", "s", "E",
                 "verification.json#/controller_flags/sensor_disagreement_first/t_s", digits=2)

    # ---- sample index helpers (layout metadata, not rendered values) ------------------------
    t_vals = [s["t_s"] for s in samples]
    idx_fault_first = next(i for i, t in enumerate(t_vals) if t >= fault_t0 - 1e-9)
    flags = [s["estimate"]["altimeter_rejected"] for s in samples]
    idx_flag_first = next(i for i, f in enumerate(flags) if f)
    if any(not f for f in flags[idx_flag_first:]):
        raise SystemExit("the rejection flag clears after being raised: the lane model assumes it does not")
    idx = {
        "fault_first_sample": idx_fault_first,
        "flag_first_sample": idx_flag_first,
        "last_periodic": last - 1,
        "touchdown": last,
    }
    if samples[last]["kind"] != "touchdown" or any(s["kind"] != "periodic" for s in samples[:last]):
        raise SystemExit("unexpected sample kinds")

    # ---- recorded series -------------------------------------------------------------------
    td_override = {str(last): "D-host"}
    b.rec_series("t_s", "Logical time", "s", "T", "trace.json#/samples/{i}/t_s", cls_by_index=td_override)
    b.rec_series("step", "Step", "", "T", "trace.json#/samples/{i}/step", cls_by_index=td_override)
    b.rec_series("kind", "Sample kind", "", "T", "trace.json#/samples/{i}/kind")
    for k, ax in enumerate("xyz"):
        b.rec_series(f"truth_{ax}", f"True position {ax} (centre of mass)", "m", "T",
                     f"trace.json#/samples/{{i}}/truth/position_m/{k}", ref="centre of mass", cls_by_index=td_override)
    for k, ax in enumerate("xyz"):
        b.rec_series(f"base_{ax}", f"True nozzle-plane position {ax}", "m", "T",
                     f"trace.json#/samples/{{i}}/truth/base_position_m/{k}", ref="nozzle plane", cls_by_index=td_override)
    b.rec_series("prop_kg", "True propellant mass", "kg", "T", "trace.json#/samples/{i}/truth/propellant_kg",
                 cls_by_index=td_override)
    for k, c in enumerate("wxyz"):
        b.rec_series(f"truth_q_{c}", f"True attitude q_{c}", "", "T", f"trace.json#/samples/{{i}}/truth/attitude/{k}",
                     cls_by_index=td_override, render="none")
    for k, ax in enumerate("xyz"):
        b.rec_series(f"est_{ax}", f"Estimated position {ax} (centre of mass)", "m", "E",
                     f"trace.json#/samples/{{i}}/estimate/position_m/{k}", ref="centre of mass")
    b.rec_series("alt_rejected", "Altimeter rejected (estimator flag)", "", "E",
                 "trace.json#/samples/{i}/estimate/altimeter_rejected", render="lane")
    for k, ax in enumerate("xyz"):
        b.rec_series(f"gnss_{ax}", f"GNSS position {ax} (observation)", "m", "O",
                     f"trace.json#/samples/{{i}}/observation/gnss_position_m/{k}", ref="centre of mass", render="points",
                     null_parent=True, note="Null where GNSS delivered nothing in that control cycle.")
    b.rec_series("altimeter", "Altimeter (observation)", "m", "O", "trace.json#/samples/{i}/observation/altimeter_m",
                 ref="nozzle plane", render="points")
    for k, c in enumerate("wxyz"):
        b.rec_series(f"imu_q_{c}", f"IMU attitude q_{c} (observation)", "", "O",
                     f"trace.json#/samples/{{i}}/observation/imu/attitude/{k}", render="none")
    ch_index = {c["id"]: k for k, c in enumerate(rec["channels"])}
    b.rec_series("err_z_host", "Vertical error, estimate - truth (host metric)", "m", "D-host",
                 f"record.json#/channels/{ch_index['err_z']}/values/{{i}}", ref="centre of mass")
    b.rec_series("err_h_host", "Horizontal error magnitude (host metric)", "m", "D-host",
                 f"record.json#/channels/{ch_index['err_h']}/values/{{i}}", ref="centre of mass")
    b.rec_series("pad_distance_host", "True distance of nozzle plane from pad centre (host metric)", "m", "D-host",
                 f"record.json#/channels/{ch_index['pad_distance']}/values/{{i}}", ref="nozzle plane")

    S = b.series
    v = lambda sid: S[sid]["values"]  # noqa: E731

    # ---- derived series --------------------------------------------------------------------
    for ax in "xy":
        b.der_series(f"err_est_{ax}", f"Estimate - truth, {ax}", "m", "est_minus_truth", [f"est_{ax}", f"truth_{ax}"],
                     [e - t for e, t in zip(v(f"est_{ax}"), v(f"truth_{ax}"))], ref="centre of mass")
    for ax in "xyz":
        gv = [None if g is None else g - t for g, t in zip(v(f"gnss_{ax}"), v(f"truth_{ax}"))]
        b.der_series(f"err_gnss_{ax}", f"GNSS - truth, {ax}", "m", "obs_minus_truth", [f"gnss_{ax}", f"truth_{ax}"], gv,
                     ref="centre of mass", render="points")
    b.der_series("err_altimeter", "Altimeter - true nozzle altitude", "m", "altimeter_minus_truth_nozzle",
                 ["altimeter", "base_z"], [a - z for a, z in zip(v("altimeter"), v("base_z"))], ref="nozzle plane",
                 render="points")

    m_dry, c_dry, c_prop = veh["dry_mass_kg"], veh["dry_cm_station_m"], veh["propellant_cm_station_m"]
    s_cm = [(m_dry * c_dry + p * c_prop) / (m_dry + p) for p in v("prop_kg")]
    b.der_series("s_cm", "Centre-of-mass station s_cm (proxy)", "m", "s_cm_proxy", ["prop_kg"], s_cm, render="none",
                 source_facts=["S_rejection_rule"],
                 note="Uses recorded TRUTH propellant as a proxy for the controller's nominal propellant.")
    # The derivation also reads three case.json constants.
    S["s_cm"]["derivation"]["scalar_inputs"] = ["case.dry_mass_kg", "case.dry_cm_station_m", "case.propellant_cm_station_m"]

    qs = [[S[f"imu_q_{c}"]["values"][i] for c in "wxyz"] for i in range(n)]
    nz = [quat_x_axis(q)[2] for q in qs]
    b.der_series("imu_nz", "Body-axis z component from IMU attitude", "", "body_axis_z_from_imu",
                 [f"imu_q_{c}" for c in "wxyz"], nz, render="none")
    est_noz = [ez - sc * z for ez, sc, z in zip(v("est_z"), s_cm, nz)]
    b.der_series("est_nozzle_alt", "Estimated nozzle-plane altitude (approx.)", "m", "est_nozzle_altitude",
                 ["est_z", "s_cm", "imu_nz"], est_noz, ref="nozzle plane", render="none",
                 source_facts=["S_nozzle_from_cm"])
    resid = [a - e for a, e in zip(v("altimeter"), est_noz)]
    b.der_series("alt_residual", "Altimeter - estimated nozzle altitude (approx.)", "m", "altimeter_residual",
                 ["altimeter", "est_nozzle_alt"], resid, ref="nozzle plane", render="points",
                 source_facts=["S_rejection_rule"],
                 note="Computed by this view, approximate: the controller's residual uses unrecorded internal terms.")
    bel = []
    for i in range(n):
        w, x, y, z = qs[i]
        rx, ry = 1 - 2 * (y * y + z * z), 2 * (x * y + w * z)
        bel.append((v("est_x")[i] - s_cm[i] * rx, v("est_y")[i] - s_cm[i] * ry))
    b.der_series("believed_nozzle_x", "Believed nozzle-plane position x (approx.)", "m", "believed_nozzle_xy",
                 ["est_x", "s_cm"] + [f"imu_q_{c}" for c in "wxyz"], [p[0] for p in bel], ref="nozzle plane",
                 source_facts=["S_nozzle_from_cm"])
    b.der_series("believed_nozzle_y", "Believed nozzle-plane position y (approx.)", "m", "believed_nozzle_xy",
                 ["est_y", "s_cm"] + [f"imu_q_{c}" for c in "wxyz"], [p[1] for p in bel], ref="nozzle plane",
                 source_facts=["S_nozzle_from_cm"])
    for sid in ("believed_nozzle_x", "believed_nozzle_y"):
        b.series[sid]["note"] = ("At the touchdown sample this is the last recorded estimate before contact, "
                                 "not the belief at the touchdown instant (S_last_cycle_in_sample).")
    bpd = [math.hypot(x - pad[0], y - pad[1]) for x, y in bel]
    b.der_series("believed_pad_distance", "Believed distance of nozzle plane from pad centre (approx.)", "m",
                 "believed_pad_distance", ["believed_nozzle_x", "believed_nozzle_y"], bpd, ref="nozzle plane")
    S["believed_pad_distance"]["derivation"]["scalar_inputs"] = ["case.pad_x_m", "case.pad_y_m"]
    rule = ["min(estimator, altimeter)" if f else "estimator" for f in v("alt_rejected")]
    b.der_series("guidance_rule", "Guidance altitude source: rule active", "", "guidance_rule_from_flag", ["alt_rejected"],
                 rule, cls="S", render="lane", source_facts=["S_guidance_min"])
    lower = [("altimeter" if a < e else "estimator") if f else None
             for a, e, f in zip(v("altimeter"), est_noz, v("alt_rejected"))]
    b.der_series("lower_source", "Lower of the two altitudes while the rule is active (approx.)", "", "lower_altitude_source",
                 ["altimeter", "est_nozzle_alt", "alt_rejected"], lower, render="lane", source_facts=["S_guidance_min"])

    # ---- derived scalars -------------------------------------------------------------------
    pre = [i for i in range(n) if t_vals[i] < fault_t0 - 1e-9]
    b.der_scalar("pre.max_abs_err_x", "Largest |estimate - truth| in x before the fault", "m", "max_abs_before_fault",
                 max(abs(S["err_est_x"]["values"][i]) for i in pre), series_inputs=["err_est_x"], digits=2)
    b.der_scalar("pre.max_abs_residual", "Largest |altimeter residual| before the fault (approx.)", "m",
                 "max_abs_before_fault", max(abs(resid[i]) for i in pre), series_inputs=["alt_residual"], digits=2,
                 note="Pre-fault agreement supports the s_cm proxy: a large error in s_cm would show here.")
    full = (m_dry * c_dry + veh["propellant_mass_kg"] * c_prop) / (m_dry + veh["propellant_mass_kg"])
    b.der_scalar("s_cm.full_tanks_m", "s_cm with full tanks", "m", "s_cm_station_bound", full,
                 scalar_inputs=["case.dry_mass_kg", "case.dry_cm_station_m", "case.propellant_cm_station_m"], digits=2)
    b.der_scalar("s_cm.empty_tanks_m", "s_cm with empty tanks", "m", "s_cm_station_bound", c_dry,
                 scalar_inputs=["case.dry_cm_station_m"], digits=2)
    # Geometry check with the truth attitude.
    tq = [[S[f"truth_q_{c}"]["values"][i] for c in "wxyz"] for i in range(n)]
    off = max(abs((v("truth_z")[i] - v("base_z")[i]) - s_cm[i] * quat_x_axis(tq[i])[2]) for i in range(n))
    b.der_scalar("check.offset_geometry_m", "Largest centre-of-mass to nozzle offset mismatch (geometry check)", "m",
                 "max_offset_check", off, series_inputs=["truth_z", "base_z", "s_cm"] + [f"truth_q_{c}" for c in "wxyz"],
                 digits=3)

    # Touchdown-related scalars: the last sample.
    b.der_scalar("td.true_nozzle_x", "True nozzle-plane x at touchdown", "m", "touchdown_sample_value",
                 v("base_x")[last], series_inputs=["base_x"], at=last, cls="D-host", digits=2,
                 note="Truth of the touchdown sample is the host's interpolated contact state.")
    b.der_scalar("td.true_nozzle_y", "True nozzle-plane y at touchdown", "m", "touchdown_sample_value",
                 v("base_y")[last], series_inputs=["base_y"], at=last, cls="D-host", digits=2)
    b.der_scalar("td.true_cm_x", "True centre-of-mass x at touchdown", "m", "touchdown_sample_value",
                 v("truth_x")[last], series_inputs=["truth_x"], at=last, cls="D-host", digits=2)
    b.der_scalar("td.true_cm_y", "True centre-of-mass y at touchdown", "m", "touchdown_sample_value",
                 v("truth_y")[last], series_inputs=["truth_y"], at=last, cls="D-host", digits=2)
    b.der_scalar("td.est_cm_x", "Last estimated centre-of-mass x before contact", "m", "touchdown_sample_value",
                 v("est_x")[last], series_inputs=["est_x"], at=last, cls="E", digits=2)
    b.der_scalar("td.est_cm_y", "Last estimated centre-of-mass y before contact", "m", "touchdown_sample_value",
                 v("est_y")[last], series_inputs=["est_y"], at=last, cls="E", digits=2)
    b.der_scalar("td.believed_nozzle_x", "Believed nozzle-plane x, last estimate before contact (approx.)", "m",
                 "touchdown_sample_value", bel[last][0], series_inputs=["believed_nozzle_x"], at=last, digits=2)
    b.der_scalar("td.believed_nozzle_y", "Believed nozzle-plane y, last estimate before contact (approx.)", "m",
                 "touchdown_sample_value", bel[last][1], series_inputs=["believed_nozzle_y"], at=last, digits=2)
    b.der_scalar("td.believed_pad_distance", "Believed distance from pad centre, last estimate before contact (approx.)",
                 "m", "touchdown_sample_value", bpd[last], series_inputs=["believed_pad_distance"], at=last, digits=2)
    b.der_scalar("td.gap_m", "Distance between true nozzle point and believed nozzle point at touchdown (approx.)", "m",
                 "touchdown_gap", math.hypot(v("base_x")[last] - bel[last][0], v("base_y")[last] - bel[last][1]),
                 series_inputs=["base_x", "base_y", "believed_nozzle_x", "believed_nozzle_y"], at=last, digits=2)
    b.der_scalar("td.err_est_x", "Estimate - truth in x, last estimate before contact", "m", "touchdown_sample_value",
                 S["err_est_x"]["values"][last], series_inputs=["err_est_x"], at=last, digits=2)
    b.der_scalar("td.err_z_host", "Estimate - truth in z, last estimate before contact (host metric)", "m",
                 "touchdown_sample_value", S["err_z_host"]["values"][last], series_inputs=["err_z_host"], at=last,
                 cls="D-host", digits=2)
    b.der_scalar("td.altimeter", "Altimeter reading, last control cycle before contact", "m", "touchdown_sample_value",
                 v("altimeter")[last], series_inputs=["altimeter"], at=last, cls="O", digits=2)
    b.der_scalar("td.est_nozzle_alt", "Estimated nozzle altitude, last estimate before contact (approx.)", "m",
                 "touchdown_sample_value", est_noz[last], series_inputs=["est_nozzle_alt"], at=last, digits=1)

    # ---- verification: requirements and invariants -----------------------------------------
    req_rows, inv_rows = [], []
    for k, r in enumerate(ver["requirements"]):
        label_ptr = f"record.json#/requirements/{k}/label"
        assert rec["requirements"][k]["id"] == r["id"]
        b.rec_scalar(f"req.{r['id']}.label", "Label", "", "D-host", label_ptr)
        row = {"id": r["id"], "short": r["id"].split("_")[0], "label": f"req.{r['id']}.label", "fields": {}}
        for fld, dg in (("pass", None), ("evaluated", None), ("limit", None), ("value", None), ("expected", None),
                        ("observed", None), ("step", 0), ("t_s", 3), ("cause", None)):
            sid = f"req.{r['id']}.{fld}"
            b.rec_scalar(sid, fld, r["unit"] if fld in ("limit", "value") else "", "D-host",
                         f"verification.json#/requirements/{k}/{fld}", digits=_digits(r, fld, dg))
            row["fields"][fld] = sid
        req_rows.append(row)
    for k, r in enumerate(ver["invariants"]):
        label_ptr = f"record.json#/requirements/{k + len(ver['requirements'])}/label"
        assert rec["requirements"][k + len(ver["requirements"])]["id"] == r["id"]
        b.rec_scalar(f"inv.{r['id']}.label", "Label", "", "D-host", label_ptr)
        row = {"id": r["id"], "short": r["id"].split("_")[0], "label": f"inv.{r['id']}.label", "fields": {}}
        for fld in ("pass", "evaluated", "limit", "worst_value", "failure_count", "first_failure"):
            sid = f"inv.{r['id']}.{fld}"
            b.rec_scalar(sid, fld, r["unit"] if fld in ("limit", "worst_value") else "", "D-host",
                         f"verification.json#/invariants/{k}/{fld}", digits=_digits(r, fld, None))
            row["fields"][fld] = sid
        row["bound"] = "lower" if r["id"].startswith("S1") else "upper"
        row["source_facts"] = ["S_invariant_limits"]
        inv_rows.append(row)

    # ==== iteration 2 ========================================================================
    # Velocity, commands and flags (recorded)
    for k, ax in enumerate("xyz"):
        b.rec_series(f"truth_v{ax}", f"True velocity {ax} (centre of mass)", "m/s", "T",
                     f"trace.json#/samples/{{i}}/truth/velocity_mps/{k}", ref="centre of mass", cls_by_index=td_override)
        b.rec_series(f"est_v{ax}", f"Estimated velocity {ax} (centre of mass)", "m/s", "E",
                     f"trace.json#/samples/{{i}}/estimate/velocity_mps/{k}", ref="centre of mass")
    b.rec_series("err_vz_host", "Vertical velocity error, estimate - truth (host metric)", "m/s", "D-host",
                 f"record.json#/channels/{ch_index['err_vz']}/values/{{i}}", ref="centre of mass")
    b.rec_series("err_vh_host", "Horizontal velocity error magnitude (host metric)", "m/s", "D-host",
                 f"record.json#/channels/{ch_index['err_vh']}/values/{{i}}", ref="centre of mass")
    b.rec_series("cmd_throttle", "Throttle command", "", "K", "trace.json#/samples/{i}/command/throttle",
                 render="none", note="Recorded under command in the trace: what the controller sent that cycle.")
    for k, ax in enumerate("yz"):
        b.rec_series(f"cmd_gimbal_{ax}", f"Gimbal command {ax} (tangent)", "tan", "K",
                     f"trace.json#/samples/{{i}}/command/gimbal_tan/{k}", render="none")
    b.rec_series("engine", "Engine state (applied)", "", "T", "trace.json#/samples/{i}/applied/engine", render="none")
    b.rec_series("sensor_disagreement", "Sensor disagreement (estimator flag)", "", "E",
                 "trace.json#/samples/{i}/estimate/sensor_disagreement", render="none")
    b.rec_series("ascent_abort", "Ascent abort (estimator flag)", "", "E",
                 "trace.json#/samples/{i}/estimate/ascent_abort", render="none")
    b.rec_series("active_faults", "Faults active at the sample", "", "T", "trace.json#/samples/{i}/active_faults",
                 render="none")
    S["gnss_x"]["null_text"] = "no fix on this cycle"
    S["gnss_y"]["null_text"] = "no fix on this cycle"
    S["gnss_z"]["null_text"] = "no fix on this cycle"
    S["err_gnss_x"]["null_text"] = "no fix on this cycle"
    S["err_gnss_y"]["null_text"] = "no fix on this cycle"
    S["err_gnss_z"]["null_text"] = "no fix on this cycle"
    S["lower_source"]["null_text"] = "rule not active"

    # The host metrics are the plain subtractions the view would do: checked here, labelled D-host.
    for i in range(n):
        eh = math.hypot(v("est_x")[i] - v("truth_x")[i], v("est_y")[i] - v("truth_y")[i])
        evh = math.hypot(v("est_vx")[i] - v("truth_vx")[i], v("est_vy")[i] - v("truth_vy")[i])
        padd = math.hypot(v("base_x")[i] - pad[0], v("base_y")[i] - pad[1])
        for name, a, c in (
            ("err_z_host", v("err_z_host")[i], v("est_z")[i] - v("truth_z")[i]),
            ("err_h_host", v("err_h_host")[i], eh),
            ("err_vz_host", v("err_vz_host")[i], v("est_vz")[i] - v("truth_vz")[i]),
            ("err_vh_host", v("err_vh_host")[i], evh),
            ("pad_distance_host", v("pad_distance_host")[i], padd),
        ):
            if abs(a - c) > 1e-9 * max(1.0, abs(c)):
                raise SystemExit(f"host metric {name} differs from its subtraction at sample {i}")

    csc("case.gnss_period_cycles", "GNSS period", "cycles", "case.json#/sensors/gnss_period_cycles", 0)
    csc("case.record_every_steps", "Trace sample period", "steps", "case.json#/record_every", 0)
    csc("case.gnss_position_gain", "GNSS position gain", "", "case.json#/controller/gains/gnss_position_gain", 2)
    csc("case.ignition_fraction", "Ignition fraction", "", "case.json#/controller/gains/ignition_fraction", 2)
    csc("case.altimeter_sigma_m", "Altimeter noise (1 sigma)", "m", "case.json#/sensors/altimeter_sigma_m", 1)
    ctl_steps = case["sensors"]["control_period_steps"]
    b.der_scalar("cad.samples_per_cycle", "Control cycles per trace sample", "cycles", "ratio_of_steps",
                 case["record_every"] / ctl_steps, scalar_inputs=["case.record_every_steps", "case.control_period_steps"],
                 digits=0, source_facts=["S_cadence"])
    b.der_scalar("cad.gnss_period_s", "Time between GNSS fixes", "s", "gnss_period",
                 case["sensors"]["gnss_period_cycles"] * (ctl_steps * case["dt_s"]),
                 scalar_inputs=["case.gnss_period_cycles", "case.control_period_s"], digits=1,
                 source_facts=["S_cadence"])
    has_fix = [x is not None for x in v("gnss_x")]
    b.der_scalar("gnss.fix_samples", "Samples whose control cycle delivered a GNSS fix", "", "count_where",
                 sum(has_fix), series_inputs=["gnss_x"], digits=0, params={"where": "not null"})
    b.der_scalar("gnss.no_fix_samples", "Samples whose control cycle delivered no GNSS fix", "", "count_where",
                 n - sum(has_fix), series_inputs=["gnss_x"], digits=0, params={"where": "null"})
    b.der_scalar("check.no_fix_only_at_touchdown", "No-fix sample is the off-grid touchdown sample only", "",
                 "null_only_at_touchdown", [i for i, f in enumerate(has_fix) if not f] == [last],
                 series_inputs=["gnss_x", "kind"])
    b.der_scalar("check.detection_flags_identical", "sensor_disagreement equals altimeter_rejected at every sample", "",
                 "flags_identical", v("sensor_disagreement") == v("alt_rejected"),
                 series_inputs=["sensor_disagreement", "alt_rejected"], source_facts=["S_detection_same"])
    b.rec_scalar("run.cutoff_t_s", "Engine cutoff time", "s", "T", "run.json#/summary/cutoff_t_s", digits=3)
    b.rec_scalar("run.flameout_t_s", "Flameout time", "s", "T", "run.json#/summary/flameout_t_s", digits=3)
    b.rec_scalar("run.ascent_abort_first", "Ascent abort first flagged", "", "E",
                 "verification.json#/controller_flags/ascent_abort_first")
    b.rec_scalar("run.ignition_command_t_s", "Ignition command time", "s", "T",
                 f"trace.json#/events/{evk['ignition']}/detail/command_t_s", digits=1)
    b.der_scalar("check.no_ascent_abort_flag", "No ascent-abort flag at any sample", "", "none_true",
                 not any(v("ascent_abort")), series_inputs=["ascent_abort"])
    b.der_scalar("check.ignition_before_fault", "Ignition precedes the fault start", "", "before",
                 b.scalars["run.ignition_t_s"]["v"] < fault_t0, scalar_inputs=["run.ignition_t_s", "case.fault_start_s"])
    b.der_scalar("fault.active_at_last_sample", "The configured fault is active at the last sample", "", "fault_active_at_last_sample",
                 fault["kind"] in v("active_faults")[last], series_inputs=["active_faults"], at=last,
                 scalar_inputs=["run.fault_kind"])
    b.der_scalar("fault.ended_before_touchdown", "The configured fault window ends before touchdown", "", "before",
                 fault["end_s"] < b.scalars["run.touchdown_t_s"]["v"],
                 scalar_inputs=["case.fault_end_s", "run.touchdown_t_s"])

    # Frame, initial state and dispersion
    for ax_i, ax in enumerate("xyz"):
        b.rec_scalar(f"frame.{ax}", f"Axis {ax}", "", "D-host", f"record.json#/scene/frame/axes/{ax}")
        csc(f"init.nominal_p{ax}", f"Nominal initial position {ax}", "m", f"case.json#/initial/position_m/{ax_i}", 0)
        b.rec_scalar(f"init.disp_p{ax}", f"Dispersed initial position {ax}", "m", "D-host",
                     f"record.json#/scene/initial/position_m/{ax_i}", digits=1)
        csc(f"init.nominal_v{ax}", f"Nominal initial velocity {ax}", "m/s", f"case.json#/initial/velocity_mps/{ax_i}", 0)
        b.rec_scalar(f"init.disp_v{ax}", f"Dispersed initial velocity {ax}", "m/s", "D-host",
                     f"record.json#/scene/initial/velocity_mps/{ax_i}", digits=1)
        csc(f"init.range_p{ax}", f"Dispersion half-width, position {ax}", "m", f"case.json#/dispersion/position_m/{ax_i}", 0)
        csc(f"init.range_v{ax}", f"Dispersion half-width, velocity {ax}", "m/s", f"case.json#/dispersion/velocity_mps/{ax_i}", 0)

    # Lane evidence: where the altimeter was the lower altitude (approximate, S rule applied)
    flagged = [i for i, f in enumerate(flags) if f]
    b.der_scalar("lane.flagged_samples", "Samples with the rejection flag raised", "", "count_where", len(flagged),
                 series_inputs=["alt_rejected"], digits=0, params={"where": "true"})
    b.der_scalar("lane.altimeter_lower_samples", "Flagged samples where the altimeter was the lower altitude (approx.)", "",
                 "count_where", sum(1 for i in flagged if lower[i] == "altimeter"), series_inputs=["lower_source"],
                 digits=0, params={"where": "altimeter"}, source_facts=["S_guidance_min"])
    b.der_scalar("lane.expected_first_fix_jump_m", "Estimate step caused by one biased GNSS fix: gain x bias", "m",
                 "first_fix_jump", gains["gnss_position_gain"] * fault["magnitude"],
                 scalar_inputs=["case.gnss_position_gain", "case.fault_magnitude_m"], digits=2,
                 source_facts=["S_estimator_fixed_gain"],
                 note="Inference from the fixed gain: the estimate moves by gain x (GNSS - estimate) per fix.")

    # Divergence panel: no divergence instant is recorded; first recorded sample above a threshold.
    thresholds = [1, 3, 5, 10]
    div_metrics = [("err_h_host", "h"), ("err_z_host", "z")]
    div_ids = {}
    for sid_, key in div_metrics:
        vals = v(sid_)
        div_ids[sid_] = {}
        for th in thresholds:
            first = next((i for i, x in enumerate(vals) if abs(x) > th), None)
            nm = f"div.{key}.{th}.t_s"
            b.der_scalar(nm, f"First recorded sample with |{sid_}| above {th} m", "s", "first_sample_above",
                         None if first is None else t_vals[first], series_inputs=[sid_], digits=3,
                         at=first, params={"threshold": th})
            div_ids[sid_][str(th)] = nm
    idx["pre_fault_last"] = idx_fault_first - 1

    # R5 radius windows (first and last recorded sample inside; never an interpolated crossing)
    r5 = case["requirements"]["r5_position_m"]
    win_ids = {}
    for key, sid_ in (("true", "pad_distance_host"), ("believed", "believed_pad_distance")):
        vals = v(sid_)
        inside = [i for i, d_ in enumerate(vals) if d_ <= r5]
        runs = 0
        prev = False
        for i in range(n):
            cur = vals[i] <= r5
            runs += 1 if (cur and not prev) else 0
            prev = cur
        b.der_scalar(f"win.{key}.first_t", f"First recorded sample inside the R5 radius ({key})", "s", "first_inside_radius",
                     t_vals[inside[0]], series_inputs=[sid_], scalar_inputs=["case.r5_radius_m"], digits=3, at=inside[0])
        b.der_scalar(f"win.{key}.last_t", f"Last recorded sample inside the R5 radius ({key})", "s", "last_inside_radius",
                     t_vals[inside[-1]], series_inputs=[sid_], scalar_inputs=["case.r5_radius_m"], digits=3, at=inside[-1])
        b.der_scalar(f"win.{key}.runs", f"Separate stretches inside the R5 radius ({key})", "", "inside_radius_runs",
                     runs, series_inputs=[sid_], scalar_inputs=["case.r5_radius_m"], digits=0)
        k_min = min(range(n), key=lambda i: vals[i])
        b.der_scalar(f"win.{key}.min_m", f"Smallest recorded distance to the pad centre ({key})", "m", "min_over_samples",
                     vals[k_min], series_inputs=[sid_], digits=2, at=k_min)
        win_ids[key] = {"first": inside[0], "last": inside[-1]}
    b.der_scalar("td.believed_inside_r5", "Believed nozzle point is inside the R5 radius at the last estimate", "",
                 "inside_radius_at_touchdown", v("believed_pad_distance")[last] <= r5,
                 series_inputs=["believed_pad_distance"], scalar_inputs=["case.r5_radius_m"], at=last)
    b.der_scalar("td.true_inside_r5", "True nozzle point is inside the R5 radius at touchdown", "",
                 "inside_radius_at_touchdown", v("pad_distance_host")[last] <= r5,
                 series_inputs=["pad_distance_host"], scalar_inputs=["case.r5_radius_m"], at=last)

    # Which point each requirement judges (S fact) and a numeric check against the recorded touchdown
    td_truth = ver["touchdown"]["truth"]
    bv, bp = td_truth["base_velocity_mps"], td_truth["base_position_m"]
    req_by_id = {r["id"]: r for r in ver["requirements"]}
    checks = {
        "R1_vertical_speed": abs(bv[2]),
        "R2_horizontal_speed": math.hypot(bv[0], bv[1]),
        "R5_position": math.hypot(bp[0] - pad[0], bp[1] - pad[1]),
    }
    for rid, val in checks.items():
        ok = abs(val - req_by_id[rid]["value"]) < 1e-9
        b.der_scalar(f"check.{rid.split('_')[0]}_nozzle", f"{rid.split('_')[0]} equals the nozzle-plane quantity at touchdown", "",
                     "nozzle_reference_check", ok, source_facts=["S_requirements_nozzle"],
                     scalar_inputs=[f"req.{rid}.value"])
        for row in req_rows:
            if row["id"] == rid:
                row["reference"] = {"text": "nozzle plane", "check": f"check.{rid.split('_')[0]}_nozzle"}
    s2 = [r for r in ver["invariants"] if r["id"] == "S2_keep_out"][0]
    b.der_scalar("check.s2_equals_r5", "S2 worst value equals the R5 value", "", "equals_check",
                 s2["worst_value"] == req_by_id["R5_position"]["value"],
                 scalar_inputs=["inv.S2_keep_out.worst_value", "req.R5_position.value"], source_facts=["S_invariant_limits"])
    b.rec_scalar("prov.stored_parameters", "Parameters in the stored request", "", "D-host",
                 "record.json#/request/parameters", digits=0, reduce="len")

    # Build provenance: run's recorded source hash against the current tree
    cur_files = {rel: sha256_text_file(ROOT / ROCKET_DIR / rel) for rel in HASHED_FILES}
    differing = [rel for rel in HASHED_FILES if cur_files[rel] != RECORDING_FILE_SHA256[rel]]
    cur_hash = vv_rocket_source_sha256()
    b.der_scalar("prov.current_sha", "vv-rocket source hash of the current tree (same algorithm as the run's)", "",
                 "source_tree_sha256", cur_hash)
    b.der_scalar("prov.recording_commit", "Commit whose tree reproduces the run's source hash", "",
                 "pinned_recording_commit", RECORDING_COMMIT)
    b.der_scalar("prov.differing_files", "Hashed sources that differ between the recording tree and the current tree", "",
                 "source_tree_diff", ", ".join(differing) if differing else "none", scalar_inputs=["prov.recording_commit"])
    b.der_scalar("prov.hash_matches", "The current tree's source hash equals the run's", "", "equals_check",
                 cur_hash == run["source_sha256"], scalar_inputs=["prov.current_sha", "run.hash.source"])
    rocket_facts = [f for f in facts.values() if f["identical_to_recording"] is not None]
    b.der_scalar("prov.cited_sources_identical", "Every vv-rocket source cited by this view is identical to the recording tree", "",
                 "cited_sources_identical", all(f["identical_to_recording"] for f in rocket_facts))
    ev_file = ROOT / "docs/evidence/m19/belief-truth/iteration-2/cargo-earlier-build.txt"
    ev_line = next(ln for ln in ev_file.read_text(encoding="utf-8").splitlines() if ln.startswith("test result:"))
    b.der_scalar("prov.earlier_build_result", "Result line of the earlier-build replay test, from the evidence file", "",
                 "evidence_file_line", ev_line, params={"file": "docs/evidence/m19/belief-truth/iteration-2/cargo-earlier-build.txt",
                                                        "line_starts_with": "test result:"},
                 source_facts=["S_earlier_build_test"])
    b.rec_scalar("prov.current_domain_version", "Domain version the current tree reports", "", "S",
                 "domain.json#/version")

    # ---- events ----------------------------------------------------------------------------
    def nav(t):
        for i, tv in enumerate(t_vals):
            if tv >= t - 1e-9:
                return i
        return last

    def on_tick(t):
        return any(abs(tv - t) < 1e-9 for tv in t_vals)

    ev_defs = [
        ("ignition", "Ignition", "run.ignition_t_s", "T", "solid"),
        ("fault_start", "Fault starts: gnss_bias", "run.fault_start_event_t_s", "T", "dashed"),
        ("altimeter_rejected", "Controller detects the disagreement and rejects the altimeter (one condition)",
         "run.reject_first_t_s", "E", "dotted"),
        ("touchdown", "Touchdown: the nozzle plane reaches the ground", "run.touchdown_t_s", "D-host", "solid"),
    ]
    events = []
    for eid, label, sid, cls, dash in ev_defs:
        t = b.scalars[sid]["v"]
        i = nav(t)
        on = on_tick(t)
        events.append({
            "id": eid, "label": label, "t": sid, "cls": cls, "dash": dash,
            "short": {"ignition": "Ignition", "fault_start": "Fault starts", "altimeter_rejected": "Altimeter rejected",
                      "touchdown": "Touchdown"}[eid],
            "nav_index": i, "on_sample_tick": on,
            "between": None if on else [i - 1, i],
        })

    # Display digits per series (a view choice; the raw value stays in the entry).
    for sid, e in b.series.items():
        if sid in ("step",):
            e["digits"] = 0
        elif sid == "t_s":
            e["digits"] = 3
        elif sid.startswith(("truth_q_", "imu_q_")):
            e["digits"] = 6
        elif sid == "imu_nz":
            e["digits"] = 5
        elif sid == "s_cm":
            e["digits"] = 3
        elif sid == "prop_kg":
            e["digits"] = 1
        elif sid.startswith("cmd_gimbal"):
            e["digits"] = 4
        elif sid == "cmd_throttle":
            e["digits"] = 3
        elif e["unit"] in ("m", "m/s"):
            e["digits"] = 2

    # ---- views of the sample grid ----------------------------------------------------------
    return {
        "schema": SCHEMA,
        "generator": "spikes/m19-belief-truth/extract.py",
        "fixture": FIXTURE_REL,
        "inputs": inputs,
        "source_files": source_files,
        "extra_inputs": extra_inputs,
        "classes": CLASSES,
        "source_facts": facts,
        "derivations": DERIVATIONS | {
            "touchdown_sample_value": {
                "formula": "Value of the named series at the touchdown sample (the last sample), unchanged.",
                "approx": False},
            "touchdown_gap": {
                "formula": "hypot(true nozzle x - believed nozzle x, true nozzle y - believed nozzle y) at the "
                           "touchdown sample. The believed point is the last estimate before contact, approximate.",
                "approx": True},
            "ratio_of_steps": {"formula": "record_every_steps / control_period_steps.", "approx": False},
            "gnss_period": {"formula": "gnss_period_cycles * control period (control_period_steps * dt_s).", "approx": False},
            "count_where": {"formula": "Number of samples of the named series satisfying params.where "
                                       "(not null, null, true, or equal to a word).", "approx": False},
            "null_only_at_touchdown": {"formula": "True when the only null GNSS sample is the off-grid touchdown sample.",
                                       "approx": False},
            "flags_identical": {"formula": "True when the two recorded flag series are equal at every sample.",
                                "approx": False},
            "none_true": {"formula": "True when the recorded flag series is false at every sample.", "approx": False},
            "before": {"formula": "True when the first value is smaller than the second.", "approx": False},
            "fault_active_at_last_sample": {
                "formula": "True when the configured fault kind is in the recorded active_faults of the last sample.",
                "approx": False},
            "first_sample_above": {
                "formula": "t_s of the first recorded sample whose absolute value of the series exceeds params.threshold. "
                           "A recorded sample, never an interpolated crossing. Null when no sample exceeds it.",
                "approx": False},
            "first_inside_radius": {
                "formula": "t_s of the first recorded sample whose distance is at most the R5 radius.", "approx": False},
            "last_inside_radius": {
                "formula": "t_s of the last recorded sample whose distance is at most the R5 radius.", "approx": False},
            "inside_radius_runs": {
                "formula": "Number of separate stretches of consecutive samples at most the R5 radius.", "approx": False},
            "min_over_samples": {"formula": "Smallest recorded value of the series.", "approx": False},
            "inside_radius_at_touchdown": {
                "formula": "True when the series value at the touchdown sample is at most the R5 radius.", "approx": False},
            "nozzle_reference_check": {
                "formula": "True when the requirement's recorded value equals the nozzle-plane quantity in "
                           "verification.json touchdown.truth (R1: |base vz|; R2: horizontal base speed; R5: "
                           "base position distance to the pad).", "approx": False},
            "equals_check": {"formula": "True when the two recorded or derived values are equal.", "approx": False},
            "first_fix_jump": {
                "formula": "gnss_position_gain * bias magnitude: the step in the estimate caused by one GNSS fix "
                           "that carries the bias, when the estimate had been at the truth.", "approx": True},
            "count_keys": {"formula": "Number of entries.", "approx": False},
            "evidence_file_line": {
                "formula": "The first line starting with params.line_starts_with in the committed evidence file "
                           "params.file, written by running the test named by the source fact.", "approx": False},
            "source_tree_sha256": {
                "formula": "sha256 over the 20 vv-rocket hashed sources of the working tree, by the algorithm of "
                           "crates/vv-rocket/src/lib.rs source_sha256 (CRLF read as LF).", "approx": False},
            "pinned_recording_commit": {
                "formula": "Pinned in extract.py. The test proves with git that the tree at this commit reproduces "
                           "run.json source_sha256. It says the tree reproduces the hash, not that it built the run.",
                "approx": False},
            "source_tree_diff": {
                "formula": "Hashed sources whose per-file sha256 differs between the pinned recording tree and the "
                           "working tree.", "approx": False},
            "cited_sources_identical": {
                "formula": "True when every vv-rocket source cited as a source fact has the same per-file sha256 as "
                           "the recording tree.", "approx": False},
        },
        "provenance": {
            "recording_commit": RECORDING_COMMIT,
            "recording_file_sha256": RECORDING_FILE_SHA256,
            "current_file_sha256": cur_files,
            "differing": differing,
            "hashed_files": HASHED_FILES,
            "facts": ["S_replay_host_sdk", "S_earlier_build_test"],
        },
        "divergence": {"thresholds": thresholds, "metrics": [
            {"series": sid_, "scalars": div_ids[sid_]} for sid_, _ in div_metrics]},
        "windows": win_ids,
        "n_samples": n,
        "index": idx,
        "series": b.series,
        "scalars": b.scalars,
        "events": events,
        "requirements": req_rows,
        "invariants": inv_rows,
    }


_UNIT_DIGITS = {"m": 2, "m/s": 2, "rad/s": 4, "cos": 5, "kg": 1, "g0": 2, "ignitions": 0}


def _digits(r: dict, fld: str, default):
    if fld in ("value", "limit", "worst_value"):
        return _UNIT_DIGITS[r["unit"]]
    return default


def render(data: dict) -> bytes:
    text = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return (text + "\n").encode("utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, default=HERE / "data.json")
    ap.add_argument("--check", action="store_true", help="fail if the output file differs from a fresh extraction")
    args = ap.parse_args(argv)
    out = render(build())
    if args.check:
        if not args.output.exists() or args.output.read_bytes() != out:
            print("data.json is stale: run extract.py", file=sys.stderr)
            return 1
        print("data.json matches a fresh extraction")
        return 0
    with open(args.output, "wb") as fh:
        fh.write(out)
    print(f"wrote {args.output} ({len(out)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
