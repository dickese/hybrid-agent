"""Synchronous run orchestration, health checks, checkpoints, and recovery."""

from __future__ import annotations

import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import gitutil, policy, store
from .config import BridgeConfig, ensure_runtime_layout, load_config, runtime_writable
from .contracts import Task, load_task
from .errors import (
    BridgeError,
    ConfigError,
    PolicyError,
    TaskError,
    WorkerError,
)
from .events import WorkerOutcome, classify_failure, parse_events
from .lock import RepositoryLock
from .proc import ProcessResult, run_worker
from .redact import SecretRedactor

EXIT_BY_STATUS = {
    "COMPLETED": 0,
    "FAILED": 3,
    "TIMED_OUT": 4,
    "BLOCKED": 5,
    "INTERRUPTED": 5,
}


def _execute_worker_attempt(
    config: BridgeConfig,
    task: Task,
    profile: Any,
    run_id: str,
    workspace: str,
    before_branch: str,
    before_head: str,
    baseline: dict[str, Any],
    resolved_agent_id: str,
    resolved_model_route: str,
    execution_profile: str | None,
    agent_permission_policy: str | None,
    effective_context_limit: int | None,
    effective_output_limit: int | None,
    resume_session_id: str | None,
    credential: str | None,
    timeout_seconds: float,
    run_directory: Path,
) -> tuple[dict[str, Any], int]:
    """Shared single-attempt worker execution path.
    
    Enforces all guards: registry qualification, capability validation, permission validation,
    workspace allowlist, repository lock, expected Git branch/HEAD, checkpoint validation,
    run registration, process termination verification, timeout handling, scope evaluation,
    structured event parsing, persistent result and evidence.
    """
    # Build prompt
    prompt = policy.build_prompt(
        task,
        profile,
        workspace_root=workspace,
        branch=before_branch,
        head=before_head,
        max_prompt_chars=config.max_prompt_chars,
        agent_permission_policy=agent_permission_policy,
    )
    
    # Build argv
    argv = _build_argv(
        config, profile, prompt, resume_session_id,
        resolved_agent_id, resolved_model_route,
        execution_profile, effective_context_limit, effective_output_limit
    )
    
    # Store command for evidence
    store.atomic_write_json(
        run_directory / "command.json",
        {
            "worker_type": config.worker_type,
            "cwd": workspace,
            "argv_without_prompt": argv[:-1],
            "prompt_path": "prompt.txt",
        },
    )
    
    # Run worker
    redactor = SecretRedactor([credential] if credential else [])
    env = _build_worker_env(config, task, credential, run_id)
    
    def on_start(pid: int, creation_time: int | None) -> None:
        store.update_state(
            config.runtime_root,
            run_id,
            status="RUNNING",
            pid=pid,
            process_creation_time=creation_time,
            started_at=store.utc_now(),
        )
    
    try:
        process_result = run_worker(
            argv,
            cwd=workspace,
            env=env,
            stdout_path=run_directory / "stdout.ndjson",
            stderr_path=run_directory / "stderr.log",
            timeout_seconds=timeout_seconds,
            redactor=redactor,
            on_start=on_start,
        )
    except KeyboardInterrupt:
        error = {
            "code": "bridge_interrupted",
            "category": "recovery",
            "message": "Bridge run was interrupted by the operator",
            "retryable": False,
        }
        result = _base_result(
            config, task, profile, run_id,
            status="INTERRUPTED", baseline=baseline, error=error,
            session_id=None, exit_code=None, duration_ms=0,
            changed_files=[], scope_ok=None, summary=error["message"],
            worker=None, timed_out=False, quarantine=False,
            logical_agent=resolved_agent_id, model_route=resolved_model_route,
        )
        _persist_result(config, task, run_id, result)
        return result, EXIT_BY_STATUS["INTERRUPTED"]
    except WorkerError as exc:
        result = _base_result(
            config, task, profile, run_id,
            status="FAILED", baseline=baseline, error=exc.to_dict(),
            session_id=None, exit_code=None, duration_ms=0,
            changed_files=[], scope_ok=None, summary=exc.message,
            worker=None, timed_out=False, quarantine=False,
            logical_agent=resolved_agent_id, model_route=resolved_model_route,
        )
        _persist_result(config, task, run_id, result)
        return result, EXIT_BY_STATUS["FAILED"]
    
    # Finalize run (parse events, evaluate scope, classify failure, persist result)
    return _finalize_run(
        config, task, profile, run_id,
        workspace=workspace,
        before_branch=before_branch,
        before_head=before_head,
        baseline=baseline,
        process_result=process_result,
        timeout_seconds=timeout_seconds,
        redactor=redactor,
        run_directory=run_directory,
        resolved_agent_id=resolved_agent_id,
        resolved_model_route=resolved_model_route,
    )


