"""Orçamento de execuções: limite acumulado, concorrência, manifesto registado, sementes e contagem."""

from __future__ import annotations

import ast
import inspect
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

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
    r = rb._reserve("demo-campaign", [5000 + i for i in range(n)], "race", repo, ledger)
    print(json.dumps({"ok": True, "total": r.total_after}))
except rb.BudgetExceeded as error:
    print(json.dumps({"ok": False}))
"""


def manifest_data(max_runs: int = 10, allowed=((5000, 5099),), amendments=None, campaign=CAMPAIGN,
                  prereg="docs/prereg.md", status=None) -> dict:
    data = {
        "schema": rb.MANIFEST_SCHEMA, "campaign_id": campaign, "max_runs": max_runs,
        "allowed_seeds": [list(r) for r in allowed],
        "preregistration": {"path": prereg, "commit": "abcdef1"}, "created": "2026-11-24",
    }
    if amendments is not None:
        data["amendments"] = amendments
    if status is not None:
        data["status"] = status
    return data


def amendment(max_runs: int, reason: str = "repetição prevista") -> dict:
    return {"max_runs": max_runs, "reason": reason, "date": "2026-11-25"}


def closing(max_runs: int, reason: str = "campanha encerrada") -> dict:
    return {**amendment(max_runs, reason), "closes": True}


def write_manifest(repo: Path, data: dict) -> Path:
    path = repo / "budgets" / f"{data['campaign_id']}.json"
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
        self.seeds_rs = self.repo / "exec" / "src" / "seeds.rs"
        shutil.copy(ROOT / "exec" / "src" / "seeds.rs", self.seeds_rs)
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        git(self.repo, "config", "core.autocrlf", "false")
        self.ledger = self.tmp / "ledger"
        self.manifest = write_manifest(self.repo, manifest_data())
        commit(self.repo, "manifest")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def reserve(self, plan, label="t"):
        return rb._reserve(CAMPAIGN, plan, label, self.repo, self.ledger)

    def run_budgeted(self, plan, spawn, jobs=1):
        return rb._run_budgeted(CAMPAIGN, plan, spawn, "t", jobs, self.repo, self.ledger)

    def total(self):
        return rb._ledger_total(CAMPAIGN, self.repo, self.ledger)

    def amend(self, data):
        write_manifest(self.repo, data)
        commit(self.repo, "amend")

    def edit_seeds_rs(self, text: str):
        self.seeds_rs.write_text(text, encoding="utf-8", newline="\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "--allow-empty", "-m", "seeds")


class CapTests(BudgetCase):
    def test_cap_plus_one_is_refused_and_spawn_never_called(self):
        calls = []
        with self.assertRaises(rb.BudgetExceeded):
            self.run_budgeted([5000 + i for i in range(11)], calls.append)
        self.assertEqual(calls, [])
        self.assertEqual(self.total(), 0)

    def test_exactly_the_cap_runs_every_planned_item_once(self):
        calls = []
        out = self.run_budgeted([5000 + i for i in range(10)], calls.append)
        self.assertEqual(calls, [5000 + i for i in range(10)])
        self.assertEqual(len(out), 10)
        self.assertEqual(self.total(), 10)

    def test_parallel_jobs_keep_the_plan_order_of_outcomes(self):
        out = self.run_budgeted([5000 + i for i in range(8)], lambda seed: seed * 2, jobs=4)
        self.assertEqual([o.result for o in out], [(5000 + i) * 2 for i in range(8)])

    def test_empty_plan_is_refused(self):
        with self.assertRaises(rb.BudgetError):
            self.reserve([])

    def test_total_accumulates_across_invocations_and_output_roots(self):
        roots = [self.tmp / "out-a", self.tmp / "out-b"]
        for index, root in enumerate(roots):
            def spawn(seed, root=root):
                (root / f"s{seed}").mkdir(parents=True)
                (root / f"s{seed}" / "verification.json").write_text("{}")
            self.run_budgeted([5000 + index * 10 + i for i in range(4)], spawn)
        self.assertEqual(self.total(), 8)
        called = []
        with self.assertRaises(rb.BudgetExceeded):
            self.run_budgeted([5050 + i for i in range(4)], called.append)
        self.assertEqual(called, [])
        self.assertEqual(self.total(), 8)

    def test_failed_runs_are_not_refunded(self):
        def failing(seed):
            raise RuntimeError("boom")
        out = self.run_budgeted([5000 + i for i in range(6)], failing)
        self.assertTrue(all(isinstance(o.error, RuntimeError) for o in out))
        self.assertEqual(self.total(), 6)
        with self.assertRaises(rb.BudgetExceeded):
            self.reserve([5000 + i for i in range(5)])

    def test_replay_of_the_m10_stage_rerun_shape_is_refused_at_the_crossing(self):
        write_manifest(self.repo, manifest_data(max_runs=45_000, allowed=((7000, 7099),), campaign="m10-replay",
                                                prereg="docs/replay.md"))
        commit(self.repo, "m10 replay budget")
        stages = [("0", 1400), ("1", 7680), ("2", 12000), ("3", 7200), ("3b", 1920), ("4", 9500), ("5", 5120)]
        self.assertEqual(sum(n for _, n in stages), 44_820)

        def reserve(n, label):
            return rb._reserve("m10-replay", [7000 + i % 100 for i in range(n)], label, self.repo, self.ledger)

        for label, n in stages:
            self.assertLessEqual(n, 12_000)  # cada etapa respeita um limite por etapa
            reserve(n, label)
        self.assertEqual(rb._ledger_total("m10-replay", self.repo, self.ledger), 44_820)
        with self.assertRaises(rb.BudgetExceeded):  # repetição «2g»: 44 820 + 2 400 > 45 000
            reserve(2400, "2g")
        self.assertEqual(rb._ledger_total("m10-replay", self.repo, self.ledger), 44_820)
        reserve(180, "remaining")  # o que resta cabe
        with self.assertRaises(rb.BudgetExceeded):
            reserve(1, "one-more")


class PublicApiTests(unittest.TestCase):
    def test_public_functions_accept_no_location_parameters(self):
        for function in (rb.reserve, rb.run_budgeted, rb.ledger_total, rb.recount, rb.guard_report):
            names = set(inspect.signature(function).parameters)
            with self.subTest(function=function.__name__):
                self.assertFalse(names & {"repo", "ledger_dir", "ledger", "root", "path"}, names)

    def test_no_environment_or_cli_override_of_the_location(self):
        tree = ast.parse((ROOT / "scripts" / "run_budget.py").read_text(encoding="utf-8"))
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        self.assertNotIn("getenv", names)
        imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        self.assertNotIn("argparse", imported)
        self.assertNotIn("sys", imported)
        # `os.environ` só aparece para retirar as variáveis GIT_* do ambiente de `git`
        uses = [n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == "environ"]
        self.assertEqual(len(uses), 1)


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
            rb._reserve("other", [5000], "", self.repo, self.ledger)

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
            rb._reserve("../escape", [5000], "", self.repo, self.ledger)

    def test_raising_the_cap_without_an_amendment_is_refused(self):
        self.reserve([5000 + i for i in range(10)])
        self.amend(manifest_data(max_runs=20))
        with self.assertRaisesRegex(rb.BudgetError, "sem adenda"):
            self.reserve([5000])

    def test_amendment_with_reason_raises_the_cap_and_the_total_carries_over(self):
        self.reserve([5000 + i for i in range(10)])
        self.amend(manifest_data(max_runs=20, amendments=[amendment(20)]))
        self.assertEqual(self.reserve([5000 + i for i in range(10)]).total_after, 20)
        with self.assertRaises(rb.BudgetExceeded):
            self.reserve([5000])

    def test_amendment_without_reason_is_refused(self):
        self.amend(manifest_data(max_runs=20, amendments=[amendment(20, "  ")]))
        with self.assertRaisesRegex(rb.BudgetError, "reason"):
            self.reserve([5000])

    def test_amendment_must_match_max_runs(self):
        self.amend(manifest_data(max_runs=20, amendments=[amendment(15)]))
        with self.assertRaisesRegex(rb.BudgetError, "última adenda"):
            self.reserve([5000])

    def test_amendments_are_append_only_across_commits(self):
        self.amend(manifest_data(max_runs=20, amendments=[amendment(20, "primeira")]))
        self.assertEqual(self.reserve([5000]).runs, 1)
        self.amend(manifest_data(max_runs=25, amendments=[amendment(25, "substituída")]))
        with self.assertRaisesRegex(rb.BudgetError, "só de acréscimo"):
            self.reserve([5000])
        self.amend(manifest_data(max_runs=25, amendments=[amendment(20, "primeira"), amendment(25, "segunda")]))
        with self.assertRaisesRegex(rb.BudgetError, "só de acréscimo"):  # o histórico já tem a versão substituída
            self.reserve([5000])

    def test_appending_an_amendment_keeps_the_history_valid(self):
        self.amend(manifest_data(max_runs=20, amendments=[amendment(20, "primeira")]))
        self.amend(manifest_data(max_runs=30, amendments=[amendment(20, "primeira"), amendment(30, "segunda")]))
        self.assertEqual(self.reserve([5000]).max_runs, 30)

    def test_lowering_the_cap_is_refused(self):
        self.amend(manifest_data(max_runs=5))
        with self.assertRaisesRegex(rb.BudgetError, "desceu"):
            self.reserve([5000])

    def test_a_second_manifest_cannot_reuse_the_preregistration_or_the_seeds(self):
        write_manifest(self.repo, manifest_data(campaign="second", allowed=((7000, 7099),), prereg="docs/other.md"))
        commit(self.repo, "second")
        self.assertEqual(rb._reserve("second", [7000], "", self.repo, self.ledger).runs, 1)
        write_manifest(self.repo, manifest_data(campaign="third", allowed=((7200, 7299),), prereg="docs/other.md"))
        commit(self.repo, "third")
        with self.assertRaisesRegex(rb.BudgetError, "pré-registo"):
            rb._reserve("third", [7200], "", self.repo, self.ledger)
        write_manifest(self.repo, manifest_data(campaign="fourth", allowed=((5090, 5120),), prereg="docs/fourth.md"))
        commit(self.repo, "fourth")
        with self.assertRaisesRegex(rb.BudgetError, "sobrepõem-se"):
            rb._reserve("fourth", [5100], "", self.repo, self.ledger)
        with self.assertRaisesRegex(rb.BudgetError, "sobrepõem-se"):  # a campanha original também fica bloqueada
            self.reserve([5000])

    def test_git_environment_variables_do_not_move_the_manifest_or_the_ledger(self):
        bogus = self.tmp / "bogus"
        subprocess.run(["git", "init", "-q", str(bogus)], check=True)
        expected = rb._default_ledger_dir(self.repo)
        with patch.dict(os.environ, {"GIT_DIR": str(bogus / ".git"), "GIT_COMMON_DIR": str(bogus / ".git"),
                                     "GIT_WORK_TREE": str(bogus)}):
            self.assertEqual(rb._default_ledger_dir(self.repo), expected)
            self.assertEqual(expected, (self.repo / ".git").resolve() / rb.LEDGER_DIRNAME)
            self.assertEqual(self.reserve([5000]).runs, 1)  # o manifesto vem do repositório certo

    def test_manifest_bytes_survive_autocrlf_and_gitattributes_cover_budgets(self):
        shown = subprocess.run(["git", "-C", str(ROOT), "check-attr", "text", "eol", "--", "budgets/x.json"],
                               capture_output=True, text=True, check=True).stdout
        self.assertIn("eol: lf", shown)
        self.assertIn("text: set", shown)
        shutil.copy(ROOT / ".gitattributes", self.repo / ".gitattributes")
        commit(self.repo, "attributes")
        git(self.repo, "config", "core.autocrlf", "true")
        self.manifest.unlink()
        git(self.repo, "checkout", "--", f"budgets/{CAMPAIGN}.json")
        self.assertNotIn(b"\r\n", self.manifest.read_bytes())
        self.assertEqual(self.reserve([5000]).runs, 1)
        self.manifest.write_bytes(self.manifest.read_bytes().replace(b"\n", b"\r\n"))
        with self.assertRaisesRegex(rb.BudgetError, "difere do blob"):
            self.reserve([5000])


class RenameAndHistoryTests(BudgetCase):
    def rename_manifest(self, new_id: str, **changes):
        data = manifest_data(campaign=new_id, **changes)
        git(self.repo, "mv", f"budgets/{CAMPAIGN}.json", f"budgets/{new_id}.json")
        write_manifest(self.repo, data)
        commit(self.repo, "rename")

    def test_renaming_the_manifest_does_not_reset_the_budget(self):
        self.reserve([5000 + i for i in range(10)])  # 10 de 10
        self.rename_manifest("renamed")
        with self.assertRaisesRegex(rb.BudgetError, "apaga ou renomeia"):
            rb._reserve("renamed", [5000], "", self.repo, self.ledger)

    def test_ledger_scan_refuses_an_id_that_reuses_seeds_of_an_existing_ledger(self):
        self.reserve([5000])
        fresh = self.tmp / "fresh"
        subprocess.run(["git", "init", "-q", str(fresh)], check=True)
        git(fresh, "config", "core.autocrlf", "false")
        (fresh / "exec" / "src").mkdir(parents=True)
        shutil.copy(self.seeds_rs, fresh / "exec" / "src" / "seeds.rs")
        write_manifest(fresh, manifest_data(campaign="newid", prereg="docs/new.md"))
        commit(fresh, "new")
        with self.assertRaisesRegex(rb.BudgetError, "sobrepõem-se"):  # o mesmo diretório de registos, sem manifesto irmão
            rb._reserve("newid", [5000], "", fresh, self.ledger)

    def test_rise_without_amendment_on_an_orphan_history_is_refused_by_the_ledger(self):
        self.reserve([5000 + i for i in range(10)])
        git(self.repo, "checkout", "-q", "--orphan", "orphan")
        write_manifest(self.repo, manifest_data(max_runs=20))
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-m", "orphan with a higher cap")
        with self.assertRaisesRegex(rb.BudgetError, "sem adenda nova face ao último registo"):
            self.reserve([5000])
        write_manifest(self.repo, manifest_data(max_runs=20, amendments=[amendment(20)]))
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-m", "orphan with an amendment")
        self.assertEqual(self.reserve([5000]).total_after, 11)


class ClosureTests(BudgetCase):
    def close(self, max_runs=10, amendments=()):
        self.amend(manifest_data(max_runs=max_runs, amendments=[*amendments, closing(max_runs)], status="closed"))

    def test_a_closed_campaign_refuses_every_reservation_and_spawn(self):
        self.reserve([5000, 5001])
        self.close()
        calls = []
        with self.assertRaisesRegex(rb.BudgetError, "fechada"):
            self.run_budgeted([5002], calls.append)
        self.assertEqual(calls, [])
        self.assertEqual(self.total(), 2)  # o registo de fecho não conta execuções

    def test_closing_needs_a_closing_amendment_with_a_reason(self):
        self.amend(manifest_data(status="closed"))
        with self.assertRaisesRegex(rb.BudgetError, "não há reabertura"):
            self.reserve([5000])
        self.amend(manifest_data(max_runs=10, amendments=[closing(10, " ")], status="closed"))
        with self.assertRaisesRegex(rb.BudgetError, "reason"):
            self.reserve([5000])

    def test_closing_amendment_without_status_closed_is_refused(self):
        self.amend(manifest_data(max_runs=10, amendments=[closing(10)]))
        with self.assertRaisesRegex(rb.BudgetError, "não há reabertura"):
            self.reserve([5000])

    def test_a_closed_campaign_cannot_be_reopened_by_a_later_commit(self):
        self.close()
        self.amend(manifest_data(max_runs=10, amendments=[amendment(11)]))
        with self.assertRaises(rb.BudgetError):
            self.reserve([5000])
        self.amend(manifest_data(max_runs=10))
        with self.assertRaisesRegex(rb.BudgetError, "só de acréscimo|reaberta"):
            self.reserve([5000])

    def test_reopening_on_a_rewritten_history_is_caught_by_the_ledger(self):
        self.reserve([5000])
        self.close()
        with self.assertRaises(rb.BudgetError):
            self.reserve([5001])  # grava o registo de fecho
        git(self.repo, "checkout", "-q", "--orphan", "orphan")
        write_manifest(self.repo, manifest_data())
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-m", "orphan without the closure")
        with self.assertRaisesRegex(rb.BudgetError, "reaberta"):
            self.reserve([5001])

    def test_a_closed_campaign_can_still_be_recounted(self):
        self.reserve([5000, 5001])
        self.close()
        for i in range(2):
            (self.tmp / "a" / f"r{i}").mkdir(parents=True)
            (self.tmp / "a" / f"r{i}" / "verification.json").write_text("{}")
        self.assertEqual(rb._guard_report(CAMPAIGN, self.tmp / "a", repo=self.repo, ledger_dir=self.ledger).runs, 2)

    def test_amendment_then_closure_keeps_a_valid_history(self):
        self.amend(manifest_data(max_runs=20, amendments=[amendment(20)]))
        self.assertEqual(self.reserve([5000]).runs, 1)
        self.amend(manifest_data(max_runs=20, amendments=[amendment(20), closing(20)], status="closed"))
        with self.assertRaisesRegex(rb.BudgetError, "fechada"):
            self.reserve([5000])


class SeedTests(BudgetCase):
    def source(self) -> str:
        return (ROOT / "exec" / "src" / "seeds.rs").read_text(encoding="utf-8")

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

    def test_protected_ranges_come_from_the_rust_source_at_head(self):
        ranges = {(lo, hi) for lo, hi, _ in rb._protected_ranges(self.repo)}
        self.assertTrue({(3000, 3099), (6000, 6099), (44_000, 44_999), (100, 129), (50_000, 59_999), (81_000, 81_999)} <= ranges)
        self.seeds_rs.write_text("// alteração por registar\n", encoding="utf-8")  # a árvore de trabalho não conta
        self.assertEqual(self.reserve([5000]).runs, 1)

    def test_removed_required_entry_fails_closed(self):
        start = self.source().index("    Protected {\n        start: 3000")
        end = self.source().index("    Protected {", start + 10)
        self.edit_seeds_rs(self.source()[:start] + self.source()[end:])
        with self.assertRaisesRegex(rb.BudgetError, "obrigatórios"):
            self.reserve([5000])

    def test_unsupported_formats_fail_closed(self):
        cases = {
            "hex": self.source().replace("start: 3000", "start: 0xBB8", 1),
            "expression": self.source().replace("end: 3099", "end: 3000 + 99", 1),
            "end below start": self.source().replace("end: 3099", "end: 2999", 1),
            "no literals": "pub struct Protected { pub start: u64 }\n",
            "swapped fields": self.source().replace("start: 3000,\n        end: 3099,", "end: 3099,\n        start: 3000,", 1),
        }
        for name, text in cases.items():
            with self.subTest(case=name):
                self.edit_seeds_rs(text)
                with self.assertRaises(rb.BudgetError):
                    self.reserve([5000])
        self.edit_seeds_rs(self.source())
        self.assertEqual(self.reserve([5000]).runs, 1)

    def test_comment_noise_is_ignored(self):
        noisy = ("// Protected { start: 9, end: 1, reason: \"x\" }\n/* Protected { start: 0x1, end: oops } */\n"
                 + self.source().replace("reason: \"M10 evaluation seeds\"", "reason: \"M10 // not a comment\"", 1))
        self.edit_seeds_rs(noisy)
        ranges = {(lo, hi) for lo, hi, _ in rb._protected_ranges(self.repo)}
        self.assertIn((3000, 3099), ranges)
        self.assertNotIn((9, 1), ranges)

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
        self.assertEqual(rb._default_ledger_dir(self.repo), rb._default_ledger_dir(other))
        self.assertEqual(rb._default_ledger_dir(other), (self.repo / ".git").resolve() / rb.LEDGER_DIRNAME)
        rb._reserve(CAMPAIGN, [5000 + i for i in range(6)], "a", self.repo)  # localização predefinida
        with self.assertRaises(rb.BudgetExceeded):
            rb._reserve(CAMPAIGN, [5000 + i for i in range(6)], "b", other)
        self.assertEqual(rb._reserve(CAMPAIGN, [5000 + i for i in range(4)], "c", other).total_after, 10)
        self.assertEqual(rb._ledger_total(CAMPAIGN, self.repo), 10)


class LedgerTests(BudgetCase):
    def files(self):
        return self.ledger / f"{CAMPAIGN}.jsonl", self.ledger / f"{CAMPAIGN}.tip"

    def test_tampered_line_or_torn_final_line_fails_closed(self):
        self.reserve([5000, 5001])
        self.reserve([5002])
        ledger, _ = self.files()
        lines = ledger.read_bytes().split(b"\n")
        ledger.write_bytes(lines[0].replace(b'"runs":2', b'"runs":1') + b"\n" + lines[1] + b"\n")
        with self.assertRaises(rb.BudgetError):
            self.reserve([5003])
        ledger.write_bytes(lines[0] + b"\n" + lines[1][:20])
        with self.assertRaisesRegex(rb.BudgetError, "incompleta"):
            self.total()

    def test_deleting_trailing_lines_is_detected_by_the_tip_record(self):
        self.reserve([5000, 5001])
        self.reserve([5002, 5003, 5004])
        ledger, _ = self.files()
        first = ledger.read_bytes().split(b"\n")[0] + b"\n"
        ledger.write_bytes(first)
        with self.assertRaisesRegex(rb.BudgetError, "atrás do registo de ponta"):
            self.reserve([5005])

    def test_deleting_the_ledger_file_is_detected_by_the_tip_record(self):
        self.reserve([5000])
        self.files()[0].unlink()
        with self.assertRaisesRegex(rb.BudgetError, "atrás do registo de ponta"):
            self.reserve([5001])

    def test_tip_that_disagrees_with_the_ledger_or_is_torn_fails_closed(self):
        self.reserve([5000])
        _, tip = self.files()
        good = tip.read_bytes()
        tip.write_bytes(good.replace(b'"sha256":"', b'"sha256":"0'))
        with self.assertRaisesRegex(rb.BudgetError, "diverge"):
            self.reserve([5001])
        tip.write_bytes(good[:-5])
        with self.assertRaisesRegex(rb.BudgetError, "incompleta"):
            self.reserve([5001])

    def test_deleting_both_files_is_not_prevented(self):
        # Limite conhecido, documentado em docs/run-budget.md: quem apaga o registo e a ponta repõe o orçamento.
        self.reserve([5000 + i for i in range(10)])
        for file in self.files():
            file.unlink()
        self.assertEqual(self.reserve([5000]).total_after, 1)

    def test_a_crash_between_ledger_and_tip_is_recoverable_in_the_safe_direction(self):
        self.reserve([5000, 5001])
        ledger, tip = self.files()
        tip.unlink()  # a ponta ficou para trás do registo: aceite, a próxima reserva repõe-a
        self.assertEqual(self.reserve([5002]).total_after, 3)
        self.assertEqual(len(tip.read_bytes().splitlines()), 1)

    def test_ledger_and_tip_are_outside_artefact_roots_and_in_the_common_dir_by_default(self):
        self.assertEqual(rb._default_ledger_dir(self.repo), (self.repo / ".git").resolve() / rb.LEDGER_DIRNAME)


class RecountTests(BudgetCase):
    def make_runs(self, root: Path, n: int):
        for i in range(n):
            d = root / f"run-{i}"
            d.mkdir(parents=True)
            (d / "verification.json").write_text("{}")

    def guard(self, roots, **kw):
        return rb._guard_report(CAMPAIGN, roots, repo=self.repo, ledger_dir=self.ledger, **kw)

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
        ok = self.guard(self.tmp / "a", declared_unrecorded=2, unrecorded_run_ids=["r-6", "r-7"])
        self.assertEqual((ok.runs, ok.unrecorded_run_ids), (5, ("r-6", "r-7")))
        with self.assertRaises(rb.BudgetError):
            self.guard(self.tmp / "a", declared_unrecorded=1, unrecorded_run_ids=["r-6"])

    def test_declared_count_must_match_the_listed_run_ids(self):
        self.reserve([5000 + i for i in range(7)])
        self.make_runs(self.tmp / "a", 5)
        for kwargs in ({"declared_unrecorded": 2}, {"unrecorded_run_ids": ["r-6", "r-7"]},
                       {"declared_unrecorded": 2, "unrecorded_run_ids": ["r-6", "r-6"]},
                       {"declared_unrecorded": 2, "unrecorded_run_ids": ["r-6", ""]},
                       {"declared_unrecorded": 3, "unrecorded_run_ids": ["r-6", "r-7"]}):
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(rb.BudgetError, "não coincide"):
                self.guard(self.tmp / "a", **kwargs)

    def test_more_artefacts_than_reserved_fails_even_if_declared(self):
        self.reserve([5000, 5001])
        self.make_runs(self.tmp / "a", 5)
        with self.assertRaises(rb.BudgetError):
            self.guard(self.tmp / "a")

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
SPAWN_MODULES = {"subprocess", "multiprocessing", "pty", "importlib"}
SPAWN_NAMES = {"ProcessPoolExecutor", "__import__", "import_module"}
SPAWN_OS = ("system", "popen", "startfile", "fork", "forkpty")


def _is_os_spawn(name: str) -> bool:
    return name in SPAWN_OS or name.startswith(("spawn", "exec"))


def _spawn_hit(node: ast.AST) -> str | None:
    """Nome do lançamento direto que `node` representa, ou None."""
    if isinstance(node, ast.Attribute):
        if isinstance(node.value, ast.Name):
            base = node.value.id
            if base == "os" and _is_os_spawn(node.attr):
                return f"os.{node.attr}"
            if base in SPAWN_MODULES:
                return f"{base}.{node.attr}"
        if node.attr.startswith("create_subprocess") or node.attr in SPAWN_NAMES:
            return node.attr
    elif isinstance(node, ast.Name) and node.id in SPAWN_NAMES:
        return node.id
    return None


def _analyse(path: Path) -> tuple[set[str], set[str], list[str]]:
    """(lançamentos diretos, nomes importados, violações das regras de quem usa `run_budget`)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    hits: set[str] = set()
    names: set[str] = set()
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    spawn_nodes: list[ast.AST] = []
    from_spawn_modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            top = (node.module or "").split(".")[0]
            names.add(top)
            names |= {a.name for a in node.names}
            if top in SPAWN_MODULES or any(a.name in SPAWN_NAMES for a in node.names):
                from_spawn_modules.append(node.module or "")
            if top == "os":
                hits |= {f"os.{a.name}" for a in node.names if _is_os_spawn(a.name)}
        hit = _spawn_hit(node)
        if hit:
            hits.add(hit)
            spawn_nodes.append(node)
    hits |= names & (SPAWN_MODULES | SPAWN_NAMES)
    violations: list[str] = []
    if "run_budget" in names:
        spawn_funcs, calls = set(), 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and (
                    (isinstance(node.func, ast.Attribute) and node.func.attr == "run_budgeted")
                    or (isinstance(node.func, ast.Name) and node.func.id == "run_budgeted")):
                calls += 1
                arg = next((k.value for k in node.keywords if k.arg == "spawn"), node.args[2] if len(node.args) > 2 else None)
                if isinstance(arg, ast.Name):
                    spawn_funcs.add(arg.id)
                elif isinstance(arg, ast.Attribute):
                    spawn_funcs.add(arg.attr)
                elif isinstance(arg, ast.Lambda):
                    spawn_funcs.add(id(arg))
        if not calls:
            violations.append("importa run_budget mas não chama run_budgeted com spawn=")
        violations += [f"`from {m} import ...` lança fora de spawn=" for m in from_spawn_modules]
        for node in spawn_nodes:
            current, routed = parents.get(node), False
            while current is not None and not routed:
                routed = (isinstance(current, ast.FunctionDef) and current.name in spawn_funcs) or id(current) in spawn_funcs
                current = parents.get(current)
            if not routed:
                violations.append(f"linha {getattr(node, 'lineno', '?')}: {_spawn_hit(node)} fora da função passada em spawn=")
    return hits, names, violations


