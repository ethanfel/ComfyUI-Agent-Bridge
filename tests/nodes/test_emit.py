import torch
from src.bridge.store import ChannelStore
from src.nodes.emit import AgentEmit

def test_emit_text_only_writes_inbox():
    node = AgentEmit()
    node.run(channel="main", text="hi", image=None)
    got = ChannelStore.instance().pull("main")
    assert got["text"] == "hi"
    assert got["image_path"] is None

def test_emit_image_materializes_path(tmp_path, monkeypatch):
    monkeypatch.setenv("COMFY_BRIDGE_TMP", str(tmp_path))
    node = AgentEmit()
    img = torch.zeros(1, 4, 4, 3)
    node.run(channel="main", text=None, image=img)
    got = ChannelStore.instance().pull("main")
    assert got["image_path"] is not None
    assert got["image_path"].endswith(".png")

def test_emit_returns_passthrough():
    node = AgentEmit()
    out = node.run(channel="main", text="hi", image=None)
    assert out == ("hi", None)  # (text, image) passthrough
