"""Shared automatic recovery engine with per-agent policies."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import BridgeConfig, RecoveryPolicy
from .errors import ConfigError, PolicyError
from .gitutil import fingerprint, fingerprint_differences, fingerprints_match, resolve_workspace, status_entries, branch, head
from .lock import RepositoryLock
from .proc import ProcessResult, run_worker
from .redact import SecretRedactor
from .store import (
    load_checkpoint,
    load_workflow,
    list_runs,
    read_result,
    read_state,
    update_state,
    write_result,
    utc_now,
)
from .events import FailureCode, classify_failure, parse_events
from .policy import resolve_agent_for_task, build_prompt, evaluate_scope
from .config import Profile
from .contracts import Task, load_task
from .runner import _execute_worker_attempt, _build_argv, _build_worker_env, _read_credential, _persist_result, _base_result, EXIT_BY_STATUS


@dataclass(frozen=True)
class RecoveryDecision:
    """Decision made by the recovery engine."""
    action: str  # "RETRY", "ESCALATE", "QUARANTINE", "BLOCK", "CONTINUE"
    reason: str
    agent_id: str | None = None
    model_route: str | None = None
    retry_count: int = 0
    total_recovery_retries: int = 0
    checkpoint_id: str | None = None
    requires_user_intervention: bool = False


@dataclass(frozen=True)
class RecoveryContext:
    """Context for recovery evaluation."""
    config: BridgeConfig
    task: Task
    profile: Profile
    run_id: str
    run_directory: Path
    baseline: dict[str, Any]
    workspace: str
    exit_code: int | None
    outcome: Any  # WorkerOutcome
    stderr_tail: str
    error_classification: dict[str, Any] | None


def get_agent_recovery_policy(config: BridgeConfig, agent_id: str) -> dict[str, Any] | None:
    """Get the recovery policy for a specific agent."""
    if not config.recovery_policy:
        return None
    return config.recovery_policy.per_agent_policies.get(agent_id)


def is_failure_retryable(
    error_classification: dict[str, Any],
    agent_recovery_policy: dict[str, Any] | None,
) -> bool:
    """Determine if a failure is retryable based on agent policy."""
    if not agent_recovery_policy:
        return error_classification.get("retryable", False)
    
    category = error_classification.get("category", "").lower()
    code = error_classification.get("code", "").lower()
    
    retryable_categories = {c.lower() for c in agent_recovery_policy.get("retryable_categories", [])}
    non_retryable_categories = {c.lower() for c in agent_recovery_policy.get("non_retryable_categories", [])}
    
    # Explicit non-retryable takes precedence
    if category in non_retryable_categories or code in non_retryable_categories:
        return False
    
    return category in retryable_categories or code in retryable_categories or error_classification.get("retryable", False)


def get_consecutive_failure_count(workflow: dict[str, Any], task_id: str) -> int:
    """Get consecutive failure count for a task lineage."""
    # For now, use the correction_rounds as a proxy
    entry = workflow.get("tasks", {}).get(task_id)
    if isinstance(entry, dict):
        return int(entry.get("correction_rounds", 0) or 0)
    return 0


def get_total_recovery_retries(workflow: dict[str, Any], task_id: str) -> int:
    """Get total recovery retries for a task lineage."""
    entry = workflow.get("tasks", {}).get(task_id)
    if isinstance(entry, dict):
        return int(entry.get("total_recovery_retries", 0) or 0)
    return 0


def check_circuit_breaker(
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
    
    # Check route health tracking
    route_health_path = Path(config.runtime_root) / "route-health.json"
    if not route_health_path.is_file():
        return False, None
    
    import json
    try:
        health_data = json.loads(route_health_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, None
    
    route_key = agent_id  # logical agent ID
    route_info = health_data.get(route_key, {})
    consecutive_failures = route_info.get("consecutive_failures", 0)
    cooldown_until = route_info.get("cooldown_until")
    
    threshold = agent_policy.get("circuit_breaker_threshold", 5)
    if consecutive_failures >= threshold:
        if cooldown_until:
            try:
                cooldown_time = datetime.fromisoformat(cooldown_until.replace("Z", "+00:00"))
                if datetime.now(timezone.utc) < cooldown_time:
                    return True, cooldown_until
            except ValueError:
                pass
        return True, cooldown_until
    
    return False, None


def update_route_health(
    config: BridgeConfig,
    agent_id: str,
    failure_classification: dict[str, Any] | None = None,
    success: bool = False,
) -> None:
    """Update route health tracking."""
    if not config.recovery_policy or not config.recovery_policy.route_health_tracking.get("enabled", True):
        return
    
    # route-health.json is in the state directory (sibling of runtime_root)
    state_root = Path(config.runtime_root).parent / "state"
    route_health_path = state_root / "route-health.json"
    route_health_path.parent.mkdir(parents=True, exist_ok=True)
    
    import json
    health_data = {}
    if route_health_path.is_file():
        try:
            health_data = json.loads(route_health_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            health_data = {}
    
    route_key = agent_id
    route_info = health_data.get(route_key, {
        "logical_agent": agent_id,
        "consecutive_failures": 0,
        "last_failure_classification": None,
        "cooldown_until": None,
    })
    
    if success:
        route_info["consecutive_failures"] = 0
        route_info["last_failure_classification"] = None
    elif failure_classification:
        route_info["consecutive_failures"] = route_info.get("consecutive_failures", 0) + 1
        route_info["last_failure_classification"] = failure_classification.get("code")
        
        # Check if we need to set cooldown
        agent_policy = config.recovery_policy.per_agent_policies.get(agent_id) if config.recovery_policy else None
        if agent_policy:
            threshold = agent_policy.get("circuit_breaker_threshold", 5)
            if route_info["consecutive_failures"] >= threshold:
                cooldown_seconds = agent_policy.get("circuit_breaker_cooldown_seconds", 600)
                route_info["cooldown_until"] = (
                    datetime.now(timezone.utc).timestamp() + cooldown_seconds
                )
    
    health_data[route_key] = route_info
    route_health_path.write_text(json.dumps(health_data, indent=2), encoding="utf-8")


def evaluate_recovery(
    context: RecoveryContext,
) -> RecoveryDecision:
    """Evaluate whether and how to recover from a failure."""
    config = context.config
    task = context.task
    profile = context.profile
    error_classification = context.error_classification
    
    # Resolve the agent for this task
    agent_id, model_route = resolve_agent_for_task(task, config, profile)
    agent_policy = get_agent_recovery_policy(config, agent_id)
    
    if not agent_policy:
        # No recovery policy - conservative default
        return RecoveryDecision(
            action="BLOCK",
            reason="No recovery policy configured for agent",
            agent_id=agent_id,
            model_route=model_route,
            requires_user_intervention=True,
        )
    
    # Check circuit breaker
    circuit_open, cooldown_until = check_circuit_breaker(config, agent_id)
    if circuit_open:
        return RecoveryDecision(
            action="QUARANTINE",
            reason=f"Route circuit breaker open (cooldown until {cooldown_until})",
            agent_id=agent_id,
            model_route=model_route,
            requires_user_intervention=True,
        )
    
    # Check if failure is retryable
    if error_classification and not is_failure_retryable(error_classification, agent_policy):
        # Non-retryable failure - check if we should escalate
        if agent_policy.get("quarantine_on_persistent_failures", True):
            return RecoveryDecision(
                action="QUARANTINE",
                reason=f"Non-retryable failure: {error_classification.get('code')}",
                agent_id=agent_id,
                model_route=model_route,
                requires_user_intervention=True,
            )
        return RecoveryDecision(
            action="BLOCK",
            reason=f"Non-retryable failure: {error_classification.get('code')}",
            agent_id=agent_id,
            model_route=model_route,
            requires_user_intervention=True,
        )
    
    # Check retry budgets
    workflow = load_workflow(config.runtime_root)
    consecutive_failures = get_consecutive_failure_count(workflow, task.task_id)
    total_recovery_retries = get_total_recovery_retries(workflow, task.task_id)
    
    max_consecutive = agent_policy.get("consecutive_retries", 2)
    max_total = agent_policy.get("total_recovery_retries_per_task", 3)
    
    if consecutive_failures >= max_consecutive:
        return RecoveryDecision(
            action="ESCALATE",
            reason=f"Consecutive failure limit reached ({consecutive_failures}/{max_consecutive})",
            agent_id=agent_id,
            model_route=model_route,
            retry_count=consecutive_failures,
            total_recovery_retries=total_recovery_retries,
            requires_user_intervention=True,
        )
    
    if total_recovery_retries >= max_total:
        return RecoveryDecision(
            action="ESCALATE",
            reason=f"Total recovery retry budget exhausted ({total_recovery_retries}/{max_total})",
            agent_id=agent_id,
            model_route=model_route,
            retry_count=consecutive_failures,
            total_recovery_retries=total_recovery_retries,
            requires_user_intervention=True,
        )
    
    # Check if we have a valid checkpoint to resume from
    checkpoint_id = task.checkpoint_id
    if checkpoint_id:
        try:
            checkpoint = load_checkpoint(config.runtime_root, checkpoint_id)
            # Verify checkpoint matches current workspace state
            current_fp = fingerprint(context.workspace)
            if fingerprints_match(checkpoint["fingerprint"], current_fp):
                return RecoveryDecision(
                    action="RETRY",
                    reason="Valid checkpoint available for resume",
                    agent_id=agent_id,
                    model_route=model_route,
                    retry_count=consecutive_failures,
                    total_recovery_retries=total_recovery_retries,
                    checkpoint_id=checkpoint_id,
                )
            else:
                differences = fingerprint_differences(checkpoint["fingerprint"], current_fp)
                return RecoveryDecision(
                    action="BLOCK",
                    reason=f"Working tree diverged from checkpoint: {differences}",
                    agent_id=agent_id,
                    model_route=model_route,
                    requires_user_intervention=True,
                )
        except Exception:
            pass  # Fall through to no-checkpoint logic
    
    # No checkpoint or invalid checkpoint - can we retry from scratch?
    # Only retry if we have low consecutive failures
    if consecutive_failures == 0:
        return RecoveryDecision(
            action="RETRY",
            reason="First failure, retrying from scratch",
            agent_id=agent_id,
            model_route=model_route,
            retry_count=0,
            total_recovery_retries=0,
        )
    
    return RecoveryDecision(
        action="BLOCK",
        reason="No valid checkpoint and consecutive failures > 0",
        agent_id=agent_id,
        model_route=model_route,
        retry_count=consecutive_failures,
        total_recovery_retries=total_recovery_retries,
        requires_user_intervention=True,
    )


def execute_recovery(
    config: BridgeConfig,
    task: Task,
    profile: Profile,
    failed_run_id: str,
    decision: RecoveryDecision,
) -> tuple[dict[str, Any], int]:
    """Execute a recovery decision by running the worker again using shared execution path.
    
    Uses the failed run's session_id for exact-session recovery (not task.resume_session_id).
    Only RETRY action executes a worker; ESCALATE returns recommendation without execution.
    """
    if decision.action != "RETRY":
        raise PolicyError(f"Cannot execute recovery action: {decision.action} (only RETRY executes)")
    
    # Use the resolved agent from the decision
    agent_id = decision.agent_id
    model_route = decision.model_route
    
    # Get agent registry entry for execution profile and settings
    agent_entry = config.agent_registry.get(agent_id)
    execution_profile = agent_entry.execution_profile if agent_entry else None
    agent_permission_policy = agent_entry.permission_policy if agent_entry else None
    effective_context_limit = agent_entry.effective_context_limit if agent_entry else None
    effective_output_limit = agent_entry.effective_output_limit if agent_entry else None
    
    workspace = resolve_workspace(config.workspace(task.workspace_id))
    
    # If we have a checkpoint, validate it
    baseline = fingerprint(workspace)
    if decision.checkpoint_id:
        checkpoint = load_checkpoint(config.runtime_root, decision.checkpoint_id)
        if not fingerprints_match(checkpoint["fingerprint"], baseline):
            differences = fingerprint_differences(checkpoint["fingerprint"], baseline)
            raise PolicyError(
                "Working tree does not match the approved checkpoint",
                checkpoint_id=decision.checkpoint_id,
                differences=differences,
            )
    
    # Get the failed run's session_id for exact-session recovery
    failed_result = read_result(config.runtime_root, failed_run_id)
    resume_session_id = failed_result.get("session_id")
    
    # Get branch/head for prompt building
    before_branch = branch(workspace)
    before_head = head(workspace)
    
    # Build prompt
    prompt = build_prompt(
        task,
        profile,
        workspace_root=workspace,
        branch=before_branch,
        head=before_head,
        max_prompt_chars=config.max_prompt_chars,
        agent_permission_policy=agent_permission_policy,
    )
    
    # Create new run directory
    from .store import create_run, new_run_id
    new_run_id_val = new_run_id()
    run_directory = create_run(
        config.runtime_root,
        run_id=new_run_id_val,
        task=task,
        config_snapshot=config.sanitized(),
        prompt=prompt,
        baseline=baseline,
    )
    
    # Get credential
    credential = None
    if config.worker_type == "opencode":
        credential = _read_credential(config)
    
    timeout_seconds = float(task.timeout_seconds or config.timeout_seconds)
    
    # Execute using shared execution path with exact failed session_id
    return _execute_worker_attempt(
        config=config,
        task=task,
        profile=profile,
        run_id=new_run_id_val,
        workspace=workspace,
        before_branch=before_branch,
        before_head=before_head,
        baseline=baseline,
        resolved_agent_id=agent_id,
        resolved_model_route=model_route,
        execution_profile=execution_profile,
        agent_permission_policy=agent_permission_policy,
        effective_context_limit=effective_context_limit,
        effective_output_limit=effective_output_limit,
        resume_session_id=resume_session_id,  # Exact-session recovery: use failed run's session_id
        credential=credential,
        timeout_seconds=timeout_seconds,
        run_directory=run_directory,
    )


def _update_workflow_recovery_counters(
    runtime_root: str,
    task_id: str,
    consecutive_failures: int,
    total_recovery_retries: int,
) -> None:
    """Persist recovery counters in workflow for bounded recovery tracking."""
    workflow = load_workflow(runtime_root)
    tasks = workflow["tasks"]
    entry = tasks.get(task_id)
    if not isinstance(entry, dict):
        entry = {
            "task_id": task_id,
            "status": "PENDING",
            "run_ids": [],
            "attempts": 0,
            "correction_rounds": 0,
            "total_recovery_retries": 0,
        }
        tasks[task_id] = entry
    entry["correction_rounds"] = consecutive_failures
    entry["total_recovery_retries"] = total_recovery_retries
    entry["updated_at"] = utc_now()
    save_workflow(runtime_root, workflow)


def auto_recover(
    config_path: str,
    task_path: str,
    max_recovery_attempts: int = 3,
) -> tuple[dict[str, Any], int]:
    """Main entry point for automatic recovery.
    
    Loads config and task, evaluates the last failed run, and attempts recovery
    according to the shared recovery policy.
    
    Bounded recovery semantics:
    - Only RETRY authorizes another worker invocation
    - ESCALATE returns structured recommendation only (no execution)
    - max_recovery_attempts limits total recovery invocations
    - Consecutive and total recovery counters persisted in workflow
    """
    config = load_config(config_path)
    task = load_task(task_path)
    profile = config.profile(task.profile)
    
    # Find the last run for this task
    runs = list_runs(config.runtime_root, limit=500)
    task_runs = [r for r in runs if r.get("task_id") == task.task_id]
    if not task_runs:
        raise PolicyError("No runs found for task", task_id=task.task_id)
    
    last_run = task_runs[0]  # Most recent
    run_id = last_run["run_id"]
    
    # Load run result
    try:
        result = read_result(config.runtime_root, run_id)
    except Exception:
        raise PolicyError("No result found for last run", run_id=run_id)
    
    # Check if last run was a failure that could be recovered
    status = result.get("status")
    if status not in ("FAILED", "TIMED_OUT", "INTERRUPTED"):
        raise PolicyError(f"Last run status {status} does not require recovery", run_id=run_id)
    
    # Load workflow to get current recovery counters
    workflow = load_workflow(config.runtime_root)
    task_entry = workflow["tasks"].get(task.task_id, {})
    consecutive_failures = int(task_entry.get("correction_rounds", 0) or 0)
    total_recovery_retries = int(task_entry.get("total_recovery_retries", 0) or 0)
    
    # Bounded recovery: enforce max_recovery_attempts
    if total_recovery_retries >= max_recovery_attempts:
        return {
            "status": "BLOCKED",
            "message": f"Max recovery attempts ({max_recovery_attempts}) exceeded",
            "total_recovery_retries": total_recovery_retries,
            "max_recovery_attempts": max_recovery_attempts,
        }, 5
    
    # Load run details
    run_directory = Path(config.runtime_root) / "runs" / run_id
    state = read_state(config.runtime_root, run_id)
    
    # Parse events to get outcome
    redactor = SecretRedactor([])
    outcome = parse_events(
        run_directory / "stdout.ndjson",
        redactor=redactor,
        max_summary_chars=config.max_summary_chars,
    )
    
    # Get error classification
    error_classification = result.get("error")
    
    # Create recovery context
    workspace = resolve_workspace(config.workspace(task.workspace_id))
    baseline = fingerprint(workspace)
    
    context = RecoveryContext(
        config=config,
        task=task,
        profile=profile,
        run_id=run_id,
        run_directory=run_directory,
        baseline=baseline,
        workspace=workspace,
        exit_code=result.get("exit_code"),
        outcome=outcome,
        stderr_tail=state.get("stderr_tail", ""),
        error_classification=error_classification,
    )
    
    # Evaluate recovery
    decision = evaluate_recovery(context)
    
    # Handle decision
    if decision.action == "RETRY":
        # Execute recovery attempt
        new_result, exit_code = execute_recovery(config, task, profile, run_id, decision)
        
        # Update recovery counters
        new_consecutive = consecutive_failures + 1
        new_total = total_recovery_retries + 1
        _update_workflow_recovery_counters(
            config.runtime_root, task.task_id, new_consecutive, new_total
        )
        
        # Update route health based on result
        agent_id = decision.agent_id
        new_error = new_result.get("error")
        update_route_health(config, agent_id, new_error, success=new_error is None)
        
        return new_result, exit_code
    
    elif decision.action == "ESCALATE":
        # ESCALATE returns structured recommendation ONLY - no worker execution
        # Update counters for tracking but don't execute
        new_consecutive = consecutive_failures + 1
        new_total = total_recovery_retries + 1
        _update_workflow_recovery_counters(
            config.runtime_root, task.task_id, new_consecutive, new_total
        )
        
        return {
            "status": "ESCALATED",
            "message": decision.reason,
            "decision": decision.__dict__,
            "escalation_recommendation": config.recovery_policy.escalation_policy.default_recommendations.get(decision.agent_id)
            if config.recovery_policy and config.recovery_policy.escalation_policy
            else None,
            "consecutive_failures": new_consecutive,
            "total_recovery_retries": new_total,
            "requires_user_intervention": True,
        }, 0
    
    elif decision.action == "QUARANTINE":
        # Mark as quarantined
        update_state(config.runtime_root, run_id, quarantine=True)
        return {
            "status": "QUARANTINED",
            "message": decision.reason,
            "decision": decision.__dict__,
        }, 5
    
    else:  # BLOCK
        return {
            "status": "BLOCKED",
            "message": decision.reason,
            "decision": decision.__dict__,
        }, 5