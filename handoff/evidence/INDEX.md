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
