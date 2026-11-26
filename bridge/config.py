"""Configuration loading and validation.

Configuration is user-managed and is the only source of executable, agent,
model, workspace, and credential locations.  Task files cannot override it.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import ConfigError
from .redact import contains_secret_shape

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")
_AGENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_ENV_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")

_ALLOWED_KEYS = {
    "schema_version",
    "opencode_executable",
    "opencode_config",
    "opencode_config_dir",
    "runtime_root",
    "credential_file",
    "credential_env",
    "workspaces",
    "profiles",
    "approved_models",
    "worker",
    "timeout_seconds",
    "max_timeout_seconds",
    "max_summary_chars",
    "max_prompt_chars",
    "lock_timeout_seconds",
    "max_runs_per_task",
}


@dataclass(frozen=True)
class Profile:
    profile_id: str
    agent: str
    model: str
    access: str


@dataclass(frozen=True)
class BridgeConfig:
    source_path: str
    opencode_executable: str | None
    opencode_config: str | None
    opencode_config_dir: str | None
    runtime_root: str
    credential_file: str | None
    credential_env: str
    workspaces: dict[str, str]
    profiles: dict[str, Profile]
    approved_models: tuple[str, ...]
    worker_type: str
    fake_worker_executable: str | None
    fake_python_executable: str | None
    timeout_seconds: int
    max_timeout_seconds: int
    max_summary_chars: int
    max_prompt_chars: int
    lock_timeout_seconds: int
    max_runs_per_task: int

    def workspace(self, workspace_id: str) -> str:
        try:
            return self.workspaces[workspace_id]
        except KeyError as exc:
            raise ConfigError(
                "workspace_id is not in the config allowlist",
                workspace_id=workspace_id,
            ) from exc

    def profile(self, profile_id: str) -> Profile:
        try:
            return self.profiles[profile_id]
        except KeyError as exc:
            raise ConfigError(
                "profile is not in the config allowlist", profile=profile_id
            ) from exc

    def sanitized(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "worker_type": self.worker_type,
            "opencode_executable": self.opencode_executable,
            "opencode_config": self.opencode_config,
            "opencode_config_dir": self.opencode_config_dir,
            "runtime_root": self.runtime_root,
            "credential_env": self.credential_env,
            "credential_file_present": bool(
                self.credential_file and Path(self.credential_file).is_file()
            ),
            "workspaces": dict(self.workspaces),
            "profiles": {
                key: {
                    "agent": value.agent,
                    "model": value.model,
                    "access": value.access,
                }
                for key, value in self.profiles.items()
            },
            "approved_models": list(self.approved_models),
            "timeout_seconds": self.timeout_seconds,
            "max_timeout_seconds": self.max_timeout_seconds,
            "max_summary_chars": self.max_summary_chars,
            "max_prompt_chars": self.max_prompt_chars,
            "lock_timeout_seconds": self.lock_timeout_seconds,
            "max_runs_per_task": self.max_runs_per_task,
        }


def load_config(path: str | Path) -> BridgeConfig:
    source = Path(path).expanduser().resolve(strict=True)
    if not source.is_file():
        raise ConfigError("Config path is not a file", path=str(source))
    try:
        data = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConfigError("Config is not readable JSON", error=str(exc)) from exc
    return parse_config(data, source_path=str(source))


def parse_config(data: Any, source_path: str | None = None) -> BridgeConfig:
    if not isinstance(data, dict):
        raise ConfigError("Config must be a JSON object")
    unknown = sorted(set(data) - _ALLOWED_KEYS)
    if unknown:
        raise ConfigError("Config contains unsupported keys", keys=unknown)
    _reject_secret_shapes(data, "config")

    if data.get("schema_version") != 1:
        raise ConfigError("Unsupported config schema_version", expected=1)

    config_path = Path(source_path).resolve() if source_path else None
    config_dir = config_path.parent if config_path else Path.cwd()

    worker = data.get("worker", {"type": "opencode"})
    if not isinstance(worker, dict):
        raise ConfigError("worker must be an object")
    worker_type = worker.get("type", "opencode")
    if worker_type not in {"opencode", "fake"}:
        raise ConfigError("worker.type must be 'opencode' or 'fake'")
    unknown_worker = sorted(
        set(worker) - {"type", "executable", "python_executable"}
    )
    if unknown_worker:
        raise ConfigError("worker contains unsupported keys", keys=unknown_worker)

    fake_worker_executable: str | None = None
    fake_python_executable: str | None = None
    opencode_executable: str | None = None
    opencode_config: str | None = None
    opencode_config_dir: str | None = None

    if worker_type == "opencode":
        opencode_executable = _absolute_existing_file(
            data.get("opencode_executable"),
            "opencode_executable",
            suffixes={".exe"},
        )
        opencode_config = _absolute_existing_file(
            data.get("opencode_config", str(config_dir / "opencode.json")),
            "opencode_config",
            suffixes={".json", ".jsonc"},
        )
        opencode_config_dir = _absolute_existing_dir(
            data.get("opencode_config_dir", str(config_dir / ".opencode")),
            "opencode_config_dir",
        )
    else:
        fake_worker_executable = _absolute_existing_file(
            worker.get("executable"), "worker.executable", suffixes={".py"}
        )
        fake_python_executable = _absolute_existing_file(
            worker.get("python_executable", sys.executable),
            "worker.python_executable",
            suffixes={".exe"},
        )

    runtime_root = _absolute_path(data.get("runtime_root"), "runtime_root")
    credential_file = data.get("credential_file")
    if credential_file is not None:
        credential_file = _absolute_path(credential_file, "credential_file")
        if not Path(credential_file).is_file():
            raise ConfigError(
                "credential_file does not exist", path=credential_file
            )

    credential_env = data.get("credential_env", "NINE_ROUTER_KEY")
    if not isinstance(credential_env, str) or not _ENV_RE.fullmatch(credential_env):
        raise ConfigError("credential_env is not a valid environment variable name")

    workspaces_raw = data.get("workspaces")
    if not isinstance(workspaces_raw, dict) or not workspaces_raw:
        raise ConfigError("workspaces must be a non-empty object")
    workspaces: dict[str, str] = {}
    seen_paths: dict[str, str] = {}
    for workspace_id, raw_path in workspaces_raw.items():
        if not isinstance(workspace_id, str) or not _ID_RE.fullmatch(workspace_id):
            raise ConfigError("workspace id is invalid", workspace_id=workspace_id)
        path = _absolute_path(raw_path, f"workspaces.{workspace_id}")
        norm = os.path.normcase(str(Path(path)))
        if norm in seen_paths:
            raise ConfigError(
                "two workspace ids resolve to the same path",
                first=seen_paths[norm],
                second=workspace_id,
            )
        seen_paths[norm] = workspace_id
        workspaces[workspace_id] = path

    profiles_raw = data.get("profiles")
    if not isinstance(profiles_raw, dict) or not profiles_raw:
        raise ConfigError("profiles must be a non-empty object")

    approved_raw = data.get("approved_models")
    if not isinstance(approved_raw, list) or not approved_raw:
        raise ConfigError("approved_models must be a non-empty list")
    approved_models: list[str] = []
    for model in approved_raw:
        if not isinstance(model, str) or not _MODEL_RE.fullmatch(model):
            raise ConfigError("approved_models contains an invalid model id", model=model)
        if model in approved_models:
            raise ConfigError("approved_models contains a duplicate", model=model)
        approved_models.append(model)

    profiles: dict[str, Profile] = {}
    for profile_id, raw in profiles_raw.items():
        if not isinstance(profile_id, str) or not _ID_RE.fullmatch(profile_id):
            raise ConfigError("profile id is invalid", profile=profile_id)
        if not isinstance(raw, dict):
            raise ConfigError("profile must be an object", profile=profile_id)
        unknown_profile = sorted(set(raw) - {"agent", "model", "access"})
        if unknown_profile:
            raise ConfigError(
                "profile contains unsupported keys",
                profile=profile_id,
                keys=unknown_profile,
            )
        agent = raw.get("agent")
        if not isinstance(agent, str) or not _AGENT_RE.fullmatch(agent):
            raise ConfigError("profile agent is invalid", profile=profile_id)
        model = raw.get("model")
        if not isinstance(model, str) or model not in approved_models:
            raise ConfigError(
                "profile model is not in approved_models",
                profile=profile_id,
                model=model,
            )
        access = raw.get("access")
        if access not in {"read", "write"}:
            raise ConfigError(
                "profile access must be 'read' or 'write'", profile=profile_id
            )
        profiles[profile_id] = Profile(
            profile_id=profile_id, agent=agent, model=model, access=access
        )

    timeout_seconds = _bounded_int(data.get("timeout_seconds", 900), "timeout_seconds", 1, 86400)
    max_timeout_seconds = _bounded_int(
        data.get("max_timeout_seconds", 1800), "max_timeout_seconds", 1, 86400
    )
    if timeout_seconds > max_timeout_seconds:
        raise ConfigError("timeout_seconds exceeds max_timeout_seconds")
    max_summary_chars = _bounded_int(
        data.get("max_summary_chars", 2000), "max_summary_chars", 100, 100000
    )
    max_prompt_chars = _bounded_int(
        data.get("max_prompt_chars", 12000), "max_prompt_chars", 1000, 100000
    )
    lock_timeout_seconds = _bounded_int(
        data.get("lock_timeout_seconds", 5), "lock_timeout_seconds", 0, 300
    )
    max_runs_per_task = _bounded_int(
        data.get("max_runs_per_task", 4), "max_runs_per_task", 1, 10
    )

    return BridgeConfig(
        source_path=str(config_path) if config_path else "",
        opencode_executable=opencode_executable,
        opencode_config=opencode_config,
        opencode_config_dir=opencode_config_dir,
        runtime_root=runtime_root,
        credential_file=credential_file,
        credential_env=credential_env,
        workspaces=workspaces,
        profiles=profiles,
        approved_models=tuple(approved_models),
        worker_type=worker_type,
        fake_worker_executable=fake_worker_executable,
        fake_python_executable=fake_python_executable,
        timeout_seconds=timeout_seconds,
        max_timeout_seconds=max_timeout_seconds,
        max_summary_chars=max_summary_chars,
        max_prompt_chars=max_prompt_chars,
        lock_timeout_seconds=lock_timeout_seconds,
        max_runs_per_task=max_runs_per_task,
    )


def ensure_runtime_layout(config: BridgeConfig) -> None:
    root = Path(config.runtime_root)
    for name in ("runs", "locks", "checkpoints", "tmp", "logs"):
        (root / name).mkdir(parents=True, exist_ok=True)


def runtime_writable(config: BridgeConfig) -> bool:
    try:
        ensure_runtime_layout(config)
        with tempfile.NamedTemporaryFile(
            dir=config.runtime_root, prefix=".write-probe-", delete=True
        ) as handle:
            handle.write(b"ok")
            handle.flush()
        return True
    except OSError:
        return False


def _absolute_path(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{field} must be a non-empty absolute path")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ConfigError(f"{field} must be absolute", path=value)
    return str(path.resolve(strict=False))


def _absolute_existing_file(
    value: Any, field: str, suffixes: set[str]
) -> str:
    path_text = _absolute_path(value, field)
    path = Path(path_text)
    if not path.is_file():
        raise ConfigError(f"{field} does not exist", path=path_text)
    if path.suffix.lower() not in suffixes:
        raise ConfigError(
            f"{field} has an unsupported extension",
            path=path_text,
            allowed=sorted(suffixes),
        )
    return path_text


def _absolute_existing_dir(value: Any, field: str) -> str:
    path_text = _absolute_path(value, field)
    if not Path(path_text).is_dir():
        raise ConfigError(f"{field} does not exist", path=path_text)
    return path_text


def _bounded_int(value: Any, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{field} must be an integer")
    if not minimum <= value <= maximum:
        raise ConfigError(
            f"{field} is out of range", minimum=minimum, maximum=maximum
        )
    return value


def _reject_secret_shapes(value: Any, field: str) -> None:
    if isinstance(value, str):
        if contains_secret_shape(value):
            raise ConfigError(
                f"{field} contains credential-shaped material; keep secrets out of config"
            )
    elif isinstance(value, dict):
        for key, item in value.items():
            _reject_secret_shapes(key, f"{field}.key")
            _reject_secret_shapes(item, f"{field}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_secret_shapes(item, f"{field}[{index}]")
