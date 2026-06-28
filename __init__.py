"""ComfyUI-Agent-Bridge: in-graph bridge nodes + MCP server for coding agents."""
import os
import sys

# Import our internal package whether ComfyUI loads us as a package (relative
# imports work) or we're imported standalone (tests). Using __package__ as the
# signal — instead of a broad try/except — avoids masking real errors (e.g. a
# missing dependency) as an import-context problem. The node modules need only
# torch/numpy/Pillow (always present in ComfyUI), not `mcp`.
if __package__:
    from .src.nodes.emit import AgentEmit
    from .src.nodes.receive import AgentReceive
else:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from src.nodes.emit import AgentEmit
    from src.nodes.receive import AgentReceive

NODE_CLASS_MAPPINGS = {
    "AgentEmit": AgentEmit,
    "AgentReceive": AgentReceive,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "AgentEmit": "Agent Emit (→ agent)",
    "AgentReceive": "Agent Receive (← agent)",
}

# The MCP bridge is optional: it needs the `mcp` package. If that isn't installed
# in ComfyUI's Python, keep the nodes working and tell the user how to enable it.
try:
    if __package__:
        from .src.bridge import mcp_server
    else:
        from src.bridge import mcp_server
    mcp_server.start_in_background()
except ModuleNotFoundError as exc:
    if (exc.name or "").split(".")[0] == "mcp":
        print("[comfyui-agent-bridge] MCP bridge disabled: 'mcp' is not installed "
              "in ComfyUI's Python. The Agent Emit/Receive nodes still load; "
              "enable the bridge with:\n"
              f"    {sys.executable} -m pip install 'mcp>=1.2.0'")
    else:
        print(f"[comfyui-agent-bridge] MCP bridge failed to start: {exc}")
except Exception as exc:  # never block ComfyUI startup
    print(f"[comfyui-agent-bridge] MCP bridge failed to start: {exc}")

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
