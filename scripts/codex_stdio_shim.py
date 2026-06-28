#!/usr/bin/env python3
"""Stdio<->HTTP MCP proxy so a stdio-only Codex build can reach the bridge.

The ComfyUI Agent Bridge serves MCP over **streamable HTTP** at
``http://127.0.0.1:9188/mcp`` (override with ``COMFY_BRIDGE_URL``). Claude Code
and HTTP-capable Codex builds connect to that URL directly and do **not** need
this script. It exists only for a Codex build that can *only* speak stdio MCP.

A Codex-spawned process is separate from ComfyUI, so this proxy connects
upstream as an HTTP MCP **client** to the in-process bridge, then runs a stdio
MCP **server** toward Codex whose ``list_tools`` / ``call_tool`` handlers simply
forward to the upstream session. On connection failure it exits non-zero with a
helpful stderr message so Codex surfaces a clear error.
"""
import os
import sys

import anyio
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

URL = os.environ.get("COMFY_BRIDGE_URL", "http://127.0.0.1:9188/mcp")


async def _run() -> None:
    async with streamablehttp_client(URL) as (read, write, _):
        async with ClientSession(read, write) as upstream:
            await upstream.initialize()

            server = Server("comfy-bridge-stdio-proxy")

            @server.list_tools()
            async def _list_tools():
                return (await upstream.list_tools()).tools

            @server.call_tool()
            async def _call_tool(name, arguments):
                # Forward verbatim; return the upstream CallToolResult as-is.
                return await upstream.call_tool(name, arguments or {})

            async with stdio_server() as (stdin, stdout):
                await server.run(
                    stdin, stdout, server.create_initialization_options()
                )


def main() -> int:
    try:
        anyio.run(_run)
    except Exception as exc:  # noqa: BLE001 -- surface a clear startup error
        sys.stderr.write(
            f"comfyui-nodes-agents: stdio proxy could not reach the HTTP MCP "
            f"bridge at {URL}\n  {type(exc).__name__}: {exc}\n"
            "Is ComfyUI running with the bridge started? Set COMFY_BRIDGE_URL "
            "if it listens elsewhere.\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
