import json
import tempfile
from pathlib import Path
import sys
sys.path.insert(0, 'D:\\tools\\hybrid-agent')
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
    print('session_id:', outcome.session_id)
    print('terminal_seen:', outcome.terminal_seen)
    print('terminal_reason:', outcome.terminal_reason)
    print('has_terminal_completion:', outcome.has_terminal_completion)
    print('protocol_ok:', outcome.protocol_ok)