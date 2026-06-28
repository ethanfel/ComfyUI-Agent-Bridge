"""FastMCP server wiring + background lifecycle for the ComfyUI agent bridge."""
import os
import threading

from mcp.server.fastmcp import FastMCP

from src.bridge import mcp_tools

_started = False
_lock = threading.Lock()


def build_server(host: str = "127.0.0.1", port: int = 9188) -> FastMCP:
    mcp = FastMCP("comfy-bridge", host=host, port=port)
    mcp.tool()(mcp_tools.comfy_pull)
    mcp.tool()(mcp_tools.comfy_push)
    mcp.tool()(mcp_tools.comfy_list_channels)
    mcp.tool()(mcp_tools.comfy_run_workflow)
    mcp.tool()(mcp_tools.comfy_get_result)
    return mcp


def registered_tool_names(mcp: FastMCP) -> list:
    # FastMCP exposes a tool manager; fall back across SDK versions.
    mgr = getattr(mcp, "_tool_manager", None)
    if mgr is not None and hasattr(mgr, "_tools"):
        return list(mgr._tools.keys())
    return [t.name for t in getattr(mcp, "list_tools", lambda: [])()]


def start_in_background(host: str = "127.0.0.1", port: int = None,
                        _test_no_serve: bool = False) -> None:
    global _started
    with _lock:
        if _started:
            return
        _started = True
    port = port if port is not None else int(
        os.environ.get("COMFY_BRIDGE_MCP_PORT", "9188"))
    mcp = build_server(host=host, port=port)
    if _test_no_serve:
        return

    def _serve():
        mcp.run(transport="streamable-http")

    threading.Thread(target=_serve, name="comfy-bridge-mcp",
                     daemon=True).start()
    print(f"[comfyui-nodes-agents] MCP bridge on "
          f"http://{host}:{port}/mcp  (claude mcp add --transport http "
          f"comfy http://{host}:{port}/mcp)")
