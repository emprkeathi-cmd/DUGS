"""
dugs engine.py — discovers nodes, loads workflow JSON, walks the graph.

Workflow JSON shape:
{
  "name": "my workflow",
  "nodes": [
    {"name": "Start", "type": "trigger.manual", "params": {"data": {"x": 1}}},
    {"name": "Add", "type": "core.set", "params": {"mode": "keep", "assignments": [{"name": "y", "value": 2}]}},
    {"name": "Show", "type": "core.log", "params": {"label": "OUT"}}
  ],
  "connections": {
    "Start": [{"to": "Add", "out": 0, "in": 0}],
    "Add":   [{"to": "Show", "out": 0, "in": 0}]
  }
}
"""

from __future__ import annotations
import os
import sys
import json
import importlib.util
import inspect
from node_base import Node


def discover_nodes(nodes_dir: str) -> dict[str, type[Node]]:
    registry: dict[str, type[Node]] = {}
    if not os.path.isdir(nodes_dir):
        return registry
    for fname in os.listdir(nodes_dir):
        if not fname.endswith(".py") or fname.startswith("_"):
            continue
        path = os.path.join(nodes_dir, fname)
        try:
            spec = importlib.util.spec_from_file_location(fname[:-3], path)
            module = importlib.util.module_from_spec(spec)
            # make sure node_base is importable from the nodes dir
            sys.path.insert(0, nodes_dir)
            sys.path.insert(0, os.path.dirname(nodes_dir))
            sys.modules[spec.name] = module  # so getattr(sys.modules[...], ...) lookups work later
            spec.loader.exec_module(module)
            for _, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, Node) and obj is not Node and hasattr(obj, "TYPE"):
                    registry[obj.TYPE] = obj
        except Exception as e:
            print(f"  [warn] could not load {fname}: {e}")
    return registry


class Engine:
    def __init__(self, nodes_dir: str):
        self.nodes_dir = nodes_dir
        self.registry = discover_nodes(nodes_dir)

    def run_workflow(self, workflow: dict, start_node: str | None = None,
                      start_data: dict | None = None) -> dict:
        """
        start_node / start_data: used by the webhook handler in api.py to kick
        off execution at a specific trigger node with real request data,
        instead of running every start node with empty input.
        """
        nodes_spec = workflow.get("nodes", [])
        connections = workflow.get("connections", {})

        # build instances
        instances: dict[str, Node] = {}
        for n in nodes_spec:
            cls = self.registry.get(n["type"])
            if cls is None:
                raise ValueError(f"Unknown node type: '{n['type']}' — is the node file in nodes/?")
            instances[n["name"]] = cls(n["name"], dict(n.get("params", {})))

        # find start nodes (no incoming connections OR INPUTS==0)
        has_incoming = set()
        for src, links in connections.items():
            for link in links:
                has_incoming.add(link["to"])

        if start_node:
            queue: list[tuple[str, list]] = [(start_node, [{"json": start_data or {}}])]
            start_nodes = [start_node]
        else:
            start_nodes = [
                name for name, inst in instances.items()
                if inst.INPUTS == 0 or name not in has_incoming
            ]
            queue = [(name, []) for name in start_nodes]

        results: dict[str, list] = {}

        print(f"\n=== running: {workflow.get('name', '(unnamed)')} ===")
        print(f"starting from: {start_nodes}\n")

        # Grab the exact WebhookRespondSignal class object from the already
        # dynamically-loaded webhook.respond node module (NOT a fresh package
        # import — that would create a second, different class object and
        # break isinstance checks below).
        WebhookRespondSignal = None
        respond_cls = self.registry.get("webhook.respond")
        if respond_cls is not None:
            WebhookRespondSignal = getattr(sys.modules.get(respond_cls.__module__), "WebhookRespondSignal", None)

        visited = set()
        while queue:
            name, incoming = queue.pop(0)
            if name in visited:
                continue
            visited.add(name)

            node = instances[name]
            print(f"--> {node.TYPE} '{name}'  ({len(incoming)} items in)")
            try:
                output = node.run(incoming)
            except Exception as e:
                if WebhookRespondSignal is not None and isinstance(e, WebhookRespondSignal):
                    print(f"    [respond] status={e.status}")
                    results[name] = [[{"json": e.body}]]
                    print("\n=== done (responded) ===")
                    return {"__webhook_response__": {"status": e.status, "body": e.body}, **results}
                print(f"    [ERROR] {e}")
                output = [{"json": {"error": str(e), "node": name}}]

            # normalise: single port vs multiple ports
            if output and isinstance(output[0], list):
                ports = output
            else:
                ports = [output]
            results[name] = ports

            # push to connected nodes
            for link in connections.get(name, []):
                out_port = link.get("out", 0)
                target = link["to"]
                items_for_target = ports[out_port] if out_port < len(ports) else []
                print(f"    -> '{target}' ({len(items_for_target)} items)")
                queue.append((target, items_for_target))

        print("\n=== done ===")
        return results


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    nodes_dir = os.path.join(here, "nodes")
    engine = Engine(nodes_dir)

    print("=" * 44)
    print("  dugs — engine")
    print("=" * 44)
    print("discovered nodes:")
    for t, c in sorted(engine.registry.items()):
        print(f"  {t:22s}  {c.TITLE}  [{c.CATEGORY}]")

    wf_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "demo_workflow.json")
    print(f"\nrunning: {wf_path}\n")
    with open(wf_path) as f:
        workflow = json.load(f)
    engine.run_workflow(workflow)
