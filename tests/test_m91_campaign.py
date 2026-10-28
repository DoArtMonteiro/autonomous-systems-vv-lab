"""Campanha de aceitação M9.1: matriz, sorteios, pontuação, hipóteses G1 a G5 e uma execução reduzida."""

from __future__ import annotations

import json
import random
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import m91_campaign as m91  # noqa: E402
import m9_campaign as m9  # noqa: E402

BINARY = m9.binary_default()


def check(identifier, passed=True, evaluated=True):
    return {"id": identifier, "pass": passed, "evaluated": evaluated}


def verification(outcome="landed", failed_invariants=(), failed_requirements=(), unevaluated=(), flags=None):
    """Um `verification.json` v2 sintético."""
    flags = flags or {}
    requirements = [
        check(f"R{n}_x", f"R{n}" not in failed_requirements, outcome != "no_contact") for n in range(1, 7)
    ]
    invariants = [
        check(f"S{n}_x", f"S{n}" not in failed_invariants, f"S{n}" not in unevaluated) for n in range(1, 6)
    ]
    block = {"source": "controller-reported; not used for any verdict"}
    for name in m91.FLAGS:
        block[f"{name}_first"] = {"step": 10, "t_s": 0.1} if flags.get(name) else None
    return {"schema": m91.VERIFICATION_SCHEMA, "outcome": outcome, "requirements": requirements,
            "invariants": invariants, "controller_flags": block}


def cell(scenario, policy, runs=30, recovered=0, hard=None, no_contact=0, detection=None, s5=0, r1_failures=0,
         r1_met=None, containment=None):
    hard = runs - recovered - no_contact if hard is None else hard
    return {
        "scenario": scenario, "policy": policy, "runs": runs, "outcome_landed": recovered, "recovered": recovered,
        "hard_landing": hard, "no_contact": no_contact,
        "detection": {"sensor_disagreement": 0, "altimeter_rejected": 0, "ascent_abort": 0, **(detection or {})},
        "containment": runs if containment is None else containment,
        "r1_met": runs - r1_failures if r1_met is None else r1_met,
        "invariant_failures": {"S1": 0, "S2": 0, "S3": 0, "S4": 0, "S5": s5},
        "requirement_failures": {"R1": r1_failures, "R2": 0, "R3": 0, "R4": 0, "R5": 0, "R6": 0},
    }


def replace(cells, scenario, policy, **kwargs):
    return [cell(scenario, policy, **kwargs) if (c["scenario"], c["policy"]) == (scenario, policy) else c for c in cells]


def passing_cells():
    """Células sintéticas em que todas as hipóteses pré-registadas se cumprem."""
    cells = []
    for s in m91.SCENARIOS:
        for p in m91.MAIN_POLICIES:
            cells.append(cell(s, p, recovered=20))
    cells = [c for c in cells if (c["scenario"], c["policy"]) not in
             {(s, "guarded") for s in m91.DETECTION_SCENARIOS}]
    for s in m91.DETECTION_SCENARIOS:
        cells.append(cell(s, "guarded", recovered=20, detection={"sensor_disagreement": 30}))
    cells = replace(cells, "gnss_bias", "robust", recovered=0)
    cells = replace(cells, "gnss_bias", "guarded", recovered=3, detection={"sensor_disagreement": 30})
    cells.append(cell("gnss_dropout", "baseline_guarded", recovered=0, hard=30, r1_failures=30, s5=30))
    return cells


def verdicts(cells, extras=None):
    return {h["id"]: h for h in m91.evaluate_hypotheses(cells, extras)}


GOOD_IDENTITY = {"pairs_compared": 100, "identical": 100, "different": []}


