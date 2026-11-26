# RUNBOOK — OpenCode-first Bootstrap & Codex Handoff

Version 0.2 | Windows / PowerShell | Synchronous CLI Bridge MVP

Companion to `RUNBOOK.md` (Hybrid Agent CLI Bridge v0.1). This document overrides its phase ownership, sequencing, gates and GOAL prompt; retain v0.1 technical contracts and safety requirements unless explicitly changed here. If conflict: this document controls ownership; stricter safety rules remain. No MCP, async worker, daemon, Redis, worktree, auto commit/push or real project source modification during bootstrap. This is a plan, not evidence of an installed system.

## 1. Objective and authority

- OpenCode TUI is the bootstrap/setup engineer; use an existing approved model/route, not Zen fallback implicitly. OpenCode may prepare and test all runtime-side code and Codex integration templates without starting a Codex model session.
- Codex is the sole **operational** orchestrator and task acceptance authority once handoff is complete. OpenCode may mark bootstrap checks PASS or BLOCKED based on actual evidence, not mark Codex-only checks or operational tasks ACCEPTED.
- Minimize Codex inference: no full repeated tool inventory, router probe, PONG, direct CLI PoC, failure matrix, source audit, or unit test suite unless a relevant failure, stale fingerprint, or code change invalidates evidence.
- Codex must still check the actual execution boundary. This is a narrow integration check, not an attempt to bypass sandbox.
- Existing credentials/configs preserved. User approval required for new routes/accounts, paid usage outside approved policy, permission expansion, global changes, external data transfer not already approved. Use disposable synthetic Git fixture only. Never log keys or full env. If blocked, record precise safe remediation; never switch to an unapproved model, fake results or retry indefinitely.

## 2. Ownership and sequence

| Stage | Original phase | Owner | Gate |
|---|---|---|---|
| A0 | P00 host | OpenCode TUI | HOST_READY |
| A1 | P01 | OpenCode TUI | RUNTIME_READY |
| A2 | P02 | OpenCode TUI | BRIDGE_READY |
| A3 | P03 | OpenCode TUI | GUARDRAILS_READY |
| A4 | P05 runtime-only | OpenCode TUI | RECOVERY_READY |
| A5 | P04 templates + handoff | OpenCode TUI | READY_FOR_CODEX |
| B0 | P00 Codex boundary | Codex | CODEX_CONTEXT_READY |
| B1 | P04 activation + P05 policy | Codex | HYBRID_READY |
| B2 | P04 fixture end-to-end | Codex | PILOT_READY |
| C | P06 | Codex after user approval | Operational task ACCEPTED |

P07 remains out of scope. A5 is not proof of B0/B1/B2. No circular dependency: A1/A2 use direct OpenCode CLI; do not require the bridge or Codex before they exist. A4 implements only deterministic state/reconciliation machinery, not autonomous orchestration decisions.

## 3. Stage A — OpenCode TUI

### A0 — Host preflight (P00.1–P00.3)

Use v0.1 P00 host/router/provider steps; run on local Windows. Determine actual workspace root, executable paths and versions, CLI schemas/flags, existing OpenCode config scope, router URL/approved exact model ID, and credential presence only. Prefer existing config and route; avoid update or reinstall when working. Record `codex --version` or `codex --help` if available without invoking inference. Do not run `codex exec`, interactive Codex or native subagents.

Check router model inventory once and run a single non-interactive OpenCode PONG on approved route. Confirm route via sanitized router evidence if available. Do not assume a TUI-selected provider applies to a fresh CLI process. Distinguish requested route from actual upstream model; use null if unknown. Record OS, absolute executable paths, cwd, service mode, relevant config location and hash of **sanitized non-secret** effective settings. No secret hashes or raw credential config copies in handoff.

Gate: host CLI launch + router connectivity + actual PONG and route evidence. Codex context explicitly NOT_RUN.

### A1 — Direct CLI capabilities (P01)

