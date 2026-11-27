# Augani/agent-orchestrator Assessment for Hybrid Agent Replacement

**Date:** 2026-11-27  
**Status:** COMPLETE — Ready for GO / CONDITIONAL_GO / NO_GO decision

---

## 1. Upstream Capability Assessment Matrix

| Requirement (from Hybrid Agent) | Upstream Status | Evidence / Notes | Gap Severity |
|--------------------------------|-----------------|------------------|--------------|
| **Windows execution** | ⚠️ PARTIAL | Uses `fcntl.flock` for `record_lock` (line 184-193), `os.killpg`/`SIGTERM` for process groups (line 3124-3128), Unix permissions (`mode=0o700`). No Windows equivalents. | **BLOCKER** |
| **Codex coordinator** | ✅ IMPLEMENTED | Built-in routes (`cost-first`, `quality-first`, etc.) define coordinator model (`current-codex-task`) + recommended task model. Coordinator runs as a Codex task, executors are separate CLIs. | — |
| **OpenCode external worker** | ✅ IMPLEMENTED | `BUILTIN_PROFILES["opencode"]` (line 558-571): `argv=["opencode","--cwd","{workspace}","--quiet","--output-format","text","--prompt","{prompt_text}"]`, `prompt_transport="arg"`. Model args supported via `--model`. | — |
| **Custom CLI adapters** | ✅ IMPLEMENTED | `load_profiles()` merges `BUILTIN_PROFILES` with `~/.config/agent-orchestrator/agents.json` (line 749-760). Profiles validated via `validate_profile()` (line 762-857). Supports 4 prompt transports: `file`, `stdin`, `jsonl-stdin`, `arg`. | — |
| **Explicit model/profile selection** | ✅ IMPLEMENTED | `--cli` required at launch (line 4042). `--model` required when profile has `model_args` (line 1458-1466). `--reasoning-effort`, `--cli-agent`, `--max-turns`, `--max-cost-usd` all mapped per-profile. | — |
| **Project mode without worktrees** | ✅ IMPLEMENTED | `WORKSPACE_MODES = ("worktree", "project")` (line 47). `preferences.json` stores `workspace_mode`. `create-plan` accepts `--topology auto|single|cross-harness`. No forced worktree creation. | — |
| **Single-writer protection** | ✅ IMPLEMENTED | `record_lock()` uses `fcntl.flock` on `.lock` files (line 184-193). Active workspace check in `command_launch` (line 2871-2876). **Windows-incompatible locking.** | **BLOCKER** |
| **Durable plan/job state** | ✅ IMPLEMENTED | Plans at `~/.codex/agent-orchestrator/plans/<plan_id>/plan.json`. Jobs at `~/.codex/agent-orchestrator/jobs/<job_id>/` with `meta.json`, `result.json`, `review.json`, `events/`, `questions/`. Checkpoint via `plan-checkpoint`. | — |
| **Progress dashboard** | ✅ IMPLEMENTED | `command_dashboard` (terminal, line 3792-3806) + `dashboard-web` (HTTP server, line 3809-3812). `ensure-dashboard` auto-starts web server. | — |
| **Independent review/acceptance** | ✅ IMPLEMENTED | `record-review` command (line 3479-3516) requires `--verdict accepted|repair_required|rejected`, `--reviewer`, `--test` (mandatory for `accepted`). Updates plan item state. Immutable after acceptance. | — |
| **Retry/recovery/resume** | ✅ IMPLEMENTED | Executor policy `on_exhausted`: `request_user_approval` or `request_user_then_terra_after_grace`. Terra fallback gated by feedback timeout + pool exhaustion (line 2268-2338). Per-plan `max_attempts_per_item` (default 3). | — |
| **Human intervention** | ✅ IMPLEMENTED | `feedback` system (line 983-1037): `create_feedback` → `notify_user` (macOS `osascript`, Linux `notify-send`) → `answer_feedback`. Worker `ask` channel (line 3352-3392) with `--wait-seconds` (default 1800). | — |
| **Permission boundaries** | ✅ IMPLEMENTED | Per-profile sandbox flags: Codex `--sandbox workspace-write`, Claude `--permission-mode acceptEdits`, Cursor `--sandbox enabled`, OpenCode runs in workspace with `--cwd`. No global "allow all" default. | — |

