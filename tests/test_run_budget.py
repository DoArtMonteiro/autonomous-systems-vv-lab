"""Orçamento de execuções: limite acumulado, concorrência, manifesto registado em commit, sementes e contagem."""

from __future__ import annotations

import ast
import json
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_budget as rb  # noqa: E402

CAMPAIGN = "demo-campaign"

# Cada processo reserva um bloco depois de um instante comum, para que as tentativas colidam.
RESERVE_CHILD = """
import json, sys, time
sys.path.insert(0, sys.argv[1])
import run_budget as rb
repo, ledger, start, n = sys.argv[2], sys.argv[3], float(sys.argv[4]), int(sys.argv[5])
while time.time() < start:
    time.sleep(0.001)
try:
    r = rb.reserve("demo-campaign", [5000 + i for i in range(n)], "race", repo=repo, ledger_dir=ledger)
    print(json.dumps({"ok": True, "total": r.total_after}))
except rb.BudgetExceeded as error:
    print(json.dumps({"ok": False}))
"""


def manifest_data(max_runs: int = 10, allowed=((5000, 5099),), amendments=None) -> dict:
    data = {
        "schema": rb.MANIFEST_SCHEMA, "campaign_id": CAMPAIGN, "max_runs": max_runs,
        "allowed_seeds": [list(r) for r in allowed],
        "preregistration": {"path": "docs/prereg.md", "commit": "abcdef1"}, "created": "2026-11-24",
    }
    if amendments is not None:
        data["amendments"] = amendments
    return data


def write_manifest(repo: Path, data: dict) -> Path:
    path = repo / "budgets" / f"{CAMPAIGN}.json"
    path.parent.mkdir(exist_ok=True)
    path.write_bytes((json.dumps(data, indent=2) + "\n").encode("utf-8"))
    return path


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                    "-c", "commit.gpgsign=false", *args], check=True, capture_output=True)


def commit(repo: Path, message: str = "m") -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-m", message)


class BudgetCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.repo = self.tmp / "repo"
        (self.repo / "exec" / "src").mkdir(parents=True)
        shutil.copy(ROOT / "exec" / "src" / "seeds.rs", self.repo / "exec" / "src" / "seeds.rs")
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        git(self.repo, "config", "core.autocrlf", "false")
        self.ledger = self.tmp / "ledger"
        self.manifest = write_manifest(self.repo, manifest_data())
        commit(self.repo, "manifest")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def reserve(self, plan, label="t"):
        return rb.reserve(CAMPAIGN, plan, label, repo=self.repo, ledger_dir=self.ledger)

    def total(self):
        return rb.ledger_total(CAMPAIGN, repo=self.repo, ledger_dir=self.ledger)

    def amend(self, data):
        write_manifest(self.repo, data)
        commit(self.repo, "amend")


