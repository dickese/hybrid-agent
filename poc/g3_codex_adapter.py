#!/usr/bin/env python3
"""G3 Codex integration adapter: minimal wrapper for Windows-hosted Codex to invoke Augani in Docker.

This adapter provides the smallest possible integration mechanism:
- Creates/inspects durable plans
- Dispatches approved OpenCode jobs
- Monitors job progress
- Inspects structured job results
- Reads actual worker implementation
- Runs deterministic verification
- Records independent review
- Advances plan only after acceptance

Does NOT automatically pre-record reviews on behalf of Codex.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
import time
from typing import Any


# Configuration constants
DOCKER_IMAGE = "hybrid-agent-g3:0.1"
WORK_MOUNT = "D:/tools/hybrid-agent:/work:ro"
RUNTIME_MOUNT_BASE = "D:/tools/hybrid-agent/.runtime"
OPENCODE_CONFIG_MOUNT = "C:/Users/ANH DUC/.config/opencode/opencode.json:/run/opencode-global.json:ro"
SECRET_MOUNT = "D:/tools/hybrid-agent/.runtime/secrets/9router.key:/run/secrets/9router.key:ro"
RUNNER_PATH = "/work/agent-orchestrator-poc/plugins/agent-orchestrator/scripts/cli_agent_job.py"
CONFIG_PATH = "/work/poc/opencode_agents.json"
DEFAULT_CLI = "opencode-9router"
DEFAULT_MODEL = "9router/agent-build"
DEFAULT_CLI_AGENT = "bridge-g3"
DASHBOARD_PORT = 8080

# Shared persistent workspace (host-mounted, survives container recreation)
SHARED_WORKSPACE_HOST = "D:/tools/hybrid-agent/.runtime/poc-g3/workspace"
SHARED_WORKSPACE_CONTAINER = "/g3/workspace"

# Path conversion: host path -> container path
HOST_WORK_ROOT = "D:/tools/hybrid-agent"
CONTAINER_WORK_ROOT = "/work"

# G3 authorization gate
G3_AUTHORIZED_ENV = "G3_AUTHORIZED"
# Durable authorization state file (persists across container restarts)
AUTH_STATE_FILE = pathlib.Path("/g3/state/.g3_authorized")


def to_container_path(host_path: pathlib.Path) -> str:
    """Convert a host path to container path (D:/tools/hybrid-agent -> /work)."""
    try:
        rel = host_path.resolve().relative_to(HOST_WORK_ROOT)
        # Use PurePosixPath to ensure forward slashes for container paths
        return str(pathlib.PurePosixPath(CONTAINER_WORK_ROOT) / rel.as_posix())
    except ValueError:
        # Path is not under HOST_WORK_ROOT, return as-is (assume already container path)
        return str(host_path)


def compose_exec(args: list[str], env: dict[str, str], timeout: int = 300, **kwargs) -> subprocess.CompletedProcess:
    """Execute a command in the running docker-compose service."""
    cmd = ["docker", "compose", "-f", "docker-compose.g3.yml", "exec", "-T", "g3-orchestrator"] + args
    # Use the host environment - docker-compose will pass env vars defined in the compose file
    # and we pass additional ones via -e flags if needed
    return subprocess.run(cmd, env=env, timeout=timeout, **kwargs)


def ensure_container_running(g3_base: pathlib.Path) -> None:
    """Ensure the docker-compose service is running."""
    result = subprocess.run(
        ["docker", "compose", "-f", "docker-compose.g3.yml", "ps", "-q", "g3-orchestrator"],
        capture_output=True, text=True
    )
    if not result.stdout.strip():
        # Start the service
        subprocess.run(
            ["docker", "compose", "-f", "docker-compose.g3.yml", "up", "-d", "g3-orchestrator"],
            check=True
        )
        # Wait for container to be ready
        time.sleep(3)


def jrun(args: list[str], env: dict[str, str], g3_base: pathlib.Path, timeout: int = 300) -> dict[str, Any]:
    """Run a JSON-output command in the container via docker-compose exec."""
    ensure_container_running(g3_base)
    result = compose_exec(
        ["python3", "-B", RUNNER_PATH, *args, "--json"],
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(args)}\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}")
    return json.loads(result.stdout)


def run_cli(args: list[str], env: dict[str, str], g3_base: pathlib.Path, expect: int = 0, timeout: int = 300) -> subprocess.CompletedProcess:
    """Run a CLI command in the container via docker-compose exec."""
    ensure_container_running(g3_base)
    result = compose_exec(
        ["python3", "-B", RUNNER_PATH, *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != expect:
        raise RuntimeError(f"Command failed (rc={result.returncode}): {' '.join(args)}\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}")
    return result


def check_authorization_state(g3_base: pathlib.Path) -> bool:
    """Check if a live job has already been authorized and launched.
    
    Returns True if authorization has been consumed (i.e., a live job was launched).
    """
    # Check in container state
    auth_file = g3_base / "state" / ".g3_authorized"
    if auth_file.exists():
        return True
    return False


def mark_authorization_consumed(g3_base: pathlib.Path) -> None:
    """Mark the G3 authorization as consumed (one live job launched)."""
    auth_file = g3_base / "state" / ".g3_authorized"
    auth_file.parent.mkdir(parents=True, exist_ok=True)
    auth_file.write_text(__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(), encoding="utf-8")


def validate_authorization(env: dict[str, str], g3_base: pathlib.Path) -> None:
    """Validate G3 authorization: requires env var AND not already consumed."""
    if env.get(G3_AUTHORIZED_ENV) != "1":
        raise RuntimeError(f"G3 authorization required: set {G3_AUTHORIZED_ENV}=1 to launch live worker job")
    
    if check_authorization_state(g3_base):
        raise RuntimeError("G3 authorization already consumed: maximum one live worker job permitted for G3-C fixture")


def create_plan(task_file: pathlib.Path | None, plan_file: pathlib.Path, workspace: str, plan_id: str, title: str, executor: str, env: dict, g3_base: pathlib.Path) -> dict:
    """Create a durable plan."""
    # Convert host paths to container paths
    plan_file_container = to_container_path(plan_file)
    args = [
        "create-plan",
        "--plan-file", plan_file_container,
        "--workspace", workspace,
        "--title", title,
        "--plan-id", plan_id,
        "--executor", executor,
        "--config", CONFIG_PATH,
    ]
    if task_file:
        task_file_container = to_container_path(task_file)
        # Note: upstream create-plan doesn't have --task-file, this is for reference only
    return jrun(args, env, g3_base, timeout=120)


def launch_job(cli: str, model: str, cli_agent: str, workspace: str, task_file: pathlib.Path, plan_id: str, checklist_item: str, allowed_paths: list[str], max_changed_files: int, timeout_seconds: int, env: dict, g3_base: pathlib.Path) -> dict:
    """Launch an approved OpenCode worker job. Requires G3_AUTHORIZED=1."""
    # Enforce G3 authorization (env var + durable state)
    validate_authorization(env, g3_base)
    
    # Invoke scope validation before dispatch
    validate_scope_before_launch(task_file, allowed_paths, env, g3_base)
    
    # Convert host paths to container paths
    task_file_container = to_container_path(task_file)
    
    args = [
        "launch",
        "--cli", cli,
        "--model", model,
        "--cli-agent", cli_agent,
        "--workspace", workspace,
        "--task-file", task_file_container,
        "--plan-id", plan_id,
        "--checklist-item", checklist_item,
        "--config", CONFIG_PATH,
        "--timeout-seconds", str(timeout_seconds),
        "--max-changed-files", str(max_changed_files),
        "--no-notify",
        "--allow-unstructured-task",
    ]
    for path in allowed_paths:
        args.extend(["--allow-path", path])
    # Use a timeout that accounts for the worker timeout + buffer
    adapter_timeout = timeout_seconds + 120
    result = jrun(args, env, g3_base, timeout=adapter_timeout)
    
    # Mark authorization as consumed on successful launch
    mark_authorization_consumed(g3_base)
    return result


def validate_scope_before_launch(task_file: pathlib.Path, allowed_paths: list[str], env: dict, g3_base: pathlib.Path) -> None:
    """Validate scope by invoking g3_validate_scope.py before worker dispatch."""
    import json
    # Prepare launch args for validation (simulate what launch would pass)
    launch_args = []
    for path in allowed_paths:
        launch_args.extend(["--allow-path", path])
    
    # Convert host path to container path for the task file
    task_file_container = to_container_path(task_file)
    
    # Run scope validator in container
    result = compose_exec(
        [
            "python3", "-B", "/work/poc/g3_validate_scope.py",
            task_file_container,
            json.dumps(launch_args)
        ],
        env=env,
        timeout=60,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Scope validation failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}")
    print("Scope validation passed: runtime allowlist matches task contract exactly")


def wait_job(job_id: str, timeout_seconds: int, poll_seconds: int, env: dict, g3_base: pathlib.Path) -> dict:
    """Wait for job completion."""
    # Use the same timeout as the wait command itself
    adapter_timeout = timeout_seconds + 60
    return jrun([
        "wait", job_id,
        "--timeout-seconds", str(timeout_seconds),
        "--poll-seconds", str(poll_seconds),
    ], env, g3_base, timeout=adapter_timeout)


def job_status(job_id: str, env: dict, g3_base: pathlib.Path) -> dict:
    """Get job status."""
    return jrun(["status", job_id], env, g3_base)


def record_review(job_id: str, verdict: str, reviewer: str, test_result: str, notes: str, env: dict, g3_base: pathlib.Path) -> dict:
    """Record an independent review (requires --test evidence for acceptance)."""
    return jrun([
        "record-review", job_id,
        "--verdict", verdict,
        "--reviewer", reviewer,
        "--test", test_result,
        "--notes", notes,
    ], env, g3_base)


def plan_status(plan_id: str, env: dict, g3_base: pathlib.Path) -> dict:
    """Get plan status."""
    return jrun(["plan-status", plan_id], env, g3_base)


def dashboard_start(env: dict, g3_base: pathlib.Path) -> subprocess.Popen:
    """Start the dashboard server in the container (binds 0.0.0.0:8080)."""
    # The dashboard-web command in upstream binds 127.0.0.1; we need a wrapper
    # For now, return the command that user can run
    return None


def verify_worker_changes(workspace: pathlib.Path, allowed_prefixes: tuple[str, ...], required_files: list[str]) -> tuple[list[str], list[str]]:
    """Verify worker changes are within scope and required files exist.
    
    Inspects both tracked diffs and untracked files.
    """
    proc = subprocess.run(
        ["git", "-C", str(workspace), "status", "--porcelain=v1", "--untracked-files=all"],
        capture_output=True, text=True, check=True
    )
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    paths = []
    for line in lines:
        value = line[3:] if len(line) > 3 else line
        if " -> " in value:
            value = value.split(" -> ", 1)[1]
        paths.append(value.strip().strip('"'))
    
    out_of_scope = [p for p in paths if not any(p.startswith(prefix) for prefix in allowed_prefixes)]
    missing = [f for f in required_files if not (workspace / f).is_file()]
    return out_of_scope, missing


def get_shared_workspace() -> pathlib.Path:
    """Get the shared persistent workspace path (host-side for verification)."""
    return pathlib.Path(SHARED_WORKSPACE_HOST)


def run_deterministic_tests(workspace: pathlib.Path, test_cmd: list[str], env: dict) -> tuple[bool, str]:
    """Run deterministic tests in the workspace."""
    proc = subprocess.run(test_cmd, cwd=workspace, env=env, capture_output=True, text=True, timeout=120)
    output = proc.stdout + proc.stderr
    ok = proc.returncode == 0 and "OK" in output
    return ok, output


def main() -> int:
    parser = argparse.ArgumentParser(description="G3 Codex integration adapter")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Default shared workspace
    default_workspace = SHARED_WORKSPACE_CONTAINER
    
    # create-plan
    p_plan = subparsers.add_parser("create-plan", help="Create a durable plan")
    p_plan.add_argument("--task-file", type=pathlib.Path, help="Task contract file (optional)")
    p_plan.add_argument("--plan-file", type=pathlib.Path, required=True)
    p_plan.add_argument("--workspace", default=default_workspace)
    p_plan.add_argument("--plan-id", required=True)
    p_plan.add_argument("--title", required=True)
    p_plan.add_argument("--executor", required=True)
    
    # launch
    p_launch = subparsers.add_parser("launch", help="Launch an approved OpenCode job")
    p_launch.add_argument("--task-file", type=pathlib.Path, required=True)
    p_launch.add_argument("--workspace", default=default_workspace)
    p_launch.add_argument("--plan-id", required=True)
    p_launch.add_argument("--checklist-item", required=True)
    p_launch.add_argument("--allowed-paths", nargs="+", required=True)
    p_launch.add_argument("--max-changed-files", type=int, default=10)
    p_launch.add_argument("--timeout-seconds", type=int, default=600)
    
    # wait
    p_wait = subparsers.add_parser("wait", help="Wait for job completion")
    p_wait.add_argument("--job-id", required=True)
    p_wait.add_argument("--timeout-seconds", type=int, default=660)
    p_wait.add_argument("--poll-seconds", type=int, default=2)
    
    # status
    p_status = subparsers.add_parser("status", help="Get job status")
    p_status.add_argument("--job-id", required=True)
    
    # record-review
    p_review = subparsers.add_parser("record-review", help="Record independent review")
    p_review.add_argument("--job-id", required=True)
    p_review.add_argument("--verdict", choices=["accepted", "rejected"], required=True)
    p_review.add_argument("--reviewer", required=True)
    p_review.add_argument("--test-result", required=True)
    p_review.add_argument("--notes", required=True)
    
    # plan-status
    p_plan_status = subparsers.add_parser("plan-status", help="Get plan status")
    p_plan_status.add_argument("--plan-id", required=True)
    
    # verify
    p_verify = subparsers.add_parser("verify", help="Verify worker changes and run tests")
    p_verify.add_argument("--workspace", type=pathlib.Path, default=pathlib.Path(SHARED_WORKSPACE_HOST))
    p_verify.add_argument("--allowed-prefixes", nargs="+", required=True)
    p_verify.add_argument("--required-files", nargs="+", required=True)
    p_verify.add_argument("--test-cmd", required=True, help="Test command to run (quoted as single string)")
    
    # dashboard-url
    p_dash = subparsers.add_parser("dashboard-url", help="Print dashboard URL")
    
    args = parser.parse_args()
    
    # Environment setup
    g3_base = pathlib.Path(os.environ.get("G3_BASE", "D:/tools/hybrid-agent/.runtime/poc-g3")).resolve()
    g3_base.mkdir(parents=True, exist_ok=True)
    
    # Ensure shared workspace exists on host
    shared_ws_host = pathlib.Path(SHARED_WORKSPACE_HOST)
    shared_ws_host.mkdir(parents=True, exist_ok=True)
    
    env = os.environ.copy()
    env["AGENT_ORCHESTRATOR_HOME"] = str(g3_base / "state")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["G3_CLI"] = env.get("G3_CLI", DEFAULT_CLI)
    env["G3_MODEL"] = env.get("G3_MODEL", DEFAULT_MODEL)
    env["G3_CLI_AGENT"] = env.get("G3_CLI_AGENT", DEFAULT_CLI_AGENT)
    
    # Load 9Router secret (only for processes that need it)
    secret_path = pathlib.Path("D:/tools/hybrid-agent/.runtime/secrets/9router.key")
    if secret_path.is_file():
        env["NINE_ROUTER_KEY"] = secret_path.read_text(encoding="utf-8").strip()
    
    try:
        if args.command == "create-plan":
            # Use shared workspace for plan
            workspace = SHARED_WORKSPACE_CONTAINER
            result = create_plan(
                args.task_file, args.plan_file, workspace, args.plan_id,
                args.title, args.executor, env, g3_base
            )
            print(json.dumps(result, indent=2))
        
        elif args.command == "launch":
            # Use shared workspace for launch
            workspace = SHARED_WORKSPACE_CONTAINER
            result = launch_job(
                env["G3_CLI"], env["G3_MODEL"], env["G3_CLI_AGENT"],
                workspace, args.task_file, args.plan_id, args.checklist_item,
                args.allowed_paths, args.max_changed_files, args.timeout_seconds,
                env, g3_base
            )
            print(json.dumps(result, indent=2))
        
        elif args.command == "wait":
            result = wait_job(args.job_id, args.timeout_seconds, args.poll_seconds, env, g3_base)
            print(json.dumps(result, indent=2))
        
        elif args.command == "status":
            result = job_status(args.job_id, env, g3_base)
            print(json.dumps(result, indent=2))
        
        elif args.command == "record-review":
            result = record_review(
                args.job_id, args.verdict, args.reviewer,
                args.test_result, args.notes, env, g3_base
            )
            print(json.dumps(result, indent=2))
        
        elif args.command == "plan-status":
            result = plan_status(args.plan_id, env, g3_base)
            print(json.dumps(result, indent=2))
        
        elif args.command == "verify":
            # Verify uses host-side workspace path for git inspection
            out_of_scope, missing = verify_worker_changes(
                args.workspace, tuple(args.allowed_prefixes), args.required_files
            )
            if out_of_scope:
                print(f"Out of scope: {out_of_scope}", file=sys.stderr)
                return 1
            if missing:
                print(f"Missing required files: {missing}", file=sys.stderr)
                return 1
            
            # Parse test command (split on whitespace, respecting quotes)
            import shlex
            test_cmd = shlex.split(args.test_cmd)
            
            ok, output = run_deterministic_tests(args.workspace, test_cmd, env)
            if not ok:
                print(f"Tests failed:\n{output}", file=sys.stderr)
                return 1
            print("Verification passed")
        
        elif args.command == "dashboard-url":
            print(f"http://127.0.0.1:{DASHBOARD_PORT}/#token=<from-container-logs>")
            print("Run 'docker logs hybrid-agent-g3' to get the token from dashboard startup")
            print("Dashboard restricted to localhost (127.0.0.1) only")
        
        return 0
    
    except Exception as exc:
        print(f"Error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())