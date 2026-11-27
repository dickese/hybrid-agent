#!/usr/bin/env python3
"""G3 Offline Runtime Bootstrap: idempotent initialization without model inference.

This script prepares the G3 runtime environment inside the Docker container:
- Initializes the shared persistent workspace (only if not already initialized)
- Prepares container-compatible OpenCode configuration
- Verifies agent profile availability
- Establishes required state and evidence directories
- Validates readiness without dispatching a worker

Usage (inside container):
    python3 /work/poc/g3_bootstrap.py --verify-only

Usage (from Windows host):
    docker compose -f docker-compose.g3.yml exec g3-orchestrator python3 /work/poc/g3_bootstrap.py --verify-only
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
from typing import Any


# Configuration constants
SHARED_WORKSPACE = pathlib.Path("/g3/workspace")
STATE_DIR = pathlib.Path("/g3/state")
EVIDENCE_DIR = pathlib.Path("/g3/evidence")
OPENCODE_GLOBAL_CONFIG = pathlib.Path("/run/opencode-global.json")
OPENCODE_CONFIG_DIR = pathlib.Path("/tmp/opencode-config")
OPENCODE_CONFIG_FILE = OPENCODE_CONFIG_DIR / "opencode.json"
RUNNER_PATH = "/work/agent-orchestrator-poc/plugins/agent-orchestrator/scripts/cli_agent_job.py"
CONFIG_PATH = "/work/poc/opencode_agents.json"
CLI_AGENT = "bridge-g3"
CLI = "opencode-9router"
MODEL = "9router/agent-build"


def run_cmd(args: list[str], env: dict[str, str] | None = None, **kwargs) -> subprocess.CompletedProcess:
    """Run a command and return the completed process."""
    return subprocess.run(args, capture_output=True, text=True, env=env, **kwargs)


def jrun(args: list[str], env: dict[str, str] | None = None) -> dict[str, Any]:
    """Run a JSON-output command."""
    result = run_cmd([sys.executable, "-B", RUNNER_PATH, *args, "--json"], env=env)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(args)}\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}")
    return json.loads(result.stdout)


def init_workspace() -> bool:
    """Initialize the shared persistent workspace if not already initialized.
    
    Returns:
        True if workspace was newly initialized, False if it already existed.
    """
    if (SHARED_WORKSPACE / ".git").exists():
        return False
    
    SHARED_WORKSPACE.mkdir(parents=True, exist_ok=True)
    (SHARED_WORKSPACE / "README.md").write_text("# G3 disposable workspace\n", encoding="utf-8")
    (SHARED_WORKSPACE / ".gitignore").write_text("__pycache__/\n*.pyc\n.pytest_cache/\n", encoding="utf-8")
    
    # Copy .opencode agents
    shutil.copytree("/work/.opencode", SHARED_WORKSPACE / ".opencode", dirs_exist_ok=True)
    
    # Initialize git with safe directory handling
    subprocess.run(["git", "init", "-q"], cwd=SHARED_WORKSPACE, check=True)
    subprocess.run(["git", "config", "--global", "--add", "safe.directory", str(SHARED_WORKSPACE)], check=True)
    subprocess.run(["git", "config", "user.email", "poc@example.test"], cwd=SHARED_WORKSPACE, check=True)
    subprocess.run(["git", "config", "user.name", "PoC"], cwd=SHARED_WORKSPACE, check=True)
    subprocess.run(["git", "add", "-A"], cwd=SHARED_WORKSPACE, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=SHARED_WORKSPACE, check=True)
    
    return True


def prepare_opencode_config() -> None:
    """Prepare container-compatible OpenCode configuration."""
    OPENCODE_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    
    if OPENCODE_GLOBAL_CONFIG.exists():
        source = OPENCODE_GLOBAL_CONFIG.read_text(encoding="utf-8")
        # Adapt baseURL for container-to-host connectivity
        adapted = source.replace(
            "http://127.0.0.1:20128/v1", "http://host.docker.internal:20128/v1"
        )
        OPENCODE_CONFIG_FILE.write_text(adapted, encoding="utf-8")
    else:
        # Fallback minimal config
        minimal_config = {
            "provider": {
                "9router": {
                    "npm": "@9router/opencode-provider",
                    "options": {"apiKey": "${NINE_ROUTER_KEY}", "baseURL": "http://host.docker.internal:20128/v1"}
                }
            }
        }
        OPENCODE_CONFIG_FILE.write_text(json.dumps(minimal_config, indent=2), encoding="utf-8")


def verify_agent_profile() -> dict[str, Any]:
    """Verify the approved agent profile is available and correct."""
    # Use the runner's profiles command to check
    result = run_cmd([
        sys.executable, "-B", RUNNER_PATH, "profiles", "--config", CONFIG_PATH
    ])
    if result.returncode != 0:
        raise RuntimeError(f"Profiles command failed: {result.stderr}")
    
    # Parse the JSON output (profiles are top-level keys)
    import json
    profiles = json.loads(result.stdout)
    
    # Verify our custom agent exists
    if CLI not in profiles:
        raise RuntimeError(f"Custom agent '{CLI}' not found in profiles")
    
    # Verify the CLI agent profile exists (the bridge-g3.md profile)
    agent_path = SHARED_WORKSPACE / ".opencode" / "agents" / f"{CLI_AGENT}.md"
    if not agent_path.exists():
        raise RuntimeError(f"CLI agent profile '{CLI_AGENT}' not found at {agent_path}")
    
    return {
        "cli": CLI,
        "model": MODEL,
        "cli_agent": CLI_AGENT,
        "profile_path": str(agent_path),
        "profile_verified": True
    }


def verify_directories() -> dict[str, bool]:
    """Ensure required directories exist."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    SHARED_WORKSPACE.mkdir(parents=True, exist_ok=True)
    
    return {
        "state_dir": STATE_DIR.exists(),
        "evidence_dir": EVIDENCE_DIR.exists(),
        "workspace_dir": SHARED_WORKSPACE.exists(),
    }


