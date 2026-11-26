from __future__ import annotations

import subprocess
import sys
import unittest

from bridge.errors import LockError
from bridge.lock import RepositoryLock
from tests.support import FRAMEWORK_ROOT, BridgeTestCase


class LockTests(BridgeTestCase):
    def test_cross_process_lock_blocks_then_releases(self) -> None:
        holder = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "tests.lock_holder",
                str(self.runtime),
                str(self.fixture),
                "5",
            ],
            cwd=str(FRAMEWORK_ROOT),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            shell=False,
        )
        try:
            assert holder.stdout is not None
            ready = holder.stdout.readline().strip()
            self.assertEqual(ready, "LOCKED")
            with self.assertRaises(LockError):
                with RepositoryLock(
                    self.runtime,
                    str(self.fixture),
                    timeout_seconds=0.5,
                    run_id="blocked",
                    task_id="LOCK-TEST",
                ):
                    pass
        finally:
            holder.terminate()
            try:
                holder.wait(timeout=10)
            except subprocess.TimeoutExpired:
                holder.kill()
                holder.wait(timeout=10)

        with RepositoryLock(
            self.runtime,
            str(self.fixture),
            timeout_seconds=2,
            run_id="after-release",
            task_id="LOCK-TEST",
        ):
            pass


if __name__ == "__main__":
    unittest.main()
