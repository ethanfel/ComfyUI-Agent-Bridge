"""SDK-independent MCP tool logic. Bound to FastMCP in mcp_server.py."""
import os
from .store import ChannelStore
from . import workflows, paths
from .logutil import log, short

COMFY_BASE_URL = os.environ.get("COMFY_BASE_URL", "http://127.0.0.1:8188")


def comfy_pull(channel: str = "main") -> dict:
    """Read the latest text/image the graph emitted on a channel."""
    result = ChannelStore.instance().pull(channel)
    # advertise the path the agent can open (for remote/Docker shared folders)
    result["image_path"] = paths.to_public(result["image_path"])
    got = "empty" if result["turn"] == 0 else (
        f"turn={result['turn']} text={short(result['text'])!r} "
        f"image={result['image_path']!r} seed={result['seed']}")
    log(f"comfy_pull(channel={channel!r}) -> {got}")
    return result


def _validate_push(channel, text, image_path, seed):
    """Warn when the sender (agent) passes something the graph can't use."""
    warnings = []
    if not channel or not isinstance(channel, str):
        warnings.append(f"channel should be a non-empty string, got {channel!r}")
    if image_path is not None:
        if not isinstance(image_path, str):
            warnings.append(f"image_path must be a path string, got "
                            f"{type(image_path).__name__}")
        elif not os.path.exists(image_path):
            warnings.append(
                f"image_path does not exist on the ComfyUI host: {image_path!r} "
                "— the sender pushed a path this machine can't open (check the "
                "shared folder / COMFY_BRIDGE_TMP_PUBLIC mapping). Agent Receive "
                "will fall back to a blank image.")
    if seed is not None and not isinstance(seed, int):
        warnings.append(f"seed must be an int, got {type(seed).__name__}={seed!r}")
    if text is None and image_path is None and seed is None:
        warnings.append("push has no text, image_path, or seed (empty message)")
    return warnings


def comfy_push(channel: str = "main", text: str | None = None,
               image_path: str | None = None, seed: int | None = None) -> dict:
    """Send text/image/seed to the graph's Agent Receive node on a channel."""
    # translate the agent-visible path back to the bridge's container-side path
    local_path = paths.to_local(image_path)
    warnings = _validate_push(channel, text, local_path, seed)
    turn = ChannelStore.instance().push(channel, text=text,
                                        image_path=local_path, seed=seed)
    log(f"comfy_push(channel={channel!r}, text={short(text)!r}, "
        f"image={image_path!r}"
        + (f" -> {local_path!r}" if local_path != image_path else "")
        + f", seed={seed!r}) -> out_turn={turn}")
    for w in warnings:
        log(f"  ⚠ SENDER PROBLEM: {w}")
    return {"channel": channel, "out_turn": turn, "warnings": warnings}


def comfy_list_channels() -> list:
    """List active channels and their turn counters."""
    channels = ChannelStore.instance().list_channels()
    log(f"comfy_list_channels() -> {len(channels)} channel(s)")
    return channels


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
