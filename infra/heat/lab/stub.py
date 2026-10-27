#!/usr/bin/env python3
"""HTTP stub nhan dien backend, khong mo phong API Shlink."""

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import socket
import sys


def make_handler(backend):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", backend):
        raise ValueError("backend phai la nhan 1-64 ky tu chu, so, dau cham, gach noi")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path not in ("/", "/health"):
                self.send_error(404)
                return
            payload = json.dumps({
                "service": "campuslink-lb-stub",
                "backend": backend,
                "hostname": socket.gethostname(),
                "time_utc": datetime.now(timezone.utc).isoformat(),
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format_string, *args):
            # Khong ghi URL, query string hay header nguoi goi vao log.
            print(json.dumps({"time_utc": datetime.now(timezone.utc).isoformat(),
                              "backend": backend, "event": "http_request"}),
                  file=sys.stderr, flush=True)

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", required=True)
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    try:
        handler = make_handler(args.backend)
    except ValueError as error:
        parser.error(str(error))
    with ThreadingHTTPServer((args.bind, args.port), handler) as server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
