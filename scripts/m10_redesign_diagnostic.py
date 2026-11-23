"""Diagnóstico do pré-registo da reformulação do M10 (sementes de desenvolvimento 5000-5099 apenas).

Repete a parte de `rampbase` a 0,5 m/s (início 4,5; 6; 8; 10 s) com os braços B e B+ e decompõe os U
de B+ por veredicto de isolamento, requisito e invariante falhados. Reutiliza a sonda da revisão
independente (`m10_adversarial_probe`), que recusa sementes fora de 5000-5099 e as protegidas.

    python scripts/m10_redesign_diagnostic.py run --binary <vv-rocket> --output <registos.json>
    python scripts/m10_redesign_diagnostic.py summary <registos.json>
"""

from __future__ import annotations

import argparse
import collections
import copy
import json
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import m10_adversarial_probe as probe  # noqa: E402

camp = probe.camp
ARMS = ("m10_b", "m10_b_plus")
MAX_RUNS = 400


def planned(seeds):
    jobs = [j for j in probe.jobs_for("rampbase") if j[1] in ARMS and "ramp0.5@" in j[3]]
    return [(j, s) for j in jobs for s in seeds]


def run_all(binary: Path, seeds, jobs: int):
    probe.guard(list(seeds))
    plan = planned(seeds)
    if len(plan) > MAX_RUNS:
        raise SystemExit(f"plan has {len(plan)} runs; the limit is {MAX_RUNS}")
    approved, _ = camp.load_template(ROOT / "crates/vv-rocket/landing/m10-nominal.json")
    with tempfile.TemporaryDirectory(prefix="m10-diag-") as tmp:
        work = Path(tmp)

        def one(item):
            (tpl, arm, faults, tag), seed = item
            rec = probe.run(binary, copy.deepcopy(approved), arm, faults, seed, work, f"{tpl}~{tag}")
            rec["onset"] = faults[0]["start_s"]
            rec["magnitude"] = faults[0]["magnitude"]
            rec["class"] = probe.physical_class(rec)
            return rec

        with ThreadPoolExecutor(max_workers=max(1, min(jobs, 16))) as pool:
            return list(pool.map(one, plan))


def decompose(recs):
    out = []
    for arm in ARMS:
        rs = [r for r in recs if r["arm"] == arm]
        cls = collections.Counter(r["class"] for r in rs)
        out.append(f"{arm}: n={len(rs)} {dict(sorted(cls.items()))}")
        us = [r for r in rs if r["class"] == "U"]
        by_iso = collections.Counter(r["iso"] or "n/a" for r in us)
        out.append(f"  U por veredicto de isolamento: {dict(sorted(by_iso.items()))}")
        out.append(f"  U com falha hv: {sum(bool(r['af']['horizontal_velocity']) for r in us)}; "
                   f"vertical: {sum(bool(r['af']['vertical']) for r in us)}; "
                   f"posição horizontal: {sum(bool(r['af']['horizontal_position']) for r in us)}")
        req = collections.Counter(k for r in us for k in r["fail"])
        out.append(f"  U por requisito falhado (um U conta em todos os que falha): {dict(sorted(req.items()))}")
        sig = collections.Counter(tuple(sorted(r["fail"])) for r in us)
        out.append(f"  U por conjunto de requisitos falhados: "
                   f"{ {','.join(k) or '-': v for k, v in sorted(sig.items(), key=lambda kv: -kv[1])} }")
        inv = collections.Counter(i for r in us for i in r["inv_fail"])
        out.append(f"  U por invariante falhado: {dict(sorted(inv.items()))}; execuções U com invariante: "
                   f"{sum(bool(r['inv_fail']) for r in us)}")
        out.append(f"  U com transição insegura: {sum(bool(r['unsafe_tr']) for r in us)}")
        delays = []
        for r in us:
            for e in r.get("iso_ev") or []:
                delays.append(round(e["t_s"] - r["onset"], 2))
        out.append(f"  atraso do isolamento depois do início nos U (s): {sorted(delays)}")
        for onset in sorted({r["onset"] for r in rs}):
            sub = [r for r in rs if r["onset"] == onset]
            c = collections.Counter(r["class"] for r in sub)
            i = collections.Counter(r["iso"] or "n/a" for r in sub)
            out.append(f"  início {onset}: classes {dict(sorted(c.items()))}; isolamento {dict(sorted(i.items()))}")
        out.append("")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("mode", choices=("run", "summary"))
    ap.add_argument("path", nargs="?")
    ap.add_argument("--binary", type=Path)
    ap.add_argument("--output", type=Path)
    ap.add_argument("--seeds", default="5000-5019")
    ap.add_argument("--jobs", type=int, default=8)
    a = ap.parse_args()
    if a.mode == "summary":
        print(decompose(json.loads(Path(a.path).read_text(encoding="utf-8"))["records"]))
        return 0
    seeds = camp.parse_seeds(a.seeds)
    recs = run_all(a.binary, seeds, a.jobs)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps({"seeds": a.seeds, "records": recs}, separators=(",", ":")), encoding="utf-8")
    print(len(recs), "runs ->", a.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
