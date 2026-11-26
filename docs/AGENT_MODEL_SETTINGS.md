# Agent Model Settings

## Overview

This document records the requested target settings, effective verified settings, and configuration locations for all six specialized agents. Settings are organized by configuration layer.

## Configuration Layers

| Layer | Responsible For | Configuration File |
|-------|-----------------|-------------------|
| 9Router | Combo membership, model priority, provider selection, routing strategy, internal fallback | 9Router Dashboard (external) |
| OpenCode | Model route selection, capability metadata, context limits, output limits, thinking options, execution profiles, tool permissions, session handling | `opencode.json` |
| CLI Bridge | Logical agent selection, task routing, token budget enforcement, permission boundaries, checkpoints, recovery budgets | `config/bridge.local.json`, `config/agent-registry.json`, `config/routing-policy.json`, `config/recovery-policy.json` |

## Requested Targets vs Effective Verified Settings

| Agent | Thinking Preference | Target Context | Target Output | Effective Context | Effective Output | Verified |
|-------|---------------------|----------------|---------------|-------------------|------------------|----------|
| agent-fast | Auto / Low | 128000 | 8192 | 128000 | 8192 | ✓ (API) |
| agent-build | Auto / Medium | 128000 | 16384 | 128000 | 8192* | ✓ (API) |
| agent-heavy | High | 128000 | 16384 | 128000 | 8192* | ✓ (API) |
| agent-review | Medium / High | 128000 | 8192 | 128000 | 8192 | ✓ (API) |
| agent-vision | Medium | 128000 | 64000 | 128000 | 64000 | ✓ (API) |
| agent-docs | Low | 128000 | 16384 | 128000 | 8192* | ✓ (API) |

**Note**: All agents have qualification status `NOT_VERIFIED` (pending live functional verification). Effective settings are verified from 9Router API `/v1/models/{id}` endpoint. *Output limits: 9Router reports `max_completion_tokens=8192` for most combos (agent-vision: 64000). Target outputs of 16384 are aspirational; effective output = min(OpenCode limit, 9Router max_completion_tokens).

## Per-Agent Model Configuration

### agent-fast (`9router/agent-fast`)

| Setting | Value | Source | Notes |
|---------|-------|--------|-------|
| Model Route | `9router/agent-fast` | `config/bridge.local.json` → `profiles.agent-fast.model` | Combo registered in 9Router |
| OpenCode Model ID | `agent-fast` | `opencode.json` → `providers.9router.models.agent-fast.modelID` | Pass-through to 9Router |
| Context Limit | 128000 | `opencode.json` → `limit.context` | **Verified via 9Router API** |
| Output Limit | 8192 | `opencode.json` → `limit.output` | **Verified: 9Router API reports max_completion_tokens=8192** |
| Thinking | Auto/Low | 9Router combo internal | `thinkingFormat: openai`, `thinkingCanDisable: true` |
| Tools | Disabled | 9Router combo capabilities | `tools: false` |
| Vision | Enabled | 9Router combo capabilities | `vision: true` |
| Safety Margin | 10% | `config/agent-registry.json` → `context_safety_margin` | Applied at bridge layer |

### agent-build (`9router/agent-build`)

| Setting | Value | Source | Notes |
|---------|-------|--------|-------|
| Model Route | `9router/agent-build` | `config/bridge.local.json` → `profiles.agent-build.model` | Combo registered in 9Router |
| OpenCode Model ID | `agent-build` | `opencode.json` → `providers.9router.models.agent-build.modelID` | Pass-through to 9Router |
| Context Limit | 128000 | `opencode.json` → `limit.context` | **Verified via 9Router API** |
| Output Limit | 16384 | `opencode.json` → `limit.output` | Target: 16384; **Verified: 9Router API reports max_completion_tokens=8192** |
| Thinking | Auto/Medium | 9Router combo internal | `thinkingFormat: deepseek`, `thinkingCanDisable: true` |
| Tools | Enabled | 9Router combo capabilities | `tools: true` |
| Vision | Enabled | 9Router combo capabilities | `vision: true` |
| Safety Margin | 10% | `config/agent-registry.json` → `context_safety_margin` | Applied at bridge layer |

### agent-heavy (`9router/agent-heavy`)

