"""Shared helpers for bridge tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

FRAMEWORK_ROOT = Path(__file__).resolve().parents[1]
FAKE_WORKER = FRAMEWORK_ROOT / "tests" / "fake_worker.py"


def run_git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        check=True,
    )


def make_fixture(path: Path, *, dirty: bool = False) -> Path:
    path.mkdir(parents=True, exist_ok=False)
    subprocess.run(
        ["git", "init", "-b", "master"],
        cwd=path,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    run_git(path, "config", "user.name", "Fixture")
    run_git(path, "config", "user.email", "fixture@example.invalid")
    (path / "add.py").write_text("def add(a, b): return a - b\n", encoding="utf-8")
    (path / "test_add.py").write_text(
        "from add import add; assert add(2, 3) == 5\n", encoding="utf-8"
    )
    run_git(path, "add", "add.py", "test_add.py")
    run_git(path, "commit", "-m", "fixture baseline")
    if dirty:
        (path / "add.py").write_text(
            "def add(a, b): return a - b\n# user edit\n", encoding="utf-8"
        )
    return path


def task_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "schema_version": 1,
        "task_id": "TEST-001",
        "workspace_id": "demo",
        "profile": "coder",
        "expected_branch": "master",
        "objective": "Fix add.py so the fixture test passes.",
        "references": ["add.py", "test_add.py"],
        "allowed_paths": ["add.py"],
        "acceptance_criteria": ["python -B test_add.py exits 0", "test_add.py unchanged"],
        "timeout_seconds": 30,
    }
    data.update(overrides)
    return data


def write_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def write_fake_config(
    root: Path,
    fixture: Path,
    *,
    runtime_root: Path | None = None,
    timeout_seconds: int = 30,
    max_timeout_seconds: int = 60,
    lock_timeout_seconds: int = 1,
    max_runs_per_task: int = 4,
    approved_models: list[str] | None = None,
) -> Path:
    config = {
        "schema_version": 1,
        "runtime_root": str(runtime_root or (root / ".runtime")),
        "workspaces": {"demo": str(fixture)},
        "profiles": {
            "explorer": {
                "agent": "bridge-explorer",
                "model": "test/model",
                "access": "read",
            },
            "coder": {
                "agent": "bridge-coder",
                "model": "test/model",
                "access": "write",
            },
        },
        "approved_models": approved_models or ["test/model"],
        "worker": {
            "type": "fake",
            "executable": str(FAKE_WORKER),
            "python_executable": sys.executable,
        },
        "timeout_seconds": timeout_seconds,
        "max_timeout_seconds": max_timeout_seconds,
        "max_summary_chars": 2000,
        "max_prompt_chars": 12000,
        "lock_timeout_seconds": lock_timeout_seconds,
        "max_runs_per_task": max_runs_per_task,
    }
    return write_json(root / "bridge.fake.json", config)


def write_task(root: Path, data: dict[str, Any], name: str = "task.json") -> Path:
    return write_json(root / name, data)


def run_cli(
    args: list[str], *, cwd: Path = FRAMEWORK_ROOT
) -> tuple[int, dict[str, Any] | None, str, str]:
    completed = subprocess.run(
        [sys.executable, "-m", "bridge.cli", *args],
        cwd=str(cwd),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        timeout=120,
    )
    payload: dict[str, Any] | None = None
    if completed.stdout.strip():
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError:
            payload = None
    return completed.returncode, payload, completed.stdout, completed.stderr


class BridgeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory(prefix="bridge-test-")
        self.root = Path(self._temp.name)
        self.runtime = self.root / ".runtime"
        self.fixture = make_fixture(self.root / "fixture")
        self.config = write_fake_config(self.root, self.fixture, runtime_root=self.runtime)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def run_task(self, data: dict[str, Any] | None = None) -> tuple[int, dict[str, Any] | None, str, str]:
        task = write_task(self.root, data or task_data())
        return run_cli(
            ["run", "--config", str(self.config), "--task", str(task)]
        )
