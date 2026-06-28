from src.bridge.store import ChannelStore

def test_emit_then_pull_returns_payload():
    s = ChannelStore.instance()
    s.emit("main", text="hello", image_path="/tmp/a.png")
    got = s.pull("main")
    assert got["text"] == "hello"
    assert got["image_path"] == "/tmp/a.png"
    assert got["turn"] == 1

def test_pull_unknown_channel_is_empty_not_error():
    s = ChannelStore.instance()
    got = s.pull("never")
    assert got == {"turn": 0, "text": None, "image_path": None}

def test_emit_bumps_turn_each_time():
    s = ChannelStore.instance()
    s.emit("main", text="a")
    s.emit("main", text="b")
    assert s.pull("main")["turn"] == 2
    assert s.pull("main")["text"] == "b"
