import copy
import json
import os
from typing import Optional


def workflows_dir() -> str:
    return os.environ.get("COMFY_BRIDGE_WORKFLOWS", "workflows")


def load_workflow(name: str, base_dir: Optional[str] = None) -> dict:
    base = base_dir or workflows_dir()
    path = os.path.join(base, f"{name}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"workflow not found: {path}")
    with open(path) as fh:
        return json.load(fh)


def apply_inputs(workflow: dict, inputs: Optional[dict]) -> dict:
    """inputs: {"<node_id>.<field>": value}. Returns a new dict (no mutation)."""
    wf = copy.deepcopy(workflow)
    for key, value in (inputs or {}).items():
        node_id, _, field = key.partition(".")
        if node_id not in wf:
            raise KeyError(f"unknown node id in inputs: {node_id}")
        wf[node_id].setdefault("inputs", {})[field] = value
    return wf
