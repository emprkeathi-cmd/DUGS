import json
import urllib.request
import urllib.error
from node_base import Node


class HttpRequestNode(Node):
    TYPE = "web.http"
    TITLE = "HTTP Request"
    CATEGORY = "action"
    INPUTS = 1
    OUTPUTS = 1

    def run(self, items):
        url = self.params.get("url")
        if not url:
            raise ValueError("HTTP Request node needs a 'url' param")
        method = self.params.get("method", "GET").upper()
        headers = dict(self.params.get("headers", {}))
        body = self.params.get("body")
        timeout = self.params.get("timeout", 15)

        data_bytes = None
        if body is not None:
            data_bytes = json.dumps(body).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")

        run_for = items if items else [{"json": {}}]
        out = []
        for _ in run_for:
            req = urllib.request.Request(url, data=data_bytes, method=method, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
                    status = resp.status
                    resp_headers = dict(resp.headers.items())
            except urllib.error.HTTPError as e:
                raw = e.read().decode("utf-8", errors="replace")
                status = e.code
                resp_headers = dict(e.headers.items()) if e.headers else {}
            except Exception as e:
                out.append({"json": {"error": str(e), "url": url}})
                continue
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = raw
            out.append({"json": {"status": status, "body": parsed, "headers": resp_headers}})
        return out
