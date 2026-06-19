"""
Code node: run a small piece of Python to transform the items.
The escape hatch — when no existing node does what you want, write a few lines.

params:
  code : a Python snippet. It has access to:
           items  -> the incoming list of items (list of {"json": {...}})
         and must set:
           result -> the outgoing list of items
         If `result` isn't set, items are passed through unchanged.

Example code param:
  "for it in items: it['json']['doubled'] = it['json'].get('n',0) * 2\nresult = items"

NOTE: this runs Python with no sandbox. Only run code you wrote/trust.
For a hosted/multi-user setup later, this needs real sandboxing.
"""
from node_base import Node


class CodeNode(Node):
    TYPE = "core.code"
    TITLE = "Code"
    CATEGORY = "core"
    INPUTS = 1
    OUTPUTS = 1
    PARAMS = [
        {"key": "code", "label": "Python code", "type": "multiline", "default": "result = items"},
    ]

    def run(self, items):
        code = self.params.get("code", "")
        if not code.strip():
            return items
        scope = {"items": items, "result": None}
        exec(code, {}, scope)  # noqa: S102 (intentional — user code escape hatch)
        result = scope.get("result")
        if result is None:
            return items
        # be forgiving: if user returned bare dicts, wrap them
        normalised = []
        for r in result:
            if isinstance(r, dict) and "json" in r:
                normalised.append(r)
            elif isinstance(r, dict):
                normalised.append({"json": r})
        return normalised
