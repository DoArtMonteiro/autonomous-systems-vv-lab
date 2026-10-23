from __future__ import annotations

import copy
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import adversarial_campaign as ac  # noqa: E402
from process_limits import ProcessLimitError  # noqa: E402


REDUCTION = {
    "atoms": {"before": 4, "after": 1},
    "active_fault_ticks": {"before": 20, "after": 5},
    "steps": {"before": 100, "after": 50},
}


def make_doc(control_violations: int = 0, recheck: str = "agree", **overrides):
    """A campaign.json in the engine's real shape."""
    doc = {
        "schema": ac.CAMPAIGN_SCHEMA,
        "campaign_sha256": "a" * 64,
        "control": [
            {"policy": "dominant_axis", "violations": ["p"] * control_violations},
            {"policy": "x_first", "violations": []},
        ],
        "metrics": {
            "candidates": 10,
            "evaluations": {"control": 2, "search": 16, "minimization": 1, "case_artifacts": 1, "total": 20},
            "violating_candidates": 4,
            "violations_by_policy": {
                "dominant_axis": {"temporal:stop_response": 3},
                "x_first": {"temporal:stop_response": 1, "temporal:mission_progress": 2},
            },
            "unique_classes_found": 2,
            "novel_classes_found": 2,
            "inherited_classes_found": 0,
            "unidentified_violations": 0,
            "unique_classes_kept": 2,
            "inconclusive_evaluations": 5,
            "control_violations": control_violations,
            "recheck": {recheck: 1, "not_applicable": 1},
        },
        "failures": [
            {"identity": {"policy": "dominant_axis"}, "recheck": {"result": recheck}, "inherited_from_control": False, "reduction": copy.deepcopy(REDUCTION)},
            {"identity": {"policy": "x_first"}, "recheck": {"result": "not_applicable"}, "inherited_from_control": False, "reduction": copy.deepcopy(REDUCTION)},
        ],
        "policy_matrix": {
            "temporal:stop_response": {"both": 3, "neither": 4, "only:dominant_axis": 1, "only:x_first": 2},
            "temporal:mission_progress": {"both": 1, "neither": 8, "only:x_first": 1},
        },
    }
    doc.update(overrides)
    return doc


def with_metrics(**metrics):
    doc = make_doc()
    doc["metrics"].update(metrics)
    return doc


class PlanTests(unittest.TestCase):
    def test_default_plan_counts_invocations_before_running(self):
        plan = ac.plan_campaign((42, 1337, 2026))
        self.assertEqual(plan["planned_pairs"], 9)
        self.assertEqual(plan["max_replay_m4_invocations"], 9 * 2 * 4)
        self.assertEqual(plan["max_total_invocations"], 18 + 9 + 72)
        self.assertEqual(plan["time_budget_seconds"], 300.0)

    def test_plan_rejects_invalid_budgets(self):
        cases = [
            ({"budget": 0}, "budget"),
            ({"budget": 513}, "budget"),
            ({"minimize_budget": 257}, "minimize_budget"),
            ({"max_failures": 17}, "max_failures"),
            ({"time_budget_seconds": 301}, "time_budget_seconds"),
            ({"time_budget_seconds": 0}, "time_budget_seconds"),
            ({"time_budget_seconds": float("nan")}, "time_budget_seconds"),
            ({"max_artifact_bytes": ac.MAX_ARTIFACT_BYTES + 1}, "max_artifact_bytes"),
            ({"max_artifact_bytes": 10}, "max_artifact_bytes"),
            ({"max_invocations": 50}, "needs up to"),
            ({"max_pairs": 2}, "above max_pairs"),
            ({"max_invocations": ac.MAX_INVOCATIONS + 1}, "max_invocations"),
        ]
        for kwargs, message in cases:
            with self.subTest(kwargs=kwargs):
                with self.assertRaisesRegex(ac.AdversarialCampaignError, message):
                    ac.plan_campaign((42, 1337, 2026), **kwargs)

    def test_plan_rejects_bad_seeds(self):
        for seeds in ((), (1, 1), (2**64,), (-1,)):
            with self.subTest(seeds=seeds):
                with self.assertRaises(ac.AdversarialCampaignError):
                    ac.plan_campaign(seeds)

    def test_matrix_inputs_exist_and_match_expectations_file(self):
        ac.check_case_inputs(ac.CASES)
        expectations = json.loads((ROOT / "scenarios/m3/expectations.json").read_text(encoding="utf-8"))
        by_scenario = {(c["scenario"], c["contract_set"], c["fault_combination"]): c for c in expectations["cases"]}
        clean = next(c for c in ac.CASES if c.role == ac.ROLE_CLEAN)
        faulty = next(c for c in ac.CASES if c.role == ac.ROLE_KNOWN_FAULTY)
        self.assertEqual(
            by_scenario[("nominal-stop.json", "nominal", "nominal")]["expected_by_seed"]["42"]["temporal"], "PASS"
        )
        self.assertEqual(clean.scenario, "scenarios/m3/nominal-stop.json")
        entry = by_scenario[("delayed-after-fallback.json", "nominal", "delayed-movement")]
        self.assertEqual(entry["expected_by_seed"]["42"]["temporal"], "FAIL")
        self.assertEqual(faulty.actuator, "scenarios/m3/" + expectations["fault_combinations"]["delayed-movement"])
        self.assertEqual(faulty.contracts, "scenarios/m3/" + expectations["contract_sets"]["nominal"])

    def test_check_case_inputs_rejects_missing_file(self):
        bad = (ac.Case("x", ac.ROLE_CLEAN, "scenarios/none.json", "scenarios/m3/contracts-nominal.json", None),)
        with self.assertRaisesRegex(ac.AdversarialCampaignError, "missing input"):
            ac.check_case_inputs(bad)


