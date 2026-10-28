from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import m9_campaign as m9  # noqa: E402

BINARY = m9.binary_default()
MISSING_BINARY = (
    "vv-rocket release binary is missing; run "
    "cargo build --release --manifest-path crates/vv-rocket/Cargo.toml"
)


def record(fault, policy, seed, outcome="landed", invariants=(), group="matrix", grid_index=None,
           requirements=(), source="abc"):
    return {
        "group": group,
        "fault": fault,
        "policy": policy,
        "seed": seed,
        "grid_index": grid_index,
        "magnitude": None,
        "window": None,
        "outcome": outcome,
        "failed": list(requirements) + list(invariants),
        "requirements_failed": list(requirements),
        "invariants_failed": list(invariants),
        "exit_code": 0 if outcome == "landed" and not invariants else 2,
        "replay": "verified",
        "dir": f"runs/{fault}/{policy}/seed-{seed}",
        "source_sha256": source,
    }


def family_records(fault, baseline_landed, robust_landed, runs=30, overlap=None):
    """Registos sintéticos: as primeiras `landed` sementes aterram em cada política."""
    out = []
    for seed in range(runs):
        out.append(record(fault, "baseline", seed, "landed" if seed < baseline_landed else "hard_landing",
                          requirements=() if seed < baseline_landed else ("R1",)))
        robust_ok = seed >= runs - robust_landed if overlap == "disjoint" else seed < robust_landed
        out.append(record(fault, "robust", seed, "landed" if robust_ok else "hard_landing",
                          requirements=() if robust_ok else ("R1",)))
    return out


def verdicts(records):
    cells = m9.build_cells(records)
    pairs = m9.build_pairs(records)
    return {h["id"]: h for h in m9.evaluate_hypotheses(cells, pairs)}


class SamplingTests(unittest.TestCase):
    def test_sampling_is_deterministic_and_independent_of_the_policy(self):
        template = m9.load_template()
        for fault in m9.FAULTS:
            for seed in (1000, 1013, 1029):
                self.assertEqual(m9.sample_fault(fault, seed), m9.sample_fault(fault, seed))
                base = m9.build_case(template, m9.RunSpec("matrix", fault, "baseline", seed))
                robust = m9.build_case(template, m9.RunSpec("matrix", fault, "robust", seed))
                self.assertEqual(base["controller"]["policy"], "baseline")
                self.assertEqual(robust["controller"]["policy"], "robust")
                self.assertNotEqual(base["name"], robust["name"])
                for case in (base, robust):
                    del case["name"]
                    del case["controller"]["policy"]
                self.assertEqual(m9.case_bytes(base), m9.case_bytes(robust))

    def test_fault_index_follows_the_documented_table_order(self):
        self.assertEqual(m9.FAULTS[0], "thrust_loss")
        self.assertEqual(m9.FAULTS[7], "imu_accel_bias")
        self.assertEqual(len(m9.FAULTS), 8)
        # A semente do gerador é semente * 100 + índice: o sorteio muda com o índice.
        import random

        draw = random.Random(1000 * 100 + 3).random()
        low, high = m9.MAGNITUDE_RANGES["altimeter_bias"]
        self.assertEqual(m9.sample_fault("altimeter_bias", 1000)["magnitude"], low + (high - low) * draw)

    def test_magnitudes_and_windows_stay_inside_the_preregistered_ranges(self):
        for fault in m9.FAULTS:
            for seed in m9.DEFAULT_SEEDS:
                spec = m9.sample_fault(fault, seed)
                bounds = m9.MAGNITUDE_RANGES[fault]
                if bounds is None:
                    self.assertEqual(spec["magnitude"], 0.0)
                else:
                    self.assertTrue(bounds[0] <= spec["magnitude"] <= bounds[1], (fault, seed))
                start, end = spec["start_s"], spec["end_s"]
                self.assertLess(start, end)
                length = round((end - start) * 100) / 100
                if fault == "gimbal_stuck":
                    self.assertTrue(0.5 <= length <= 3.0, (seed, length))
                    self.assertTrue(5.0 <= start <= 20.0)
                    self.assertLessEqual(end, 23.0)
                elif fault in ("altimeter_dropout", "gnss_dropout"):
                    self.assertTrue(2.0 <= length <= 10.0, (seed, length))
                    self.assertGreaterEqual(start, 5.0)
                    self.assertLessEqual(end, 23.0)
                else:
                    self.assertEqual((start, end), m9.FIXED_WINDOWS[fault])

    def test_windows_are_whole_steps_of_ten_milliseconds(self):
        for fault in ("gimbal_stuck", "altimeter_dropout", "gnss_dropout"):
            for seed in m9.DEFAULT_SEEDS:
                spec = m9.sample_fault(fault, seed)
                for key in ("start_s", "end_s"):
                    self.assertAlmostEqual(spec[key] * 100, round(spec[key] * 100), places=6)

    def test_boundary_grid_has_six_equally_spaced_points_with_both_endpoints(self):
        self.assertEqual(m9.boundary_magnitudes("thrust_loss"), [0.05, 0.1, 0.15, 0.2, 0.25, 0.3])
        self.assertEqual(m9.boundary_magnitudes("ignition_delay"), [0.1, 0.28, 0.46, 0.64, 0.82, 1.0])
        with self.assertRaises(m9.M9CampaignError):
            m9.boundary_magnitudes("gnss_bias")

    def test_boundary_runs_use_the_grid_magnitude_and_the_fixed_window(self):
        run = m9.RunSpec("boundary", "ignition_delay", "robust", 1003, 3)
        spec = m9.fault_for(run)
        self.assertEqual(spec["magnitude"], 0.64)
        self.assertEqual((spec["start_s"], spec["end_s"]), m9.FIXED_WINDOWS["ignition_delay"])

    def test_nominal_has_no_fault(self):
        case = m9.build_case(m9.load_template(), m9.RunSpec("matrix", "nominal", "robust", 1000))
        self.assertEqual(case["faults"], [])


