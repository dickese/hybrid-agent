#!/usr/bin/env python3
"""G2 negative-path preflight: exercise the real OpenCode adapter without inference.

Launches the unmodified runner with the custom `opencode-9router` profile and a
deliberately nonexistent model route. OpenCode must reject the model locally
(`provider.no-route` / "Model unavailable") before any provider call. This proves
the full runner -> OpenCode -> workspace-agent wiring without spending tokens.

It also fails loudly if the workspace `bridge-build` agent is not discovered,
because that would surface as `Agent not found` instead.
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys

RUNNER = os.environ["RUNNER"]
CONFIG = os.environ["CONFIG"]
BASE = pathlib.Path(os.environ.get("G2_BASE", "/g2"))
WORKSPACE = BASE / "workspace"
TASK = pathlib.Path("/work/poc/g2_task.md")
PLAN = pathlib.Path("/work/poc/g2_plan.md")
STATE = BASE / "neg-state"
BAD_MODEL = "9router/__nonexistent__"


def prepare_opencode_config(env: dict[str, str]) -> None:
    """Mirror the real global OpenCode config, adapting only the container baseURL."""
    cfg_dir = pathlib.Path("/tmp/cfg")
    cfg_dir.mkdir(parents=True, exist_ok=True)
    source = pathlib.Path("/run/opencode-global.json").read_text(encoding="utf-8")
    adapted = source.replace(
        "http://127.0.0.1:20128/v1", "http://host.docker.internal:20128/v1"
    )
    (cfg_dir / "opencode.json").write_text(adapted, encoding="utf-8")
    shutil.copytree("/work/.opencode", cfg_dir / ".opencode", dirs_exist_ok=True)
    env["OPENCODE_CONFIG"] = str(cfg_dir / "opencode.json")
    env["OPENCODE_CONFIG_DIR"] = ""
    env["OPENCODE_DISABLE_PROJECT_CONFIG"] = "0"
    env["OPENCODE_DISABLE_AUTOUPDATE"] = "1"


def run(args, env, expect=0, timeout=240):
    proc = subprocess.run(
        [sys.executable, RUNNER, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    if proc.returncode != expect:
        raise AssertionError(
            f"rc={proc.returncode} expected {expect} for {' '.join(args)}\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    return proc


def jrun(args, env, expect=0, timeout=240):
    return json.loads(run(args + ["--json"], env, expect, timeout).stdout)


def git_status() -> str:
    proc = subprocess.run(
        ["git", "-C", str(WORKSPACE), "status", "--porcelain=v1", "--untracked-files=all"],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def main() -> int:
    env = os.environ.copy()
    env["AGENT_ORCHESTRATOR_HOME"] = str(STATE)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    prepare_opencode_config(env)

    before = git_status()
    if before:
        raise AssertionError(f"workspace must start clean:\n{before}")

    plan = jrun(
        [
            "create-plan",
            "--plan-file",
            str(PLAN),
            "--workspace",
            str(WORKSPACE),
            "--title",
            "G2 negative preflight",
            "--plan-id",
            "g2-neg",
            "--executor",
            f"opencode-9router={BAD_MODEL}",
            "--config",
            CONFIG,
        ],
        env,
    )
    launch = jrun(
        [
            "launch",
            "--cli",
            "opencode-9router",
            "--model",
            BAD_MODEL,
            "--cli-agent",
            "bridge-build",
            "--workspace",
            str(WORKSPACE),
            "--task-file",
            str(TASK),
            "--plan-id",
            "g2-neg",
            "--checklist-item",
            "item-001",
            "--config",
            CONFIG,
            "--allow-path",
            "src/**",
            "--allow-path",
            "tests/**",
            "--allow-path",
            ".opencode/**",
            "--max-changed-files",
            "10",
            "--timeout-seconds",
            "120",
            "--no-notify",
        ],
        env,
    )
    job_id = launch["job_id"]
    waited = run(
        ["wait", job_id, "--timeout-seconds", "180", "--poll-seconds", "1", "--json"],
        env,
        expect=1,
        timeout=220,
    )
    result = json.loads(waited.stdout)
    status = jrun(["status", job_id], env)

    job_dir = STATE / "jobs" / job_id
    stdout = (job_dir / "stdout.log").read_text(encoding="utf-8", errors="replace")
    stderr = (job_dir / "stderr.log").read_text(encoding="utf-8", errors="replace")
    combined = stdout + "\n" + stderr

    if "Agent not found" in combined:
        raise AssertionError(
            "workspace agent profile was not discovered; OpenCode reported Agent not found"
        )
    if "Model unavailable" not in combined and "no-route" not in combined:
        raise AssertionError(
            "expected a local model rejection before inference; output was:\n" + combined
        )

    after = git_status()
    if after:
        raise AssertionError(f"negative run dirtied the workspace:\n{after}")

    summary = {
        "check": "G2 negative-path adapter preflight",
        "status": "PASS",
        "job_id": job_id,
        "plan_id": plan["plan_id"],
        "state": result.get("state"),
        "acceptance_state": status.get("acceptance_state"),
        "model": status.get("model"),
        "cli": status.get("cli"),
        "cli_agent": status.get("cli_agent"),
        "agent_discovered": "Agent not found" not in combined,
        "local_model_rejection": "Model unavailable" in combined or "no-route" in combined,
        "workspace_clean_after": True,
        "inference_performed": False,
    }
    out_dir = BASE / "evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "g2_negative_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
