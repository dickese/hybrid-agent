from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from bridge.config import load_config, parse_config
from bridge.errors import ConfigError
from tests.support import BridgeTestCase, write_fake_config, write_json


class ConfigTests(BridgeTestCase):
    def test_fake_config_loads(self) -> None:
        config = load_config(self.config)
        self.assertEqual(config.worker_type, "fake")
        self.assertEqual(config.profiles["coder"].access, "write")
        snapshot = config.sanitized()
        self.assertNotIn("api_key", json.dumps(snapshot).lower())

    def test_opencode_config_loads(self) -> None:
        opencode_config = self.root / "opencode.json"
        write_json(opencode_config, {"$schema": "https://opencode.ai/config.json"})
        config_dir = self.root / ".opencode"
        config_dir.mkdir()
        data = {
            "schema_version": 1,
            "opencode_executable": sys.executable,
            "opencode_config": str(opencode_config),
            "opencode_config_dir": str(config_dir),
            "runtime_root": str(self.runtime),
            "workspaces": {"demo": str(self.fixture)},
            "profiles": {
                "coder": {
                    "agent": "bridge-coder",
                    "model": "9router/deepseek-v4.1-flash-free",
                    "access": "write",
                }
            },
            "approved_models": ["9router/deepseek-v4.1-flash-free"],
            "worker": {"type": "opencode"},
        }
        path = write_json(self.root / "opencode-bridge.json", data)
        config = load_config(path)
        self.assertEqual(config.worker_type, "opencode")
        self.assertEqual(config.opencode_executable, str(Path(sys.executable).resolve()))

    def test_unknown_key_rejected(self) -> None:
        data = json.loads(self.config.read_text(encoding="utf-8"))
        data["api_key"] = "value"
        with self.assertRaises(ConfigError):
            parse_config(data, source_path=str(self.config))

    def test_model_not_approved_rejected(self) -> None:
        data = json.loads(self.config.read_text(encoding="utf-8"))
        data["approved_models"] = ["other/model"]
        with self.assertRaises(ConfigError):
            parse_config(data, source_path=str(self.config))

    def test_bad_access_rejected(self) -> None:
        data = json.loads(self.config.read_text(encoding="utf-8"))
        data["profiles"]["coder"]["access"] = "admin"
        with self.assertRaises(ConfigError):
            parse_config(data, source_path=str(self.config))

    def test_secret_in_config_rejected(self) -> None:
        data = json.loads(self.config.read_text(encoding="utf-8"))
        data["credential_file"] = "sk-ABCDEFGHIJKLMNOPQRSTUVWX"
        with self.assertRaises(ConfigError):
            parse_config(data, source_path=str(self.config))

    def test_relative_paths_rejected(self) -> None:
        data = json.loads(self.config.read_text(encoding="utf-8"))
        data["runtime_root"] = ".runtime"
        with self.assertRaises(ConfigError):
            parse_config(data, source_path=str(self.config))

    def test_snapshot_does_not_include_secret_value(self) -> None:
        secret = "sk-TESTONLY1234567890ABCDEF"
        secret_file = self.root / "secret.key"
        secret_file.write_text(secret, encoding="utf-8")
        data = json.loads(self.config.read_text(encoding="utf-8"))
        data["credential_file"] = str(secret_file)
        config = parse_config(data, source_path=str(self.config))
        self.assertNotIn(secret, json.dumps(config.sanitized()))

    def test_duplicate_workspace_paths_rejected(self) -> None:
        data = json.loads(self.config.read_text(encoding="utf-8"))
        data["workspaces"]["demo2"] = data["workspaces"]["demo"]
        with self.assertRaises(ConfigError):
            parse_config(data, source_path=str(self.config))


if __name__ == "__main__":
    unittest.main()