class TreeTests(unittest.TestCase):
    def test_identical_trees_and_each_kind_of_difference(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp, "a"), Path(tmp, "b")
            for base in (a, b):
                (base / "sub").mkdir(parents=True)
                (base / "x.json").write_text("one", encoding="utf-8")
                (base / "sub" / "y.json").write_text("two", encoding="utf-8")
            same = ac.compare_trees(a, b)
            self.assertEqual((same["files_total"], same["files_identical"], same["difference_count"]), (2, 2, 0))

            (b / "x.json").write_text("changed", encoding="utf-8")
            (b / "extra.json").write_text("e", encoding="utf-8")
            (a / "only-first.json").write_text("f", encoding="utf-8")
            result = ac.compare_trees(a, b)
            self.assertEqual(result["files_total"], 4)
            self.assertEqual(result["files_identical"], 1)
            self.assertEqual(
                result["differences"],
                [
                    {"path": "extra.json", "kind": "missing_in_first"},
                    {"path": "only-first.json", "kind": "missing_in_repeat"},
                    {"path": "x.json", "kind": "content_differs"},
                ],
            )

    def test_missing_tree_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = ac.compare_trees(Path(tmp, "nope"), Path(tmp, "nada"))
            self.assertEqual(result["files_total"], 0)


class AggregationTests(unittest.TestCase):
    def test_aggregates_real_shape(self):
        agg = ac.aggregate_campaign(make_doc())
        self.assertEqual(agg["problems"], [])
        self.assertEqual((agg["candidates"], agg["evaluations"]), (10, 20))
        self.assertEqual(agg["violations_by_policy"], {"dominant_axis": 3, "x_first": 3})
        self.assertEqual(
            agg["violations_by_property"], {"temporal:mission_progress": 2, "temporal:stop_response": 4}
        )
        self.assertEqual((agg["unique_failure_classes"], agg["inconclusive"], agg["control_violations"]), (2, 5, 0))
        self.assertEqual(agg["recheck"], {"agree": 1, "disagree": 0, "not_applicable": 1})
        self.assertEqual(agg["reduction"]["failures_with_metrics"], 2)
        self.assertEqual(agg["reduction"]["totals"]["atoms"], {"before": 8, "after": 2, "percent": 75.0})
        self.assertEqual(agg["reduction"]["totals"]["steps"]["percent"], 50.0)
        self.assertEqual(
            agg["policy_matrix_totals"],
            {"both": 4, "neither": 12, "only:dominant_axis": 1, "only:x_first": 3},
        )

    def test_class_split_and_unidentified_fields_are_required(self):
        present = ac.aggregate_campaign(make_doc())
        self.assertEqual(present["problems"], [])
        self.assertEqual(
            (present["novel_classes"], present["inherited_classes"], present["unidentified_violations"]), (2, 0, 0)
        )
        doc = make_doc()
        for key in ("novel_classes_found", "inherited_classes_found", "unidentified_violations"):
            del doc["metrics"][key]
        del doc["failures"][0]["inherited_from_control"]
        self.assertEqual(len(ac.aggregate_campaign(doc)["problems"]), 4)

    def test_class_fields_malformed_or_inconsistent_are_problems(self):
        doc = with_metrics(novel_classes_found="1", unidentified_violations=True)
        doc["failures"][0]["inherited_from_control"] = "yes"
        self.assertEqual(len(ac.aggregate_campaign(doc)["problems"]), 3)
        problems = ac.aggregate_campaign(with_metrics(novel_classes_found=99))["problems"]
        self.assertEqual(problems, ["metrics: novel_classes_found + inherited_classes_found != unique_classes_found"])

    def test_oversized_integer_is_a_document_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "campaign.json"
            path.write_text('{"a": ' + "1" * 5000 + "}", encoding="utf-8")
            with self.assertRaises(ac.CampaignDocError):
                ac.load_campaign_json(path)

    def test_disagreement_is_surfaced(self):
        agg = ac.aggregate_campaign(make_doc(recheck="disagree"))
        self.assertEqual(agg["recheck"]["disagree"], 1)
        self.assertEqual(agg["recheck_disagreements"][0]["failure_index"], 0)
        self.assertEqual(agg["recheck_disagreements"][0]["identity"], {"policy": "dominant_axis"})

    def test_wrong_schema_and_garbage_do_not_raise(self):
        garbage = {"schema": "other", "metrics": "x", "failures": 3, "control": 7, "policy_matrix": [1]}
        agg = ac.aggregate_campaign(garbage)
        self.assertTrue(any("schema" in p for p in agg["problems"]))
        self.assertIsNone(agg["control_violations"])
        self.assertIsNone(agg["candidates"])
        self.assertIsNone(agg["violations_by_policy"])
        for odd in ({}, {"failures": [1, None, "x"], "metrics": {"evaluations": []}}, {"policy_matrix": {"a": 5}}):
            with self.subTest(odd=odd):
                self.assertTrue(ac.aggregate_campaign(odd)["problems"])

    def test_bool_and_negative_counts_are_rejected(self):
        doc = make_doc()
        doc["metrics"]["candidates"] = True
        doc["metrics"]["evaluations"]["total"] = -1
        doc["policy_matrix"]["temporal:stop_response"]["both"] = True
        agg = ac.aggregate_campaign(doc)
        self.assertIsNone(agg["candidates"])
        self.assertIsNone(agg["evaluations"])
        self.assertIsNone(agg["policy_matrix"])
        self.assertEqual(len(agg["problems"]), 3)

    def test_no_fallback_for_missing_control_violations(self):
        doc = make_doc(control_violations=2)
        del doc["metrics"]["control_violations"]
        agg = ac.aggregate_campaign(doc)
        self.assertIsNone(agg["control_violations"])
        self.assertTrue(agg["problems"])

    def test_bad_recheck_and_reduction_are_problems(self):
        doc = make_doc()
        doc["failures"][0]["recheck"]["result"] = "maybe"
        del doc["failures"][1]["reduction"]["steps"]
        agg = ac.aggregate_campaign(doc)
        self.assertEqual(len(agg["problems"]), 2, agg["problems"])
        self.assertEqual(agg["recheck"], {"agree": 0, "disagree": 0, "not_applicable": 1})
        self.assertEqual(agg["reduction"]["failures_with_metrics"], 1)

    def test_more_failures_than_the_engine_cap_is_a_problem(self):
        doc = make_doc()
        doc["failures"] = doc["failures"][:1] * (ac.MAX_FAILURES_RANGE[1] + 1)
        agg = ac.aggregate_campaign(doc)
        self.assertEqual(sum(agg["recheck"].values()), ac.MAX_FAILURES_RANGE[1])
        self.assertTrue(any("engine cap" in p for p in agg["problems"]))

    def test_document_failures_cover_problems_disagreement_and_unidentified(self):
        self.assertEqual(ac.document_failures(ac.aggregate_campaign(make_doc())), [])
        disagree = ac.document_failures(ac.aggregate_campaign(make_doc(recheck="disagree")))
        self.assertEqual(len(disagree), 1)
        self.assertIn("disagreed", disagree[0])
        unidentified = ac.document_failures(ac.aggregate_campaign(with_metrics(unidentified_violations=3)))
        self.assertIn("3 violation(s)", unidentified[0])
        self.assertEqual(ac.document_failures(ac.aggregate_campaign(with_metrics(unidentified_violations=0))), [])
        self.assertIn("invalid", ac.document_failures(ac.aggregate_campaign({}))[0])

    def test_percent_reduction_edge_cases(self):
        self.assertIsNone(ac.percent_reduction(0, 0))
        self.assertIsNone(ac.percent_reduction(2, 3))
        self.assertEqual(ac.percent_reduction(3, 1), 66.67)

    def test_load_campaign_json_rejects_non_objects(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "campaign.json")
            path.write_text("[1]", encoding="utf-8")
            with self.assertRaises(ac.CampaignDocError):
                ac.load_campaign_json(path)
            path.write_text("{", encoding="utf-8")
            with self.assertRaises(ac.CampaignDocError):
                ac.load_campaign_json(path)
            with self.assertRaises(ac.CampaignDocError):
                ac.load_campaign_json(Path(tmp, "missing.json"))


