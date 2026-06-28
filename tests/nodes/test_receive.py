import math

import torch
from src.bridge.store import ChannelStore
from src.bridge import images
from src.nodes.receive import AgentReceive


def test_is_changed_is_always_dirty():
    # NaN is never equal to itself, so ComfyUI re-runs the node every queue and
    # picks up newly pushed messages instead of serving a cached output.
    a = AgentReceive.IS_CHANGED(channel="main", wait_seconds=0.0)
    b = AgentReceive.IS_CHANGED(channel="main", wait_seconds=0.0)
    assert math.isnan(a) and math.isnan(b)
    assert a != b  # NaN != NaN

def test_receive_text(monkeypatch):
    ChannelStore.instance().push("main", text="done")
    node = AgentReceive()
    text, image, seed = node.run(channel="main", wait_seconds=0.0)
    assert text == "done"
    # no image pushed -> placeholder empty image
    assert image.shape[0] == 1 and image.shape[3] == 3
    assert seed == 0  # no seed pushed -> 0

def test_receive_image(tmp_path):
    p = images.save_tensor_png(torch.zeros(1, 4, 4, 3), str(tmp_path))
    ChannelStore.instance().push("main", image_path=p)
    node = AgentReceive()
    text, image, seed = node.run(channel="main", wait_seconds=0.0)
    assert text == ""  # no text -> empty string for STRING output
    assert image.shape == (1, 4, 4, 3)

def test_receive_seed():
    ChannelStore.instance().push("main", seed=123456789)
    node = AgentReceive()
    text, image, seed = node.run(channel="main", wait_seconds=0.0)
    assert seed == 123456789

def test_receive_timeout_returns_empty():
    node = AgentReceive()
    text, image, seed = node.run(channel="main", wait_seconds=0.2, keep_last=False)
    assert text == ""
    assert image.shape[0] == 1
    assert seed == 0


def test_keep_last_holds_value_after_consume():
    ChannelStore.instance().push("main", text="held-msg", seed=42)
    node = AgentReceive()
    t1, _, s1 = node.run(channel="main", wait_seconds=0.0)
    assert t1 == "held-msg" and s1 == 42  # consumed the fresh message
    # no new push -> keep_last holds the last value (text AND seed)
    t2, _, s2 = node.run(channel="main", wait_seconds=0.0, keep_last=True,
                         stop_on_timeout=False)
    assert t2 == "held-msg" and s2 == 42


def test_keep_last_false_blanks_after_consume():
    ChannelStore.instance().push("main", text="one")
    node = AgentReceive()
    node.run(channel="main", wait_seconds=0.0)  # consume
    t2, _, _ = node.run(channel="main", wait_seconds=0.0, keep_last=False,
                        stop_on_timeout=False)
    assert t2 == ""


def test_stop_on_timeout_without_server_does_not_crash():
    node = AgentReceive()
    text, image, seed = node.run(channel="main", wait_seconds=0.0,
                                 stop_on_timeout=True)
    assert text == ""
    assert image.shape[0] == 1
