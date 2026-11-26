"""Cross-process cooperative locks.

The repository lock is the single-writer invariant for the MVP.  It uses an
OS byte-range lock (msvcrt on Windows, flock elsewhere) plus a thread lock in
the current process.  The lock file is never deleted, so a stale file cannot
be mistaken for a held lock.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import LockError

if os.name == "nt":
    import msvcrt
else:  # pragma: no cover - Windows is the target platform
    import fcntl

_THREAD_GUARD = threading.Lock()
_THREAD_LOCKS: dict[str, threading.Lock] = {}


def _thread_lock(path: str) -> threading.Lock:
    key = os.path.normcase(path)
    with _THREAD_GUARD:
        lock = _THREAD_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _THREAD_LOCKS[key] = lock
        return lock


def _read_holder(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        if not raw:
            return {}
        # Byte zero is reserved for the OS lock; metadata starts at byte one.
        text = raw[1:].decode("utf-8", "replace").strip("\x00")
        if not text:
            return {}
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


class FileLock:
    def __init__(
        self,
        path: str | Path,
        *,
        timeout_seconds: float,
        kind: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.path = Path(path)
        self.timeout_seconds = max(0.0, float(timeout_seconds))
        self.kind = kind
        self.metadata = metadata or {}
        self._handle: Any = None
        self._thread: threading.Lock | None = None

    def __enter__(self) -> "FileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        thread = _thread_lock(str(self.path))
        if not thread.acquire(timeout=self.timeout_seconds):
            raise LockError(
                "Another thread in this bridge process holds the lock",
                kind=self.kind,
                path=str(self.path),
            )
        self._thread = thread
        try:
            self._handle = self.path.open("a+b")
            self._handle.seek(0, os.SEEK_END)
            if self._handle.tell() == 0:
                self._handle.write(b"\x00")
                self._handle.flush()
            self._handle.seek(0)
            deadline = time.monotonic() + self.timeout_seconds
            while True:
                try:
                    if os.name == "nt":
                        msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)
                    else:  # pragma: no cover
                        fcntl.flock(
                            self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB
                        )
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        holder = _read_holder(self.path)
                        raise LockError(
                            "Timed out waiting for the repository lock",
                            kind=self.kind,
                            path=str(self.path),
                            holder=holder,
                        )
                    time.sleep(0.1)
            payload = {
                "kind": self.kind,
                "pid": os.getpid(),
                "acquired_at": datetime.now(timezone.utc).isoformat(),
                **self.metadata,
            }
            encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode(
                "utf-8"
            )
            self._handle.seek(1)
            self._handle.truncate()
            self._handle.write(encoded)
            self._handle.flush()
            return self
        except BaseException:
            self._cleanup_handle()
            if self._thread is not None:
                self._thread.release()
                self._thread = None
            raise

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        try:
            if self._handle is not None:
                try:
                    if os.name == "nt":
                        self._handle.seek(0)
                        msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:  # pragma: no cover
                        fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
                try:
                    self._handle.seek(1)
                    self._handle.truncate()
                    self._handle.write(
                        json.dumps(
                            {
                                "kind": self.kind,
                                "released_at": datetime.now(timezone.utc).isoformat(),
                                "pid": os.getpid(),
                            },
                            sort_keys=True,
                        ).encode("utf-8")
                    )
                    self._handle.flush()
                except OSError:
                    pass
        finally:
            self._cleanup_handle()
            if self._thread is not None:
                self._thread.release()
                self._thread = None

    def _cleanup_handle(self) -> None:
        if self._handle is not None:
            try:
                self._handle.close()
            except OSError:
                pass
            self._handle = None


def repository_lock_path(runtime_root: str | Path, repository_root: str) -> Path:
    canonical = os.path.normcase(str(Path(repository_root).resolve(strict=False)))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
    return Path(runtime_root) / "locks" / f"repo-{digest}.lock"


class RepositoryLock(FileLock):
    def __init__(
        self,
        runtime_root: str | Path,
        repository_root: str,
        *,
        timeout_seconds: float,
        run_id: str,
        task_id: str,
    ) -> None:
        super().__init__(
            repository_lock_path(runtime_root, repository_root),
            timeout_seconds=timeout_seconds,
            kind="repository",
            metadata={
                "repository": str(Path(repository_root).resolve(strict=False)),
                "run_id": run_id,
                "task_id": task_id,
            },
        )


class StateLock(FileLock):
    def __init__(
        self,
        runtime_root: str | Path,
        *,
        timeout_seconds: float = 10.0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            Path(runtime_root) / "locks" / "state.lock",
            timeout_seconds=timeout_seconds,
            kind="state",
            metadata=metadata,
        )