class ControlExpectationTests(unittest.TestCase):
    def test_clean_base(self):
        self.assertTrue(ac.evaluate_control(ac.ROLE_CLEAN, 0)[0])
        self.assertFalse(ac.evaluate_control(ac.ROLE_CLEAN, 1)[0])
        self.assertFalse(ac.evaluate_control(ac.ROLE_CLEAN, None)[0])

    def test_known_faulty_base(self):
        self.assertTrue(ac.evaluate_control(ac.ROLE_KNOWN_FAULTY, 1)[0])
        self.assertFalse(ac.evaluate_control(ac.ROLE_KNOWN_FAULTY, 0)[0])
        self.assertFalse(ac.evaluate_control(ac.ROLE_KNOWN_FAULTY, None)[0])

    def test_divergence_base_and_unknown_role(self):
        self.assertTrue(ac.evaluate_control(ac.ROLE_DIVERGENCE, None)[0])
        self.assertTrue(ac.evaluate_control(ac.ROLE_DIVERGENCE, 5)[0])
        self.assertFalse(ac.evaluate_control("bogus", 0)[0])


class FakeBinaries:
    """Stands in for run_bounded_process and writes synthetic campaign trees."""

    def __init__(self, *, repeat_differs=False, replay_code=0, m4_code=0, faulty_control=1, clean_control=0,
                 doc=None, case_dirs=1):
        self.repeat_differs = repeat_differs
        self.replay_code = replay_code
        self.m4_code = m4_code
        self.faulty_control = faulty_control
        self.clean_control = clean_control
        self.doc = doc
        self.case_dirs = case_dirs
        self.commands: list[list[str]] = []
        self.campaign_runs = 0

    def __call__(self, command, *, cwd, timeout_seconds, max_output_bytes, description):
        self.commands.append(list(command))
        sub = command[1]
        code = 0
        if sub == "campaign":
            self.campaign_runs += 1
            out = Path(command[command.index("--output") + 1])
            base = command[command.index("--base") + 1]
            violations = self.faulty_control if "delayed-after-fallback" in base else self.clean_control
            out.mkdir(parents=True)
            for index in range(self.case_dirs):
                for side in ("original", "minimized"):
                    (out / "cases" / f"{index:02d}-x" / side).mkdir(parents=True)
                    (out / "cases" / f"{index:02d}-x" / side / "m4.json").write_text("{}", encoding="utf-8")
            doc = make_doc(control_violations=violations) if self.doc is None else self.doc
            (out / "campaign.json").write_text(json.dumps(doc), encoding="utf-8")
            if self.repeat_differs and self.campaign_runs % 2 == 0:
                (out / "report.md").write_text("different", encoding="utf-8")
            else:
                (out / "report.md").write_text("same", encoding="utf-8")
        elif sub == "replay":
            code = self.replay_code
        elif sub == "replay-m4":
            code = self.m4_code
        return SimpleNamespace(returncode=code, stdout="", stderr="")


