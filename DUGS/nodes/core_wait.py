import time
from node_base import Node


class WaitNode(Node):
    TYPE = "core.wait"
    TITLE = "Wait"
    CATEGORY = "core"
    INPUTS = 1
    OUTPUTS = 1

    def run(self, items):
        time.sleep(float(self.params.get("seconds", 1)))
        return items
