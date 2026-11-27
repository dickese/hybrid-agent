# G4 — Reconciliation & implementation-plan delta

**Status:** DISCOVERY_COMPLETE_REMOTE / LOCAL_RECONCILIATION_REQUIRED  
**Verdict:** CONDITIONAL_GO for local reconciliation; implementation and live acceptance not authorized by this artifact.  
**Baseline inspected:** `dickese/hybrid-agent`, remote `master`, `9dc7dba299d1d66a5572a863a618ed9c8f106341` (G3_LIVE_PASS).  
**Authority:** User's G4 Architecture Amendment (Adaptive Capability Routing — External First, Native When Needed).

This is an amendment to the existing G4 plan, not a second plan or engine. Merge the delta below into the actual local plan after inspecting local changes. Do not overwrite existing artifacts or reset runtime state. Remote discovery cannot establish local HEAD, dirty files, active writer ownership or unpushed work. No repository changes, model inference, live job, commit or push were performed by this review.

## 1. Local reconciliation gate (before any mutation)

Run read-only checks in `D:\tools\hybrid-agent` using the current branch:

```powershell
git branch --show-current
git rev-parse HEAD
git status --porcelain=v1 --untracked-files=all
git diff --stat
git diff --cached --stat
git ls-files
```

Locate the actual existing G4 plans, task contracts, phase evidence and local/untracked artifacts. Inspect shared Augani job state and any other orchestrator/writer coordination records for this canonical working tree, including worker child process liveness. Git status alone is not a writer ownership check. Do not run Git mutations, create worktrees, reset, stash or clean. If writer ownership cannot be established, stay in read-only discovery. Preserve user changes and all G3 evidence. Update the existing plan by mapping actual phase IDs to the delta below. Do not start completed tasks again.

## 2. Component disposition at the inspected remote baseline

| Component / actual location | Disposition | Required delta |
|---|---|---|
| Augani pinned runtime; plan/job state, dashboard, event channel, review gate | REUSE | Keep one execution engine; preserve the G3 fixture and state. Docker/Linux remains the validated execution route. |
| `config/agent-registry.json` | EXTEND + REVISE | Six agents exist. Add runtime, explicit access mode, relative cost and qualified capability evidence; introduce native roles in the same registry. Do not conflate route with logical role. |
| `config/routing-policy.json` | REVISE | Existing category→agent rules and permission requirements are fixed. Add stage selection and eligibility-first agent selection, not another registry. |
| `config/recovery-policy.json` | EXTEND + REVISE | Keep failure classification/budget semantics, remove escalation that expands access. Reconcile with Augani attempts and 9Router fallback; avoid multiplicative retries. |
| `poc/opencode_agents.json` | EXTEND for G4 via existing profile mechanism | Only `9router/agent-build` is declared at this baseline. Register approved other routes without changing 9Router combos. Keep G3 entry behavior compatible. |
| `.opencode/agents/bridge-fast.md` | REVISE | Existing `edit:*`, `python -B *`, `pwsh *` conflict with read-only discovery. Deny writes and indirect shell mutations. |
| `.opencode/agents/bridge-build.md` | REVISE | Existing broad edit/shell permissions are not enforced task scope. Only coder role receives scoped source-write. |
| `.opencode/agents/bridge-heavy.md` | REVISE | Existing broad write and `docker *` permissions conflict with new ownership. Keep route available as a potential qualified external coder alternate, not a second independent writer role; otherwise read-only/artifacts-only per task. |
| `.opencode/agents/bridge-docs.md` | REVISE | Existing `*.md`, `*.txt`, `AGENTS.md` and `docs/**` writes are too broad. Mount only designated artifact workspace writable; target repository read-only. |
| `.opencode/agents/bridge-review.md`, `bridge-vision.md` | REUSE + enforce | Already configured read-only with shell denied. Validate actual runtime isolation, not just profile text. |
| `bridge/contracts.py`, `bridge/gitutil.py` | REUSE selectively | Existing task parsing and workspace fingerprint helpers. Prefer Augani contracts/state and use missing helpers only; no parallel task/state engine. |
| `poc/g3_codex_adapter.py`, `poc/g3_validate_scope.py`, `poc/g3_bootstrap.py` | REUSE as reference / retain fixture | G3 is a bounded one-job PoC. Do not remove its reservation or generalize fixture hardcodes by editing the accepted fixture. Extend the existing production integration entry point if present locally; otherwise a thin adapter to Augani, not another orchestrator. |
| Native execution integration | NEW or EXTEND after local inspection | Define native role/access restrictions and actual invocation capability. Not proven by G3 single external job. |
| Cross-session canonical workspace ownership | EXTEND if existing guard insufficient | Verify Augani protects same working tree across all participating sessions; add minimal shared guard only for missing cross-runtime coverage. |

