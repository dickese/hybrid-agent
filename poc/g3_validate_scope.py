#!/usr/bin/env python3
"""G3 task-scope validation: preventive isolation matching runtime allowlist to task contract.

This script validates that the runtime allowlist exactly matches the task contract's
allowed_paths, and that protected paths (.opencode/**, AGENTS.md, skills, profiles, permissions)
are denied by default for ordinary coding tasks.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


# Protected paths are repository-relative (hybrid-agent repo).
# Task contract paths are workspace-relative (disposable workspace).
# These should not conflict. Protected paths only apply if the task tries to
# reference absolute paths or escape the workspace.
PROTECTED_PATHS = [
    ".opencode/**",
    "AGENTS.md",
    "handoff/**",
    "config/**",
    "docs/**",
    "scripts/**",
    "bridge/**",
    "poc/**",
    "examples/**",
    # Note: tests/** is NOT protected here because task contracts may allow workspace/tests/**
]


def validate_task_contract(task_file: Path) -> dict:
    """Parse task contract and extract allowed_paths from the '## Allowed Paths' section only."""
    text = task_file.read_text(encoding="utf-8")
    allowed = []
    in_allowed = False
    for line in text.splitlines():
        stripped = line.strip()
        # Look for the "## Allowed Paths" heading (markdown level 2)
        if stripped.lower() == "## allowed paths":
            in_allowed = True
            continue
        # Stop at next heading of same or higher level
        if in_allowed and stripped.startswith("##"):
            break
        if in_allowed:
            if stripped.startswith("#") or not stripped:
                continue
            if stripped.startswith("- "):
                allowed.append(stripped[2:].strip())
            elif stripped and not stripped.startswith("-"):
                # Non-list item in the section - stop parsing
                break
    return {"allowed_paths": allowed}


def validate_runtime_allowlist(launch_args: list[str]) -> list[str]:
    """Extract --allow-path arguments from launch command."""
    allowed = []
    i = 0
    while i < len(launch_args):
        if launch_args[i] == "--allow-path" and i + 1 < len(launch_args):
            allowed.append(launch_args[i + 1])
            i += 2
        else:
            i += 1
    return allowed


def check_protected_paths_denied(allowed_paths: list[str]) -> list[str]:
    """Check that no protected paths are in the allowlist."""
    violations = []
    for allowed in allowed_paths:
        for protected in PROTECTED_PATHS:
            if protected.endswith("/**"):
                prefix = protected[:-3]
                if allowed.startswith(prefix):
                    violations.append(f"Protected path allowed: {allowed} matches {protected}")
            elif allowed == protected:
                violations.append(f"Protected path allowed: {allowed}")
    return violations


def check_exact_match(contract_allowed: list[str], runtime_allowed: list[str]) -> tuple[bool, list[str]]:
    """Verify runtime allowlist exactly matches task contract (order-insensitive)."""
    contract_set = set(contract_allowed)
    runtime_set = set(runtime_allowed)
    missing = contract_set - runtime_set
    extra = runtime_set - contract_set
    issues = []
    if missing:
        issues.append(f"Contract paths missing from runtime: {sorted(missing)}")
    if extra:
        issues.append(f"Runtime paths not in contract: {sorted(extra)}")
    return len(issues) == 0, issues


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: g3_validate_scope.py <task_file> <launch_args_json>", file=sys.stderr)
        return 1

    task_file = Path(sys.argv[1])
    launch_args = json.loads(sys.argv[2])

    contract = validate_task_contract(task_file)
    runtime_allowed = validate_runtime_allowlist(launch_args)

    print(f"Contract allowed_paths: {contract['allowed_paths']}")
    print(f"Runtime --allow-path:   {runtime_allowed}")

    # Check protected paths
    protected_violations = check_protected_paths_denied(runtime_allowed)
    if protected_violations:
        print("❌ PROTECTED PATH VIOLATIONS:", file=sys.stderr)
        for v in protected_violations:
            print(f"  {v}", file=sys.stderr)
        return 1

    # Check exact match
    ok, issues = check_exact_match(contract['allowed_paths'], runtime_allowed)
    if not ok:
        print("❌ SCOPE MISMATCH:", file=sys.stderr)
        for issue in issues:
            print(f"  {issue}", file=sys.stderr)
        return 1

    print("✅ Scope validation passed: runtime allowlist matches task contract exactly")
    return 0


if __name__ == "__main__":
    sys.exit(main())