class FrozenTemplateTests(unittest.TestCase):
    def test_the_template_hash_is_checked_before_use(self):
        m9.load_template()
        with patch.object(m9, "TEMPLATE_SHA256", "0" * 64):
            with self.assertRaisesRegex(m9.M9CampaignError, "frozen pre-registered template"):
                m9.load_template()

    def test_ignition_delay_window_covers_every_plausible_ignition(self):
        spec = m9.sample_fault("ignition_delay", 1000)
        self.assertEqual((spec["start_s"], spec["end_s"]), (0.0, 10.0))


def synthetic_run(directory, run, faults_acted, template=None):
    """Escreve uma execução mínima que `inspect_run` aceita (sem binário)."""
    template = template or m9.load_template()
    directory.mkdir(parents=True)
    (directory / "case.json").write_bytes(m9.case_bytes(m9.build_case(template, run)))
    (directory / "run.json").write_text(json.dumps(
        {"seed": run.seed, "policy": run.policy, "outcome": "landed", "source_sha256": "abc"}), encoding="utf-8")
    verification = {
        "outcome": "landed",
        "requirements": [{"id": "R1_vertical_speed", "evaluated": True, "pass": True}],
        "invariants": [{"id": "S1_tilt_envelope", "pass": True}],
    }
    if faults_acted is not None:
        verification["faults"] = faults_acted
    (directory / "verification.json").write_text(json.dumps(verification), encoding="utf-8")


