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

# Terminal completion reasons per OpenCode NDJSON schema
_TERMINAL_REASONS = {"stop", "completed", "complete", "finished"}
# Non-terminal reasons that should not count as completion
_NON_TERMINAL_REASONS = {"error", "aborted", "cancelled", "canceled", "max_turns", "context_limit"}

# Structured failure classification codes
class FailureCode:
    STREAM_INVALID = "STREAM_INVALID"
    STREAM_INCOMPLETE = "STREAM_INCOMPLETE"
    INVALID_9ROUTER_STREAM_EVENT = "INVALID_9ROUTER_STREAM_EVENT"
    NETWORK_TRANSIENT = "NETWORK_TRANSIENT"
    GATEWAY_TRANSIENT = "GATEWAY_TRANSIENT"
    RATE_LIMITED = "RATE_LIMITED"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    MODEL_NOT_FOUND = "MODEL_NOT_FOUND"
    REQUEST_SCHEMA_INCOMPATIBLE = "REQUEST_SCHEMA_INCOMPATIBLE"
    TOKEN_LIMIT_MISMATCH = "TOKEN_LIMIT_MISMATCH"
    CONTEXT_OVERFLOW = "CONTEXT_OVERFLOW"
    TOOL_EXECUTION_FAILED = "TOOL_EXECUTION_FAILED"
    AUTH_FAILURE = "AUTH_FAILURE"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    UNKNOWN_EXECUTION_STATE = "UNKNOWN_EXECUTION_STATE"
    NO_COMPATIBLE_ROUTE = "NO_COMPATIBLE_ROUTE"
    RETRY_EXHAUSTED = "RETRY_EXHAUSTED"
    PROTOCOL_ERROR = "protocol_error"
    WORKER_ERROR = "worker_error"
    WORKER_EXIT_NONZERO = "worker_exit_nonzero"
    WORKER_ABORTED = "worker_aborted"
    WORKER_TIMEOUT = "worker_timeout"
    CANCELLATION_UNVERIFIED = "cancellation_unverified"
    POLICY_VIOLATION = "policy_violation"
    AUTH_ERROR = "auth_error"
    TRANSIENT_ERROR = "transient_error"
    BRIDGE_INTERRUPTED = "bridge_interrupted"
    BRIDGE_INTERNAL_ERROR = "bridge_internal_error"


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
    terminal_reason: str | None  # Explicit terminal reason from step_finish
    last_event_type: str | None
    last_step_reason: str | None
    raw_events: int
    summary: str
    redacted_summary: str

    @property
    def has_activity(self) -> bool:
        return bool(self.texts or self.tools_used)

    @property
    def has_terminal_completion(self) -> bool:
        """True only when a valid step_finish with terminal reason was observed."""
        return self.terminal_seen and self.terminal_reason in _TERMINAL_REASONS

    @property
    def protocol_ok(self) -> bool:
        return (
            not self.malformed_lines
            and self.error_message is None
            and self.session_id is not None
            and self.has_terminal_completion
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "event_counts": self.event_counts,
            "tools_used": list(self.tools_used),
            "edit_tools_used": list(self.edit_tools_used),
            "malformed_lines": list(self.malformed_lines),
            "terminal_seen": self.terminal_seen,
            "terminal_reason": self.terminal_reason,
            "last_event_type": self.last_event_type,
            "last_step_reason": self.last_step_reason,
            "raw_events": self.raw_events,
            "has_activity": self.has_activity,
            "has_terminal_completion": self.has_terminal_completion,
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
    terminal_reason: str | None = None
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
            error_code=FailureCode.PROTOCOL_ERROR,
            malformed_lines=(),
            terminal_seen=False,
            terminal_reason=None,
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
                        error_code = FailureCode.UNKNOWN_EXECUTION_STATE

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
                    error_code = FailureCode.WORKER_ERROR

            if event_type == "text" and isinstance(part.get("text"), str):
                value = part["text"]
                if text_chars < MAX_TEXT_CHARS:
                    remaining = MAX_TEXT_CHARS - text_chars
                    texts.append(value[:remaining])
                    text_chars += min(len(value), remaining)
                # Text events are NOT terminal - only step_finish with valid reason is
            elif event_type == "tool_use":
                tool_name = part.get("tool")
                if isinstance(tool_name, str) and tool_name:
                    tools.append(tool_name)
                    if tool_name.lower() in _EDIT_TOOLS:
                        edit_tools.add(tool_name.lower())
                state = part.get("state")
                if isinstance(state, dict) and state.get("status") == "error":
                    # A failed tool call is not automatically fatal: the model
                    # may recover. It is retained in counts/tools only.
                    pass
            elif event_type == "step_finish":
                reason = part.get("reason")
                if isinstance(reason, str):
                    last_reason = reason
                    terminal_seen = True
                    terminal_reason = reason.lower()
                    if terminal_reason in _NON_TERMINAL_REASONS:
                        if error_message is None:
                            error_message = f"Worker step finished with reason {reason}"
                            error_code = FailureCode.WORKER_ABORTED
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
        terminal_reason=terminal_reason,
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


# Structured regex patterns for failure classification
_AUTH_RE = re.compile(
    r"(?i)(\b401\b|\b403\b|unauthorized|forbidden|missing api key|invalid api key|authentication failed)"
)
_QUOTA_RE = re.compile(
    r"(?i)(quota exhaust|quota exceeded|insufficient quota|quota limit|out of quota|billing limit|credit limit)"
)
_RATE_LIMIT_RE = re.compile(
    r"(?i)(\b429\b|rate limit|too many requests|rate exceeded|throttle)"
)
_GATEWAY_RE = re.compile(
    r"(?i)(\b50[0-4]\b|bad gateway|service unavailable|gateway timeout|upstream timeout|gateway error)"
)
_NETWORK_RE = re.compile(
    r"(?i)(connection reset|connection refused|connection timeout|network error|dns|resolve|socket|econnrefused|etimedout)"
)
_MODEL_NOT_FOUND_RE = re.compile(
    r"(?i)(model not found|model unavailable|model does not exist|unknown model|model_id.*not found|no such model)"
)
_SCHEMA_RE = re.compile(
    r"(?i)(incompatible|schema|validation|message format|unexpected field|malformed request|bad request.*400)"
)
_TOKEN_LIMIT_RE = re.compile(
    r"(?i)(token limit|max tokens|context length|context window|too many tokens|exceeds.*limit|max_completion_tokens|context.*overflow)"
)
_CONTEXT_OVERFLOW_RE = re.compile(
    r"(?i)(context.*overflow|context.*exceed|context.*limit|context window.*full|history too long)"
)
_TOOL_EXEC_RE = re.compile(
    r"(?i)(tool.*fail|tool.*error|function.*fail|function.*error|execution failed|tool call.*error)"
)
_SESSION_ERROR_RE = re.compile(
    r"(?i)(session not found|session expired|invalid session|session_id.*not found|no such session)"
)

# Pattern to detect Invalid 9router/openai-compatible-chat stream event
_INVALID_9ROUTER_STREAM_RE = re.compile(
    r"(?i)(invalid 9router|openai.compatible.chat stream event|invalid stream event|malformed stream|stream protocol error)"
)

# Pattern to detect when model is generating text ABOUT errors (not actual errors)
_EXAMPLE_ERROR_RE = re.compile(
    r"(?i)(example|sample|demonstrat|illustrat|show.*error|error.*example|for instance|such as.*error)"
)


def _classify_from_text(text: str) -> tuple[str, str, bool] | None:
    """Classify failure from error text. Returns (code, category, retryable) or None."""
    if not text:
        return None

    # Skip if text appears to be model-generated examples of errors
    if _EXAMPLE_ERROR_RE.search(text):
        return None

    # Check in order of specificity
    if _AUTH_RE.search(text):
        return FailureCode.AUTH_FAILURE, "auth", False
    if _QUOTA_RE.search(text):
        return FailureCode.QUOTA_EXHAUSTED, "quota", False  # Quota exhaustion is not retryable by default
    if _RATE_LIMIT_RE.search(text):
        return FailureCode.RATE_LIMITED, "rate_limit", True
    if _GATEWAY_RE.search(text):
        return FailureCode.GATEWAY_TRANSIENT, "gateway", True
    if _NETWORK_RE.search(text):
        return FailureCode.NETWORK_TRANSIENT, "network", True
    if _MODEL_NOT_FOUND_RE.search(text):
        return FailureCode.MODEL_NOT_FOUND, "model", False
    if _SCHEMA_RE.search(text):
        return FailureCode.REQUEST_SCHEMA_INCOMPATIBLE, "schema", False
    if _TOKEN_LIMIT_RE.search(text):
        return FailureCode.TOKEN_LIMIT_MISMATCH, "token_limit", False
    if _CONTEXT_OVERFLOW_RE.search(text):
        return FailureCode.CONTEXT_OVERFLOW, "context", False
    if _TOOL_EXEC_RE.search(text):
        return FailureCode.TOOL_EXECUTION_FAILED, "tool", False
    if _SESSION_ERROR_RE.search(text):
        return FailureCode.SESSION_NOT_FOUND, "session", False
    if _INVALID_9ROUTER_STREAM_RE.search(text):
        return FailureCode.INVALID_9ROUTER_STREAM_EVENT, "protocol", False

    return None


def classify_failure(
    *,
    exit_code: int | None,
    outcome: WorkerOutcome,
    stderr_tail: str,
) -> dict[str, Any] | None:
    """Return an error object, or None when the worker is COMPLETED.

    Conservative classification:
    - Requires explicit terminal completion (step_finish with valid reason)
    - Does not treat text events as terminal
    - Does not treat has_activity as success
    - Distinguishes specific failure categories
    - Does not classify model-generated error examples as actual failures
    """

    searchable = "\n".join(
        [stderr_tail or "", outcome.error_message or "", outcome.redacted_summary]
    )

    # 1. Malformed NDJSON - never retryable
    if outcome.malformed_lines:
        return {
            "code": FailureCode.STREAM_INVALID,
            "category": "protocol",
            "message": "Worker emitted malformed or conflicting NDJSON",
            "retryable": False,
            "details": {"malformed_lines": list(outcome.malformed_lines)},
        }

    # 2. Explicit error events from worker
    if outcome.error_message is not None:
        classification = _classify_from_text(searchable)
        if classification:
            code, category, retryable = classification
            return {
                "code": code,
                "category": category,
                "message": outcome.error_message,
                "retryable": retryable,
            }
        # Fallback to original error code
        return {
            "code": outcome.error_code or FailureCode.WORKER_ERROR,
            "category": "worker",
            "message": outcome.error_message,
            "retryable": False,
        }

    # 3. Non-zero exit code
    if exit_code is not None and exit_code != 0:
        classification = _classify_from_text(searchable)
        if classification:
            code, category, retryable = classification
            return {
                "code": code,
                "category": category,
                "message": f"Worker exited with code {exit_code}: {outcome.error_message or 'unknown error'}",
                "retryable": retryable,
                "details": {"exit_code": exit_code},
            }
        return {
            "code": FailureCode.WORKER_EXIT_NONZERO,
            "category": "worker",
            "message": f"Worker exited with code {exit_code}",
            "retryable": False,
            "details": {"exit_code": exit_code},
        }

    # 4. Missing session ID - protocol failure
    if outcome.session_id is None:
        return {
            "code": FailureCode.SESSION_NOT_FOUND,
            "category": "protocol",
            "message": "Worker output did not contain a session ID",
            "retryable": False,
        }

    # 5. No terminal completion - stream incomplete
    if not outcome.has_terminal_completion:
        # Check if we have any events at all
        if outcome.raw_events == 0:
            return {
                "code": FailureCode.STREAM_INCOMPLETE,
                "category": "protocol",
                "message": "Worker produced no events (empty stream)",
                "retryable": False,
            }
        # Check if stream ended without proper termination
        return {
            "code": FailureCode.STREAM_INCOMPLETE,
            "category": "protocol",
            "message": f"Worker stream ended without terminal completion (last: {outcome.last_event_type}, reason: {outcome.terminal_reason or 'none'})",
            "retryable": False,
            "details": {
                "last_event_type": outcome.last_event_type,
                "terminal_reason": outcome.terminal_reason,
                "raw_events": outcome.raw_events,
            },
        }

    # 6. Success - only when terminal completion confirmed
    return None