class PlanTests(unittest.TestCase):
    def test_matrix_is_1050_runs_with_unique_ids(self):
        runs = m91.plan_runs(m91.DEFAULT_SEEDS)
        self.assertEqual(len(runs), 11 * 3 * 30 + 2 * 30)
        self.assertEqual(len(runs), 1050)
        self.assertEqual(len({r.key for r in runs}), 1050)
        self.assertEqual(len({r.rel for r in runs}), 1050)
        self.assertEqual((min(m91.DEFAULT_SEEDS), max(m91.DEFAULT_SEEDS)), (2000, 2029))
        self.assertEqual(len(m91.SCENARIOS), 11)
        self.assertEqual(len(m91.full_plan_keys()), 1050)

    def test_baseline_guarded_runs_only_in_the_nominal_and_gnss_dropout_scenarios(self):
        extra = [r for r in m91.plan_runs(m91.DEFAULT_SEEDS) if r.policy == "baseline_guarded"]
        self.assertEqual(len(extra), 60)
        self.assertEqual({r.fault for r in extra}, {"nominal", "gnss_dropout"})
        for scenario in m91.SCENARIOS:
            policies = {r.policy for r in m91.plan_runs((2000,), (scenario,))}
            self.assertEqual(policies, set(m91.POLICIES) if scenario in m91.EXTRA_SCENARIOS else set(m91.MAIN_POLICIES))

    def test_subset_plan_keeps_canonical_order(self):
        runs = m91.plan_runs((2000, 2001), ("gnss_dropout", "nominal"), ("guarded", "baseline_guarded"))
        self.assertEqual(len(runs), 2 * 2 * 2)
        self.assertEqual([r.fault for r in runs][:4], ["nominal"] * 4)

    def test_parsers_reject_unknown_names(self):
        self.assertEqual(m91.parse_names(m91.SCENARIOS, "s")("gnss_bias,nominal"), ("nominal", "gnss_bias"))
        with self.assertRaises(Exception):
            m91.parse_names(m91.SCENARIOS, "s")("nominal,nope")

    def test_limits_allow_the_full_plan_but_not_the_m9_ceiling(self):
        good = dict(max_runs=m91.DEFAULT_MAX_RUNS, max_artifact_bytes=2**20, time_budget_seconds=60, jobs=2,
                    runs_ceiling=m91.MAX_RUNS)
        m9.validate_limits(1050, **good)
        with self.assertRaises(m9.M9CampaignError):
            m9.validate_limits(1050, **{**good, "runs_ceiling": m9.MAX_RUNS})
        with self.assertRaisesRegex(m9.M9CampaignError, "1052 simulator runs"):
            m9.validate_limits(1050, **{**good, "max_runs": 1051})


class SamplingTests(unittest.TestCase):
    def test_draws_are_deterministic_and_inside_the_preregistered_ranges(self):
        for fault, (low, high) in (("altimeter_bias_low", (5.0, 50.0)), ("gnss_bias_low", (5.0, 30.0))):
            for seed in m91.DEFAULT_SEEDS:
                draw = m91.sample_fault(fault, seed)
                self.assertEqual(draw, m91.sample_fault(fault, seed))
                self.assertTrue(low <= draw["magnitude"] <= high, (fault, seed, draw))
                self.assertEqual((draw["start_s"], draw["end_s"]), (0.0, 40.0))
                self.assertEqual(list(draw), ["kind", "start_s", "end_s", "magnitude"])
                rng = random.Random(seed * 100 + m91.FAULTS.index(fault))
                self.assertEqual(draw["magnitude"], low + (high - low) * rng.random())

    def test_fault_indices_are_8_and_9_and_the_m9_faults_are_unchanged(self):
        self.assertEqual(m91.FAULTS.index("altimeter_bias_low"), 8)
        self.assertEqual(m91.FAULTS.index("gnss_bias_low"), 9)
        for fault in m9.FAULTS:
            self.assertEqual(m91.FAULTS.index(fault), m9.FAULTS.index(fault))
            for seed in (2000, 2017, 2029):
                self.assertEqual(m91.sample_fault(fault, seed), m9.sample_fault(fault, seed))
        with self.assertRaises(m9.M9CampaignError):
            m91.sample_fault("teleport", 2000)

    def test_gnss_bias_draws_match_the_preregistered_expectation(self):
        # The document states 3 magnitudes below 10 m (5.74, 7.69, 10.00) and one at 10.33 m.
        magnitudes = sorted(m91.sample_fault("gnss_bias", s)["magnitude"] for s in m91.DEFAULT_SEEDS)
        self.assertEqual([round(m, 2) for m in magnitudes[:4]], [5.74, 7.69, 10.0, 10.33])

    def test_the_same_case_goes_to_every_policy(self):
        template = m91.load_template()
        for scenario in m91.SCENARIOS:
            cases = []
            for policy in m91.POLICIES:
                case = m91.build_case(template, m9.RunSpec("matrix", scenario, policy, 2003))
                self.assertEqual(case["controller"]["policy"], policy)
                self.assertLessEqual(len(case["name"]), 80)
                del case["name"], case["controller"]["policy"]
                cases.append(m9.case_bytes(case))
            self.assertEqual(len(set(cases)), 1)
        self.assertEqual(m91.build_case(template, m9.RunSpec("matrix", "nominal", "guarded", 2000))["faults"], [])


