from __future__ import annotations

import unittest
from pathlib import Path

from bridge import gitutil
from bridge.errors import PolicyError
from tests.support import BridgeTestCase, make_fixture, run_git


class GitTests(BridgeTestCase):
    def test_clean_fixture(self) -> None:
        state = gitutil.repo_state(self.fixture)
        self.assertFalse(state.dirty)
        self.assertEqual(state.branch, "master")
        self.assertEqual(len(state.head), 40)

    def test_dirty_and_untracked_detection(self) -> None:
        (self.fixture / "add.py").write_text("changed\n", encoding="utf-8")
        (self.fixture / "new file.txt").write_text("new\n", encoding="utf-8")
        entries = gitutil.status_entries(self.fixture)
        paths = {entry.path for entry in entries}
        self.assertIn("add.py", paths)
        self.assertIn("new file.txt", paths)
        self.assertIn("add.py", gitutil.changed_paths(entries))

    def test_rename_keeps_both_paths(self) -> None:
        run_git(self.fixture, "mv", "add.py", "renamed.py")
        entries = gitutil.status_entries(self.fixture)
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0].renamed)
        self.assertEqual(entries[0].path, "renamed.py")
        self.assertEqual(entries[0].orig_path, "add.py")
        self.assertEqual(
            gitutil.changed_paths(entries), ["add.py", "renamed.py"]
        )

    def test_fingerprint_matches_until_user_edit(self) -> None:
        first = gitutil.fingerprint(self.fixture)
        second = gitutil.fingerprint(self.fixture)
        self.assertTrue(gitutil.fingerprints_match(first, second))
        (self.fixture / "add.py").write_text("user edit\n", encoding="utf-8")
        third = gitutil.fingerprint(self.fixture)
        self.assertFalse(gitutil.fingerprints_match(first, third))
        self.assertIn(
            "worktree_hashes",
            gitutil.fingerprint_differences(first, third),
        )

    def test_diff_evidence_and_untracked_hash(self) -> None:
        (self.fixture / "add.py").write_text("changed\n", encoding="utf-8")
        (self.fixture / "new.txt").write_text("new\n", encoding="utf-8")
        destination = self.root / "diff.patch"
        size = gitutil.write_diff_evidence(self.fixture, destination)
        self.assertGreater(size, 0)
        text = destination.read_text(encoding="utf-8")
        self.assertIn("changed", text)
        self.assertIn("# untracked new.txt sha256=", text)

    def test_ensure_within_rejects_escape(self) -> None:
        with self.assertRaises(PolicyError):
            gitutil.ensure_within(self.fixture, "../outside.txt")

    def test_unicode_workspace(self) -> None:
        unicode_fixture = make_fixture(self.root / "fixture có dấu")
        root = gitutil.resolve_workspace(str(unicode_fixture))
        self.assertEqual(Path(root).name, "fixture có dấu")
        state = gitutil.repo_state(root)
        self.assertFalse(state.dirty)


if __name__ == "__main__":
    unittest.main()