def execute_run(config_path: str, task_path: str) -> tuple[dict[str, Any], int]:
    config = load_config(config_path)
    ensure_runtime_layout(config)
    task = load_task(task_path)
    if task.fake_scenario is not None and config.worker_type != "fake":
        raise TaskError("metadata.fake_scenario is only valid for the fake test worker")
    profile = config.profile(task.profile)

    # Resolve logical agent and model route from routing policy
    resolved_agent_id, resolved_model_route = policy.resolve_agent_for_task(task, config, profile)

    # Validate agent capabilities
    missing_capabilities = policy.validate_agent_capabilities(resolved_agent_id, config, profile)
    if missing_capabilities:
        raise PolicyError(
            "Agent capabilities not satisfied by profile",
            agent=resolved_agent_id,
            missing_capabilities=missing_capabilities,
        )

    # Validate permission policy
    if not policy.validate_permission_policy(resolved_agent_id, config, profile):
        raise PolicyError(
            "Profile access level does not satisfy agent permission policy",
            agent=resolved_agent_id,
            required=config.routing_policy.permission_requirements.get(resolved_agent_id) if config.routing_policy else "unknown",
            actual=profile.access,
        )

    # Check route health / circuit breaker
    circuit_open, cooldown_until = _check_circuit_breaker(config, resolved_agent_id)
    if circuit_open:
        raise PolicyError(
            "Route circuit breaker is open; route is temporarily unavailable",
            agent=resolved_agent_id,
            cooldown_until=cooldown_until,
        )

    if (
        task.timeout_seconds is not None
        and task.timeout_seconds > config.max_timeout_seconds
    ):
        raise TaskError(
            "task timeout exceeds config max_timeout_seconds",
            timeout_seconds=task.timeout_seconds,
            max_timeout_seconds=config.max_timeout_seconds,
        )

    workspace = gitutil.resolve_workspace(config.workspace(task.workspace_id))
    for relative in (*task.references, *task.allowed_paths):
        gitutil.ensure_within(workspace, relative, field="task path")

    before_branch = gitutil.branch(workspace)
    before_head = gitutil.head(workspace)
    _check_expected_git_state(task, before_branch, before_head)
    if task.resume_session_id is not None:
        _validate_resume(config, task, workspace)

    credential = _read_credential(config) if config.worker_type == "opencode" else None
    redactor = SecretRedactor([credential] if credential else [])
    timeout_seconds = float(task.timeout_seconds or config.timeout_seconds)
    run_id = store.new_run_id()

    with RepositoryLock(
        config.runtime_root,
        workspace,
        timeout_seconds=config.lock_timeout_seconds,
        run_id=run_id,
        task_id=task.task_id,
    ):
        before_branch = gitutil.branch(workspace)
        before_head = gitutil.head(workspace)
        _check_expected_git_state(task, before_branch, before_head)
        baseline = gitutil.fingerprint(workspace)
        checkpoint_id = task.checkpoint_id
        if checkpoint_id is not None:
            checkpoint = store.load_checkpoint(config.runtime_root, checkpoint_id)
            _validate_checkpoint(checkpoint, task, workspace)
            if not gitutil.fingerprints_match(
                checkpoint["fingerprint"], baseline
            ):
                differences = gitutil.fingerprint_differences(
                    checkpoint["fingerprint"], baseline
                )
                raise PolicyError(
                    "Working tree does not match the approved checkpoint",
                    checkpoint_id=checkpoint_id,
                    differences=differences,
                )
        elif baseline.get("status"):
            raise PolicyError(
                "Repository has a dirty baseline; commit or create an approved checkpoint",
                changed_files=[
                    entry.get("path")
                    for entry in baseline.get("status", [])
                    if isinstance(entry, dict)
                ],
            )

        # Get agent entry for permission policy, execution profile, and effective model settings
        agent_entry = config.agent_registry.get(resolved_agent_id)
        agent_permission_policy = agent_entry.permission_policy if agent_entry else None
        execution_profile = agent_entry.execution_profile if agent_entry else None
        effective_context_limit = agent_entry.effective_context_limit if agent_entry else None
        effective_output_limit = agent_entry.effective_output_limit if agent_entry else None

        run_directory = store.create_run(
            config.runtime_root,
            run_id=run_id,
            task=task,
            config_snapshot=config.sanitized(),
            prompt="",  # Will be built in _execute_worker_attempt
            baseline=baseline,
        )
        _ensure_evidence_files(run_directory)
        
        try:
            store.record_run_start(
                config.runtime_root,
                task=task,
                run_id=run_id,
                baseline=baseline,
                max_runs_per_task=config.max_runs_per_task,
            )
        except BridgeError as exc:
            result = _base_result(
                config,
                task,
                profile,
                run_id,
                status="BLOCKED",
                baseline=baseline,
                error=exc.to_dict(),
                session_id=None,
                exit_code=None,
                duration_ms=0,
                changed_files=[],
                scope_ok=None,
                summary=exc.message,
                worker=None,
                timed_out=False,
                quarantine=False,
                logical_agent=resolved_agent_id,
                model_route=resolved_model_route,
            )
            _persist_result(config, task, run_id, result, record_finish=False)
            return result, EXIT_BY_STATUS["BLOCKED"]

        # Execute worker using shared execution path (handles KeyboardInterrupt, WorkerError, and finalization internally)
        return _execute_worker_attempt(
            config=config,
            task=task,
            profile=profile,
            run_id=run_id,
            workspace=workspace,
            before_branch=before_branch,
            before_head=before_head,
            baseline=baseline,
            resolved_agent_id=resolved_agent_id,
            resolved_model_route=resolved_model_route,
            execution_profile=execution_profile,
            agent_permission_policy=agent_permission_policy,
            effective_context_limit=effective_context_limit,
            effective_output_limit=effective_output_limit,
            resume_session_id=task.resume_session_id,
            credential=credential,
            timeout_seconds=timeout_seconds,
            run_directory=run_directory,
        )


