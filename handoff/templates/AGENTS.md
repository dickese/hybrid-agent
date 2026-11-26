# Hybrid Agent Orchestration

## Bridge Commands

The synchronous Python bridge at `bridge/` dispatches tasks to OpenCode workers.
Codex is the orchestrator and task acceptance authority.

### Task Workflow

1. Create a task JSON contract (see `examples/smoke-task.json`).
2. Run: `python -m bridge.cli run --config config/bridge.local.json --task <task.json>`
3. stdout is exactly one JSON object with `status`, `scope_ok`, `changed_files`, `summary`.
4. `COMPLETED` means the worker finished. It is NOT `ACCEPTED`.
5. Independently verify: run acceptance tests, inspect diff, review scope.
6. Only the Codex orchestrator marks a task ACCEPTED.

### Exit Codes

- 0: COMPLETED (not ACCEPTED)
- 2: Invalid task or config (reject before spawn)
- 3: Worker failure (nonzero exit, malformed output, transient error)
- 4: Timeout (worker killed, descendants cleaned)
- 5: Policy violation, lock conflict, or blocker (scope, auth, dirty baseline)

### Safety Rules

- Never auto-rollback worker edits; preserve diff evidence.
- Never retry a writer with partial edits.
- Never mark ACCEPTED without independent verification.
- Credentials are injected via env; never in config, logs, or artifacts.
- Use disposable fixtures only; never modify real project repos during bootstrap.
- Recovery: `python -m bridge.cli recover --config config/bridge.local.json`

### Skill Reference

See `.agents/skills/hybrid-orchestration/SKILL.md` for the full orchestration skill.
