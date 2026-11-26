# Agent Routing Guide

## Overview

This guide describes the deterministic task routing system for the Hybrid Agent CLI Bridge. Six specialized logical agents are available, each with distinct capabilities, permissions, and intended use cases.

## Agent Registry

| Agent ID | Role | Access | Primary Model Route |
|----------|------|--------|---------------------|
| `agent-fast` | Lightweight execution worker | write | `9router/agent-fast` |
| `agent-build` | General coding worker | write | `9router/agent-build` |
| `agent-heavy` | Complex reasoning worker | write | `9router/agent-heavy` |
| `agent-review` | Independent reviewer | read_only | `9router/agent-review` |
| `agent-vision` | Multimodal analysis worker | write | `9router/agent-vision` |
| `agent-docs` | Documentation worker | write_docs_only | `9router/agent-docs` |

## Default Task Routing

The following mapping is used when Codex does not explicitly select an agent:

| Task Category | Routed Agent |
|---------------|--------------|
| Small automation, preflight, environment setup, log analysis, test execution | `agent-fast` |
| Backend/frontend development, feature implementation, bug fixes, refactoring, test creation | `agent-build` |
| Complex implementation, architecture analysis, multi-module debugging, database migrations | `agent-heavy` |
| Code review, regression analysis, spec compliance, test coverage analysis | `agent-review` |
| Screenshot analysis, UI/UX review, visual regression, wireframe interpretation | `agent-vision` |
| Runbooks, technical specs, business documentation, handoff documents, summarization | `agent-docs` |

## Explicit Agent Selection

Codex may explicitly select a logical agent by specifying the `profile` field in the task contract:

```json
{
  "profile": "agent-heavy",
  ...
}
```

Selection is subject to:
- Capability validation (agent must have required capabilities)
- Qualification status (agent must be QUALIFIED)
- Permission boundaries (task must not require forbidden operations)
- Route health (agent's route must not be quarantined)

## Capability Requirements

| Agent | Required Capabilities |
|-------|----------------------|
| agent-fast | text, reasoning |
| agent-build | text, image, tools, reasoning |
| agent-heavy | text, image, audio, video, pdf, tools, reasoning, search |
| agent-review | text, tools, reasoning |
| agent-vision | text, image, audio, video, tools, reasoning |
| agent-docs | text, image, audio, video, reasoning, search |

## Permission Boundaries

| Agent | Policy | Enforcement |
|-------|--------|-------------|
| agent-fast | write | OpenCode agent profile `bridge-fast` with scoped write |
| agent-build | write | OpenCode agent profile `bridge-build` with scoped write |
| agent-heavy | write | OpenCode agent profile `bridge-heavy` with scoped write |
| agent-review | read_only | OpenCode agent profile `bridge-review` denies edit tools |
| agent-vision | write | OpenCode agent profile `bridge-vision` with scoped write |
| agent-docs | write_docs_only | OpenCode agent profile `bridge-docs` scoped to docs paths |

**Note**: Permission enforcement relies on OpenCode agent profiles. The bridge validates `allowed_paths` in the task contract against actual file changes post-execution.

## Routing Decision Flow

```
Task Contract Received
         │
         ▼
┌─────────────────────────┐
│ Explicit profile set?   │──Yes──▶ Validate capability/qualification/permission/health ──▶ Use explicit
└───────────┬─────────────┘
            │ No
            ▼
┌─────────────────────────┐
│ Match task_category     │
│ to routing_rules[]      │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ Validate selected agent │
│ capability, qualification│
│ permission, route health │
└───────────┬─────────────┘
            │
            ▼
      Route to agent
```

## Verification Commands

```powershell
# Check route health
python -m bridge.cli health --config config/bridge.local.json --live --profile agent-build

# List all profiles
python -c "import json; c=json.load(open('config/bridge.local.json')); print(json.dumps(c['profiles'], indent=2))"

# Verify agent registry
python -c "import json; r=json.load(open('config/agent-registry.json')); print(json.dumps(r['agents'], indent=2))"
```

## Limitations

- Routing is deterministic; no LLM-based router is used
- Agent qualification status is initially NOT_VERIFIED for all six agents
- Route health tracking is at combo level (individual upstream models not isolated)
- Vision fallback is forbidden for agent-vision when images are required

## Related Files

- `config/agent-registry.json` — Machine-readable agent definitions
- `config/routing-policy.json` — Routing rules and capability checks
- `config/recovery-policy.json` — Per-agent recovery budgets
- `docs/AGENT_RECOVERY_GUIDE.md` — Recovery procedures
- `docs/AGENT_MODEL_SETTINGS.md` — Model settings and limits