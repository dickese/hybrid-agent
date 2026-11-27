# G3_START_CODEX — Codex Integration Handoff

## Verified Environment
- **Upstream**: Augani/agent-orchestrator v0.7.1 (commit `8d9b897c49500e8e1b54ec8028352544db95618d`)
- **Container**: `hybrid-agent-g3:0.1` (Node 22 + Python 3.11 + OpenCode 2.2.0 + git)
- **Runtime**: Docker Desktop (WSL2 backend), persistent container `hybrid-agent-g3`
- **9Router**: Windows-hosted at `http://127.0.0.1:20128/v1` → container via `host.docker.internal:20128`
- **Shared Workspace**: Host-mounted at `D:/tools/hybrid-agent/.runtime/poc-g3/workspace` (Windows) / `/g3/workspace` (container) — persists across container recreation
- **State**: Persistent at `D:/tools/hybrid-agent/.runtime/poc-g3/state`
- **Evidence**: `D:/tools/hybrid-agent/.runtime/poc-g3/evidence`

## Container Lifecycle Commands
```bash
# Start persistent container (run once)
docker compose -f docker-compose.g3.yml up -d g3-orchestrator

# Verify container health
docker exec hybrid-agent-g3 python3 -B /work/agent-orchestrator-poc/plugins/agent-orchestrator/scripts/cli_agent_job.py doctor --config /work/poc/opencode_agents.json

# Stop container
docker compose -f docker-compose.g3.yml down

# View logs
docker logs hybrid-agent-g3

# Restart container (preserves workspace and state)
docker compose -f docker-compose.g3.yml restart g3-orchestrator
```

## Dashboard Access (Windows Host)
- **URL**: `http://127.0.0.1:8080/#token=<TOKEN>`
- **Token**: Retrieved from `/g3/state/dashboard.json` inside container (`docker exec hybrid-agent-g3 cat /g3/state/dashboard.json`)
- **Authentication**: Required (401 without token)
- **Host Binding**: Restricted to `127.0.0.1:8080` (not exposed to LAN)
- **Verified from Windows host**: Yes (direct port mapping `127.0.0.1:8080:8080`)
- **Features**: Project overview, job detail, progress events, questions, review status, blocker status, human intervention controls

### Dashboard Startup Commands
```bash
# Start persistent container (run once)
docker compose -f docker-compose.g3.yml up -d g3-orchestrator

# Start dashboard on container port 8080 (binds 0.0.0.0:8080 internally, mapped to 127.0.0.1:8080 on host)
docker exec -d -e AGENT_ORCHESTRATOR_HOME=/g3/state hybrid-agent-g3 python3 -B /work/agent-orchestrator-poc/plugins/agent-orchestrator/scripts/cli_agent_job.py dashboard-web --port 8080 --no-open

# Get token
docker exec hybrid-agent-g3 cat /g3/state/dashboard.json
# Open http://127.0.0.1:8080/#token=<TOKEN> in Windows browser
```

## Approved Worker Route & Execution Profile
- **CLI**: `opencode-9router` (custom profile in `poc/opencode_agents.json`)
- **Model**: `9router/agent-build`
- **Agent Profile**: `bridge-g3` (`.opencode/agents/bridge-g3.md`)
- **Coordination Channel**: Enabled — allows `python3 *channel.py event*` and `python3 *channel.py ask*`
- **Permissions**: Read/glob/grep/edit allowed; shell restricted to test commands + coordination channel

## Exact Codex Coordinator Invocation Commands
```bash
# Prerequisite: Start persistent container
docker compose -f docker-compose.g3.yml up -d g3-orchestrator

# 1. Create/select durable plan (plan-id: g3)
python3 poc/g3_codex_adapter.py create-plan \
  --task-file poc/g3_task.md \
  --plan-file poc/g3_plan.md \
  --plan-id g3 \
  --title "G3 Codex integration live test" \
  --executor "opencode-9router=9router/agent-build"

# 2. Dispatch exactly one approved OpenCode job (REQUIRES G3_AUTHORIZED=1)
G3_AUTHORIZED=1 python3 poc/g3_codex_adapter.py launch \
  --task-file poc/g3_task.md \
  --plan-id g3 \
  --checklist-item item-001 \
  --allowed-paths "src/**" "tests/**" \
  --max-changed-files 10 \
  --timeout-seconds 600

# 3. Observe execution status (poll or wait)
python3 poc/g3_codex_adapter.py wait --job-id <JOB_ID> --timeout-seconds 660 --poll-seconds 2

# 4. Inspect actual source changes (uses host-mounted shared workspace)
python3 poc/g3_codex_adapter.py verify \
  --workspace D:/tools/hybrid-agent/.runtime/poc-g3/workspace \
  --allowed-prefixes "src/" "tests/" \
  --required-files "src/slugify.py" "tests/__init__.py" "tests/test_slugify.py" \
  --test-cmd python3 -B -m unittest discover -s tests -t . -v

# 5. Run deterministic tests (included in verify)

# 6. Perform independent review (MANUAL - actual Codex)
#    Review diff + test results, then record verdict:
python3 poc/g3_codex_adapter.py record-review \
  --job-id <JOB_ID> \
  --verdict accepted|rejected \
  --reviewer codex-g3-live \
  --test-result "python3 -B -m unittest discover -s tests -t . -v: OK (Ran N tests)" \
  --notes "Independent Codex review: scoped files only, deterministic tests pass, no out-of-scope changes."

# 7. Verify plan advancement only after acceptance
python3 poc/g3_codex_adapter.py plan-status --plan-id g3
```

