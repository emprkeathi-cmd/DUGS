"""
A trigger node: starts the workflow and provides the first item(s).
Drop-in node file — the engine auto-discovers it.
"""
from node_base import Node, make_item


class ManualTrigger(Node):
    TYPE = "trigger.manual"
    TITLE = "Manual Trigger"
    CATEGORY = "trigger"
    INPUTS = 0          # triggers take no input
    OUTPUTS = 1

    def run(self, items):
        # A trigger ignores incoming items (there are none) and emits a
        # starting item. Any params set on the node become the initial json.
        start_data = self.params.get("data", {"started": True})
        return [make_item(start_data)]