class ActedTests(unittest.TestCase):
    spec = m9.RunSpec("matrix", "thrust_loss", "baseline", 1000)

    def inspect(self, faults):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "run"
            synthetic_run(directory, self.spec, faults)
            return m9.inspect_run(self.spec, directory, m9.load_template(), 0)

    def test_a_fault_that_acted_gives_a_record(self):
        result = self.inspect([{"kind": "thrust_loss", "acted": True}])
        self.assertEqual(result["outcome"], "landed")
        self.assertEqual(result["exit_code"], 0)

    def test_a_fault_that_never_acted_is_a_draw_error(self):
        with self.assertRaises(m9.DrawError):
            self.inspect([{"kind": "thrust_loss", "acted": False}])

    def test_a_missing_acted_field_is_a_hard_error_not_a_draw_error(self):
        for faults in (None, [{"kind": "thrust_loss"}], [{"kind": "thrust_loss", "acted": "yes"}]):
            with self.subTest(faults=faults):
                with self.assertRaises(m9.M9CampaignError) as caught:
                    self.inspect(faults)
                self.assertNotIsInstance(caught.exception, m9.DrawError)

    def test_draw_errors_are_counted_reported_and_fail_the_campaign(self):
        runs = [m9.RunSpec("matrix", "thrust_loss", "baseline", s) for s in (1, 2, 3)]
        with tempfile.TemporaryDirectory() as temporary:
            runner = m9.Runner(Path("vv-rocket"), Path(temporary), max_runs=10,
                               max_artifact_bytes=2**20, time_budget_seconds=30)

            def fake_land(run, directory):
                return 0

            def fake_record(run, directory, exit_code):
                if run.seed != 2:
                    return record("thrust_loss", "baseline", run.seed)
                raise m9.DrawError(f"{run.rel}: the thrust_loss window never acted (acted == false)")

            with patch.object(runner, "land", fake_land), patch.object(runner, "record", fake_record):
                with self.assertRaisesRegex(m9.M9CampaignError, "1 runs had a fault that never acted"):
                    m9.run_parallel(runner, runner.execute, runs, 2)
            listed = json.loads((Path(temporary) / "draw_errors.json").read_text(encoding="utf-8"))
            self.assertEqual(listed["count"], 1)
            self.assertIn("seed-2", listed["errors"][0])


class PlanTests(unittest.TestCase):
    def test_default_plan_is_the_preregistered_matrix(self):
        runs = m9.plan_runs(m9.DEFAULT_SEEDS)
        matrix = [r for r in runs if r.group == "matrix"]
        boundary = [r for r in runs if r.group == "boundary"]
        self.assertEqual(len(matrix), 9 * 2 * 30)
        self.assertEqual(len(boundary), 2 * 6 * 2 * 10)
        self.assertEqual(min(m9.DEFAULT_SEEDS), 1000)
        self.assertEqual(max(m9.DEFAULT_SEEDS), 1029)
        self.assertEqual(len({r.key for r in runs}), len(runs))
        self.assertEqual(len({r.rel for r in runs}), len(runs))
        self.assertEqual(sorted(runs, key=m9.plan_order), runs)

    def test_limits_reject_a_plan_above_max_runs(self):
        good = dict(max_runs=800, max_artifact_bytes=2**20, time_budget_seconds=60, jobs=2)
        m9.validate_limits(780, **good)
        with self.assertRaisesRegex(m9.M9CampaignError, "782 simulator runs"):
            m9.validate_limits(780, **{**good, "max_runs": 781})

    def test_limits_reject_out_of_range_values(self):
        good = dict(max_runs=10, max_artifact_bytes=2**20, time_budget_seconds=60, jobs=2)
        for bad in (
            {"max_runs": 0},
            {"max_runs": m9.MAX_RUNS + 1},
            {"max_artifact_bytes": 10},
            {"max_artifact_bytes": m9.MAX_ARTIFACT_BYTES + 1},
            {"time_budget_seconds": 0},
            {"time_budget_seconds": float("nan")},
            {"time_budget_seconds": m9.MAX_TIME_BUDGET_SECONDS + 1},
            {"jobs": 0},
            {"jobs": m9.MAX_JOBS + 1},
        ):
            with self.subTest(bad=bad), self.assertRaises(m9.M9CampaignError):
                m9.validate_limits(1, **{**good, **bad})

    def test_conditions_parser_keeps_canonical_order_and_rejects_unknown_names(self):
        self.assertEqual(m9.parse_conditions("thrust_loss,nominal"), ("nominal", "thrust_loss"))
        with self.assertRaises(Exception):
            m9.parse_conditions("nominal,nope")

    def test_subset_plan_without_boundary_sweep(self):
        runs = m9.plan_runs((1000, 1001), ("nominal", "gnss_bias"), include_boundary=False)
        self.assertEqual(len(runs), 2 * 2 * 2)
        runs = m9.plan_runs((1000, 1001), ("nominal", "thrust_loss"))
        self.assertEqual(len([r for r in runs if r.group == "boundary"]), 6 * 2 * 2)


