"""Fail-closed NDJSON event parsing and failure classification."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .redact import SecretRedactor

MAX_LINE_CHARS = 4 * 1024 * 1024
MAX_TEXT_CHARS = 500_000
_SESSION_RE = re.compile(r"^ses_[A-Za-z0-9]{8,120}$")
_EDIT_TOOLS = {"edit", "write", "patch", "multiedit", "apply_patch"}


@dataclass
class WorkerOutcome:
    session_id: str | None
    texts: tuple[str, ...]
    tools_used: tuple[str, ...]
    edit_tools_used: tuple[str, ...]
    event_counts: dict[str, int]
    error_message: str | None
    error_code: str | None
    malformed_lines: tuple[int, ...]
    terminal_seen: bool
    last_event_type: str | None
    last_step_reason: str | None
    raw_events: int
    summary: str
    redacted_summary: str

    @property
    def has_activity(self) -> bool:
        return bool(self.texts or self.tools_used or self.terminal_seen)

    @property
    def protocol_ok(self) -> bool:
        return (
            not self.malformed_lines
            and self.error_message is None
            and self.session_id is not None
            and self.has_activity
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "event_counts": self.event_counts,
            "tools_used": list(self.tools_used),
            "edit_tools_used": list(self.edit_tools_used),
            "malformed_lines": list(self.malformed_lines),
            "terminal_seen": self.terminal_seen,
            "last_event_type": self.last_event_type,
            "last_step_reason": self.last_step_reason,
            "raw_events": self.raw_events,
            "has_activity": self.has_activity,
            "protocol_ok": self.protocol_ok,
        }


def parse_events(
    path: str | Path,
    *,
    redactor: SecretRedactor,
    max_summary_chars: int,
) -> WorkerOutcome:
    texts: list[str] = []
    tools: list[str] = []
    edit_tools: set[str] = set()
    counts: dict[str, int] = {}
    malformed: list[int] = []
    session_id: str | None = None
    error_message: str | None = None
    error_code: str | None = None
    terminal_seen = False
    last_type: str | None = None
    last_reason: str | None = None
    raw_events = 0
    text_chars = 0

    source = Path(path)
    try:
        handle = source.open("r", encoding="utf-8-sig", errors="replace")
    except OSError:
        return WorkerOutcome(
            session_id=None,
            texts=(),
            tools_used=(),
            edit_tools_used=(),
            event_counts={},
            error_message="Worker event stream is missing",
            error_code="protocol_error",
            malformed_lines=(),
            terminal_seen=False,
            last_event_type=None,
            last_step_reason=None,
            raw_events=0,
            summary="",
            redacted_summary="",
        )

    with handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            if len(line) > MAX_LINE_CHARS:
                malformed.append(line_number)
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                malformed.append(line_number)
                continue
            if not isinstance(event, dict):
                malformed.append(line_number)
                continue
            raw_events += 1
            event_type = event.get("type")
            if not isinstance(event_type, str) or not event_type:
                malformed.append(line_number)
                continue
            counts[event_type] = counts.get(event_type, 0) + 1
            last_type = event_type
            part = event.get("part")
            if not isinstance(part, dict):
                part = {}

            candidate_session = event.get("sessionID") or part.get("sessionID")
            if isinstance(candidate_session, str) and _SESSION_RE.fullmatch(
                candidate_session
            ):
                if session_id is None:
                    session_id = candidate_session
                elif session_id != candidate_session:
                    malformed.append(line_number)
                    if error_message is None:
                        error_message = "Worker emitted conflicting session IDs"
                        error_code = "session_mismatch"

            nested_error = event.get("error")
            part_type = part.get("type")
            if (
                event_type.lower() in {"error", "fatal"}
                or part_type == "error"
                or (nested_error is not None)
            ):
                message = _extract_error_message(event, part)
                if error_message is None:
                    error_message = message or f"Worker emitted {event_type} event"
                    error_code = "worker_error"

            if event_type == "text" and isinstance(part.get("text"), str):
                value = part["text"]
                if text_chars < MAX_TEXT_CHARS:
                    remaining = MAX_TEXT_CHARS - text_chars
                    texts.append(value[:remaining])
                    text_chars += min(len(value), remaining)
                terminal_seen = True
            elif event_type == "tool_use":
                tool_name = part.get("tool")
                if isinstance(tool_name, str) and tool_name:
                    tools.append(tool_name)
                    if tool_name.lower() in _EDIT_TOOLS:
                        edit_tools.add(tool_name.lower())
                state = part.get("state")
                if isinstance(state, dict) and state.get("status") == "error":
                    # A failed tool call is not automatically fatal: the model
                    # may recover.  It is retained in counts/tools only.
                    pass
            elif event_type == "step_finish":
                reason = part.get("reason")
                if isinstance(reason, str):
                    last_reason = reason
                    if reason.lower() in {"error", "aborted", "cancelled", "canceled"}:
                        if error_message is None:
                            error_message = f"Worker step finished with reason {reason}"
                            error_code = "worker_aborted"
                terminal_seen = True
            elif event_type in {"step_start", "reasoning", "snapshot"}:
                pass

    combined = "\n".join(texts).strip()
    if not combined:
        if tools:
            combined = "Worker used tools: " + ", ".join(sorted(set(tools)))
        else:
            combined = "Worker produced no text summary"
    if len(combined) > max_summary_chars:
        combined = combined[:max_summary_chars].rstrip() + "…"
    redacted = redactor.redact(combined)
    if error_message is not None:
        error_message = redactor.redact(error_message)[:2000]

    return WorkerOutcome(
        session_id=session_id,
        texts=tuple(texts),
        tools_used=tuple(tools),
        edit_tools_used=tuple(sorted(edit_tools)),
        event_counts=counts,
        error_message=error_message,
        error_code=error_code,
        malformed_lines=tuple(malformed),
        terminal_seen=terminal_seen,
        last_event_type=last_type,
        last_step_reason=last_reason,
        raw_events=raw_events,
        summary=combined,
        redacted_summary=redacted,
    )


def _extract_error_message(event: dict[str, Any], part: dict[str, Any]) -> str:
    for candidate in (
        event.get("error"),
        part.get("error"),
        part.get("text"),
        event.get("message"),
        part.get("message"),
    ):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()[:2000]
        if isinstance(candidate, dict):
            for key in ("message", "error", "detail", "reason"):
                value = candidate.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()[:2000]
    return ""


_AUTH_RE = re.compile(
    r"(?i)(\b401\b|\b403\b|unauthorized|forbidden|missing api key|invalid api key|authentication failed)"
)
_TRANSIENT_RE = re.compile(
    r"(?i)(\b429\b|rate limit|too many requests|\b50[0-4]\b|bad gateway|service unavailable|gateway timeout|connection reset|timed out)"
)


def classify_failure(
    *,
    exit_code: int | None,
    outcome: WorkerOutcome,
    stderr_tail: str,
) -> dict[str, Any] | None:
    """Return an error object, or None when the worker is COMPLETED."""

    searchable = "\n".join(
        [stderr_tail or "", outcome.error_message or "", outcome.redacted_summary]
    )
    if outcome.malformed_lines:
        return {
            "code": "protocol_error",
            "category": "protocol",
            "message": "Worker emitted malformed or conflicting NDJSON",
            "retryable": False,
            "details": {"malformed_lines": list(outcome.malformed_lines)},
        }
    if outcome.error_message is not None:
        category = "worker"
        code = outcome.error_code or "worker_error"
        retryable = False
        if _AUTH_RE.search(searchable):
            category = "auth"
            code = "auth_error"
        elif _TRANSIENT_RE.search(searchable):
            category = "transient"
            code = "transient_error"
            retryable = True
        return {
            "code": code,
            "category": category,
            "message": outcome.error_message,
            "retryable": retryable,
        }
    if exit_code is None or exit_code != 0:
        category = "worker"
        code = "worker_exit_nonzero"
        retryable = False
        if _AUTH_RE.search(searchable):
            category = "auth"
            code = "auth_error"
        elif _TRANSIENT_RE.search(searchable):
            category = "transient"
            code = "transient_error"
            retryable = True
        return {
            "code": code,
            "category": category,
            "message": f"Worker exited with code {exit_code}",
            "retryable": retryable,
            "details": {"exit_code": exit_code},
        }
    if outcome.session_id is None:
        return {
            "code": "protocol_error",
            "category": "protocol",
            "message": "Worker output did not contain a session ID",
            "retryable": False,
        }
    if not outcome.has_activity:
        return {
            "code": "protocol_error",
            "category": "protocol",
            "message": "Worker output did not contain terminal activity",
            "retryable": False,
        }
    return None