### Summary: Upstream Coverage
- **11/12 requirements natively implemented**
- **1 BLOCKER: Windows compatibility** (fcntl locking, Unix signals, Unix permissions)
- **1 CONDITIONAL: OpenCode model routing via 9Router** — requires verification that `--model "9router/agent-build"` works with `prompt_transport="arg"`

---

## 2. Windows Compatibility Analysis

### Blockers (require code changes in upstream)

| Component | Location | Issue | Fix Approach |
|-----------|----------|-------|--------------|
| **Record locking** | `record_lock()` line 184-193 | `fcntl.flock` Unix-only | Replace with cross-platform lock: `portalocker` lib or Windows `msvcrt.locking` / `CreateFile` with `FILE_FLAG_DELETE_ON_CLOSE` + exclusive share mode |
| **Process group termination** | `terminate_process_group()` line 3124-3128 | `os.killpg` + `SIGTERM`/`SIGKILL` Unix-only | Windows: use Job Objects (already implemented in Hybrid Agent `bridge/proc.py:JobObject`) or `taskkill /T /PID` |
| **File permissions** | Multiple `mode=0o700`, `os.chmod(path, 0o600)` | Unix permissions meaningless on Windows | No-op on Windows; rely on ACLs / default user isolation |
| **Notifications** | `notify_user()` line 884-909 | `osascript` (macOS), `notify-send` (Linux) | Windows: use `win10toast` or PowerShell `New-BurntToastNotification` |
| **`start_new_session=True`** | `subprocess.Popen` line 3082, 3185, 3191 | Unix session leader semantics | Windows: `CREATE_NEW_PROCESS_GROUP` (0x00000200) + Job Object for tree kill |
| **`close_fds=True`** | `subprocess.Popen` line 3094, 3192 | Unix fd inheritance control | Windows default is non-inheritable; can omit or set `False` |