class HypothesisTests(unittest.TestCase):
    def test_h1_supported_when_robust_is_not_worse_in_every_family_fault(self):
        records = []
        for fault, (b, r) in {"altimeter_bias": (5, 30), "altimeter_dropout": (20, 20), "gnss_dropout": (10, 25)}.items():
            records += family_records(fault, b, r)
        h1 = verdicts(records)["H1"]
        self.assertEqual(h1["verdict"], "supported")
        self.assertTrue(h1["complete"])

    def test_h1_not_supported_when_robust_is_worse_in_one_fault(self):
        records = []
        for fault, (b, r) in {"altimeter_bias": (5, 30), "altimeter_dropout": (21, 20), "gnss_dropout": (10, 25)}.items():
            records += family_records(fault, b, r)
        h1 = verdicts(records)["H1"]
        self.assertEqual(h1["verdict"], "not_supported")
        self.assertIn("altimeter_dropout", h1["evidence"])

    def test_h1_not_evaluated_without_its_faults(self):
        h = verdicts(family_records("thrust_loss", 30, 30))
        self.assertEqual(h["H1"]["verdict"], "not_evaluated")
        self.assertFalse(h["H1"]["complete"])

    def test_h2_supported_at_exactly_three_discordant_pairs(self):
        records = []
        for fault in m9.HYPOTHESIS_FAMILIES["H2"]:
            records += family_records(fault, 30, 27)  # 3 pares: só baseline aterra
        h2 = verdicts(records)["H2"]
        self.assertEqual(h2["verdict"], "supported")
        self.assertEqual(h2["observed"]["thrust_loss"]["discordant"], 3)

    def test_h2_not_supported_with_four_discordant_pairs_in_one_fault(self):
        records = family_records("thrust_loss", 30, 30)
        records += family_records("ignition_delay", 30, 26)
        records += family_records("gimbal_stuck", 30, 30)
        h2 = verdicts(records)["H2"]
        self.assertEqual(h2["verdict"], "not_supported")
        self.assertEqual(h2["observed"]["ignition_delay"]["discordant"], 4)

    def test_h2_counts_discordant_pairs_in_both_directions(self):
        records = family_records("thrust_loss", 15, 15, overlap="disjoint")  # 30 discordantes
        h2 = verdicts(records)["H2"]
        self.assertEqual(h2["observed"]["thrust_loss"]["only_baseline"], 15)
        self.assertEqual(h2["observed"]["thrust_loss"]["only_robust"], 15)
        self.assertEqual(h2["verdict"], "not_supported")

    def test_h3_observed_with_one_baseline_only_pair(self):
        h3 = verdicts(family_records("gnss_bias", 1, 0))["H3"]
        self.assertEqual(h3["verdict"], "observed")

    def test_h3_not_observed_when_robust_never_loses(self):
        h3 = verdicts(family_records("gnss_bias", 0, 5))["H3"]
        self.assertEqual(h3["verdict"], "not_observed")

    def test_h3_not_evaluated_without_gnss_bias(self):
        self.assertEqual(verdicts(family_records("nominal", 5, 5))["H3"]["verdict"], "not_evaluated")


