#!/usr/bin/env python3
"""G2 live verification for the Augani/agent-orchestrator PoC.

Runs the UNMODIFIED upstream runner with the custom `opencode-9router` profile
against the already-approved `9router/agent-build` route in a disposable
workspace. Performs one bounded inference call, then independently verifies the
files and tests, records an independent review, advances the plan, and checks
the upstream dashboard.

Refuses to run unless G2_AUTHORIZED=1. The 9Router key is read from a mounted
secret file and is never printed or written to evidence.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

RUNNER = os.environ["RUNNER"]
CONFIG = os.environ["CONFIG"]
BASE = pathlib.Path(os.environ.get("G2_BASE", "/g2"))
STATE = BASE / "state"
EVIDENCE = BASE / "evidence"
TASK = pathlib.Path("/work/poc/g2_task.md")
PLAN = pathlib.Path("/work/poc/g2_plan.md")

CLI = os.environ.get("G2_CLI", "opencode-9router")
MODEL = os.environ.get("G2_MODEL", "9router/agent-build")
CLI_AGENT = os.environ.get("G2_CLI_AGENT", "bridge-build")
TEST_CMD = [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-v"]

SUMMARY: dict = {
    "gate": "G2",
    "environment": "disposable Docker container (WSL2 backend)",
    "upstream_commit": "8d9b897c49500e8e1b54ec8028352544db95618d",
    "live_inference_performed": False,
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def prepare_workspace_and_config(env: dict[str, str]) -> pathlib.Path:
    """Create an isolated workspace in container tmpfs, copy .opencode agents, init git."""
    workspace = pathlib.Path("/tmp/g2-workspace")
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)
    (workspace / "README.md").write_text("# G2 disposable workspace\n", encoding="utf-8")
    (workspace / ".gitignore").write_text("__pycache__/\n*.pyc\n.pytest_cache/\n", encoding="utf-8")
    shutil.copytree("/work/.opencode", workspace / ".opencode", dirs_exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
    subprocess.run(["git", "config", "user.email", "poc@example.test"], cwd=workspace, check=True)
    subprocess.run(["git", "config", "user.name", "PoC"], cwd=workspace, check=True)
    subprocess.run(["git", "add", "-A"], cwd=workspace, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=workspace, check=True)

    cfg_dir = pathlib.Path("/tmp/cfg")
    cfg_dir.mkdir(parents=True, exist_ok=True)
    source = pathlib.Path("/run/opencode-global.json").read_text(encoding="utf-8")
    adapted = source.replace(
        "http://127.0.0.1:20128/v1", "http://host.docker.internal:20128/v1"
    )
    (cfg_dir / "opencode.json").write_text(adapted, encoding="utf-8")
    env["OPENCODE_CONFIG"] = str(cfg_dir / "opencode.json")
    env["OPENCODE_CONFIG_DIR"] = ""
    env["OPENCODE_DISABLE_PROJECT_CONFIG"] = "0"
    env["OPENCODE_DISABLE_AUTOUPDATE"] = "1"
    return workspace


def load_secret(env: dict[str, str]) -> None:
    secret = pathlib.Path("/run/secrets/9router.key")
    if secret.is_file():
        env["NINE_ROUTER_KEY"] = secret.read_text(encoding="utf-8").strip()
    if not env.get("NINE_ROUTER_KEY"):
        raise RuntimeError("NINE_ROUTER_KEY is not available")


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


def git_status(ws: pathlib.Path) -> list[str]:
    proc = subprocess.run(
        ["git", "-C", str(ws), "status", "--porcelain=v1", "--untracked-files=all"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in proc.stdout.splitlines() if line.strip()]


def changed_paths(lines: list[str]) -> list[str]:
    paths = []
    for line in lines:
        value = line[3:] if len(line) > 3 else line
        if " -> " in value:
            value = value.split(" -> ", 1)[1]
        paths.append(value.strip().strip('"'))
    return sorted(paths)


def capture_failure(job_id: str, env: dict[str, str]) -> dict:
    info: dict = {"job_id": job_id}
    try:
        info["status"] = jrun(["status", job_id], env)
    except Exception as exc:  # noqa: BLE001
        info["status_error"] = f"{type(exc).__name__}: {exc}"
    job_dir = STATE / "jobs" / job_id
    for name in ("stdout.log", "stderr.log", "runner.log"):
        path = job_dir / name
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            info[name] = text[-4000:]
    return info


def independent_assertions(ws: pathlib.Path) -> int:
    code = r"""
import sys
sys.path.insert(0, "src")
from slugify import slugify

cases = [
    ("Hello, World!", "hello-world"),
    ("  Multiple   spaces  ", "multiple-spaces"),
    ("Caf\u00e9 D\u00e9j\u00e0 Vu", "cafe-deja-vu"),
    ("Python 3.11", "python-3-11"),
    ("A_B.C", "a-b-c"),
    ("\u00dcber Cool", "uber-cool"),
    ("---", ""),
    ("", ""),
]
for source, expected in cases:
    actual = slugify(source)
    assert actual == expected, f"{source!r}: got {actual!r}, expected {expected!r}"
