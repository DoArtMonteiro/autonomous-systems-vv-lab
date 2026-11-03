"""M14 assumption-fragility study (exploratory, development seeds).

For a claim "the pass rate is at least P0" and one assumption axis, every level of the axis runs
N seeds through `vv-exec run`. Each level gets a verdict from one-sided 95 % Clopper-Pearson
bounds: `holds` when the lower bound is at least P0, `refuted` when the upper bound is below P0,
`inconclusive` otherwise. The robustness margin is the interval between the last level that holds,
counting from the nominal end, and the first level that is refuted. A claim whose verdicts come
back after a refutation is flagged non-monotone: a test of the end points alone would mislead.

    python scripts/m14_fragility.py --output-root exec/out/m14-fragility
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import m14_stats as st  # noqa: E402

EXE = ".exe" if os.name == "nt" else ""
VV_EXEC = ROOT / "exec" / "target" / "release" / f"vv-exec{EXE}"
P0 = 0.95
SEEDS = {"first": 32000, "count": 100}
CASES = ROOT / "exec" / "cases" / "m14"

# id, statement, domain, case, verdict field, axis (name, pointer, unit, low, high, levels, integer)
CLAIMS = [
    ("F1", "Corredor junto à zona: o veículo não viola a segurança", "ground-m4", CASES / "ground-zone-corridor.json", "invariants_pass",
     ("ruído GPS", "/scenario/sensors/gps/noise_max_mm", "mm", 0, 10, 11, True)),
    ("F2", "Corredor junto à zona: o veículo não viola a segurança", "ground-m4", CASES / "ground-zone-corridor.json", "invariants_pass",
     ("atraso máximo de observação", "/scenario/sensors/communication/delay_max_ticks", "ticks", 0, 3, 4, True)),
    ("F3", "Paragem nominal: o veículo não viola a segurança", "ground-m4", CASES / "ground-nominal-stop.json", "invariants_pass",
     ("ruído GPS", "/scenario/sensors/gps/noise_max_mm", "mm", 0, 200, 11, True)),
    ("F4", "Paragem nominal: o veículo não viola a segurança", "ground-m4", CASES / "ground-nominal-stop.json", "invariants_pass",
     ("atraso máximo de observação", "/scenario/sensors/communication/delay_max_ticks", "ticks", 0, 3, 4, True)),
    ("F5", "M9.1 guarded: aterra e cumpre todos os requisitos", "rocket-landing", CASES / "rocket-imu-accel-bias.json", "all_pass",
     ("viés do acelerómetro a partir de 5 s", "/faults/0/magnitude", "model", 0.05, 0.5, 10, False)),
    ("F6", "M9.1 guarded: aterra e cumpre todos os requisitos", "rocket-landing", CASES / "rocket-gnss-bias.json", "all_pass",
     ("viés GNSS a partir de 5 s", "/faults/0/magnitude", "model", 5.0, 30.0, 11, False)),
    ("F7", "M9.1 guarded: aterra e cumpre todos os requisitos", "rocket-landing", CASES / "rocket-thrust-loss.json", "all_pass",
     ("perda de impulso a partir de 5 s", "/faults/0/magnitude", "model", 0.05, 0.30, 11, False)),
]


def run_claim(claim: tuple, out: Path) -> dict:
    cid, statement, domain, case, field, (axis, pointer, unit, low, high, levels, integer) = claim
    param = {"name": "axis", "pointer": pointer, "unit": unit, "low": low, "high": high}
    if integer:
        param["integer"] = True
    spec = {
        "schema": "vv-experiment.v1",
        "id": f"m14-fragility-{cid.lower()}",
        "description": f"M14 fragility {cid}. Exploratory, development seeds.",
        "domain": domain,
        "base_case": str(case),
        "parameters": [param],
        "design": {"kind": "grid", "levels": levels},
        "seeds": {"mode": "range", **SEEDS},
        "retention": {"policy": "none", "sample_every": 0},
        "limits": {"max_runs": levels * SEEDS["count"], "max_retained": 1, "max_artifact_bytes": 1_000_000, "max_wall_s": 3600},
    }
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{spec['id']}.json"
    path.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8", newline="\n")
    run_dir = out / cid
    r = subprocess.run([str(VV_EXEC), "run", str(path), "--output", str(run_dir)], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"{cid}: {r.stderr.strip()}")
    v = subprocess.run([str(VV_EXEC), "verify", str(run_dir)], capture_output=True, text=True)
    try:
        verified = json.loads(v.stdout)["pass"]
    except (json.JSONDecodeError, KeyError):
        verified = False
    plan = json.loads((run_dir / "plan.json").read_text(encoding="utf-8"))
    records = [json.loads(line.split(" ", 1)[1]) for line in (run_dir / "records.jsonl").read_text(encoding="utf-8").splitlines()]
    step = (high - low) / (levels - 1)
    rows = []
    for cell in range(levels):
        recs = [x for x in records if x["cell"] == cell]
        n = len(recs)
        k = sum(x[field] is True for x in recs)
        errors = sum(x["error"] is not None for x in recs)
        lo, hi = st.one_sided_lower(k, n), st.one_sided_upper(k, n)
        verdict = "holds" if lo >= P0 else "refuted" if hi < P0 else "inconclusive"
        value = low + cell * step
        rows.append({"value": round(value) if integer else round(value, 6), "n": n, "pass": k, "errors": errors, "lower": lo, "upper": hi, "verdict": verdict})
    first_refuted = next((i for i, x in enumerate(rows) if x["verdict"] == "refuted"), None)
    last_hold = None
    for i, x in enumerate(rows[: first_refuted if first_refuted is not None else len(rows)]):
        if x["verdict"] == "holds":
            last_hold = i
    later_hold = first_refuted is not None and any(x["verdict"] == "holds" for x in rows[first_refuted + 1 :])
    rates = [x["pass"] / x["n"] for x in rows]
    rises = any(rates[i + 1] > rates[i] + 0.05 for i in range(len(rates) - 1))
    return {
        "id": cid,
        "claim": f"{statement}, com probabilidade de pelo menos {P0}",
        "domain": domain,
        "case": case.relative_to(ROOT).as_posix(),
        "axis": axis,
        "unit": unit,
        "levels": rows,
        "margin": {
            "last_holding_value": None if last_hold is None else rows[last_hold]["value"],
            "first_refuted_value": None if first_refuted is None else rows[first_refuted]["value"],
        },
        "nominal_holds": rows[0]["verdict"] == "holds",
        "non_monotone": later_hold or rises,
        "plan_sha256": plan["plan_sha256"],
        "verified": verified,
    }


ONSET_SPEC = ROOT / "exec" / "examples" / "m14-gnss-bias-onset.json"


def run_onset(out: Path) -> dict:
    """GNSS bias onset study: the M9.1 G3 criterion was registered with the bias from 0 s."""
    run_dir = out / "onset"
    r = subprocess.run([str(VV_EXEC), "run", str(ONSET_SPEC), "--output", str(run_dir)], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"onset: {r.stderr.strip()}")
    v = subprocess.run([str(VV_EXEC), "verify", str(run_dir)], capture_output=True, text=True)
    try:
        verified = json.loads(v.stdout)["pass"]
    except (json.JSONDecodeError, KeyError):
        verified = False
    plan = json.loads((run_dir / "plan.json").read_text(encoding="utf-8"))
    spec = json.loads(ONSET_SPEC.read_text(encoding="utf-8"))
    p = spec["parameters"][0]
    levels = spec["design"]["levels"]
    mags = [p["low"] + i * (p["high"] - p["low"]) / (levels - 1) for i in range(levels)]
    records = [json.loads(line.split(" ", 1)[1]) for line in (run_dir / "records.jsonl").read_text(encoding="utf-8").splitlines()]
    limit = 3.0  # R1 of crates/vv-rocket/landing/m91-nominal.json: |v_z| at contact at most 3 m/s
    rows = []
    for a, arm in enumerate(plan["arms"]):
        for c, m in enumerate(mags):
            rs = [x for x in records if x["arm"] == a and x["cell"] == c]
            r1 = sum(x["metrics"].get("requirement.R1_vertical_speed", float("inf")) <= limit for x in rs)
            landed = sum(x["outcome"] == "landed" for x in rs)
            rows.append({"arm": arm, "magnitude_m": m, "n": len(rs), "r1_pass": r1, "landed": landed})
    return {"spec": ONSET_SPEC.relative_to(ROOT).as_posix(), "plan_sha256": plan["plan_sha256"], "verified": verified, "rows": rows}


def markdown(report: dict) -> str:
    lines = ["# Fragilidade de pressupostos do M14 (exploratório)", ""]
    lines.append(
        f"Cada nível corre {SEEDS['count']} sementes de desenvolvimento ({SEEDS['first']} a {SEEDS['first'] + SEEDS['count'] - 1}). "
        f"Veredicto por nível com limites unilaterais de Clopper-Pearson a 95 % contra {P0}. "
        "Gerado por `scripts/m14_fragility.py`; não editar à mão."
    )
    lines.append("")
    for c in report["claims"]:
        m = c["margin"]
        lines.append(f"## {c['id']}: {c['axis']}")
        lines.append("")
        lines.append(f"Alegação: {c['claim']}. Caso `{c['case']}`. Recalculado: {'sim' if c['verified'] else 'NÃO'}.")
        lines.append(
            f"Margem: último nível que se mantém {m['last_holding_value']} {c['unit']}; primeiro refutado {m['first_refuted_value']} {c['unit']}. "
            f"Não monótona: {'sim' if c['non_monotone'] else 'não'}."
        )
        lines.append("")
        lines.append(f"| {c['axis']} ({c['unit']}) | Passam | Limite inferior | Limite superior | Veredicto |")
        lines.append("| --- | --- | --- | --- | --- |")
        for x in c["levels"]:
            lines.append(f"| {x['value']} | {x['pass']}/{x['n']} | {x['lower']:.3f} | {x['upper']:.3f} | {x['verdict']} |")
        lines.append("")
    o = report["onset"]
    lines.append("## Início do viés GNSS e o critério G3 do M9.1")
    lines.append("")
    lines.append(f"Especificação `{o['spec']}`. Recalculado: {'sim' if o['verified'] else 'NÃO'}. O G3 foi registado com o viés presente desde 0 s.")
    lines.append("")
    lines.append("| Início | Magnitude (m) | R1 cumprido | Aterra |")
    lines.append("| --- | --- | --- | --- |")
    for x in o["rows"]:
        lines.append(f"| {x['arm']} | {x['magnitude_m']:g} | {x['r1_pass']}/{x['n']} | {x['landed']}/{x['n']} |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--output-root", type=Path, required=True)
    args = ap.parse_args()
    root = args.output_root.resolve()
    if root.exists():
        raise SystemExit(f"{root} already exists")
    report = {"schema": "vv-m14-fragility.v1", "p0": P0, "seeds": SEEDS, "claims": [run_claim(c, root) for c in CLAIMS]}
    report["onset"] = run_onset(root)
    report["all_verified"] = all(c["verified"] for c in report["claims"]) and report["onset"]["verified"]
    (root / "fragility.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    (root / "fragility.md").write_text(markdown(report), encoding="utf-8", newline="\n")
    return 0 if report["all_verified"] else 1


if __name__ == "__main__":
    sys.exit(main())
