# G4 Adaptive Capability Routing Implementation Plan

## Goal

Add adaptive workflows and capability routing to the existing Augani-backed Hybrid Agent. Codex owns classification, scope, dependencies, escalation and acceptance. Augani owns the plan and job lifecycle, events, checkpoints, dashboard and review records. External First ? Capability-Aware Routing ? Budget-Constrained Native Fallback. At most one authorized implementation writer may be active for a canonical working tree.

## Current checkpoint

The local branch is `master` at the accepted G3 commit `9dc7dba299d1d66a5572a863a618ed9c8f106341`. Tracked and staged diffs were empty at intake. The three pre-existing untracked files are `G4_RECONCILIATION_HANDOFF.md`, `check_env.py` and `poc/g3_plan_new.md`. No local G4 plan or G4 job state existed.

The Windows bridge ledger showed one terminal run and no pending or running runs. Both existing lock files could be opened exclusively in a read-only probe. Five G2/G3 jobs had terminal results, and the running G3 container contained only its service and dashboard processes. The targeted Windows process check reported Codex but no matching external worker. This is a point-in-time observation. It provides neither a cross-runtime lock nor a guarantee for a subsequent launch.

The read-only native context reader was used once under the repository delegation policy because no scoped external discovery dispatch was established. It identified the G3 adapter and offline Augani fixtures. Codex inspected the missing bootstrap and ownership details directly. No external inference ran.

## Component reconciliation

| Disposition | Component | Work |
|---|---|---|
| REUSE | Pinned Augani lifecycle and G1 fake-worker patterns | Use its plans, jobs, dependencies, channel, dashboard, review and checkpoints. Keep G3 state and authorization intact. |
| REUSE | 9Router combos and G3 adapter | Keep current routes and fixture behavior. G3 evidence qualifies its bounded fixture. |
| EXTEND | Registry and Augani OpenCode profile mechanism | Add logical roles, access, capabilities, qualification and cost in the existing registry. Keep G3 profile defaults compatible. |
| REVISE | Routing and recovery JSON | Separate workflow classification from eligibility, preserve a single durable retry budget and prohibit access expansion. |
| REVISE | Fast, build, heavy and docs profiles | Remove broad write and shell permissions. Keep heavy available only under the access contract selected by the Orchestrator. |
| REUSE AND ENFORCE | Review and vision profiles | Retain their read-only intent and prove filesystem enforcement. |
| REUSE SELECTIVELY | Bridge contracts, Git fingerprints, repository locks and Windows Job Objects | Reuse applicable primitives. Windows writer locks and Docker Augani state currently have separate ownership mechanisms, and scope checks can detect changes after execution. |
| NEW | Thin policy adapter and shared permission boundary | Use Augani commands and records. Canonicalize host/container aliases and verify containment before granting writes. No additional orchestration or retry ledger. |

## Decisions and assumptions

| Level | Stages for implementation |
|---|---|
| L0 Direct | Minimal planning, authorized coder, V0/V1, conditional review |
| L1 Lightweight | Targeted discovery as needed, lightweight planning, authorized coder, V0/V1 and V2 by default |
| L2 Standard | Discovery and detailed plan, authorized coder, V0/V1 and V2, native architecture or V3 only with a recorded reason |
| L3 Project | Discovery, master plan, dependency-aware stages, authorized coder, V0/V1 and V2, justified native phase gates |

Risk is independent of level. High risk requires independent review and cannot skip a declared V3 gate. Plan-only, review-only, docs-only and read-only discovery select just their applicable stages, with no implementation dispatch.

| Logical role | Access | Candidate capabilities |
|---|---|---|
| External agent-fast | read-only | Discovery, triage, analysis |
| External agent-build | source-write | Scoped code and test implementation, correction |
| External agent-review | read-only | Independent requirements, regression and code review |
| External agent-vision | read-only | Visual analysis |
| External agent-docs | artifacts-only | Plans, runbooks and handoff artifacts |
| External agent-heavy | Task-qualified; source-write only as External Coder | Compatibility or capability escalation |
| Native Coder (GPT-6 Luna) | Task-scoped source-write under fallback authorization | Remaining implementation within explicit effort, time and execution limits |
| Native architect | artifacts-only | Architecture and complex design judgments |
| Native reviewer | read-only | Deep review and risk-based phase gates |
| Native specialist | read-only or artifacts-only | Specialized reasoning within the assigned contract |

