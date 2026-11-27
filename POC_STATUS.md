# Augani/agent-orchestrator PoC Status

**Upstream Commit:** `8d9b897c49500e8e1b54ec8028352544db95618d` (tag `v0.7.1`)  
**Started:** 2026-11-27  
**Status:** G0✅ G1✅ G2✅ **LIVE_PASS** G3-A✅ **READY** G3-B✅ **OFFLINE_VERIFIED** G3-C **G3_LIVE_PASS**

**G4:** G4-A complete. G4-B0 passed the patch-output-only bootstrap checks. G4-B is **G4_B_REJECTED** because the one authorized worker patch failed staged applicability checks. G4-C through G4-E are pending. See [G4 implementation plan](handoff/G4_PLAN.md) and [G4-B evidence](handoff/evidence/INDEX.md#g4-b0-bootstrap-and-g4-b-review).

---

## G0 — Environment Feasibility

### WSL Status
| Item | Status | Details |
|------|--------|---------|
| WSL Version | ✅ Available | WSL 3.0.5.0 (WSL 2 kernel 6.18.58.1) |
| Installed Distributions | ⚠️ **docker-desktop only** | No Ubuntu/Debian/standard Linux distro installed |
| WSL Python/Git/Node | ❌ Not available | docker-desktop is minimal, no bash/python3/git/node |

**Blocker (G0):** No standard Linux distribution installed in WSL. The `docker-desktop` distribution is minimal and lacks bash, python3, git, node.

**Required User Action for native WSL2:** Install a WSL distribution (e.g., Ubuntu 24.04):
```powershell
wsl --install Ubuntu-24.04
```
Then restart terminal and verify:
```powershell
wsl -- bash -c "python3 --version && git --version && node --version"
```

**Note:** Do not install WSL or modify system-wide networking automatically per instructions.

**Alternative isolated Linux environment:** Docker Desktop (WSL2 backend) is present and used for G1/G2 container runs. No host mutation.

### Windows Host Environment
| Component | Status | Version/Details |
|-----------|--------|-----------------|
| 9Router Gateway | ✅ Running | `http://127.0.0.1:20128/v1` (TCP 20128 LISTENING on 0.0.0.0) |
| OpenCode CLI | ⚠️ **Version mismatch** | `opencode v2.2.0` — upstream profile uses deprecated `opencode --cwd --quiet --output-format --prompt`; v2.2.0 requires `opencode run --model --format` subcommand |
| Codex CLI | ✅ Installed | `codex-cli 0.165.0` |
| Python (Windows) | ✅ Available | 3.11.0 |
| Git (Windows) | ✅ Available | Standard Git for Windows |

### Upstream Repository (v0.7.1)
| Item | Status | Details |
|------|--------|---------|
| Commit | ✅ Pinned | `8d9b897c49500e8e1b54ec8028352544db95618d` (tag `v0.7.1`) |
| Test Suite | ✅ **EXISTS** | 39 tests total: `test_cli_agent_job.py` (30+), `test_dashboard_server.py` (20+) |
| CI Configuration | ✅ Exists | `.github/workflows/ci.yml` — `ubuntu-latest`, Python 3.11, `python3 -m unittest discover` |
| Plugin Structure | ✅ Codex plugin | `.agents/plugins/marketplace.json` references `./plugins/agent-orchestrator` |

**Reconciliation:** The earlier assessment stated "upstream has no test suite" — **incorrect**. The upstream has a comprehensive test suite (39 tests) covering custom CLI adapters, question channel round-trip, project feedback lifecycle, placeholder validation, built-in profiles, workspace preferences, cross-harness team policy, cursor sandbox + subagent deny, antigravity JSONL stdin, model discovery, quality route + review gate, explicit executor selection, executor pool exhaustion + Terra fallback, Astra expensive-executor approval, automatic strategy pools, model router with task evidence, cost plan checkpoint, dashboard reuse, context budget enforcement.

### WSL Connectivity to Windows 9Router
| Check | Status | Details |
|-------|--------|---------|
| Windows 9Router bind | ✅ | `0.0.0.0:20128` |
| Container → 9Router | ✅ | `host.docker.internal:20128` returns HTTP 200, 106 models, all 6 agent combos present |
| Native WSL2 → 9Router | ⏳ | Pending Ubuntu install (requires user action) |

---

## G1 — Offline Upstream Workflow Verification

**Status:** ✅ **OFFLINE_PASS** (15/15 checks)  
**Environment:** Disposable `python:3.11-slim` container + git  
**Runner:** Unmodified `cli_agent_job.py` at pinned commit  
**Evidence:** `poc/evidence/g1_offline.txt`

### Upstream Tests in Container
- **39/39 PASS** (`python3 -m unittest discover -s plugins/agent-orchestrator/tests -v`)

### Custom Fake-Worker Workflow Checks (all PASS)
| Check | Scope |
|-------|-------|
| A1 Durable plan creation | Plan persisted with checklist items |
| A2 Job execution + structured progress + persistent logs | Worker progress events recorded in `channel/events/`, stdout/stderr logged |
| A3 Review gate: accept requires `--test`, plan advances, immutable | Re-review rejected after acceptance |
| A4 Coordinator-restart state recovery | Fresh process reads `plan-checkpoint` correctly |
| B1 Project mode captured; no extra worktrees | `workspace_mode=project`, worktree count = 1 |
| C1 Single-writer protection | Concurrent launch rejected with clear error |
| C2 Process termination via cancel | `cancel` sets state `cancelled` |
| D1 Timeout handling | Worker terminated, state `timed_out` |
| E1 Rejected review blocks plan item | Item state `blocked` |
| F1 Per-item retry limit (3) enforced | 4th attempt rejected |
| G1 Worker question → human answer round-trip | Channel `ask`/`answer` works |
| H1 Orchestrator feedback request → answer lifecycle | Feedback recorded, history persisted |
| I1 Checklist dependency gating | Dependent job blocked until prior accepted |
| J1 Scope violation detection | Out-of-scope write detected, worker stopped (`scope_violated`) |
| K1 Dashboard auth + internal reachability | Authenticated 200, unauth 401, projects listed |

**Note:** All checks used deterministic fake workers via the upstream custom CLI profile mechanism. No network, no inference, no Codex.

---

## G2 — Minimal OpenCode + 9Router Integration

**Status:** ✅ **LIVE_PASS** (2026-11-27T01:58:43Z) — one authorized live inference call completed, all mandatory checks passed.

### Profile Compatibility Finding
| Upstream Built-in `opencode` Profile | OpenCode v2.2.0 Reality |
|--------------------------------------|--------------------------|
| `opencode --cwd --quiet --output-format --prompt` | `opencode run --model --format` subcommand |
| **Result** | **Incompatible** — requires custom adapter |

### Custom `opencode-9router` Profile (✅ Validated)
```json
{
  "agents": {
    "opencode-9router": {
      "display_name": "OpenCode v2.2.0 via 9Router (PoC)",
      "description": "Mirrors the verified Hybrid Agent invocation: opencode --standalone run --format json <prompt> --model <route> --agent <profile>.",
      "maturity": "preview",
      "argv": ["opencode", "--standalone", "run", "--format", "json", "{prompt_text}"],
      "prompt_transport": "arg",
      "model_args": ["--model", "{model}"],
      "cli_agent_args": ["--agent", "{cli_agent}"],
      "models": ["9router/agent-build"],
      "executable_candidates": ["opencode", "opencode.exe"]
    }
  }
}
```
**Validation:** `profiles --config` ✅; `doctor` ✅ (available, executable `/usr/local/bin/opencode`, version `v2.2.0`)

### Resolved Worker Command (from unmodified runner + custom profile)
```bash
opencode --standalone run --format json "<prompt>" --model 9router/agent-build --agent bridge-build
```
**Flag order verified** via `g2_show_command.py` (no inference). Matches the proven Hybrid Agent invocation.

### 9Router Connectivity (✅ Verified)
| Check | Result |
|-------|--------|
| Windows `127.0.0.1:20128/v1/models` | HTTP 200, 106 models, all 6 agent combos |
| Container `host.docker.internal:20128/v1/models` | HTTP 200, 106 models, agent-build present |
| OpenCode `models` in container | Lists all 6 `9router/*` routes |

### Provider Config Finding
The **live** 9Router provider (with credentials) is defined in the **global** OpenCode config at `~/.config/opencode/opencode.json` (v2 schema: `provider`/`npm`/`options.apiKey`). The project `opencode.json` uses a legacy `providers` schema and is not the active config for the 9Router route. The PoC container mirrors the global config read-only, adapting only the baseURL to `host.docker.internal` inside the ephemeral container — **no host config changes**.

### Negative-Path Adapter Preflight (✅ PASS, no inference)
**Evidence:** `.runtime/poc-g2/evidence/g2_negative_summary.json`

| Aspect | Result |
|--------|--------|
| Custom profile resolution | ✅ |
| Workspace `bridge-build` agent discovery | ✅ (cwd=`/g2/workspace` with `.opencode/agents/bridge-build.md`) |
| Real OpenCode process spawn + cwd | ✅ |
| Local model rejection for `9router/__nonexistent__` | `provider.no-route` — **no inference** |
| Job state | `failed` (graceful) |
| Workspace after | Clean |

### Dashboard Accessibility
| Aspect | Status |
|--------|--------|
| Internal (container) | ✅ HTTP 200 with token; unauth 401; projects listed; job id present in overview |
| Windows host → container | ❌ **BLOCKED** — dashboard binds `127.0.0.1` inside container; Docker port mapping can't reach container loopback. Requires native WSL2 with localhost forwarding for Windows access. |

### Known Limitation — Channel Progress & Questions
The `bridge-build` execution profile (`.opencode/agents/bridge-build.md`) explicitly **denies** `shell` action except `python -B *`, `pwsh *`, test commands. The upstream coordination preamble instructs workers to run `python3 {channel_path} event ...`. This is denied by the profile, so:
- Worker progress events will **not** be emitted (job lifecycle events still captured)
- Worker questions via channel will **not** work
- Independent review workflow still functions via `record-review`

No permission shim added per scope restrictions.

---

## G2 — Live Run Artifacts (✅ COMPLETED)

| Artifact | Purpose |
|----------|---------|
| `poc/g2_live_verify.py` | Orchestrates create-plan → launch → wait → independent file/test verification → record-review → plan-status → dashboard check |
| `poc/g2_task.md` | Deterministic task packet (9 required sections, exact slugify spec) |
| `poc/g2_plan.md` | Single-item checklist plan |
| `poc/g2_negative_check.py` | Negative-path integration test (run & passed) |
| `poc/g2_preflight.sh` | Container environment verification script (run & passed) |
| `poc/g2_dashboard_check.py` | Dashboard query helper |
| `poc/g2_show_command.py` | Resolved argv printer |
| `poc/g2_probe_router.py` | 9Router connectivity probe |
| `poc/g2_validate_task.py` | Task packet validator (PASS) |
| Workspace | `.runtime/poc-g2/workspace/` — git init, `bridge-build.md` committed |
| State | `.runtime/poc-g2/state/` — fresh per run |
| Evidence | `.runtime/poc-g2/evidence/` and `poc/evidence/` |

### Exact Live Launch Command (executed with `G2_AUTHORIZED=1`)
```bash
docker run --rm \
  -v "D:/tools/hybrid-agent:/work:ro" \
  -v "D:/tools/hybrid-agent/.runtime/poc-g2:/g2" \
  -v "C:/Users/ANH DUC/.config/opencode/opencode.json:/run/opencode-global.json:ro" \
  -v "D:/tools/hybrid-agent/.runtime/secrets/9router.key:/run/secrets/9router.key:ro" \
  -e RUNNER=/work/agent-orchestrator-poc/plugins/agent-orchestrator/scripts/cli_agent_job.py \
  -e CONFIG=/work/poc/opencode_agents.json \
  -e G2_BASE=/g2 \
  -e G2_CLI=opencode-9router \
  -e G2_MODEL=9router/agent-build \
  -e G2_CLI_AGENT=bridge-build \
  -e G2_AUTHORIZED=1 \
  hybrid-agent-g2:0.2 \
  python3 -B /work/poc/g2_live_verify.py
```
**What this did (one inference):**
1. Created plan `g2` with executor `opencode-9router=9router/agent-build`
2. Launched job with `--model 9router/agent-build --agent bridge-build`
3. Waited up to 10 min, then independently verified:
   - Changed files only under `src/`, `tests/`, `.opencode/`
   - `python -B -m unittest discover -s tests -t . -v` passes (9 tests)
   - Independent assertions of 8 exact slugify cases pass
4. Recorded independent review with `--test` evidence → acceptance
5. Plan advanced to `complete`/`done`
6. Queried upstream dashboard (internal) → 200/401 + job id present
7. Wrote `g2_live_summary.json` with full evidence

### Live Run Summary
| Metric | Result |
|--------|--------|
| Job ID | `opencode-9router-20261127-015136-134b63` |
| Duration | 424.7 seconds |
| Terminal State | `succeeded` |
| Files Created | `src/slugify.py`, `tests/__init__.py`, `tests/test_slugify.py` |
| Deterministic Tests | 9/9 PASS |
| Independent Assertions | 8/8 PASS |
| Review Verdict | `accepted` (reviewer: `codex-poc-independent`) |
| Plan State After | `complete` / `done` |
| Dashboard Auth | 200 (authed) / 401 (unauth) |
| Dashboard Job ID | Present in overview |
| Evidence File | `.runtime/poc-g2/evidence/g2_live_summary.json` |

---

## G3-A — Operational Docker Environment

**Status:** ✅ **READY** — Persistent container with dashboard access from Windows host via proxy (localhost-only binding).

### Docker Environment
| Component | Status | Details |
|-----------|--------|---------|
| Image | ✅ Built | `hybrid-agent-g3:0.1` (Node 22 + Python 3.11 + OpenCode 2.2.0) |
| Container | ✅ Persistent | `hybrid-agent-g3` with `restart: unless-stopped` |
| Workspace | ✅ Host-mounted | `D:/tools/hybrid-agent:/work:ro` (read-only upstream) |
| Shared Workspace | ✅ Persistent | `D:/tools/hybrid-agent/.runtime/poc-g3/workspace` ↔ `/g3/workspace` (survives restarts) |
| State | ✅ Persistent | `D:/tools/hybrid-agent/.runtime/poc-g3/state` (survives restarts) |
| Evidence | ✅ Persistent | `D:/tools/hybrid-agent/.runtime/poc-g3/evidence` |
| Dashboard | ✅ Windows-accessible | Proxy: `0.0.0.0:8080` → `127.0.0.1:8081`; Docker maps `127.0.0.1:8080:8080` |
| 9Router | ✅ Container reachable | `host.docker.internal:20128` verified |
| Offline Bootstrap | ✅ Available | `poc/g3_bootstrap.py` (idempotent, no inference) |

### Dashboard Access Verification (Windows Host)
| Check | Status | Details |
|-------|--------|---------|
| Authenticated access | ✅ | HTTP 200 with token from container logs |
| Unauthorized rejection | ✅ | HTTP 401 without token |
| Project visibility | ✅ | Projects listed in overview |
| Active job progress | ✅ | Job ID present in overview |
| Review status | ✅ | `awaiting_review` / `accepted` / `rejected` visible |
| Blocker status | ✅ | Failed/timed_out/scope_violated shown |
| Human intervention | ✅ | Answer questions, record review via dashboard |
| Host binding | ✅ | Restricted to `127.0.0.1` (no LAN exposure) |
| Proxy validation | ✅ | Host/Origin headers preserved, auth tokens passed through |

**Dashboard URL:** `http://127.0.0.1:8080/#token=<FROM_CONTAINER_LOGS>`

### Container Lifecycle
- Start: `docker compose -f docker-compose.g3.yml up -d g3-orchestrator`
- Stop: `docker compose -f docker-compose.g3.yml down`
- Restart: `docker compose -f docker-compose.g3.yml restart g3-orchestrator` (preserves workspace/state)
- Logs: `docker logs hybrid-agent-g3`
- Bootstrap: `docker compose -f docker-compose.g3.yml exec g3-orchestrator python3 /work/poc/g3_bootstrap.py --verify-only`
- State survives container restart (mounted volume)

---

## G3-B — Codex Integration Adapter

**Status:** ✅ **OFFLINE_VERIFIED** — Minimal adapter `poc/g3_codex_adapter.py` corrected for G3 integration defects; uses docker-compose for lifecycle.

### Adapter Capabilities (Thin Wrapper)
| Capability | Command | Status |
|------------|---------|--------|
| Create/inspect durable plan | `create-plan` | ✅ |
| Dispatch approved OpenCode job | `launch` | ✅ (enforces G3_AUTHORIZED=1, durable single-launch, scope validation) |
| Monitor job progress | `wait` / `status` | ✅ (command-specific timeouts) |
| Inspect structured job results | `status` | ✅ |
| Read worker implementation | `verify` (workspace access) | ✅ (shared persistent workspace) |
| Run deterministic tests | `verify` (test command) | ✅ (fixed --test-cmd parsing) |
| Record independent review | `record-review` | ✅ (no auto-acceptance) |
| Advance plan after acceptance | `plan-status` | ✅ |

### Key Design Decisions
- **No automatic pre-recorded reviews** — Codex must explicitly invoke `record-review`
- **Native upstream commands** — Wraps unmodified `cli_agent_job.py` via docker-compose exec
- **Persistent container** — Avoids re-creating workspace/state per command
- **Shared persistent workspace** — `D:/tools/hybrid-agent/.runtime/poc-g3/workspace` ↔ `/g3/workspace`
- **Profile**: `opencode-9router=9router/agent-build` + `bridge-g3` (coordination channel enabled, scoped permissions)
- **No custom orchestration engine** — Pure upstream Augani workflow
- **G3 authorization gate** — `launch` requires `G3_AUTHORIZED=1` + durable state (max one live job)
- **Scope validation before dispatch** — Invokes `g3_validate_scope.py` automatically
- **Command-specific timeouts** — No fixed 300s timeout; adapts to operation
- **Docker Compose as single lifecycle source** — No `docker run` fallback

### Verified Profile Configuration
```json
{
  "agents": {
    "opencode-9router": {
      "argv": ["opencode", "--standalone", "run", "--format", "json", "{prompt_text}"],
      "model_args": ["--model", "{model}"],
      "cli_agent_args": ["--agent", "{cli_agent}"],
      "models": ["9router/agent-build"]
    }
  }
}
```
Resolved worker command: `opencode --standalone run --format json "<prompt>" --model 9router/agent-build --agent bridge-g3`

---

## G3-C — Live Acceptance

**Status:** **G3_LIVE_PASS**. Codex independently accepted the result of one authorized OpenCode job.

### Fixture Components
| File | Purpose |
|------|---------|
| `poc/g3_task.md` | Compact task contract (slugify implementation, 8 reference cases) |
| `poc/g3_plan.md` | Single-item checklist plan (`plan-id: g3`, `item-001`, workspace `/g3/workspace`) |
| `poc/g3_live_verify.py` | Full live verification harness (guarded by `G3_AUTHORIZED=1`, uses bootstrap) |
| `poc/g3_validate_scope.py` | Preventive scope validation (contract ↔ runtime allowlist) |
| `poc/g3_codex_adapter.py` | Codex coordinator CLI adapter (enforces auth, scope, timeouts, shared workspace) |
| `poc/g3_bootstrap.py` | Offline runtime bootstrap (idempotent, no inference) |
| `.opencode/agents/bridge-g3.md` | Execution profile with scoped permissions + coordination channel |

### G3-C Acceptance Flow (Codex Must Execute)
1. **Read** task contract (`g3_task.md`)
2. **Create/select** durable plan (`create-plan --plan-id g3`)
3. **Dispatch** exactly one approved OpenCode job (`launch --checklist-item item-001` **requires `G3_AUTHORIZED=1`**)
4. **Observe** execution status (`wait` / `status`)
5. **Inspect** actual source changes (`verify` workspace — uses host-mounted `D:/tools/hybrid-agent/.runtime/poc-g3/workspace`)
6. **Run** deterministic tests (`verify` runs `python -B -m unittest ...`)
7. **Perform independent review** (actual Codex reads diff + test output)
8. **Record verdict** (`record-review --verdict accepted|rejected --test "..."`)
9. **Verify plan advancement** only after acceptance (`plan-status g3`)

### Negative Acceptance Check (Automated in Harness)
- Uses deterministic local fake worker (`fake-fail` profile, no network access)
- Attempts `record-review --verdict accepted` without `--test` → blocked
- Verifies plan does not advance → `complete: false`

### Exact G3 Live Command (Requires `G3_AUTHORIZED=1`)
```powershell
# Prerequisites (run once):
docker compose -f docker-compose.g3.yml up -d g3-orchestrator
docker compose -f docker-compose.g3.yml exec g3-orchestrator python3 /work/poc/g3_bootstrap.py --verify-only

# 1. Create/select durable plan (plan-id: g3)
python poc/g3_codex_adapter.py create-plan ^
  --task-file poc/g3_task.md ^
  --plan-file poc/g3_plan.md ^
  --plan-id g3 ^
  --title "G3 Codex integration live test" ^
  --executor "opencode-9router=9router/agent-build"

# 2. Dispatch exactly one approved OpenCode job (REQUIRES G3_AUTHORIZED=1)
$env:G3_AUTHORIZED=1; python poc/g3_codex_adapter.py launch ^
  --task-file poc/g3_task.md ^
  --plan-id g3 ^
  --checklist-item item-001 ^
  --allowed-paths "src/**" "tests/**" ^
  --max-changed-files 10 ^
  --timeout-seconds 600

# 3. Observe execution status (poll or wait)
python poc/g3_codex_adapter.py wait --job-id <JOB_ID> --timeout-seconds 660 --poll-seconds 2

# 4. Inspect actual source changes (uses host-mounted shared workspace)
python poc/g3_codex_adapter.py verify ^
  --workspace D:/tools/hybrid-agent/.runtime/poc-g3/workspace ^
  --allowed-prefixes "src/" "tests/" ^
  --required-files "src/slugify.py" "tests/__init__.py" "tests/test_slugify.py" ^
  --test-cmd "python -B -m unittest discover -s tests -t . -v"

# 5. Run deterministic tests (included in verify)

# 6. Perform independent review (MANUAL - actual Codex)
python poc/g3_codex_adapter.py record-review ^
  --job-id <JOB_ID> ^
  --verdict accepted|rejected ^
  --reviewer codex-g3-live ^
  --test-result "python -B -m unittest discover -s tests -t . -v: OK (Ran N tests)" ^
  --notes "Independent Codex review: scoped files only, deterministic tests pass, no out-of-scope changes."

# 7. Verify plan advancement only after acceptance
python poc/g3_codex_adapter.py plan-status --plan-id g3
```

---

## Evidence Tracking

| Gate | Status | Evidence Path | Notes |
|------|--------|---------------|-------|
| G0 | ✅ STATIC_VERIFIED | `POC_STATUS.md` | WSL Ubuntu install optional (Docker path works) |
| G1 | ✅ OFFLINE_PASS | `poc/evidence/g1_offline.txt` | 15/15 checks; 39/39 upstream tests |
| G2 Profile | ✅ STATIC_VERIFIED | `poc/evidence/g2_resolved_command.txt`, `poc/evidence/g2_container_preflight.txt` | Profile schema, doctor, models, resolved argv |
| G2 Negative | ✅ OFFLINE_PASS | `.runtime/poc-g2/evidence/g2_negative_summary.json` | Real adapter, no inference |
| G2 Live | ✅ **LIVE_PASS** | `.runtime/poc-g2/evidence/g2_live_summary.json` | One inference, 9 tests + 8 assertions PASS, review accepted, plan done, dashboard OK |
| G3-A | ✅ **READY** | `docker-compose.g3.yml`, `poc/Dockerfile.g3`, `poc/g3_bootstrap.py`, `G3_START_CODEX.md` | Persistent container, Windows dashboard via proxy (localhost-only) |
| G3-B | ✅ **OFFLINE_VERIFIED** | `poc/g3_codex_adapter.py`, `.opencode/agents/bridge-g3.md`, `poc/g3_validate_scope.py` | Adapter uses docker-compose, durable auth, scoped permissions |
| G3-C | **G3_LIVE_PASS** | `.runtime/poc-g3/evidence/g3_codex_live_summary.json` | One job, 8 unit tests and 8 independent assertions passed, review accepted, plan done |

---

## Custom Code Inventory (PoC Tooling Only — No Upstream Modification)

| Component | Purpose | Lines | Status |
|-----------|---------|-------|--------|
| `poc/opencode_agents.json` | Custom `opencode-9router` profile | 19 | ✅ STATIC_VERIFIED |
| `poc/Dockerfile.g2` | Disposable Linux runtime (G2) | 12 | ✅ BUILT (`hybrid-agent-g2:0.2`) |
| `poc/Dockerfile.g3` | Persistent Linux runtime (G3) | 15 | ✅ BUILT (`hybrid-agent-g3:0.1`) |
| `docker-compose.g3.yml` | Container orchestration for G3 | 45 | ✅ VALID |
| `poc/g1_offline_verify.py` | G1 fake-worker harness | ~480 | ✅ PASS (15/15) |
| `poc/g2_negative_check.py` | G2 negative-path integration | ~160 | ✅ PASS |
| `poc/g2_live_verify.py` | G2 live verification harness (guarded) | ~380 | ✅ LIVE_PASS |
| `poc/g2_preflight.sh` | Container environment verification | 30 | ✅ PASS |
| `poc/g2_show_command.py` | Resolved argv printer | 25 | ✅ PASS |
| `poc/g2_dashboard_check.py` | Dashboard query helper | 45 | ✅ PASS |
| `poc/g2_probe_router.py` | 9Router connectivity probe | 35 | ✅ PASS |
| `poc/g2_validate_task.py` | Task packet validator | 20 | ✅ PASS |
| `poc/g2_task.md` | Deterministic task packet (G2) | 120 | ✅ VALID |
| `poc/g2_plan.md` | Single-item checklist plan (G2) | 25 | ✅ VALID |
| `poc/g3_task.md` | Compact task contract (G3) | 85 | ✅ VALID |
| `poc/g3_plan.md` | Single-item checklist plan (G3) | 20 | ✅ VALID |
| `poc/g3_live_verify.py` | G3 live verification harness (guarded) | ~420 | ⏳ AUTH_REQUIRED |
| `poc/g3_validate_scope.py` | Preventive scope validation | 85 | ✅ VALID |
| `poc/g3_codex_adapter.py` | Codex coordinator CLI adapter | ~280 | ✅ VALID |
| `.opencode/agents/bridge-g3.md` | G3 execution profile (coord channel) | 60 | ✅ VALID |

**Total custom PoC code:** ~2,300 lines (all in `poc/`, `.opencode/`, `.runtime/poc-g2/`, `.runtime/poc-g3/`). **No upstream fork, no upstream core changes, no Windows shims, no custom workflow engine, no state store migration.**

---

## Remaining Mandatory Checks

| # | Check | Status |
|---|-------|--------|
| 1 | WSL Ubuntu installed (for native dashboard) | ⚠️ OPTIONAL — Docker dashboard works from Windows host |
| 2 | Upstream test suite passes in container | ✅ 39/39 |
| 3 | Fake worker workflow verified offline | ✅ 15/15 |
| 4 | OpenCode v2.2.0 + 9Router profile + route verified | ✅ STATIC_VERIFIED |
| 5 | Negative-path adapter integration (real binary, no inference) | ✅ PASS |
| 6 | Live inference run + independent verification (G2) | ✅ **LIVE_PASS** (2026-11-27T01:58:43Z) |
| 7 | Dashboard progress (internal + Windows host) | ✅ PASS (G3-A: proxy 0.0.0.0:8080 → 127.0.0.1:8081, Docker maps 127.0.0.1:8080) |
| 8 | Recovery/permission limitations documented | ✅ (see G2/G3 limitation notes) |
| 9 | Codex coordinator + independent review commands prepared | ✅ G3-B OFFLINE_VERIFIED |
| 10 | Task-scope validation (preventive, before dispatch) | ✅ G3-B: `g3_validate_scope.py` invoked by adapter |
| 11 | Coordination channel enabled safely | ✅ G3-B: `bridge-g3` profile allows channel commands only |
| 12 | G3-C live acceptance | **G3_LIVE_PASS** |
| 13 | Shared persistent workspace mapping | ✅ Host `D:/tools/hybrid-agent/.runtime/poc-g3/workspace` ↔ Container `/g3/workspace` |
| 14 | Unified runtime initialization | ✅ AGENT_ORCHESTRATOR_HOME, config, profile, model, workspace, provider connectivity |
| 15 | Correct adapter timeout handling | ✅ Command-specific timeouts (no fixed 300s) |
| 16 | Dashboard localhost restriction | ✅ `127.0.0.1:8080:8080` in docker-compose |
| 17 | G3 authorization enforcement | ✅ Adapter `launch` requires `G3_AUTHORIZED=1` + durable state |
| 18 | No automatic acceptance | ✅ Harness requires actual Codex review, negative check uses local fake worker |
| 19 | Docker Compose as single lifecycle source | ✅ No `docker run` fallback in adapter |
| 20 | Offline bootstrap available | ✅ `poc/g3_bootstrap.py` (idempotent, no inference) |
| 21 | Worker permissions scoped to task | ✅ `bridge-g3` restricts read/glob/grep/edit to src/**, tests/** |
| 22 | Test command parsing fixed | ✅ `--test-cmd` accepts quoted string, parsed with shlex |

---

## Blocker Summary

| Blocker | Impact | Resolution |
|---------|--------|------------|
| **B1: G3 live inference authorization** | Approval granted for one bounded job. | Resolved by the single approved dispatch. |
| **B2: Channel progress/question denied by `bridge-build` profile (G2)** | G2 worker cannot emit structured progress or ask questions via coordination channel. | **RESOLVED in G3**: `bridge-g3` profile explicitly allows `python3 *channel.py event*` and `python3 *channel.py ask*` only. No broad shell permissions granted. |

---

## Final Recommendation (Current)

**GO** — G3-A READY, G3-B OFFLINE_VERIFIED, G3-C **G3_LIVE_PASS**

### Verified Capabilities
- ✅ **Persistent Docker environment** with durable plan/worker workspace (survives restarts)
- ✅ **Windows-host dashboard access** at `http://127.0.0.1:8080/#token=<TOKEN>` (authenticated, 401 unauth, via proxy)
- ✅ **Coordination channel safely enabled** — only `event` and `ask` commands permitted via `bridge-g3` profile
- ✅ **Task-scope validation** — preventive isolation matching runtime allowlist to task contract; protected paths denied
- ✅ **Minimal Codex adapter** — thin wrapper over upstream commands via docker-compose, no custom orchestration engine
- ✅ **Recovery behavior verified** — container restart preserves state; failed workers not auto-accepted; retry budgets bounded; writer serialization enforced
- ✅ **Offline bootstrap** — `g3_bootstrap.py` initializes workspace, config, verifies profile without inference
- ✅ **Durable single-launch authorization** — `G3_AUTHORIZED=1` + state file prevents duplicate live jobs
- ✅ **Scoped worker permissions** — `bridge-g3` restricts read/glob/grep/edit to `src/**`, `tests/**` only
- ✅ **Local deterministic fake worker** — negative acceptance check uses no network access

### Actual Dashboard Accessibility
- **URL**: `http://127.0.0.1:8080/#token=<FROM_DOCKER_LOGS>`
- **Verified from Windows host**: Authenticated 200, unauthenticated 401, projects listed, job ID present, progress visible, review status visible, blocker status visible, human intervention controls functional
- **Architecture**: Upstream dashboard on `127.0.0.1:8081` → Python proxy on `0.0.0.0:8080` → Docker maps `127.0.0.1:8080:8080` → Windows host

### Coordination-Channel Status
- **G2 (`bridge-build`)**: BLOCKED — profile denies shell commands needed for channel
- **G3 (`bridge-g3`)**: ENABLED — profile allows ONLY `python3 *channel.py event*` and `python3 *channel.py ask*` (no broad shell)

### Persistent Container/Workspace Behavior
- Container `hybrid-agent-g3` runs persistently (`sleep infinity` + dashboard proxy)
- State mounted at `D:/tools/hybrid-agent/.runtime/poc-g3/state`
- Shared workspace at `D:/tools/hybrid-agent/.runtime/poc-g3/workspace` ↔ `/g3/workspace` (persists across restarts)
- Plan/job/events survive container restart
- No orphan workers (single-writer enforced by upstream)
- No automatic commit/push/worktrees

### Permission and Recovery Limitations
- **No exact OpenCode session resume** — task-level restart from verified checkpoint only
- **Scope violations block automatic retry** — user must inspect and authorize correction
- **Protected paths** (`.opencode/**`, `AGENTS.md`, `config/**`, etc.) denied by default for coding tasks
- **Max 3 retries per checklist item** enforced by upstream
- **User can stop execution** via `cancel` command; workspace preserved for inspection
- **Maximum one live worker job** for G3-C fixture (enforced by adapter + durable state)

### Custom Operational Adapter Inventory
| Adapter | Purpose | Lines |
|---------|---------|-------|
| `poc/g3_codex_adapter.py` | Codex → Augani Docker CLI wrapper (docker-compose) | ~320 |
| `poc/g3_validate_scope.py` | Preventive task-scope validation | ~85 |
| `poc/g3_live_verify.py` | Full G3-C live verification harness | ~450 |
| `poc/g3_bootstrap.py` | Offline runtime bootstrap | ~180 |
| `docker-compose.g3.yml` | Container orchestration (incl. dashboard proxy) | 50 |
| `.opencode/agents/bridge-g3.md` | Scoped execution profile + coordination channel | 70 |

### G3-C Live Result

- Plan g3, item item-001, job opencode-9router-20261127-043745-f93cad.
- Worker opencode-9router, model 9router/agent-build, profile bridge-g3, duration 48.771 seconds.
- Four files within scope. All 8 unit tests and all 8 independent assertions passed.
- The Windows dashboard showed progress and acceptance. The durable plan advanced to done after review.

### Evidence References
- G3-A: `docker-compose.g3.yml`, `poc/Dockerfile.g3`, `poc/g3_bootstrap.py`, `G3_START_CODEX.md`
- G3-B: `poc/g3_codex_adapter.py`, `.opencode/agents/bridge-g3.md`, `poc/g3_validate_scope.py`
- G3-C: .runtime/poc-g3/evidence/g3_codex_live_summary.json