Follow v0.1 P01 using clean disposable fixture(s), not EngoLearn. Validate actual OpenCode CLI `run`, model and agent selection, NDJSON event layout, read-only profile, scoped write + tool execution and exact-session resume if required by recovery design. Confirm `python -B test_add.py` independently, Git diff and unchanged test. Verify real permission behavior rather than relying on a prompt. Save sanitized NDJSON samples and version-specific parser notes. Limit live model calls; use fake worker for most tests later. Do not recursively delegate setup tasks through the bridge or uncontrolled nested agents.

Gate: independent test pass; read-only no changes; scoped diff; event/session evidence; no unexpected interactive input. If permission enforcement is incomplete, record the limitation and block real-repo use until resolved.

### A2 — Bridge implementation (P02)

Implement minimal synchronous Python bridge and contracts from v0.1, with commands `health`, `run`, `status`, `result`, `list`. Default health is offline/no model invocation; `--live` opt-in. Build argv safely; canonical path allowlist, sanitized config, compact stdout JSON, separate evidence files, exact session ID handling, exit codes and failure classification. Do not introduce an MCP server or process supervisor for async execution.

Use fake workers and unit tests first; then run one live bridge smoke on a new clean fixture. Persist actual execution evidence. Bridge `COMPLETED` is not task `ACCEPTED`.

Gate: unit tests and actual smoke pass; no false success or scope drift. Provide exact PowerShell launch command and absolute Python/bridge root needed by Codex.

### A3 — Safety and reliability (P03)

Implement and execute v0.1 failure matrix. Test invalid scope/path, branch mismatch, dirty baseline, malformed NDJSON/exit-zero failure, concurrent writer lock, timeout, crash, secret redaction, model/profile validation and Unicode paths. Ensure Windows process cancellation is verified, including service-owned session behavior if applicable. If cancellation cannot be established, quarantine and no automatic writer retry; report blocker. No blanket permission escalation.

Gate: actual test results recorded with exit code and counts, failure cases checked, no unresolved critical guardrail failures. Any limitations must be explicit; diff inspection is detection, not sandbox enforcement. Host checks cannot prove Codex sandbox compatibility.

### A4 — Persistent state & recovery (P05 runtime-only)

Implement deterministic state store, atomic writes, checkpoint fingerprint/reconciliation, bounded retry budget, dirty-baseline detection and exact-session mapping if supported. Test interrupted run, duplicate task rejection, user edits preservation, partial writes, correction and retry exhaustion with fake workers. Keep orchestration decisions and ACCEPTED transitions in Codex policy, not automatic bridge actions. No automatic Codex session rotation or new supervisor in MVP.

Gate: recovery drill passes. If dirty-checkpoint continuation is not safe, fail closed and document manual checkpoint/commit requirement. No automatic destructive cleanup.

### A5 — Integration assets and handoff (P04 preparation)

Prepare candidate files under `handoff/templates/` for Codex to inspect and activate; do not edit user-global Codex settings or invoke inference. Use actual installed CLI version and verified docs for schema; do not guess model identifiers from UI labels. Preserve existing project/global `AGENTS.md`, skills and agent config. Candidate files:

- `AGENTS.md` orchestration rules (or merge fragment).
- `.agents/skills/hybrid-orchestration/SKILL.md` (verify supported discovery location locally).
- `.codex/agents/` planner, reviewer, verifier templates, and optional project config fragment; use default/inherited model unless an approved exact native ID is verified. No arbitrary effort values.
- Minimal Codex integration task contract and a **fresh** disposable fixture creation script (not already-fixed fixture); preserve the immutable test for independent verification.
- `scripts/verify-handoff.ps1` or equivalent Python script: no model calls, verify relevant executable paths, version/config/code fingerprints, expected files, fixture isolation, local config presence, writable approved runtime location, credential presence only if required. Output concise JSON with PASS/BLOCKED, changed items and next action. Do not print secrets or network probe by default.
- `handoff/START_CODEX.md`: compact entrypoint with exact commands, handoff status, evidence references, and Codex-only steps. Use real paths/values from setup, not placeholders at final handoff. Maximum ~100 lines.

