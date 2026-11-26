from __future__ import annotations

import unittest

from bridge.contracts import parse_task, validate_relative_path
from bridge.errors import TaskError
from tests.support import task_data


class TaskContractTests(unittest.TestCase):
    def test_valid_task(self) -> None:
        task = parse_task(task_data())
        self.assertEqual(task.task_id, "TEST-001")
        self.assertEqual(task.allowed_paths, ("add.py",))

    def test_unknown_key_rejected(self) -> None:
        data = task_data()
        data["command"] = "rm -rf /"
        with self.assertRaises(TaskError):
            parse_task(data)

    def test_absolute_path_rejected(self) -> None:
        for value in ("C:/tmp/add.py", "/tmp/add.py", "\\\\server\\share\\add.py"):
            with self.subTest(value=value):
                with self.assertRaises(TaskError):
                    validate_relative_path(value)

    def test_traversal_rejected(self) -> None:
        for value in ("../add.py", "a/../../add.py", "a/./b", "a//b"):
            with self.subTest(value=value):
                with self.assertRaises(TaskError):
                    validate_relative_path(value)

    def test_git_and_reserved_paths_rejected(self) -> None:
        for value in (".git/config", "src/.git/hooks/x", "CON", "nul.txt", "a:b"):
            with self.subTest(value=value):
                with self.assertRaises(TaskError):
                    validate_relative_path(value)

    def test_secret_shape_rejected(self) -> None:
        data = task_data(objective="Use sk-ABCDEFGHIJKLMNOPQRSTUVWX as the key")
        with self.assertRaises(TaskError):
            parse_task(data)

    def test_bad_identifiers_rejected(self) -> None:
        for field, value in (
            ("task_id", "bad id"),
            ("workspace_id", "../demo"),
            ("profile", "coder!"),
            ("expected_branch", "bad branch"),
            ("parent_task_id", "x" * 100),
            ("checkpoint_id", "../checkpoint"),
            ("resume_session_id", "not-a-session"),
        ):
            with self.subTest(field=field):
                data = task_data(**{field: value})
                with self.assertRaises(TaskError):
                    parse_task(data)

    def test_timeout_bounds(self) -> None:
        for value in (0, 86401, True, "30"):
            with self.subTest(value=value):
                with self.assertRaises(TaskError):
                    parse_task(task_data(timeout_seconds=value))

    def test_resume_requires_parent(self) -> None:
        with self.assertRaises(TaskError):
            parse_task(task_data(resume_session_id="ses_abcdefgh12345678"))

    def test_metadata_only_fake_scenario(self) -> None:
        task = parse_task(task_data(metadata={"fake_scenario": "timeout"}))
        self.assertEqual(task.fake_scenario, "timeout")
        with self.assertRaises(TaskError):
            parse_task(task_data(metadata={"other": "value"}))

    def test_duplicate_paths_rejected(self) -> None:
        with self.assertRaises(TaskError):
            parse_task(task_data(allowed_paths=["add.py", "add.py"]))

    def test_backslash_normalized(self) -> None:
        self.assertEqual(validate_relative_path("src\\add.py"), "src/add.py")


if __name__ == "__main__":
    unittest.main()
