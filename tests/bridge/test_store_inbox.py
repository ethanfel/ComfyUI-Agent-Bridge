from src.bridge.store import ChannelStore

def test_emit_then_pull_returns_payload():
    s = ChannelStore.instance()
    s.emit("main", text="hello", image_path="/tmp/a.png", seed=7)
    got = s.pull("main")
    assert got["text"] == "hello"
    assert got["image_path"] == "/tmp/a.png"
    assert got["seed"] == 7
    assert got["turn"] == 1

def test_pull_unknown_channel_is_empty_not_error():
    s = ChannelStore.instance()
    got = s.pull("never")
    assert got == {"turn": 0, "text": None, "image_path": None, "seed": None}

def test_emit_pull_is_fifo():
    s = ChannelStore.instance()
    s.emit("main", text="a")
    s.emit("main", text="b")
    first = s.pull("main")
    second = s.pull("main")
    assert (first["turn"], first["text"]) == (1, "a")   # oldest first
    assert (second["turn"], second["text"]) == (2, "b")
    assert s.pull("main")["text"] is None               # drained
