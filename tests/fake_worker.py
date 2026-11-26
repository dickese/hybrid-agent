"""Deterministic fake OpenCode worker for bridge tests.

This file is test-only.  It emits the same NDJSON envelope shape observed from
OpenCode v2.2.0 and performs controlled fixture edits.  It never touches the
network or credentials.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

SESSION = os.environ.get(
    "BRIDGE_FAKE_SESSION", "ses_fake000000000000000000000000"
)
SCENARIO = os.environ.get("BRIDGE_FAKE_SCENARIO", "success")
WORKSPACE = Path.cwd()


def emit(event_type: str, part: dict, *, session: str | None = SESSION) -> None:
    payload = {
        "type": event_type,
        "timestamp": int(time.time() * 1000),
        "part": part,
    }
    if session is not None:
        payload["sessionID"] = session
        part.setdefault("sessionID", session)
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def text(value: str, *, session: str | None = SESSION) -> None:
    emit("text", {"type": "text", "text": value}, session=session)


def step_start() -> None:
    emit("step_start", {"type": "step-start"})


def step_finish(reason: str = "stop") -> None:
    emit("step_finish", {"type": "step-finish", "reason": reason})


def tool(name: str, input_data: dict, output: str, status: str = "completed") -> None:
    emit(
        "tool_use",
        {
            "type": "tool",
            "tool": name,
            "state": {
                "status": status,
                "input": input_data,
                "output": output,
                "title": name,
            },
        },
    )


def write_add() -> None:
    (WORKSPACE / "add.py").write_text(
        "def add(a, b): return a + b\n", encoding="utf-8"
    )


def main() -> int:
    step_start()
    if SCENARIO == "success":
        text("Inspecting the fixture.")
        tool("read", {"path": str(WORKSPACE / "add.py")}, "read add.py")
        write_add()
        tool(
            "edit",
            {"path": str(WORKSPACE / "add.py"), "oldString": "a - b", "newString": "a + b"},
            "Edited add.py",
        )
        tool(
            "shell",
            {"command": "python -B test_add.py", "workdir": str(WORKSPACE)},
            "(no output)",
        )
        step_finish()
        text("Fixed add.py; the approved test command passed.")
        return 0
    if SCENARIO == "read_success":
        text("add.py subtracts instead of adding; the test therefore fails.")
        tool("read", {"path": str(WORKSPACE / "add.py")}, "read add.py")
        step_finish()
        text("Diagnosis complete. No files changed.")
        return 0
    if SCENARIO == "no_changes":
        step_finish()
        text("No changes were necessary.")
        return 0
    if SCENARIO == "scope_violation":
        write_add()
        (WORKSPACE / "test_add.py").write_text(
            "from add import add; assert add(2, 3) == 5\n# tampered\n",
            encoding="utf-8",
        )
        tool(
            "edit",
            {"path": str(WORKSPACE / "test_add.py")},
            "Edited test_add.py",
        )
        step_finish()
        text("Edited both add.py and test_add.py.")
        return 0
    if SCENARIO == "read_edit_attempt":
        tool(
            "edit",
            {"path": str(WORKSPACE / "add.py")},
            "Permission denied",
            status="error",
        )
        step_finish()
        text("I attempted an edit but it was denied.")
        return 0
    if SCENARIO == "malformed":
        print("{this is not valid JSON", flush=True)
        step_finish()
        text("Malformed output followed by a plausible summary.")
        return 0
    if SCENARIO == "error_event":
        emit(
            "error",
            {
                "type": "error",
                "error": {"message": "synthetic worker error"},
            },
        )
        return 0
    if SCENARIO == "nonzero":
        step_finish()
        text("Synthetic non-zero exit.")
        return 7
    if SCENARIO == "auth_error":
        step_finish()
        text("The provider rejected the request.")
        print("401 Unauthorized: Missing API key", file=sys.stderr, flush=True)
        return 1
    if SCENARIO == "transient":
        step_finish()
        text("The provider is rate limited.")
        print("429 Too Many Requests", file=sys.stderr, flush=True)
        return 1
    if SCENARIO == "timeout":
        text("Starting a deliberately slow operation.")
        time.sleep(120)
        step_finish()
        text("This should never be reached.")
        return 0
    if SCENARIO == "no_session":
        text("A response without a session id.", session=None)
        step_finish()
        return 0
    if SCENARIO == "no_activity":
        return 0
    if SCENARIO == "secret":
        step_finish()
        text("The fake credential is sk-TESTONLY1234567890ABCDEF and must be redacted.")
        return 0
    if SCENARIO == "secret_in_diff":
        (WORKSPACE / "add.py").write_text(
            "# sk-TESTONLY1234567890ABCDEF\ndef add(a, b): return a + b\n",
            encoding="utf-8",
        )
        step_finish()
        text("Wrote a file containing a credential-shaped string.")
        return 0
    if SCENARIO == "hold_success":
        text("Holding the repository lock for a concurrency drill.")
        time.sleep(4)
        write_add()
        tool("edit", {"path": str(WORKSPACE / "add.py")}, "Edited add.py")
        step_finish()
        text("Finished the held run.")
        return 0
    if SCENARIO == "hold_after_edit":
        write_add()
        tool("edit", {"path": str(WORKSPACE / "add.py")}, "Edited add.py")
        text("Edited add.py; now holding for external interruption.")
        time.sleep(30)
        step_finish()
        text("This should never be reached.")
        return 0
    print(f"Unknown fake scenario: {SCENARIO}", file=sys.stderr, flush=True)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