| Setting | Value | Source | Notes |
|---------|-------|--------|-------|
| Model Route | `9router/agent-heavy` | `config/bridge.local.json` → `profiles.agent-heavy.model` | Combo registered in 9Router |
| OpenCode Model ID | `agent-heavy` | `opencode.json` → `providers.9router.models.agent-heavy.modelID` | Pass-through to 9Router |
| Context Limit | 128000 | `opencode.json` → `limit.context` | **Verified via 9Router API** |
| Output Limit | 16384 | `opencode.json` → `limit.output` | Target: 16384; **Verified: 9Router API reports max_completion_tokens=8192** |
| Thinking | High | 9Router combo internal | `thinkingFormat: minimax`, `thinkingCanDisable: true` |
| Tools | Enabled | 9Router combo capabilities | `tools: true` |
| Vision | Enabled | 9Router combo capabilities | `vision: true`, `pdf: true`, `audioInput: true`, `videoInput: true` |
| Search | Enabled | 9Router combo capabilities | `search: true` |
| Safety Margin | 10% | `config/agent-registry.json` → `context_safety_margin` | Applied at bridge layer |

### agent-review (`9router/agent-review`)

| Setting | Value | Source | Notes |
|---------|-------|--------|-------|
| Model Route | `9router/agent-review` | `config/bridge.local.json` → `profiles.agent-review.model` | Combo registered in 9Router |
| OpenCode Model ID | `agent-review` | `opencode.json` → `providers.9router.models.agent-review.modelID` | Pass-through to 9Router |
| Context Limit | 128000 | `opencode.json` → `limit.context` | **Verified via 9Router API** |
| Output Limit | 8192 | `opencode.json` → `limit.output` | **Verified: 9Router API reports max_completion_tokens=8192** |
| Thinking | Medium/High | 9Router combo internal | `thinkingFormat: openai`, `thinkingCanDisable: true` |
| Tools | Enabled | 9Router combo capabilities | `tools: true` |
| Vision | Disabled | 9Router combo capabilities | `vision: false` |
| Safety Margin | 10% | `config/agent-registry.json` → `context_safety_margin` | Applied at bridge layer |

### agent-vision (`9router/agent-vision`)

| Setting | Value | Source | Notes |
|---------|-------|--------|-------|
| Model Route | `9router/agent-vision` | `config/bridge.local.json` → `profiles.agent-vision.model` | Combo registered in 9Router |
| OpenCode Model ID | `agent-vision` | `opencode.json` → `providers.9router.models.agent-vision.modelID` | Pass-through to 9Router |
| Context Limit | 128000 | `opencode.json` → `limit.context` | **Verified: 9Router API reports contextWindow=128000** |
| Output Limit | 64000 | `opencode.json` → `limit.output` | **Verified: 9Router API reports max_completion_tokens=64000** |
| Thinking | Medium | 9Router combo internal | `thinkingFormat: openai`, `thinkingCanDisable: true` |
| Tools | Enabled | 9Router combo capabilities | `tools: true` |
| Vision | Enabled | 9Router combo capabilities | `vision: true`, `audioInput: true`, `videoInput: true` |
| Safety Margin | 15% | `config/agent-registry.json` → `context_safety_margin` | Higher margin for multimodal |

### agent-docs (`9router/agent-docs`)

| Setting | Value | Source | Notes |
|---------|-------|--------|-------|
| Model Route | `9router/agent-docs` | `config/bridge.local.json` → `profiles.agent-docs.model` | Combo registered in 9Router |
| OpenCode Model ID | `agent-docs` | `opencode.json` → `providers.9router.models.agent-docs.modelID` | Pass-through to 9Router |
| Context Limit | 128000 | `opencode.json` → `limit.context` | **Verified via 9Router API** |
| Output Limit | 16384 | `opencode.json` → `limit.output` | Target: 16384; **Verified: 9Router API reports max_completion_tokens=8192** |
| Thinking | Low | 9Router combo internal | `thinkingFormat: openai`, `thinkingCanDisable: true` |
| Tools | Disabled | 9Router combo capabilities | `tools: false` |
| Vision | Enabled | 9Router combo capabilities | `vision: true`, `audioInput: true`, `videoInput: true` |
| Search | Enabled | 9Router combo capabilities | `search: true` |
| Safety Margin | 10% | `config/agent-registry.json` → `context_safety_margin` | Applied at bridge layer |

## Common Constraints & Limitations

### Context Window
- All combos report `contextWindow: 128000` (verified via 9Router API)
- Bridge applies safety margin (10-15%) to derive effective usable context
- System prompts, message history, tool definitions, output tokens, and reasoning tokens consume context
- If history exceeds compatible model's context budget, compaction or checkpoint-based rotation required