print("INDEPENDENT_ASSERTIONS_OK", len(cases))
"""
    proc = subprocess.run(
        [sys.executable, "-B", "-c", code],
        cwd=ws,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0:
        raise AssertionError(f"independent assertions failed:\n{proc.stdout}\n{proc.stderr}")
    match = re.search(r"INDEPENDENT_ASSERTIONS_OK (\d+)", proc.stdout)
    if not match:
        raise AssertionError(f"independent assertion marker missing:\n{proc.stdout}")
    return int(match.group(1))


def dashboard_check(job_id: str, env: dict[str, str]) -> dict:
    proc = subprocess.Popen(
        [sys.executable, RUNNER, "dashboard-web", "--no-open", "--port", "0"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        line = proc.stdout.readline()
        match = re.search(r"(http://127\.0\.0\.1:(\d+)/#token=([A-Za-z0-9_-]+))", line)
        if not match:
            raise AssertionError(f"no dashboard url line: {line!r}")
        port, token = match.group(2), match.group(3)
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/overview",
            headers={"X-Orchestrator-Token": token},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            status = resp.status
        payload = json.loads(raw)
        unauth = None
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/overview", timeout=5)
            unauth = "unexpected-200"
        except urllib.error.HTTPError as exc:
            unauth = exc.code
        if status != 200 or unauth != 401:
            raise AssertionError(f"dashboard auth mismatch: status={status} unauth={unauth}")
        if not payload.get("projects"):
            raise AssertionError("dashboard overview has no projects")
        if job_id not in raw:
            raise AssertionError("dashboard overview does not expose the live job id")
        return {
            "status": status,
            "unauth_status": unauth,
            "project_count": len(payload["projects"]),
            "job_id_present": True,
        }
    finally:
        proc.terminate()
        try:
            proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def main() -> int:
    if os.environ.get("G2_AUTHORIZED") != "1":
        raise SystemExit(
            "Refusing to run: set G2_AUTHORIZED=1 only after explicit user approval for one live inference call."
        )

    env = os.environ.copy()
    env["AGENT_ORCHESTRATOR_HOME"] = str(STATE)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    workspace = prepare_workspace_and_config(env)
    # Try to force OpenCode to use the workspace as project directory
    env["OPENCODE_PROJECT_DIR"] = str(workspace)
    env["OPENCODE_CWD"] = str(workspace)
    load_secret(env)

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    SUMMARY["started_at"] = utc_now()
    SUMMARY["route"] = {"cli": CLI, "model": MODEL, "cli_agent": CLI_AGENT}
    SUMMARY["workspace"] = str(workspace)
    SUMMARY["state_home"] = str(STATE)

    version = subprocess.run(
        ["opencode", "--version"], env=env, capture_output=True, text=True, timeout=30
    )
    SUMMARY["opencode_version"] = (version.stdout or version.stderr).strip()
    SUMMARY["python_version"] = sys.version.split()[0]

    # load_secret must be called before this check so NINE_ROUTER_KEY is available
    models = subprocess.run(
        ["opencode", "models"], env=env, capture_output=True, text=True, timeout=60
    )
    if MODEL not in models.stdout.splitlines():
        raise AssertionError(f"approved route {MODEL} is not listed by the worker environment")

    before = git_status(workspace)
    if before:
        raise AssertionError(f"workspace must start clean:\n" + "\n".join(before))

    plan = jrun(
        [
            "create-plan",
            "--plan-file",
            str(PLAN),
            "--workspace",
            str(workspace),
            "--title",
            "G2 live bounded change",
            "--plan-id",
            "g2",
            "--executor",
            f"{CLI}={MODEL}",
            "--config",
            CONFIG,
        ],
        env,
    )
    SUMMARY["plan"] = {
        "plan_id": plan["plan_id"],
        "counts_before": plan["counts"],
        "items": len(plan["items"]),
    }

    started = time.monotonic()
    launch = jrun(
        [
            "launch",
            "--cli",
            CLI,
            "--model",
            MODEL,
            "--cli-agent",
            CLI_AGENT,
            "--workspace",
            str(workspace),
            "--task-file",
            str(TASK),
            "--plan-id",
            "g2",
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
            "600",
            "--no-notify",
        ],
        env,
    )
    job_id = launch["job_id"]
    SUMMARY["job_id"] = job_id
    SUMMARY["live_inference_performed"] = True

    waited = subprocess.run(
        [
            sys.executable,
            RUNNER,
            "wait",
            job_id,
            "--timeout-seconds",
            "660",
            "--poll-seconds",
            "2",
            "--json",
        ],
        capture_output=True,
        text=True,
        timeout=700,
        env=env,
    )
    result = json.loads(waited.stdout) if waited.stdout.strip() else {}
    SUMMARY["duration_seconds"] = round(time.monotonic() - started, 1)
    SUMMARY["terminal_state"] = result.get("state")
    if waited.returncode != 0 or result.get("state") != "succeeded":
        SUMMARY["failure"] = capture_failure(job_id, env)
        raise AssertionError(f"live job did not succeed: state={result.get('state')}")

    status = jrun(["status", job_id], env)
    for key, expected in (("cli", CLI), ("model", MODEL), ("cli_agent", CLI_AGENT)):
        if status.get(key) != expected:
            raise AssertionError(f"job {key}={status.get(key)!r}, expected {expected!r}")
    if status.get("acceptance_state") != "awaiting_review":
        raise AssertionError(f"unexpected acceptance state: {status.get('acceptance_state')}")
    SUMMARY["job_status_before_review"] = {
        "state": status.get("state"),
        "acceptance_state": status.get("acceptance_state"),
        "current_phase": status.get("current_phase"),
        "cli": status.get("cli"),
        "model": status.get("model"),
        "cli_agent": status.get("cli_agent"),
    }

    lines = git_status(workspace)
    paths = changed_paths(lines)
    SUMMARY["changed_paths"] = paths
    allowed_prefixes = ("src/", "tests/", ".opencode/")
    out_of_scope = [p for p in paths if not p.startswith(allowed_prefixes)]
    if out_of_scope:
        raise AssertionError(f"out-of-scope paths changed: {out_of_scope}")
    for required in ("src/slugify.py", "tests/__init__.py", "tests/test_slugify.py"):
        if not (workspace / required).is_file():
            raise AssertionError(f"required file missing: {required}")
    source_text = (workspace / "src" / "slugify.py").read_text(encoding="utf-8")
    tests_text = (workspace / "tests" / "test_slugify.py").read_text(encoding="utf-8")
    if "def slugify(" not in source_text:
        raise AssertionError("src/slugify.py does not define slugify")
    if "unittest" not in tests_text:
        raise AssertionError("tests/test_slugify.py does not use unittest")

    test_proc = subprocess.run(
        TEST_CMD, cwd=workspace, env=env, capture_output=True, text=True, timeout=120
    )
    test_output = test_proc.stdout + test_proc.stderr
    SUMMARY["tests"] = {
        "command": "python -B -m unittest discover -s tests -t . -v",
        "returncode": test_proc.returncode,
        "ran": (re.search(r"Ran (\d+) tests?", test_output) or [None, None])[1],
        "ok": test_proc.returncode == 0 and "OK" in test_output,
    }
    if not SUMMARY["tests"]["ok"]:
        raise AssertionError(f"deterministic tests failed:\n{test_output}")

    SUMMARY["independent_assertion_count"] = independent_assertions(workspace)

    review = jrun(
        [
            "record-review",
            job_id,
            "--verdict",
            "accepted",
            "--reviewer",
            "codex-poc-independent",
            "--test",
            f"{' '.join(TEST_CMD)}: OK (Ran {SUMMARY['tests']['ran']} tests)",
            "--notes",
            "Independent coordinator verification: scoped files only, deterministic tests pass, no out-of-scope changes.",
        ],
        env,
    )
    SUMMARY["review"] = {
        "verdict": review.get("verdict"),
        "reviewer": review.get("reviewer"),
        "tests": review.get("tests"),
    }

    after = jrun(["status", job_id], env)
    if after.get("acceptance_state") != "accepted":
        raise AssertionError(f"review did not accept: {after.get('acceptance_state')}")
    plan_after = jrun(["plan-status", "g2"], env)
    SUMMARY["plan_after"] = {
        "complete": plan_after.get("complete"),
        "counts": plan_after.get("counts"),
        "item_state": plan_after["items"][0]["state"],
    }
    if not plan_after.get("complete") or plan_after["items"][0]["state"] != "done":
        raise AssertionError("plan did not advance after acceptance")

    SUMMARY["dashboard"] = dashboard_check(job_id, env)
    SUMMARY["finished_at"] = utc_now()
    SUMMARY["status"] = "LIVE_PASS"

    (EVIDENCE / "g2_live_summary.json").write_text(
        json.dumps(SUMMARY, indent=2), encoding="utf-8"
    )
    print(json.dumps(SUMMARY, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        SUMMARY["status"] = "LIVE_FAIL"
        SUMMARY["error"] = f"{type(exc).__name__}: {exc}"
        SUMMARY["finished_at"] = utc_now()
        try:
            EVIDENCE.mkdir(parents=True, exist_ok=True)
            (EVIDENCE / "g2_live_failure.json").write_text(
                json.dumps(SUMMARY, indent=2), encoding="utf-8"
            )
        except Exception:  # noqa: BLE001
            pass
        print(json.dumps(SUMMARY, indent=2))
        sys.exit(2)
