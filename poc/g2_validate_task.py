#!/usr/bin/env python3
"""Validate the G2 task packet with the upstream runner's own validator."""
from __future__ import annotations

import importlib.util
import json
import os

RUNNER = os.environ["RUNNER"]
TASK = "/work/poc/g2_task.md"

spec = importlib.util.spec_from_file_location("runner", RUNNER)
assert spec and spec.loader
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

text = open(TASK, encoding="utf-8").read()
problems = runner.validate_task_packet(text)
print(json.dumps({"task": TASK, "problems": problems, "valid": not problems}, indent=2))
