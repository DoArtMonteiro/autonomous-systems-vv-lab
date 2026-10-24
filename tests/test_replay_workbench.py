from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import replay_workbench as wb  # noqa: E402
from adversarial_campaign import default_binary  # noqa: E402

LAB = default_binary("vv-lab")
CASE_ID = "corpus/delayed_after_fallback/01"
BAD = ["temporal/command_applied/delayed_actuation"]
# Real M6 run root for the optional integration tests (the evidence is gitignored).
REAL_RUN = os.environ.get("VV_WORKBENCH_RUN")


def row(violations=()):
    return {
        "violations": list(violations),
        "first_violation_tick": None,
        "inconclusive": [],
        "untriggered": [],
        "mission": "completed",
        "completion_tick": 10,
        "waypoints_completed": 1,
        "fallback_ticks": 0,
        "movement_ticks": 6,
        "actuator_fault_events": 0,
        "distance_remaining_mm": 0,
    }


@unittest.skipUnless(LAB.exists(), "release vv-lab binary not built")
class WorkbenchFixture(unittest.TestCase):
    """A minimal run root around one genuine `vv-lab run-m4` case."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "run-root"
        self.case = self.root / "run" / "cases" / CASE_ID
        self.case.parent.mkdir(parents=True)
        subprocess.run(
            [
                str(LAB),
                "run-m4",
                str(ROOT / "scenarios/m3/delayed-after-fallback.json"),
                "--seed",
                "42",
                "--controller",
                "dominant_axis",
                "--contracts",
                str(ROOT / "scenarios/m3/contracts-nominal.json"),
                "--actuator",
                str(ROOT / "scenarios/m3/actuator-delayed.json"),
                "--output",
                str(self.case),
            ],
            capture_output=True,
        )
        # Exit 2 means the case violates properties, which is what the fixture needs.
        self.assertTrue((self.case / "m4.json").is_file())
        # Side copies as vv-repair writes them: the normalised configuration that the artifacts embed.
        events = json.loads((self.case / "events.json").read_text(encoding="utf-8"))
        verification = json.loads((self.case / "verification.json").read_text(encoding="utf-8"))
        (self.case / "scenario.json").write_text(json.dumps(events["scenario"]), encoding="utf-8")
        (self.case / "actuator.json").write_text(json.dumps(verification["actuator_config"]), encoding="utf-8")
        shutil.copyfile(ROOT / "scenarios/m3/contracts-nominal.json", self.case / "contracts.json")
        manifest = json.loads((self.case / "m4.json").read_text(encoding="utf-8"))
        workloads = [
            {"index": 0, "split": "heldout", "seed": 7, "draw": 0, "family": "timing", "atoms": []},
            {"index": 1, "split": "heldout", "seed": 7, "draw": 1, "family": "mixed", "atoms": []},
            {"index": 2, "split": "tuning", "seed": 1, "draw": 0, "family": "mixed", "atoms": []},
        ]
        self.evidence = {
            "schema": "vv-repair.evidence.v1",
            "source_sha256": manifest["source_sha256"],
            "experiment_sha256": "e" * 64,
            "evidence_sha256": "a" * 64,
            "experiment": {
                "baseline": {"id": "baseline"},
                "candidates": [{"id": "cand"}],
                "sim_seeds": [42],
                "tuning_seeds": [1],
                "heldout_seeds": [7],
                "acceptance": {
                    "alpha_permille": 50,
                    "max_completion_loss_permille": 10,
                    "max_mean_distance_increase_mm": 100,
                    "min_heldout_pairs": 200,
                },
            },
            "workloads": {"delayed_after_fallback": workloads},
            "results": {
                "delayed_after_fallback": {
                    "baseline": {"42": [row(), row(BAD), row()]},
                    # pair 0 broken, pair 1 fixed, pair 2 broken on a tuning seed (not counted)
                    "cand": {"42": [row(BAD), row(), row(BAD)]},
                }
            },
            "corpus": [
                {
                    "id": CASE_ID,
                    "suite": "delayed_after_fallback",
                    "found_on": "baseline",
                    "class": "safety/safe_fallback/none",
                    "sim_seed": 42,
                    "steps": manifest["metrics"]["ticks"],
                    "atoms": [],
                    "case_dir": "cases/" + CASE_ID,
                    "m4_sha256": wb.sha256_file(self.case / "m4.json"),
                    "replay": {
                        "baseline": {"status": "persisted", "violations": ["safety/safe_fallback/none"], "mission": "incomplete"},
                        "cand": {"status": "resolved", "violations": BAD, "mission": "incomplete"},
                    },
                }
            ],
            "introduced": [],
        }
        self.analysis = {
            "acceptance": self.evidence["experiment"]["acceptance"],
            "candidates": [
                {
                    "id": "cand",
                    "role": "candidate",
                    "verdict": {"decision": "reject", "safety": "regressed", "progress": "pass", "notes": ["n</script><b>x"]},
                    "gates": {"safety": True, "completion": True, "no_suite_regression": False},
                    "summary": {"heldout": {"pairs": 2, "fixed": 1, "broken": 1, "completion_lost": 0, "baseline_completed": 2}},
                    "suites": {"delayed_after_fallback": {"heldout": {"fixed": 1, "broken": 1}}},
                }
            ],
        }
        self.write()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self) -> None:
        (self.root / "run" / "evidence.json").write_text(json.dumps(self.evidence), encoding="utf-8")
        (self.root / "analysis.json").write_text(json.dumps(self.analysis), encoding="utf-8")
        summary = {"evidence_sha256": self.evidence["evidence_sha256"], "source_sha256": self.evidence["source_sha256"]}
        (self.root / "summary.json").write_text(json.dumps(summary), encoding="utf-8")

    def payload(self, binary=LAB):
        return wb.build_payload(self.root, binary)

    def case_view(self, payload):
        return next(c for c in payload["cases"] if c["id"] == CASE_ID)


class IntegrityTests(WorkbenchFixture):
    def test_genuine_case_passes_integrity_and_replay(self):
        view = self.case_view(self.payload())
        self.assertEqual(view["integrity"]["problems"], [])
        self.assertEqual(view["replay_check"]["status"], "verified")
        self.assertIn("M4 replay verified", view["replay_check"]["stdout"])

    def test_flipped_byte_is_flagged(self):
        events = self.case / "events.json"
        data = bytearray(events.read_bytes())
        data[-5] = ord("0") if data[-5] != ord("0") else ord("1")
        events.write_bytes(bytes(data))
        view = self.case_view(self.payload())
        self.assertTrue(any("events.json" in p and "sha256" in p for p in view["integrity"]["problems"]))
        self.assertNotEqual(view["replay_check"]["status"], "verified")

    def test_missing_artifact_is_flagged_without_crashing(self):
        (self.case / "report.json").unlink()
        view = self.case_view(self.payload())
        self.assertTrue(any("report.json" in p and "missing" in p for p in view["integrity"]["problems"]))

    def test_manifest_hash_mismatch_with_evidence_is_flagged(self):
        self.evidence["corpus"][0]["m4_sha256"] = "0" * 64
        self.write()
        view = self.case_view(self.payload())
        self.assertTrue(any("m4.json" in p for p in view["integrity"]["problems"]))

    def test_incompatible_source_revision_surfaces_replay_stderr(self):
        manifest = json.loads((self.case / "m4.json").read_text(encoding="utf-8"))
        manifest["source_sha256"] = "38039c255f6f60c8b1a5d50332c2280665df469a1a00ad43b06f5df47bf643cb"
        (self.case / "m4.json").write_text(json.dumps(manifest), encoding="utf-8")
        view = self.case_view(self.payload())
        self.assertEqual(view["replay_check"]["status"], "failed")
        # Editing the manifest also breaks manifest_sha256, which replay-m4 checks first.
        self.assertTrue(view["replay_check"]["stderr"].startswith("error:"))
        self.assertTrue(any("source_sha256" in p for p in view["integrity"]["problems"]))

    def test_without_binary_nothing_is_called_verified(self):
        view = self.case_view(self.payload(binary=None))
        self.assertEqual(view["replay_check"]["status"], "not_run")

    def test_tampered_side_configuration_is_flagged(self):
        actuator = json.loads((self.case / "actuator.json").read_text(encoding="utf-8"))
        actuator["faults"][0]["windows"][0]["start_tick"] += 1
        (self.case / "actuator.json").write_text(json.dumps(actuator), encoding="utf-8")
        view = self.case_view(self.payload())
        self.assertTrue(any("actuator.json differs" in p for p in view["integrity"]["problems"]))
        # The drawn window still comes from the hashed copy, not from the edited file.
        verification = json.loads((self.case / "verification.json").read_text(encoding="utf-8"))
        windows = verification["actuator_config"]["faults"][0]["windows"]
        self.assertEqual(view["trace"]["actuator_faults"][0]["windows"], windows)

    def test_broken_event_chain_is_flagged(self):
        doc = json.loads((self.case / "events.json").read_text(encoding="utf-8"))
        doc["events"][3]["previous_hash"] = "f" * 64
        (self.case / "events.json").write_text(json.dumps(doc), encoding="utf-8")
        view = self.case_view(self.payload())
        self.assertTrue(any("hash chain breaks" in p for p in view["integrity"]["problems"]))

    def test_case_dir_outside_run_is_refused(self):
        for bad in ("../../outside", "C:outside", "cases/../../x"):
            self.evidence["corpus"][0]["case_dir"] = bad
            self.write()
            view = self.case_view(self.payload())
            self.assertEqual(view["integrity"]["problems"], ["case_dir is unsafe"], bad)
            self.assertIsNone(view["trace"])
            self.assertEqual(view["replay_check"]["status"], "not_run")

    def test_run_level_checks_flag_summary_mismatch(self):
        (self.root / "summary.json").write_text(json.dumps({"evidence_sha256": "b" * 64}), encoding="utf-8")
        failed = [c["name"] for c in self.payload()["checks"] if not c["ok"]]
        self.assertIn("evidence_sha256 matches summary.json", failed)


class TraceTests(WorkbenchFixture):
    def test_ticks_are_the_recorded_tick_results_only(self):
        view = self.case_view(self.payload())
        events = json.loads((self.case / "events.json").read_text(encoding="utf-8"))["events"]
        recorded = [e for e in events if e["event"]["kind"] == "tick_result"]
        ticks = view["trace"]["ticks"]
        self.assertEqual([t["tick"] for t in ticks], [e["tick"] for e in recorded])
        for t, e in zip(ticks, recorded):
            self.assertEqual(t["truth"], e["event"]["truth_position"])
            self.assertEqual(t["truth_from"], e["event"]["truth_from"])
            self.assertEqual(t["action"], e["event"]["action"])

    def test_violation_and_fault_markers_come_from_artifacts(self):
        trace = self.case_view(self.payload())["trace"]
        verification = json.loads((self.case / "verification.json").read_text(encoding="utf-8"))
        failed = {c["contract_id"] for c in verification["contract_results"] if c["outcome"] == "FAIL"}
        self.assertEqual({c["id"] for c in trace["contracts"] if c["outcome"] == "FAIL"}, failed)
        self.assertTrue(trace["actuator_faults"], "the fixture actuator has a delay window")
        expected = "verification.json actuator_config (configured)"
        self.assertTrue(all(f["source"] == expected for f in trace["actuator_faults"]))
        self.assertTrue([t["tick"] for t in trace["ticks"] if t["gps_dropped"]], "the fixture scenario drops GPS samples")

    def test_failed_contract_shows_the_violated_instance_and_recorded_actuator_events(self):
        trace = self.case_view(self.payload())["trace"]
        verification = json.loads((self.case / "verification.json").read_text(encoding="utf-8"))
        for failure in verification["failures"]:
            shown = next(c for c in trace["contracts"] if c["id"] == failure["contract_id"])
            self.assertEqual(shown["trigger_tick"], failure["first_trigger_tick"])
            self.assertEqual(shown["deadline_tick"], failure["applicable_deadline_tick"])
        recorded = {(i["event"]["kind"], i["event"]["tick"]) for f in verification["failures"] for i in f["fault_events"]}
        self.assertEqual({(e["kind"], e["tick"]) for e in trace["actuator_events"]}, recorded)

    def test_actuation_per_tick_comes_from_counterexample_ticks_only(self):
        trace = self.case_view(self.payload())["trace"]
        verification = json.loads((self.case / "verification.json").read_text(encoding="utf-8"))
        recorded = {}
        for f in verification["failures"]:
            for row in f.get("counterexample_ticks", []):
                recorded.setdefault(row["tick"], row)
        self.assertTrue(recorded, "the fixture has counterexample ticks")
        for tick in trace["ticks"]:
            row = recorded.get(tick["tick"])
            if row is None:
                self.assertIsNone(tick["actuation"], tick["tick"])
            else:
                self.assertEqual(tick["actuation"]["realized_action"], row["realized_action"])
                self.assertEqual(tick["actuation"]["actuator_behavior"], row["actuator_behavior"])
                self.assertNotIn("conflict", tick["actuation"])

    def test_payload_is_reproducible_apart_from_build_metadata(self):
        first, second = self.payload(), self.payload()
        first.pop("generated")
        second.pop("generated")
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))

    def test_conflicting_actuation_records_are_flagged(self):
        doc = json.loads((self.case / "verification.json").read_text(encoding="utf-8"))
        rows = [r for f in doc["failures"] for r in f.get("counterexample_ticks", [])]
        first = rows[0]
        clash = dict(first, realized_action={"heading": "north", "distance_mm": 999})
        doc["failures"].append({"contract_id": "synthetic", "counterexample_ticks": [clash]})
        (self.case / "verification.json").write_text(json.dumps(doc), encoding="utf-8")
        trace = wb.trace(self.case)
        flagged = next(t for t in trace["ticks"] if t["tick"] == first["tick"])
        self.assertTrue(flagged["actuation"]["conflict"])

    def test_missing_events_gives_no_trace(self):
        (self.case / "events.json").unlink()
        self.assertIsNone(self.case_view(self.payload())["trace"])


class PairTests(WorkbenchFixture):
    def test_broken_pairs_are_heldout_rows_only(self):
        pairs = self.payload()["broken_pairs"]["cand"]
        self.assertEqual([(p["suite"], p["workload"]) for p in pairs], [("delayed_after_fallback", 0)])
        self.assertEqual(pairs[0]["candidate_violations"], BAD)

    def test_recount_check_matches_analysis(self):
        checks = {c["name"]: c for c in self.payload()["checks"]}
        self.assertTrue(checks["broken pairs recounted from rows match analysis.json"]["ok"])

    def test_recount_check_fails_when_analysis_disagrees(self):
        self.analysis["candidates"][0]["suites"]["delayed_after_fallback"]["heldout"]["broken"] = 3
        self.write()
        checks = {c["name"]: c for c in self.payload()["checks"]}
        self.assertFalse(checks["broken pairs recounted from rows match analysis.json"]["ok"])


class RenderTests(WorkbenchFixture):
    def test_html_embeds_data_without_breaking_out_of_script(self):
        html = wb.render(self.payload(), focus_case=CASE_ID)
        self.assertNotIn("n</script><b>x", html)
        self.assertEqual(html.count("</script>"), html.count("<script"))

    def test_scenario_and_candidate_context_come_from_the_stored_files(self):
        self.evidence["suites"] = [{"id": "delayed_after_fallback", "description": "GPS dropout and a delayed command"}]
        self.analysis["candidates"][0]["overrides"] = {"fallback_after_ticks": 2}
        self.write()
        payload = self.payload()
        self.assertEqual(payload["run"]["suites"], {"delayed_after_fallback": "GPS dropout and a delayed command"})
        self.assertEqual(payload["candidates"][0]["overrides"], {"fallback_after_ticks": 2})

    def test_page_carries_the_honesty_labels_and_accessible_controls(self):
        html = wb.render(self.payload(), focus_case=CASE_ID)
        for label in (
            "Trace shown: ",
            "No candidate trace is stored",
            "not recorded for this tick",
            "safety (pooled strict RD)",
            "optgroup",
            "aria-valuetext",
            "aria-pressed",
            "data-fid",
            "Arena (recorded scenario)",
            "fails gate",
            "failed gate",
            "Verified by recomputation",
            "configuration.`",
        ):
            self.assertIn(label, html, label)

    def test_output_inside_run_directory_is_refused(self):
        with self.assertRaises(wb.WorkbenchError):
            wb.check_output(self.root, self.root / "run" / "workbench.html")
        wb.check_output(self.root, self.root / "workbench.html")


@unittest.skipUnless(REAL_RUN and LAB.exists(), "set VV_WORKBENCH_RUN to a real M6 run root")
class RealRunTests(unittest.TestCase):
    def test_real_run_validates_and_recounts(self):
        payload = wb.build_payload(Path(REAL_RUN), LAB)
        self.assertTrue(all(c["ok"] for c in payload["checks"]), payload["checks"])
        self.assertTrue(all(c["replay_check"]["status"] == "verified" for c in payload["cases"]))
        self.assertTrue(all(not c["integrity"]["problems"] for c in payload["cases"]))

    def test_generation_keeps_vv_repair_replay_green(self):
        root = Path(REAL_RUN)
        with tempfile.TemporaryDirectory() as tmp:
            wb.write_workbench(root, Path(tmp) / "workbench.html", LAB, None)
        result = subprocess.run(
            [str(default_binary("vv-repair")), "replay", str(root / "run")], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
