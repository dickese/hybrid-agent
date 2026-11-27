# G3 Plan: Codex Integration Live Test

## Goal
Execute the G3-C live acceptance fixture: implement slugify function with tests using a single authorized OpenCode worker job.

## Decisions and assumptions
- Use the pinned Augani upstream implementation (commit 8d9b897c49500e8e1b54ec8028352544db95618d).
- Container: hybrid-agent-g3:0.1 with persistent lifecycle via docker-compose.
- Shared workspace: D:/tools/hybrid-agent/.runtime/poc-g3/workspace (host) / /g3/workspace (container).
- 9Router endpoint: http://host.docker.internal:20128/v1.
- Worker route: opencode-9router=9router/agent-build with bridge-g3 agent profile.
- Scope restricted to src/** and tests/** only.
- Dashboard accessible from Windows host at http://127.0.0.1:8080 via proxy.

## Constraints and guardrails
- Maximum one live worker job (enforced by G3_AUTHORIZED=1 + durable state).
- Worker permissions scoped to src/** and tests/** only.
- No live inference without explicit G3_AUTHORIZED=1.
- No automatic acceptance - Codex must perform independent review.
- Test command: python -B -m unittest discover -s tests -t . -v (8 reference assertions).

## Checklist
- [ ] item-001: Implement slugify function with tests

## Validation strategy
- Worker creates src/slugify.py and tests/test_slugify.py.
- Deterministic unit tests must pass (8 reference cases).
- Independent Codex review of diff + test output required.
- Record review with --test evidence for acceptance.
- Plan advances to complete only after accepted verdict.
- Dashboard shows job progression from Windows host.

## Completion criteria
- src/slugify.py exists with slugify(text: str) -> str function.
- tests/test_slugify.py exists with 8 reference test cases.
- All unit tests pass.
- Independent Codex review recorded as accepted.
- Plan status shows complete.
- Dashboard accessible from Windows host.

## Plan ID
g3

## Title
G3 Codex integration live test

## Workspace
/g3/workspace

## Executor
opencode-9router=9router/agent-build

## Checklist Items
- id: item-001
  title: Implement slugify function with tests
  state: pending
  depends_on: []