def _finalize_run(
    config: BridgeConfig,
    task: Task,
    profile: Any,
    run_id: str,
    *,
    workspace: str,
    before_branch: str,
    before_head: str,
    baseline: dict[str, Any],
    process_result: ProcessResult,
    timeout_seconds: float,
    redactor: SecretRedactor,
    run_directory: Path,
    resolved_agent_id: str,
    resolved_model_route: str,
) -> tuple[dict[str, Any], int]:
    outcome = parse_events(
        run_directory / "stdout.ndjson",
        redactor=redactor,
        max_summary_chars=config.max_summary_chars,
    )
    after_branch = gitutil.branch(workspace)
    after_head = gitutil.head(workspace)
    after_entries = gitutil.status_entries(workspace)
    gitutil.write_diff_evidence(
        workspace, run_directory / "diff.patch", redactor=redactor
    )
    diff_text = gitutil.diff_text_for_scan(workspace)
    # Get agent permission policy for write_docs_only enforcement
    agent_entry = config.agent_registry.get(resolved_agent_id)
    agent_permission_policy = agent_entry.permission_policy if agent_entry else None
    evaluation = policy.evaluate_scope(
        task,
        profile,
        workspace_root=workspace,
        before_branch=before_branch,
        before_head=before_head,
        after_branch=after_branch,
        after_head=after_head,
        entries=after_entries,
        edit_tools_used=outcome.edit_tools_used,
        diff_text=diff_text,
        agent_permission_policy=agent_permission_policy,
    )

    error: dict[str, Any] | None = None
    status = "COMPLETED"
    quarantine = False
    if process_result.timed_out:
        error = {
            "code": "worker_timeout",
            "category": "timeout",
            "message": f"Worker exceeded {int(timeout_seconds)} seconds",
            "retryable": False,
            "details": {"kill_verified": process_result.kill_verified},
        }
        status = "TIMED_OUT"
        if not process_result.kill_verified:
            error = {
                "code": "cancellation_unverified",
                "category": "timeout",
                "message": "Worker timed out and its process tree could not be proven stopped",
                "retryable": False,
                "details": {"kill_verified": False},
            }
            status = "BLOCKED"
            quarantine = True
    else:
        error = classify_failure(
            exit_code=process_result.exit_code,
            outcome=outcome,
            stderr_tail=process_result.stderr_tail,
        )
        if error is None and not evaluation.scope_ok:
            error = {
                "code": "policy_violation",
                "category": "policy",
                "message": "Worker result violated scope or Git policy",
                "retryable": False,
                "details": {"violations": evaluation.violations},
            }
        status = policy.status_for_error(error)
        if error is not None and error.get("code") == "policy_violation":
            status = "BLOCKED"

    worker = {
        "type": config.worker_type,
        "pid": process_result.pid,
        "creation_time": process_result.creation_time,
        "exit_code": process_result.exit_code,
        "kill_verified": process_result.kill_verified,
        "stdout_bytes": process_result.stdout_bytes,
        "stderr_bytes": process_result.stderr_bytes,
        "event_counts": outcome.event_counts,
        "malformed_lines": list(outcome.malformed_lines),
        "tools_used": list(outcome.tools_used),
        "edit_tools_used": list(outcome.edit_tools_used),
        "terminal_seen": outcome.terminal_seen,
        "last_event_type": outcome.last_event_type,
    }
    summary = outcome.redacted_summary
    if error is not None:
        summary = f"{error.get('message')}: {summary}"[: config.max_summary_chars]
    result = _base_result(
        config,
        task,
        profile,
        run_id,
        status=status,
        baseline=baseline,
        error=error,
        session_id=outcome.session_id,
        exit_code=process_result.exit_code,
        duration_ms=process_result.duration_ms,
        changed_files=evaluation.changed_files,
        scope_ok=evaluation.scope_ok,
        summary=summary,
        worker=worker,
        timed_out=process_result.timed_out,
        quarantine=quarantine,
        logical_agent=resolved_agent_id,
        model_route=resolved_model_route,
    )
    result["policy"] = evaluation.to_dict()
    _persist_result(config, task, run_id, result)
    return result, EXIT_BY_STATUS.get(status, 3)


