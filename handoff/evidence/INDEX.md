# Evidence Index

Links to execution evidence for the OpenCode-first bootstrap (stages A0–A4).
All files under `.runtime/evidence/`; raw run artifacts under `.runtime/runs/`.

## A0 — Host Preflight

| File | Description |
|------|-------------|
| `9router-show-all.txt` | 9Router model inventory |
| `9router-show-opencode.txt` | 9Router OpenCode-specific models |
| `a0-pong.ndjson` | First PONG via shared service |
| `a0-pong-standalone.ndjson` | PONG via `--standalone` with 9Router |
| `a0-pong-standalone.stderr.log` | Standalone PONG stderr (empty) |

## A1 — Runtime Validation

| File | Description |
|------|-------------|
| `a1-readonly.ndjson` | Read-only profile smoke NDJSON |
| `a1-write.ndjson` | Scoped write smoke NDJSON |
| `a1-continue-first.ndjson` | Session continuation — first run |
| `a1-continue-second.ndjson` | Session continuation — second run |
| `a1-live-health.json` | Live health check result (all PASS) |

## A2 — Bridge Live Smoke

| File | Description |
|------|-------------|
| `a2-live-smoke.md` | Full A2 evidence report |
| `a2-live-smoke-result.json` | Bridge result JSON (COMPLETED, scope_ok) |
| `a2-live-smoke-diff.patch` | Git diff: `a - b` → `a + b` |

**Run artifacts**: `.runtime/runs/b17bc0f28741495f947f5e662c8ea08b/`

## A3 — Failure Matrix

| File | Description |
|------|-------------|
| `a3-failure-matrix.md` | 13/13 failure cases verified with test evidence |

**Test command**: `python -m unittest discover -s tests -v` → 69 tests OK

## A4 — Recovery Drill

| File | Description |
|------|-------------|
| `a4-recovery-drill.md` | 8 recovery scenarios verified with test evidence |

**Test command**: `python -m unittest tests.test_recovery -v` → 8 tests OK

## G3 — Codex Integration (Offline Verification)

| File | Description |
|------|-------------|
| `.runtime/poc-g3/evidence/g3_scope_validation.json` | Scope validation (contract ↔ runtime allowlist exact match, protected paths denied) |
| `.runtime/poc-g3/evidence/g3_adapter_timeout_test.json` | Adapter timeout handling (command-specific, no fixed 300s) |
| `.runtime/poc-g3/evidence/g3_auth_gate_test.json` | G3 authorization gate (launch requires G3_AUTHORIZED=1 + durable state) |
| `.runtime/poc-g3/evidence/g3_workspace_persistence.json` | Shared workspace mapping (host ↔ container, survives restart) |
| `.runtime/poc-g3/evidence/g3_dashboard_localhost.json` | Dashboard localhost restriction (127.0.0.1:8080:8080 via proxy) |
| `.runtime/poc-g3/evidence/g3_negative_acceptance.json` | Negative acceptance check (local deterministic fake worker, no network) |
| `.runtime/poc-g3/evidence/g3_bootstrap_test.json` | Offline bootstrap (idempotent, no inference) |
| `.runtime/poc-g3/evidence/g3_adapter_compose_test.json` | Adapter uses docker-compose exec (no docker run fallback) |

**Test commands**:
- `python poc/g3_validate_scope.py poc/g3_task.md '["--allow-path", "src/**", "--allow-path", "tests/**"]'` → PASS
- `python poc/g3_validate_scope.py poc/g3_task.md '["--allow-path", "src/**", "--allow-path", ".opencode/**"]'` → FAIL (protected path)
- `python poc/g3_codex_adapter.py --help` → All commands available
- `python poc/g3_codex_adapter.py dashboard-url` → Shows localhost-only URL
- `python poc/g3_bootstrap.py --verify-only --json` → READY (no inference)
- `python poc/g3_bootstrap.py --json` → READY (initializes workspace)
- `docker compose -f docker-compose.g3.yml exec g3-orchestrator python3 /work/poc/g3_bootstrap.py --verify-only --json` → READY

## G3-C Live Codex Acceptance

