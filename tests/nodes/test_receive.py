import torch
from src.bridge.store import ChannelStore
from src.bridge import images
from src.nodes.receive import AgentReceive

def test_receive_text(monkeypatch):
    ChannelStore.instance().push("main", text="done")
    node = AgentReceive()
    text, image = node.run(channel="main", wait_seconds=0.0)
    assert text == "done"
    # no image pushed -> placeholder empty image
    assert image.shape[0] == 1 and image.shape[3] == 3

def test_receive_image(tmp_path):
    p = images.save_tensor_png(torch.zeros(1, 4, 4, 3), str(tmp_path))
    ChannelStore.instance().push("main", image_path=p)
    node = AgentReceive()
    text, image = node.run(channel="main", wait_seconds=0.0)
    assert text == ""  # no text -> empty string for STRING output
    assert image.shape == (1, 4, 4, 3)

def test_receive_timeout_returns_empty():
    node = AgentReceive()
    text, image = node.run(channel="main", wait_seconds=0.2)
    assert text == ""
    assert image.shape[0] == 1