### Output Tokens
- 9Router API reports `max_completion_tokens: 8192` for agent-fast, agent-build, agent-heavy, agent-review, agent-docs
- 9Router API reports `max_completion_tokens: 64000` for agent-vision
- OpenCode `limit.output` set to target values (8192 or 16384) but actual upstream enforces 9Router limits
- **Conservative approach**: Effective output limit = min(OpenCode limit, 9Router max_completion_tokens)
- For agents targeting 16384 output (agent-build, agent-heavy, agent-docs), actual verified limit is 8192

### Thinking/Reasoning
- Each combo has different `thinkingFormat`: openai, deepseek, minimax
- `thinkingCanDisable: true` for all combos
- `thinkingRange: null` (no explicit low/medium/high range exposed)
- Thinking preference recorded as policy; actual control is 9Router-internal
- **Do not assume** Low/Medium/High maps identically across providers

### Vision/Image Input
- agent-fast: vision=true but tools=false (analysis only)
- agent-build: vision=true, tools=true
- agent-heavy: vision=true, tools=true, pdf/audio/video input
- agent-review: vision=false (text-only review)
- agent-vision: vision=true, tools=true, audio/video input — **verified vision required**
- agent-docs: vision=true, tools=false, audio/video input

**Critical**: agent-vision must not fallback to text-only route when images are required. `vision_fallback_forbidden: true` in recovery policy.

### Tool Calling
- Enabled: agent-build, agent-heavy, agent-review, agent-vision
- Disabled: agent-fast, agent-docs (by combo design)
- OpenCode agent profiles (`bridge-*`) must match combo capabilities

### Streaming & Multi-turn
- All combos support streaming via OpenAI-compatible interface
- Multi-turn tool results depend on upstream model compliance
- Verification required: valid streaming, tool calling, multi-turn results, stream termination

## Verification Status

| Agent | Route Availability | Settings Verified | Streaming Verified | Tool Calling Verified | Multi-turn Verified | Context Verified | Output Verified | Permission Enforced | Session Continuation Verified | Vision Verified | Fallback Compatibility |
|-------|-------------------|-------------------|--------------------|-----------------------|---------------------|------------------|-----------------|---------------------|-------------------------------|-----------------|------------------------|
| agent-fast | ✓ | ✗ | ✗ | N/A | ✗ | ✗ | ✗ | ✗ | ✗ | N/A | ✗ |
| agent-build | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | N/A | ✗ |
| agent-heavy | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | N/A | ✗ |
| agent-review | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | N/A | ✗ |
| agent-vision | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| agent-docs | ✓ | ✗ | ✗ | N/A | ✗ | ✗ | ✗ | ✗ | ✗ | N/A | ✗ |

**Legend**: ✓ = Confirmed, ✗ = NOT_VERIFIED, N/A = Not Applicable

## Configuration Commands

### Verify OpenCode sees all models
```powershell
opencode models
```

### Check specific model configuration
```powershell
# View opencode.json models section
cat opencode.json | ConvertFrom-Json | Select-Object -ExpandProperty providers | Select-Object -ExpandProperty 9router | Select-Object -ExpandProperty models
```

### Test live health for specific agent
```powershell
python -m bridge.cli health --config config/bridge.local.json --live --profile agent-build
```

### List bridge profiles
```powershell
python -c "import json; c=json.load(open('config/bridge.local.json')); [print(f'{k}: {v[\"model\"]} ({v[\"access\"]})') for k,v in c['profiles'].items()]"
```

## Unsupported/Unverified Settings

| Setting | Status | Reason |
|---------|--------|--------|
| Explicit thinking effort (low/medium/high) via API | UNSUPPORTED | 9Router combo internal; `thinkingRange: null` |
| Per-request context/output override | UNVERIFIED | Depends on upstream model compliance |
| Provider-specific model options | UNVERIFIED | 9Router abstracts providers |
| Context compaction mechanism | UNVERIFIED | OpenCode capability not yet tested |
| Exact upstream model identification | UNSUPPORTED | Only combo-level visibility |

## Related Files

- `config/agent-registry.json` — Per-agent effective settings
- `config/bridge.local.json` — Bridge profiles and approved models
- `opencode.json` — OpenCode provider and model configuration
- `config/recovery-policy.json` — Recovery budgets per agent
- `docs/AGENT_ROUTING_GUIDE.md` — Routing and capability requirements
- `docs/AGENT_RECOVERY_GUIDE.md` — Recovery procedures