"""Real end-to-end MCP round-trip: boot the streamable-HTTP server on an
ephemeral port in a daemon thread, connect a real MCP client, list the tools,
and call them — proving an external agent (Claude Code / Codex) can drive the
in-process ChannelStore. Skips gracefully if the port can't be bound."""
import asyncio
import json
import socket
import threading
import time

import pytest

from src.bridge import mcp_server
from src.bridge.store import ChannelStore


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_port(host: str, port: int, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def _payload(result):
    """Tool returning a dict -> a single JSON TextContent."""
    assert result.isError is False
    return json.loads(result.content[0].text)


def _payload_list(result):
    """Tool returning a list -> FastMCP emits one JSON TextContent per item."""
    assert result.isError is False
    return [json.loads(c.text) for c in result.content]


async def _roundtrip():
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    host, port = "127.0.0.1", _free_port()
    mcp = mcp_server.build_server(host=host, port=port)
    threading.Thread(
        target=lambda: mcp.run(transport="streamable-http"),
        name="comfy-bridge-mcp-test", daemon=True,
    ).start()
    if not _wait_port(host, port):
        pytest.skip("MCP server port could not be bound")

    url = f"http://{host}:{port}/mcp"
    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
            assert {
                "comfy_pull", "comfy_push", "comfy_list_channels",
                "comfy_run_workflow", "comfy_get_result",
            } <= names

            # agent -> graph: push via the tool, read via the store
            pushed = _payload(await session.call_tool(
                "comfy_push", {"channel": "rt", "text": "hi-from-agent"}))
            assert pushed["channel"] == "rt" and pushed["out_turn"] == 1
            assert pushed["warnings"] == []  # valid push -> no sender warnings
            got = ChannelStore.instance().receive("rt", wait_seconds=0)
            assert got["text"] == "hi-from-agent"

            # graph -> agent: emit via the store, pull via the tool
            ChannelStore.instance().emit("rt", text="from-graph")
            pulled = _payload(await session.call_tool(
                "comfy_pull", {"channel": "rt"}))
            assert pulled["text"] == "from-graph"

            listed = _payload_list(await session.call_tool(
                "comfy_list_channels", {}))
            assert any(c["name"] == "rt" for c in listed)


def test_mcp_roundtrip():
    asyncio.run(asyncio.wait_for(_roundtrip(), timeout=30))
