from __future__ import annotations

import copy
import io
import sys
import unittest
from contextlib import redirect_stderr
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import m6_analysis as ma  # noqa: E402
import m6_px4_export as px4  # noqa: E402
import m6_repair_lab as lab  # noqa: E402
import m6_report as mr  # noqa: E402

Z95 = ma.Z[50]
V = "temporal/fallback_response/none"
NEW = "safety/world_bounds/none"


def row(violations=(), mission="completed", distance=None, movement=6):
    return {
        "violations": list(violations),
        "first_violation_tick": None,
        "inconclusive": [],
        "untriggered": [],
        "mission": mission,
        "completion_tick": 10 if mission == "completed" else None,
        "waypoints_completed": 1,
        "fallback_ticks": 0,
        "movement_ticks": movement,
        "actuator_fault_events": 0,
        "distance_remaining_mm": distance,
    }


def corpus_item(status: str) -> dict:
    return {
        "id": "corpus/s/01",
        "suite": "s",
        "found_on": "baseline",
        "class": V,
        "sim_seed": 42,
        "source_workload": 0,
        "identity": {
            "policy": "dominant_axis",
            "kind": "temporal",
            "property": "fallback_response",
            "trigger_tick": 3,
            "deadline_tick": 5,
            "violation_tick": 6,
            "trigger_event_kind": None,
            "mechanism": [],
        },
        "atoms": [{"uid": 1, "kind": "comm_delay", "min": 1, "max": 3}],
        "steps": 12,
        "reduction": {
            "atoms_before": 3,
            "atoms_after": 1,
            "steps_before": 16,
            "steps_after": 12,
            "evaluations": 9,
            "exhausted": False,
            "one_minimal_verified": True,
        },
        "recheck": {"result": "agree"},
        "evidence": {"expected": "fallback by tick 5", "observed": "nominal at tick 6"},
        "causal_trace": [],
        "case_dir": "cases/corpus/s/01",
        "m4_sha256": "0" * 64,
        "replay": {"baseline": {"status": "persisted"}, "cand": {"status": status}},
    }


def evidence(base_rows, cand_rows, splits, corpus_status="resolved", introduced=(), changes_oracle=False):
    workloads = [
        {"index": i, "split": split, "seed": 1, "draw": 0, "family": "sensor", "atoms": []}
        for i, split in enumerate(splits)
    ]
    item = corpus_item(corpus_status)
    extra = [{**copy.deepcopy(item), "id": f"introduced/s/cand/{n}", "found_on": "cand", "class": c} for n, c in enumerate(introduced)]
    acceptance = {
        "alpha_permille": 50,
        "max_completion_loss_permille": 10,
        "max_mean_distance_increase_mm": 100,
        "min_heldout_pairs": 1,
    }
    config = {"policy": "dominant_axis", "rationale": "r", "effective": {}, "role": "candidate", "expect": {}}
    return {
        "schema": "vv-repair.evidence.v1",
        "evidence_sha256": "e" * 64,
        "source_sha256": "s" * 64,
        "experiment_sha256": "x" * 64,
        "experiment": {
            "suites": [{"id": "s"}],
            "acceptance": acceptance,
            "baseline": {"id": "baseline"},
            "candidates": [{"id": "cand"}],
            "tuning_seeds": [1],
            "heldout_seeds": [2],
            "sim_seeds": [42],
            "max_corpus_per_suite": 8,
        },
        "configs": [
            {**config, "id": "baseline", "overrides": {}, "config_sha256": "a" * 64, "changes_oracle": False},
            {**config, "id": "cand", "overrides": {"fallback_after_ticks": 2}, "config_sha256": "b" * 64, "changes_oracle": changes_oracle},
        ],
        "suites": [{"id": "s", "scenario_name": "synthetic", "description": "<b>suite</b>"}],
        "workloads": {"s": workloads},
        "results": {"s": {"baseline": {"42": base_rows}, "cand": {"42": cand_rows}}},
        "corpus": [item],
        "introduced": extra,
        "totals": {"workloads": len(workloads), "evaluations": 1, "minimization_evaluations": 0, "unidentified_violations": 0},
    }


