"""Command-line interface for the synchronous Hybrid Agent bridge."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any, Sequence

from . import __version__, store
from .config import load_config
from .errors import BridgeError, TaskError
from .redact import SecretRedactor
from .recovery import auto_recover
from .runner import checkpoint, execute_run, health, recover


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m bridge.cli",
        description="Synchronous OpenCode bridge for Codex orchestration",
    )
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    health_parser = subparsers.add_parser("health", help="Check config and runtime")
    health_parser.add_argument("--config", required=True)
    health_parser.add_argument("--live", action="store_true")
    health_parser.add_argument("--profile")

    run_parser = subparsers.add_parser("run", help="Run one task synchronously")
    run_parser.add_argument("--config", required=True)
    run_parser.add_argument("--task", required=True)

    status_parser = subparsers.add_parser("status", help="Read persisted run state")
    status_parser.add_argument("--config", required=True)
    status_parser.add_argument("--run-id", required=True)

    result_parser = subparsers.add_parser("result", help="Read persisted run result")
    result_parser.add_argument("--config", required=True)
    result_parser.add_argument("--run-id", required=True)

    list_parser = subparsers.add_parser("list", help="List run metadata")
    list_parser.add_argument("--config", required=True)
    list_parser.add_argument("--limit", type=int, default=50)

    recover_parser = subparsers.add_parser(
        "recover", help="Reconcile runs left PENDING/RUNNING"
    )
    recover_parser.add_argument("--config", required=True)
    recover_parser.add_argument("--apply", action="store_true")

    checkpoint_parser = subparsers.add_parser(
        "checkpoint", help="Record an approved dirty baseline checkpoint"
    )
    checkpoint_parser.add_argument("--config", required=True)
    checkpoint_parser.add_argument("--task", required=True)
    checkpoint_parser.add_argument("--checkpoint-id")

    auto_recover_parser = subparsers.add_parser(
        "auto-recover", help="Automatically recover a failed task using shared recovery policy"
    )
    auto_recover_parser.add_argument("--config", required=True)
    auto_recover_parser.add_argument("--task", required=True)
    auto_recover_parser.add_argument("--max-attempts", type=int, default=3)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    redactor = SecretRedactor()
    try:
        if args.command == "health":
            payload, code = health(
                args.config, live=args.live, profile_id=args.profile
            )
        elif args.command == "run":
            payload, code = execute_run(args.config, args.task)
        elif args.command == "status":
            config = load_config(args.config)
            state = store.read_state(config.runtime_root, args.run_id)
            payload = {
                "schema_version": 1,
                "command": "status",
                "run_status": state.get("status"),
                "run": store.public_state(state),
            }
            code = 0
        elif args.command == "result":
            config = load_config(args.config)
            payload = store.read_result(config.runtime_root, args.run_id)
            code = 0
        elif args.command == "list":
            config = load_config(args.config)
            payload = {
                "schema_version": 1,
                "command": "list",
                "runs": store.list_runs(config.runtime_root, limit=args.limit),
            }
            code = 0
        elif args.command == "recover":
            payload, code = recover(args.config, apply=args.apply)
        elif args.command == "checkpoint":
            payload, code = checkpoint(
                args.config, args.task, checkpoint_id=args.checkpoint_id
            )
        elif args.command == "auto-recover":
            payload, code = auto_recover(
                args.config, args.task, max_recovery_attempts=args.max_attempts
            )
        else:  # pragma: no cover - argparse enforces the command
            raise TaskError("Unknown command")
    except BridgeError as exc:
        payload = {
            "schema_version": 1,
            "command": args.command,
            "status": "BLOCKED" if exc.exit_code == 5 else "FAILED",
            "error": exc.to_dict(),
            "timestamp": store.utc_now(),
        }
        code = exc.exit_code
        print(redactor.redact(exc.message), file=sys.stderr)
    except Exception as exc:  # pragma: no cover - defensive last resort
        _write_crash_log(args, exc)
        payload = {
            "schema_version": 1,
            "command": args.command,
            "status": "FAILED",
            "error": {
                "code": "bridge_internal_error",
                "category": "internal",
                "message": "Unexpected bridge failure; inspect the local crash log",
                "details": {"error_type": type(exc).__name__},
            },
            "timestamp": store.utc_now(),
        }
        code = 3
        print("Unexpected bridge failure", file=sys.stderr)

    print(
        json.dumps(
            redactor.redact_obj(payload),
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    return int(code)


def _write_crash_log(args: argparse.Namespace, exc: BaseException) -> None:
    try:
        config_path = getattr(args, "config", None)
        if config_path:
            config = load_config(config_path)
            root = Path(config.runtime_root)
        else:
            root = Path.cwd() / ".runtime"
        log_dir = root / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        text = SecretRedactor().redact(traceback.format_exc())
        with (log_dir / "bridge-crash.log").open(
            "a", encoding="utf-8", newline="\n"
        ) as handle:
            handle.write(f"\n--- {store.utc_now()} ---\n{text}\n")
    except Exception:
        return


if __name__ == "__main__":
    raise SystemExit(main())
