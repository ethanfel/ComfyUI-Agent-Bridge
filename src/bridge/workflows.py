import copy
import json
import os


def workflows_dir() -> str:
    return os.environ.get("COMFY_BRIDGE_WORKFLOWS", "workflows")


def load_workflow(name: str, base_dir: str | None = None) -> dict:
    base = base_dir or workflows_dir()
    path = os.path.join(base, f"{name}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"workflow not found: {path}")
    with open(path) as fh:
        return json.load(fh)


def apply_inputs(workflow: dict, inputs: dict | None) -> dict:
    """inputs: {"<node_id>.<field>": value}. Returns a new dict (no mutation)."""
    wf = copy.deepcopy(workflow)
    for key, value in (inputs or {}).items():
        node_id, _, field = key.partition(".")
        if node_id not in wf:
            raise KeyError(f"unknown node id in inputs: {node_id}")
        wf[node_id].setdefault("inputs", {})[field] = value
    return wf


async def submit_prompt(workflow: dict, base_url: str = "http://127.0.0.1:8188",
                        session=None) -> str:
    import aiohttp
    owns = session is None
    session = session or aiohttp.ClientSession()
    try:
        async with session.post(f"{base_url}/prompt", json={"prompt": workflow}) as r:
            data = await r.json()
        return data["prompt_id"]
    finally:
        if owns:
            await session.close()


async def fetch_result(prompt_id: str, base_url: str = "http://127.0.0.1:8188",
                       session=None) -> dict:
    import aiohttp
    owns = session is None
    session = session or aiohttp.ClientSession()
    try:
        async with session.get(f"{base_url}/history/{prompt_id}") as r:
            history = await r.json()
        entry = history.get(prompt_id, {})
        images = []
        for node_out in entry.get("outputs", {}).values():
            images.extend(node_out.get("images", []))
        return {"prompt_id": prompt_id, "images": images,
                "raw": entry.get("outputs", {})}
    finally:
        if owns:
            await session.close()
