"""Hold a repository lock in a child process for lock tests."""

from __future__ import annotations

import sys
import time

from bridge.lock import RepositoryLock


def main() -> int:
    runtime_root, repository, seconds = sys.argv[1:4]
    with RepositoryLock(
        runtime_root,
        repository,
        timeout_seconds=5,
        run_id="lock-holder",
        task_id="LOCK-TEST",
    ):
        print("LOCKED", flush=True)
        time.sleep(float(seconds))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