Evidence: `AUGANI_ASSESSMENT.md` §3; current registry, routing and recovery JSON; OpenCode profiles; `POC_STATUS.md` and `handoff/evidence/INDEX.md`. All six registry entries currently have `qualification_status: NOT_VERIFIED`; the G3 evidence qualifies only its specific agent-build route/profile/fixture, not all modalities or production workloads. The old assessment's Windows shims and upstream-fork suggestions are not binding because G3 validated Docker; do not reintroduce them without a gap.

## 3. Architecture and policy delta

One Codex Orchestrator makes workflow and agent decisions; Augani owns execution lifecycle. Keep logical decisions separate without creating services. Workflow classification emits level L0–L3, risk independently, objective kind, mandatory stages and acceptance constraints. Agent selection filters capability, access, risk, context and availability/reliability; prefers qualified external agents by relative cost, with a recorded reason for native escalation. Unknown qualification is not a pass; use controlled qualification or block if no eligible agent. Do not hardcode physical model names.

| Stage | L0 Direct | L1 Lightweight | L2 Standard | L3 Project |
|---|---|---|---|---|
| Classification | Required | Required | Required | Required |
| Discovery | Optional | As needed | Required | Required |
| Planning | Minimal | Lightweight | Detailed | Master plan |
| Architecture | No by default | Optional | Conditional | As needed |
| Implementation | External coder | External coder | External coder | External coder |
| V0 verification | Required if implementation | Required if implementation | Required if implementation | Required if implementation |
| V1 self-check | Coder handoff | Coder handoff | Coder handoff | Coder handoff |
| V2 external review | Optional | Default | Default | Default |
| V3 native review | Risk escalation | Risk escalation | Risk-based | Phase gate / risk-based |
| Acceptance | Orchestrator | Orchestrator | Orchestrator | Orchestrator |

Plan-only, review-only, docs-only and read-only tasks skip source implementation entirely. Apply relevant evidence checks without requiring build/test when no implementation exists. High risk never bypasses mandatory review regardless of L0–L3. Escalation preserves accepted artifacts, completed stages and evidence, and invalidates stale results if source/requirements change.

| Logical role | Runtime | Access | Qualification status at baseline |
|---|---|---|---|
| agent-fast | External | read-only | Registry configured; new permission contract not tested |
| agent-build | External | source-write | G3 fixture live pass reported; generalized scope not verified |
| agent-review | External | read-only | Profile configured; independent G4 review not verified |
| agent-vision | External | read-only | Profile configured; vision capability not verified here |
| agent-docs | External | artifacts-only | Existing permissions conflict; revise |
| native-architect | Native | artifacts-only | Proposed; runtime/access enforcement not verified |
| native-reviewer | Native | read-only | G3 actual Codex review reported; separate native subagent profile not verified |
| native-specialist | Native | read-only/artifacts-only | Proposed; verify before selection |

Retain existing `agent-heavy` logical entry and combo for compatibility; reconcile its permissions and role in the existing registry. Do not treat this proposal as authorization for an extra writer. No native coder fallback.

### Execution and ownership invariants

- At most one active source writer per canonical working tree, including across Windows/Docker aliases and orchestrator sessions. Read-only agents inspect stable snapshots or wait for a verification checkpoint before reviewing mutable source. No file-level locking or parallel source writers on the same tree.
- Enforce read-only and artifacts-only at runtime/filesystem; test direct and indirect writes, Git metadata, path traversal, symlinks/junctions, and shell bypass. If enforcement cannot be established, block the affected route rather than claim isolation.
- Orchestrator owns controlled Git actions only after verified worker and child-process termination. A timeout is not proof of termination. Ambiguous execution state is blocked until reconciliation.
- Use Augani task packet, event/job result and review record. Include objective, relevant context, input artifacts, scope, forbidden actions, criteria, verification, expected output, dependencies. Return status, findings, evidence, changed files, tests, blockers and next action.
- Record routing trace with selected agent, capabilities, access, risk, reason and escalation reason; persist via existing evidence/job mechanisms. Record actual provider/model only when observable.
- V0 failure blocks acceptance even after positive LLM review. V2/V3 reviewers use independent sessions and cannot repair code. Corrections return to external coder under shared writer guard.
- Model fallback stays in 9Router; capability escalation belongs to the orchestrator. Reuse one durable retry budget mapped to Augani attempts; avoid nested automatic retries, do not reset budget on route switch. Preserve G3 authorization fixture; G4 live execution needs separate explicit authorization.

