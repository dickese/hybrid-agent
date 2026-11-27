# Augani/agent-orchestrator PoC Status

**Upstream Commit:** `8d9b897c49500e8e1b54ec8028352544db95618d` (tag `v0.7.1`)  
**Started:** 2026-11-27  
**Status:** G0✅ G1✅ G2✅ **LIVE_PASS** G3⏳

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

## G3 — Codex Integration Preparation

**Status:** 🟡 **READY FOR AUTHORIZATION** — G2 LIVE_PASS achieved, Codex commands prepared.

### Planned Commands (requires explicit Codex authorization)
| Step | Command | Purpose |
|------|---------|---------|
| 1 | `codex exec --prompt "..."` | Dispatch one OpenCode task via Codex coordinator |
| 2 | Verify worker route/profile | `opencode-9router=9router/agent-build` + `bridge-build` |
| 3 | Codex independent review | Actual diff + test results → accept/reject |
| 4 | Plan advances only after acceptance | Upstream gate |

### Proposed G3 Live Command (analogous to G2)
```bash
docker run --rm \
  -v "D:/tools/hybrid-agent:/work:ro" \
  -v "D:/tools/hybrid-agent/.runtime/poc-g3:/g3" \
  -v "C:/Users/ANH DUC/.config/opencode/opencode.json:/run/opencode-global.json:ro" \
  -v "D:/tools/hybrid-agent/.runtime/secrets/9router.key:/run/secrets/9router.key:ro" \
  -e RUNNER=/work/agent-orchestrator-poc/plugins/agent-orchestrator/scripts/cli_agent_job.py \
  -e CONFIG=/work/poc/opencode_agents.json \
  -e G3_BASE=/g3 \
  -e G3_CLI=opencode-9router \
  -e G3_MODEL=9router/agent-build \
  -e G3_CLI_AGENT=bridge-build \
  -e G3_AUTHORIZED=1 \
  hybrid-agent-g2:0.2 \
  python3 -B /work/poc/g3_live_verify.py
```
*(G3 harness `g3_live_verify.py` to be created with Codex coordinator dispatch logic)*

**Exact commands and authorization will be documented for G3 explicit approval.**

---

## Evidence Tracking

| Gate | Status | Evidence Path | Notes |
|------|--------|---------------|-------|
| G0 | ✅ STATIC_VERIFIED | `POC_STATUS.md` | WSL Ubuntu install required for native path |
| G1 | ✅ OFFLINE_PASS | `poc/evidence/g1_offline.txt` | 15/15 checks; 39/39 upstream tests |
| G2 Profile | ✅ STATIC_VERIFIED | `poc/evidence/g2_resolved_command.txt`, `poc/evidence/g2_container_preflight.txt` | Profile schema, doctor, models, resolved argv |
| G2 Negative | ✅ OFFLINE_PASS | `.runtime/poc-g2/evidence/g2_negative_summary.json` | Real adapter, no inference |
| G2 Live | ✅ **LIVE_PASS** | `.runtime/poc-g2/evidence/g2_live_summary.json` | One inference, 9 tests + 8 assertions PASS, review accepted, plan done, dashboard OK |
| G3 | ⏳ NOT_STARTED | — | — |

---

## Custom Code Inventory (PoC Tooling Only — No Upstream Modification)

| Component | Purpose | Lines | Status |
|-----------|---------|-------|--------|
| `poc/opencode_agents.json` | Custom `opencode-9router` profile | 19 | ✅ STATIC_VERIFIED |
| `poc/Dockerfile.g2` | Disposable Linux runtime (Node 22 + Python 3.11 + OpenCode 2.2.0) | 12 | ✅ BUILT (`hybrid-agent-g2:0.2`) |
| `poc/g1_offline_verify.py` | G1 fake-worker harness | ~480 | ✅ PASS (15/15) |
| `poc/g2_negative_check.py` | G2 negative-path integration | ~160 | ✅ PASS |
| `poc/g2_live_verify.py` | G2 live verification harness (guarded) | ~380 | ⏳ AUTH_REQUIRED |
| `poc/g2_preflight.sh` | Container environment verification | 30 | ✅ PASS |
| `poc/g2_show_command.py` | Resolved argv printer | 25 | ✅ PASS |
| `poc/g2_dashboard_check.py` | Dashboard query helper | 45 | ✅ PASS |
| `poc/g2_probe_router.py` | 9Router connectivity probe | 35 | ✅ PASS |
| `poc/g2_validate_task.py` | Task packet validator | 20 | ✅ PASS |
| `poc/g2_task.md` | Deterministic task packet | 120 | ✅ VALID |
| `poc/g2_plan.md` | Single-item checklist plan | 25 | ✅ VALID |

**Total custom PoC code:** ~1,400 lines (all in `poc/` and `.runtime/poc-g2/`). **No upstream fork, no upstream core changes, no Windows shims, no custom workflow engine, no state store migration.**

---

## Remaining Mandatory Checks

| # | Check | Status |
|---|-------|--------|
| 1 | WSL Ubuntu installed (for native dashboard) | ❌ BLOCKED — user action required |
| 2 | Upstream test suite passes in container | ✅ 39/39 |
| 3 | Fake worker workflow verified offline | ✅ 15/15 |
| 4 | OpenCode v2.2.0 + 9Router profile + route verified | ✅ STATIC_VERIFIED |
| 5 | Negative-path adapter integration (real binary, no inference) | ✅ PASS |
| 6 | Live inference run + independent verification | ✅ **LIVE_PASS** (2026-11-27T01:58:43Z) |
| 7 | Dashboard progress (internal) | ✅ PASS (live run verified) |
| 8 | Recovery/permission limitations documented | ✅ (see G2 limitation note) |
| 9 | Codex coordinator + independent review commands prepared | 🟡 Next: G3 authorization |

---

## Blocker Summary

| Blocker | Impact | Resolution |
|---------|--------|------------|
| **B1: Live inference authorization** | G2 live run cannot proceed without explicit user approval (potential upstream cost). | Request approval for **one** bounded inference call with the exact command above. |
| **B2: Native WSL2 distro missing** | Dashboard inaccessible from Windows host (container 127.0.0.1 bind). Final PoC dashboard evidence requires WSL2 Ubuntu + localhost forwarding. | User runs `wsl --install Ubuntu-24.04` and restarts terminal. |
| **B3: Channel progress/question denied by `bridge-build` profile** | Worker cannot emit structured progress or ask questions via coordination channel. | Scope restriction: no permission shim. Lifecycle events still captured; review gate works. Documented as known limitation. |

---

## Final Recommendation (Current)

**CONDITIONAL_GO** — pending:

1. **G3 Codex integration commands** documented and authorized
2. **Native WSL2 dashboard** if Windows-host visibility is required for acceptance (user action: `wsl --install Ubuntu-24.04`)

**G2 LIVE_PASS achieved** — core adoption path is viable. The Docker-based isolated PoC successfully demonstrated:
- Unmodified upstream Augani/agent-orchestrator (v0.7.1, commit `8d9b897`)
- OpenCode v2.2.0 via custom `opencode-9router` profile + `9router/agent-build` route
- `bridge-build` execution profile with real tool execution and file modifications
- Deterministic test verification (9 upstream + 8 independent assertions)
- Independent review gate with acceptance → plan completion
- Persistent job status and dashboard authentication

The native WSL2 distro remains the recommended production environment for Windows-hosted dashboard access; the Docker path is a valid isolated PoC substitute.