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
