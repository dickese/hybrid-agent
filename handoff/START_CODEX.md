# Codex Handoff — START HERE

**Status**: READY_FOR_CODEX
**Workspace**: `D:\tools\hybrid-agent`
**Generated**: 2026-11-26T11:30 UTC
**Python**: 3.11.0 | **OpenCode**: v2.2.0 | **Codex CLI**: codex-cli 0.165.0

## Approved Routes (Six Specialized Agents)

| Logical Agent | Model Route | OpenCode Profile | Access | Purpose |
|---------------|-------------|------------------|--------|---------|
| `agent-fast` | `9router/agent-fast` | `bridge-fast` | write | Lightweight execution, preflight, small scripts |
| `agent-build` | `9router/agent-build` | `bridge-build` | write | General coding, features, bugs, refactoring |
| `agent-heavy` | `9router/agent-heavy` | `bridge-heavy` | write | Complex reasoning, architecture, migrations |
| `agent-review` | `9router/agent-review` | `bridge-review` | read_only | Independent code review, regression analysis |
| `agent-vision` | `9router/agent-vision` | `bridge-vision` | write | Screenshot analysis, UI/UX, visual regression |
| `agent-docs` | `9router/agent-docs` | `bridge-docs` | write_docs_only | Documentation, specs, handoffs, summarization |
| Legacy `explorer` | `9router/deepseek-v4.1-flash-free` | `bridge-explorer` | read | Read-only exploration (deprecated) |
| Legacy `coder` | `9router/deepseek-v4.1-flash-free` | `bridge-coder` | write | General coding (deprecated) |

- Provider: `9router` at `http://127.0.0.1:20128/v1`
- Credential: `.runtime/secrets/9router.key` (env `NINE_ROUTER_KEY`)
- All six combos registered in 9Router and OpenCode; qualification status: **NOT_VERIFIED**

## Gates

| Gate | Status | Evidence |
|------|--------|----------|
| A0 Host preflight | PASS | `.runtime/evidence/a0-*.md` |
| A1 Runtime ready | PASS | `.runtime/evidence/a1-*.md`, `a1-live-health.json` |
| A2 Bridge ready | PASS | `.runtime/evidence/a2-live-smoke.md`, `a2-live-smoke-result.json` |
| A3 Guardrails ready | PASS | `.runtime/evidence/a3-failure-matrix.md` (69 tests, 13/13 cases) |
| A4 Recovery ready | PASS | `.runtime/evidence/a4-recovery-drill.md` (8 recovery tests) |
| A5 Handoff ready | PASS | This package |
| B0 Codex boundary | NOT_RUN | Codex-only |
| B1 Hybrid activation | NOT_RUN | Codex-only |
| B2 End-to-end fixture | NOT_RUN | Codex-only |

## Commands

### Offline verification (run first)
```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify-handoff.ps1
```

### Bridge health (offline)
```powershell
python -m bridge.cli health --config config/bridge.local.json
```

### Bridge health (live — uses one model call, specify profile)
```powershell
python -m bridge.cli health --config config/bridge.local.json --live --profile agent-build
```

### Create fresh fixture
```powershell
powershell -ExecutionPolicy Bypass -File scripts/create-fixture.ps1 -Name b2-codex
```

### Run a task with explicit agent selection
```powershell
# General implementation (default)
python -m bridge.cli run --config config/bridge.local.json --task task.json

# Explicit agent via task contract "profile" field:
# { "profile": "agent-heavy", ... }
python -m bridge.cli run --config config/bridge.local.json --task task-heavy.json
```

### Check status / result
```powershell
python -m bridge.cli status --config config/bridge.local.json --run-id <id>
python -m bridge.cli result --config config/bridge.local.json --run-id <id>
python -m bridge.cli list   --config config/bridge.local.json
```

### Recovery
```powershell
python -m bridge.cli recover --config config/bridge.local.json          # dry-run
python -m bridge.cli recover --config config/bridge.local.json --apply  # reconcile
```