def health(
    config_path: str, *, live: bool = False, profile_id: str | None = None
) -> tuple[dict[str, Any], int]:
    config = load_config(config_path)
    checks: list[dict[str, Any]] = []
    versions: dict[str, Any] = {}

    checks.append({"name": "config", "status": "PASS", "detail": config.source_path})
    writable = runtime_writable(config)
    checks.append(
        {
            "name": "runtime_writable",
            "status": "PASS" if writable else "FAIL",
            "detail": config.runtime_root,
        }
    )

    if config.worker_type == "opencode":
        checks.append(
            {
                "name": "opencode_executable",
                "status": "PASS",
                "detail": config.opencode_executable,
            }
        )
        version = _executable_version(
            [config.opencode_executable, "--version"], timeout=15
        )
        versions["opencode"] = version
        checks.append(
            {
                "name": "opencode_version",
                "status": "PASS" if version else "FAIL",
                "detail": version,
            }
        )
        checks.append(
            {
                "name": "opencode_config",
                "status": "PASS",
                "detail": config.opencode_config,
            }
        )
        checks.append(
            {
                "name": "opencode_config_dir",
                "status": "PASS",
                "detail": config.opencode_config_dir,
            }
        )
        credential_ok = _credential_available(config)
        checks.append(
            {
                "name": "credential_presence",
                "status": "PASS" if credential_ok else "FAIL",
                "detail": "file or environment variable is present"
                if credential_ok
                else "credential is missing",
            }
        )
    else:
        checks.append(
            {
                "name": "fake_worker",
                "status": "PASS",
                "detail": config.fake_worker_executable,
            }
        )
        version = _executable_version(
            [config.fake_python_executable, "--version"], timeout=15
        )
        versions["python"] = version
        checks.append(
            {
                "name": "python_version",
                "status": "PASS" if version else "FAIL",
                "detail": version,
            }
        )

    for workspace_id, path in sorted(config.workspaces.items()):
        try:
            root = gitutil.resolve_workspace(path)
            state = gitutil.repo_state(root)
            checks.append(
                {
                    "name": f"workspace:{workspace_id}",
                    "status": "WARN" if state.dirty else "PASS",
                    "detail": {
                        "path": root,
                        "branch": state.branch,
                        "head": state.head,
                        "dirty": state.dirty,
                        "changed_files": gitutil.changed_paths(state.entries),
                    },
                }
            )
        except BridgeError as exc:
            checks.append(
                {
                    "name": f"workspace:{workspace_id}",
                    "status": "FAIL",
                    "detail": exc.to_dict(),
                }
            )

    # Route health checks
    # route-health.json is in the state directory (sibling of runtime_root)
    state_root = Path(config.runtime_root).parent / "state"
    route_health_path = state_root / "route-health.json"
    route_health_status = "PASS"
    route_health_detail: dict[str, Any] = {}
    if route_health_path.is_file() and config.recovery_policy:
        try:
            import json
            health_data = json.loads(route_health_path.read_text(encoding="utf-8"))
            routes = health_data.get("routes", {})
            for agent_id, route_info in routes.items():
                agent_policy = config.recovery_policy.per_agent_policies.get(agent_id)
                if not agent_policy:
                    continue
                consecutive_failures = route_info.get("consecutive_failures", 0)
                cooldown_until = route_info.get("cooldown_until")
                threshold = agent_policy.get("circuit_breaker_threshold", 5)
                
                is_circuit_open = False
                if consecutive_failures >= threshold:
                    if cooldown_until:
                        try:
                            from datetime import datetime, timezone
                            cooldown_time = datetime.fromisoformat(cooldown_until.replace("Z", "+00:00"))
                            if datetime.now(timezone.utc) < cooldown_time:
                                is_circuit_open = True
                        except ValueError:
                            pass
                    else:
                        is_circuit_open = True
                
                route_health_detail[agent_id] = {
                    "consecutive_failures": consecutive_failures,
                    "threshold": threshold,
                    "cooldown_until": cooldown_until,
                    "circuit_open": is_circuit_open,
                    "last_failure": route_info.get("last_failure_classification"),
                    "qualification_status": route_info.get("qualification_status", "NOT_VERIFIED"),
                }
                if is_circuit_open:
                    route_health_status = "FAIL"
            checks.append(
                {
                    "name": "route_health",
                    "status": route_health_status,
                    "detail": route_health_detail,
                }
            )
        except (OSError, json.JSONDecodeError):
            checks.append(
                {
                    "name": "route_health",
                    "status": "WARN",
                    "detail": "Could not read route health file",
                }
            )

    route = {
        "requested_model": (
            config.profiles[profile_id].model
            if profile_id and profile_id in config.profiles
            else next(iter(config.profiles.values())).model
        ),
        "actual_upstream_model": None,
    }
    if profile_id is not None and profile_id not in config.profiles:
        checks.append(
            {
                "name": "profile",
                "status": "FAIL",
                "detail": f"unknown profile: {profile_id}",
            }
        )

    live_result: dict[str, Any] | None = None
    if live:
        if config.worker_type != "opencode":
            checks.append(
                {
                    "name": "live",
                    "status": "FAIL",
                    "detail": "live health requires worker.type=opencode",
                }
            )
        else:
            try:
                live_result = _live_pong(config, profile_id)
                checks.append(
                    {
                        "name": "live_pong",
                        "status": "PASS" if live_result.get("pong") else "FAIL",
                        "detail": live_result,
                    }
                )
            except BridgeError as exc:
                checks.append(
                    {
                        "name": "live_pong",
                        "status": "FAIL",
                        "detail": exc.to_dict(),
                    }
                )

    failed = [check for check in checks if check["status"] == "FAIL"]
    status = "BLOCKED" if failed else "PASS"
    payload = {
        "schema_version": 1,
        "command": "health",
        "status": status,
        "worker_type": config.worker_type,
        "checks": checks,
        "versions": versions,
        "route": route,
        "live": live_result,
        "timestamp": store.utc_now(),
    }
    return payload, 5 if failed else 0


