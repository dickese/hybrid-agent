#!/usr/bin/env python3
"""G1 offline workflow verification for Augani/agent-orchestrator v0.7.1.

Runs the UNMODIFIED upstream runner (cli_agent_job.py) against a deterministic
fake worker via the custom CLI profile mechanism. All state lives under a
disposable directory. No network, no inference, no Codex.

Prints a JSON evidence summary to stdout.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

RUNNER = os.environ["RUNNER"]
BASE = Path(os.environ.get("G1_BASE", tempfile.mkdtemp(prefix="g1-")))
BASE.mkdir(parents=True, exist_ok=True)
RESULTS: list[dict] = []


def record(name: str, status: str, detail: str) -> None:
    RESULTS.append({"check": name, "status": status, "detail": detail})
    print(f"[{status}] {name}: {detail}", flush=True)


SCENARIOS: list = []


def check(name: str):
    def deco(fn):
        def wrapper():
            try:
                detail = fn()
                record(name, "PASS", detail or "ok")
            except Exception as exc:  # noqa: BLE001
                record(name, "FAIL", f"{type(exc).__name__}: {exc}")
        SCENARIOS.append(wrapper)
        return wrapper
    return deco


def run(args, env, expect=0, timeout=90):
    proc = subprocess.run(
        [sys.executable, RUNNER, *args],
        env=env, capture_output=True, text=True, timeout=timeout,
    )
    if proc.returncode != expect:
        raise AssertionError(
            f"rc={proc.returncode} expected {expect} for {' '.join(args)}\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    return proc


def new_env(state_dir: Path) -> dict:
    env = os.environ.copy()
    env["AGENT_ORCHESTRATOR_HOME"] = str(state_dir)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


TASK_SECTIONS = (
    "Objective", "Why", "Scope", "Files to inspect", "Implementation guidance",
    "Constraints", "Acceptance criteria", "Validation", "Final report",
)


def write_task(path: Path) -> None:
    path.write_text(
        "\n\n".join(f"# {h}\nDeterministic detail for {h}." for h in TASK_SECTIONS),
        encoding="utf-8",
    )


def write_plan(path: Path, item_title: str = "Implement and verify the bounded change.") -> None:
    path.write_text(
        "# Goal\nShip the bounded feature.\n\n"
        "# Decisions and assumptions\nUse the public runner contract.\n\n"
        "# Constraints and guardrails\nDo not publish or change credentials.\n\n"
        f"# Checklist\n- [ ] {item_title}\n\n"
        "# Validation strategy\nRun the focused tests.\n\n"
        "# Completion criteria\nReview accepted with test evidence.\n",
        encoding="utf-8",
    )


def make_workspace(root: Path, git: bool = True) -> Path:
    ws = root / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    if git:
        subprocess.run(["git", "init", "-q", str(ws)], check=True)
        subprocess.run(["git", "-C", str(ws), "config", "user.email", "poc@example.test"], check=True)
        subprocess.run(["git", "-C", str(ws), "config", "user.name", "PoC"], check=True)
        (ws / "seed.txt").write_text("seed\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(ws), "add", "seed.txt"], check=True)
        subprocess.run(["git", "-C", str(ws), "commit", "-qm", "seed"], check=True)
    return ws


FAKE_WORKER = r'''
import os, sys, time, pathlib, subprocess
mode = sys.argv[1]
prompt = pathlib.Path(sys.argv[2]).read_text(encoding="utf-8")
channel = prompt.split("python3 ", 1)[1].split(" event", 1)[0].strip()
def ev(phase, msg):
    subprocess.run([sys.executable, channel, "event", "--phase", phase, "--message", msg], check=False)
if mode == "ok":
    ev("implementation", "writing bounded output")
    pathlib.Path("output.txt").write_text("bounded change complete\n", encoding="utf-8")
    print("OK wrote output.txt")
elif mode == "sleep":
    ev("implementation", "sleeping for single-writer test")
    time.sleep(60)
    print("SLEEP done")
elif mode == "fail":
    ev("implementation", "intentional failure")
    print("FAIL intentional", file=sys.stderr)
    sys.exit(1)
elif mode == "ask":
    ev("implementation", "needs clarification")
    r = subprocess.run([sys.executable, channel, "ask", "--question", "Which mode should I use?", "--wait-seconds", "30"], capture_output=True, text=True)
    pathlib.Path("answer.txt").write_text((r.stdout or "").strip() + "\n", encoding="utf-8")
    print("ANSWER=" + (r.stdout or "").strip())
elif mode == "scope":
    ev("implementation", "writing out of scope then sleeping")
    pathlib.Path("outside.txt").write_text("drift\n", encoding="utf-8")
    time.sleep(10)
    print("SCOPE done")
'''


def build_config(root: Path) -> Path:
    (root / "fake_worker.py").write_text(FAKE_WORKER, encoding="utf-8")
    fw = str(root / "fake_worker.py")
    agents = {
        name: {
            "argv": [sys.executable, fw, mode, "{prompt_file}"],
            "prompt_transport": "file",
        }
        for name, mode in {
            "fake-ok": "ok", "fake-sleep": "sleep", "fake-fail": "fail",
            "fake-ask": "ask", "fake-scope": "scope",
        }.items()
    }
    cfg = root / "agents.json"
    cfg.write_text(json.dumps({"agents": agents}), encoding="utf-8")
    return cfg


def launch(args, env):
    p = run(args + ["--json"], env)
    return json.loads(p.stdout)["job_id"]


def wait_job(job_id, env, timeout=40, expect=0):
    p = run(["wait", job_id, "--timeout-seconds", str(timeout), "--poll-seconds", "0.2", "--json"], env, expect=expect)
    return json.loads(p.stdout)


def status(job_id, env):
    return json.loads(run(["status", job_id, "--json"], env).stdout)


def main() -> int:
    print(f"RUNNER={RUNNER}\nBASE={BASE}\n", flush=True)
    CFG = build_config(BASE)
    task = BASE / "task.md"; write_task(task)
    plan = BASE / "plan.md"; write_plan(plan)

    # ---------------- Scenario A: core flow ----------------
    @check("A1 durable plan creation")
    def _():
        root = BASE / "A"; root.mkdir()
        env = new_env(root / "state")
        p = run(["create-plan", "--plan-file", str(plan), "--workspace", str(make_workspace(root)),
                 "--title", "Core flow", "--plan-id", "core", "--executor", "fake-ok",
                 "--config", str(CFG), "--json"], env)
        data = json.loads(p.stdout)
        assert data["plan_id"] == "core"
        assert data["counts"] == {"pending": 1}, data["counts"]
        assert data["items"][0]["state"] == "pending"
        assert (root / "state" / "plans" / "core" / "plan.json").is_file()
        return f"plan persisted; items={len(data['items'])}"

    @check("A2 job execution + structured progress + persistent logs")
    def _():
        root = BASE / "A"; env = new_env(root / "state")
        ws = root / "workspace"
        jid = launch(["launch", "--cli", "fake-ok", "--workspace", str(ws),
                      "--task-file", str(task), "--plan-id", "core", "--checklist-item", "item-001",
                      "--config", str(CFG), "--no-notify"], env)
        st = wait_job(jid, env)
        assert st["state"] == "succeeded", st["state"]
        job = root / "state" / "jobs" / jid
        assert (job / "meta.json").is_file() and (job / "result.json").is_file()
        assert (ws / "output.txt").read_text().strip() == "bounded change complete"
        events = []
        for d in (job / "events", job / "channel" / "events"):
            if d.is_dir():
                events += [json.loads(f.read_text()) for f in d.glob("*.json")]
        progress = [e for e in events if e.get("type") == "worker_progress"]
        assert progress, "no worker_progress events"
        assert progress[-1]["phase"] == "implementation"
        assert st["current_phase"] == "implementation", st.get("current_phase")
        assert "OK wrote output.txt" in (job / "stdout.log").read_text()
        return f"job={jid} events={len(events)} phase={st['current_phase']}"

    @check("A3 review gate: accept requires test evidence, plan advances, immutable")
    def _():
        root = BASE / "A"; env = new_env(root / "state")
        jid = status_dir = None
        # find the job bound to core
        jobs = list((root / "state" / "jobs").iterdir())
        jid = jobs[0].name
        st = status(jid, env)
        assert st["acceptance_state"] == "awaiting_review", st["acceptance_state"]
        run(["record-review", jid, "--verdict", "accepted", "--reviewer", "poc",
             "--notes", "no test", "--json"], env, expect=2)
        run(["record-review", jid, "--verdict", "accepted", "--reviewer", "poc",
             "--test", "python3 -m unittest: PASS", "--notes", "diff ok", "--json"], env)
        st2 = status(jid, env)
        assert st2["acceptance_state"] == "accepted", st2["acceptance_state"]
        planp = json.loads(run(["plan-status", "core", "--json"], env).stdout)
        assert planp["complete"] is True and planp["items"][0]["state"] == "done"
        run(["record-review", jid, "--verdict", "accepted", "--reviewer", "poc",
             "--test", "again", "--notes", "again", "--json"], env, expect=2)
        return "accept gated by --test; plan complete; re-review rejected"

    @check("A4 coordinator-restart state recovery (fresh process reads disk)")
    def _():
        root = BASE / "A"; env = new_env(root / "state")
        cp = json.loads(run(["plan-checkpoint", "core", "--json"], env).stdout)
        assert cp["complete"] is True
        assert cp["counts"].get("done") == 1, cp["counts"]
        return f"checkpoint complete={cp['complete']} counts={cp['counts']}"

    # ---------------- Scenario B: project mode / no worktrees ----------------
    @check("B1 project mode captured; no extra worktrees created")
    def _():
        root = BASE / "B"; root.mkdir()
        env = new_env(root / "state")
        ws = make_workspace(root)
        run(["preferences", "--workspace-mode", "project", "--json"], env)
        p = run(["create-plan", "--plan-file", str(plan), "--workspace", str(ws),
                 "--title", "Project", "--plan-id", "proj", "--executor", "fake-ok",
                 "--config", str(CFG), "--json"], env)
        data = json.loads(p.stdout)
        assert data["workspace_mode"] == "project", data["workspace_mode"]
        wt = subprocess.run(["git", "-C", str(ws), "worktree", "list", "--porcelain"],
                            capture_output=True, text=True, check=True).stdout
        assert wt.count("worktree ") == 1, wt
        assert not (ws / ".git" / "worktrees").exists() or not any((ws / ".git" / "worktrees").iterdir())
        return "workspace_mode=project; worktree count=1"

    # ---------------- Scenario C: single-writer + cancel ----------------
    @check("C1 single-writer protection rejects concurrent writer")
    def _():
        root = BASE / "C"; root.mkdir()
        env = new_env(root / "state")
        ws = make_workspace(root)
        jid = launch(["launch", "--cli", "fake-sleep", "--approved-executor", "fake-sleep",
                      "--workspace", str(ws), "--task-file", str(task), "--config", str(CFG),
                      "--no-notify", "--timeout-seconds", "60"], env)
        time.sleep(1.5)
        p = run(["launch", "--cli", "fake-ok", "--approved-executor", "fake-ok",
                 "--workspace", str(ws), "--task-file", str(task), "--config", str(CFG),
                 "--no-notify"], env, expect=2)
        assert "already writing this workspace" in p.stderr, p.stderr
        # cleanup: cancel the sleep job
        run(["cancel", jid, "--json"], env)
        deadline = time.time() + 15
        while time.time() < deadline:
            if status(jid, env)["state"] in ("cancelled", "failed", "lost"):
                break
            time.sleep(0.5)
        return f"second launch rejected; sleeper={status(jid, env)['state']}"

    @check("C2 process termination via cancel")
    def _():
        root = BASE / "C"; env = new_env(root / "state")
        jobs = [p.name for p in (root / "state" / "jobs").iterdir()]
        jid = jobs[0]
        st = status(jid, env)
        assert st["state"] == "cancelled", st["state"]
        return f"job={jid} state=cancelled"

    # ---------------- Scenario D: timeout ----------------
    @check("D1 timeout handling terminates worker as timed_out")
    def _():
        root = BASE / "D"; root.mkdir()
        env = new_env(root / "state")
        ws = make_workspace(root)
        jid = launch(["launch", "--cli", "fake-sleep", "--approved-executor", "fake-sleep",
                      "--workspace", str(ws), "--task-file", str(task), "--config", str(CFG),
                      "--no-notify", "--timeout-seconds", "3"], env)
        st = wait_job(jid, env, timeout=30, expect=1)
        assert st["state"] == "timed_out", st["state"]
        assert st["timed_out"] is True
        return f"state=timed_out after {st.get('duration_seconds')}s"

    # ---------------- Scenario E: review reject -> blocked ----------------
    @check("E1 rejected review blocks plan item")
    def _():
        root = BASE / "E"; root.mkdir()
        env = new_env(root / "state")
        ws = make_workspace(root)
        run(["create-plan", "--plan-file", str(plan), "--workspace", str(ws),
             "--title", "Reject", "--plan-id", "rej", "--executor", "fake-ok",
             "--config", str(CFG), "--json"], env)
        jid = launch(["launch", "--cli", "fake-ok", "--workspace", str(ws), "--task-file", str(task),
                      "--plan-id", "rej", "--checklist-item", "item-001", "--config", str(CFG),
                      "--no-notify"], env)
        wait_job(jid, env)
        run(["record-review", jid, "--verdict", "rejected", "--reviewer", "poc",
             "--notes", "regression found", "--json"], env)
        planp = json.loads(run(["plan-status", "rej", "--json"], env).stdout)
        assert planp["items"][0]["state"] == "blocked", planp["items"][0]["state"]
        return "item blocked after rejection"

    # ---------------- Scenario F: retry limit ----------------
    @check("F1 per-item retry limit enforced (max_attempts_per_item=3)")
    def _():
        root = BASE / "F"; root.mkdir()
        env = new_env(root / "state")
        ws = make_workspace(root)
        run(["create-plan", "--plan-file", str(plan), "--workspace", str(ws),
             "--title", "Retry", "--plan-id", "retry", "--executor", "fake-fail",
             "--config", str(CFG), "--json"], env)
        for i in range(3):
            jid = launch(["launch", "--cli", "fake-fail", "--workspace", str(ws), "--task-file", str(task),
                          "--plan-id", "retry", "--checklist-item", "item-001", "--config", str(CFG),
                          "--no-notify"], env)
            st = wait_job(jid, env, expect=1)
            assert st["state"] == "failed", (i, st["state"])
        p = run(["launch", "--cli", "fake-fail", "--workspace", str(ws), "--task-file", str(task),
                 "--plan-id", "retry", "--checklist-item", "item-001", "--config", str(CFG),
                 "--no-notify"], env, expect=2)
        assert "3-attempt limit" in p.stderr, p.stderr
        return "4th attempt rejected at 3-attempt limit"

    # ---------------- Scenario G: human ask round-trip ----------------
    @check("G1 worker question -> human answer round-trip")
    def _():
        root = BASE / "G"; root.mkdir()
        env = new_env(root / "state")
        ws = make_workspace(root)
        jid = launch(["launch", "--cli", "fake-ask", "--approved-executor", "fake-ask",
                      "--workspace", str(ws), "--task-file", str(task), "--config", str(CFG),
                      "--no-notify"], env)
        q = None
        deadline = time.time() + 20
        while time.time() < deadline:
            vals = json.loads(run(["questions", jid, "--json"], env).stdout)
            if vals:
                q = vals[0]; break
            time.sleep(0.3)
        assert q is not None, "no pending question appeared"
        run(["answer", jid, q["id"], "--text", "Use strict mode.", "--json"], env)
        st = wait_job(jid, env, timeout=30)
        assert st["state"] == "succeeded", st["state"]
        assert "ANSWER=Use strict mode." in (root / "state" / "jobs" / jid / "stdout.log").read_text()
        return f"question answered; worker resumed -> {st['state']}"

    # ---------------- Scenario H: orchestrator feedback round-trip ----------------
    @check("H1 orchestrator feedback request -> answer lifecycle")
    def _():
        root = BASE / "H"; root.mkdir()
        env = new_env(root / "state")
        ws = make_workspace(root)
        run(["request-feedback", "--workspace", str(ws), "--question", "Which scope?",
             "--feedback-id", "fb1", "--no-notify", "--json"], env)
        pend = json.loads(run(["feedback", "--json"], env).stdout)
        assert len(pend) == 1 and pend[0]["state"] == "pending", pend
        run(["answer-feedback", "fb1", "--text", "Minimal scope.", "--json"], env)
        assert json.loads(run(["feedback", "--json"], env).stdout) == []
        hist = json.loads(run(["feedback", "--all", "--json"], env).stdout)
        assert hist[0]["answer"] == "Minimal scope."
        return "feedback answered; history persisted"

    # ---------------- Scenario I: dependencies ----------------
    @check("I1 checklist dependency gated on independent acceptance")
    def _():
        root = BASE / "I"; root.mkdir()
        env = new_env(root / "state")
        ws = make_workspace(root)
        a = launch(["launch", "--cli", "fake-ok", "--approved-executor", "fake-ok",
                    "--workspace", str(ws), "--task-file", str(task), "--config", str(CFG),
                    "--no-notify"], env)
        wait_job(a, env)
        p = run(["launch", "--cli", "fake-ok", "--approved-executor", "fake-ok",
                 "--workspace", str(ws), "--task-file", str(task), "--config", str(CFG),
                 "--depends-on", a, "--no-notify"], env, expect=2)
        assert "only after it is independently accepted" in p.stderr, p.stderr
        run(["record-review", a, "--verdict", "accepted", "--reviewer", "poc",
             "--test", "PASS", "--notes", "ok", "--json"], env)
        b = launch(["launch", "--cli", "fake-ok", "--approved-executor", "fake-ok",
                    "--workspace", str(ws), "--task-file", str(task), "--config", str(CFG),
                    "--depends-on", a, "--allow-dirty", "--no-notify"], env)
        st = wait_job(b, env)
        assert st["state"] == "succeeded"
        return f"dep {a} blocked until accepted; then {b} succeeded"

    # ---------------- Scenario J: scope violation ----------------
    @check("J1 unsafe scope change detected and worker stopped")
    def _():
        root = BASE / "J"; root.mkdir()
        env = new_env(root / "state")
        ws = make_workspace(root)
        jid = launch(["launch", "--cli", "fake-scope", "--approved-executor", "fake-scope",
                      "--workspace", str(ws), "--task-file", str(task), "--config", str(CFG),
                      "--allow-path", "allowed/**", "--allow-unstructured-task",
                      "--no-notify"], env)
        st = wait_job(jid, env, timeout=30, expect=1)
        assert st["state"] == "scope_violated", st["state"]
        assert any("outside.txt" in v for v in st["scope_violations"]), st["scope_violations"]
        return f"state=scope_violated violations={st['scope_violations']}"

    # ---------------- Scenario K: dashboard ----------------
    @check("K1 dashboard serves authenticated overview")
    def _():
        root = BASE / "A"; env = new_env(root / "state")
        proc = subprocess.Popen(
            [sys.executable, RUNNER, "dashboard-web", "--no-open", "--port", "0"],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        try:
            line = proc.stdout.readline()
            m = re.search(r"(http://127\.0\.0\.1:(\d+)/#token=([A-Za-z0-9_-]+))", line)
            assert m, f"no url line: {line!r}"
            port, token = m.group(2), m.group(3)
            req = urllib.request.Request(f"http://127.0.0.1:{port}/api/overview",
                                         headers={"X-Orchestrator-Token": token})
            with urllib.request.urlopen(req, timeout=5) as resp:
                assert resp.status == 200, resp.status
                body = json.loads(resp.read())
            assert "projects" in body and body["projects"], body
            # unauthenticated must be 401
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/api/overview", timeout=5)
                raise AssertionError("unauthenticated request unexpectedly succeeded")
            except urllib.error.HTTPError as e:
                assert e.code == 401, e.code
            return f"port={port} projects={len(body['projects'])} auth=200/401"
        finally:
            proc.terminate()
            try:
                proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    for scenario in SCENARIOS:
        scenario()

    passed = sum(1 for r in RESULTS if r["status"] == "PASS")
    failed = sum(1 for r in RESULTS if r["status"] == "FAIL")
    summary = {"gate": "G1", "runner": RUNNER, "base": str(BASE),
               "passed": passed, "failed": failed, "results": RESULTS}
    print("\n==== G1 SUMMARY ====")
    print(json.dumps(summary, indent=2))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