class FrozenTemplateTests(unittest.TestCase):
    def test_the_template_hash_is_checked_before_use(self):
        m91.load_template()
        with patch.object(m91, "TEMPLATE_SHA256", "0" * 64):
            with self.assertRaisesRegex(m9.M9CampaignError, "frozen pre-registered template"):
                m91.load_template()
        self.assertEqual(m91.TEMPLATE_SHA256, "69ecad65e9ec4329ffc74a3b985dbb7dc60d5cdaa1e4a9a380f296a76f68114b")


class ScoringTests(unittest.TestCase):
    def test_a_clean_landing_is_detected_nowhere_contained_and_recovered(self):
        score = m91.score_verification(verification())
        self.assertTrue(score["contained"] and score["recovered"] and score["r1_met"])
        self.assertEqual(score["flags"], {"sensor_disagreement": False, "altimeter_rejected": False, "ascent_abort": False})
        self.assertEqual((score["invariant_ids_failed"], score["requirement_ids_failed"]), ([], []))

    def test_detection_contained_and_recovered_are_independent(self):
        # Detected but not recovered: hard landing with R1 failed, invariants held.
        score = m91.score_verification(verification("hard_landing", failed_requirements=("R1",),
                                                     flags={"sensor_disagreement": True, "altimeter_rejected": True}))
        self.assertTrue(score["flags"]["sensor_disagreement"] and score["flags"]["altimeter_rejected"])
        self.assertTrue(score["contained"])
        self.assertFalse(score["recovered"])
        self.assertFalse(score["r1_met"])
        # Recovered without any detection.
        self.assertTrue(m91.score_verification(verification())["recovered"])
        # Not contained: outcome landed (R1 to R6 and S5 hold) but S1 failed, so not recovered.
        score = m91.score_verification(verification("landed", failed_invariants=("S1",)))
        self.assertFalse(score["contained"] or score["recovered"])
        self.assertEqual(score["invariant_ids_failed"], ["S1"])
        # Contained by cutting the engine: ascent_abort flag, hard landing, invariants hold.
        score = m91.score_verification(verification("hard_landing", failed_requirements=("R1",), flags={"ascent_abort": True}))
        self.assertTrue(score["flags"]["ascent_abort"] and score["contained"])

    def test_no_contact_leaves_s2_unevaluated_and_it_does_not_count_as_a_failure(self):
        score = m91.score_verification(verification("no_contact", unevaluated=("S2",)))
        self.assertTrue(score["contained"])
        self.assertFalse(score["recovered"])
        self.assertFalse(score["r1_met"], "R1 is not evaluated without contact")
        score = m91.score_verification(verification("no_contact", failed_invariants=("S5",), unevaluated=("S2",)))
        self.assertFalse(score["contained"])
        self.assertEqual(score["invariant_ids_failed"], ["S5"])

    def test_an_unevaluated_invariant_is_never_a_failure(self):
        v = verification("no_contact", unevaluated=("S2",))
        v["invariants"][1]["pass"] = False  # even if it carried a stray false, evaluated is false
        self.assertTrue(m91.score_verification(v)["contained"])

    def test_malformed_verification_is_a_campaign_error(self):
        good = verification()
        for change in ({"schema": "vv-rocket-landing-verification.v1"}, {"controller_flags": None},
                       {"controller_flags": {"source": "x"}}, {"invariants": good["invariants"][:4]},
                       {"invariants": list(reversed(good["invariants"]))}, {"requirements": None}):
            with self.subTest(change=list(change)), self.assertRaises(m9.M9CampaignError):
                m91.score_verification({**good, **change})


