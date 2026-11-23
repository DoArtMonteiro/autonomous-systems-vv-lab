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
SCHEMA = "m19-belief-truth-data.v1"

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
    def rec_scalar(self, sid, label, unit, cls, ptr, *, digits=None, note=None):
        entry = {"label": label, "unit": unit, "cls": cls, "ptr": ptr, "v": resolve(self.docs, ptr)}
        if digits is not None:
            entry["digits"] = digits
        if note:
            entry["note"] = note
        self.scalars[sid] = entry

    def der_scalar(self, sid, label, unit, name, v, *, series_inputs=(), scalar_inputs=(), cls="D-view",
                   digits=None, note=None, source_facts=None, at=None):
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
    source_files = {rel: sha256_bytes((ROOT / rel).read_bytes()) for rel in SOURCES}

    facts = {}
    for f in SOURCE_FACTS:
        facts[f["id"]] = {
            "file": f["file"],
            "lines": line_range(f["file"], f["anchors"]),
            "anchors": f["anchors"],
            "claim": f["claim"],
            "cls": "S",
        }

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
    b.rec_scalar("run.seed", "Seed", "", "T", "run.json#/seed", digits=0)
    b.rec_scalar("run.policy", "Controller policy", "", "C", "run.json#/policy")
    b.rec_scalar("run.fault_kind", "Fault kind", "", "C", "case.json#/faults/0/kind")
    b.rec_scalar("run.domain", "Domain", "", "T", "record.json#/domain/id")
    b.rec_scalar("run.version", "Recording domain build", "", "T", "record.json#/domain/version")
    b.rec_scalar("run.sample_interval_s", "Trace sampling interval", "s", "D-host", "record.json#/scene/sample_interval_s", digits=1)
    b.rec_scalar("run.verdict_note", "Host note on sampling and verdicts", "", "D-host", "record.json#/notes/2")
    b.rec_scalar("run.model_validity", "Model validity statement", "", "D-host", "record.json#/model_validity")
    b.rec_scalar("run.hash.source", "run.json source_sha256", "", "T", "run.json#/source_sha256")
    b.rec_scalar("run.hash.case", "run.json case sha256", "", "T", "run.json#/case/sha256")
    b.rec_scalar("run.hash.trace", "run.json trace sha256", "", "T", "run.json#/trace/sha256")
    b.rec_scalar("run.hash.verification", "run.json verification sha256", "", "T", "run.json#/verification/sha256")
    b.rec_scalar("run.outcome_code", "Outcome code", "", "D-host", "verification.json#/outcome")
    b.rec_scalar("run.outcome_label", "Outcome label", "", "D-host", "record.json#/outcome/label")
    b.rec_scalar("run.outcome_explanation", "Outcome explanation", "", "D-host", "record.json#/outcome/explanation")
    b.rec_scalar("run.requirements_pass", "Mission requirements pass", "", "D-host", "verification.json#/requirements_pass")
    b.rec_scalar("run.invariants_pass", "Safety invariants pass", "", "D-host", "verification.json#/invariants_pass")
    b.rec_scalar("run.steps", "Steps simulated", "", "T", "run.json#/summary/steps", digits=0)
    b.rec_scalar("run.ignition_t_s", "Ignition", "s", "T", "trace.json#/events/0/t_s", digits=1)
    b.rec_scalar("run.fault_start_event_t_s", "Fault start event", "s", "T", "trace.json#/events/1/t_s", digits=1)
    b.rec_scalar("run.touchdown_t_s", "Touchdown time", "s", "D-host", "trace.json#/events/2/t_s", digits=3,
                 note="Interpolated by the host between two steps (S_touchdown_sample).")
    b.rec_scalar("run.touchdown_step", "Touchdown step", "", "D-host", "trace.json#/events/2/step", digits=0)
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
                     [e - t for e, t in zip(v(f"est_{ax}"), v(f"truth_{ax}"))], ref="centre of mass",
                     cls_by_index=td_override)
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
        ("altimeter_rejected", "Controller first rejects the altimeter", "run.reject_first_t_s", "E", "dotted"),
        ("touchdown", "Touchdown: the nozzle plane reaches the ground", "run.touchdown_t_s", "D-host", "solid"),
    ]
    events = []
    for eid, label, sid, cls, dash in ev_defs:
        t = b.scalars[sid]["v"]
        i = nav(t)
        on = on_tick(t)
        events.append({
            "id": eid, "label": label, "t": sid, "cls": cls, "dash": dash,
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
        elif e["unit"] == "m":
            e["digits"] = 2

    # ---- views of the sample grid ----------------------------------------------------------
    return {
        "schema": SCHEMA,
        "generator": "spikes/m19-belief-truth/extract.py",
        "fixture": FIXTURE_REL,
        "inputs": inputs,
        "source_files": source_files,
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
        },
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
