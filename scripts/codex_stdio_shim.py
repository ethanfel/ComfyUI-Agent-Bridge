#!/usr/bin/env python3
"""Stdio MCP shim -> the in-process HTTP bridge.

Intent
------
The ComfyUI Agent Bridge serves MCP over **streamable HTTP** at
``http://127.0.0.1:9188/mcp``. Claude Code (and modern Codex builds) connect to
that URL directly -- this script is **not needed** for them:

    claude mcp add --transport http comfy http://127.0.0.1:9188/mcp

This shim exists only for the conditional case of a Codex build that *only*
speaks stdio MCP. The idea is to spawn this process from the agent, read stdio
JSON-RPC frames, forward them to the HTTP bridge, and stream responses back --
i.e. a stdio<->streamable-HTTP MCP proxy.

Status
------
The installed MCP Python SDK (mcp 1.28.1) does **not** ship a ready-made proxy
helper (there is no ``mcp.shared.proxy.create_proxy_server``). A correct,
robust proxy that pumps a bidirectional streamable-HTTP session into a stdio
server is more than a trivial amount of plumbing, so it is intentionally left
unimplemented here rather than shipped half-working.

Prefer HTTP MCP (see the command above). If you genuinely need a stdio bridge
for an HTTP-incapable Codex build, implement the pump using
``mcp.client.streamable_http.streamablehttp_client`` (client side) and
``mcp.server.stdio.stdio_server`` (server side), wiring an MCP ``ClientSession``
to a ``Server`` that re-exposes the upstream tools. See README.md.

Running this script prints this guidance and exits non-zero.
"""
import os
import sys

URL = os.environ.get("COMFY_BRIDGE_URL", "http://127.0.0.1:9188/mcp")


def main() -> int:
    sys.stderr.write(
        "comfyui-nodes-agents: HTTP MCP is the recommended transport.\n"
        f"This stdio shim targets {URL} but is NOT implemented for your\n"
        "installed MCP SDK (mcp 1.28.1 has no ready-made proxy helper).\n"
        "\n"
        "Use HTTP MCP directly instead:\n"
        f"  claude mcp add --transport http comfy {URL}\n"
        "or point your Codex config at the same URL. See README.md.\n"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