def analyse_scripts(base: Path = ROOT / "scripts"):
    """Ficheiros que lançam processos, diretamente ou por importarem um módulo local que lança (ponto fixo)."""
    paths = sorted(base.rglob("*.py"))
    direct, imports, violations = {}, {}, {}
    for path in paths:
        direct[path], imports[path], violations[path] = _analyse(path)
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
    spawners = {path.relative_to(base.parent).as_posix(): hits | ({"<uses run_budget>"} if "run_budget" in imports[path] else set())
                for path, hits in flagged.items()}
    bad = {path.relative_to(base.parent).as_posix(): v for path, v in violations.items() if v}
    return spawners, bad


def spawning_scripts(base: Path = ROOT / "scripts") -> dict[str, set[str]]:
    return analyse_scripts(base)[0]


class SpawnAllowlistTests(unittest.TestCase):
    def test_every_spawning_script_is_allowlisted_or_uses_run_budget(self):
        spawners, violations = analyse_scripts()
        unlisted = [p for p, hits in spawners.items() if p not in SPAWN_ALLOWLIST and "<uses run_budget>" not in hits]
        self.assertEqual(unlisted, [], "scripts que lançam processos sem usar run_budget nem estar autorizados")
        self.assertEqual(violations, {}, "scripts que usam run_budget mas lançam fora de spawn=")

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
                "pool.py": "from concurrent.futures import ProcessPoolExecutor\n",
                "pool_attr.py": "import concurrent.futures as cf\ncf.ProcessPoolExecutor()\n",
                "dynamic.py": "m = __import__('subprocess')\n",
                "importlib_user.py": "import importlib\nimportlib.import_module('x')\n",
                "mp.py": "import multiprocessing\n",
                "budgeted.py": ("import subprocess\nimport run_budget\n"
                                "def spawn(item):\n    return subprocess.run(['x', str(item)])\n"
                                "run_budget.run_budgeted('c', [1], spawn)\n"),
                "clean.py": "import json\n",
            }
            for name, text in files.items():
                (base / name).write_text(text, encoding="utf-8")
            spawners, violations = analyse_scripts(base)
            self.assertEqual(sorted(spawners), sorted(f"scripts/{n}" for n in files if n != "clean.py"))
            self.assertIn("<uses run_budget>", spawners["scripts/budgeted.py"])
            self.assertNotIn("<uses run_budget>", spawners["scripts/new_spawner.py"])
            self.assertEqual(violations, {})

    def test_run_budget_users_must_spawn_only_inside_the_spawn_function(self):
        cases = {
            "top_level.py": "import subprocess\nimport run_budget\nsubprocess.run(['x'])\n"
                            "def spawn(i):\n    return i\nrun_budget.run_budgeted('c', [1], spawn)\n",
            "other_function.py": "import subprocess\nimport run_budget\ndef spawn(i):\n    return i\n"
                                 "def helper():\n    subprocess.run(['x'])\nrun_budget.run_budgeted('c', [1], spawn)\n",
            "reserve_only.py": "import subprocess\nimport run_budget\nrun_budget.reserve('c', [1])\nsubprocess.run(['x'])\n",
            "from_import.py": "from subprocess import run\nimport run_budget\ndef spawn(i):\n    return run(['x'])\n"
                              "run_budget.run_budgeted('c', [1], spawn)\n",
        }
        good = {"keyword.py": "import subprocess\nimport run_budget\ndef go(i):\n    return subprocess.run(['x'])\n"
                              "run_budget.run_budgeted('c', [1], spawn=go)\n",
                "lambda_user.py": "import subprocess\nimport run_budget\n"
                                  "run_budget.run_budgeted('c', [1], lambda i: subprocess.run(['x']))\n"}
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "scripts"
            base.mkdir()
            for name, text in {**cases, **good}.items():
                (base / name).write_text(text, encoding="utf-8")
            _, violations = analyse_scripts(base)
            self.assertEqual(sorted(violations), sorted(f"scripts/{n}" for n in cases))

    def test_allowlist_has_no_stale_entries_and_every_entry_has_a_reason(self):
        found = spawning_scripts()
        for path, reason in SPAWN_ALLOWLIST.items():
            with self.subTest(path=path):
                self.assertIn(path, found, "entrada obsoleta: o ficheiro já não lança processos")
                self.assertGreater(len(reason.split()), 3)
                self.assertNotIn(chr(0x2014), reason)


if __name__ == "__main__":
    unittest.main()