## Disposable Fixture Location
- **Task Contract**: `poc/g3_task.md`
- **Plan Definition**: `poc/g3_plan.md`
- **Scope Validation**: `poc/g3_validate_scope.py` (invoked automatically by adapter before launch)
  ```bash
  # Manual scope validation (optional - adapter does this automatically)
  docker exec hybrid-agent-g3 python3 /work/poc/g3_validate_scope.py /work/poc/g3_task.md '[\"--allow-path\", \"src/**\", \"--allow-path\", \"tests/**\"]'
  ```

## Task Acceptance Criteria
1. Worker creates `src/slugify.py` with `slugify(text: str) -> str`
2. Worker creates `tests/test_slugify.py` with 8 reference test cases
3. All deterministic tests pass (`python -B -m unittest discover -s tests -t . -v`)
4. Independent assertions (8 exact slugify cases) pass
5. **Actual Codex** performs independent review of diff + test results
6. Review recorded with `--test` evidence → acceptance
6. Plan advances to `complete`/`done` only after acceptance
7. Dashboard shows job progression from Windows host

## Review Procedure
1. **Codex reads** the actual diff (`git diff` in workspace) and test output
2. **Codex verifies** no out-of-scope changes, all 8 reference cases covered
3. **Codex decides** verdict: `accepted` or `rejected`
4. **Codex runs** `record-review` command with `--test` evidence (required for acceptance)
5. **System verifies** plan advancement only after `accepted` verdict
6. **Negative check**: rejected review without `--test` blocks plan advancement (automated in harness)

## Recovery Limitations
- **Container restart**: Preserves workflow state (plan, jobs, events in `/g3/state`)
- **Failed worker**: State = `failed`/`timed_out`/`scope_violated`; never auto-accepted
- **Retry budget**: Per-item limit of 3 (enforced by upstream)
- **Writer serialization**: `launch` rejects concurrent jobs for same checklist item
- **Partial changes**: Inspectable via `git status` in workspace after failure
- **Session recovery**: Task-level restart from verified checkpoint (not exact OpenCode session resume)
- **Scope violations**: Block automatic retry; user must inspect and authorize correction
- **User stop**: `cancel` command sets job state `cancelled`; workspace preserved for inspection

## Evidence References
- G0–G2: `POC_STATUS.md` (G0✅ G1✅ G2✅ LIVE_PASS)
- G1 offline: `poc/evidence/g1_offline.txt` (15/15 checks, 39/39 upstream tests)
- G2 profile: `poc/evidence/g2_resolved_command.txt`, `poc/evidence/g2_container_preflight.txt`
- G2 negative: `.runtime/poc-g2/evidence/g2_negative_summary.json`
- G2 live: `.runtime/poc-g2/evidence/g2_live_summary.json` (424.7s, 9 tests + 8 assertions, review accepted, plan done)
- Evidence index: `handoff/evidence/INDEX.md`

## Remaining Authorization Requirements
1. **G3_AUTHORIZED=1** for live inference call (one bounded OpenCode job via 9Router)
2. **Actual Codex** must perform the independent review (not automated)
3. Dashboard token from container logs for Windows host access

## Quick Start Checklist
- [ ] `docker compose -f docker-compose.g3.yml up -d g3-orchestrator`
- [ ] `docker logs hybrid-agent-g3` → note dashboard token
- [ ] Open `http://127.0.0.1:8080/#token=<TOKEN>` in Windows browser
- [ ] Run Codex coordinator commands above (steps 1–7) — **scope validation is automatic**
- [ ] Record review verdict as actual Codex (manual step, not automated)
- [ ] Verify plan advancement
- [ ] Confirm `G3_AUTHORIZED=1` was used only for the single live launch