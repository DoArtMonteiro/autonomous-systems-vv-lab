from __future__ import annotations

import sys
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from m4_campaign import (  # noqa: E402
    CASES,
    Campaign,
    M4CampaignError,
    plan_campaign,
)
from check_platform_artifacts import (  # noqa: E402
    CampaignError,
    compare_m4_platform_outputs,
)


class M4CampaignPlanningTests(unittest.TestCase):
    def test_repository_matrix_validates_all_invocation_budgets_before_execution(self):
        plan = plan_campaign((42, 1337, 2026))

        self.assertEqual(len(CASES), 4)
        self.assertEqual(plan["planned_pairs"], 12)
        self.assertEqual(plan["planned_simulator_invocations"], 72)
        self.assertEqual(plan["planned_comparison_invocations"], 12)
        self.assertEqual(plan["planned_total_invocations"], 84)
        self.assertEqual(plan["max_artifact_bytes"], 64 * 1024 * 1024)
        self.assertEqual(plan["time_budget_seconds"], 120.0)

    def test_campaign_rejects_a_plan_that_would_exceed_the_invocation_cap(self):
        with self.assertRaisesRegex(M4CampaignError, "needs 84 invocations"):
            plan_campaign((42, 1337, 2026), max_invocations=83)

    def test_single_seed_plan_counts_six_simulator_invocations_per_pair(self):
        plan = plan_campaign((42,))

        self.assertEqual(plan["planned_pairs"], 4)
        self.assertEqual(plan["planned_simulator_invocations"], 24)
        self.assertEqual(plan["planned_comparison_invocations"], 4)
        self.assertEqual(plan["planned_total_invocations"], 28)

    def test_campaign_rejects_duplicate_seeds_before_any_work(self):
        with self.assertRaisesRegex(M4CampaignError, "unique"):
            plan_campaign((42, 42))

    def test_comparison_counts_its_two_replays_before_launching(self):
        plan = plan_campaign((42,))
        plan["max_invocations"] = 7
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            campaign = Campaign(Path("vv-lab"), Path(temporary), (42,), plan)
            result = SimpleNamespace(returncode=0, stdout="", stderr="")
            with patch("m4_campaign.run_bounded_process", return_value=result) as run:
                for _ in range(4):
                    campaign.invoke(["vv-lab"], "run", simulator_invocations=1)
                comparison_log = campaign.invoke(
                    ["vv-lab", "compare-m4"],
                    "compare",
                    simulator_invocations=2,
                    comparison=True,
                )
                self.assertTrue(comparison_log.is_file())
                self.assertEqual(campaign.simulator_invocations, 6)
                self.assertEqual(campaign.comparison_invocations, 1)
                self.assertEqual(campaign.command_invocations, 5)
                with self.assertRaisesRegex(M4CampaignError, "invocation budget"):
                    campaign.invoke(["vv-lab"], "extra", simulator_invocations=1)
                self.assertEqual(run.call_count, 5)

    def test_platform_comparison_covers_all_pairs_and_rejects_calendar_drift(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            root = Path(temporary)
            entries = []
            for scenario in (
                "nominal",
                "x-first-overshoot",
                "gps-fallback",
                "intermittent-actuation",
            ):
                for seed in (42, 1337, 2026):
                    entries.append(
                        {
                            "scenario": scenario,
                            "seed": seed,
                            "calendar_sha256": "a" * 64,
                            "comparison_sha256": "b" * 64,
                            "input_sha256": {
                                "scenario": "c" * 64,
                                "contracts": "d" * 64,
                                "actuator": "e" * 64,
                            },
                            "repeat_output_sha256": {
                                policy: {
                                    name: "f" * 64
                                    for name in (
                                        "events.json",
                                        "report.json",
                                        "mission.json",
                                        "verification.json",
                                        "m4.json",
                                    )
                                }
                                for policy in ("dominant_axis", "x_first")
                            },
                            "policy_metrics": {
                                "dominant_axis": {},
                                "x_first": {},
                            },
                        }
                    )
            for platform in ("linux-campaign", "windows-campaign"):
                directory = root / platform
                directory.mkdir()
                (directory / "m4-fingerprints.json").write_text(
                    json.dumps({"schema_version": 1, "suite": "m4", "outputs": entries}),
                    encoding="utf-8",
                )

            result = compare_m4_platform_outputs(root)
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["pair_count"], 12)

            for digest_path in (
                ("calendar_sha256",),
                ("comparison_sha256",),
                ("input_sha256", "scenario"),
                ("repeat_output_sha256", "x_first", "m4.json"),
            ):
                malformed = json.loads(json.dumps(entries))
                value = malformed[0]
                for key in digest_path[:-1]:
                    value = value[key]
                value[digest_path[-1]] = "z" * 64
                for platform in ("linux-campaign", "windows-campaign"):
                    (root / platform / "m4-fingerprints.json").write_text(
                        json.dumps(
                            {
                                "schema_version": 1,
                                "suite": "m4",
                                "outputs": malformed,
                            }
                        ),
                        encoding="utf-8",
                    )
                with self.subTest(digest_path=digest_path):
                    with self.assertRaises(CampaignError):
                        compare_m4_platform_outputs(root)

            for platform in ("linux-campaign", "windows-campaign"):
                (root / platform / "m4-fingerprints.json").write_text(
                    json.dumps({"schema_version": 1, "suite": "m4", "outputs": entries}),
                    encoding="utf-8",
                )

            changed = json.loads(
                (root / "windows-campaign" / "m4-fingerprints.json").read_text(
                    encoding="utf-8"
                )
            )
            changed["outputs"][0]["calendar_sha256"] = "0" * 64
            (root / "windows-campaign" / "m4-fingerprints.json").write_text(
                json.dumps(changed), encoding="utf-8"
            )
            with self.assertRaisesRegex(CampaignError, "differ between Linux and Windows"):
                compare_m4_platform_outputs(root)


if __name__ == "__main__":
    unittest.main()