def run_record(scenario, policy, seed, flags=(), outcome="landed", failed_invariants=(), magnitude=None, source="abc"):
    score = m91.score_verification(verification(outcome, failed_invariants, flags={f: True for f in flags}))
    return {"group": "matrix", "fault": scenario, "policy": policy, "seed": seed, "grid_index": None,
            "magnitude": magnitude, "window": None, "outcome": outcome,
            "failed": score["requirement_ids_failed"] + score["invariant_ids_failed"],
            "requirements_failed": score["requirement_ids_failed"], "exit_code": 0, "replay": "verified",
            "dir": f"runs/{scenario}/{policy}/seed-{seed}", "source_sha256": source,
            **{k: score[k] for k in ("invariant_ids_failed", "contained", "recovered", "r1_met", "flags")}}


class CellTests(unittest.TestCase):
    def test_cells_count_detection_containment_recovery_and_failures_separately(self):
        records = [run_record("gnss_bias", "guarded", s, flags=("sensor_disagreement", "altimeter_rejected"), outcome="hard_landing")
                   for s in range(3)]
        records.append(run_record("gnss_bias", "guarded", 3))
        records.append(run_record("gnss_bias", "guarded", 4, outcome="landed", failed_invariants=("S1",)))
        records.append(run_record("gnss_bias", "guarded", 5, outcome="no_contact", failed_invariants=("S5",)))
        (c,) = m91.build_cells(records)
        self.assertEqual((c["runs"], c["recovered"], c["outcome_landed"], c["hard_landing"], c["no_contact"]), (6, 1, 2, 3, 1))
        self.assertEqual(c["detection"], {"sensor_disagreement": 3, "altimeter_rejected": 3, "ascent_abort": 0})
        self.assertEqual(c["containment"], 4)
        self.assertEqual(c["invariant_failures"], {"S1": 1, "S2": 0, "S3": 0, "S4": 0, "S5": 1})
        self.assertEqual(c["r1_met"], 5, "R1 holds in every run that touched down with R1 not failed")

    def test_false_alarms_are_counted_against_the_limit_of_one(self):
        cells = [cell("nominal", "guarded", detection={"sensor_disagreement": 1}),
                 cell("thrust_loss", "guarded", detection={"ascent_abort": 2}),
                 cell("gnss_bias", "guarded", detection={"sensor_disagreement": 30})]
        rows = {a["scenario"]: a for a in m91.build_false_alarms(cells)}
        self.assertEqual(set(rows), {"nominal", "thrust_loss"}, "biased-sensor cells are not false-alarm cells")
        self.assertTrue(rows["nominal"]["within_limit"])
        self.assertFalse(rows["thrust_loss"]["within_limit"])

    def test_regressions_list_every_cell_where_guarded_recovers_less(self):
        cells = [cell("nominal", "robust", recovered=30), cell("nominal", "guarded", recovered=30),
                 cell("thrust_loss", "robust", recovered=10), cell("thrust_loss", "guarded", recovered=9),
                 cell("gnss_bias_low", "robust", recovered=20), cell("gnss_bias_low", "guarded", recovered=10),
                 cell("gimbal_stuck", "robust", recovered=5), cell("gimbal_stuck", "guarded", recovered=8)]
        rows = {g["scenario"]: g for g in m91.build_regressions(cells)}
        self.assertEqual(set(rows), {"thrust_loss", "gnss_bias_low"})
        self.assertTrue(rows["thrust_loss"]["within_g4_tolerance"])
        self.assertFalse(rows["gnss_bias_low"]["within_g4_tolerance"])
        self.assertEqual(rows["gnss_bias_low"]["difference"], -10)


