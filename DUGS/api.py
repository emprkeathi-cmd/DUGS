"""
api.py — the spine. Wraps the dugs engine in a small HTTP service so anything
(a UI, a container, curl, another machine) can drive it over the network.

Pure Python standard library. No installs.

Endpoints:
  GET  /nodes              -> list available node types (for a UI palette)
  GET  /health             -> {"status": "ok"}
  POST /run                -> body = workflow JSON; runs it; returns per-node results
  POST /webhooks/register  -> body = workflow JSON; scans for webhook.trigger nodes
                               and registers their paths so real HTTP hits route to them
  ANY  /hook/<path>        -> a real webhook hit; runs the matching workflow

Run:
  python3 api.py                 # listens on http://127.0.0.1:5800
  python3 api.py 0.0.0.0 5800    # listen on all interfaces (for container/remote)
"""

from __future__ import annotations
import os
import sys
import json
from urllib.parse import urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from engine import Engine, discover_nodes

HERE = os.path.dirname(os.path.abspath(__file__))
NODES_DIR = os.path.join(HERE, "nodes")

engine = Engine(NODES_DIR)

# path -> {"workflow": {...}, "node_name": "...", "method": "POST"}
# Registered whenever a workflow containing a webhook.trigger node is saved
# (the UI should POST to /webhooks/register after every save) or on server boot
# by scanning the projects folder.
webhook_registry: dict[str, dict] = {}

PROJECTS_DIR = os.path.join(HERE, "projects")


def node_catalog() -> list[dict]:
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


def register_webhooks_from_workflow(workflow: dict):
    """Scan a workflow for webhook.trigger nodes and register their paths."""
    for n in workflow.get("nodes", []):
        if n.get("type") == "webhook.trigger":
            path = (n.get("params", {}).get("path") or "/webhook").strip()
            if not path.startswith("/"):
                path = "/" + path
            method = (n.get("params", {}).get("method") or "ANY").upper()
            webhook_registry[path] = {
                "workflow": workflow,
                "node_name": n["name"],
                "method": method,
            }
            print(f"  [webhook] registered {method} /hook{path} -> '{n['name']}' in '{workflow.get('name','?')}'")


def register_all_saved_webhooks():
    """On boot, scan every saved project for webhook triggers."""
    if not os.path.isdir(PROJECTS_DIR):
        return
    for fname in os.listdir(PROJECTS_DIR):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(PROJECTS_DIR, fname)) as f:
                wf = json.load(f)
            register_webhooks_from_workflow(wf)
        except Exception as e:
            print(f"  [warn] could not scan {fname} for webhooks: {e}")


