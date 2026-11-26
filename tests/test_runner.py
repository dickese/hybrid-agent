from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from bridge import proc, store
from tests.support import (
    BridgeTestCase,
    make_fixture,
    run_cli,
    run_git,
    task_data,
    write_fake_config,
    write_task,
)


class RunnerTests(BridgeTestCase):
    def test_success_completed_not_accepted(self) -> None:
        code, payload, stdout, stderr = self.run_task(
            task_data(metadata={"fake_scenario": "success"})
        )
        self.assertEqual(code, 0, stderr)
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["status"], "COMPLETED")
        self.assertTrue(payload["scope_ok"])
        self.assertEqual(payload["changed_files"], ["add.py"])
        self.assertEqual(payload["error"], None)
        self.assertTrue(payload["session_id"].startswith("ses_"))
        self.assertNotIn("ACCEPTED", json.dumps(payload))
        completed = subprocess.run(
            [sys.executable, "-B", "test_add.py"],
            cwd=str(self.fixture),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )
        self.assertEqual(completed.returncode, 0)
        status = run_git(self.fixture, "status", "--porcelain").stdout
        self.assertEqual(status.strip(), "M add.py")
        run_id = payload["run_id"]
        result = store.read_result(self.runtime, run_id)
        self.assertEqual(result["status"], "COMPLETED")
        state = store.read_state(self.runtime, run_id)
        self.assertEqual(state["status"], "COMPLETED")
        for name in ("stdout.ndjson", "stderr.log", "diff.patch", "result.json", "state.json"):
            self.assertTrue((self.runtime / "runs" / run_id / name).is_file(), name)

    def test_read_only_success_no_changes(self) -> None:
        code, payload, _, stderr = self.run_task(
            task_data(
                profile="explorer",
                allowed_paths=[],
                metadata={"fake_scenario": "read_success"},
            )
        )
        self.assertEqual(code, 0, stderr)
        assert payload is not None
        self.assertEqual(payload["status"], "COMPLETED")
        self.assertEqual(payload["changed_files"], [])
        self.assertEqual(
            run_git(self.fixture, "status", "--porcelain").stdout.strip(), ""
        )

    def test_read_only_edit_tool_attempt_blocked(self) -> None:
        code, payload, _, stderr = self.run_task(
            task_data(
                profile="explorer",
                allowed_paths=[],
                metadata={"fake_scenario": "read_edit_attempt"},
            )
        )
        self.assertEqual(code, 5, stderr)
        assert payload is not None
        self.assertEqual(payload["status"], "BLOCKED")
        self.assertIn("read_only_edit_tool", json.dumps(payload["error"]))

    def test_scope_violation_blocked_and_diff_preserved(self) -> None:
        code, payload, _, stderr = self.run_task(
            task_data(metadata={"fake_scenario": "scope_violation"})
        )
        self.assertEqual(code, 5, stderr)
        assert payload is not None
        self.assertEqual(payload["status"], "BLOCKED")
        self.assertIn("outside_scope", json.dumps(payload["error"]))
        self.assertIn("test_add.py", payload["changed_files"])
        run_id = payload["run_id"]
        diff = (self.runtime / "runs" / run_id / "diff.patch").read_text(
            encoding="utf-8"
        )
        self.assertIn("test_add.py", diff)
        self.assertIn("tampered", (self.fixture / "test_add.py").read_text(encoding="utf-8"))

    def test_malformed_ndjson_fails_closed(self) -> None:
        code, payload, _, stderr = self.run_task(
            task_data(metadata={"fake_scenario": "malformed"})
        )
        self.assertEqual(code, 3, stderr)
        assert payload is not None
        self.assertEqual(payload["status"], "FAILED")
        self.assertEqual(payload["error"]["code"], "STREAM_INVALID")

    def test_error_event_fails(self) -> None:
        code, payload, _, stderr = self.run_task(
            task_data(metadata={"fake_scenario": "error_event"})
        )
        self.assertEqual(code, 3, stderr)
        assert payload is not None
        self.assertEqual(payload["status"], "FAILED")
        self.assertEqual(payload["error"]["code"], "worker_error")

    def test_nonzero_exit_fails(self) -> None:
        code, payload, _, stderr = self.run_task(
            task_data(metadata={"fake_scenario": "nonzero"})
        )
        self.assertEqual(code, 3, stderr)
        assert payload is not None
        self.assertEqual(payload["status"], "FAILED")
        self.assertEqual(payload["error"]["code"], "worker_exit_nonzero")

    def test_auth_failure_blocked(self) -> None:
        code, payload, _, stderr = self.run_task(
            task_data(metadata={"fake_scenario": "auth_error"})
        )
        self.assertEqual(code, 5, stderr)
        assert payload is not None
        self.assertEqual(payload["status"], "BLOCKED")
        self.assertEqual(payload["error"]["category"], "auth")

    def test_transient_failure_classified(self) -> None:
        code, payload, _, stderr = self.run_task(
            task_data(metadata={"fake_scenario": "transient"})
        )
        self.assertEqual(code, 3, stderr)
        assert payload is not None
        self.assertEqual(payload["status"], "FAILED")
        self.assertEqual(payload["error"]["category"], "rate_limit")
        self.assertTrue(payload["error"]["retryable"])

    def test_timeout_kills_worker(self) -> None:
        task = task_data(
            timeout_seconds=1,
            metadata={"fake_scenario": "timeout"},
        )
        code, payload, _, stderr = self.run_task(task)
        self.assertEqual(code, 4, stderr)
        assert payload is not None
        self.assertEqual(payload["status"], "TIMED_OUT")
        self.assertTrue(payload["worker"]["kill_verified"])
        pid = payload["worker"]["pid"]
        creation = payload["worker"]["creation_time"]
        self.assertIsNotNone(pid)
        self.assertFalse(proc.process_alive(pid, creation))

    def test_dirty_baseline_blocked_before_run(self) -> None:
        (self.fixture / "add.py").write_text("user edit\n", encoding="utf-8")
        code, payload, _, stderr = self.run_task()
        self.assertEqual(code, 5, stderr)
        assert payload is not None
        self.assertEqual(payload["status"], "BLOCKED")
        self.assertEqual(payload["error"]["code"], "policy_blocked")
        self.assertEqual(store.list_runs(self.runtime), [])

    def test_wrong_branch_blocked(self) -> None:
        run_git(self.fixture, "checkout", "-b", "other")
        code, payload, _, stderr = self.run_task()
        self.assertEqual(code, 5, stderr)
        assert payload is not None
        self.assertEqual(payload["status"], "BLOCKED")

    def test_expected_head_mismatch_blocked(self) -> None:
        code, payload, _, stderr = self.run_task(
            task_data(expected_head="0" * 40)
        )
        self.assertEqual(code, 5, stderr)
        assert payload is not None
        self.assertEqual(payload["status"], "BLOCKED")

    def test_duplicate_task_rejected(self) -> None:
        first = task_data(metadata={"fake_scenario": "success"})
        code, payload, _, stderr = self.run_task(first)
        self.assertEqual(code, 0, stderr)
        run_git(self.fixture, "checkout", "--", "add.py")
        code, payload, _, stderr = self.run_task(first)
        self.assertEqual(code, 5, stderr)
        assert payload is not None
        self.assertEqual(payload["status"], "BLOCKED")
        self.assertIn("already has a recorded run", payload["error"]["message"])

    def test_unicode_and_space_path(self) -> None:
        fixture = make_fixture(self.root / "fixture có dấu")
        config = write_fake_config(
            self.root / "unicode-config", fixture, runtime_root=self.runtime
        )
        task = write_task(self.root / "unicode-task.json", task_data(metadata={"fake_scenario": "success"}))
        code, payload, _, stderr = run_cli(
            ["run", "--config", str(config), "--task", str(task)]
        )
        self.assertEqual(code, 0, stderr)
        assert payload is not None
        self.assertEqual(payload["status"], "COMPLETED")

    def test_secret_redacted_from_summary_and_result(self) -> None:
        secret = "sk-TESTONLY1234567890ABCDEF"
        code, payload, _, stderr = self.run_task(
            task_data(metadata={"fake_scenario": "secret"})
        )
        self.assertEqual(code, 0, stderr)
        assert payload is not None
        self.assertNotIn(secret, payload["summary"])
        self.assertIn("[REDACTED]", payload["summary"])
        run_id = payload["run_id"]
        result_text = (self.runtime / "runs" / run_id / "result.json").read_text(
            encoding="utf-8"
        )
        self.assertNotIn(secret, result_text)
        stdout_text = (self.runtime / "runs" / run_id / "stdout.ndjson").read_text(
            encoding="utf-8"
        )
        self.assertNotIn(secret, stdout_text)

    def test_secret_in_diff_blocked_and_redacted_evidence(self) -> None:
        secret = "sk-TESTONLY1234567890ABCDEF"
        code, payload, _, stderr = self.run_task(
            task_data(metadata={"fake_scenario": "secret_in_diff"})
        )
        self.assertEqual(code, 5, stderr)
        assert payload is not None
        self.assertEqual(payload["status"], "BLOCKED")
        self.assertIn("secret_in_diff", json.dumps(payload["error"]))
        run_id = payload["run_id"]
        diff = (self.runtime / "runs" / run_id / "diff.patch").read_text(
            encoding="utf-8"
        )
        self.assertNotIn(secret, diff)
        self.assertIn("[REDACTED]", diff)


if __name__ == "__main__":
    unittest.main()
