from node_base import Node


class CodeNode(Node):
    TYPE = "core.code"
    TITLE = "Code"
    CATEGORY = "core"
    INPUTS = 1
    OUTPUTS = 1

    def run(self, items):
        code = self.params.get("code", "")
        if not code.strip():
            return items
        scope = {"items": items, "result": None}
        exec(code, {}, scope)
        result = scope.get("result")
        if result is None:
            return items
        normalised = []
        for r in result:
            if isinstance(r, dict) and "json" in r:
                normalised.append(r)
            elif isinstance(r, dict):
                normalised.append({"json": r})
        return normalised