Do not mark READY_FOR_CODEX unless all required A0–A4 gates pass, critical blockers are empty, candidate integration files and smoke fixture exist, and handoff manifest validates. If blocked, set BLOCKED and specify exact remaining action/owner. A report cannot substitute for executable artifacts.

## 4. Minimal handoff package (generated by OpenCode locally)

```text
handoff/
  START_CODEX.md          # only mandatory initial prose read
  manifest.json           # machine-readable gate results, fingerprints, commands
  templates/              # candidate Codex-only integration files
  evidence/INDEX.md       # links to existing run/test artifacts; no duplicated logs
scripts/
  verify-handoff.ps1      # deterministic offline check
  ...                     # fixture setup helper (actual names recorded in manifest)
.runtime/                 # ignored, local restricted access
  phase-reports/
  runs/
  ...
```

Store bridge source/config/examples/tests in normal project layout from v0.1. Keep raw logs in restricted local runtime storage; sanitize before linking/exporting. Do not include credentials in any artifact. Manifest may contain non-secret local paths; keep local. Use existing ignored config rather than embedding secrets. Hash source/config *sanitized nonsecret values* and relevant evidence files to detect drift, not to claim independent attestation. Handoff paths must resolve in workspace; do not reference missing files. If a smoke uses a disposable fixture outside the workspace, record its approved canonical path separately.

### START_CODEX.md content budget

1. Status (READY_FOR_CODEX / BLOCKED), workspace, timestamp, actual versions and approved model route.
2. Gates A0–A5 table and concise evidence pointers. Known limitations and only outstanding Codex-specific tasks.
3. Exact offline verification and synchronous bridge commands, working directory, required permission notes, expected result JSON fields.
4. Templates to activate/merge, fixture task, native review/verification expectation and stop policy.
5. No full transcript, no duplicated runbook or provider setup tutorial. Use links to original reports only when troubleshooting.

### manifest.json example shape (illustrative, not evidence)

```json
{
  "schema_version": 1,
  "status": "BLOCKED",
  "workspace_root": "REPLACE_WITH_ACTUAL_PATH",
  "generated_at": null,
  "gates": {"A0": "NOT_RUN", "A1": "NOT_RUN", "A2": "NOT_RUN", "A3": "NOT_RUN", "A4": "NOT_RUN", "A5": "NOT_RUN"},
  "codex_context": "NOT_RUN",
  "versions": {},
  "executables": {},
  "route": {"requested_model": null, "actual_upstream_model": null},
  "fingerprints": [],
  "commands": {},
  "evidence": [],
  "blockers": [],
  "limitations": [],
  "codex_pending": ["B0", "B1", "B2"]
}
```

In actual manifest: gates PASS/FAIL/BLOCKED/NOT_RUN, timestamps, evidence paths and exit codes; include tests observed/pass/fail counts where appropriate. Command entries should include cwd, executable and argv rather than ambiguous shell strings. Use SHA-256 hashes of relevant non-secret files and version identifiers. Include provenance (host, run ID, fixture HEAD, test commands) for live smoke. Never infer test success from model narration.

## 5. Stage B — Codex-only work

### B0 — Minimal boundary validation

Read only `handoff/START_CODEX.md` and `manifest.json` initially. If status != READY_FOR_CODEX, report blocker and stop; do not redo setup yourself. Execute offline verifier in the same Codex session/workspace/sandbox that will dispatch bridge tasks. Do not run raw `/models`, direct PONG, repeated CLI inventory or full suite if the recorded evidence is valid. On drift, read only affected report and delegate remediation to OpenCode; rerun affected verification after change.

B0 live boundary check may be combined with B2 single fixture worker call. B0 stays pending until a real Codex-originated bridge invocation traverses OpenCode and the approved 9Router route successfully. Verify structured runtime outcome, scope and router evidence as available. No separate redundant PONG required. If network, ACL, sandbox, env, or credential access fails, record exact sanitized error and stop/return to OpenCode/user; do not bypass or change global settings.

### B1 — Activate native integration