class HypothesisTests(unittest.TestCase):
    def test_all_pass_on_the_passing_fixture(self):
        v = verdicts(passing_cells(), {"command_identity": GOOD_IDENTITY, "small_gnss_bias_draws": 3})
        self.assertEqual({k: x["verdict"] for k, x in v.items()},
                         {"G1": "supported", "G2": "supported", "G2b": "supported", "G3": "supported",
                          "G4": "supported", "G5": "recorded"})
        self.assertTrue(all(x["complete"] for x in v.values()))

    def test_g1_needs_30_of_30_detection_in_every_biased_scenario(self):
        for scenario in m91.DETECTION_SCENARIOS:
            cells = replace(passing_cells(), scenario, "guarded", recovered=5, detection={"sensor_disagreement": 29})
            self.assertEqual(verdicts(cells)["G1"]["verdict"], "not_supported", scenario)

    def test_g1_allows_one_false_alarm_per_flag_and_not_two(self):
        base = passing_cells() + [cell("nominal", "guarded", recovered=30)]
        base = [c for c in base if not (c["scenario"] == "nominal" and c["policy"] == "guarded" and c["recovered"] == 20)]
        one = replace(base, "nominal", "guarded", recovered=30, detection={"sensor_disagreement": 1, "ascent_abort": 1})
        self.assertEqual(verdicts(one)["G1"]["verdict"], "supported")
        for flag in m91.FLAGS:
            two = replace(base, "nominal", "guarded", recovered=30, detection={flag: 2})
            self.assertEqual(verdicts(two)["G1"]["verdict"], "not_supported", flag)

    def test_g2_fails_on_a_single_s5_violation(self):
        self.assertEqual(verdicts(replace(passing_cells(), "gnss_dropout", "guarded", recovered=20, s5=1))["G2"]["verdict"], "not_supported")

    def test_g2b_fails_if_baseline_guarded_still_drifts_away(self):
        cells = replace(passing_cells(), "gnss_dropout", "baseline_guarded", recovered=0, hard=29, no_contact=1)
        self.assertEqual(verdicts(cells)["G2b"]["verdict"], "not_supported")
        # S5 and R1 failures are recorded, not criteria.
        ok = verdicts(replace(passing_cells(), "gnss_dropout", "baseline_guarded", recovered=30, hard=0))["G2b"]
        self.assertEqual(ok["verdict"], "supported")

    def test_g3_boundary_is_27_of_30_for_r1(self):
        for met, expected in ((27, "supported"), (26, "not_supported"), (30, "supported")):
            cells = replace(passing_cells(), "gnss_bias", "guarded", recovered=3, detection={"sensor_disagreement": 30},
                            r1_failures=30 - met)
            h = verdicts(cells, {"small_gnss_bias_draws": 3})["G3"]
            self.assertEqual(h["verdict"], expected, met)
        self.assertEqual(h["observed"]["draws_below_10_m"], 3)

    def test_g4_tolerance_is_two_in_each_of_the_nine_m9_scenarios(self):
        for scenario in m91.M9_SCENARIOS:
            cells = replace(replace(passing_cells(), scenario, "robust", recovered=20), scenario, "guarded", recovered=18,
                            detection={"sensor_disagreement": 30} if scenario in m91.DETECTION_SCENARIOS else None)
            self.assertEqual(verdicts(cells)["G4"]["verdict"], "supported", scenario)
            cells = replace(cells, scenario, "guarded", recovered=17,
                            detection={"sensor_disagreement": 30} if scenario in m91.DETECTION_SCENARIOS else None)
            self.assertEqual(verdicts(cells)["G4"]["verdict"], "not_supported", scenario)

    def test_g4_ignores_the_new_fault_scenarios(self):
        cells = replace(passing_cells(), "gnss_bias_low", "guarded", recovered=0, detection={"sensor_disagreement": 30})
        cells = replace(cells, "gnss_bias_low", "robust", recovered=30)
        self.assertEqual(verdicts(cells)["G4"]["verdict"], "supported")
        self.assertEqual([g["scenario"] for g in m91.build_regressions(cells)], ["gnss_bias_low"])

    def test_g4_marks_a_scenario_where_robust_recovered_nothing_as_not_informative(self):
        h = verdicts(replace(passing_cells(), "gnss_bias", "robust", recovered=0))["G4"]
        self.assertFalse(h["observed"]["scenarios"]["gnss_bias"]["informative"])
        self.assertIn("não informativa", h["evidence"])

    def test_g4_strong_check_is_reported_with_its_own_numbers(self):
        h = verdicts(passing_cells(), {"command_identity": {"pairs_compared": 50, "identical": 49, "different": ["x"]}})["G4"]
        self.assertEqual(h["verdict"], "supported", "the strong check is reported apart from the numeric criterion")
        self.assertIn("49 de 50", h["evidence"])
        self.assertIn("não cumpre", h["evidence"].split("Verificação forte")[1])

    def test_g5_records_without_a_success_criterion(self):
        for recovered in (0, 30):
            cells = replace(passing_cells(), "altimeter_bias_low", "guarded", recovered=recovered, detection={"sensor_disagreement": 30})
            h = verdicts(cells)["G5"]
            self.assertEqual(h["verdict"], "recorded")
            self.assertEqual(h["observed"]["altimeter_bias_low"]["recovered"], recovered)

    def test_missing_cells_are_not_evaluated(self):
        v = verdicts([])
        self.assertTrue(all(h["verdict"] == "not_evaluated" for h in v.values()))
        v = verdicts([cell("nominal", "guarded")])
        self.assertEqual(v["G2"]["verdict"], "not_evaluated")
        self.assertFalse(v["G1"]["complete"])