def run_fake(fake, *, seeds=(42,), cases=ac.CASES, **plan_kwargs):
    tmp = tempfile.TemporaryDirectory()
    plan = ac.plan_campaign(seeds, cases=cases, **plan_kwargs)
    campaign = ac.Campaign(
        Path("vv-adversary"), Path("vv-lab"), Path(tmp.name, "out"), seeds, plan, cases=cases
    )
    with patch("adversarial_campaign.run_bounded_process", fake):
        summary = campaign.run()
    return tmp, campaign, summary


class CampaignRunTests(unittest.TestCase):
    def test_all_checks_pass_with_good_binaries(self):
        fake = FakeBinaries()
        tmp, campaign, summary = run_fake(fake)
        with tmp:
            det = summary["deterministic"]
            self.assertEqual(det["status"], "passed", det["failed_pairs"])
            self.assertEqual(det["executed_pairs"], 3)
            pair = det["pairs"][0]
            self.assertEqual(pair["determinism"]["files_total"], pair["determinism"]["files_identical"])
            self.assertEqual(pair["replay_m4"], {"checked": 2, "passed": 2, "failed": []})
            # 3 pairs x (2 campaigns + 1 replay + 2 replay-m4)
            self.assertEqual(campaign.invocations, 15)
            self.assertEqual(len(summary["timing"]["commands"]), 15)
            self.assertEqual(summary["timing"]["campaigns"][0]["evaluations"], 20)
            self.assertIn("seconds_per_evaluation", summary["timing"]["campaigns"][0])
            # measured values live only in the timing block
            self.assertNotIn("first_seconds", json.dumps(det))
            self.assertNotIn("seconds_per_evaluation", json.dumps(det))
            ac.write_reports(campaign.root, summary)
            self.assertEqual(json.loads((campaign.root / "summary.json").read_text())["schema"], ac.SUMMARY_SCHEMA)
            markdown = (campaign.root / "summary.md").read_text()
            self.assertIn("| clean-nominal | 42 | ok |", markdown)
            self.assertNotIn("\u2014", markdown)

    def test_sim_seed_defaults_to_campaign_seed_and_can_be_overridden(self):
        fake = FakeBinaries()
        tmp, _, _ = run_fake(fake, seeds=(7,))
        with tmp:
            command = fake.commands[0]
            self.assertEqual(command[command.index("--campaign-seed") + 1], "7")
            self.assertEqual(command[command.index("--sim-seed") + 1], "7")
            self.assertEqual(command[command.index("--budget") + 1], str(ac.DEFAULT_BUDGET))
        fake = FakeBinaries()
        plan = ac.plan_campaign((7,))
        with tempfile.TemporaryDirectory() as dir_, patch("adversarial_campaign.run_bounded_process", fake):
            ac.Campaign(Path("a"), Path("b"), Path(dir_, "o"), (7,), plan, sim_seed=99).run()
        self.assertEqual(fake.commands[0][fake.commands[0].index("--sim-seed") + 1], "99")

    def test_nondeterministic_repeat_fails_and_lists_path(self):
        tmp, _, summary = run_fake(FakeBinaries(repeat_differs=True))
        with tmp:
            det = summary["deterministic"]
            self.assertEqual(det["status"], "failed")
            self.assertEqual(det["pairs"][0]["determinism"]["differences"], [{"path": "report.md", "kind": "content_differs"}])
            self.assertTrue(any("determinism" in m for m in det["pairs"][0]["failures"]))

    def test_replay_failures_fail_the_run(self):
        for kwargs, message in (({"replay_code": 3}, "replay exited 3"), ({"m4_code": 1}, "replay-m4 failed")):
            with self.subTest(kwargs=kwargs):
                tmp, _, summary = run_fake(FakeBinaries(**kwargs))
                with tmp:
                    self.assertEqual(summary["deterministic"]["status"], "failed")
                    self.assertTrue(any(message in m for m in summary["deterministic"]["pairs"][0]["failures"]))

    def test_clean_control_violation_fails(self):
        tmp, _, summary = run_fake(FakeBinaries(clean_control=2))
        with tmp:
            det = summary["deterministic"]
            self.assertEqual(det["status"], "failed")
            self.assertEqual(det["failed_pairs"], ["clean-nominal/seed-42"])
            self.assertFalse(det["pairs"][0]["control_expectation"]["ok"])

    def test_known_faulty_control_without_violation_fails(self):
        tmp, _, summary = run_fake(FakeBinaries(faulty_control=0))
        with tmp:
            det = summary["deterministic"]
            self.assertEqual(det["failed_pairs"], ["known-faulty-delayed-after-fallback/seed-42"])

    def test_recheck_disagreement_fails_the_pair(self):
        tmp, _, summary = run_fake(FakeBinaries(doc=make_doc(recheck="disagree")))
        with tmp:
            det = summary["deterministic"]
            self.assertEqual(det["status"], "failed")
            self.assertEqual(len(det["failed_pairs"]), 3)
            self.assertEqual(det["recheck_disagreements_total"], 3)
            self.assertTrue(any("disagreed" in m for m in det["pairs"][0]["failures"]))

    def test_unidentified_violations_fail_the_pair_and_zero_passes(self):
        tmp, _, summary = run_fake(FakeBinaries(doc=with_metrics(unidentified_violations=2)))
        with tmp:
            self.assertEqual(summary["deterministic"]["status"], "failed")
            self.assertTrue(any("without an identified class" in m for m in summary["deterministic"]["pairs"][0]["failures"]))
        doc = with_metrics(novel_classes_found=1, inherited_classes_found=1, unidentified_violations=0)
        tmp, campaign, summary = run_fake(FakeBinaries(doc=doc), cases=ac.CASES[:1])
        with tmp:
            self.assertEqual(summary["deterministic"]["status"], "passed", summary["deterministic"]["pairs"][0]["failures"])
            ac.write_reports(campaign.root, summary)
            markdown = (campaign.root / "summary.md").read_text()
            self.assertIn("| novel | inherited | unidentified |", markdown)

    def test_invalid_campaign_document_fails_the_pair(self):
        tmp, _, summary = run_fake(FakeBinaries(doc={"schema": "other"}))
        with tmp:
            pair = summary["deterministic"]["pairs"][0]
            self.assertEqual(summary["deterministic"]["status"], "failed")
            self.assertTrue(any("campaign.json invalid" in m for m in pair["failures"]))
            self.assertFalse(pair["control_expectation"]["ok"])

    def test_case_artifact_checks(self):
        tmp, _, summary = run_fake(FakeBinaries(case_dirs=5))  # above max_failures 4
        with tmp:
            failures = summary["deterministic"]["pairs"][0]["failures"]
            self.assertTrue(any("above max_failures" in m for m in failures))
            self.assertEqual(summary["deterministic"]["pairs"][0]["replay_m4"]["checked"], 8)
        tmp, _, summary = run_fake(FakeBinaries(case_dirs=0))
        with tmp:
            self.assertEqual(summary["deterministic"]["pairs"][0]["replay_m4"]["checked"], 0)

    def test_campaign_exit_nonzero_stops_pair(self):
        def failing(command, **kwargs):
            return SimpleNamespace(returncode=2, stdout="", stderr="bad input")

        tmp, _, summary = run_fake(failing)
        with tmp:
            self.assertEqual(summary["deterministic"]["status"], "failed")
            self.assertIn("exited 2", summary["deterministic"]["pairs"][0]["failures"][0])

    def test_process_limit_aborts_and_reports(self):
        def timing_out(command, **kwargs):
            raise ProcessLimitError("campaign exceeded the 1-second timeout")

        tmp, _, summary = run_fake(timing_out)
        with tmp:
            det = summary["deterministic"]
            self.assertEqual(det["status"], "failed")
            self.assertIn("timeout", det["abort_reason"])
            self.assertEqual(det["executed_pairs"], 1)

    def test_invocation_budget_is_enforced_at_runtime(self):
        fake = FakeBinaries()
        tmp = tempfile.TemporaryDirectory()
        plan = ac.plan_campaign((42,))
        plan["max_invocations"] = 2
        campaign = ac.Campaign(Path("a"), Path("b"), Path(tmp.name, "o"), (42,), plan)
        with tmp, patch("adversarial_campaign.run_bounded_process", fake):
            summary = campaign.run()
        self.assertEqual(summary["deterministic"]["abort_reason"], "campaign would exceed its invocation budget")
        self.assertEqual(len(fake.commands), 2)

    def test_expired_time_budget_aborts_before_starting_a_process(self):
        fake = FakeBinaries()
        tmp = tempfile.TemporaryDirectory()
        plan = ac.plan_campaign((42,))
        campaign = ac.Campaign(Path("a"), Path("b"), Path(tmp.name, "o"), (42,), plan)
        campaign.deadline = campaign.start - 1
        with tmp, patch("adversarial_campaign.run_bounded_process", fake):
            summary = campaign.run()
        self.assertEqual(summary["deterministic"]["abort_reason"], "campaign exceeded its time budget")
        self.assertEqual(fake.commands, [])


