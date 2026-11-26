"""Bridge error types and exit-code mapping."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


EXIT_COMPLETED = 0
EXIT_INVALID = 2
EXIT_WORKER_FAILURE = 3
EXIT_TIMEOUT = 4
EXIT_BLOCKED = 5


@dataclass
class BridgeError(Exception):
    """An expected bridge failure with a stable classification."""

    message: str
    category: str = "internal"
    exit_code: int = EXIT_WORKER_FAILURE
    code: str = "bridge_error"
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "category": self.category,
            "message": self.message,
            "details": self.details,
        }


class ConfigError(BridgeError):
    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(
            message=message,
            category="config",
            exit_code=EXIT_INVALID,
            code="invalid_config",
            details=details,
        )


class TaskError(BridgeError):
    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(
            message=message,
            category="task",
            exit_code=EXIT_INVALID,
            code="invalid_task",
            details=details,
        )


class PolicyError(BridgeError):
    def __init__(self, message: str, code: str = "policy_blocked", **details: Any) -> None:
        super().__init__(
            message=message,
            category="policy",
            exit_code=EXIT_BLOCKED,
            code=code,
            details=details,
        )


class LockError(PolicyError):
    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message, code="repository_locked", **details)


class WorkerError(BridgeError):
    def __init__(self, message: str, category: str = "worker", **details: Any) -> None:
        super().__init__(
            message=message,
            category=category,
            exit_code=EXIT_WORKER_FAILURE,
            code="worker_failure",
            details=details,
        )


class GitError(BridgeError):
    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(
            message=message,
            category="git",
            exit_code=EXIT_BLOCKED,
            code="git_error",
            details=details,
        )


class NotFoundError(BridgeError):
    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(
            message=message,
            category="not_found",
            exit_code=EXIT_BLOCKED,
            code="not_found",
            details=details,
        )


class TimeoutFailure(BridgeError):
    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(
            message=message,
            category="timeout",
            exit_code=EXIT_TIMEOUT,
            code="worker_timeout",
            details=details,
        )
