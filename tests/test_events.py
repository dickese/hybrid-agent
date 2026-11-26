from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from bridge.events import classify_failure, parse_events
from bridge.redact import SecretRedactor


def line(event: dict) -> str:
    return json.dumps(event) + "\n"


class EventParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory(prefix="events-")
        self.path = Path(self._temp.name) / "stdout.ndjson"
        self.redactor = SecretRedactor()

    def tearDown(self) -> None:
        self._temp.cleanup()

    def write(self, *events: dict) -> None:
        self.path.write_text("".join(line(event) for event in events), encoding="utf-8")

    def test_success_shape(self) -> None:
        self.write(
            {
                "type": "step_start",
                "sessionID": "ses_abcdefgh12345678",
                "part": {"type": "step-start"},
            },
            {
                "type": "tool_use",
                "sessionID": "ses_abcdefgh12345678",
                "part": {
                    "type": "tool",
                    "tool": "edit",
                    "state": {"status": "completed"},
                },
            },
            {
                "type": "text",
                "sessionID": "ses_abcdefgh12345678",
                "part": {"type": "text", "text": "Done."},
            },
        )
        outcome = parse_events(
            self.path, redactor=self.redactor, max_summary_chars=2000
        )
        self.assertTrue(outcome.protocol_ok)
        self.assertEqual(outcome.session_id, "ses_abcdefgh12345678")
        self.assertIn("edit", outcome.edit_tools_used)
        self.assertIsNone(
            classify_failure(exit_code=0, outcome=outcome, stderr_tail="")
        )

    def test_malformed_fails_closed(self) -> None:
        self.path.write_text(
            line({"type": "step_start", "sessionID": "ses_abcdefgh12345678"})
            + "{broken\n"
            + line(
                {
                    "type": "text",
                    "sessionID": "ses_abcdefgh12345678",
                    "part": {"type": "text", "text": "plausible"},
                }
            ),
            encoding="utf-8",
        )
        outcome = parse_events(
            self.path, redactor=self.redactor, max_summary_chars=2000
        )
        self.assertFalse(outcome.protocol_ok)
        error = classify_failure(exit_code=0, outcome=outcome, stderr_tail="")
        self.assertEqual(error["code"], "protocol_error")

    def test_error_event_fails_even_with_exit_zero(self) -> None:
        self.write(
            {
                "type": "error",
                "sessionID": "ses_abcdefgh12345678",
                "error": {"message": "provider failed"},
            }
        )
        outcome = parse_events(
            self.path, redactor=self.redactor, max_summary_chars=2000
        )
        error = classify_failure(exit_code=0, outcome=outcome, stderr_tail="")
        self.assertEqual(error["code"], "worker_error")

    def test_missing_session_fails(self) -> None:
        self.write({"type": "text", "part": {"type": "text", "text": "hello"}})
        outcome = parse_events(
            self.path, redactor=self.redactor, max_summary_chars=2000
        )
        error = classify_failure(exit_code=0, outcome=outcome, stderr_tail="")
        self.assertEqual(error["code"], "protocol_error")

    def test_no_activity_fails(self) -> None:
        self.write({"type": "step_start", "sessionID": "ses_abcdefgh12345678"})
        outcome = parse_events(
            self.path, redactor=self.redactor, max_summary_chars=2000
        )
        error = classify_failure(exit_code=0, outcome=outcome, stderr_tail="")
        self.assertEqual(error["code"], "protocol_error")

    def test_auth_classification(self) -> None:
        self.write(
            {
                "type": "text",
                "sessionID": "ses_abcdefgh12345678",
                "part": {"type": "text", "text": "failed"},
            }
        )
        outcome = parse_events(
            self.path, redactor=self.redactor, max_summary_chars=2000
        )
        error = classify_failure(
            exit_code=1, outcome=outcome, stderr_tail="401 Unauthorized"
        )
        self.assertEqual(error["category"], "auth")
        self.assertFalse(error["retryable"])

    def test_secret_summary_redacted(self) -> None:
        secret = "sk-TESTONLY1234567890ABCDEF"
        self.write(
            {
                "type": "text",
                "sessionID": "ses_abcdefgh12345678",
                "part": {"type": "text", "text": f"key={secret}"},
            }
        )
        outcome = parse_events(
            self.path,
            redactor=SecretRedactor([secret]),
            max_summary_chars=2000,
        )
        self.assertNotIn(secret, outcome.redacted_summary)
        self.assertIn("[REDACTED]", outcome.redacted_summary)


if __name__ == "__main__":
    unittest.main()
