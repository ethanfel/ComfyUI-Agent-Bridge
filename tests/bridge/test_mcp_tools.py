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

def test_push_warns_on_missing_image_path():
    res = mcp_tools.comfy_push(channel="w", image_path="/no/such/file.png")
    assert any("does not exist" in w for w in res["warnings"])

def test_push_warns_on_empty_message():
    res = mcp_tools.comfy_push(channel="w")
    assert any("empty message" in w for w in res["warnings"])

def test_push_no_warnings_for_valid_text():
    res = mcp_tools.comfy_push(channel="w", text="ok")
    assert res["warnings"] == []
