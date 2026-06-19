"""
api.py — the spine. Wraps the dugs engine in a small HTTP service so anything
(a UI, a container, curl, another machine) can drive it over the network.

This is what makes dugs "run local AND host it": the engine logic doesn't change,
we just put a thin HTTP layer in front. Same idea n8n uses to keep its UI and
engine separate — done cleanly.

Pure Python standard library. No installs.

Endpoints:
  GET  /nodes              -> list available node types (for a UI palette)
  GET  /health             -> {"status": "ok"}
  POST /run                -> body = workflow JSON; runs it; returns per-node results

Run:
  python3 api.py                 # listens on http://127.0.0.1:5800
  python3 api.py 0.0.0.0 5800    # listen on all interfaces (for container/remote)
"""

from __future__ import annotations
import os
import sys
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from engine import Engine

HERE = os.path.dirname(os.path.abspath(__file__))
NODES_DIR = os.path.join(HERE, "nodes")

# one engine instance, shared. Re-discovers nodes on each /nodes call so newly
# dropped-in node files show up without a restart (nice for development).
engine = Engine(NODES_DIR)


def node_catalog() -> list[dict]:
    """Describe every discovered node — what a UI needs to draw the palette."""
    engine.registry = engine.registry  # (kept for clarity)
    out = []
    for type_id, cls in sorted(engine.registry.items()):
        out.append({
            "type": type_id,
            "title": cls.TITLE,
            "category": cls.CATEGORY,
            "inputs": cls.INPUTS,
            "outputs": cls.OUTPUTS,
            "params": getattr(cls, "PARAMS", []),
        })
    return out


class Handler(BaseHTTPRequestHandler):
    # quieter logging
    def log_message(self, fmt, *args):
        sys.stderr.write("  api: " + (fmt % args) + "\n")

    def _send(self, code: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        # allow a local UI on another port to call us
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(200, {"ok": True})

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"status": "ok"})
        elif self.path == "/nodes":
            # re-discover so freshly added node files appear
            from engine import discover_nodes
            engine.registry = discover_nodes(NODES_DIR)
            self._send(200, {"nodes": node_catalog()})
        else:
            self._send(404, {"error": "not found", "path": self.path})

    def do_POST(self):
        if self.path != "/run":
            self._send(404, {"error": "not found", "path": self.path})
            return
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            workflow = json.loads(raw)
        except json.JSONDecodeError as e:
            self._send(400, {"error": "invalid JSON", "detail": str(e)})
            return
        try:
            # re-discover in case new node files were added
            from engine import discover_nodes
            engine.registry = discover_nodes(NODES_DIR)
            results = engine.run_workflow(workflow)
            self._send(200, {"ok": True, "results": results})
        except Exception as e:
            self._send(500, {"ok": False, "error": str(e)})


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 5800
    server = ThreadingHTTPServer((host, port), Handler)
    print("=" * 44)
    print("  dugs — api server")
    print("=" * 44)
    print(f"  listening on http://{host}:{port}")
    print(f"  nodes dir:   {NODES_DIR}")
    print( "  endpoints:   GET /health  GET /nodes  POST /run")
    print( "  (ctrl-c to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped.")


if __name__ == "__main__":
    main()
