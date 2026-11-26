"""Strict task-contract validation for the synchronous bridge.

The task file is untrusted input.  It may select only a configured workspace
and profile; it never supplies an executable, model, agent, or absolute path.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any

from .errors import TaskError
from .redact import contains_secret_shape

MAX_TASK_BYTES = 64 * 1024
MAX_OBJECTIVE_CHARS = 8000
MAX_REFERENCE_COUNT = 50
MAX_ALLOWED_PATH_COUNT = 100
MAX_ACCEPTANCE_COUNT = 20

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,254}$")
_HEAD_RE = re.compile(r"^[0-9a-fA-F]{40}([0-9a-fA-F]{24})?$")
_SESSION_RE = re.compile(r"^ses_[A-Za-z0-9]{8,120}$")
_CHECKPOINT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
_SCENARIO_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")

_ALLOWED_KEYS = {
    "schema_version",
    "task_id",
    "workspace_id",
    "profile",
    "expected_branch",
    "expected_head",
    "objective",
    "references",
    "allowed_paths",
    "acceptance_criteria",
    "timeout_seconds",
    "parent_task_id",
    "checkpoint_id",
    "resume_session_id",
    "metadata",
}

_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


@dataclass(frozen=True)
class Task:
    task_id: str
    workspace_id: str
    profile: str
    expected_branch: str
    objective: str
    references: tuple[str, ...]
    allowed_paths: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    timeout_seconds: int | None = None
    expected_head: str | None = None
    parent_task_id: str | None = None
    checkpoint_id: str | None = None
    resume_session_id: str | None = None
    fake_scenario: str | None = None
    task_category: str | None = None
    source_path: str | None = None

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": 1,
            "task_id": self.task_id,
            "workspace_id": self.workspace_id,
            "profile": self.profile,
            "expected_branch": self.expected_branch,
            "expected_head": self.expected_head,
            "objective": self.objective,
            "references": list(self.references),
            "allowed_paths": list(self.allowed_paths),
            "acceptance_criteria": list(self.acceptance_criteria),
            "timeout_seconds": self.timeout_seconds,
            "parent_task_id": self.parent_task_id,
            "checkpoint_id": self.checkpoint_id,
            "resume_session_id": self.resume_session_id,
        }
        if self.fake_scenario is not None:
            result["metadata"] = {"fake_scenario": self.fake_scenario}
        if self.task_category is not None:
            result.setdefault("metadata", {})["task_category"] = self.task_category
        return result


def load_task(path: str | Path) -> Task:
    source = Path(path).expanduser().resolve(strict=True)
    if not source.is_file():
        raise TaskError("Task path is not a file", path=str(source))
    if source.stat().st_size > MAX_TASK_BYTES:
        raise TaskError("Task file is too large", max_bytes=MAX_TASK_BYTES)
    try:
        text = source.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise TaskError("Task file is not valid UTF-8", error=str(exc)) from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise TaskError(
            "Task file is not valid JSON",
            line=exc.lineno,
            column=exc.colno,
        ) from exc
    return parse_task(data, source_path=str(source))


def parse_task(data: Any, source_path: str | None = None) -> Task:
    if not isinstance(data, dict):
        raise TaskError("Task must be a JSON object")
    unknown = sorted(set(data) - _ALLOWED_KEYS)
    if unknown:
        raise TaskError("Task contains unsupported keys", keys=unknown)

    if data.get("schema_version") != 1:
        raise TaskError("Unsupported task schema_version", expected=1)

    task_id = _require_id(data.get("task_id"), "task_id")
    workspace_id = _require_id(data.get("workspace_id"), "workspace_id")
    profile = _require_id(data.get("profile"), "profile")

    expected_branch = data.get("expected_branch")
    if not isinstance(expected_branch, str) or not _valid_branch(expected_branch):
        raise TaskError("expected_branch is not a safe Git branch name")

    expected_head = data.get("expected_head")
    if expected_head is not None:
        if not isinstance(expected_head, str) or not _HEAD_RE.fullmatch(expected_head):
            raise TaskError("expected_head must be a full hexadecimal commit id")

    objective = data.get("objective")
    if not isinstance(objective, str) or not objective.strip():
        raise TaskError("objective must be a non-empty string")
    if len(objective) > MAX_OBJECTIVE_CHARS:
        raise TaskError("objective is too long", max_chars=MAX_OBJECTIVE_CHARS)
    _reject_control(objective, "objective", allow_newlines=True)
    if contains_secret_shape(objective):
        raise TaskError("objective contains credential-shaped material")

    references = _require_path_list(data.get("references", []), "references", MAX_REFERENCE_COUNT)
    allowed_paths = _require_path_list(
        data.get("allowed_paths", []), "allowed_paths", MAX_ALLOWED_PATH_COUNT
    )
    acceptance = _require_string_list(
        data.get("acceptance_criteria", []),
        "acceptance_criteria",
        MAX_ACCEPTANCE_COUNT,
        1000,
    )

    timeout = data.get("timeout_seconds")
    if timeout is not None:
        if isinstance(timeout, bool) or not isinstance(timeout, int):
            raise TaskError("timeout_seconds must be an integer")
        if not 1 <= timeout <= 86400:
            raise TaskError("timeout_seconds is out of range", min=1, max=86400)

    parent_task_id = data.get("parent_task_id")
    if parent_task_id is not None:
        if not isinstance(parent_task_id, str) or not _ID_RE.fullmatch(parent_task_id):
            raise TaskError("parent_task_id is invalid")
        if parent_task_id == task_id:
            raise TaskError("parent_task_id must differ from task_id")

    checkpoint_id = data.get("checkpoint_id")
    if checkpoint_id is not None:
        if not isinstance(checkpoint_id, str) or not _CHECKPOINT_RE.fullmatch(checkpoint_id):
            raise TaskError("checkpoint_id is invalid")

    resume_session_id = data.get("resume_session_id")
    if resume_session_id is not None:
        if not isinstance(resume_session_id, str) or not _SESSION_RE.fullmatch(
            resume_session_id
        ):
            raise TaskError("resume_session_id is invalid")
        if parent_task_id is None:
            raise TaskError("resume_session_id requires parent_task_id")

    fake_scenario: str | None = None
    task_category: str | None = None
    metadata = data.get("metadata", {})
    if metadata is not None:
        if not isinstance(metadata, dict):
            raise TaskError("metadata must be an object")
        unknown_meta = sorted(set(metadata) - {"fake_scenario", "task_category"})
        if unknown_meta:
            raise TaskError("metadata contains unsupported keys", keys=unknown_meta)
        scenario = metadata.get("fake_scenario")
        if scenario is not None:
            if not isinstance(scenario, str) or not _SCENARIO_RE.fullmatch(scenario):
                raise TaskError("metadata.fake_scenario is invalid")
            fake_scenario = scenario
        category = metadata.get("task_category")
        if category is not None:
            if not isinstance(category, str) or not _ID_RE.fullmatch(category):
                raise TaskError("metadata.task_category is invalid")
            task_category = category

    return Task(
        task_id=task_id,
        workspace_id=workspace_id,
        profile=profile,
        expected_branch=expected_branch,
        objective=objective,
        references=tuple(references),
        allowed_paths=tuple(allowed_paths),
        acceptance_criteria=tuple(acceptance),
        timeout_seconds=timeout,
        expected_head=expected_head,
        parent_task_id=parent_task_id,
        checkpoint_id=checkpoint_id,
        resume_session_id=resume_session_id,
        fake_scenario=fake_scenario,
        task_category=task_category,
        source_path=source_path,
    )


def validate_relative_path(value: Any, field: str = "path") -> str:
    """Return a normalized POSIX relative path, or raise TaskError."""

    if not isinstance(value, str):
        raise TaskError(f"{field} must be a string")
    if not value or len(value) > 512:
        raise TaskError(f"{field} length is invalid", max_chars=512)
    _reject_control(value, field)
    raw = value.replace("\\", "/")
    if raw.startswith("/") or raw.startswith("//"):
        raise TaskError(f"{field} must be relative")
    if PureWindowsPath(value).is_absolute() or PureWindowsPath(value).drive:
        raise TaskError(f"{field} must be relative and must not contain a drive")
    if ":" in raw:
        raise TaskError(f"{field} must not contain an alternate data stream")
    parts = raw.split("/")
    if any(part == "" for part in parts):
        raise TaskError(f"{field} contains an empty path segment")
    for part in parts:
        if part in {".", ".."}:
            raise TaskError(f"{field} must not contain '.' or '..' segments")
        if part.lower() == ".git":
            raise TaskError(f"{field} must not target .git")
        if part.endswith(" ") or part.endswith("."):
            raise TaskError(f"{field} contains a Windows-ambiguous segment")
        base = part.split(".", 1)[0].upper()
        if base in _WINDOWS_RESERVED:
            raise TaskError(f"{field} contains a reserved Windows device name")
    return "/".join(parts)


def _require_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise TaskError(f"{field} is invalid", pattern=_ID_RE.pattern)
    return value


def _valid_branch(value: str) -> bool:
    if not _BRANCH_RE.fullmatch(value):
        return False
    if ".." in value or "//" in value or value.endswith("/") or value.endswith(".lock"):
        return False
    if "@{" in value or "\\" in value or " " in value:
        return False
    return True


def _reject_control(value: str, field: str, allow_newlines: bool = False) -> None:
    for char in value:
        code = ord(char)
        if code < 32 or code == 127:
            if allow_newlines and char in "\n\r\t":
                continue
            raise TaskError(f"{field} contains control characters")


def _require_path_list(value: Any, field: str, limit: int) -> list[str]:
    if not isinstance(value, list):
        raise TaskError(f"{field} must be a list")
    if len(value) > limit:
        raise TaskError(f"{field} has too many entries", max_entries=limit)
    result: list[str] = []
    for item in value:
        normalized = validate_relative_path(item, field)
        if normalized in result:
            raise TaskError(f"{field} contains a duplicate path", path=normalized)
        result.append(normalized)
    return result


def _require_string_list(
    value: Any, field: str, limit: int, max_chars: int
) -> list[str]:
    if not isinstance(value, list):
        raise TaskError(f"{field} must be a list")
    if len(value) > limit:
        raise TaskError(f"{field} has too many entries", max_entries=limit)
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise TaskError(f"{field} entries must be non-empty strings")
        if len(item) > max_chars:
            raise TaskError(f"{field} entry is too long", max_chars=max_chars)
        _reject_control(item, field, allow_newlines=True)
        if contains_secret_shape(item):
            raise TaskError(f"{field} contains credential-shaped material")
        result.append(item)
    return result
