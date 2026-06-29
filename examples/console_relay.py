#!/usr/bin/env python3
"""Relay bridge-channel messages into a tmux pane (a 'designated console').

Run this ON THE MACHINE where the target tmux session lives. It polls a bridge
channel (whatever an `Agent Emit` node writes) and types each NEW message into
the given tmux pane with `tmux send-keys`, optionally pressing Enter to submit.

ComfyUI (Agent Emit, channel="console")  ->  bridge  ->  THIS relay  ->  tmux pane

Usage:
    python examples/console_relay.py --target claude:0.0 --channel console \
        --url http://192.168.1.12:9188/mcp

Find a target id:
    tmux list-panes -a -F '#{session_name}:#{window_index}.#{pane_index}  #{pane_id}'

Options:
    --target       tmux pane, e.g. 'claude:0.0' or '%3'           (required)
    --channel      bridge channel to read                         (default: console)
    --url          bridge MCP URL ($COMFY_BRIDGE_URL)             (default: 127.0.0.1:9188/mcp)
    --poll         seconds between polls                          (default: 1.0)
    --no-submit    type the text but don't press Enter
    --tmux-socket  tmux -S socket path (if non-default)

Needs:  pip install "mcp>=1.2.0"   and  tmux on PATH.
Only injects when the channel's `turn` advances, so a message is typed once.
"""
import argparse
import asyncio
import os
import subprocess

from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession


def tmux_send(target, text, submit, socket):
    base = ["tmux"]
    if socket:
        base += ["-S", socket]
    # -l => literal, so words like "Enter" in the text aren't taken as keys
    subprocess.run(base + ["send-keys", "-t", target, "-l", "--", text], check=True)
    if submit:
        subprocess.run(base + ["send-keys", "-t", target, "Enter"], check=True)


async def run(url, channel, target, poll, submit, socket):
    print(f"[relay] {url} channel={channel!r} -> tmux {target!r} "
          f"(submit={submit}, poll={poll}s)")
    last_turn = 0
    async with streamablehttp_client(url) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            while True:
                import json
                res = await s.call_tool("comfy_pull", {"channel": channel})
                msg = json.loads(res.content[0].text) if res.content else {}
                turn, text = msg.get("turn", 0), msg.get("text")
                if turn > last_turn and text:
                    last_turn = turn
                    print(f"[relay] turn={turn} -> {text[:80]!r}")
                    try:
                        tmux_send(target, text, submit, socket)
                    except subprocess.CalledProcessError as e:
                        print(f"[relay] tmux error: {e}")
                await asyncio.sleep(poll)


def main():
    p = argparse.ArgumentParser(description="Relay a bridge channel into a tmux pane.")
    p.add_argument("--target", required=True)
    p.add_argument("--channel", default="console")
    p.add_argument("--url", default=os.environ.get("COMFY_BRIDGE_URL",
                                                   "http://127.0.0.1:9188/mcp"))
    p.add_argument("--poll", type=float, default=1.0)
    p.add_argument("--no-submit", dest="submit", action="store_false")
    p.add_argument("--tmux-socket", default=None)
    a = p.parse_args()
    try:
        asyncio.run(run(a.url, a.channel, a.target, a.poll, a.submit, a.tmux_socket))
    except KeyboardInterrupt:
        print("\n[relay] stopped")


if __name__ == "__main__":
    main()