def mark_respond_nodes_as_real(workflow: dict):
    """Flip 'is_test_run' to True on every webhook.respond node so it
    actually raises the signal instead of passing data through (used only
    when a REAL hook hits, not when testing from the editor)."""
    for n in workflow.get("nodes", []):
        if n.get("type") == "webhook.respond":
            n.setdefault("params", {})["is_test_run"] = True


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("  api: " + (fmt % args) + "\n")

    def _send(self, code: int, payload, is_raw=False):
        if is_raw:
            body = payload if isinstance(payload, bytes) else str(payload).encode("utf-8")
            ctype = "text/plain"
        else:
            body = json.dumps(payload).encode("utf-8")
            ctype = "application/json"
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(200, {"ok": True})

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/health":
            self._send(200, {"status": "ok"})
        elif path == "/nodes":
            engine.registry = discover_nodes(NODES_DIR)
            self._send(200, {"nodes": node_catalog()})
        elif path == "/webhooks":
            self._send(200, {"registered": [
                {"path": p, "method": v["method"], "node": v["node_name"], "workflow": v["workflow"].get("name")}
                for p, v in webhook_registry.items()
            ]})
        elif path.startswith("/hook/"):
            self._handle_webhook_hit(path[5:], "GET", parsed)
        else:
            self._send(404, {"error": "not found", "path": path})

    def _do_any(self, method):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/run":
            self._handle_run()
        elif path == "/webhooks/register":
            self._handle_register()
        elif path.startswith("/hook/"):
            self._handle_webhook_hit(path[5:], method, parsed)
        else:
            self._send(404, {"error": "not found", "path": path})

    def do_POST(self):
        self._do_any("POST")

    def do_PUT(self):
        self._do_any("PUT")

    def do_PATCH(self):
        self._do_any("PATCH")

    def do_DELETE(self):
        self._do_any("DELETE")

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return None, b""
        try:
            return json.loads(raw), raw
        except json.JSONDecodeError:
            return None, raw

    def _handle_run(self):
        body, raw = self._read_json_body()
        if body is None and raw:
            self._send(400, {"error": "invalid JSON"}); return
        workflow = body or {}
        try:
            engine.registry = discover_nodes(NODES_DIR)
            results = engine.run_workflow(workflow)
            self._send(200, {"ok": True, "results": results})
        except Exception as e:
            self._send(500, {"ok": False, "error": str(e)})

    def _handle_register(self):
        body, raw = self._read_json_body()
        if body is None:
            self._send(400, {"error": "invalid JSON"}); return
        try:
            register_webhooks_from_workflow(body)
            paths = [n.get("params", {}).get("path", "/webhook")
                     for n in body.get("nodes", []) if n.get("type") == "webhook.trigger"]
            self._send(200, {"ok": True, "registered_paths": paths})
        except Exception as e:
            self._send(500, {"ok": False, "error": str(e)})

    def _handle_webhook_hit(self, path, method, parsed):
        if not path.startswith("/"):
            path = "/" + path
        entry = webhook_registry.get(path)
        if entry is None:
            self._send(404, {"error": f"no webhook registered for {path}",
                              "hint": "save/open the project in the editor so it auto-registers, "
                                      "or POST the workflow to /webhooks/register"})
            return
        if entry["method"] != "ANY" and entry["method"] != method:
            self._send(405, {"error": f"webhook at {path} expects {entry['method']}, got {method}"})
            return

        body_json, raw = self._read_json_body() if method in ("POST", "PUT", "PATCH", "DELETE") else (None, b"")
        if body_json is None and raw:
            body_json = raw.decode("utf-8", errors="replace")

        query = {k: v[0] if len(v) == 1 else v for k, v in parse_qs(parsed.query).items()}
        headers = {k: v for k, v in self.headers.items()}

        request_data = {
            "method": method,
            "path": path,
            "query": query,
            "headers": headers,
            "body": body_json,
        }

        workflow = json.loads(json.dumps(entry["workflow"]))  # deep copy
        mark_respond_nodes_as_real(workflow)

        try:
            engine.registry = discover_nodes(NODES_DIR)
            results = engine.run_workflow(workflow, start_node=entry["node_name"], start_data=request_data)
        except Exception as e:
            self._send(500, {"ok": False, "error": str(e)})
            return

        webhook_resp = results.get("__webhook_response__")
        if webhook_resp:
            self._send(webhook_resp["status"], webhook_resp["body"])
        else:
            # no Respond node was reached — auto-ack
            self._send(200, {"ok": True, "note": "workflow finished, no Respond to Webhook node was hit"})


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 5800
    register_all_saved_webhooks()
    server = ThreadingHTTPServer((host, port), Handler)
    print("=" * 44)
    print("  dugs — api server")
    print("=" * 44)
    print(f"  listening on http://{host}:{port}")
    print(f"  nodes dir:   {NODES_DIR}")
    print( "  endpoints:   GET /health  GET /nodes  POST /run")
    print( "               POST /webhooks/register  GET /webhooks")
    print( "               ANY  /hook/<path>   <- real webhook hits land here")
    print( "  (ctrl-c to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped.")


if __name__ == "__main__":
    main()