def checkpoint(
    config_path: str, task_path: str, checkpoint_id: str | None = None
) -> tuple[dict[str, Any], int]:
    config = load_config(config_path)
    ensure_runtime_layout(config)
    task = load_task(task_path)
    profile = config.profile(task.profile)
    workspace = gitutil.resolve_workspace(config.workspace(task.workspace_id))
    for relative in (*task.references, *task.allowed_paths):
        gitutil.ensure_within(workspace, relative, field="task path")
    before_branch = gitutil.branch(workspace)
    before_head = gitutil.head(workspace)
    _check_expected_git_state(task, before_branch, before_head)
    selected_id = checkpoint_id or task.checkpoint_id or store.new_checkpoint_id(
        task.task_id
    )
    with RepositoryLock(
        config.runtime_root,
        workspace,
        timeout_seconds=config.lock_timeout_seconds,
        run_id="checkpoint",
        task_id=task.task_id,
    ):
        before_branch = gitutil.branch(workspace)
        before_head = gitutil.head(workspace)
        _check_expected_git_state(task, before_branch, before_head)
        fingerprint = gitutil.fingerprint(workspace)
        path = store.write_checkpoint(
            config.runtime_root,
            checkpoint_id=selected_id,
            task=task,
            fingerprint=fingerprint,
        )
    return (
        {
            "schema_version": 1,
            "command": "checkpoint",
            "status": "PASS",
            "checkpoint_id": selected_id,
            "task_id": task.task_id,
            "workspace_id": task.workspace_id,
            "profile": profile.profile_id,
            "branch": fingerprint.get("branch"),
            "head": fingerprint.get("head"),
            "dirty": bool(fingerprint.get("status")),
            "changed_files": [
                entry.get("path") for entry in fingerprint.get("status", [])
            ],
            "path": str(path),
            "timestamp": store.utc_now(),
        },
        0,
    )