class SummaryTests(unittest.TestCase):
    def test_cells_separate_outcome_requirements_and_invariants(self):
        records = [
            record("nominal", "baseline", 1, "landed"),
            record("nominal", "baseline", 2, "landed", invariants=("S3_axial_load",)),
            record("nominal", "baseline", 3, "hard_landing", requirements=("R1", "R5")),
            record("nominal", "baseline", 4, "no_contact"),
        ]
        (cell,) = m9.build_cells(records)
        self.assertEqual(cell["runs"], 4)
        self.assertEqual(cell["landed"], 1)
        self.assertEqual(cell["landed_with_invariant_failure"], 1)
        self.assertEqual(cell["hard_landing"], 1)
        self.assertEqual(cell["no_contact"], 1)
        self.assertEqual(cell["invariant_failure_runs"], 1)
        self.assertEqual(cell["requirement_failures"], {"R1": 1, "R2": 0, "R3": 0, "R4": 0, "R5": 1, "R6": 0})

    def test_pairs_classify_each_seed(self):
        records = [
            record("gnss_bias", "baseline", 1), record("gnss_bias", "robust", 1),
            record("gnss_bias", "baseline", 2), record("gnss_bias", "robust", 2, "hard_landing"),
            record("gnss_bias", "baseline", 3, "hard_landing"), record("gnss_bias", "robust", 3),
            record("gnss_bias", "baseline", 4, "hard_landing"), record("gnss_bias", "robust", 4, "hard_landing"),
            record("gnss_bias", "baseline", 5),  # sem par: ignorada
        ]
        (pair,) = m9.build_pairs(records)
        self.assertEqual(
            (pair["pairs"], pair["both_land"], pair["only_baseline"], pair["only_robust"], pair["neither"]),
            (4, 1, 1, 1, 1),
        )

    def test_boundary_findings_report_no_boundary_or_first_failing_magnitude(self):
        records = []
        for index, magnitude in enumerate(m9.boundary_magnitudes("thrust_loss")):
            for policy in m9.POLICIES:
                for seed in (1, 2):
                    r = record("thrust_loss", policy, seed, group="boundary", grid_index=index)
                    r["magnitude"] = magnitude
                    if policy == "robust" and index >= 4:
                        r["outcome"] = "hard_landing"
                    records.append(r)
        rows, findings = m9.build_boundaries(records)
        self.assertEqual(len(rows), 12)
        by_policy = {f["policy"]: f for f in findings}
        self.assertEqual(by_policy["baseline"]["finding"], "nenhuma fronteira dentro da gama pré-registada")
        self.assertIsNone(by_policy["baseline"]["first_magnitude_with_failures"])
        self.assertEqual(by_policy["robust"]["first_magnitude_with_failures"], 0.25)

    def test_full_matrix_is_flagged_as_preregistered_and_a_subset_is_not(self):
        full = [record(r.fault, r.policy, r.seed, group=r.group, grid_index=r.grid_index)
                for r in m9.plan_runs(m9.DEFAULT_SEEDS)]
        meta = {"command": "x", "machine": "y", "duration_s": 1.0, "binary_sha256": "b"}
        summary = m9.build_summary(full, meta)
        self.assertTrue(summary["preregistered"])
        self.assertEqual(summary["seeds"], list(m9.DEFAULT_SEEDS))
        self.assertEqual(summary["schema"], "vv-m9-campaign.v1")
        self.assertEqual(len(summary["runs"]), 780)
        self.assertFalse(m9.build_summary(full[1:], meta)["preregistered"])
        self.assertTrue(summary["limitations"])
        self.assertIn("H1", {h["id"] for h in summary["hypotheses"]})

    def test_runs_from_different_sources_are_rejected(self):
        records = [record("nominal", "baseline", 1, source="a"), record("nominal", "robust", 1, source="b")]
        with self.assertRaisesRegex(m9.M9CampaignError, "different sources"):
            m9.build_summary(records, {})

    def test_markdown_has_no_em_dash_and_states_the_verdicts(self):
        records = family_records("gnss_bias", 1, 0)
        text = m9.render_markdown(m9.build_summary(records, {"command": "c", "machine": "m", "duration_s": 1.5}))
        self.assertNotIn(chr(0x2014), text)
        self.assertIn("(observed)", text)
        self.assertIn("não (subconjunto", text)


class RunnerUnitTests(unittest.TestCase):
    def make_runner(self, root, **overrides):
        values = dict(max_runs=5, max_artifact_bytes=2**20, time_budget_seconds=30)
        values.update(overrides)
        return m9.Runner(Path("vv-rocket"), Path(root), **values)

    def test_a_replay_that_is_not_verified_is_a_campaign_error(self):
        run = m9.RunSpec("matrix", "nominal", "baseline", 1000)
        with tempfile.TemporaryDirectory() as temporary:
            runner = self.make_runner(temporary)
            failed = SimpleNamespace(returncode=1, stdout='{"status":"failed"}', stderr="")
            with patch("m9_campaign.run_bounded_process", return_value=failed):
                with self.assertRaisesRegex(m9.M9CampaignError, "not verified"):
                    runner.replay(run, Path(temporary))
            wrong = SimpleNamespace(returncode=0, stdout='{"status":"other"}', stderr="")
            with patch("m9_campaign.run_bounded_process", return_value=wrong):
                with self.assertRaisesRegex(m9.M9CampaignError, "status"):
                    runner.replay(run, Path(temporary))

    def test_land_rejects_an_input_error_exit_code(self):
        run = m9.RunSpec("matrix", "nominal", "baseline", 1000)
        with tempfile.TemporaryDirectory() as temporary:
            runner = self.make_runner(temporary)
            bad = SimpleNamespace(returncode=3, stdout="", stderr="invalid case")
            with patch("m9_campaign.run_bounded_process", return_value=bad):
                with self.assertRaisesRegex(m9.M9CampaignError, "returned 3"):
                    runner.land(run, Path(temporary) / "runs" / "x")

    def test_runner_enforces_max_runs(self):
        run = m9.RunSpec("matrix", "nominal", "baseline", 1000)
        with tempfile.TemporaryDirectory() as temporary:
            runner = self.make_runner(temporary, max_runs=1)
            ok = SimpleNamespace(returncode=0, stdout="", stderr="")
            with patch("m9_campaign.run_bounded_process", return_value=ok):
                runner.land(run, Path(temporary) / "a" / "x")
                with self.assertRaisesRegex(m9.M9CampaignError, "max_runs"):
                    runner.land(run, Path(temporary) / "b" / "x")

    def test_runner_enforces_the_time_budget(self):
        run = m9.RunSpec("matrix", "nominal", "baseline", 1000)
        with tempfile.TemporaryDirectory() as temporary:
            runner = self.make_runner(temporary)
            runner.deadline = 0.0
            with self.assertRaisesRegex(m9.M9CampaignError, "time budget"):
                runner.land(run, Path(temporary) / "x")


