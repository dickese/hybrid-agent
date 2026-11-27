#!/usr/bin/env python3
"""Non-inference connectivity probe for the Windows-hosted 9Router.

Reads the key from NINE_ROUTER_KEY (never printed) and reports only status,
model count, and whether the approved route is present.
"""
from __future__ import annotations

import json
import os
import urllib.request

BASE = os.environ.get("ROUTER_BASE", "http://host.docker.internal:20128")
KEY = os.environ.get("NINE_ROUTER_KEY", "").strip()

for label, headers in (
    ("no-auth", {}),
    ("bearer", {"Authorization": f"Bearer {KEY}"} if KEY else {}),
):
    try:
        req = urllib.request.Request(BASE + "/v1/models", headers=headers)
        with urllib.request.urlopen(req, timeout=8) as resp:
            payload = json.loads(resp.read())
        ids = [item.get("id") for item in payload.get("data", [])]
        print(
            json.dumps(
                {
                    "probe": label,
                    "status": resp.status,
                    "model_count": len(ids),
                    "has_agent_build": "agent-build" in ids,
                    "key_present": bool(KEY),
                }
            )
        )
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"probe": label, "error": f"{type(exc).__name__}: {exc}"}))