class MainTests(unittest.TestCase):
    def run_main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = ac.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_missing_binary_is_a_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _, err = self.run_main(
                ["--binary", str(Path(tmp, "none")), "--lab-binary", str(Path(tmp, "none2")), "--output-root", str(Path(tmp, "o"))]
            )
            self.assertEqual(code, 2)
            self.assertIn("does not exist", err)
            self.assertFalse(Path(tmp, "o").exists())

    def test_non_empty_output_root_is_rejected_without_running(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_bin = Path(tmp, "bin")
            fake_bin.write_text("", encoding="utf-8")
            out = Path(tmp, "o")
            out.mkdir()
            (out / "x").write_text("1", encoding="utf-8")
            with patch("adversarial_campaign.run_bounded_process") as run:
                code, _, err = self.run_main(
                    ["--binary", str(fake_bin), "--lab-binary", str(fake_bin), "--output-root", str(out)]
                )
            self.assertEqual(code, 2)
            self.assertIn("empty or absent", err)
            run.assert_not_called()

    def test_over_budget_arguments_are_rejected_before_any_process(self):
        with patch("adversarial_campaign.run_bounded_process") as run:
            code, _, err = self.run_main(["--time-budget-seconds", "301"])
            self.assertEqual(code, 2)
            code, _, _ = self.run_main(["--budget", "9999"])
            self.assertEqual(code, 2)
        run.assert_not_called()

    def test_exit_codes_follow_summary_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_bin = Path(tmp, "bin")
            fake_bin.write_text("", encoding="utf-8")
            for fake, expected in ((FakeBinaries(), 0), (FakeBinaries(replay_code=1), 1)):
                out = Path(tmp, f"o{expected}")
                with patch("adversarial_campaign.run_bounded_process", fake):
                    code, stdout, _ = self.run_main(
                        ["--binary", str(fake_bin), "--lab-binary", str(fake_bin), "--output-root", str(out), "--seeds", "42"]
                    )
                self.assertEqual(code, expected)
                self.assertTrue((out / "summary.json").is_file())
                self.assertTrue((out / "summary.md").is_file())
                self.assertEqual(json.loads(stdout)["status"], "passed" if expected == 0 else "failed")


ADVERSARY = ac.default_binary("vv-adversary")
LAB = ac.default_binary("vv-lab")


@unittest.skipUnless(ADVERSARY.is_file() and LAB.is_file(), "release binaries vv-adversary and vv-lab are not built")
class RealBinaryIntegrationTests(unittest.TestCase):
    def test_tiny_matrix_runs_against_real_binaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp, "out")
            stdout, stderr = io.StringIO(), io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = ac.main(
                    [
                        "--seeds", "42", "--budget", "4", "--minimize-budget", "8", "--max-failures", "2",
                        "--time-budget-seconds", "240", "--output-root", str(out),
                    ]
                )
            summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(code, 0, summary["deterministic"]["pairs"])
            for pair in summary["deterministic"]["pairs"]:
                self.assertEqual(pair["failures"], [])
                self.assertEqual(pair["determinism"]["difference_count"], 0)


if __name__ == "__main__":
    unittest.main()