class StatisticsTest(unittest.TestCase):
    def test_wilson_and_mcnemar(self):
        self.assertIsNone(ma.wilson(0, 0, Z95)["rate"])
        interval = ma.wilson(5, 10, Z95)
        self.assertAlmostEqual(interval["rate"], 0.5)
        self.assertAlmostEqual(interval["low"], 0.236593, places=5)
        self.assertEqual(ma.mcnemar_exact(0, 0), 1.0)
        self.assertAlmostEqual(ma.mcnemar_exact(5, 0), 0.0625)
        self.assertEqual(ma.mcnemar_exact(3, 7), ma.mcnemar_exact(7, 3))

    def test_risk_difference_sign_and_interval(self):
        better = ma.paired_risk_difference(fixed=20, broken=0, n=100, z=Z95)
        self.assertLess(better["estimate"], 0)
        self.assertLess(better["high"], 0)
        self.assertIsNone(ma.paired_risk_difference(0, 0, 0, Z95)["estimate"])

    def test_compare_counts_pairs(self):
        pairs = [(row([V]), row()), (row(), row([NEW])), (row(), row(mission="incomplete", distance=500))]
        result = ma.compare(pairs, Z95)
        self.assertEqual((result["fixed"], result["broken"], result["unchanged"]), (1, 1, 1))
        self.assertEqual(result["completion_lost"], 1)
        self.assertEqual(result["pairs_with_new_class"], 1)
        self.assertAlmostEqual(result["distance_increase_mm"]["mean"], 500 / 3, places=4)


class VerdictTest(unittest.TestCase):
    def analyse(self, base, cand, splits=None, **kwargs):
        splits = splits or ["heldout"] * len(base)
        return ma.analyze(evidence(base, cand, splits, **kwargs))["candidates"][0]

    def test_clean_improvement_is_accepted(self):
        result = self.analyse([row([V])] * 30 + [row()] * 30, [row()] * 60)
        self.assertEqual(result["verdict"]["decision"], "accept")
        self.assertEqual(result["verdict"]["safety"], "improved")

    def test_paralysis_is_rejected_on_progress(self):
        stalled = row(mission="incomplete", distance=1500, movement=0)
        result = self.analyse([row([V])] * 30 + [row()] * 30, [stalled] * 60)
        self.assertEqual(result["verdict"]["decision"], "reject")
        self.assertEqual(result["verdict"]["progress"], "fail")

    def test_vacuous_fixes_do_not_count_as_improvement(self):
        frozen = row(movement=0)
        result = self.analyse([row([V])] * 30 + [row()] * 30, [frozen] * 30 + [row()] * 30)
        held = result["summary"]["heldout"]
        self.assertEqual((held["fixed"], held["fixed_vacuous"]), (30, 30))
        self.assertFalse(result["gates"]["safety"])
        self.assertEqual(result["verdict"]["decision"], "reject")

    def test_oracle_changing_candidate_is_never_accepted(self):
        result = self.analyse([row([V])] * 30 + [row()] * 30, [row()] * 60, changes_oracle=True)
        self.assertEqual(result["verdict"]["safety"], "improved")
        self.assertEqual(result["verdict"]["decision"], "reject")

    def test_regression_and_new_class_are_flagged(self):
        regressed = self.analyse([row()] * 60, [row([NEW])] * 30 + [row()] * 30)
        self.assertEqual(regressed["verdict"]["safety"], "regressed")
        mixed = self.analyse([row([V])] * 30 + [row()] * 30, [row()] * 60, introduced=[NEW])
        self.assertEqual(mixed["verdict"]["safety"], "mixed")
        self.assertFalse(mixed["gates"]["no_new_class"])

    def test_unresolved_corpus_blocks_acceptance(self):
        result = self.analyse([row([V])] * 30 + [row()] * 30, [row()] * 60, corpus_status="untriggered")
        self.assertFalse(result["gates"]["corpus"])
        self.assertEqual(result["verdict"]["decision"], "reject")

    def test_overfit_and_oracle_notes(self):
        base = [row([V])] * 60
        cand = [row()] * 30 + [row([V])] * 30
        result = self.analyse(base, cand, splits=["tuning"] * 30 + ["heldout"] * 30, changes_oracle=True)
        notes = " ".join(result["verdict"]["notes"])
        self.assertIn("overfit", notes)
        self.assertIn("oracle", notes)

    def test_rows_must_match_workloads(self):
        with self.assertRaises(ValueError):
            ma.analyze(evidence([row()], [row(), row()], ["heldout"]))