def recover(config_path: str, *, apply: bool = False) -> tuple[dict[str, Any], int]:
    config = load_config(config_path)
    ensure_runtime_layout(config)
    actions = store.recover_runs(config.runtime_root, apply=apply)
    quarantined = [action for action in actions if action["action"] == "QUARANTINE"]
    status = "BLOCKED" if quarantined else "PASS"
    return (
        {
            "schema_version": 1,
            "command": "recover",
            "status": status,
            "dry_run": not apply,
            "actions": actions,
            "quarantined": len(quarantined),
            "timestamp": store.utc_now(),
        },
        5 if quarantined else 0,
    )


def _base_result(
    config: BridgeConfig,
    task: Task,
    profile: Any,
    run_id: str,
    *,
    status: str,
    baseline: dict[str, Any],
    error: dict[str, Any] | None,
    session_id: str | None,
    exit_code: int | None,
    duration_ms: int | None,
    changed_files: list[str],
    scope_ok: bool | None,
    summary: str,
    worker: dict[str, Any] | None,
    timed_out: bool,
    quarantine: bool,
    logical_agent: str | None = None,
    model_route: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "task_id": task.task_id,
        "workspace_id": task.workspace_id,
        "profile": task.profile,
        "status": status,
        "runtime": config.worker_type,
        "requested_model": profile.model,
        "logical_agent": logical_agent,
        "model_route": model_route,
        "actual_upstream_model": None,
        "session_id": session_id,
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "changed_files": changed_files,
        "scope_ok": scope_ok,
        "summary": summary,
        "evidence": {
            "stdout": "stdout.ndjson",
            "stderr": "stderr.log",
            "diff": "diff.patch",
            "task": "task.json",
            "prompt": "prompt.txt",
            "config": "config.snapshot.json",
            "baseline": "baseline.json",
        },
        "error": error,
        "timed_out": timed_out,
        "quarantine": quarantine,
        "worker": worker,
        "baseline": {
            "branch": baseline.get("branch"),
            "head": baseline.get("head"),
            "dirty": bool(baseline.get("status")),
            "checkpoint_id": task.checkpoint_id,
        },
        "created_at": store.utc_now(),
        "finished_at": store.utc_now(),
    }


def _persist_result(
    config: BridgeConfig,
    task: Task,
    run_id: str,
    result: dict[str, Any],
    *,
    record_finish: bool = True,
) -> None:
    store.write_result(config.runtime_root, run_id, result)
    store.update_state(
        config.runtime_root,
        run_id,
        status=result["status"],
        session_id=result.get("session_id"),
        error=result.get("error"),
        quarantine=result.get("quarantine", False),
        finished_at=result.get("finished_at"),
    )
    if record_finish:
        store.record_run_finish(
            config.runtime_root,
            task=task,
            run_id=run_id,
            status=result["status"],
            session_id=result.get("session_id"),
            next_action=policy.next_action_for_status(result["status"]),
        )


def _ensure_evidence_files(run_directory: Path) -> None:
    for name in ("stdout.ndjson", "stderr.log", "diff.patch"):
        path = run_directory / name
        if not path.exists():
            path.write_bytes(b"")


def _check_expected_git_state(
    task: Task, actual_branch: str, actual_head: str
) -> None:
    if actual_branch != task.expected_branch:
        raise PolicyError(
            "Workspace branch does not match expected_branch",
            expected=task.expected_branch,
            actual=actual_branch,
        )
    if task.expected_head is not None and actual_head.lower() != task.expected_head.lower():
        raise PolicyError(
            "Workspace HEAD does not match expected_head",
            expected=task.expected_head,
            actual=actual_head,
        )


