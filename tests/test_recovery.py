from __future__ import annotations

import subprocess
import sys
import time
import unittest
from pathlib import Path

from bridge import gitutil, proc, store
from bridge.contracts import parse_task
from tests.support import (
    FRAMEWORK_ROOT,
    BridgeTestCase,
    run_cli,
    run_git,
    task_data,
    write_task,
)


class RecoveryTests(BridgeTestCase):
    def checkpoint(self, task: dict) -> dict:
        path = write_task(self.root, task, name=f"{task['task_id']}.json")
        code, payload, _, stderr = run_cli(
            ["checkpoint", "--config", str(self.config), "--task", str(path)]
        )
        self.assertEqual(code, 0, stderr)
        assert payload is not None
        return payload

    def test_checkpoint_allows_approved_dirty_correction(self) -> None:
        (self.fixture / "add.py").write_text(
            "def add(a, b): return a - b\n# approved user edit\n",
            encoding="utf-8",
        )
        parent = task_data(task_id="CKPT-001")
        checkpoint = self.checkpoint(parent)
        self.assertTrue(checkpoint["dirty"])
        correction = task_data(
            task_id="CKPT-001-C1",
            parent_task_id="CKPT-001",
            checkpoint_id=checkpoint["checkpoint_id"],
            metadata={"fake_scenario": "success"},
        )
        code, payload, _, stderr = self.run_task(correction)
        self.assertEqual(code, 0, stderr)
        assert payload is not None
        self.assertEqual(payload["status"], "COMPLETED")
        self.assertEqual(payload["baseline"]["checkpoint_id"], checkpoint["checkpoint_id"])
        self.assertIn("a + b", (self.fixture / "add.py").read_text(encoding="utf-8"))

    def test_checkpoint_mismatch_preserves_user_edit(self) -> None:
        (self.fixture / "add.py").write_text(
            "def add(a, b): return a - b\n# approved\n", encoding="utf-8"
        )
        parent = task_data(task_id="CKPT-002")
        checkpoint = self.checkpoint(parent)
        (self.fixture / "test_add.py").write_text(
            "from add import add; assert add(2, 3) == 5\n# unapproved\n",
            encoding="utf-8",
        )
        correction = task_data(
            task_id="CKPT-002-C1",
            parent_task_id="CKPT-002",
            checkpoint_id=checkpoint["checkpoint_id"],
            metadata={"fake_scenario": "success"},
        )
        code, payload, _, stderr = self.run_task(correction)
        self.assertEqual(code, 5, stderr)
        assert payload is not None
        self.assertEqual(payload["status"], "BLOCKED")
        self.assertIn("checkpoint", payload["error"]["message"].lower())
        self.assertIn(
            "# unapproved",
            (self.fixture / "test_add.py").read_text(encoding="utf-8"),
        )

    def test_exact_session_resume_mapping(self) -> None:
        first = task_data(
            task_id="SES-001", metadata={"fake_scenario": "success"}
        )
        code, payload, _, stderr = self.run_task(first)
        self.assertEqual(code, 0, stderr)
        assert payload is not None
        session_id = payload["session_id"]
        checkpoint = self.checkpoint(task_data(task_id="SES-001"))
        correction = task_data(
            task_id="SES-001-C1",
            parent_task_id="SES-001",
            checkpoint_id=checkpoint["checkpoint_id"],
            resume_session_id=session_id,
            metadata={"fake_scenario": "success"},
        )
        code, payload, _, stderr = self.run_task(correction)
        self.assertEqual(code, 0, stderr)
        assert payload is not None
        self.assertEqual(payload["status"], "COMPLETED")
        self.assertEqual(payload["session_id"], session_id)

    def test_resume_unknown_session_rejected(self) -> None:
        task = task_data(
            task_id="SES-002-C1",
            parent_task_id="SES-002",
            resume_session_id="ses_doesnotexist12345678",
        )
        code, payload, _, stderr = self.run_task(task)
        self.assertEqual(code, 2, stderr)
        assert payload is not None
        self.assertEqual(payload["status"], "FAILED")

    def test_recover_dry_run_then_apply(self) -> None:
        task = task_data(task_id="REC-001")
        run_id = store.new_run_id()
        baseline = gitutil.fingerprint(self.fixture)
        store.create_run(
            self.runtime,
            run_id=run_id,
            task=parse_task(task),
            config_snapshot={},
            prompt="",
            baseline=baseline,
        )
        store.update_state(
            self.runtime,
            run_id,
            status="RUNNING",
            pid=999999,
            process_creation_time=None,
        )
        code, payload, _, stderr = run_cli(
            ["recover", "--config", str(self.config)]
        )
        self.assertEqual(code, 0, stderr)
        assert payload is not None
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["actions"][0]["action"], "WOULD_MARK_INTERRUPTED")
        self.assertEqual(store.read_state(self.runtime, run_id)["status"], "RUNNING")
        code, payload, _, stderr = run_cli(
            ["recover", "--config", str(self.config), "--apply"]
        )
        self.assertEqual(code, 0, stderr)
        assert payload is not None
        self.assertEqual(payload["actions"][0]["action"], "MARK_INTERRUPTED")
        state = store.read_state(self.runtime, run_id)
        self.assertEqual(state["status"], "INTERRUPTED")
        result = store.read_result(self.runtime, run_id)
        self.assertEqual(result["error"]["code"], "interrupted_run")

    def test_crashed_bridge_is_recovered_and_partial_edit_preserved(self) -> None:
        task = write_task(
            self.root,
            task_data(
                task_id="CRASH-001",
                timeout_seconds=60,
                metadata={"fake_scenario": "hold_after_edit"},
            ),
            name="crash-task.json",
        )
        bridge = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "bridge.cli",
                "run",
                "--config",
                str(self.config),
                "--task",
                str(task),
            ],
            cwd=str(FRAMEWORK_ROOT),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            shell=False,
        )
        run_id: str | None = None
        deadline = time.time() + 30
        while time.time() < deadline:
            runs = store.list_runs(self.runtime)
            active = [run for run in runs if run["status"] == "RUNNING"]
            if active:
                run_id = active[0]["run_id"]
                if "+ b" in (self.fixture / "add.py").read_text(encoding="utf-8"):
                    break
            time.sleep(0.2)
        self.assertIsNotNone(run_id)
        assert run_id is not None
        state_before = store.read_state(self.runtime, run_id)
        fake_pid = state_before.get("pid")
        creation = state_before.get("process_creation_time")
        bridge.kill()
        bridge.wait(timeout=15)
        time.sleep(2)
        if isinstance(fake_pid, int):
            self.assertFalse(proc.process_alive(fake_pid, creation))
        self.assertIn("+ b", (self.fixture / "add.py").read_text(encoding="utf-8"))
        code, payload, _, stderr = run_cli(
            ["recover", "--config", str(self.config), "--apply"]
        )
        self.assertEqual(code, 0, stderr)
        assert payload is not None
        self.assertEqual(payload["actions"][0]["action"], "MARK_INTERRUPTED")
        state = store.read_state(self.runtime, run_id)
        self.assertEqual(state["status"], "INTERRUPTED")
        self.assertIn("+ b", (self.fixture / "add.py").read_text(encoding="utf-8"))

    def test_retry_budget_exhausted(self) -> None:
        workflow = store.load_workflow(self.runtime)
        workflow["tasks"]["BUDGET-PARENT"] = {
            "task_id": "BUDGET-PARENT",
            "status": "PENDING",
            "attempts": 4,
            "parent_task_id": None,
            "run_ids": [],
        }
        store.save_workflow(self.runtime, workflow)
        task = task_data(
            task_id="BUDGET-CHILD",
            parent_task_id="BUDGET-PARENT",
            metadata={"fake_scenario": "success"},
        )
        code, payload, _, stderr = self.run_task(task)
        self.assertEqual(code, 5, stderr)
        assert payload is not None
        self.assertEqual(payload["status"], "BLOCKED")
        self.assertIn("budget", payload["error"]["message"].lower())

    def test_accepted_task_rejected(self) -> None:
        workflow = store.load_workflow(self.runtime)
        workflow["tasks"]["TEST-001"] = {
            "task_id": "TEST-001",
            "status": "ACCEPTED",
            "attempts": 1,
            "parent_task_id": None,
            "run_ids": [],
        }
        store.save_workflow(self.runtime, workflow)
        code, payload, _, stderr = self.run_task(
            task_data(metadata={"fake_scenario": "success"})
        )
        self.assertEqual(code, 5, stderr)
        assert payload is not None
        self.assertEqual(payload["status"], "BLOCKED")
        self.assertIn("ACCEPTED", payload["error"]["message"])


if __name__ == "__main__":
    unittest.main()
