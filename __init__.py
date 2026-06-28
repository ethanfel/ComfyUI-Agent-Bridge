"""ComfyUI-Agent-Bridge: in-graph bridge nodes + MCP server for coding agents."""
try:
    # Normal path: ComfyUI loads this dir as a package, so relative imports work
    # (and nothing generic like `src` leaks onto sys.path to collide with other
    # custom nodes).
    from .src.nodes.emit import AgentEmit
    from .src.nodes.receive import AgentReceive
    from .src.bridge import mcp_server
except ImportError:
    # Fallback: imported standalone (e.g. test suite / direct import) where there
    # is no parent package — put our own dir on sys.path and import absolutely.
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from src.nodes.emit import AgentEmit
    from src.nodes.receive import AgentReceive
    from src.bridge import mcp_server

NODE_CLASS_MAPPINGS = {
    "AgentEmit": AgentEmit,
    "AgentReceive": AgentReceive,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "AgentEmit": "Agent Emit (→ agent)",
    "AgentReceive": "Agent Receive (← agent)",
}

# Start the MCP bridge when ComfyUI loads this package.
try:
    mcp_server.start_in_background()
except Exception as exc:  # never block ComfyUI startup
    print(f"[comfyui-nodes-agents] MCP bridge failed to start: {exc}")

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
