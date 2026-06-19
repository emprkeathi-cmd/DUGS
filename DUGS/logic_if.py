"""
IF node: splits items into two outputs based on a condition.
  output 0 = items where condition is TRUE
  output 1 = items where condition is FALSE

Demonstrates a node with multiple output ports — and note: the engine
needed ZERO changes to support this. Pure drop-in.

params:
  field    : which json field to test
  operator : "equals" | "greater" | "exists"
  value    : value to compare against
"""
from node_base import Node


class IfNode(Node):
    TYPE = "logic.if"
    TITLE = "IF"
    CATEGORY = "logic"
    INPUTS = 1
    OUTPUTS = 2   # [true, false]
    PARAMS = [
        {"key": "field", "label": "Field", "type": "text", "default": ""},
        {"key": "operator", "label": "Operator (equals/greater/exists)", "type": "text", "default": "exists"},
        {"key": "value", "label": "Value", "type": "text", "default": ""},
    ]

    def run(self, items):
        field = self.params.get("field")
        op = self.params.get("operator", "exists")
        value = self.params.get("value")

        true_items, false_items = [], []
        for item in items:
            j = item.get("json", {})
            actual = j.get(field)
            if op == "equals":
                passed = actual == value
            elif op == "greater":
                passed = (actual is not None) and (actual > value)
            elif op == "exists":
                passed = field in j
            else:
                passed = False
            (true_items if passed else false_items).append(item)

        return [true_items, false_items]   # one list per output port