### Checkpoint (for approved dirty baseline)
```powershell
python -m bridge.cli checkpoint --config config/bridge.local.json --task task.json --checkpoint-id ckpt-001
```

## Result JSON Fields

`status`: COMPLETED | FAILED | TIMED_OUT | BLOCKED
`scope_ok`: true if changes within allowed_paths
`exit_code`: 0=COMPLETED, 2=invalid, 3=worker-fail, 4=timeout, 5=policy/lock
COMPLETED ≠ ACCEPTED — Codex must independently verify and accept.

## Agent Invocation Examples

### agent-fast (lightweight)
```json
{
  "profile": "agent-fast",
  "objective": "Run preflight checks and analyze logs",
  "allowed_paths": ["logs/", "scripts/preflight.ps1"]
}
```

### agent-build (general coding)
```json
{
  "profile": "agent-build",
  "objective": "Implement user authentication feature",
  "allowed_paths": ["src/auth/", "tests/auth/"]
}
```

### agent-heavy (complex reasoning)
```json
{
  "profile": "agent-heavy",
  "objective": "Analyze and refactor distributed transaction logic",
  "allowed_paths": ["src/transactions/", "src/state/"]
}
```

### agent-review (independent review)
```json
{
  "profile": "agent-review",
  "objective": "Review PR #123 for security and compliance",
  "allowed_paths": ["src/", "tests/"]
}
```

### agent-vision (multimodal)
```json
{
  "profile": "agent-vision",
  "objective": "Analyze screenshot for UI regression",
  "allowed_paths": ["screenshots/", "docs/ui/"]
}
```

### agent-docs (documentation)
```json
{
  "profile": "agent-docs",
  "objective": "Create runbook for deployment procedure",
  "allowed_paths": ["docs/runbooks/", "docs/specs/"]
}
```

## Templates to Activate

- `handoff/templates/AGENTS.md` — merge into project AGENTS.md
- `handoff/templates/.agents/skills/hybrid-orchestration/SKILL.md`
- `handoff/templates/.codex/agents/` — planner, reviewer, verifier

## Documentation References

- `docs/AGENT_ROUTING_GUIDE.md` — Routing rules, capabilities, permissions
- `docs/AGENT_RECOVERY_GUIDE.md` — Recovery budgets, procedures, escalation
- `docs/AGENT_MODEL_SETTINGS.md` — Model settings, limits, verification status
- `config/agent-registry.json` — Machine-readable agent definitions
- `config/routing-policy.json` — Deterministic routing rules
- `config/recovery-policy.json` — Per-agent recovery configuration

## Known Limitations

1. OpenCode shared background service lacks `NINE_ROUTER_KEY`; bridge uses `--standalone`.
2. Bridge diff inspection detects scope violations but is not sandbox enforcement.
3. `oc/` model IDs in 9Router proxy through OpenCode cloud (429 on free tier); use `ag/` or `ollama/` upstream models in `opencode.json` modelID.
4. Ollama-backed models may be slow (>5min); `ag/gemini-3.8-flash` is fastest tested.
5. **All six specialized agents: qualification_status = NOT_VERIFIED** — require live verification before operational use.
6. Agent-vision vision fallback forbidden; requires verified image-input capability.
7. Effective output limits may be lower than targets (9Router reports max_completion_tokens=8192 for most combos).
8. Thinking effort control is 9Router-internal; Low/Medium/High not uniformly mapped across providers.
9. Route health tracked at combo level; individual upstream models not isolated.

## Codex-Only Steps (B0–B2)

1. Read this file and `handoff/manifest.json`.
2. Run `scripts/verify-handoff.ps1` — confirm PASS.
3. Create fresh fixture: `scripts/create-fixture.ps1 -Name b2-codex`.
4. Inspect and activate templates from `handoff/templates/`.
5. Run one bridge task from Codex context (also satisfies B0 boundary check).
6. Independently verify: test exit code, git diff, native review.
7. Accept fixture task. Stop at P06 user approval gate.
