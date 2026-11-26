"""Secret redaction for bridge summaries and exported evidence."""

from __future__ import annotations

import re
from typing import Any, Iterable

REDACTED = "[REDACTED]"

_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-[A-Za-z0-9][A-Za-z0-9_\-]{7,}"),
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[A-Za-z0-9._~+/=\-]{8,}"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=\-]{16,}"),
    re.compile(r"(?i)(api[_-]?key\s*[=:]\s*[\"']?)[A-Za-z0-9._~+/=\-]{8,}"),
    re.compile(r"(?i)(NINE_ROUTER_KEY\s*[=:]\s*)[^\s\"']+"),
    re.compile(r"(?i)(password\s*[=:]\s*[\"']?)[^\s\"']{6,}"),
    re.compile(
        r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
        re.DOTALL,
    ),
)


class SecretRedactor:
    """Replace known secret values and common credential-shaped strings."""

    def __init__(self, secrets: Iterable[str] | None = None) -> None:
        self._secrets = sorted(
            {s for s in (secrets or []) if isinstance(s, str) and len(s) >= 6},
            key=len,
            reverse=True,
        )

    def redact(self, text: str) -> str:
        if not isinstance(text, str):
            return text
        result = text
        for secret in self._secrets:
            result = result.replace(secret, REDACTED)
        for pattern in _PATTERNS:
            if pattern.groups:
                result = pattern.sub(lambda m: m.group(1) + REDACTED, result)
            else:
                result = pattern.sub(REDACTED, result)
        return result

    def redact_obj(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.redact(value)
        if isinstance(value, list):
            return [self.redact_obj(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self.redact_obj(item) for item in value)
        if isinstance(value, dict):
            return {key: self.redact_obj(item) for key, item in value.items()}
        return value


def contains_secret_shape(text: str) -> bool:
    """Return True when text contains a high-confidence credential shape."""

    if not isinstance(text, str):
        return False
    if re.search(r"sk-[A-Za-z0-9][A-Za-z0-9_\-]{15,}", text):
        return True
    if re.search(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----", text):
        return True
    if re.search(r"(?i)authorization\s*:\s*bearer\s+\S{16,}", text):
        return True
    return False
