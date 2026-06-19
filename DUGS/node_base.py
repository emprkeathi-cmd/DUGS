"""
node_base.py — the contract every node follows.

A node is the smallest unit of work. The engine doesn't care what a node
does internally; it only cares that:
  - it has a TYPE (unique string id, e.g. "trigger.manual")
  - it declares how many inputs / outputs it has
  - it has a run(items, params) method: items in -> items out

DATA SHAPE (kept compatible with n8n's good idea):
  Data passed between nodes is always a list of "items".
  Each item is a dict: {"json": {...}, "binary": {...}}  (binary optional)
  A hardware node that fires once just works on a single-item list.
  A web node that returns 500 rows returns a 500-item list.
  Same shape either way -> no special-casing later.
"""

from __future__ import annotations
from typing import Any


def make_item(data: dict | None = None) -> dict:
    """Helper: wrap a plain dict into the standard item shape."""
    return {"json": data or {}}


class Node:
    # Subclasses override these.
    TYPE: str = "base"          # unique id used in workflow JSON
    TITLE: str = "Base Node"    # human label for the UI later
    CATEGORY: str = "core"      # core / trigger / action / logic / hardware
    INPUTS: int = 1             # how many input ports
    OUTPUTS: int = 1            # how many output ports

    def __init__(self, name: str, params: dict | None = None):
        # `name` is the instance name in a given workflow (e.g. "My Trigger").
        # `params` are the node's configured settings from the workflow JSON.
        self.name = name
        self.params = params or {}

    def run(self, items: list[dict]) -> list[dict] | list[list[dict]]:
        """
        Do the work.
          - `items` is the incoming list of items (may be empty for triggers).
          - return a list of items  -> goes out of output port 0
          - OR return a list-of-lists -> one list per output port
            (used by branching nodes like IF: [true_items, false_items])
        Subclasses MUST override this.
        """
        raise NotImplementedError(f"Node {self.TYPE} has no run() implemented")

    def __repr__(self):
        return f"<{self.TYPE} '{self.name}'>"