def _validate_checkpoint(
    checkpoint: dict[str, Any], task: Task, workspace: str
) -> None:
    if checkpoint.get("workspace_id") != task.workspace_id:
        raise PolicyError(
            "Checkpoint belongs to a different workspace",
            checkpoint_id=task.checkpoint_id,
        )
    if checkpoint.get("profile") != task.profile:
        raise PolicyError(
            "Checkpoint belongs to a different profile",
            checkpoint_id=task.checkpoint_id,
        )
    if checkpoint.get("task_id") not in {task.task_id, task.parent_task_id}:
        raise PolicyError(
            "Checkpoint belongs to an unrelated task",
            checkpoint_id=task.checkpoint_id,
        )
    fingerprint = checkpoint.get("fingerprint") or {}
    root = fingerprint.get("root")
    if not isinstance(root, str) or os.path.normcase(root) != os.path.normcase(workspace):
        raise PolicyError(
            "Checkpoint fingerprint is for a different repository root",
            checkpoint_id=task.checkpoint_id,
        )


def _validate_resume(config: BridgeConfig, task: Task, workspace: str) -> None:
    matches = [
        run
        for run in store.list_runs(config.runtime_root, limit=500)
        if run.get("session_id") == task.resume_session_id
    ]
    if not matches:
        raise TaskError(
            "resume_session_id does not match any recorded run",
            session_id=task.resume_session_id,
        )
    match = matches[0]
    if match.get("task_id") != task.parent_task_id:
        raise TaskError(
            "resume_session_id belongs to a different parent task",
            session_id=task.resume_session_id,
            expected_parent=task.parent_task_id,
            actual_task=match.get("task_id"),
        )
    if match.get("workspace_id") != task.workspace_id or match.get("profile") != task.profile:
        raise TaskError(
            "resume_session_id belongs to a different workspace/profile",
            session_id=task.resume_session_id,
        )


def _read_credential(config: BridgeConfig) -> str:
    if config.credential_file:
        try:
            value = Path(config.credential_file).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ConfigError("credential_file could not be read", error=str(exc)) from exc
        if not value:
            raise ConfigError("credential_file is empty")
        return value
    value = os.environ.get(config.credential_env, "").strip()
    if not value:
        raise ConfigError(
            "credential is not available; set credential_file or the configured environment variable"
        )
    return value


def _credential_available(config: BridgeConfig) -> bool:
    if config.credential_file:
        path = Path(config.credential_file)
        try:
            return path.is_file() and path.stat().st_size > 0
        except OSError:
            return False
    return bool(os.environ.get(config.credential_env))


def _build_argv(
    config: BridgeConfig,
    profile: Any,
    prompt: str,
    resume_session_id: str | None,
    resolved_agent_id: str,
    resolved_model_route: str,
    execution_profile: str | None = None,
    effective_context_limit: int | None = None,
    effective_output_limit: int | None = None,
) -> list[str]:
    if config.worker_type == "opencode":
        # Use execution profile (e.g., "bridge-build") for --agent, not logical agent ID
        agent_for_cli = execution_profile or resolved_agent_id
        argv = [
            config.opencode_executable,
            "--standalone",
            "run",
            "--agent",
            agent_for_cli,
            "--model",
            resolved_model_route,
            "--format",
            "json",
        ]
        # OpenCode v2.2.0 does not support --max-context or --max-output flags.
        # Model limits are configured in opencode.json provider/model settings.
        if resume_session_id:
            argv.extend(["--session", resume_session_id])
        argv.append(prompt)
        return argv
    argv = [config.fake_python_executable, config.fake_worker_executable]
    if resume_session_id:
        argv.extend(["--session", resume_session_id])
    argv.append(prompt)
    return argv


def _build_worker_env(
    config: BridgeConfig,
    task: Task,
    credential: str | None,
    run_id: str,
) -> dict[str, str]:
    allow = (
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "SystemRoot",
        "WINDIR",
        "COMSPEC",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "HOME",
        "HOMEDRIVE",
        "HOMEPATH",
        "LOCALAPPDATA",
        "APPDATA",
        "PROCESSOR_ARCHITECTURE",
        "NUMBER_OF_PROCESSORS",
    )
    env = {key: os.environ[key] for key in allow if key in os.environ}
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    if config.worker_type == "opencode":
        assert credential is not None
        env[config.credential_env] = credential
        env["OPENCODE_CONFIG"] = config.opencode_config or ""
        # Set OPENCODE_CONFIG_DIR to empty string so OpenCode auto-discovers
        # agent profiles from the directory containing OPENCODE_CONFIG
        env["OPENCODE_CONFIG_DIR"] = ""
        # Do NOT disable project config - we need it to load agent profiles
        env["OPENCODE_DISABLE_PROJECT_CONFIG"] = "0"
        env["OPENCODE_DISABLE_AUTOUPDATE"] = "1"
    else:
        env["BRIDGE_FAKE_SCENARIO"] = task.fake_scenario or "success"
        env["BRIDGE_FAKE_TASK_ID"] = task.task_id
        env["BRIDGE_FAKE_RUN_ID"] = run_id
        env["BRIDGE_FAKE_SESSION"] = task.resume_session_id or "ses_fake000000000000000000000000"
    return env