class IdentityTests(unittest.TestCase):
    def write_trace(self, root, record, commands):
        directory = root / record["dir"]
        directory.mkdir(parents=True)
        (directory / "trace.json").write_text(json.dumps(
            {"samples": [{"step": i * 10, "command": c} for i, c in enumerate(commands)]}), encoding="utf-8")

    def test_only_pairs_without_guarded_flags_are_compared(self):
        commands = [{"throttle": 0.5, "gimbal_tan": [0.0, 0.0]}, {"throttle": 0.6, "gimbal_tan": [0.1, 0.0]}]
        flagged = run_record("gnss_bias", "guarded", 2000, flags=("sensor_disagreement",))
        same_g, same_r = run_record("nominal", "guarded", 2000), run_record("nominal", "robust", 2000)
        diff_g, diff_r = run_record("thrust_loss", "guarded", 2001), run_record("thrust_loss", "robust", 2001)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_trace(root, flagged, [{"throttle": 0.0}])
            self.write_trace(root, run_record("gnss_bias", "robust", 2000), commands)
            for record in (same_g, same_r):
                self.write_trace(root, record, commands)
            self.write_trace(root, diff_r, commands)
            self.write_trace(root, diff_g, commands[:1] + [{"throttle": 0.7, "gimbal_tan": [0.1, 0.0]}])
            result = m91.command_identity(root, [flagged, same_g, same_r, diff_g, diff_r,
                                                 run_record("gnss_bias", "robust", 2000)])
        self.assertEqual(result["pairs_compared"], 2)
        self.assertEqual(result["identical"], 1)
        self.assertEqual(result["different"], ["runs/thrust_loss/guarded/seed-2001"])