| Evidence under .runtime/poc-g3/evidence/ | What it records |
|---|---|
| g3_codex_live_summary.json | G3_LIVE_PASS, authorization, worker timing, scope, and progress |
| g3_codex_git_status.txt | Four changed files |
| g3_codex_unittest.txt and g3_codex_assertions.txt | 8 unit tests and 8 independent reference assertions passed |
| g3_codex_review.json | Accepted Codex verdict with test evidence |
| g3_codex_plan_before_review.json and g3_codex_plan_after_review.json | Plan advanced to done after review |
| g3_codex_dashboard_before_review.json and g3_codex_dashboard_after_review.json | Windows dashboard visibility and acceptance |

## G4-A Local Reconciliation

| Evidence | Observed result |
|---|---|
| [G4 plan and handoff](../G4_PLAN.md) | Component dispositions, roles, workflow and permission policies, phase contracts, and the G4-B dispatch gate |
| `.runtime/poc-g4/state/plans/g4/plan.json` | Offline Augani `create-plan` and `plan-status` both exited 0. G4-A is done, four items are pending, and there are zero job IDs. |
| Git intake | `master` at `9dc7dba299d1d66a5572a863a618ed9c8f106341`, with empty tracked and staged diffs and three pre-existing untracked files |
| Writer intake | One terminal Windows Bridge run, two lock files available, five terminal G2/G3 jobs, and no matching active external worker observed |

G4 routing R01–R07, working-tree safety W01–W05, verification and recovery V01–V06, and compatibility C01–C02 are **NOT_RUN**. The reconciliation and offline plan creation did not exercise a G4 worker or change G3 state.

## G4-B0 Bootstrap and G4-B Review

Evidence is under `.runtime/poc-g4/bootstrap-b0/`. The worker could read staged source and write only to its isolated output and scratch areas. Its container had no mount for the canonical repository, Git metadata, G3, Augani state, or Docker socket. A separate Augani controller owned the durable plan and job state.

| Evidence | Observed result |
|---|---|
| `offline-evidence.json` | Fake worker wrote patch output. Direct, shell, traversal and symlink writes to protected locations failed. The stopped container had no surviving detached child. Canonical source, observed Git metadata and G3 hashes matched. A second process could not acquire the existing Windows repository lock. |
| `authorization.json`, `launch.json`, `job-status.json`, `live/control/worker-exit.json` | One job, `g4-b-development-001`, ran on `opencode-9router` / `9router/agent-build` in 522.563 seconds. Worker and container are stopped. |
| `worker.patch`, `patch-applicability.txt` | Headers named the four authorized paths. `git apply --check` exited 128 on a malformed hunk. Git's automatic recount exited 1 because both existing configuration hunks failed to match the staged files. |
| `review.json`, `plan-after-review.json` | Codex recorded rejection. G4-A remains done, G4-B is blocked, and G4-C through G4-E remain pending. |

No patch was applied to the canonical tree. No routing or compatibility tests ran because the patch could not be staged. This evidence covers the G4-B0 bootstrap only. Production G4-D permission enforcement and the G4 acceptance criteria remain unverified.

## G4-B Complete-File Correction

Evidence is under `.runtime/poc-g4/correction-002/`.

| Evidence | Observed result |
|---|---|
| `preflight.json` | Prior output did not contain a recoverable four-file result. Fake complete-file delivery passed and produced a reproducible diff for both modified and new files. Missing, extra, duplicate, symlink and non-regular entries were rejected. |
| `authorization.json`, `job-status.json`, `live/control/worker-exit.json` | `g4-b-development-002` ran once for 566.532 seconds. Augani recorded successful execution and the worker container stopped. |
| `diff-result.json`, `candidate.patch` | Exactly four regular files passed syntax validation. The deterministic diff applied to the exact baseline and reproduced all four candidate hashes. |
| `staged-tests.txt`, `legacy-tests-windows.txt`, `legacy-loader.txt` | Adaptive suite stopped at setup with zero tests run. Windows compatibility ran nine tests, with two errors caused by renamed legacy keys. The direct loader probe also failed on missing `default_routing`. |
| `independent-routing.txt` | Seven independent probes. R01 and R02 examples passed. R03, R04, R05 and R07 checks failed. |
| `review.json`, `plan-after-review.json` | Codex rejected the correction. Both attempts remain recorded. G4-B is blocked, no candidate files were integrated, and G4-C through G4-E remain pending. |