def _executable_version(argv: list[str], *, timeout: int) -> str | None:
    try:
        completed = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = (completed.stdout + completed.stderr).decode("utf-8", "replace").strip()
    return text.splitlines()[0][:200] if text else None


def _live_pong(
    config: BridgeConfig, profile_id: str | None
) -> dict[str, Any]:
    profile = (
        config.profiles[profile_id]
        if profile_id is not None
        else next(iter(config.profiles.values()))
    )
    # Create a dummy task for routing resolution
    dummy_task = Task(
        task_id="HEALTH",
        workspace_id=next(iter(config.workspaces)),
        profile=profile.profile_id,
        expected_branch="master",
        objective="health",
        references=(),
        allowed_paths=(),
        acceptance_criteria=(),
    )
    resolved_agent_id, resolved_model_route = policy.resolve_agent_for_task(dummy_task, config, profile)

    # Get effective model settings and execution profile from agent registry
    agent_entry = config.agent_registry.get(resolved_agent_id)
    execution_profile = agent_entry.execution_profile if agent_entry else None
    effective_context_limit = agent_entry.effective_context_limit if agent_entry else None
    effective_output_limit = agent_entry.effective_output_limit if agent_entry else None

    credential = _read_credential(config)
    redactor = SecretRedactor([credential])
    temp = Path(config.runtime_root) / "tmp" / f"health-{store.new_run_id()}"
    temp.mkdir(parents=True, exist_ok=False)
    argv = _build_argv(
        config, profile, "Reply with exactly PONG", None,
        resolved_agent_id, resolved_model_route,
        execution_profile, effective_context_limit, effective_output_limit
    )
    env = _build_worker_env(config, dummy_task, credential, "health")
    result = run_worker(
        argv,
        cwd=next(iter(config.workspaces.values())),
        env=env,
        stdout_path=temp / "stdout.ndjson",
        stderr_path=temp / "stderr.log",
        timeout_seconds=120,
        redactor=redactor,
    )
    outcome = parse_events(
        temp / "stdout.ndjson",
        redactor=redactor,
        max_summary_chars=config.max_summary_chars,
    )
    return {
        "pong": outcome.session_id is not None
        and "PONG" in outcome.redacted_summary.upper()
        and not outcome.malformed_lines
        and outcome.error_message is None,
        "session_id": outcome.session_id,
        "text": outcome.redacted_summary,
        "exit_code": result.exit_code,
        "timed_out": result.timed_out,
    }


def _check_circuit_breaker(
    config: BridgeConfig,
    agent_id: str,
) -> tuple[bool, str | None]:
    """Check if the agent's route is circuit-broken.
    Returns (is_open, cooldown_until).
    """
    if not config.recovery_policy:
        return False, None
    
    agent_policy = config.recovery_policy.per_agent_policies.get(agent_id)
    if not agent_policy:
        return False, None
    
    # Check route health tracking (in state directory)
    state_root = Path(config.runtime_root).parent / "state"
    route_health_path = state_root / "route-health.json"
    if not route_health_path.is_file():
        return False, None
    
    import json
    try:
        health_data = json.loads(route_health_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, None
    
    routes = health_data.get("routes", {})
    route_info = routes.get(agent_id, {})
    consecutive_failures = route_info.get("consecutive_failures", 0)
    cooldown_until = route_info.get("cooldown_until")
    
    threshold = agent_policy.get("circuit_breaker_threshold", 5)
    if consecutive_failures >= threshold:
        if cooldown_until:
            try:
                from datetime import datetime, timezone
                cooldown_time = datetime.fromisoformat(cooldown_until.replace("Z", "+00:00"))
                if datetime.now(timezone.utc) < cooldown_time:
                    return True, cooldown_until
            except ValueError:
                pass
        return True, cooldown_until
    
    return False, None
