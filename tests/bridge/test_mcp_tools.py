from src.bridge.store import ChannelStore
from src.bridge import mcp_tools

def test_tool_push_then_graph_receives():
    mcp_tools.comfy_push(channel="main", text="hello")
    got = ChannelStore.instance().receive("main", wait_seconds=0)
    assert got["text"] == "hello"

def test_tool_pull_reads_graph_emit():
    ChannelStore.instance().emit("main", text="from-graph")
    got = mcp_tools.comfy_pull(channel="main")
    assert got["text"] == "from-graph"

def test_tool_list_channels():
    ChannelStore.instance().emit("a", text="x")
    names = [c["name"] for c in mcp_tools.comfy_list_channels()]
    assert "a" in names
