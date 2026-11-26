"""Git inspection helpers.

All Git calls use argv, never a shell.  Status parsing is NUL-safe so spaces,
Unicode, renames, and deletions are preserved.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import GitError, PolicyError

_GIT_TIMEOUT = 30
_MAX_DIFF_SCAN_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class StatusEntry:
    x: str
    y: str
    path: str
    orig_path: str | None = None

    @property
    def code(self) -> str:
        return self.x + self.y

    @property
    def untracked(self) -> bool:
        return self.code == "??"

    @property
    def staged(self) -> bool:
        return self.x not in {" ", "?", "!"}

    @property
    def deleted(self) -> bool:
        return "D" in self.code

    @property
    def renamed(self) -> bool:
        return "R" in self.code

    def to_dict(self) -> dict[str, Any]:
        return {
            "x": self.x,
            "y": self.y,
            "code": self.code,
            "path": self.path,
            "orig_path": self.orig_path,
            "untracked": self.untracked,
            "staged": self.staged,
            "deleted": self.deleted,
            "renamed": self.renamed,
        }


@dataclass(frozen=True)
class RepoState:
    root: str
    branch: str
    head: str
    entries: tuple[StatusEntry, ...]

    @property
    def dirty(self) -> bool:
        return bool(self.entries)

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "branch": self.branch,
            "head": self.head,
            "dirty": self.dirty,
            "status": [entry.to_dict() for entry in self.entries],
        }


def _git_env() -> dict[str, str]:
    allow = (
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "SystemRoot",
        "WINDIR",
        "COMSPEC",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "HOME",
        "HOMEDRIVE",
        "HOMEPATH",
        "LOCALAPPDATA",
        "APPDATA",
    )
    env = {key: os.environ[key] for key in allow if key in os.environ}
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["LC_ALL"] = "C"
    return env


def _decode_path(value: bytes) -> str:
    return value.decode("utf-8", "surrogateescape").replace("\\", "/")


def run_git(
    root: str | Path,
    args: list[str],
    *,
    check: bool = True,
    timeout: int = _GIT_TIMEOUT,
) -> subprocess.CompletedProcess[bytes]:
    command = [
        "git",
        "-c",
        "core.quotepath=false",
        "-c",
        "color.ui=false",
        "-C",
        str(root),
        *args,
    ]
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            env=_git_env(),
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitError("Git command could not be executed", error=str(exc)) from exc
    if check and completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", "replace").strip()
        raise GitError(
            "Git command failed",
            args=args,
            exit_code=completed.returncode,
            stderr=stderr[:1000],
        )
    return completed


def repo_root(path: str | Path) -> str:
    completed = run_git(path, ["rev-parse", "--show-toplevel"])
    text = completed.stdout.decode("utf-8", "surrogateescape").strip()
    if not text:
        raise GitError("Git did not return a repository root", path=str(path))
    return str(Path(text).resolve(strict=True))


def resolve_workspace(configured_path: str) -> str:
    path = Path(configured_path).expanduser()
    if not path.is_absolute():
        raise GitError("Configured workspace must be absolute", path=str(path))
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise GitError("Configured workspace does not exist", path=str(path)) from exc
    if not resolved.is_dir():
        raise GitError("Configured workspace is not a directory", path=str(resolved))
    root = repo_root(resolved)
    if os.path.normcase(root) != os.path.normcase(str(resolved)):
        raise GitError(
            "Configured workspace must be the canonical Git repository root",
            configured=str(resolved),
            git_root=root,
        )
    return root


def branch(root: str | Path) -> str:
    completed = run_git(root, ["branch", "--show-current"])
    return completed.stdout.decode("utf-8", "replace").strip()


def head(root: str | Path) -> str:
    completed = run_git(root, ["rev-parse", "--verify", "HEAD"])
    value = completed.stdout.decode("ascii", "replace").strip()
    if not re.fullmatch(r"[0-9a-fA-F]{40}([0-9a-fA-F]{24})?", value):
        raise GitError("Git returned an invalid HEAD", value=value[:100])
    return value.lower()


def status_entries(root: str | Path) -> tuple[StatusEntry, ...]:
    completed = run_git(
        root,
        ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
    )
    tokens = completed.stdout.split(b"\0")
    entries: list[StatusEntry] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if not token:
            continue
        if len(token) < 4 or token[2:3] != b" ":
            raise GitError("Unparseable git status entry", token=repr(token[:200]))
        x = chr(token[0])
        y = chr(token[1])
        path = _decode_path(token[3:])
        orig_path: str | None = None
        if x in {"R", "C"} or y in {"R", "C"}:
            if index >= len(tokens) or not tokens[index]:
                raise GitError("Rename/copy status entry is missing its source path")
            orig_path = _decode_path(tokens[index])
            index += 1
        entries.append(StatusEntry(x=x, y=y, path=path, orig_path=orig_path))
    return tuple(entries)


def repo_state(root: str | Path) -> RepoState:
    canonical = str(Path(root).resolve(strict=True))
    return RepoState(
        root=canonical,
        branch=branch(canonical),
        head=head(canonical),
        entries=status_entries(canonical),
    )


def diff_bytes(root: str | Path) -> bytes:
    completed = run_git(
        root,
        ["diff", "--no-color", "--binary", "HEAD", "--"],
        check=False,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", "replace").strip()
        raise GitError(
            "Git diff failed",
            exit_code=completed.returncode,
            stderr=stderr[:1000],
        )
    return completed.stdout


def _file_sha256(path: Path) -> str | None:
    try:
        if path.is_symlink():
            return "link:" + hashlib.sha256(
                os.readlink(path).encode("utf-8", "surrogateescape")
            ).hexdigest()
        if not path.is_file():
            return None
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _changed_paths_for_hash(entries: tuple[StatusEntry, ...]) -> list[str]:
    paths: set[str] = set()
    for entry in entries:
        paths.add(entry.path)
        if entry.renamed and entry.orig_path:
            paths.add(entry.orig_path)
    return sorted(paths)


def fingerprint(root: str | Path) -> dict[str, Any]:
    canonical = str(Path(root).resolve(strict=True))
    state = repo_state(canonical)
    hashes = {
        path: _file_sha256(Path(canonical) / path)
        for path in _changed_paths_for_hash(state.entries)
    }
    status_payload = json.dumps(
        [entry.to_dict() for entry in state.entries],
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    diff = diff_bytes(canonical)
    return {
        "root": canonical,
        "branch": state.branch,
        "head": state.head,
        "status": [entry.to_dict() for entry in state.entries],
        "worktree_hashes": hashes,
        "status_sha256": hashlib.sha256(status_payload).hexdigest(),
        "diff_sha256": hashlib.sha256(diff).hexdigest(),
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }


def fingerprints_match(left: dict[str, Any], right: dict[str, Any]) -> bool:
    keys = ("branch", "head", "status", "worktree_hashes", "diff_sha256")
    return all(left.get(key) == right.get(key) for key in keys)


def fingerprint_differences(
    expected: dict[str, Any], actual: dict[str, Any]
) -> list[str]:
    keys = ("branch", "head", "status", "worktree_hashes", "diff_sha256")
    return [key for key in keys if expected.get(key) != actual.get(key)]


def changed_paths(entries: tuple[StatusEntry, ...]) -> list[str]:
    paths: set[str] = set()
    for entry in entries:
        paths.add(entry.path)
        if entry.renamed and entry.orig_path:
            paths.add(entry.orig_path)
    return sorted(paths)


def write_diff_evidence(
    root: str | Path,
    destination: str | Path,
    *,
    redactor: Any | None = None,
) -> int:
    canonical = str(Path(root).resolve(strict=True))
    state = repo_state(canonical)
    diff = diff_bytes(canonical)
    untracked_lines: list[str] = []
    for entry in state.entries:
        if entry.untracked:
            digest = _file_sha256(Path(canonical) / entry.path)
            untracked_lines.append(f"# untracked {entry.path} sha256={digest}")
    if redactor is not None:
        text = redactor.redact(diff.decode("utf-8", "replace"))
        payload = text.encode("utf-8")
    else:
        payload = diff
    if untracked_lines:
        if payload and not payload.endswith(b"\n"):
            payload += b"\n"
        payload += ("\n".join(untracked_lines) + "\n").encode("utf-8")
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return len(payload)


def diff_text_for_scan(root: str | Path) -> str:
    data = diff_bytes(root)[:_MAX_DIFF_SCAN_BYTES]
    return data.decode("utf-8", "replace")


def _is_reparse_point(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    attributes = getattr(info, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag) or path.is_symlink()


def ensure_within(
    root: str | Path,
    relative_path: str,
    *,
    must_exist: bool = False,
    field: str = "path",
) -> Path:
    canonical = Path(root).resolve(strict=True)
    current = canonical
    for part in relative_path.split("/"):
        current = current / part
        if current.exists() or current.is_symlink():
            if _is_reparse_point(current):
                raise PolicyError(
                    f"{field} traverses a symlink or junction",
                    path=relative_path,
                )
        else:
            break
    candidate = canonical / relative_path
    try:
        resolved = candidate.resolve(strict=False)
    except OSError as exc:
        raise PolicyError(
            f"{field} cannot be resolved safely", path=relative_path, error=str(exc)
        ) from exc
    try:
        common = os.path.commonpath([str(canonical), str(resolved)])
    except ValueError as exc:
        raise PolicyError(
            f"{field} is outside the workspace", path=relative_path
        ) from exc
    if os.path.normcase(common) != os.path.normcase(str(canonical)):
        raise PolicyError(f"{field} is outside the workspace", path=relative_path)
    if must_exist and not candidate.exists():
        raise PolicyError(f"{field} does not exist", path=relative_path)
    return candidate
