import json
import tempfile
from pathlib import Path
import sys
sys.path.insert(0, 'D:\\tools\\hybrid-agent')

# Let's trace through the actual parse_events logic using the exact same file reading
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
    
    # Replicate the exact file reading from parse_events
    import re
    _SESSION_RE = re.compile(r"^ses_[A-Za-z0-9]{8,120}$")
    
    session_id = None
    source = path
    handle = source.open("r", encoding="utf-8-sig", errors="replace")
    
    with handle:
        for line_number, line in enumerate(handle, start=1):
            print(f'Raw line {line_number}: {repr(line)}')
            if not line.strip():
                continue
            if len(line) > 4 * 1024 * 1024:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            
            print(f'  Parsed event: {event}')
            part = event.get("part")
            if not isinstance(part, dict):
                part = {}
            
            candidate_session = event.get("sessionID") or part.get("sessionID")
            print(f'  candidate_session: {candidate_session}')
            if isinstance(candidate_session, str) and _SESSION_RE.fullmatch(candidate_session):
                print(f'  MATCHES regex')
                if session_id is None:
                    session_id = candidate_session
                    print(f'  SET session_id = {session_id}')
                elif session_id != candidate_session:
                    print(f'  CONFLICT')
            else:
                print(f'  NO MATCH')
    
    print(f'\nFinal session_id: {session_id}')