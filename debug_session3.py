import json
import tempfile
from pathlib import Path
import sys
sys.path.insert(0, 'D:\\tools\\hybrid-agent')

# Let's trace through the actual parse_events logic manually
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
    
    # Read raw
    with path.open('r', encoding='utf-8-sig') as f:
        content = f.read()
        print('Raw content:')
        print(repr(content))
    
    # Parse manually
    import re
    _SESSION_RE = re.compile(r"^ses_[A-Za-z0-9]{8,120}$")
    
    session_id = None
    for line_number, line in enumerate(content.splitlines(), start=1):
        if not line.strip():
            continue
        event = json.loads(line)
        print(f'\nLine {line_number}: {event}')
        part = event.get("part") or {}
        candidate_session = event.get("sessionID") or part.get("sessionID")
        print(f'  candidate_session: {candidate_session}')
        if isinstance(candidate_session, str) and _SESSION_RE.fullmatch(candidate_session):
            print(f'  MATCHES regex')
            if session_id is None:
                session_id = candidate_session
                print(f'  SET session_id = {session_id}')
            elif session_id != candidate_session:
                print(f'  CONFLICT: {session_id} != {candidate_session}')
        else:
            print(f'  NO MATCH or not string')
    
    print(f'\nFinal session_id: {session_id}')