"""
dugs — a clean, modular node engine (engine.py is the core). Three jobs:
  1. DISCOVER: scan nodes/ folder, register every Node subclass by its TYPE.
  2. LOAD: read a workflow JSON (nodes + connections).
  3. RUN: walk the graph in connection order, passing item-lists between nodes.

Workflow JSON shape (our own, clean version):
{
  "name": "demo",
  "nodes": [
    {"name": "Start", "type": "trigger.manual", "params": {"data": {"x": 1}}},
    {"name": "Add Field", "type": "core.set", "params": {"fields": {"y": 2}}},
    {"name": "Show", "type": "core.log", "params": {"label": "OUT"}}
  ],
  "connections": {
    "Start":     [{"to": "Add Field", "out": 0, "in": 0}],
    "Add Field": [{"to": "Show",      "out": 0, "in": 0}]
  }
}

connections: key = source node name, value = list of links from it.
  each link: to=target node name, out=which output port, in=which input port.
"""

from __future__ import annotations
import os
import sys
import json
import importlib.util
import inspect
from node_base import Node


# ---------------------------------------------------------------------------
# 1. DISCOVERY — find every node file in nodes/ and register it by TYPE.
# ---------------------------------------------------------------------------
def discover_nodes(nodes_dir: str) -> dict[str, type[Node]]:
    registry: dict[str, type[Node]] = {}
    for fname in os.listdir(nodes_dir):
        if not fname.endswith(".py") or fname.startswith("_"):
            continue
        path = os.path.join(nodes_dir, fname)
        spec = importlib.util.spec_from_file_location(fname[:-3], path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        # find Node subclasses defined in this file
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, Node) and obj is not Node:
                registry[obj.TYPE] = obj
    return registry


# ---------------------------------------------------------------------------
# 2 + 3. THE ENGINE
# ---------------------------------------------------------------------------
class Engine:
    def __init__(self, nodes_dir: str):
        self.registry = discover_nodes(nodes_dir)

    def run_workflow(self, workflow: dict) -> dict:
        nodes_spec = workflow["nodes"]
        connections = workflow.get("connections", {})

        # build instances by name
        instances: dict[str, Node] = {}
        for n in nodes_spec:
            cls = self.registry.get(n["type"])
            if cls is None:
                raise ValueError(f"Unknown node type: {n['type']}")
            instances[n["name"]] = cls(n["name"], n.get("params", {}))

        # figure out which nodes are triggers (no incoming connections / 0 inputs)
        has_incoming = set()
        for src, links in connections.items():
            for link in links:
                has_incoming.add(link["to"])
        start_nodes = [
            name for name, inst in instances.items()
            if inst.INPUTS == 0 or name not in has_incoming
        ]

        # execution: a simple queue. (topological walk via connections)
        # each entry: (node_name, incoming_items)
        results: dict[str, list] = {}
        queue: list[tuple[str, list]] = [(name, []) for name in start_nodes]

        print(f"\n=== running workflow: {workflow.get('name','(unnamed)')} ===")
        print(f"start nodes: {start_nodes}\n")

        while queue:
            name, incoming = queue.pop(0)
            node = instances[name]
            print(f"--> running {node.TYPE} '{name}'")
            output = node.run(incoming)

            # normalise: a node may return one list (port 0) or list-of-lists
            if output and isinstance(output[0], list):
                ports = output            # already per-port
            else:
                ports = [output]          # single port 0
            results[name] = ports

            # push to connected nodes
            for link in connections.get(name, []):
                out_port = link.get("out", 0)
                target = link["to"]
                items_for_target = ports[out_port] if out_port < len(ports) else []
                queue.append((target, items_for_target))

        print("\n=== done ===")
        return results


# ---------------------------------------------------------------------------
# CLI: python engine.py <workflow.json>
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    nodes_dir = os.path.join(here, "nodes")
    engine = Engine(nodes_dir)

    print("=" * 44)
    print("  dugs — node engine")
    print("=" * 44)
    print("discovered node types:")
    for t, c in sorted(engine.registry.items()):
        print(f"  {t:18s} -> {c.TITLE}  [{c.CATEGORY}]")

    wf_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "demo_workflow.json")
    with open(wf_path) as f:
        workflow = json.load(f)

    engine.run_workflow(workflow)