def check_9router_connectivity() -> dict[str, Any]:
    """Check 9Router connectivity from inside the container."""
    import urllib.request
    import urllib.error
    
    url = "http://host.docker.internal:20128/v1/models"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m["id"] for m in data.get("data", [])]
            # Model can be either "agent-build" or "9router/agent-build"
            agent_build_present = "agent-build" in models or MODEL in models
            return {
                "reachable": True,
                "model_count": len(models),
                "agent_build_present": agent_build_present,
                "models": models[:10]  # First 10 for brevity
            }
    except urllib.error.URLError as e:
        return {
            "reachable": False,
            "error": str(e),
            "agent_build_present": False
        }


def verify_dashboard_runtime() -> dict[str, Any]:
    """Verify dashboard runtime file exists and has expected structure."""
    dashboard_file = STATE_DIR / "dashboard.json"
    if not dashboard_file.exists():
        return {"exists": False, "note": "Dashboard not started yet"}
    
    try:
        data = json.loads(dashboard_file.read_text(encoding="utf-8"))
        return {
            "exists": True,
            "url": data.get("url"),
            "port": data.get("port"),
            "token_present": "token=" in data.get("url", "")
        }
    except Exception as e:
        return {"exists": True, "error": str(e)}


def main() -> int:
    parser = argparse.ArgumentParser(description="G3 Offline Runtime Bootstrap")
    parser.add_argument("--verify-only", action="store_true", help="Only verify, don't initialize")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()
    
    env = os.environ.copy()
    env["AGENT_ORCHESTRATOR_HOME"] = str(STATE_DIR)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["OPENCODE_CONFIG"] = str(OPENCODE_CONFIG_FILE)
    env["OPENCODE_CONFIG_DIR"] = ""
    env["OPENCODE_DISABLE_PROJECT_CONFIG"] = "0"
    env["OPENCODE_DISABLE_AUTOUPDATE"] = "1"
    
    results: dict[str, Any] = {
        "bootstrap": "G3 offline runtime bootstrap",
        "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }
    
    try:
        # Verify directories
        results["directories"] = verify_directories()
        
        # Initialize workspace if not verify-only
        if not args.verify_only:
            initialized = init_workspace()
            results["workspace_initialized"] = initialized
        else:
            results["workspace_initialized"] = False
            results["workspace_exists"] = (SHARED_WORKSPACE / ".git").exists()
        
        # Prepare OpenCode config
        prepare_opencode_config()
        results["opencode_config"] = str(OPENCODE_CONFIG_FILE)
        
        # Verify agent profile
        results["agent_profile"] = verify_agent_profile()
        
        # Check 9Router connectivity (non-blocking for offline bootstrap)
        results["9router"] = check_9router_connectivity()
        
        # Verify dashboard runtime
        results["dashboard"] = verify_dashboard_runtime()
        
        # Verify runner doctor
        doctor_result = run_cmd([
            sys.executable, "-B", RUNNER_PATH, "doctor", "--config", CONFIG_PATH
        ], env=env)
        results["doctor"] = {
            "exit_code": doctor_result.returncode,
            "stdout": doctor_result.stdout[-500:] if doctor_result.stdout else "",
            "stderr": doctor_result.stderr[-500:] if doctor_result.stderr else ""
        }
        
        results["status"] = "READY"
        
    except Exception as e:
        results["status"] = "ERROR"
        results["error"] = f"{type(e).__name__}: {e}"
    
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(f"G3 Bootstrap Status: {results['status']}")
        if results.get("error"):
            print(f"Error: {results['error']}", file=sys.stderr)
            return 1
    
    return 0 if results.get("status") == "READY" else 1


if __name__ == "__main__":
    sys.exit(main())