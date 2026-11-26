from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from bridge.events import FailureCode, classify_failure, parse_events
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
            {
                "type": "step_finish",
                "sessionID": "ses_abcdefgh12345678",
                "part": {"type": "step-finish", "reason": "stop"},
            },
        )
        outcome = parse_events(
            self.path, redactor=self.redactor, max_summary_chars=2000
        )
        self.assertTrue(outcome.protocol_ok)
        self.assertTrue(outcome.has_terminal_completion)
        self.assertEqual(outcome.session_id, "ses_abcdefgh12345678")
        self.assertIn("edit", outcome.edit_tools_used)
        self.assertEqual(outcome.terminal_reason, "stop")
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
        self.assertEqual(error["code"], FailureCode.STREAM_INVALID)

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
        self.assertEqual(error["code"], FailureCode.WORKER_ERROR)

    def test_missing_session_fails(self) -> None:
        self.write({"type": "text", "part": {"type": "text", "text": "hello"}})
        outcome = parse_events(
            self.path, redactor=self.redactor, max_summary_chars=2000
        )
        error = classify_failure(exit_code=0, outcome=outcome, stderr_tail="")
        self.assertEqual(error["code"], FailureCode.SESSION_NOT_FOUND)

    def test_no_activity_fails(self) -> None:
        self.write({"type": "step_start", "sessionID": "ses_abcdefgh12345678"})
        outcome = parse_events(
            self.path, redactor=self.redactor, max_summary_chars=2000
        )
        error = classify_failure(exit_code=0, outcome=outcome, stderr_tail="")
        self.assertEqual(error["code"], FailureCode.STREAM_INCOMPLETE)

    def test_partial_stream_without_completion(self) -> None:
        """Test that a stream with activity but no terminal completion is rejected."""
        self.write(
            {
                "type": "step_start",
                "sessionID": "ses_abcdefgh12345678",
                "part": {"type": "step-start"},
            },
            {
                "type": "text",
                "sessionID": "ses_abcdefgh12345678",
                "part": {"type": "text", "text": "Working on it..."},
            },
            # No step_finish - incomplete stream
        )
        outcome = parse_events(
            self.path, redactor=self.redactor, max_summary_chars=2000
        )
        self.assertFalse(outcome.has_terminal_completion)
        self.assertFalse(outcome.protocol_ok)
        error = classify_failure(exit_code=0, outcome=outcome, stderr_tail="")
        self.assertEqual(error["code"], FailureCode.STREAM_INCOMPLETE)

    def test_stream_error_with_exit_code_zero(self) -> None:
        """Test that explicit error events are caught even when exit code is 0."""
        self.write(
            {
                "type": "step_start",
                "sessionID": "ses_abcdefgh12345678",
                "part": {"type": "step-start"},
            },
            {
                "type": "error",
                "sessionID": "ses_abcdefgh12345678",
                "error": {"message": "upstream model returned 429"},
            },
            {
                "type": "step_finish",
                "sessionID": "ses_abcdefgh12345678",
                "part": {"type": "step-finish", "reason": "error"},
            },
        )
        outcome = parse_events(
            self.path, redactor=self.redactor, max_summary_chars=2000
        )
        error = classify_failure(exit_code=0, outcome=outcome, stderr_tail="")
        self.assertEqual(error["code"], FailureCode.RATE_LIMITED)
        self.assertTrue(error["retryable"])

    def test_quota_exhaustion_vs_transient_gateway(self) -> None:
        """Test that quota exhaustion is distinguished from transient gateway errors."""
        self.write(
            {
                "type": "step_start",
                "sessionID": "ses_abcdefgh12345678",
                "part": {"type": "step-start"},
            },
            {
                "type": "error",
                "sessionID": "ses_abcdefgh12345678",
                "error": {"message": "quota exhausted for this model"},
            },
            {
                "type": "step_finish",
                "sessionID": "ses_abcdefgh12345678",
                "part": {"type": "step-finish", "reason": "error"},
            },
        )
        outcome = parse_events(
            self.path, redactor=self.redactor, max_summary_chars=2000
        )
        error = classify_failure(exit_code=0, outcome=outcome, stderr_tail="")
        self.assertEqual(error["code"], FailureCode.QUOTA_EXHAUSTED)
        self.assertFalse(error["retryable"])

        # Gateway error should be retryable
        self.write(
            {
                "type": "step_start",
                "sessionID": "ses_abcdefgh12345678",
                "part": {"type": "step-start"},
            },
            {
                "type": "error",
                "sessionID": "ses_abcdefgh12345678",
                "error": {"message": "502 bad gateway"},
            },
            {
                "type": "step_finish",
                "sessionID": "ses_abcdefgh12345678",
                "part": {"type": "step-finish", "reason": "error"},
            },
        )
        outcome = parse_events(
            self.path, redactor=self.redactor, max_summary_chars=2000
        )
        error = classify_failure(exit_code=0, outcome=outcome, stderr_tail="")
        self.assertEqual(error["code"], FailureCode.GATEWAY_TRANSIENT)
        self.assertTrue(error["retryable"])

    def test_model_generated_error_examples_not_classified(self) -> None:
        """Test that model text containing error examples is not classified as actual failure."""
        self.write(
            {
                "type": "step_start",
                "sessionID": "ses_abcdefgh12345678",
                "part": {"type": "step-start"},
            },
            {
                "type": "text",
                "sessionID": "ses_abcdefgh12345678",
                "part": {"type": "text", "text": "For example, if you see a 429 error, you should retry."},
            },
            {
                "type": "step_finish",
                "sessionID": "ses_abcdefgh12345678",
                "part": {"type": "step-finish", "reason": "stop"},
            },
        )
        outcome = parse_events(
            self.path, redactor=self.redactor, max_summary_chars=2000
        )
        # Should be COMPLETED (no error) because the error text is in an example context
        error = classify_failure(exit_code=0, outcome=outcome, stderr_tail="")
        self.assertIsNone(error, "Model-generated error examples should not be classified as failures")

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
