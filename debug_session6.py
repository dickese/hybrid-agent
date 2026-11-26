import json
import tempfile
from pathlib import Path
import sys
sys.path.insert(0, 'D:\\tools\\hybrid-agent')

# Patch FIRST, then import
import bridge.events as events_module
import re

original_parse = events_module.parse_events

def debug_parse(path, *, redactor, max_summary_chars):
    _SESSION_RE = re.compile(r"^ses_[A-Za-z0-9]{8,120}$")
    texts = []
    tools = []
    edit_tools = set()
    counts = {}
    malformed = []
    session_id = None
    error_message = None
    error_code = None
    terminal_seen = False
    terminal_reason = None
    last_type = None
    last_reason = None
    raw_events = 0
    text_chars = 0
    
    source = Path(path)
    handle = source.open("r", encoding="utf-8-sig", errors="replace")
    
    with handle:
        for line_number, line in enumerate(handle, start=1):
            print(f'DEBUG: line {line_number}: {repr(line[:100])}')
            if not line.strip():
                continue
            if len(line) > 4 * 1024 * 1024:
                malformed.append(line_number)
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                malformed.append(line_number)
                continue
            if not isinstance(event, dict):
                malformed.append(line_number)
                continue
            raw_events += 1
            event_type = event.get("type")
            if not isinstance(event_type, str) or not event_type:
                malformed.append(line_number)
                continue
            counts[event_type] = counts.get(event_type, 0) + 1
            last_type = event_type
            part = event.get("part")
            if not isinstance(part, dict):
                part = {}
            
            candidate_session = event.get("sessionID") or part.get("sessionID")
            print(f'DEBUG: candidate_session = {candidate_session}')
            if isinstance(candidate_session, str) and _SESSION_RE.fullmatch(candidate_session):
                print(f'DEBUG: MATCHES regex')
                if session_id is None:
                    session_id = candidate_session
                    print(f'DEBUG: SET session_id = {session_id}')
                elif session_id != candidate_session:
                    malformed.append(line_number)
                    if error_message is None:
                        error_message = "Worker emitted conflicting session IDs"
                        error_code = events_module.FailureCode.UNKNOWN_EXECUTION_STATE
            else:
                print(f'DEBUG: NO MATCH')
            
            if event_type == "text" and isinstance(part.get("text"), str):
                value = part["text"]
                if text_chars < 500_000:
                    remaining = 500_000 - text_chars
                    texts.append(value[:remaining])
                    text_chars += min(len(value), remaining)
            elif event_type == "tool_use":
                tool_name = part.get("tool")
                if isinstance(tool_name, str) and tool_name:
                    tools.append(tool_name)
                    if tool_name.lower() in {"edit", "write", "patch", "multiedit", "apply_patch"}:
                        edit_tools.add(tool_name.lower())
            elif event_type == "step_finish":
                reason = part.get("reason")
                if isinstance(reason, str):
                    last_reason = reason
                    terminal_seen = True
                    terminal_reason = reason.lower()
    
    combined = "\n".join(texts).strip()
    if not combined:
        if tools:
            combined = "Worker used tools: " + ", ".join(sorted(set(tools)))
        else:
            combined = "Worker produced no text summary"
    if len(combined) > max_summary_chars:
        combined = combined[:max_summary_chars].rstrip() + "…"
    redacted = redactor.redact(combined)
    if error_message is not None:
        error_message = redactor.redact(error_message)[:2000]
    
    return events_module.WorkerOutcome(
        session_id=session_id,
        texts=tuple(texts),
        tools_used=tuple(tools),
        edit_tools_used=tuple(sorted(edit_tools)),
        event_counts=counts,
        error_message=error_message,
        error_code=error_code,
        malformed_lines=tuple(malformed),
        terminal_seen=terminal_seen,
        terminal_reason=terminal_reason,
        last_event_type=last_type,
        last_step_reason=last_reason,
        raw_events=raw_events,
        summary=combined,
        redacted_summary=redacted,
    )

events_module.parse_events = debug_parse

# NOW import the patched function
from bridge.events import parse_events
from bridge.redact import SecretRedactor

with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / 'stdout.ndjson'
    events = [
        {
            'type': 'step_start',
            'sessionID': 'ses_abcdefgh12345678',
            'part': {'type': 'step-start'},
        },
        {
            'type': 'tool_use',
            'sessionID': 'ses_abcdefgh12345678',
            'part': {
                'type': 'tool',
                'tool': 'edit',
                'state': {'status': 'completed'},
            },
        },
        {
            'type': 'text',
            'sessionID': 'ses_abcdefgh12345678',
            'part': {'type': 'text', 'text': 'Done.'},
        },
        {
            'type': 'step_finish',
            'sessionID': 'ses_abcdefgh12345678',
            'part': {'type': 'step-finish', 'reason': 'stop'},
        },
    ]
    path.write_text(''.join(json.dumps(e) + '\n' for e in events), encoding='utf-8')
    
    outcome = parse_events(path, redactor=SecretRedactor(), max_summary_chars=2000)
    print(f'\nFinal session_id: {outcome.session_id}')
    print(f'terminal_seen: {outcome.terminal_seen}')
    print(f'terminal_reason: {outcome.terminal_reason}')
    print(f'has_terminal_completion: {outcome.has_terminal_completion}')
    print(f'protocol_ok: {outcome.protocol_ok}')