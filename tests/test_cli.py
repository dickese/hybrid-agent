from __future__ import annotations

import json
import unittest

from tests.support import BridgeTestCase, run_cli, task_data, write_task


class CliTests(BridgeTestCase):
    def test_health_offline_fake_pass(self) -> None:
        code, payload, stdout, stderr = run_cli(
            ["health", "--config", str(self.config)]
        )
        self.assertEqual(code, 0, stderr)
        assert payload is not None
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["worker_type"], "fake")
        self.assertEqual(len(stdout.strip().splitlines()), 1)

    def test_health_live_fake_blocked(self) -> None:
        code, payload, _, stderr = run_cli(
            ["health", "--config", str(self.config), "--live"]
        )
        self.assertEqual(code, 5, stderr)
        assert payload is not None
        self.assertEqual(payload["status"], "BLOCKED")

    def test_run_status_result_list(self) -> None:
        task = write_task(
            self.root,
            task_data(metadata={"fake_scenario": "success"}),
        )
        code, payload, stdout, stderr = run_cli(
            ["run", "--config", str(self.config), "--task", str(task)]
        )
        self.assertEqual(code, 0, stderr)
        assert payload is not None
        self.assertEqual(len(stdout.strip().splitlines()), 1)
        run_id = payload["run_id"]

        code, status_payload, _, stderr = run_cli(
            ["status", "--config", str(self.config), "--run-id", run_id]
        )
        self.assertEqual(code, 0, stderr)
        assert status_payload is not None
        self.assertEqual(status_payload["run_status"], "COMPLETED")

        code, result_payload, _, stderr = run_cli(
            ["result", "--config", str(self.config), "--run-id", run_id]
        )
        self.assertEqual(code, 0, stderr)
        assert result_payload is not None
        self.assertEqual(result_payload["run_id"], run_id)

        code, list_payload, _, stderr = run_cli(
            ["list", "--config", str(self.config)]
        )
        self.assertEqual(code, 0, stderr)
        assert list_payload is not None
        self.assertEqual(len(list_payload["runs"]), 1)
        self.assertNotIn("summary", list_payload["runs"][0])
        self.assertNotIn("stdout", json.dumps(list_payload["runs"]))

    def test_invalid_task_path_exit_two(self) -> None:
        task = write_task(
            self.root,
            task_data(allowed_paths=["../outside.py"]),
        )
        code, payload, _, stderr = run_cli(
            ["run", "--config", str(self.config), "--task", str(task)]
        )
        self.assertEqual(code, 2, stderr)
        assert payload is not None
        self.assertEqual(payload["status"], "FAILED")
        self.assertEqual(payload["error"]["code"], "invalid_task")

    def test_unknown_profile_exit_two(self) -> None:
        task = write_task(self.root, task_data(profile="missing"))
        code, payload, _, stderr = run_cli(
            ["run", "--config", str(self.config), "--task", str(task)]
        )
        self.assertEqual(code, 2, stderr)
        assert payload is not None
        self.assertEqual(payload["status"], "FAILED")

    def test_unknown_workspace_exit_two(self) -> None:
        task = write_task(self.root, task_data(workspace_id="missing"))
        code, payload, _, stderr = run_cli(
            ["run", "--config", str(self.config), "--task", str(task)]
        )
        self.assertEqual(code, 2, stderr)
        assert payload is not None
        self.assertEqual(payload["status"], "FAILED")

    def test_missing_result_exit_five(self) -> None:
        code, payload, _, stderr = run_cli(
            [
                "result",
                "--config",
                str(self.config),
                "--run-id",
                "0" * 32,
            ]
        )
        self.assertEqual(code, 5, stderr)
        assert payload is not None
        self.assertEqual(payload["status"], "BLOCKED")
        self.assertEqual(payload["error"]["code"], "not_found")

    def test_invalid_config_exit_two(self) -> None:
        bad = self.root / "bad-config.json"
        bad.write_text("{not json", encoding="utf-8")
        code, payload, _, stderr = run_cli(
            ["health", "--config", str(bad)]
        )
        self.assertEqual(code, 2, stderr)
        assert payload is not None
        self.assertEqual(payload["status"], "FAILED")
        self.assertEqual(payload["error"]["code"], "invalid_config")


if __name__ == "__main__":
    unittest.main()
