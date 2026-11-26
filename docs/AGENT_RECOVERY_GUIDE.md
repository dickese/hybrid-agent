# Agent Recovery Guide

## Overview

All six specialized agents share a common recovery engine implementation with configurable per-agent policies. This guide describes the recovery procedures, budgets, and operational commands.

## Recovery Budgets

| Agent | Consecutive Retries | Total Recovery Retries/Task |
|-------|---------------------|------------------------------|
| agent-fast | 2 | 3 |
| agent-build | 3 | 5 |
| agent-heavy | 2 | 4 |
| agent-review | 2 | 3 |
| agent-vision | 2 | 3 |
| agent-docs | 2 | 3 |

Backoff schedule: 2s, 5s, 15s (configurable in `config/recovery-policy.json`)

## Recovery Procedure

For retryable failures, the bridge executes:

1. **Confirm previous invocation is no longer active** — Check process state via PID/creation time
2. **Acquire single-writer lock** — Repository-level lock prevents concurrent writers
3. **Read persistent checkpoint** — Load approved baseline fingerprint
4. **Reconcile filesystem state** — Compare actual vs. checkpoint; identify completed/incomplete operations
5. **Validate route health and budget** — Check consecutive failures, cooldown, quota reset time
6. **Resume exact session** — Only when workspace, profile, route, and context are compatible
7. **Continue remaining scope** — Task contract specifies `resume_session_id` and `checkpoint_id`

## Failure Classification

Supported failure codes (see `config/recovery-policy.json` for full list):

| Category | Codes | Retryable |
|----------|-------|-----------|
| Transient | NETWORK_TRANSIENT, GATEWAY_TRANSIENT, RATE_LIMITED | Yes (per agent policy) |
| Quota | QUOTA_EXHAUSTED | Agent-dependent |
| Auth/Permission | AUTH_FAILURE, PERMISSION_DENIED | **Never** |
| Schema/Model | MODEL_NOT_FOUND, REQUEST_SCHEMA_INCOMPATIBLE, TOKEN_LIMIT_MISMATCH, CONTEXT_OVERFLOW | **Never** |
| Execution | TOOL_EXECUTION_FAILED, SESSION_NOT_FOUND, UNKNOWN_EXECUTION_STATE | **Never** |
| Infrastructure | NO_COMPATIBLE_ROUTE, RETRY_EXHAUSTED | **Never** |

**Explicitly detected patterns:**
- `Invalid 9router/openai-compatible-chat stream event`
- Upstream 429 quota exhaustion
- Cached quota blocks
- Persistent upstream 404 errors
- Incompatible message schemas
- Incompatible output token limits
- Router-level success without client-side stream completion

## Route Health & Circuit Breaker

Each agent tracks:
- Logical agent ID
- Requested combo route (e.g., `9router/agent-build`)
- Actual upstream model (when available)
- Qualification status
- Consecutive failures
- Last failure classification
- Cooldown timestamp
- Quota reset time
- Sanitized evidence

**Quarantine triggers:**
- Persistent schema failures
- Model availability failures
- Token limit failures
- Streaming failures (circuit breaker threshold)

**Important**: When actual upstream identity cannot be established, failures are tracked at the visible combo level. The system does not claim individual upstream model isolation.

## Escalation Recommendations

| Current Agent | Escalation Target |
|---------------|-------------------|
| agent-fast | agent-build |
| agent-build | agent-heavy |
| agent-heavy | Codex Orchestrator |
| agent-review | Native Codex Reviewer |
| agent-vision | Approved vision-capable alternative or Codex |
| agent-docs | agent-build with documentation-only permissions |

**Constraints:**
- Escalation is a structured recommendation, not automatic invocation
- Permissions are not expanded during escalation
- Independent reviewer (agent-review) is never transferred to implementation role
- Clean task session from verified checkpoint preferred over history transfer

## Operational Commands

### Dry-run recovery (inspect only)
```powershell
python -m bridge.cli recover --config config/bridge.local.json
```

### Apply recovery (reconcile interrupted runs)
```powershell
python -m bridge.cli recover --config config/bridge.local.json --apply
```

### Create approved checkpoint for dirty baseline
```powershell
python -m bridge.cli checkpoint --config config/bridge.local.json --task <task.json> --checkpoint-id <id>
```

### Run task with explicit session resumption
```json
{
  "task_id": "TASK-001-C1",
  "parent_task_id": "TASK-001",
  "checkpoint_id": "ckpt-TASK-001-20261126T120000Z",
  "resume_session_id": "ses_abc123...",
  "profile": "agent-build",
  ...
}
```

### Check run status
```powershell
python -m bridge.cli status --config config/bridge.local.json --run-id <run_id>
```

### Read run result
```powershell
python -m bridge.cli result --config config/bridge.local.json --run-id <run_id>
```

### List recent runs
```powershell
python -m bridge.cli list --config config/bridge.local.json --limit 20
```

## Bootstrap Self-Recovery

If the current bootstrap session encounters a streaming failure:

1. Let the current session become idle
2. Open a **separate PowerShell terminal**
3. Execute:
   ```powershell
   python -m bridge.cli recover --config config/bridge.local.json --apply
   ```
4. The recovery controller operates outside the interrupted inference turn
5. No recursive invocation of the active OpenCode session

## Persistent State

- Retry counters persist across process restarts (stored in `workflow.json`)
- Total recovery counters are **not reset** when switching routes or sessions
- Global bootstrap recovery budget is separate from implementation correction budget
- Infrastructure recovery is separate from implementation correction

## Constraints

- Never blindly replay potentially non-idempotent tool operations
- Never retry authentication or permission failures automatically
- If session history exceeds context budget, use supported compaction or checkpoint-based rotation
- Return BLOCKED if execution state cannot be safely reconciled
- Prevent retry multiplication across 9Router, OpenCode, and CLI Bridge layers

## Related Files

- `config/recovery-policy.json` — Complete recovery configuration
- `config/agent-registry.json` — Per-agent recovery policy references
- `docs/AGENT_ROUTING_GUIDE.md` — Routing and escalation
- `docs/AGENT_MODEL_SETTINGS.md` — Model limits affecting recovery