class SummaryTests(unittest.TestCase):
    def test_markdown_has_no_em_dash_and_states_the_verdicts(self):
        records = [run_record(s, p, 2000, magnitude=None if s == "nominal" else 12.0)
                   for s in ("nominal", "gnss_bias") for p in ("baseline", "robust", "guarded")]
        meta = {"binary_sha256": "b" * 64, "template_sha256": "t" * 64, "command": "python scripts/m91_campaign.py",
                "machine": "fixture", "duration_s": 1.5, "determinism_check": {"runs": ["a", "b"], "files": ["x"], "identical": True},
                "command_identity": GOOD_IDENTITY}
        summary = m91.build_summary(records, meta)
        text = m91.render_markdown(summary)
        self.assertNotIn("\u2014", text)
        self.assertFalse(summary["preregistered"])
        self.assertEqual(summary["schema"], "vv-m91-campaign.v1")
        for token in ("G1", "G5", "Recuperou", "Contenção", "Falsos alarmes", "Regressões", "não (subconjunto"):
            self.assertIn(token, text)
        self.assertEqual(summary["composition"]["total"], 6)
        self.assertNotIn("\u2014", json.dumps(summary, ensure_ascii=False))

    def test_composition_states_the_arithmetic_of_1050(self):
        records = [run_record(r.fault, r.policy, r.seed, magnitude=1.0) for r in m91.plan_runs(m91.DEFAULT_SEEDS)]
        c = m91.build_composition(records)
        self.assertEqual((c["main"]["runs"], c["baseline_guarded"]["runs"], c["total"]), (990, 60, 1050))
        text = m91.composition_text(c)
        self.assertIn("11 cenários × 3 políticas × 30 sementes = 990", text)
        self.assertIn("990 + 60 = 1050", text)
        summary = m91.build_summary(records, {})
        self.assertTrue(summary["preregistered"])

    def test_runs_from_different_sources_are_rejected(self):
        records = [run_record("nominal", "guarded", 2000, source="a"), run_record("nominal", "guarded", 2001, source="b")]
        with self.assertRaisesRegex(m9.M9CampaignError, "different sources"):
            m91.build_summary(records, {})


@unittest.skipUnless(BINARY.is_file(), "vv-rocket release binary is missing")
class EndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name) / "campaign"
        cls.arguments = Namespace(
            binary=BINARY, seeds=(2000, 2001), scenarios=("nominal", "gnss_bias", "gnss_dropout"),
            policies=("robust", "guarded", "baseline_guarded"), max_runs=100, max_artifact_bytes=64 * 1024 * 1024,
            time_budget_seconds=120, jobs=2, output_root=cls.root)
        m91.execute_campaign(cls.arguments)
        cls.summary = json.loads((cls.root / "summary.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_reduced_campaign_is_verified_but_not_preregistered(self):
        s = self.summary
        self.assertEqual(s["schema"], "vv-m91-campaign.v1")
        self.assertFalse(s["preregistered"])
        # 3 scenarios x 2 main policies x 2 seeds + baseline_guarded in 2 scenarios x 2 seeds.
        self.assertEqual(s["total_runs"], 12 + 4)
        self.assertTrue(all(r["replay"] == "verified" for r in s["runs"]))
        self.assertTrue(s["determinism_check"]["identical"])
        self.assertEqual([h["id"] for h in s["hypotheses"]], ["G1", "G2", "G2b", "G3", "G4", "G5"])
        self.assertTrue((self.root / "summary.md").is_file())
        self.assertEqual(s["template_sha256"], m91.TEMPLATE_SHA256)

    def test_guarded_detects_the_gnss_bias_and_the_nominal_case_is_quiet(self):
        cells = {(c["scenario"], c["policy"]): c for c in self.summary["cells"]}
        self.assertEqual(cells[("gnss_bias", "guarded")]["detection"]["sensor_disagreement"], 2)
        self.assertEqual(cells[("nominal", "guarded")]["detection"]["sensor_disagreement"], 0)
        # With no fault all three policies behave alike (a dispersed seed may fail a requirement for all of them).
        self.assertEqual(cells[("nominal", "guarded")]["recovered"], cells[("nominal", "robust")]["recovered"])
        self.assertEqual(cells[("nominal", "guarded")]["recovered"], cells[("nominal", "baseline_guarded")]["recovered"])
        self.assertEqual(cells[("nominal", "baseline_guarded")]["runs"], 2)

    def test_case_files_follow_the_documented_layout_and_the_draw_rule(self):
        case = json.loads((self.root / "runs" / "gnss_bias" / "guarded" / "seed-2000" / "case.json").read_text(encoding="utf-8"))
        self.assertEqual(case["faults"], [m91.sample_fault("gnss_bias", 2000)])
        self.assertEqual(case["controller"]["policy"], "guarded")


if __name__ == "__main__":
    unittest.main()
