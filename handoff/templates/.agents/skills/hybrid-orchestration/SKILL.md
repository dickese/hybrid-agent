# Hybrid Orchestration Skill

## Description
Orchestrate hybrid agent workflows using the synchronous Python bridge to dispatch
coding tasks to OpenCode workers, with Codex as the planning/review/acceptance authority.

## When to Use
- Planning a coding task that requires file edits in a workspace
- Dispatching work to an OpenCode coder or explorer profile
- Reviewing bridge results and deciding acceptance
- Recovering from failed or interrupted runs

## Bridge Interface

### Create Task Contract
```json
{
  "schema_version": 1,
  "task_id": "UNIQUE-ID",
  "workspace_id": "demo",
  "profile": "coder",
  "expected_branch": "master",
  "objective": "Description of the coding task",
  "references": ["file1.py", "file2.py"],
  "allowed_paths": ["file1.py"],
  "acceptance_criteria": ["python -B test_file1.py exits 0"],
  "timeout_seconds": 300
}
```

### Dispatch
```powershell
python -m bridge.cli run --config config/bridge.local.json --task <task.json>
```

### Interpret Result
- `status: COMPLETED` → worker finished; independently verify before accepting
- `status: FAILED` → check `error`, `summary`; do not retry with partial edits
- `status: TIMED_OUT` → worker killed; check for partial changes
- `status: BLOCKED` → policy/scope/auth violation; read `error` for details
- `scope_ok: false` → worker edited outside allowed_paths; DO NOT accept

### Acceptance Workflow
1. Read result JSON from stdout
2. Run acceptance tests independently (e.g., `python -B test_add.py`)
3. Inspect `git diff` in the workspace
4. Verify `scope_ok: true` and `changed_files` match expectations
5. If all pass → mark ACCEPTED via checkpoint
6. If any fail → record failure, do not auto-retry writers

### Recovery
```powershell
python -m bridge.cli recover --config config/bridge.local.json          # dry-run
python -m bridge.cli recover --config config/bridge.local.json --apply  # reconcile
```

## Profiles
- `coder`: write access, uses bridge-coder agent, can edit files within scope
- `explorer`: read-only access, uses bridge-explorer agent, cannot modify files
