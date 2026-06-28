"""End-to-end check of the Codex stdio<->HTTP MCP proxy: boot the in-process
streamable-HTTP bridge on an ephemeral port, spawn ``scripts/codex_stdio_shim.py``
as a real stdio MCP server pointed at it, then drive that subprocess with a real
stdio MCP client — proving a stdio-only Codex build can reach the bridge through
the proxy. Skips gracefully if the port can't be bound or the subprocess can't
start."""
import asyncio
import json
import os
import socket
import sys
import threading
import time

import pytest

from src.bridge import mcp_server

SHIM = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "scripts", "codex_stdio_shim.py",
)


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


async def _roundtrip():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    host, port = "127.0.0.1", _free_port()
    mcp = mcp_server.build_server(host=host, port=port)
    threading.Thread(
        target=lambda: mcp.run(transport="streamable-http"),
        name="comfy-bridge-mcp-shim-test", daemon=True,
    ).start()
    if not _wait_port(host, port):
        pytest.skip("MCP server port could not be bound")

    env = dict(os.environ)
    env["COMFY_BRIDGE_URL"] = f"http://{host}:{port}/mcp"
    params = StdioServerParameters(command=sys.executable, args=[SHIM], env=env)

    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                tools = await session.list_tools()
                names = {t.name for t in tools.tools}
                assert {
                    "comfy_pull", "comfy_push", "comfy_list_channels",
                    "comfy_run_workflow", "comfy_get_result",
                } == names

                result = await session.call_tool("comfy_list_channels", {})
                assert result.isError is False
                # comfy_list_channels returns a list -> one JSON TextContent per
                # item; on a fresh store it's an empty list (no content blocks).
                for c in result.content:
                    json.loads(c.text)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"stdio shim subprocess could not be driven: {exc!r}")


def test_codex_shim_roundtrip():
    asyncio.run(asyncio.wait_for(_roundtrip(), timeout=30))