class CapTests(BudgetCase):
    def test_cap_plus_one_is_refused_and_spawn_never_called(self):
        calls = []
        with self.assertRaises(rb.BudgetExceeded):
            rb.run_budgeted(CAMPAIGN, [5000 + i for i in range(11)], calls.append, repo=self.repo, ledger_dir=self.ledger)
        self.assertEqual(calls, [])
        self.assertEqual(self.total(), 0)

    def test_exactly_the_cap_runs_every_planned_item_once(self):
        calls = []
        out = rb.run_budgeted(CAMPAIGN, [5000 + i for i in range(10)], calls.append, repo=self.repo, ledger_dir=self.ledger)
        self.assertEqual(calls, [5000 + i for i in range(10)])
        self.assertEqual(len(out), 10)
        self.assertEqual(self.total(), 10)

    def test_empty_plan_is_refused(self):
        with self.assertRaises(rb.BudgetError):
            self.reserve([])

    def test_total_accumulates_across_invocations_and_output_roots(self):
        roots = [self.tmp / "out-a", self.tmp / "out-b", self.tmp / "out-c"]
        for index, root in enumerate(roots[:2]):
            def spawn(seed, root=root):
                (root / f"s{seed}").mkdir(parents=True)
                (root / f"s{seed}" / "verification.json").write_text("{}")
            rb.run_budgeted(CAMPAIGN, [5000 + index * 10 + i for i in range(4)], spawn, repo=self.repo, ledger_dir=self.ledger)
        self.assertEqual(self.total(), 8)
        called = []
        with self.assertRaises(rb.BudgetExceeded):
            rb.run_budgeted(CAMPAIGN, [5050 + i for i in range(4)], called.append, repo=self.repo, ledger_dir=self.ledger)
        self.assertEqual(called, [])
        self.assertEqual(self.total(), 8)

    def test_failed_runs_are_not_refunded(self):
        def failing(seed):
            raise RuntimeError("boom")
        out = rb.run_budgeted(CAMPAIGN, [5000 + i for i in range(6)], failing, repo=self.repo, ledger_dir=self.ledger)
        self.assertTrue(all(isinstance(o.error, RuntimeError) for o in out))
        self.assertEqual(self.total(), 6)
        with self.assertRaises(rb.BudgetExceeded):
            self.reserve([5000 + i for i in range(5)])

    def test_replay_of_the_m10_stage_rerun_shape_is_refused_at_the_crossing(self):
        data = manifest_data(max_runs=45_000)
        self.amend(data)
        stages = [("0", 1400), ("1", 7680), ("2", 12000), ("3", 7200), ("3b", 1920), ("4", 9500), ("5", 5120)]
        self.assertEqual(sum(n for _, n in stages), 44_820)
        for label, n in stages:
            self.assertLessEqual(n, 12_000)  # cada etapa respeita um limite por etapa
            self.reserve([5000 + i % 100 for i in range(n)], label)
        self.assertEqual(self.total(), 44_820)
        with self.assertRaises(rb.BudgetExceeded):  # repetição «2g»: 44 820 + 2 400 > 45 000
            self.reserve([5000 + i % 100 for i in range(2400)], "2g")
        self.assertEqual(self.total(), 44_820)
        self.reserve([5000 + i % 100 for i in range(180)], "remaining")  # o que resta cabe
        with self.assertRaises(rb.BudgetExceeded):
            self.reserve([5000], "one-more")


