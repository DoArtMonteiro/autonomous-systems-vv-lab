"""M14 falsification benchmark: runs every strategy on every problem of one split, recomputes
every search, builds the exhaustive reference, checks parity with the canonical command lines
and applies the preregistered analysis (docs/m14-preregisto.md).

    python scripts/m14_benchmark.py --split development --output-root exec/out/m14-dev
    python scripts/m14_benchmark.py --freeze            # writes exec/benchmarks/m14/freeze.json
    python scripts/m14_benchmark.py --split heldout --output-root exec/out/m14-heldout

The held-out split refuses to run unless every frozen file still has its frozen sha256.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import m14_stats as st  # noqa: E402

BENCH = ROOT / "exec" / "benchmarks" / "m14" / "benchmark.json"
FREEZE = ROOT / "exec" / "benchmarks" / "m14" / "freeze.json"
EXE = ".exe" if os.name == "nt" else ""
FROZEN_FILES = [
    "exec/benchmarks/m14/benchmark.json",
    "scripts/m14_benchmark.py",
    "scripts/m14_stats.py",
    "scripts/m14_cases.py",
    "docs/m14-preregisto.md",
    "exec/src/search.rs",
    "exec/src/ground.rs",
    "exec/src/domain.rs",
    "exec/src/plan.rs",
    "exec/src/spec.rs",
    "exec/src/seeds.rs",
    "exec/Cargo.lock",
]
CLI = {
    "ground-m4": ROOT / "target" / "release" / f"vv-lab{EXE}",
    "rocket-landing": ROOT / "crates" / "vv-rocket" / "target" / "release" / f"vv-rocket{EXE}",
}
VV_EXEC = ROOT / "exec" / "target" / "release" / f"vv-exec{EXE}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen_paths() -> list[str]:
    bench = json.loads(BENCH.read_text(encoding="utf-8"))
    cases = sorted(
        {(BENCH.parent / p["base_case"]).resolve().relative_to(ROOT).as_posix() for p in bench["problems"]}
    )
    return FROZEN_FILES + cases


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def write_freeze() -> int:
    files = {p: sha256(ROOT / p) for p in frozen_paths()}
    dirty = git("status", "--porcelain", "--", *files)
    if dirty.strip():
        print("refusing to freeze: frozen files have uncommitted changes:\n" + dirty, file=sys.stderr)
        return 1
    doc = {
        "schema": "vv-m14-freeze.v1",
        "frozen_at_utc": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat(),
        "git_commit": git("rev-parse", "HEAD").strip(),
        "files": files,
    }
    FREEZE.write_text(json.dumps(doc, indent=2) + "\n", encoding="ascii", newline="\n")
    print(f"froze {len(files)} files at {doc['git_commit']}")
    return 0


def check_freeze() -> dict:
    if not FREEZE.exists():
        raise SystemExit("the held-out split needs exec/benchmarks/m14/freeze.json (run --freeze first)")
    doc = json.loads(FREEZE.read_text(encoding="ascii"))
    bad = [p for p, h in doc["files"].items() if not (ROOT / p).exists() or sha256(ROOT / p) != h]
    missing = sorted(set(frozen_paths()) - set(doc["files"]))
    if bad or missing:
        raise SystemExit(f"frozen files changed: {bad}; not frozen: {missing}")
    return doc


def run(args: list, timeout: int = 7200) -> subprocess.CompletedProcess:
    return subprocess.run([str(a) for a in args], capture_output=True, text=True, timeout=timeout)


def search_spec(bench: dict, problem: dict, split: dict, sid: str, strategy: dict, budget: int, reps: int, minimise: int) -> dict:
    domain = problem["domain"]
    return {
        "schema": "vv-search.v1",
        "id": sid,
        "description": f"M14 benchmark {problem['id']}, strategy {strategy['kind']}",
        "domain": domain,
        "base_case": str((BENCH.parent / problem["base_case"]).resolve()),
        "parameters": problem["parameters"],
        "seed_pool": split["seed_pool"],
        "target": bench["targets"][domain],
        "objective": bench["objectives"][domain],
        "strategy": strategy,
        "budget": budget,
        "repetitions": reps,
        "search_seed": split["search_seed"],
        "minimise_budget": minimise,
        "limits": {"max_evaluations": reps * (budget + 8 * minimise), "max_wall_s": 7200},
    }


def run_search(spec: dict, spec_dir: Path, out: Path, threads: int) -> dict:
    spec_dir.mkdir(parents=True, exist_ok=True)
    path = spec_dir / f"{spec['id']}.json"
    path.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8", newline="\n")
    r = run([VV_EXEC, "search", path, "--output", out, "--threads", threads])
    if r.returncode != 0:
        raise SystemExit(f"search {spec['id']} failed: {r.stderr.strip()}")
    v = run([VV_EXEC, "search-verify", out, "--threads", threads])
    try:
        verification = json.loads(v.stdout)
    except json.JSONDecodeError:
        verification = {"pass": False, "error": v.stderr.strip()}
    result = json.loads((out / "search.json").read_text(encoding="utf-8"))
    return {"result": result, "verification": verification}


def parity(problem: dict, split: dict, out: Path) -> dict:
    """Canonical command line against the in-process domain on a small factorial of the box."""
    spec = {
        "schema": "vv-experiment.v1",
        "id": f"m14-parity-{problem['id'].lower()}",
        "description": "M14 benchmark parity check of the in-process domain against its command line.",
        "domain": problem["domain"],
        "base_case": str((BENCH.parent / problem["base_case"]).resolve()),
        "parameters": problem["parameters"],
        "design": {"kind": "grid", "levels": 3},
        "seeds": {"mode": "list", "values": split["grid_seeds"][:2]},
        "retention": {"policy": "none", "sample_every": 0},
        "limits": {"max_runs": 200, "max_retained": 1, "max_artifact_bytes": 2_000_000_000, "max_wall_s": 3600},
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    path = out.parent / f"{spec['id']}.json"
    path.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8", newline="\n")
    r = run([VV_EXEC, "run", path, "--output", out])
    if r.returncode != 0:
        raise SystemExit(f"parity run {problem['id']} failed: {r.stderr.strip()}")
    e = run([VV_EXEC, "equiv", out, "--cli", CLI[problem["domain"]], "--sample", 8])
    eq = json.loads((out / "equivalence.json").read_text(encoding="utf-8"))
    return {
        "pass": eq["pass"],
        "cases": len(eq["cases"]),
        "differences": eq["differences"],
        "source_sha256_match": eq["source_sha256_match"],
        "exit": e.returncode,
    }


def properties(cls: str) -> set[str]:
    return set(cls.split("+")) if cls else set()


def analyse_problem(bench: dict, problem: dict, runs: dict, grid: dict) -> dict:
    budget = bench["budget"]
    d = len(problem["parameters"])
    grid_evals = [json.loads(line.split(" ", 1)[1]) for line in grid["log"].splitlines()]
    hits = [e for e in grid_evals if e["violated"]]
    grid_props = set().union(*[set(e["violations"]) for e in hits]) if hits else set()
    found_props: set[str] = set()
    for r in runs.values():
        for rep in r["result"]["repetitions"]:
            for c in rep["classes"]:
                found_props |= properties(c["class"])
    reference = sorted(grid_props | found_props)
    out = {
        "id": problem["id"],
        "split": problem["split"],
        "domain": problem["domain"],
        "parameters": [p["name"] for p in problem["parameters"]],
        "grid": {
            "evaluations": len(grid_evals),
            "violations": len(hits),
            "prevalence": len(hits) / len(grid_evals),
            "prevalence_ci95": st.clopper_pearson(len(hits), len(grid_evals)),
            "properties": sorted(grid_props),
            "verification_pass": grid["verification"].get("pass", False),
        },
        "reference_properties": reference,
        "properties_found_only_by_search": sorted(found_props - grid_props),
        "properties_found_only_by_grid": sorted(grid_props - found_props),
        "strategies": {},
    }
    for name, r in runs.items():
        reps = r["result"]["repetitions"]
        first = [rep["first_violation"] if rep["first_violation"] is not None else budget + 1 for rep in reps]
        found = sum(rep["first_violation"] is not None for rep in reps)
        recall = []
        devs = []
        for rep in reps:
            props = set().union(*[properties(c["class"]) for c in rep["classes"]]) if rep["classes"] else set()
            recall.append(len(props) / len(reference) if reference else 1.0)
            devs += [c["deviation_after"] for c in rep["classes"] if c["minimise_evaluations"] > 0]
        s = {
            "repetitions": len(reps),
            "with_violation": found,
            "with_violation_ci95": st.clopper_pearson(found, len(reps)),
            "first_violation": first,
            "first_violation_median": median(first),
            "first_at_evaluation_1": sum(f == 1 for f in first),
            "property_recall_mean": sum(recall) / len(recall),
            "property_recall_min": min(recall),
            "classes_per_repetition_mean": sum(len(rep["classes"]) for rep in reps) / len(reps),
            "minimised_deviation_median": median(devs) if devs else None,
            "evaluations": r["result"]["total_evaluations"],
            "wall_s": r["result"]["wall_s"],
            "verification_pass": r["verification"].get("pass", False),
            "verified_evaluations": r["verification"].get("evaluations"),
        }
        if name == "extremes":
            corners = 2**d + 1
            s["corners_and_centre"] = corners
            s["missed_by_corners_and_centre"] = sum(f > corners for f in first)
        out["strategies"][name] = s
    return out


def primary(bench: dict, problems: list[dict]) -> dict:
    """Preregistered primary analysis, held-out split only."""
    t, c = bench["primary"]["treatment"], bench["primary"]["control"]
    b = bench["bootstrap"]
    rows = []
    for p in problems:
        a = p["strategies"][t]
        r = p["strategies"][c]
        n = a["repetitions"]
        row = {"id": p["id"], "status": "eligible"}
        if not p["reference_properties"]:
            row["status"] = "excluded: no violation in the exhaustive reference or in any search (rule 2a)"
        elif a["first_at_evaluation_1"] > 0.9 * n and r["first_at_evaluation_1"] > 0.9 * n:
            row["status"] = "tie: more than 90 % of repetitions in both arms violate at evaluation 1 (rule 2b)"
        mw = st.mann_whitney(a["first_violation"], r["first_violation"])
        boot = st.bootstrap_median_difference(r["first_violation"], a["first_violation"], b["resamples"], b["seed"])
        row.update({"u": mw["u"], "z": mw["z"], "p": mw["p"], "median_control_minus_treatment": boot})
        rows.append(row)
    eligible = [x for x in rows if x["status"] == "eligible"]
    for x, adj in zip(eligible, st.holm([x["p"] for x in eligible])):
        x["p_holm"] = adj
        x["treatment_better"] = adj < bench["primary"]["alpha"] and x["median_control_minus_treatment"]["low"] > 0
        x["treatment_worse"] = adj < bench["primary"]["alpha"] and x["median_control_minus_treatment"]["high"] < 0
    better = sum(x.get("treatment_better", False) for x in eligible)
    worse = sum(x.get("treatment_worse", False) for x in eligible)
    return {
        "treatment": t,
        "control": c,
        "rows": rows,
        "eligible": len(eligible),
        "treatment_better": better,
        "treatment_worse": worse,
        "generalisation_claim": "supported" if better >= 3 and worse == 0 else "not supported",
    }


def markdown(report: dict) -> str:
    lines = [f"# Resultados do benchmark M14: divisão `{report['split']}`", ""]
    lines.append(
        f"Orçamento de {report['budget']} avaliações por repetição, {report['repetitions']} repetições por estratégia. "
        "Gerado por `scripts/m14_benchmark.py`; não editar à mão."
    )
    lines.append("")
    for p in report["problems"]:
        g = p["grid"]
        lo, hi = g["prevalence_ci95"]
        lines.append(f"## {p['id']}")
        lines.append("")
        lines.append(
            f"Referência exaustiva: {g['violations']} violações em {g['evaluations']} avaliações "
            f"(prevalência {g['prevalence']:.4f}, IC 95 % {lo:.4f} a {hi:.4f}). "
            f"Propriedades de referência: {', '.join(p['reference_properties']) or 'nenhuma'}. "
            f"Paridade com a linha de comandos: {'aprovada' if p['parity']['pass'] else 'REPROVADA'} "
            f"({p['parity']['cases']} casos, {p['parity']['differences']} diferenças)."
        )
        if p["properties_found_only_by_search"]:
            lines.append(f"Só a pesquisa encontrou: {', '.join(p['properties_found_only_by_search'])}.")
        if p["properties_found_only_by_grid"]:
            lines.append(f"Só a grelha encontrou: {', '.join(p['properties_found_only_by_grid'])}.")
        lines.append("")
        lines.append("| Estratégia | Repetições com violação | Mediana até à 1.ª violação | Revocação média de propriedades | Desvio mínimo mediano | Recalculada |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for name, s in p["strategies"].items():
            dev = "n/a" if s["minimised_deviation_median"] is None else f"{s['minimised_deviation_median']:.3f}"
            lines.append(
                f"| {name} | {s['with_violation']}/{s['repetitions']} | {s['first_violation_median']} | "
                f"{s['property_recall_mean']:.2f} | {dev} | {'sim' if s['verification_pass'] else 'NÃO'} |"
            )
        ex = p["strategies"].get("extremes")
        if ex:
            lines.append("")
            lines.append(
                f"Cantos e centro ({ex['corners_and_centre']} avaliações) sem violação em "
                f"{ex['missed_by_corners_and_centre']} de {ex['repetitions']} repetições."
            )
        lines.append("")
    if report.get("primary"):
        pr = report["primary"]
        lines.append("## Análise primária (pré-registada)")
        lines.append("")
        lines.append("| Problema | Estado | p (Mann-Whitney) | p Holm | Mediana controlo menos tratamento [IC 95 %] |")
        lines.append("| --- | --- | --- | --- | --- |")
        for x in pr["rows"]:
            m = x["median_control_minus_treatment"]
            ph = f"{x['p_holm']:.4f}" if "p_holm" in x else "n/a"
            lines.append(f"| {x['id']} | {x['status']} | {x['p']:.4f} | {ph} | {m['difference']} [{m['low']}; {m['high']}] |")
        lines.append("")
        lines.append(
            f"Alegação de generalização ({pr['treatment']} contra {pr['control']}): **{pr['generalisation_claim']}** "
            f"({pr['treatment_better']} melhores, {pr['treatment_worse']} piores, {pr['eligible']} elegíveis)."
        )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--split", choices=["development", "heldout"])
    ap.add_argument("--output-root", type=Path)
    ap.add_argument("--threads", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--freeze", action="store_true")
    args = ap.parse_args()
    if args.freeze:
        return write_freeze()
    if not args.split or not args.output_root:
        ap.error("--split and --output-root are required")
    freeze = check_freeze() if args.split == "heldout" else None
    for exe in [VV_EXEC, *CLI.values()]:
        if not exe.exists():
            raise SystemExit(f"missing binary {exe}; build vv-exec, vv-lab and vv-rocket in release")
    bench = json.loads(BENCH.read_text(encoding="utf-8"))
    split = bench["splits"][args.split]
    root = args.output_root.resolve()
    if root.exists():
        raise SystemExit(f"{root} already exists; every benchmark run writes a fresh directory")
    problems = [p for p in bench["problems"] if p["split"] == args.split]
    # Preflight: every specification of the split must pass validation before any simulation runs.
    for problem in problems:
        for name, strategy in bench["strategies"].items():
            spec = search_spec(bench, problem, split, f"{problem['id']}-{name}", strategy, bench["budget"], bench["repetitions"], bench["minimise_budget"])
            spec_dir = root.parent / f".{root.name}-preflight"
            spec_dir.mkdir(parents=True, exist_ok=True)
            path = spec_dir / f"{spec['id']}.json"
            path.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8", newline="\n")
            c = run([VV_EXEC, "search-check", path])
            if c.returncode != 0:
                raise SystemExit(f"preflight refused {spec['id']}: {c.stderr.strip()}")
    analysed = []
    for problem in problems:
        pdir = root / problem["id"]
        runs = {}
        for name, strategy in bench["strategies"].items():
            spec = search_spec(bench, problem, split, f"{problem['id']}-{name}", strategy, bench["budget"], bench["repetitions"], bench["minimise_budget"])
            runs[name] = run_search(spec, root / "specs", pdir / name, args.threads)
            hits = sum(r["first_violation"] is not None for r in runs[name]["result"]["repetitions"])
            print(f"{problem['id']} {name}: {hits}/{bench['repetitions']} with a violation, verified={runs[name]['verification'].get('pass')}", flush=True)
        levels, seeds = problem["grid_levels"], split["grid_seeds"]
        gbudget = levels ** len(problem["parameters"]) * len(seeds)
        gspec = search_spec(bench, problem, split, f"{problem['id']}-grid", {"kind": "grid", "levels": levels, "seeds": seeds}, gbudget, 1, 0)
        grid = run_search(gspec, root / "specs", pdir / "grid", args.threads)
        grid["log"] = (pdir / "grid" / "evaluations.jsonl").read_text(encoding="utf-8")
        a = analyse_problem(bench, problem, runs, grid)
        a["parity"] = parity(problem, split, pdir / "parity")
        analysed.append(a)
        print(f"{problem['id']} grid prevalence {a['grid']['prevalence']:.4f}, parity {a['parity']['pass']}", flush=True)
    report = {
        "schema": "vv-m14-benchmark-result.v1",
        "split": args.split,
        "budget": bench["budget"],
        "repetitions": bench["repetitions"],
        "benchmark_sha256": sha256(BENCH),
        "vv_exec_sha256": sha256(VV_EXEC),
        "git_commit": git("rev-parse", "HEAD").strip(),
        "freeze": freeze,
        "problems": analysed,
        "all_searches_verified": all(s["verification_pass"] for p in analysed for s in p["strategies"].values())
        and all(p["grid"]["verification_pass"] for p in analysed),
        "all_parity_pass": all(p["parity"]["pass"] for p in analysed),
    }
    if args.split == "heldout":
        report["primary"] = primary(bench, analysed)
    (root / "results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    (root / "results.md").write_text(markdown(report), encoding="utf-8", newline="\n")
    print(markdown(report))
    return 0 if report["all_searches_verified"] and report["all_parity_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