Filter by required access, capability, reasoning, risk, context, runtime availability and relevant qualification. Prefer eligible external candidates, then relative cost and reliability evidence. Use a stable tie-breaker. Record eligibility and selection reasons and the specific justification for any native escalation. An unknown qualification cannot satisfy a required capability. Codex alone holds orchestrator-control.

## Constraints and guardrails

Resolve canonical workspace ownership before granting access. A worker must receive only filesystem access allowed for the task, with protected Git metadata and user files, and no process or shell path that can broaden its access. Read-only and artifacts-only jobs get stable source snapshots or checkpoints. Verify alias handling, symlinks and junctions, direct and indirect writes, concurrent sessions, and cessation of the worker and descendants before releasing ownership. An ambiguous result blocks handoff. Git mutations require worker termination and user authority where applicable.

Use V0 deterministic evidence, V1 implementation self-check, V2 independent External Reviewer, and V3 Native Deep Review when justified. No positive review overrides a V0 failure. Corrections reuse accepted artifacts and unaffected stages under the active writer authorization. Invalidate evidence tied to changed inputs or revisions. Keep Augani as the authoritative lifecycle and attempt history, with separate native recovery authorization and unchanged external attempt accounting. 9Router owns model fallback. Codex owns capability escalation.

## Phase task contracts

| Phase / Augani item | Owner and allowed scope | Dependency and implementation contract | Deterministic acceptance |
|---|---|---|---|
| G4-A / item-001 | Codex, planning and evidence Markdown only | Accepted G3 baseline. Reconcile local state, interfaces, ownership and phase dependencies. Record bootstrap gate. | Verify Git/ledger/process observations, baseline preservation and plan creation. |
| G4-B / item-002 | Authorized coder. Registry/routing JSON, new `bridge/adaptive_routing.py` and `tests/test_adaptive_routing.py` | A and authorized scoped bootstrap. Add pure `classify_workflow(task, policy)` and `select_agent(requirements, registry, runtime_evidence, policy)` decisions with reasons and no live execution. Add the native-coder registry entry and pure fallback, effort-selection and budget-aware decisions. Keep legacy callers compatible. | `python -B -m unittest tests.test_adaptive_routing -v` covers R01–R05 and R07, including overrides, absent qualification and exact access matching. |
| G4-C / item-003 | Authorized coder. Thin Augani adapter under `poc/` or existing Augani integration entry point, fake fixture and targeted tests | B. Run conditional stages using Augani plans, job dependency IDs and checkpoints. Use fake-only stage execution before D. Integrate remaining-scope External-to-Native handoffs through the existing lifecycle and dependencies. Preserve candidates and accepted evidence, identify stale results on escalation, and supply safe verification feedback where supported. | Run targeted L0–L3 and objective-variant tests. Prove actual dependency gating and preservation across restart/escalation (R06–R07). |
| G4-D / item-004 | Authorized coder. Permission/ownership helpers, affected OpenCode profiles except G3, recovery policy, tests and the C adapter integration | C. Install the runtime boundary, canonical writer guard, child lifecycle verification, V0–V3 gates and durable correction budget. Enforce native isolation, effort, time, job and correction limits, observable token or cost ceilings, and separate native authorization without relaxing external attempt accounting. Block unsafe automatic escalation or budget extension. This is production enforcement; bootstrap already requires an independent write boundary. | W01–W05 and V01–V06. Test actual denied writes, aliases, cross-process concurrency, process death, positive review after V0 failure and retry after route change. |
| G4-E / item-005 | Codex acceptance. Authorized coder for fixture corrections. Independent scoped review. Evidence and handoff artifacts. | D. Reconcile criterion evidence and run targeted G3 regression for touched interfaces. Prepare separate live approval. | R01–R07, W01–W05, V01–V06 and C01–C02 must each have observed evidence. Verify native eligibility, scope and effort restrictions, exhaustion and exclusion of simultaneous External and Native writers. |

