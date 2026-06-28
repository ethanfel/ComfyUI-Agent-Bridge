from src.bridge.store import ChannelStore

def test_list_channels_reports_turns():
    s = ChannelStore.instance()
    s.emit("a", text="x")
    s.push("b", text="y")
    listing = {c["name"]: c for c in s.list_channels()}
    assert listing["a"]["in_turn"] == 1
    assert listing["a"]["out_turn"] == 0
    assert listing["b"]["out_turn"] == 1

def test_list_channels_empty():
    s = ChannelStore.instance()
    assert s.list_channels() == []