class ReportTest(unittest.TestCase):
    def test_render_escapes_evidence_strings(self):
        doc = evidence([row([V])] * 4, [row()] * 4, ["heldout"] * 4)
        doc["configs"][1]["rationale"] = "<script>alert(1)</script>"
        doc["corpus"][0]["evidence"]["observed"] = "<img src=x onerror=alert(1)>"
        analysis = ma.analyze(doc)
        html = mr.render(doc, analysis, {"timing_ms": {"cand": 5}, "checks": {"replay": "OK"}})
        self.assertNotIn("<script>alert", html)
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("Can a controller change fix known failures", html)

    def test_causal_text_names_trigger_deadline_and_fault(self):
        text = mr.causal_text(corpus_item("resolved"))
        self.assertIn("triggered at tick 3", text)
        self.assertIn("observation delay 1-3 ticks", text)


class LabChecksTest(unittest.TestCase):
    def test_check_evidence_fails_closed(self):
        good = evidence([row()], [row()], ["heldout"])
        lab.check_evidence(good)
        mutations = (
            lambda d: d.update(schema="other"),
            lambda d: d["totals"].update(unidentified_violations=1),
            lambda d: d["corpus"][0]["recheck"].update(result="disagree"),
        )
        for mutate in mutations:
            doc = copy.deepcopy(good)
            mutate(doc)
            with self.assertRaises(lab.LabError):
                lab.check_evidence(doc)

    def test_schema_constants_match_the_rust_writer(self):
        rust = (ROOT / "src" / "bin" / "vv-repair" / "evidence.rs").read_text(encoding="utf-8")
        self.assertIn(f'pub const EVIDENCE_SCHEMA: &str = "{lab.EVIDENCE_SCHEMA}";', rust)
        main = (ROOT / "src" / "bin" / "vv-repair" / "main.rs").read_text(encoding="utf-8")
        self.assertIn("const MAX_EVIDENCE_BYTES: usize = 64 * 1024 * 1024;", main)
        self.assertEqual(lab.MAX_EVIDENCE_BYTES, 64 * 1024 * 1024)

    def test_display_path_never_leaks_absolute_paths(self):
        self.assertEqual(lab.display_path(ROOT / "runs" / "m6" / "run"), "runs/m6/run")
        self.assertEqual(lab.display_path(Path("/elsewhere/out/run")), "<output-root>/run")

    def test_invalid_limits_exit_two(self):
        with redirect_stderr(io.StringIO()):
            self.assertEqual(lab.main(["--output-root", "x", "--time-budget-seconds", "0"]), 2)
            self.assertEqual(lab.main(["--output-root", "x", "--max-artifact-bytes", "10"]), 2)


class Px4ExportTest(unittest.TestCase):
    SCENARIO = {
        "tick_ms": 100,
        "vehicle": {"start": {"x_mm": 1000, "y_mm": 1000}},
        "mission": {"waypoints": [{"x_mm": 2500, "y_mm": 3000}], "arrival_radius_mm": 100},
    }

    def test_gps_window_is_partial_and_link_faults_are_not_mappable(self):
        item = corpus_item("resolved")
        item["atoms"] = [{"uid": 1, "kind": "gps_dropout", "start": 4, "end": 6}]
        mapped = px4.request(item, self.SCENARIO)
        self.assertEqual(mapped["status"], "partial")
        self.assertEqual(mapped["atoms"][0]["fault"], "gps_inject_off")
        self.assertEqual(mapped["atoms"][0]["trigger_after_us_hint"], 300_000)
        self.assertEqual(mapped["mission_items"][0]["north_mm"], 2000)
        self.assertEqual(mapped["mission_items"][0]["east_mm"], 1500)
        self.assertIn("hf1", mapped["gate1a_property"])
        unmappable = px4.request(corpus_item("resolved"), self.SCENARIO)
        self.assertEqual(unmappable["status"], "not_mappable")
        self.assertIn("observation delay", unmappable["atoms"][0]["reason"])


if __name__ == "__main__":
    unittest.main()
