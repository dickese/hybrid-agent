#!/usr/bin/env python3
"""Minimal HTTP reverse proxy for dashboard: forwards 0.0.0.0:8080 -> 127.0.0.1:8081 with Host header preservation."""
from __future__ import annotations

import sys
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

        # Debug: print headers being sent
        print(f"Proxy: {self.command} {self.path} -> {target_url}", flush=True)
        print(f"Proxy: Host={proxy_headers.get('Host')}, Origin={proxy_headers.get('Origin')}, X-Orchestrator-Token={'***' if 'X-Orchestrator-Token' in proxy_headers else 'MISSING'}", flush=True)

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
            print(f"Proxy: HTTPError {e.code}: {e.read().decode()}", flush=True)
            self.send_response(e.code)
            for key, value in e.headers.items():
                if key.lower() not in ("transfer-encoding", "connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "upgrade"):
                    self.send_header(key, value)
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            print(f"Proxy: Exception: {e}", flush=True)
            self.send_response(502)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(f"Proxy error: {e}".encode())

    def log_message(self, format, *args):
        # Suppress default logging
        pass


def main():
    server = ThreadingHTTPServer(("0.0.0.0", PROXY_PORT), ProxyHandler)
    print(f"Dashboard proxy listening on 0.0.0.0:{PROXY_PORT} -> {TARGET_HOST}:{TARGET_PORT}", flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()