Inspect only the candidate Codex integration files and necessary bridge interface/policy (not full source audit by default). Merge project config and skill without overwriting existing instructions; confirm installed version supports chosen schema, discover/activate skill and native reviewer/verifier. Default/inherited model or verified approved exact ID. Codex owns task acceptance, retry budget and correction decisions. Prepare a narrowly scoped native plan; combine reviewer and verifier in one independent native read-only agent for the tiny fixture if feasible, but do not let the implementing agent verify its own work. For future real tasks follow required independent gates.

### B2 — One end-to-end fixture workflow

Use fresh approved disposable fixture, not one previously repaired. Create task contract; invoke the bridge once from Codex using approved route. Observe actual JSON result, independent test exit code and Git diff, native independent review and acceptance. Persist checkpoint. This worker call also satisfies B0 live gate if it demonstrates actual boundary access. A native reviewer can run the independent test only if allowed; otherwise Codex executes it. No duplicate model pings; no automatic correction unless required, and at most original v0.1 budget. If failure is infrastructure-related, return to OpenCode with evidence rather than spending Codex on runtime debugging.

Gate: B0, B1, B2 PASS; one test fixture ACCEPTED by Codex; handoff fingerprint still valid; report exact unresolved limitations. Stop at P06 approval gate. Do not modify EngoLearn or another real repo.

## 6. Quota budget and invalidation

- OpenCode uses approved provider quota; it is not free or unlimited. Router fallback does not remove upstream limits. Avoid recursive worker loops and duplicate live calls. Use deterministic Python/PowerShell tests for most checks.
- Codex default: one session, offline verification, minimal native independent review, one external fixture run (also boundary smoke), final acceptance. No promised token savings percentage.
- Recheck only changed components: executable/CLI version → affected capability/parser checks; route/config/auth change → affected route + tool smoke; bridge source/policy change → relevant tests; Codex environment change → boundary smoke. Unknown/stale security evidence → block or targeted verification, not blind trust. A clean handoff is not an independent security audit; real source requires explicit approval and verified enforcement.
- Infra errors route back to OpenCode with compact failure ticket: gate, expected, actual, error classification, sanitized evidence path, owner, affected checks. Codex should not spend a long session troubleshooting setup.

## 7. Prompt for OpenCode TUI

```text
Read RUNBOOK.md and OPENCODE_FIRST_BOOTSTRAP_RUNBOOK.md. The latter overrides phase ownership and sequencing. Act as the OpenCode bootstrap/setup engineer. Execute A0–A5, including host preflight, direct CLI smoke, synchronous bridge implementation, safety/reliability tests, runtime checkpoint/recovery and preparation of Codex integration templates. Use the existing approved 9Router route; verify actual CLI versions and flags. No Codex inference, native subagents, MCP, async, worktrees, automatic commit/push, broad permission changes or real project modifications. Preserve existing configuration and secrets. Use synthetic disposable fixtures and fake workers for deterministic tests. Do not claim PASS without actual evidence. Generate handoff/START_CODEX.md (<=100 lines), manifest.json, evidence index, templates and offline verifier with actual commands/paths. Do not mark Codex boundary or hybrid workflow verified. If blocked, report exact error and safe next action. Stop when READY_FOR_CODEX or BLOCKED; do not start Codex.
```

## 8. Prompt for Codex (after READY_FOR_CODEX)

```text
Read only handoff/START_CODEX.md and handoff/manifest.json first. Follow Stage B of OPENCODE_FIRST_BOOTSTRAP_RUNBOOK.md. If handoff is not READY_FOR_CODEX, stop and report the blocker. Trust valid bootstrap evidence for unchanged components; run the offline verifier and do not repeat host/router/CLI preflight, full tests, or PONG. Inspect and activate only Codex-specific integration templates. Perform one minimal end-to-end hybrid fixture workflow using the bridge from your actual Codex execution context; use that same worker invocation as the live boundary smoke. Use native independent review/verification, independent tests and actual diff evidence before accepting the fixture. If infrastructure fails or evidence drifts, emit a concise remediation ticket for OpenCode rather than troubleshooting unrelated components. No sandbox bypass, new worktree, automatic commit/push, unapproved model/provider, real project modifications, MCP or async. Persist acceptance/checkpoint and stop at P06 user approval gate.
```
