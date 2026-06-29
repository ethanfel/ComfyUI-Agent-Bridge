#!/usr/bin/env python3
"""Manual test client: push a message to a bridge channel.

Usage:
    python examples/push.py <channel> <text> [--image PATH] [--seed N] [--url URL]

Examples:
    python examples/push.py sxcp_eval_out "a red fox in autumn leaves"
    python examples/push.py sxcp_eval_out "result" --image /path/out.png --seed 123
    COMFY_BRIDGE_URL=http://192.168.1.12:9188/mcp python examples/push.py main "hi"

Needs:  pip install "mcp>=1.2.0"
Default URL: $COMFY_BRIDGE_URL or http://127.0.0.1:9188/mcp
(This is only a manual tester — a real agent calls comfy_push as a native tool.)
"""
import argparse
import asyncio
import os

from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession


async def push(url, channel, text, image, seed):
    args = {"channel": channel}
    if text is not None:
        args["text"] = text
    if image is not None:
        args["image_path"] = image
    if seed is not None:
        args["seed"] = seed
    async with streamablehttp_client(url) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            res = await s.call_tool("comfy_push", args)
            print(res.content[0].text if res.content else "(no content)")


def main():
    p = argparse.ArgumentParser(description="Push a message to a ComfyUI bridge channel.")
    p.add_argument("channel")
    p.add_argument("text", nargs="?", default=None)
    p.add_argument("--image", default=None, help="image path (must be openable by ComfyUI)")
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--url", default=os.environ.get("COMFY_BRIDGE_URL",
                                                   "http://127.0.0.1:9188/mcp"))
    a = p.parse_args()
    asyncio.run(push(a.url, a.channel, a.text, a.image, a.seed))


if __name__ == "__main__":
    main()