All execution packets must include the objective, baseline and input artifacts, paths and access, forbidden actions, dependency IDs, verification commands, attempt/timeout budget and expected structured output. Workers return the job result, files, tests, evidence, blockers and next action. They cannot delegate, perform Git mutations, touch G3 state or change combos. Each external job needs independently scoped authorization. The first source task must prove its boundary with a deterministic fake worker before dispatch.

## Checklist

- [x] G4-A architecture and contract reconciliation
- [ ] G4-B registry and adaptive routing
- [ ] G4-C execution and coordination
- [ ] G4-D permissions, verification and recovery
- [ ] G4-E offline acceptance and live readiness

## Validation strategy

All 20 G4 acceptance criteria in the reconciliation handoff are NOT_RUN at this checkpoint. Historical G3 acceptance is the baseline, and no compatibility regression has been rerun. Report criterion IDs with command, exit code, test count, relevant job or session, scope result and before/after state. Keep test outputs and sanitized routing traces in the existing evidence structure.

## Completion criteria

G4 is ready for live verification after all offline gates pass. Controlled live verification then needs separate approval for the minimum new coverage: one scoped External Coder job and one independent External Reviewer job, each on an isolated task with a fixed scope and explicit timeout. Add a native invocation only if offline results identify an unproven mandatory phase gate. No automatic retries in the initial live run. Exercise escalation and failure cases offline first.

## Handoff and current blocker

G4-B0 and complete-file delivery are accepted. G4-B remains blocked after three rejected external jobs. Candidate 003 passed delivery, replay and all 24 legacy compatibility tests, but passed 24/40 adaptive tests and 3/7 independent probes. The owner authorized one bounded native recovery of the remaining scope. Preserve the external limit of three and all prior jobs and verdicts.

### Native fallback policy

Prefer external execution while a qualified candidate meets capability, access, reliability, risk and budget requirements. Permit native fallback on documented capability or context limits, repeated acceptance failures, exhausted external attempts, or bounded runtime recovery failure where policy allows. Recoverable infrastructure and delivery failures are insufficient on their own. Native Reviewer and Native Architect retain their existing permissions.

Select GPT-6 Luna only and use the lowest sufficient authorized effort. Permit low, medium or high up to the task ceiling. Choose effort from actual complexity and risk, independent of workflow level. Require an explicit scope, maximum file count, job and correction counts, timeout, observable token or cost ceiling when enforceable, and escalation authorization. Record unavailable metering. Native execution must follow verified termination of external descendants and acquisition of exclusive ownership. Require independent review and deterministic verification before integration, then repeat targeted verification.

Keep one Augani-backed attempt history and distinguish native recovery authorizations from external development attempts. If the pinned runtime lacks a supported recovery transition, preserve a verified candidate and obtain a state reconciliation decision before advancing the plan.

## G4-D Runtime Lifecycle Management

Add a lightweight, configurable readiness check before dispatch. Detect Docker availability and ensure the required Augani containers are running. Support externally managed 9Router and optional automatic startup on Windows through the existing approved launch mechanism. Prevent duplicate service instances and wait for readiness with a bounded timeout. Verify the endpoint and required model route from the actual isolated worker environment before dispatch.

Reuse existing startup commands, configuration and recovery mechanisms. Distinguish startup, connectivity and readiness failures from model capability and implementation failures. Pre-dispatch infrastructure failures must leave implementation attempt counters unchanged. Keep credentials out of status output, logs and evidence.

Verify both management modes, duplicate-start prevention, timeout behavior, Docker-to-host connectivity, route availability, and preservation of attempt counters on pre-dispatch failure.

### G4-D Executor Policy Integrity

Executor-pool updates must retain mandatory retry limits and preserve durable attempt history across route changes. Fail closed before dispatch when the limit is missing or invalid. Keep qualification jobs outside implementation attempt accounting. Use auditable, concurrency-safe policy updates and keep retry counters and authorization checks consistent across orchestrator sessions.

Reuse the existing Augani lifecycle and Hybrid Agent adapter. Add targeted regression coverage for pool amendments, cross-session checks, route changes and qualification accounting.
