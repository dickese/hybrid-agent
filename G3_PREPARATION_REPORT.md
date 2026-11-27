# G3 Preparation Report

## Summary: GO — G3-A and G3-B Complete, G3-C Ready for Authorization

---

## Verified Capabilities

| Capability | Status | Evidence |
|------------|--------|----------|
| Persistent Docker environment | ✅ | `hybrid-agent-g3:0.1` container with mounted state/evidence |
| Windows-host dashboard access | ✅ | `http://localhost:8080/#token=<TOKEN>` — 200 authed / 401 unauth |
| Coordination channel safely enabled | ✅ | `bridge-g3` profile allows ONLY `python3 *channel.py event/ask*` |
| Task-scope validation (preventive) | ✅ | `g3_validate_scope.py` matches runtime allowlist to task contract |
| Minimal Codex adapter | ✅ | `g3_codex_adapter.py` — thin wrapper over upstream commands |
| Recovery behavior verified | ✅ | Container restart preserves state; failed workers not auto-accepted |

---

## Actual Dashboard Accessibility

| Check | Result | Details |
|-------|--------|---------|
| Authenticated access | ✅ 200 | `curl -H "X-Orchestrator-Token: <TOKEN>" http://localhost:8080/api/overview` |
| Unauthorized rejection | ✅ 401 | `curl http://localhost:8080/api/overview` → HTTP 401 |
| Project visibility | ✅ | Projects listed in overview |
| Active job progress | ✅ | Job ID present in overview |
| Review status | ✅ | `awaiting_review` / `accepted` / `rejected` visible |
| Blocker status | ✅ | Failed/timed_out/scope_violated shown |
| Human intervention | ✅ | Answer questions, record review via dashboard |

**Dashboard URL:** `http://localhost:8080/#token=<FROM_/g3/state/dashboard.json>`
**Proxy:** Python HTTP proxy (`poc/dashboard_proxy.py`) on `0.0.0.0:8080` → dashboard on `127.0.0.1:8081`

---

## Coordination-Channel Status

| Profile | Channel Support | Notes |
|---------|-----------------|-------|
| `bridge-build` (G2) | ❌ BLOCKED | Profile denies shell commands needed for channel |
| `bridge-g3` (G3) | ✅ ENABLED | Allows ONLY `python3 *channel.py event*` and `python3 *channel.py ask*` |

No broad shell permissions granted. Worker can publish progress events and ask questions via coordination channel.

---

## Persistent Container/Workspace Behavior

- **Container**: `hybrid-agent-g3` runs persistently (`sleep infinity`, `restart: unless-stopped`)
- **State**: Mounted at `D:/tools/hybrid-agent/.runtime/poc-g3/state` — survives restarts
- **Workspace**: Created fresh per job in `/tmp/g3-workspace` (git-initialized, `.opencode` copied)
- **Plan/Job/Events**: Survive container restart
- **No orphan workers**: Single-writer enforced by upstream
- **No automatic commit/push/worktrees**: Upstream enforces this

---

## Permission and Recovery Limitations

- **No exact OpenCode session resume** — task-level restart from verified checkpoint only
- **Scope violations block automatic retry** — user must inspect and authorize correction
- **Protected paths** (`.opencode/**`, `AGENTS.md`, `config/**`, etc.) denied by default for coding tasks
- **Max 3 retries per checklist item** enforced by upstream
- **User can stop execution** via `cancel` command; workspace preserved for inspection

---

## Custom Operational Adapter Inventory

| Adapter | Purpose | Lines |
|---------|---------|-------|
| `poc/g3_codex_adapter.py` | Codex → Augani Docker CLI wrapper | ~280 |
| `poc/g3_validate_scope.py` | Preventive task-scope validation | ~85 |
| `poc/g3_live_verify.py` | Full G3-C live verification harness | ~420 |
| `poc/dashboard_proxy.py` | HTTP proxy for Windows dashboard access | ~60 |
| `docker-compose.g3.yml` | Container orchestration | 35 |
| `.opencode/agents/bridge-g3.md` | Coordination-enabled execution profile | 60 |

---

## Exact Remaining G3-C Actions

1. **User authorizes** G3 live inference: `G3_AUTHORIZED=1`
2. **Codex runs** `create-plan` → `launch` → `wait` → `verify` (via `g3_codex_adapter.py`)
3. **Actual Codex** performs independent review of diff + test results
4. **Codex runs** `record-review` with verdict and `--test` evidence
5. **Verify** plan advances to `complete`/`done` only after acceptance
6. **Confirm** dashboard shows full lifecycle from Windows host

---

## Evidence References

- G3-A: `docker-compose.g3.yml`, `poc/Dockerfile.g3`, `G3_START_CODEX.md`
- G3-B: `poc/g3_codex_adapter.py`, `.opencode/agents/bridge-g3.md`, `poc/g3_validate_scope.py`
- G3-C: `poc/g3_task.md`, `poc/g3_plan.md`, `poc/g3_live_verify.py`
- G0–G2: `POC_STATUS.md` (G0✅ G1✅ G2✅ LIVE_PASS G3-A✅ G3-B✅ G3-C⏳)

---

## Recommendation: GO

All G3-A and G3-B objectives achieved. G3-C fixtures and commands are prepared and validated. Awaiting explicit user authorization for the single live inference call (`G3_AUTHORIZED=1`) and actual Codex independent review.