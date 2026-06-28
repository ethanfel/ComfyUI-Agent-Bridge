"""ComfyUI-Nodes-Agents: in-graph bridge nodes + MCP server for coding agents."""
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