## 4. Merge-ready phase delta (map to actual local phase IDs)

| Phase | Deliverable | Exit gate |
|---|---|---|
| G4-A | Reconcile current plan and artifacts, component map, architecture and role contracts | Local branch/HEAD/dirty state and writer ownership recorded; no conflicting artifacts; exact existing phase mapping |
| G4-B | Extend registry and existing routing policy, logical role→runtime/profile mapping, routing traces | Offline L0–L3, risk overrides, eligibility, cost preference, provider availability, read-only routing and explicit native escalation tests |
| G4-C | Integrate conditional stages and task packets into Augani-backed flow; objective-specific workflow; dynamic escalation | Fake-worker L0/L1/L2/L3 and plan-only/review-only/docs-only flows, preserved accepted artifacts and dependencies, no extra writer |
| G4-D | Enforce access modes and writer ownership before any real source dispatch; V0–V3, retry/correction/recovery | Concurrent writer denied including host/container alias, unauthorized writes denied, crash/child process gate, V0 failure blocks acceptance, independent reviewer cannot edit, retry budget persists |
| G4-E | Offline acceptance matrix, targeted compatibility regression, controlled live plan | All mandatory offline checks pass; separately authorized live qualification only; explicit GO/CONDITIONAL_GO/NO_GO |

G4-C source execution in development is fake-only until G4-D permission enforcement passes. Implementations of the G4 system itself must respect the exclusive external coder rule and current local working-tree ownership. If an existing phase already delivers a capability, link evidence rather than duplicate it.

## 5. Acceptance evidence checklist (all G4 entries presently NOT_RUN)

| ID | Check | Expected evidence |
|---|---|---|
| R01 | L0 direct | No mandatory architect/native reviewer; V0 when source changes |
| R02 | Normal L1 | V2 default, no unnecessary V3 |
| R03 | L2 conditional native / L3 phase gate | Routing reason and selective native usage |
| R04 | Small high-risk task | Mandatory review even at L0/L1 |
| R05 | Missing capability/access/context; unavailable agent | Ineligible agents rejected; no unsafe fallback |
| R06 | Dynamic escalation | Existing artifacts preserved; stage invalidation explicit |
| R07 | Plan/review/docs/read-only only | Zero source dispatch |
| W01 | Source ownership | Only external coder obtains source-write; profile/permission negative tests |
| W02 | Concurrent source writers and path aliases | Second writer denied across sessions and Windows/Docker aliases |
| W03 | Read-only/artifacts-only direct and indirect writes | Filesystem/runtime rejection, unchanged target and Git metadata |
| W04 | User dirty files and Git safety | Baseline preserved; no worktree or checkout; Git mutation denied during writer lifetime |
| W05 | Timeout/crash | Child termination confirmed before handoff; ambiguous state blocked |
| V01 | Deterministic verification | Actual commands, exit codes and required artifacts |
| V02 | V0 failure + positive review | Acceptance denied |
| V03 | Independent reviewer and repair | Distinct session, source unchanged by reviewer; repair routed to coder |
| V04 | External review disagreement | Explicit correction/escalation trace; native only as justified |
| V05 | Durable retry budget | No multiplication/reset on route switch; bounded attempts |
| V06 | Acceptance | Review/evidence attached to actual job/revision and routing trace |
| C01 | G3 compatibility | Existing durable state unchanged; dashboard, event channel and review gate work; targeted offline regression only |
| C02 | No second engine / unchanged combos | Existing Augani flow and 9Router configuration preserved |

Use deterministic local fake workers first. Store observed command output, test exit codes, job/session IDs (when relevant), scope checks, before/after state and routing traces in existing evidence locations. Do not report PASS for configuration inspection alone. No raw credentials/tokens in artifacts. Live coverage should be limited to genuinely new capabilities (e.g., scoped writer, independent external review, native escalation if approved), not rerun accepted G3 solely to accumulate evidence.

## 6. Immediate handoff

Run G4-A local reconciliation as above, merge this delta into the existing G4 plan, report actual REUSE/EXTEND/REVISE/NEW decisions and resume only unfinished tasks under existing authorization. Preserve the accepted G3 baseline. If another session owns the writer, stay read-only until handoff. External coder is the only implementation writer; Codex/native architect/reviewer must not patch implementation. No push, merge, branch change, or inference outside explicit authorization.

Final handoff must include updated architecture and plan, component and capability/routing matrices, permission and review policy, per-criterion test evidence, known limitations, actual changed files/commit if authorized and final verdict. At the time of this remote discovery all G4 implementation and acceptance checks remain unverified.
