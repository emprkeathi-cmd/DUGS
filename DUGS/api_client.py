"""
api_client.py — thin HTTP helpers the UI uses to talk to api.py.
Kept separate from storage.py (local file I/O) and ui.py (widgets).
"""
import json
import urllib.request
from theme import API


def api_get(path):
    with urllib.request.urlopen(f"{API}{path}", timeout=10) as r:
        return json.loads(r.read().decode())


def api_post(path, payload, timeout=60):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{API}{path}", data=data,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())
