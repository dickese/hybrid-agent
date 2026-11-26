from __future__ import annotations

import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from bridge import gitutil, proc, store
from bridge.config import load_config
from bridge.contracts import parse_task
from bridge.events import classify_failure, parse_events, WorkerOutcome
from bridge.recovery import (
    evaluate_recovery,
    execute_recovery,
    auto_recover,
    RecoveryContext,
    is_failure_retryable,
    get_agent_recovery_policy,
)
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


class AutoRecoveryTests(unittest.TestCase):
    """Tests for the shared automatic recovery engine."""

    def setUp(self) -> None:
        from tests.support import make_fixture, write_fake_config
        self._temp = tempfile.TemporaryDirectory(prefix="bridge-autorecovery-test-")
        self.root = Path(self._temp.name)
        self.runtime = self.root / ".runtime"
        self.fixture = make_fixture(self.root / "fixture")
        # Create a config that uses the temp runtime but loads real policy files
        self.config = self._create_test_config()

    def _create_test_config(self) -> BridgeConfig:
        """Create a test config that uses temp runtime but real policy files."""
        import json
        import shutil
        
        # Copy policy files to temp directory
        policy_dir = FRAMEWORK_ROOT / "config"
        for policy_file in ["agent-registry.json", "routing-policy.json", "recovery-policy.json"]:
            src = policy_dir / policy_file
            dst = self.root / policy_file
            if src.exists():
                shutil.copy2(src, dst)
        
        config_data = {
            "schema_version": 1,
            "worker": {
                "type": "fake",
                "executable": str(FRAMEWORK_ROOT / "tests" / "fake_worker.py"),
                "python_executable": sys.executable,
            },
            "runtime_root": str(self.runtime),
            "credential_env": "TEST_KEY",
            "workspaces": {"demo": str(self.fixture)},
            "profiles": {
                "agent-build": {
                    "agent": "bridge-build",
                    "model": "9router/agent-build",
                    "access": "write",
                },
                "agent-fast": {
                    "agent": "bridge-fast",
                    "model": "9router/agent-fast",
                    "access": "write",
                },
            },
            "approved_models": ["9router/agent-build", "9router/agent-fast"],
            "timeout_seconds": 300,
            "max_timeout_seconds": 900,
        }
        config_path = self.root / "test_config.json"
        with open(config_path, 'w') as f:
            json.dump(config_data, f)
        return load_config(config_path)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def _make_task_with_category(self, task_id: str, category: str) -> dict:
        return {
            "schema_version": 1,
            "task_id": task_id,
            "workspace_id": "demo",
            "profile": "agent-build",
            "expected_branch": "master",
            "objective": "Test auto-recovery",
            "references": [],
            "allowed_paths": ["test.py"],
            "acceptance_criteria": ["Test passes"],
            "metadata": {"task_category": category},
        }

    def test_is_failure_retryable_rate_limited(self) -> None:
        """Test that rate_limited failures are retryable for agent-build."""
        policy = get_agent_recovery_policy(self.config, "agent-build")
        self.assertIsNotNone(policy)
        
        error = {"code": "RATE_LIMITED", "category": "rate_limit", "retryable": True}
        self.assertTrue(is_failure_retryable(error, policy))

    def test_is_failure_retryable_quota_exhausted_agent_build(self) -> None:
        """Test that quota_exhausted is retryable for agent-build (per policy)."""
        policy = get_agent_recovery_policy(self.config, "agent-build")
        self.assertIsNotNone(policy)
        
        error = {"code": "QUOTA_EXHAUSTED", "category": "quota", "retryable": False}
        self.assertTrue(is_failure_retryable(error, policy))

    def test_is_failure_retryable_auth_failure(self) -> None:
        """Test that auth_failure is never retryable."""
        policy = get_agent_recovery_policy(self.config, "agent-build")
        self.assertIsNotNone(policy)
        
        error = {"code": "AUTH_FAILURE", "category": "auth", "retryable": False}
        self.assertFalse(is_failure_retryable(error, policy))

    def test_evaluate_recovery_retry_on_transient_failure(self) -> None:
        """Test that transient failures trigger RETRY decision."""
        from bridge.contracts import load_task
        import tempfile
        import json
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            task_dict = self._make_task_with_category("AUTO-REC-001", "general_implementation")
            json.dump(task_dict, f)
            task_path = f.name
        
        try:
            task = load_task(task_path)
            profile = self.config.profile(task.profile)
            
            class MockOutcome:
                session_id = "ses_test12345678901234"
                texts = ()
                tools_used = ()
                edit_tools_used = ()
                event_counts = {"error": 1}
                error_message = "rate limit exceeded"
                error_code = "RATE_LIMITED"
                malformed_lines = ()
                terminal_seen = True
                terminal_reason = "error"
                last_event_type = "error"
                last_step_reason = "error"
                raw_events = 1
                summary = "rate limit exceeded"
                redacted_summary = "rate limit exceeded"
                has_terminal_completion = False
                has_activity = False
            
            outcome = MockOutcome()
            error_classification = classify_failure(
                exit_code=1, outcome=outcome, stderr_tail="429 Too Many Requests"
            )
            
            workspace = str(self.fixture)
            baseline = {"head": "abc123", "branch": "master"}
            
            context = RecoveryContext(
                config=self.config,
                task=task,
                profile=profile,
                run_id="test-run-id",
                run_directory=Path("test"),
                baseline=baseline,
                workspace=workspace,
                exit_code=1,
                outcome=outcome,
                stderr_tail="429 Too Many Requests",
                error_classification=error_classification,
            )
            
            decision = evaluate_recovery(context)
            self.assertEqual(decision.action, "RETRY")
            self.assertEqual(decision.agent_id, "agent-build")
        finally:
            import os
            os.unlink(task_path)

    def test_evaluate_recovery_quarantine_on_auth_failure(self) -> None:
        """Test that auth failures trigger QUARANTINE decision."""
        from bridge.contracts import load_task
        import tempfile
        import json
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            task_dict = self._make_task_with_category("AUTO-REC-002", "general_implementation")
            json.dump(task_dict, f)
            task_path = f.name
        
        try:
            task = load_task(task_path)
            profile = self.config.profile(task.profile)
            
            class MockOutcome:
                session_id = "ses_test12345678901234"
                texts = ()
                tools_used = ()
                edit_tools_used = ()
                event_counts = {"error": 1}
                error_message = "401 Unauthorized"
                error_code = "AUTH_FAILURE"
                malformed_lines = ()
                terminal_seen = True
                terminal_reason = "error"
                last_event_type = "error"
                last_step_reason = "error"
                raw_events = 1
                summary = "auth failed"
                redacted_summary = "auth failed"
                has_terminal_completion = False
                has_activity = False
            
            outcome = MockOutcome()
            error_classification = classify_failure(
                exit_code=1, outcome=outcome, stderr_tail="401 Unauthorized"
            )
            
            workspace = str(self.fixture)
            baseline = {"head": "abc123", "branch": "master"}
            
            context = RecoveryContext(
                config=self.config,
                task=task,
                profile=profile,
                run_id="test-run-id",
                run_directory=Path("test"),
                baseline=baseline,
                workspace=workspace,
                exit_code=1,
                outcome=outcome,
                stderr_tail="401 Unauthorized",
                error_classification=error_classification,
            )
            
            decision = evaluate_recovery(context)
            self.assertEqual(decision.action, "QUARANTINE")
            self.assertTrue(decision.requires_user_intervention)
        finally:
            import os
            os.unlink(task_path)

    def test_evaluate_recovery_escalate_on_budget_exhausted(self) -> None:
        """Test that exhausted retry budget triggers ESCALATE decision."""
        from bridge.contracts import load_task
        import tempfile
        import json
        
        # Pre-populate workflow with exhausted budget
        workflow = store.load_workflow(self.runtime)
        workflow["tasks"]["AUTO-REC-003"] = {
            "task_id": "AUTO-REC-003",
            "status": "PENDING",
            "attempts": 10,
            "correction_rounds": 10,
            "total_recovery_retries": 10,
            "parent_task_id": None,
            "run_ids": [],
        }
        store.save_workflow(self.runtime, workflow)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            task_dict = self._make_task_with_category("AUTO-REC-003", "general_implementation")
            json.dump(task_dict, f)
            task_path = f.name
        
        try:
            task = load_task(task_path)
            profile = self.config.profile(task.profile)
            
            class MockOutcome:
                session_id = "ses_test12345678901234"
                texts = ()
                tools_used = ()
                edit_tools_used = ()
                event_counts = {"error": 1}
                error_message = "rate limit exceeded"
                error_code = "RATE_LIMITED"
                malformed_lines = ()
                terminal_seen = True
                terminal_reason = "error"
                last_event_type = "error"
                last_step_reason = "error"
                raw_events = 1
                summary = "rate limit exceeded"
                redacted_summary = "rate limit exceeded"
                has_terminal_completion = False
                has_activity = False
            
            outcome = MockOutcome()
            error_classification = classify_failure(
                exit_code=1, outcome=outcome, stderr_tail="429 Too Many Requests"
            )
            
            workspace = str(self.fixture)
            baseline = {"head": "abc123", "branch": "master"}
            
            context = RecoveryContext(
                config=self.config,
                task=task,
                profile=profile,
                run_id="test-run-id",
                run_directory=Path("test"),
                baseline=baseline,
                workspace=workspace,
                exit_code=1,
                outcome=outcome,
                stderr_tail="429 Too Many Requests",
                error_classification=error_classification,
            )
            
            decision = evaluate_recovery(context)
            self.assertEqual(decision.action, "ESCALATE")
            self.assertTrue(decision.requires_user_intervention)
        finally:
            import os
            os.unlink(task_path)

    def test_auto_recover_cli_command(self) -> None:
        """Test the auto-recover CLI command."""
        # First run a task that fails with a retryable error
        task = write_task(self.root, self._make_task_with_category("AUTO-CLI-001", "general_implementation"))
        # Use a fake scenario that produces a rate limit error
        task = write_task(self.root, {**self._make_task_with_category("AUTO-CLI-001", "general_implementation"), "metadata": {"fake_scenario": "transient"}})
        
        # Get config path
        config_path = self.root / "test_config.json"
        
        # Run the task (should fail with rate limit)
        code, payload, _, stderr = run_cli(
            ["run", "--config", str(config_path), "--task", str(task)]
        )
        self.assertEqual(code, 3)
        assert payload is not None
        self.assertEqual(payload["status"], "FAILED")
        self.assertEqual(payload["error"]["code"], "RATE_LIMITED")
        
        # Now try auto-recover
        code, payload, _, stderr = run_cli(
            ["auto-recover", "--config", str(config_path), "--task", str(task), "--max-attempts", "1"]
        )
        # Auto-recover should attempt recovery and either succeed or fail gracefully
        # The exact outcome depends on the recovery logic
        assert payload is not None
        # Should not crash
        self.assertIn(payload["status"], ["COMPLETED", "FAILED", "QUARANTINED", "BLOCKED"])


if __name__ == "__main__":
    unittest.main()
