#!/usr/bin/env python3
"""Minimal HTTP reverse proxy for dashboard: forwards 0.0.0.0:8080 -> 127.0.0.1:8081 with Host header preservation."""
from __future__ import annotations

import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
import urllib.request
import urllib.error


TARGET_HOST = "127.0.0.1"
TARGET_PORT = 8081
PROXY_PORT = 8080


class ProxyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self._proxy_request()

    def do_POST(self):
        self._proxy_request()

    def _proxy_request(self):
        # Build target URL
        target_url = f"http://{TARGET_HOST}:{TARGET_PORT}{self.path}"

        # Read request body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else None

        # Prepare headers for upstream - dashboard validates Host and Origin
        # The dashboard expects Host: 127.0.0.1:8081 and Origin: http://127.0.0.1:8081
        proxy_headers = dict(self.headers)
        proxy_headers["Host"] = f"{TARGET_HOST}:{TARGET_PORT}"
        proxy_headers["Origin"] = f"http://{TARGET_HOST}:{TARGET_PORT}"

        # Create request to target
        req = urllib.request.Request(target_url, data=body, method=self.command, headers=proxy_headers)

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                self.send_response(resp.status)
                for key, value in resp.headers.items():
                    # Skip hop-by-hop headers
                    if key.lower() not in ("transfer-encoding", "connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "upgrade"):
                        self.send_header(key, value)
                self.end_headers()
                self.wfile.write(resp.read())
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            for key, value in e.headers.items():
                if key.lower() not in ("transfer-encoding", "connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "upgrade"):
                    self.send_header(key, value)
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            self.send_response(502)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(f"Proxy error: {e}".encode())

    def log_message(self, format, *args):
        # Suppress default logging
        pass


def wait_for_dashboard(port: int = 8081, timeout: int = 30) -> bool:
    """Wait for the dashboard to be ready on the given port."""
    import urllib.request
    import urllib.error
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(f"http://{TARGET_HOST}:{port}/api/overview", timeout=2):
                return True
        except urllib.error.HTTPError as e:
            # 401 means dashboard is running but requires auth - this is success
            if e.code == 401:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def start_dashboard(env: dict[str, str]) -> subprocess.Popen:
    """Start the upstream dashboard on port 8081."""
    import subprocess
    proc = subprocess.Popen(
        [
            "python3", "-B", "/work/agent-orchestrator-poc/plugins/agent-orchestrator/scripts/cli_agent_job.py",
            "dashboard-web", "--port", "8081", "--no-open"
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc


def main():
    # Start the upstream dashboard first
    env = os.environ.copy()
    env["AGENT_ORCHESTRATOR_HOME"] = "/g3/state"
    
    dashboard_proc = start_dashboard(env)
    
    # Wait for dashboard to be ready
    if not wait_for_dashboard(8081, 30):
        print("Dashboard failed to start in time", flush=True)
        dashboard_proc.terminate()
        sys.exit(1)
    
    # Start the proxy
    server = ThreadingHTTPServer(("0.0.0.0", PROXY_PORT), ProxyHandler)
    print(f"Dashboard proxy listening on 0.0.0.0:{PROXY_PORT} -> {TARGET_HOST}:{TARGET_PORT}", flush=True)
    
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        dashboard_proc.terminate()


if __name__ == "__main__":
    import os
    main()