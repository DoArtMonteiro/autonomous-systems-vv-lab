"""Executa as etapas 0 a 5 do pré-registo da reformulação do M10 (`docs/m10-redesign-preregistration.md`).

Sementes de desenvolvimento 5000 a 5099 apenas; os scripts chamados recusam as protegidas. Um só
binário em todas as etapas. Todas as etapas correm, mesmo que uma cláusula de paragem dispare.

    python scripts/m10_redesign_run.py --binary <vv-rocket> --root runs/m10-redesign
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import m10_campaign as camp  # noqa: E402

NOISE_KEYS = ("altimeter_sigma_m", "gnss_position_sigma_m", "gnss_velocity_sigma_mps", "imu_accel_sigma_mps2")
F3 = ",".join(camp.FAMILIES["F3"])
F2_ISO = "gnss_coherent_ramp,altimeter_stuck,altimeter_delay,altimeter_outliers"
MAX_RUNS = 45_000


def templates(root: Path) -> dict[str, Path]:
    base, _ = camp.load_template()
    out: dict[str, Path] = {}
    for name, gate, noise in (("off", False, False), ("gate", True, False), ("off15", False, True), ("gate15", True, True)):
        t = copy.deepcopy(base)
        if gate:
            t["controller"]["nav"]["ambiguity_gate"] = True
        if noise:
            for k in NOISE_KEYS:
                t["sensors"][k] = t["sensors"][k] * 1.5
        if name == "off":
            out[name] = camp.TEMPLATE  # the committed template, byte for byte
            continue
        path = root / f"template-{name}.json"
        path.write_text(json.dumps(t, indent=2) + "\n", encoding="utf-8")
        out[name] = path
    return out


def run(cmd: list[str], log: Path) -> float:
    started = time.monotonic()
    p = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = time.monotonic() - started
    with log.open("a", encoding="utf-8") as f:
        f.write(f"$ {' '.join(cmd)}\nexit {p.returncode} {elapsed:.1f} s\n{p.stdout[-600:]}\n{p.stderr[-600:]}\n")
    if p.returncode != 0:
        raise SystemExit(f"command failed ({p.returncode}): {' '.join(cmd)}\n{p.stderr[-400:]}")
    return elapsed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", type=Path, required=True)
    ap.add_argument("--root", type=Path, default=ROOT / "runs" / "m10-redesign")
    ap.add_argument("--stages", default="0,1,2,3,3b,4,5")
    a = ap.parse_args()
    root = a.root
    root.mkdir(parents=True, exist_ok=True)
    log = root / "stages.log"
    binary = str(a.binary)
    tpl = templates(root)
    py = sys.executable
    campaign = [py, "-X", "utf8", str(ROOT / "scripts/m10_campaign.py"), "--binary", binary, "--seeds", "5000-5099", "--jobs", "8"]
    probe = [py, "-X", "utf8", str(ROOT / "scripts/m10_adversarial_probe.py")]
    stages = a.stages.split(",")
    runs = 0

    def camp_run(name: str, scenarios: str, arm: str, template: str) -> None:
        run(campaign + ["--scenarios", scenarios, "--arms", arm, "--template", str(tpl[template]),
                        "--output-root", str(root / name)], log)

    def probe_run(name: str, plan: str, arm: str, seeds: str) -> None:
        run(probe + [plan, "--binary", binary, "--seeds", seeds, "--arms", arm, "--output", str(root / f"{name}.json")], log)

    arms_main = (("B", "m10_b", "off"), ("B+", "m10_b_plus", "off"), ("B+G", "m10_b_plus", "gate"))
    if "0" in stages:
        camp_run("stage0-bplus", f"{F3},{F2_ISO}", "m10_b_plus", "off")
        camp_run("stage0-b", F2_ISO, "m10_b", "off")
        runs += 1400
    if "1" in stages:
        for label, _, _ in arms_main:
            probe_run(f"stage1-ramps-{label}", "ramps", label, "5020-5059")
            runs += 2560
    if "2" in stages:
        for label, policy, t in (*arms_main, ("robust", "robust", "off"), ("guarded", "guarded", "off")):
            camp_run(f"stage2-{label}", "F1,F2,F3", policy, t)
            runs += 2400
    if "3" in stages:
        for label, policy, t in arms_main:
            camp_run(f"stage3-{label}", "F1,F2,F3", policy, t + "15")
            runs += 2400
    if "2g" in stages:  # B+G again, with the gate streaks in the records (same classes, checked in the analysis)
        camp_run("stage2-B+G-gate", "F1,F2,F3", "m10_b_plus", "gate")
        runs += 2400
    if "3g" in stages:
        camp_run("stage3-B+G-gate", "F1,F2,F3", "m10_b_plus", "gate15")
        runs += 2400
    if "3b" in stages:
        for label, _, _ in arms_main:
            probe_run(f"stage3b-ramps15-{label}", "ramps15", label, "5020-5039")
            runs += 640
    if "4" in stages:
        for label in ("B", "B+", "B+G", "robust", "guarded"):
            probe_run(f"stage4-onset-{label}", "onset", label, "5020-5039")
            runs += 1900
    if "5" in stages:
        for label in ("robust", "guarded"):
            probe_run(f"stage5-ramps-{label}", "ramps", label, "5020-5059")
            runs += 2560
    if runs > MAX_RUNS:
        raise SystemExit(f"{runs} runs above the cap {MAX_RUNS}")
    sha = hashlib.sha256(a.binary.read_bytes()).hexdigest()
    (root / "run-info.json").write_text(json.dumps({"binary_sha256": sha, "stages": stages, "runs": runs,
                                                    "templates": {k: hashlib.sha256(v.read_bytes()).hexdigest() for k, v in tpl.items()}},
                                                   indent=2), encoding="utf-8")
    print("runs", runs, "binary", sha)
    return 0


if __name__ == "__main__":
    sys.exit(main())
