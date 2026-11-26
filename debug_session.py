import json
import tempfile
from pathlib import Path

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
    
    # Debug: read and parse manually
    with path.open('r', encoding='utf-8-sig') as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue
            event = json.loads(line)
            session_id = event.get('sessionID')
            part_session = event.get('part', {}).get('sessionID')
            print('Line {}: type={}, sessionID={}, part.sessionID={}'.format(line_num, event.get('type'), session_id, part_session))