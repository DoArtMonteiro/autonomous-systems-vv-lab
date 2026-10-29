"""Retrospetiva P1 do M9.1: proveniência, limites e erros de execução."""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import m91_retrospective as retro  # noqa: E402
from process_limits import ProcessLimitError  # noqa: E402

TRACE = b'{"trace":1}'


def write_stored(campaign: Path) -> None:
    run = campaign / "runs" / "nominal" / "baseline" / "seed-1000"
    run.mkdir(parents=True)
    (run / "run.json").write_text(json.dumps({"seed": 1000, "policy": "baseline"}), encoding="utf-8")
    (run / "verification.json").write_text(json.dumps({"outcome": "landed"}), encoding="utf-8")
    (run / "case.json").write_text(json.dumps({"faults": []}), encoding="utf-8")
    (run / "trace.json").write_bytes(TRACE)


def fake_land(command, **kwargs):
    out = Path(command[command.index("--output") + 1])
    out.mkdir(parents=True)
    (out / "trace.json").write_bytes(TRACE)
    invariants = [{"id": "S5_no_powered_ascent", "pass": True, "worst_value": 0.0}]
    (out / "verification.json").write_text(
        json.dumps({"outcome": "landed", "invariants": invariants}), encoding="utf-8")
    (out / "run.json").write_text(json.dumps({"source_sha256": "abc"}), encoding="utf-8")
    return subprocess.CompletedProcess(command, 0, stdout="", stderr="")


class RetrospectiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        write_stored(self.tmp / "campaign")
        self.binary = self.tmp / "vv-rocket"
        self.binary.write_bytes(b"binary")
        self.output = self.tmp / "retro.json"

    def run_main(self, runner, *extra):
        argv = ["x", "--campaign", str(self.tmp / "campaign"), "--binary", str(self.binary),
                "--output", str(self.output), *extra]
        with patch.object(sys, "argv", argv), patch.object(retro, "run_bounded_process", runner), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return retro.main()

    def test_the_artifact_carries_provenance(self):
        self.assertEqual(self.run_main(fake_land), 0)
        result = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(result["schema"], "vv-m91-retrospective.v2")
        self.assertEqual(len(result["binary_sha256"]), 64)
        self.assertEqual(result["source_sha256"], ["abc"])
        for key in ("machine", "command", "duration_s"):
            self.assertTrue(result[key] not in (None, ""), key)
        self.assertNotIn(str(self.tmp), result["command"])
        self.assertEqual(result["errors"], [])

    def test_a_timeout_or_output_overflow_is_an_error_not_a_pass(self):
        def refuse(command, **kwargs):
            raise ProcessLimitError("land exceeded the time budget")

        self.assertEqual(self.run_main(refuse), 1)
        result = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(len(result["errors"]), 1)
        self.assertFalse(result["prediction_holds"])
        self.assertEqual(result["traces_identical"], 0)

    def test_limits_are_passed_to_every_run_and_validated(self):
        seen = {}

        def spy(command, **kwargs):
            seen.update(kwargs)
            return fake_land(command, **kwargs)

        self.run_main(spy)
        self.assertEqual(seen["max_output_bytes"], retro.m9.OUTPUT_LIMIT_BYTES)
        self.assertGreater(seen["timeout_seconds"], 0)
        self.assertLessEqual(seen["timeout_seconds"], retro.m9.DEFAULT_TIME_BUDGET_SECONDS)
        for bad in (("--jobs", "0"), ("--jobs", "99"), ("--max-runs", "0"), ("--time-budget-seconds", "0")):
            with self.assertRaises(SystemExit):
                self.run_main(fake_land, *bad)
        self.assertEqual(self.run_main(fake_land, "--max-runs", "1"), 0)
        write_stored(self.tmp / "campaign2")
        shutil.copytree(self.tmp / "campaign2" / "runs" / "nominal" / "baseline" / "seed-1000",
                        self.tmp / "campaign" / "runs" / "nominal" / "baseline" / "seed-1001")
        self.assertEqual(self.run_main(fake_land, "--max-runs", "1"), 3)


if __name__ == "__main__":
    unittest.main()
