#!/usr/bin/env python3
"""Print the exact worker command the unmodified runner builds for a profile.

No process is started and no network/inference is performed. Used to prove the
custom `opencode-9router` adapter produces the intended argv before a live run.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

RUNNER = os.environ["RUNNER"]
CONFIG = os.environ["CONFIG"]
spec = importlib.util.spec_from_file_location("runner", RUNNER)
assert spec and spec.loader
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

profiles = runner.load_profiles(Path(CONFIG))
profile = profiles["opencode-9router"]
prompt_file = Path("/tmp/g2-prompt.md")
prompt_file.write_text("SYNTHETIC PROMPT PLACEHOLDER\n", encoding="utf-8")
command, transport = runner.build_command(
    profile,
    Path("/tmp/g2-workspace"),
    prompt_file,
    "9router/agent-build",
    "bridge-build",
    None,
    None,
    None,
    Path("/tmp/g2-job/channel"),
)
print(json.dumps({"argv": command, "prompt_transport": transport}, indent=2))
sys.exit(0)
