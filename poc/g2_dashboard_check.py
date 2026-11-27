#!/usr/bin/env python3
"""Start the upstream dashboard, query it with its token, and summarize the overview.

Used to confirm dashboard accessibility and to see whether a job id is exposed.
No inference is performed.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

RUNNER = os.environ["RUNNER"]
JOB_ID = os.environ.get("JOB_ID", "")
env = os.environ.copy()

proc = subprocess.Popen(
    [sys.executable, RUNNER, "dashboard-web", "--no-open", "--port", "0"],
    env=env,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
)
try:
    line = proc.stdout.readline()
    match = re.search(r"(http://127\.0\.0\.1:(\d+)/#token=([A-Za-z0-9_-]+))", line)
    if not match:
        raise SystemExit(f"no dashboard url line: {line!r}")
    port, token = match.group(2), match.group(3)
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/overview",
        headers={"X-Orchestrator-Token": token},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        raw = resp.read().decode("utf-8")
        status = resp.status
    payload = json.loads(raw)
    unauth = None
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/api/overview", timeout=5)
        unauth = "unexpected-200"
    except urllib.error.HTTPError as exc:
        unauth = exc.code
    print(
        json.dumps(
            {
                "status": status,
                "unauth_status": unauth,
                "top_level_keys": sorted(payload.keys()),
                "project_count": len(payload.get("projects", [])),
                "job_id_present_in_body": bool(JOB_ID) and JOB_ID in raw,
                "sample_keys": (
                    sorted(payload["projects"][0].keys())
                    if payload.get("projects")
                    else []
                ),
            },
            indent=2,
        )
    )
finally:
    proc.terminate()
    try:
        proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
