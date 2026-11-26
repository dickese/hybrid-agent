"""Atomic run, result, workflow, and checkpoint persistence."""

from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .contracts import Task
from .errors import NotFoundError, PolicyError, TaskError
from .lock import StateLock
from .proc import process_alive

_RUN_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_CHECKPOINT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_run_id() -> str:
    return uuid.uuid4().hex


def _validate_run_id(run_id: str) -> str:
    if not isinstance(run_id, str) or not _RUN_ID_RE.fullmatch(run_id):
        raise TaskError("run_id is invalid", run_id=run_id)
    return run_id


def run_directory(runtime_root: str | Path, run_id: str) -> Path:
    return Path(runtime_root) / "runs" / _validate_run_id(run_id)


def atomic_write_json(path: str | Path, data: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=target.parent, prefix=f".{target.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def atomic_write_text(path: str | Path, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=target.parent, prefix=f".{target.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def create_run(
    runtime_root: str | Path,
    *,
    run_id: str,
    task: Task,
    config_snapshot: dict[str, Any],
    prompt: str,
    baseline: dict[str, Any],
) -> Path:
    directory = run_directory(runtime_root, run_id)
    directory.mkdir(parents=True, exist_ok=False)
    atomic_write_json(directory / "task.json", task.as_dict())
    atomic_write_json(directory / "config.snapshot.json", config_snapshot)
    atomic_write_text(directory / "prompt.txt", prompt)
    atomic_write_json(directory / "baseline.json", baseline)
    state = {
        "schema_version": 1,
        "run_id": run_id,
        "task_id": task.task_id,
        "workspace_id": task.workspace_id,
        "profile": task.profile,
        "status": "PENDING",
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "pid": None,
        "process_creation_time": None,
        "session_id": None,
        "error": None,
        "quarantine": False,
        "result_path": "result.json",
        "task_path": "task.json",
        "prompt_path": "prompt.txt",
        "stdout_path": "stdout.ndjson",
        "stderr_path": "stderr.log",
        "diff_path": "diff.patch",
    }
    atomic_write_json(directory / "state.json", state)
    return directory


def update_state(runtime_root: str | Path, run_id: str, **fields: Any) -> dict[str, Any]:
    directory = run_directory(runtime_root, run_id)
    path = directory / "state.json"
    state = read_json(path)
    state.update(fields)
    state["updated_at"] = utc_now()
    atomic_write_json(path, state)
    return state


def read_state(runtime_root: str | Path, run_id: str) -> dict[str, Any]:
    path = run_directory(runtime_root, run_id) / "state.json"
    if not path.is_file():
        raise NotFoundError("Run state was not found", run_id=run_id)
    return read_json(path)


def write_result(
    runtime_root: str | Path, run_id: str, result: dict[str, Any]
) -> None:
    directory = run_directory(runtime_root, run_id)
    atomic_write_json(directory / "result.json", result)


def read_result(runtime_root: str | Path, run_id: str) -> dict[str, Any]:
    path = run_directory(runtime_root, run_id) / "result.json"
    if not path.is_file():
        raise NotFoundError("Run result was not found", run_id=run_id)
    return read_json(path)


def public_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": state.get("run_id"),
        "task_id": state.get("task_id"),
        "workspace_id": state.get("workspace_id"),
        "profile": state.get("profile"),
        "status": state.get("status"),
        "created_at": state.get("created_at"),
        "updated_at": state.get("updated_at"),
        "session_id": state.get("session_id"),
        "pid": state.get("pid"),
        "quarantine": state.get("quarantine", False),
        "error": state.get("error"),
        "result_path": state.get("result_path"),
    }


def list_runs(
    runtime_root: str | Path, *, limit: int = 50
) -> list[dict[str, Any]]:
    root = Path(runtime_root) / "runs"
    if not root.is_dir():
        return []
    runs: list[dict[str, Any]] = []
    for directory in root.iterdir():
        if not directory.is_dir() or not _RUN_ID_RE.fullmatch(directory.name):
            continue
        state_path = directory / "state.json"
        if not state_path.is_file():
            continue
        try:
            state = read_json(state_path)
        except (OSError, ValueError):
            continue
        runs.append(public_state(state))
    runs.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return runs[: max(1, min(int(limit), 500))]


def find_runs_for_task(
    runtime_root: str | Path, task_id: str
) -> list[dict[str, Any]]:
    return [run for run in list_runs(runtime_root, limit=500) if run.get("task_id") == task_id]


def workflow_path(runtime_root: str | Path) -> Path:
    return Path(runtime_root) / "workflow.json"


def load_workflow(runtime_root: str | Path) -> dict[str, Any]:
    path = workflow_path(runtime_root)
    if not path.is_file():
        return {
            "schema_version": 1,
            "updated_at": utc_now(),
            "tasks": {},
        }
    try:
        data = read_json(path)
    except (OSError, ValueError) as exc:
        raise PolicyError("workflow.json is not readable", error=str(exc)) from exc
    if not isinstance(data, dict):
        raise PolicyError("workflow.json must be an object")
    data.setdefault("schema_version", 1)
    data.setdefault("tasks", {})
    return data


def save_workflow(runtime_root: str | Path, workflow: dict[str, Any]) -> None:
    workflow["updated_at"] = utc_now()
    atomic_write_json(workflow_path(runtime_root), workflow)


def _lineage_attempts(tasks: dict[str, Any], task_id: str | None) -> int:
    total = 0
    seen: set[str] = set()
    current = task_id
    while current is not None:
        if current in seen:
            raise PolicyError("workflow task parent chain contains a cycle")
        seen.add(current)
        entry = tasks.get(current)
        if not isinstance(entry, dict):
            raise PolicyError(
                "parent task is not present in workflow state", parent_task_id=current
            )
        total += int(entry.get("attempts", 0) or 0)
        parent = entry.get("parent_task_id")
        current = parent if isinstance(parent, str) else None
    return total


def record_run_start(
    runtime_root: str | Path,
    *,
    task: Task,
    run_id: str,
    baseline: dict[str, Any],
    max_runs_per_task: int,
) -> None:
    with StateLock(runtime_root, metadata={"operation": "record_run_start", "run_id": run_id}):
        workflow = load_workflow(runtime_root)
        tasks = workflow["tasks"]
        entry = tasks.get(task.task_id)
        if isinstance(entry, dict) and entry.get("status") == "ACCEPTED":
            raise PolicyError(
                "Task is already ACCEPTED; do not run it again", task_id=task.task_id
            )
        existing_runs = [
            run
            for run in find_runs_for_task(runtime_root, task.task_id)
            if run.get("run_id") != run_id
        ]
        active = [
            run
            for run in existing_runs
            if run.get("status") in {"PENDING", "RUNNING"}
        ]
        if active:
            raise PolicyError(
                "Task already has an active run",
                task_id=task.task_id,
                run_id=active[0].get("run_id"),
            )
        if task.parent_task_id is None:
            if existing_runs:
                raise PolicyError(
                    "Task id already has a recorded run; use a new task_id for a correction",
                    task_id=task.task_id,
                    run_id=existing_runs[0].get("run_id"),
                )
            lineage_attempts = 0
        else:
            lineage_attempts = _lineage_attempts(tasks, task.parent_task_id)
        if lineage_attempts + 1 > max_runs_per_task:
            raise PolicyError(
                "Task lineage exhausted its run budget",
                task_id=task.task_id,
                attempts=lineage_attempts,
                max_runs_per_task=max_runs_per_task,
            )
        if not isinstance(entry, dict):
            entry = {
                "task_id": task.task_id,
                "status": "PENDING",
                "run_ids": [],
                "attempts": 0,
                "correction_rounds": 0,
            }
            tasks[task.task_id] = entry
        entry["parent_task_id"] = task.parent_task_id
        entry["workspace_id"] = task.workspace_id
        entry["profile"] = task.profile
        entry["attempts"] = int(entry.get("attempts", 0) or 0) + 1
        entry["run_ids"] = list(entry.get("run_ids") or []) + [run_id]
        entry["baseline_head"] = baseline.get("head")
        if task.checkpoint_id:
            entry["checkpoint_id"] = task.checkpoint_id
        entry["last_run_id"] = run_id
        entry["last_run_status"] = "RUNNING"
        entry["next_action"] = "Wait for the synchronous worker result"
        entry["updated_at"] = utc_now()
        save_workflow(runtime_root, workflow)


def record_run_finish(
    runtime_root: str | Path,
    *,
    task: Task,
    run_id: str,
    status: str,
    session_id: str | None,
    next_action: str,
) -> None:
    with StateLock(runtime_root, metadata={"operation": "record_run_finish", "run_id": run_id}):
        workflow = load_workflow(runtime_root)
        tasks = workflow["tasks"]
        entry = tasks.get(task.task_id)
        if not isinstance(entry, dict):
            entry = {
                "task_id": task.task_id,
                "status": "PENDING",
                "run_ids": [],
                "attempts": 0,
                "correction_rounds": 0,
            }
            tasks[task.task_id] = entry
        entry["parent_task_id"] = task.parent_task_id
        run_ids = list(entry.get("run_ids") or [])
        if run_id not in run_ids:
            run_ids.append(run_id)
        entry["run_ids"] = run_ids
        entry["last_run_id"] = run_id
        entry["last_run_status"] = status
        entry["session_id"] = session_id
        entry["next_action"] = next_action
        entry["updated_at"] = utc_now()
        save_workflow(runtime_root, workflow)


def checkpoint_path(runtime_root: str | Path, checkpoint_id: str) -> Path:
    if not isinstance(checkpoint_id, str) or not _CHECKPOINT_RE.fullmatch(checkpoint_id):
        raise TaskError("checkpoint_id is invalid", checkpoint_id=checkpoint_id)
    return Path(runtime_root) / "checkpoints" / f"{checkpoint_id}.json"


def new_checkpoint_id(task_id: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"ckpt-{task_id}-{stamp}"


def write_checkpoint(
    runtime_root: str | Path,
    *,
    checkpoint_id: str,
    task: Task,
    fingerprint: dict[str, Any],
) -> Path:
    path = checkpoint_path(runtime_root, checkpoint_id)
    if path.exists():
        raise PolicyError(
            "checkpoint_id already exists; choose a new id",
            checkpoint_id=checkpoint_id,
        )
    payload = {
        "schema_version": 1,
        "checkpoint_id": checkpoint_id,
        "task_id": task.task_id,
        "workspace_id": task.workspace_id,
        "profile": task.profile,
        "created_at": utc_now(),
        "branch": fingerprint.get("branch"),
        "head": fingerprint.get("head"),
        "fingerprint": fingerprint,
    }
    atomic_write_json(path, payload)
    with StateLock(
        runtime_root,
        metadata={"operation": "checkpoint", "checkpoint_id": checkpoint_id},
    ):
        workflow = load_workflow(runtime_root)
        tasks = workflow["tasks"]
        entry = tasks.get(task.task_id)
        if not isinstance(entry, dict):
            entry = {
                "task_id": task.task_id,
                "status": "PENDING",
                "run_ids": [],
                "attempts": 0,
                "correction_rounds": 0,
            }
            tasks[task.task_id] = entry
        entry["parent_task_id"] = task.parent_task_id
        entry["workspace_id"] = task.workspace_id
        entry["profile"] = task.profile
        entry["checkpoint_id"] = checkpoint_id
        entry["baseline_head"] = fingerprint.get("head")
        entry["updated_at"] = utc_now()
        save_workflow(runtime_root, workflow)
    return path


def load_checkpoint(runtime_root: str | Path, checkpoint_id: str) -> dict[str, Any]:
    path = checkpoint_path(runtime_root, checkpoint_id)
    if not path.is_file():
        raise NotFoundError("Checkpoint was not found", checkpoint_id=checkpoint_id)
    data = read_json(path)
    if not isinstance(data, dict) or not isinstance(data.get("fingerprint"), dict):
        raise PolicyError("Checkpoint file is malformed", checkpoint_id=checkpoint_id)
    return data


def recover_runs(runtime_root: str | Path, *, apply: bool) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for run in list_runs(runtime_root, limit=500):
        if run.get("status") not in {"PENDING", "RUNNING"}:
            continue
        run_id = run["run_id"]
        state = read_state(runtime_root, run_id)
        pid = state.get("pid")
        creation_time = state.get("process_creation_time")
        if run.get("status") == "PENDING":
            alive: bool | None = False
            reason = "Run never reached a started worker"
        elif isinstance(pid, int):
            alive = process_alive(pid, creation_time if isinstance(creation_time, int) else None)
            reason = "Recorded worker process state was queried"
        else:
            alive = False
            reason = "Run has no recorded worker PID"
        if alive is True or alive is None:
            actions.append(
                {
                    "run_id": run_id,
                    "task_id": run.get("task_id"),
                    "action": "QUARANTINE",
                    "worker_alive": alive,
                    "reason": "Worker may still be running; manual inspection required",
                }
            )
            if apply:
                update_state(
                    runtime_root,
                    run_id,
                    quarantine=True,
                    error={
                        "code": "cancellation_unverified",
                        "category": "recovery",
                        "message": "Worker state could not be proven stopped",
                        "retryable": False,
                    },
                )
            continue
        actions.append(
            {
                "run_id": run_id,
                "task_id": run.get("task_id"),
                "action": "MARK_INTERRUPTED" if apply else "WOULD_MARK_INTERRUPTED",
                "worker_alive": False,
                "reason": reason,
            }
        )
        if not apply:
            continue
        error = {
            "code": "interrupted_run",
            "category": "recovery",
            "message": "Bridge process ended before a terminal result was persisted",
            "retryable": False,
        }
        update_state(
            runtime_root,
            run_id,
            status="INTERRUPTED",
            error=error,
            quarantine=False,
            recovered_at=utc_now(),
        )
        result_path = Path(runtime_root) / "runs" / run_id / "result.json"
        if not result_path.is_file():
            write_result(
                runtime_root,
                run_id,
                {
                    "schema_version": 1,
                    "run_id": run_id,
                    "task_id": run.get("task_id"),
                    "status": "INTERRUPTED",
                    "runtime": "bridge-recovery",
                    "requested_model": None,
                    "actual_upstream_model": None,
                    "session_id": state.get("session_id"),
                    "exit_code": None,
                    "duration_ms": None,
                    "changed_files": [],
                    "scope_ok": None,
                    "summary": "Recovered interrupted run; inspect the working tree before retrying.",
                    "evidence": {
                        "stdout": "stdout.ndjson",
                        "stderr": "stderr.log",
                        "diff": "diff.patch",
                    },
                    "error": error,
                    "recovered_at": utc_now(),
                },
            )
        task_id = run.get("task_id")
        if isinstance(task_id, str):
            workflow = load_workflow(runtime_root)
            entry = workflow["tasks"].get(task_id)
            if isinstance(entry, dict):
                entry["last_run_status"] = "INTERRUPTED"
                entry["next_action"] = "Inspect evidence and create an explicit correction task"
                entry["updated_at"] = utc_now()
                save_workflow(runtime_root, workflow)
    return actions
