"""SDK-independent MCP tool logic. Bound to FastMCP in mcp_server.py."""
import os
from src.bridge.store import ChannelStore
from src.bridge import workflows, paths

COMFY_BASE_URL = os.environ.get("COMFY_BASE_URL", "http://127.0.0.1:8188")


def comfy_pull(channel: str = "main") -> dict:
    """Read the latest text/image the graph emitted on a channel."""
    result = ChannelStore.instance().pull(channel)
    # advertise the path the agent can open (for remote/Docker shared folders)
    result["image_path"] = paths.to_public(result["image_path"])
    return result


def comfy_push(channel: str = "main", text: str | None = None,
               image_path: str | None = None) -> dict:
    """Send text/image to the graph's Agent Receive node on a channel."""
    # translate the agent-visible path back to the bridge's container-side path
    image_path = paths.to_local(image_path)
    turn = ChannelStore.instance().push(channel, text=text, image_path=image_path)
    return {"channel": channel, "out_turn": turn}


def comfy_list_channels() -> list:
    """List active channels and their turn counters."""
    return ChannelStore.instance().list_channels()


async def comfy_run_workflow(name: str, inputs: dict | None = None,
                             wait: bool = True) -> dict:
    """Load a saved workflow, optionally inject inputs, queue it, optionally wait."""
    wf = workflows.apply_inputs(workflows.load_workflow(name), inputs)
    prompt_id = await workflows.submit_prompt(wf, base_url=COMFY_BASE_URL)
    if not wait:
        return {"prompt_id": prompt_id, "status": "queued"}
    # poll history until outputs appear (bounded)
    import asyncio
    for _ in range(600):  # ~60s at 0.1s
        res = await workflows.fetch_result(prompt_id, base_url=COMFY_BASE_URL)
        # Best-effort: returns as soon as any output node appears in /history.
        # The design's upgrade path is the ComfyUI websocket `executed` event
        # for precise completion signalling instead of polling.
        if res["images"] or res["raw"]:
            return {"prompt_id": prompt_id, "status": "done", **res}
        await asyncio.sleep(0.1)
    return {"prompt_id": prompt_id, "status": "timeout"}


async def comfy_get_result(prompt_id: str) -> dict:
    """Fetch produced images/outputs for a prompt id."""
    return await workflows.fetch_result(prompt_id, base_url=COMFY_BASE_URL)
