"""Standalone SQLite memory-core: the thin long-term-brain backend behind the
two-method seam (schema/tencentdb/memory-interface.md), PLAN D1 option (b) --
"memory-core standalone (SQLite) with our own thin skill store". It speaks the
HTTP form of the seam (POST /recall, POST /commit) so
jcyber.clients.tencentdb.TencentMemory talks to it unchanged; swap for hosted
TencentDB later without touching the loop.

Run:  uv run python deploy/memory_core.py [port] [db_path]
"""

from __future__ import annotations

import json
import sqlite3
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

DB_PATH = "/tmp/jcyber_memory.db"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS atoms (engagement TEXT PRIMARY KEY, payload TEXT NOT NULL)"
    )
    return conn


class Handler(BaseHTTPRequestHandler):
    def _read(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        data = json.loads(raw or b"{}")
        return data if isinstance(data, dict) else {}

    def _send(self, obj: object, code: int = 200) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        req = self._read()
        engagement = str(req.get("engagement", ""))
        conn = _conn()
        try:
            if self.path == "/commit":
                conn.execute(
                    "INSERT INTO atoms (engagement, payload) VALUES (?, ?) "
                    "ON CONFLICT(engagement) DO UPDATE SET payload = excluded.payload",
                    (engagement, json.dumps(req.get("outbox", {}))),
                )
                conn.commit()
                self._send({})
            elif self.path == "/recall":
                row = conn.execute(
                    "SELECT payload FROM atoms WHERE engagement = ?", (engagement,)
                ).fetchone()
                self._send(json.loads(row[0]) if row else {})
            else:
                self._send({"error": "not found"}, 404)
        finally:
            conn.close()

    def log_message(self, *args: object) -> None:
        return


def serve(host: str = "127.0.0.1", port: int = 8130) -> None:
    server = HTTPServer((host, port), Handler)
    print(f"memory-core on http://{host}:{port} db={DB_PATH}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    port_arg = int(sys.argv[1]) if len(sys.argv) > 1 else 8130
    if len(sys.argv) > 2:
        DB_PATH = sys.argv[2]
    serve(port=port_arg)