def campaign_arguments(output_root, **overrides):
    values = dict(
        binary=BINARY,
        seeds=(1000, 1001),
        faults=("nominal", "thrust_loss"),
        no_boundary=False,
        max_runs=100,
        max_artifact_bytes=64 * 1024 * 1024,
        time_budget_seconds=240.0,
        jobs=4,
        output_root=Path(output_root),
        summarize_only=None,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def binary_reports_acted() -> bool:
    """O binário atual escreve `acted` em `verification.json`?"""
    if not BINARY.is_file():
        return False
    import subprocess

    with tempfile.TemporaryDirectory() as temporary:
        case = Path(temporary) / "case.json"
        case.write_bytes(m9.case_bytes(m9.build_case(m9.load_template(),
                                                     m9.RunSpec("matrix", "thrust_loss", "baseline", 77))))
        out = Path(temporary) / "out"
        subprocess.run([str(BINARY), "land", str(case), "--seed", "77", "--output", str(out)],
                       capture_output=True, check=False)
        try:
            faults = json.loads((out / "verification.json").read_text(encoding="utf-8"))["faults"]
        except (OSError, KeyError, ValueError):
            return False
        return bool(faults) and all("acted" in f for f in faults)


NO_ACTED = "the vv-rocket binary predates the `acted` field in verification.json; rebuild after the Rust fix"


@unittest.skipUnless(BINARY.is_file(), MISSING_BINARY)
@unittest.skipUnless(binary_reports_acted(), NO_ACTED)
class EndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name) / "campaign"
        m9.execute_campaign(campaign_arguments(cls.root))
        cls.summary = json.loads((cls.root / "summary.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_summary_describes_a_non_preregistered_verified_subset(self):
        s = self.summary
        self.assertEqual(s["schema"], "vv-m9-campaign.v1")
        self.assertFalse(s["preregistered"])
        self.assertEqual(s["seeds"], [1000, 1001])
        # 2 condições x 2 políticas x 2 sementes + varrimento de thrust_loss: 6 x 2 x 2.
        self.assertEqual(len(s["runs"]), 8 + 24)
        self.assertTrue(all(r["replay"] == "verified" for r in s["runs"]))
        self.assertTrue(all(r["exit_code"] in (0, 2) for r in s["runs"]))
        self.assertEqual(len(s["binary_sha256"]), 64)
        self.assertEqual(len(s["source_sha256"]), 64)
        self.assertGreater(s["duration_s"], 0)
        self.assertIn("python scripts/m9_campaign.py", s["command"])
        self.assertEqual(sorted(h["id"] for h in s["hypotheses"]), ["H1", "H2", "H3"])
        self.assertEqual(len(s["boundaries"]), 12)
        self.assertTrue(s["determinism_check"]["identical"])
        self.assertEqual(len(s["determinism_check"]["runs"]), 2)
        self.assertTrue((self.root / "summary.md").is_file())

    def test_artifacts_come_from_the_documented_layout_with_the_shared_case(self):
        base = (self.root / "runs" / "thrust_loss" / "baseline" / "seed-1000" / "case.json").read_text(encoding="utf-8")
        robust = (self.root / "runs" / "thrust_loss" / "robust" / "seed-1000" / "case.json").read_text(encoding="utf-8")
        a, b = json.loads(base), json.loads(robust)
        self.assertEqual(a["faults"], b["faults"])
        self.assertEqual(a["faults"][0], m9.sample_fault("thrust_loss", 1000))
        self.assertEqual((a["controller"]["policy"], b["controller"]["policy"]), ("baseline", "robust"))

    def test_summary_is_regenerated_from_the_stored_runs(self):
        with tempfile.TemporaryDirectory() as temporary:
            copy_root = Path(temporary) / "campaign"
            import shutil

            shutil.copytree(self.root, copy_root)
            args = campaign_arguments(copy_root, summarize_only=copy_root)
            m9.summarize_only(args)
            again = json.loads((copy_root / "summary.json").read_text(encoding="utf-8"))
            self.assertTrue(again["resummarized"])
            for key in ("cells", "pairs", "hypotheses", "boundaries", "runs", "seeds", "preregistered",
                        "source_sha256", "binary_sha256", "boundary_findings", "total_runs"):
                self.assertEqual(again[key], self.summary[key], key)
            self.assertEqual(again["command"], self.summary["command"])

    def test_summarize_only_does_not_trust_a_tampered_conclusion(self):
        with tempfile.TemporaryDirectory() as temporary:
            import shutil

            copy_root = Path(temporary) / "campaign"
            shutil.copytree(self.root, copy_root)
            verification = copy_root / "runs" / "nominal" / "baseline" / "seed-1000" / "verification.json"
            data = json.loads(verification.read_text(encoding="utf-8"))
            data["outcome"] = "hard_landing" if data["outcome"] == "landed" else "landed"
            verification.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(m9.M9CampaignError, "not verified"):
                m9.summarize_only(campaign_arguments(copy_root, summarize_only=copy_root))

    def test_a_stored_case_that_breaks_the_sampling_rule_is_rejected(self):
        run = m9.RunSpec("matrix", "thrust_loss", "robust", 1001)
        template = m9.load_template()
        with tempfile.TemporaryDirectory() as temporary:
            import shutil

            run_dir = Path(temporary) / "run"
            shutil.copytree(self.root / run.rel, run_dir)
            m9.inspect_run(run, run_dir, template, None)  # intacta: aceite
            case = json.loads((run_dir / "case.json").read_text(encoding="utf-8"))
            case["faults"][0]["magnitude"] = 0.29
            (run_dir / "case.json").write_bytes(m9.case_bytes(case))
            with self.assertRaisesRegex(m9.M9CampaignError, "pre-registered rule"):
                m9.inspect_run(run, run_dir, template, None)

    def test_main_refuses_a_non_empty_output_root(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = m9.main(["--seeds", "1000", "--faults", "nominal", "--no-boundary",
                            "--output-root", str(self.root)])
        self.assertEqual(code, 1)
        self.assertIn("not empty", stderr.getvalue())

    def test_main_rejects_a_plan_above_max_runs_before_running_anything(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "campaign"
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = m9.main(["--seeds", "1000,1001", "--faults", "nominal,thrust_loss",
                                "--max-runs", "10", "--output-root", str(target)])
            self.assertEqual(code, 1)
            self.assertIn("max_runs", stderr.getvalue())
            self.assertFalse(target.exists())

    def test_main_stops_when_the_artifact_budget_is_exceeded(self):
        with tempfile.TemporaryDirectory() as temporary:
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = m9.main(["--seeds", "1000", "--faults", "nominal", "--no-boundary",
                                "--max-artifact-bytes", "65536", "--jobs", "1",
                                "--output-root", str(Path(temporary) / "campaign")])
            self.assertEqual(code, 1)
            self.assertIn("limit", stderr.getvalue())

    def test_main_stops_when_the_time_budget_is_exceeded(self):
        with tempfile.TemporaryDirectory() as temporary:
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = m9.main(["--seeds", "1000", "--faults", "nominal", "--no-boundary",
                                "--time-budget-seconds", "0.001", "--jobs", "1",
                                "--output-root", str(Path(temporary) / "campaign")])
            self.assertEqual(code, 1)
            self.assertIn("M9 campaign failed", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