### Estimated Fix Effort
- **Lock replacement**: ~50 lines (cross-platform context manager)
- **Process termination**: ~30 lines (Hybrid Agent's `JobObject` is reusable)
- **Notifications**: ~20 lines (Windows toast fallback)
- **Permissions**: ~10 lines (no-op shim)
- **Total**: ~110 lines of platform abstraction

**Recommendation**: Fork upstream and maintain a Windows-compatible branch, or contribute PRs upstream (maintainers may accept).

---

## 3. Reusable Hybrid Agent Components (Preserve These)

| Component | Location | Why Reusable | Integration Approach |
|-----------|----------|--------------|----------------------|
| **Agent Registry (6 agents)** | `config/agent-registry.json` | Rich metadata: descriptions, suitable/unsuitable tasks, capabilities, permission policies, thinking preferences, escalation paths, context/output limits | Map to upstream profiles + executor policies; use as source of truth for routing |
| **Routing Policy** | `config/routing-policy.json` | Deterministic task_category → agent mapping with priority, capability checks, permission requirements | Translate to upstream `automatic_executor_policy` + custom routes |
| **Recovery Policy** | `config/recovery-policy.json` | Per-agent retry budgets, failure classification (17 codes), explicit detection rules, route health tracking, escalation recommendations, bootstrap self-recovery | Upstream has simpler retry (per-plan `max_attempts_per_item`); Hybrid Agent's is richer — adapt as **custom executor policy extension** |
| **CLI Invocation Helpers** | `bridge/proc.py` | Windows JobObject, process tree kill, creation-time verification, stderr tail capture, timeout handling | **Directly reusable** for Windows-compatible worker execution in fork |
| **Task Contracts** | `bridge/contracts.py` | Structured task validation (required sections, schema) | Upstream has `validate_task_packet` with 9 required sections — compatible; Hybrid Agent's can be stricter overlay |
| **Event/State Store** | `bridge/store.py`, `bridge/events.py` | Durable JSONL events, checkpoint/resume, run listing | Upstream has equivalent (`events/`, `meta.json`, `result.json`) — **migrate to upstream format** |
| **Git Utilities** | `bridge/gitutil.py` | Workspace fingerprinting, diff stat, scope violation detection | Upstream has `git_snapshot`, `scope_violations` — functionally equivalent |
| **Fake Worker / Fixture Tests** | `tests/test_*.py` | Deterministic testing without live CLIs | Upstream has no test suite — **port tests to validate fork behavior** |
| **Failure Classification** | `bridge/events.py:classify_failure` + `recovery-policy.json` | 17 failure codes with explicit detection rules | Upstream infers from exit codes/logs — Hybrid Agent's is more precise; **contribute upstream** |

---

## 4. Required Thin Adapters (New Code)

| Adapter | Purpose | Est. Lines |
|---------|---------|------------|
| **OpenCode 9Router Profile** | Custom `agents.json` entry for `opencode` profile with `model_args=["--model","{model}"]` where model=`9router/agent-build` etc. | 30 |
| **Windows Lock Shim** | Cross-platform `record_lock` replacing `fcntl.flock` | 50 |
| **Windows Process Shim** | `terminate_process_group` using JobObject (port from `bridge/proc.py`) | 30 |
| **Windows Notification Shim** | `notify_user` using Windows toast | 20 |
| **Recovery Policy → Executor Policy Bridge** | Translate Hybrid Agent's per-agent recovery config into upstream's executor policy + Terra fallback rules | 80 |
| **Agent Registry → Route/Profile Generator** | Auto-generate upstream `BUILTIN_ROUTES` + custom profiles from `agent-registry.json` | 100 |
| **Task Contract Validator** | Wrapper around upstream `validate_task_packet` adding Hybrid Agent's stricter rules | 40 |
| **Total New Code** | | **~350 lines** |

---

## 5. PoC Verification Plan (Minimal Isolated)

### Prerequisites (No Codex Plugin Install, No Paid Usage)
- OpenCode installed locally (`opencode` on PATH)
- 9Router running locally on `http://127.0.0.1:20128/v1` with valid key
- Python 3.10+

### Step 1: Prepare Custom OpenCode Profile
```json
// ~/.config/agent-orchestrator/agents.json
{
  "agents": {
    "opencode-9router": {
      "display_name": "OpenCode (9Router)",
      "description": "OpenCode worker using 9Router model combos",
      "maturity": "stable",
      "argv": [
        "opencode",
        "--cwd", "{workspace}",
        "--quiet",
        "--output-format", "text",
        "--prompt", "{prompt_text}"
      ],
      "prompt_transport": "arg",
      "model_args": ["--model", "{model}"],
      "executable_candidates": ["opencode", "opencode.exe"]
    }
  }
}
```

### Step 2: Verify OpenCode Model Selection Works
```bash
# Test 1: Direct OpenCode invocation with 9Router model
opencode --cwd /tmp/test --quiet --output-format text --prompt "Say hello" --model "9router/agent-fast"

# Test 2: Via upstream runner (dry-run launch)
python cli_agent_job.py launch \
  --cli opencode-9router \
  --model 9router/agent-fast \
  --workspace /tmp/test \
  --task-file task.md \
  --approved-executor opencode-9router=9router/agent-fast \
  --json
```

### Step 3: Verify Coordinator + Worker Flow
```bash
# Create a minimal plan
cat > plan.md << 'EOF'
# Goal
Test coordinator-executor handoff

# Checklist
- [ ] Item 1: Worker says hello
EOF

python cli_agent_job.py create-plan --plan-file plan.md --workspace /tmp/test --title "PoC" --strategy cost-first --risk low --json

# Launch executor job bound to plan
python cli_agent_job.py launch \
  --cli opencode-9router \
  --model 9router/agent-fast \
  --workspace /tmp/test \
  --task-file task.md \
  --plan-id <plan_id> \
  --checklist-item item-001 \
  --approved-executor opencode-9router=9router/agent-fast \
  --json
```

### Step 4: Verify Review Gate
```bash
# After job succeeds, record review
python cli_agent_job.py record-review \
  --job-id <job_id> \
  --verdict accepted \
  --reviewer "PoC Validator" \
  --test "echo 'test passed'" \
  --notes "Worker completed task" \
  --json
```

### Step 5: Verify Dashboard
```bash
python cli_agent_job.py dashboard --watch --interval 2
python cli_agent_job.py ensure-dashboard --port 8080 --no-open
```

### Success Criteria
- [ ] OpenCode accepts `--model "9router/agent-*"` and routes correctly
- [ ] Job creates durable state in `~/.codex/agent-orchestrator/jobs/`
- [ ] Coordinator (plan) → Executor (job) → Review flow works end-to-end
- [ ] Dashboard shows job progress
- [ ] No Codex plugin installation, no Codex CLI auth, no paid API calls

---

## 6. GO / CONDITIONAL_GO / NO_GO Recommendation

### Recommendation: **CONDITIONAL_GO**

### Conditions to Resolve Before Full Migration

| # | Condition | Owner | Effort | Blocking? |
|---|-----------|-------|--------|-----------|
| 1 | **Windows lock/process/notification shims implemented** | Team | ~2 days | **YES** |
| 2 | **OpenCode + 9Router model routing verified** (PoC Step 2) | Team | ~2 hours | **YES** |
| 3 | **Custom OpenCode profile registered in `agents.json`** | Team | ~30 min | No (trivial) |
| 4 | **Hybrid Agent recovery policy mapped to upstream executor policy** | Team | ~1 day | No (can iterate post-migration) |
| 5 | **Agent registry → route/profile generator written** | Team | ~1 day | No (manual mapping works for PoC) |

### Migration Strategy
1. **Week 1**: Implement Windows shims (fork upstream), run PoC verification
2. **Week 2**: Map 6 agents → custom profiles + executor policies; migrate task contracts
3. **Week 3**: Port recovery policy logic; integrate dashboard; freeze Hybrid Agent bridge
4. **Week 4**: End-to-end validation; deprecate `bridge/` in favor of upstream CLI

### Risk Mitigation
- **Keep Hybrid Agent bridge operational** until PoC passes all success criteria
- **Fork upstream** at known-good commit (tag `v0.x`) to control Windows fixes
- **No Codex plugin install** — run `cli_agent_job.py` directly as standalone script
- **No paid usage** — 9Router local gateway only

### What We Gain (vs. Hybrid Agent)
| Feature | Hybrid Agent | Upstream |
|---------|--------------|----------|
| Multi-CLI support (10+) | OpenCode only | ✅ OpenCode, Codex, Claude, Cursor, Gemini, Grok, Kimi, Devin, Antigravity, DeepSeek |
| Durable plan/checklist ledger | Custom JSON | ✅ Native, with `plan-checkpoint` for coordinator continuity |
| Independent review gate | Custom `record-review` | ✅ Native, immutable verdicts, test evidence required |
| Executor allowlist + Terra fallback | Manual | ✅ Policy-driven, user-approved, feedback-gated |
| Progress dashboard | Custom terminal | ✅ Terminal + Web (real-time) |
| Human feedback/escalation | Custom events | ✅ Native `feedback` + `ask` channel with notifications |
| Metrics / executor ranking | Manual | ✅ `metrics`, `recommend-executors` with local evidence |
| Cross-harness teams | Not supported | ✅ `topology: cross-harness` with native subagent deny |

---

## 7. Appendix: Key File References

### Hybrid Agent (Current)
- `config/agent-registry.json` — 6 logical agents
- `config/routing-policy.json` — Task → agent routing rules
- `config/recovery-policy.json` — Per-agent recovery, failure classification
- `config/bridge.local.json` — Working OpenCode + 9Router config
- `bridge/proc.py` — Windows JobObject, process management
- `bridge/contracts.py` — Task validation
- `bridge/recovery.py` — Recovery engine
- `opencode.json` — 9Router model definitions

### Upstream (Augani/agent-orchestrator)
- `plugins/agent-orchestrator/scripts/cli_agent_job.py` — Main runner (~4300 lines)
- `BUILTIN_PROFILES["opencode"]` — Line 558-571
- `BUILTIN_ROUTES` — Line 153-224
- `record_lock` — Line 184-193 (fcntl)
- `notify_user` — Line 884-909 (osascript/notify-send)
- `terminate_process_group` — Line 3124-3128 (killpg)
- `automatic_executor_policy` — Line 1375-1426
- `validate_task_packet` — Line 1237-1254

---

**Prepared by:** Agent Build (9Router)  
**Next Action:** Execute PoC verification (Section 5) to resolve Condition #2