class RaceTests(BudgetCase):
    def test_multi_process_race_never_exceeds_the_cap(self):
        start = time.time() + 1.5
        procs = [subprocess.Popen([sys.executable, "-c", RESERVE_CHILD, str(ROOT / "scripts"), str(self.repo),
                                   str(self.ledger), str(start), "3"],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(8)]
        results = []
        for proc in procs:
            stdout, stderr = proc.communicate(timeout=120)
            self.assertEqual(proc.returncode, 0, stderr)
            results.append(json.loads(stdout.strip().splitlines()[-1]))
        self.assertEqual(sum(1 for r in results if r["ok"]), 3)  # 3 x 3 = 9 <= 10 < 12
        self.assertEqual(self.total(), 9)
        self.assertLessEqual(self.total(), 10)


class ManifestTests(BudgetCase):
    def test_modified_manifest_is_refused(self):
        write_manifest(self.repo, manifest_data(max_runs=1_000_000))
        with self.assertRaisesRegex(rb.BudgetError, "difere do blob"):
            self.reserve([5000])

    def test_unregistered_manifest_is_refused(self):
        path = self.repo / "budgets" / "other.json"
        path.write_bytes(self.manifest.read_bytes().replace(b"demo-campaign", b"other"))
        with self.assertRaisesRegex(rb.BudgetError, "não está registado"):
            rb.reserve("other", [5000], repo=self.repo, ledger_dir=self.ledger)

    def test_restoring_the_committed_bytes_makes_it_valid_again(self):
        original = self.manifest.read_bytes()
        write_manifest(self.repo, manifest_data(max_runs=99))
        with self.assertRaises(rb.BudgetError):
            self.reserve([5000])
        self.manifest.write_bytes(original)
        self.assertEqual(self.reserve([5000]).total_after, 1)

    def test_manifest_with_unknown_field_or_bad_id_is_refused(self):
        data = manifest_data()
        data["extra"] = 1
        self.amend(data)
        with self.assertRaisesRegex(rb.BudgetError, "campos desconhecidos"):
            self.reserve([5000])
        with self.assertRaises(rb.BudgetError):
            rb.reserve("../escape", [5000], repo=self.repo, ledger_dir=self.ledger)

    def test_raising_the_cap_needs_a_committed_amendment_with_a_reason(self):
        self.reserve([5000 + i for i in range(10)])
        self.amend(manifest_data(max_runs=20))
        with self.assertRaisesRegex(rb.BudgetError, "sem adenda"):
            self.reserve([5000])
        self.amend(manifest_data(max_runs=20, amendments=[{"max_runs": 20, "reason": "  ", "date": "2026-11-25"}]))
        with self.assertRaisesRegex(rb.BudgetError, "reason"):
            self.reserve([5000])
        self.amend(manifest_data(max_runs=20, amendments=[{"max_runs": 20, "reason": "repetição prevista", "date": "2026-11-25"}]))
        self.assertEqual(self.reserve([5000 + i for i in range(10)]).total_after, 20)  # o total transita
        with self.assertRaises(rb.BudgetExceeded):
            self.reserve([5000])

    def test_amendment_must_match_max_runs(self):
        self.amend(manifest_data(max_runs=20, amendments=[{"max_runs": 15, "reason": "x", "date": "2026-11-25"}]))
        with self.assertRaisesRegex(rb.BudgetError, "última adenda"):
            self.reserve([5000])


class SeedTests(BudgetCase):
    def test_seed_outside_allowed_ranges_is_refused(self):
        with self.assertRaisesRegex(rb.BudgetError, "fora dos intervalos"):
            self.reserve([5000, 5100])
        self.assertEqual(self.total(), 0)

    def test_protected_seeds_are_refused_even_when_the_manifest_allows_them(self):
        allowed = ((2900, 3200), (6000, 6100), (44_000, 44_999), (50_000, 59_999), (81_000, 81_999), (5000, 5099))
        self.amend(manifest_data(allowed=allowed))
        for seed in (3000, 3099, 6050, 44_000, 44_500, 55_555, 81_000, 81_999):
            with self.subTest(seed=seed), self.assertRaisesRegex(rb.BudgetError, "protegido"):
                self.reserve([5000, seed])
        self.assertEqual(self.total(), 0)
        self.assertEqual(self.reserve([2999, 3100, 5000]).runs, 3)

    def test_protected_ranges_come_from_the_rust_source(self):
        ranges = {(lo, hi) for lo, hi, _ in rb.protected_ranges(self.repo)}
        self.assertTrue({(3000, 3099), (6000, 6099), (44_000, 44_999), (50_000, 59_999), (81_000, 81_999)} <= ranges)
        (self.repo / "exec" / "src" / "seeds.rs").write_text("// nada\n")
        with self.assertRaises(rb.BudgetError):
            rb.protected_ranges(self.repo)

    def test_dict_plan_items_and_bad_seeds(self):
        self.assertEqual(self.reserve([{"seed": 5001, "cell": "a"}]).runs, 1)
        with self.assertRaises(rb.BudgetError):
            self.reserve([{"cell": "a"}])
        with self.assertRaises(rb.BudgetError):
            self.reserve([True])


class WorktreeTests(BudgetCase):
    def test_ledger_is_shared_by_linked_worktrees(self):
        other = self.tmp / "linked"
        git(self.repo, "worktree", "add", "-q", "-b", "linked-branch", str(other))
        self.assertEqual(rb.default_ledger_dir(self.repo), rb.default_ledger_dir(other))
        self.assertEqual(rb.default_ledger_dir(other), (self.repo / ".git").resolve() / rb.LEDGER_DIRNAME)
        rb.reserve(CAMPAIGN, [5000 + i for i in range(6)], "a", repo=self.repo)  # localização predefinida
        with self.assertRaises(rb.BudgetExceeded):
            rb.reserve(CAMPAIGN, [5000 + i for i in range(6)], "b", repo=other)
        self.assertEqual(rb.reserve(CAMPAIGN, [5000 + i for i in range(4)], "c", repo=other).total_after, 10)
        self.assertEqual(rb.ledger_total(CAMPAIGN, repo=self.repo), 10)


class LedgerTests(BudgetCase):
    def test_default_ledger_is_in_the_git_common_dir_not_in_the_working_tree(self):
        path = rb.default_ledger_dir(self.repo)
        self.assertEqual(path, (self.repo / ".git").resolve() / rb.LEDGER_DIRNAME)
        self.assertFalse(path.is_relative_to(self.repo.resolve() / "budgets"))

    def test_tampered_or_truncated_ledger_fails_closed(self):
        self.reserve([5000, 5001])
        self.reserve([5002])
        file = self.ledger / f"{CAMPAIGN}.jsonl"
        lines = file.read_bytes().split(b"\n")
        file.write_bytes(lines[0].replace(b'"runs":2', b'"runs":1') + b"\n" + lines[1] + b"\n")
        with self.assertRaises(rb.BudgetError):
            self.reserve([5003])
        file.write_bytes(lines[0] + b"\n" + lines[1][:20])
        with self.assertRaisesRegex(rb.BudgetError, "incompleta"):
            self.total()

    def test_no_environment_or_cli_override_of_the_location(self):
        tree = ast.parse((ROOT / "scripts" / "run_budget.py").read_text(encoding="utf-8"))
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        self.assertNotIn("environ", names)
        self.assertNotIn("getenv", names)
        imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        self.assertNotIn("argparse", imported)
        self.assertNotIn("sys", imported)


class RecountTests(BudgetCase):
    def make_runs(self, root: Path, n: int):
        for i in range(n):
            d = root / f"run-{i}"
            d.mkdir(parents=True)
            (d / "verification.json").write_text("{}")

    def guard(self, roots, **kw):
        return rb.guard_report(CAMPAIGN, roots, repo=self.repo, ledger_dir=self.ledger, **kw)

    def test_matching_count_passes_across_several_roots(self):
        self.reserve([5000 + i for i in range(7)])
        self.make_runs(self.tmp / "a", 4)
        self.make_runs(self.tmp / "b", 3)
        result = self.guard([self.tmp / "a", self.tmp / "b"])
        self.assertEqual((result.runs, result.ledger_total, result.max_runs), (7, 7, 10))

    def test_mismatch_fails_the_report(self):
        self.reserve([5000 + i for i in range(7)])
        self.make_runs(self.tmp / "a", 5)
        with self.assertRaisesRegex(rb.BudgetError, "difere do registo"):
            self.guard(self.tmp / "a")
        self.assertEqual(self.guard(self.tmp / "a", declared_unrecorded=2).runs, 5)  # falhadas ou descartadas, declaradas
        with self.assertRaises(rb.BudgetError):
            self.guard(self.tmp / "a", declared_unrecorded=1)

    def test_more_artefacts_than_reserved_fails_even_if_declared(self):
        self.reserve([5000, 5001])
        self.make_runs(self.tmp / "a", 5)
        with self.assertRaises(rb.BudgetError):
            self.guard(self.tmp / "a")
        with self.assertRaises(rb.BudgetError):
            self.guard(self.tmp / "a", declared_unrecorded=0)

    def test_artefacts_above_the_cap_fail_with_budget_exceeded(self):
        self.reserve([5000 + i for i in range(10)])
        self.make_runs(self.tmp / "a", 12)
        with self.assertRaises(rb.BudgetExceeded):
            self.guard(self.tmp / "a")

    def test_overlapping_roots_and_ledger_inside_root_are_refused(self):
        self.reserve([5000])
        self.make_runs(self.tmp / "a", 1)
        with self.assertRaisesRegex(rb.BudgetError, "sobrepostas"):
            self.guard([self.tmp / "a", self.tmp / "a" / "run-0"])
        with self.assertRaisesRegex(rb.BudgetError, "dentro da pasta"):
            self.guard(self.tmp)


# Ficheiros de `scripts/` autorizados a lançar processos sem passar por `run_budget`, cada um com a razão.
SPAWN_ALLOWLIST = {
    "scripts/run_budget.py": "só executa `git` para ler o manifesto, HEAD e o diretório comum",
    "scripts/process_limits.py": "executor genérico com limites de tempo e bytes; não conhece campanhas",
    "scripts/sim_adapter.py": "adaptador de uma execução por pedido; limitado por invocação",
    "scripts/rocket_adapter.py": "adaptador de uma execução por pedido; limitado por invocação",
    "scripts/run_campaign.py": "campanha de aceitação limitada por invocação (sementes explícitas, máximo próprio); não é pré-registada",
    "scripts/replay_workbench.py": "só lê evidência e lê o commit; não executa simulações",
    "scripts/m6_repair_lab.py": "experiência M6 delimitada por tempo e por número de invocações; anterior ao orçamento",
    "scripts/m14_benchmark.py": "benchmark M14 com divisões e congelação próprias; anterior ao orçamento; migrar se for repetido",
    "scripts/m14_fragility.py": "estudo exploratório M14 com sementes de desenvolvimento, limitado por invocação; anterior ao orçamento",
    "scripts/m14_masking_model.py": "teste exploratório M14 com sementes de desenvolvimento, limitado por invocação; anterior ao orçamento",
    # Lançamento indireto, através de `process_limits` ou dos adaptadores.
    "scripts/campaign_matrix.py": "matrizes M1 e M2 limitadas por invocação; anterior ao orçamento",
    "scripts/campaign_report.py": "constrói resumos de uma campanha limitada por invocação; anterior ao orçamento",
    "scripts/failure_reduction.py": "redução de falhas limitada por invocação; anterior ao orçamento",
    "scripts/minimize_failure.py": "redução de falhas limitada por invocação; anterior ao orçamento",
    "scripts/m3_campaign.py": "campanha M3 limitada por invocação; anterior ao orçamento",
    "scripts/m3_minimize_failure.py": "redução M3 limitada por invocação; anterior ao orçamento",
    "scripts/m4_campaign.py": "campanha M4 limitada por invocação; anterior ao orçamento",
    "scripts/m9_campaign.py": "campanha M9 com máximo por invocação e sementes protegidas; anterior ao orçamento",
    "scripts/m91_campaign.py": "campanha M9.1 com máximo por invocação e sementes protegidas; anterior ao orçamento",
    "scripts/m91_retrospective.py": "verificação retrospetiva M9.1 limitada por invocação; anterior ao orçamento",
    "scripts/adversarial_campaign.py": "campanha do motor adversário limitada por invocação; anterior ao orçamento",
    "scripts/adversarial_ablation.py": "ablação limitada por invocação; anterior ao orçamento",
    "scripts/landing_adapter.py": "adaptador de uma execução por pedido; limitado por invocação",
    "scripts/mission_control.py": "interface local sobre o adaptador, uma execução por pedido do utilizador",
    "scripts/check_platform_artifacts.py": "compara artefactos entre plataformas; importa as campanhas limitadas por invocação",
    "scripts/failure_signature.py": "assinaturas de falhas; importa a redução de falhas limitada por invocação",
    "scripts/cinematic/bench.py": "mede o renderizador; não executa simulações",
    "scripts/cinematic/package_module.py": "empacota o módulo do renderizador; não executa simulações",
}
SPAWN_MODULES = {"subprocess", "multiprocessing", "pty"}
SPAWN_OS = ("system", "popen", "startfile", "fork", "forkpty")


def _is_os_spawn(name: str) -> bool:
    return name in SPAWN_OS or name.startswith(("spawn", "exec"))


def spawning_scripts(base: Path = ROOT / "scripts") -> dict[str, set[str]]:
    """Ficheiros que lançam processos, diretamente ou por importarem um módulo local que lança (ponto fixo)."""
    paths = sorted(base.rglob("*.py"))
    direct: dict[Path, set[str]] = {}
    imports: dict[Path, set[str]] = {}
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        hits: set[str] = set()
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                top = (node.module or "").split(".")[0]
                names.add(top)
                names |= {a.name for a in node.names}
                if top == "os":
                    hits |= {f"os.{a.name}" for a in node.names if _is_os_spawn(a.name)}
            elif isinstance(node, ast.Attribute):
                if isinstance(node.value, ast.Name) and node.value.id == "os" and _is_os_spawn(node.attr):
                    hits.add(f"os.{node.attr}")
                elif node.attr.startswith("create_subprocess"):
                    hits.add(node.attr)
        hits |= names & SPAWN_MODULES
        direct[path], imports[path] = hits, names
    stems = {path.stem: path for path in paths if path.stem != "run_budget"}
    flagged = {path: set(hits) for path, hits in direct.items() if hits}
    changed = True
    while changed:
        changed = False
        for path in paths:
            via = {f"via {stem}" for stem, owner in stems.items()
                   if stem in imports[path] and owner in flagged and owner != path}
            if via - flagged.get(path, set()):
                flagged.setdefault(path, set()).update(via)
                changed = True
    return {path.relative_to(base.parent).as_posix(): hits | ({"<uses run_budget>"} if "run_budget" in imports[path] else set())
            for path, hits in flagged.items()}


class SpawnAllowlistTests(unittest.TestCase):
    def test_every_spawning_script_is_allowlisted_or_uses_run_budget(self):
        unlisted = [p for p, hits in spawning_scripts().items()
                    if p not in SPAWN_ALLOWLIST and "<uses run_budget>" not in hits]
        self.assertEqual(unlisted, [], "scripts que lançam processos sem usar run_budget nem estar autorizados")

    def test_detector_flags_new_spawners_and_accepts_run_budget_users(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "scripts"
            base.mkdir()
            files = {
                "new_spawner.py": "import subprocess as sp\nsp.run(['x'])\n",
                "os_spawner.py": "import os\nos.system('x')\n",
                "indirect.py": "from helper import go\n",
                "helper.py": "import subprocess\n",
                "chain.py": "import indirect\n",
                "from_os.py": "from os import system\n",
                "budgeted.py": "import subprocess\nimport run_budget\n",
                "clean.py": "import json\n",
            }
            for name, text in files.items():
                (base / name).write_text(text, encoding="utf-8")
            found = spawning_scripts(base)
            self.assertEqual(sorted(found), ["scripts/budgeted.py", "scripts/chain.py", "scripts/from_os.py", "scripts/helper.py", "scripts/indirect.py",
                          "scripts/new_spawner.py", "scripts/os_spawner.py"])
            self.assertIn("<uses run_budget>", found["scripts/budgeted.py"])
            self.assertNotIn("<uses run_budget>", found["scripts/new_spawner.py"])

    def test_allowlist_has_no_stale_entries_and_every_entry_has_a_reason(self):
        found = spawning_scripts()
        for path, reason in SPAWN_ALLOWLIST.items():
            with self.subTest(path=path):
                self.assertIn(path, found, "entrada obsoleta: o ficheiro já não lança processos")
                self.assertGreater(len(reason.split()), 3)
                self.assertNotIn(chr(0x2014), reason)


if __name__ == "__main__":
    unittest.main()
