import threading
import time
from src.bridge.store import ChannelStore

def test_push_then_receive_consumes_once():
    s = ChannelStore.instance()
    s.push("main", text="result", image_path="/tmp/out.png")
    got = s.receive("main", wait_seconds=0)
    assert got["text"] == "result"
    assert got["image_path"] == "/tmp/out.png"
    # second receive with no new push -> empty (already consumed)
    again = s.receive("main", wait_seconds=0)
    assert again["text"] is None and again["image_path"] is None

def test_receive_nonblocking_empty_channel():
    s = ChannelStore.instance()
    got = s.receive("nope", wait_seconds=0)
    assert got == {"turn": 0, "text": None, "image_path": None}

def test_receive_blocks_until_push():
    s = ChannelStore.instance()

    def push_later():
        time.sleep(0.2)
        s.push("main", text="late")

    threading.Thread(target=push_later, daemon=True).start()
    start = time.monotonic()
    got = s.receive("main", wait_seconds=2.0)
    elapsed = time.monotonic() - start
    assert got["text"] == "late"
    assert 0.15 < elapsed < 1.5  # returned shortly after the push, not at timeout

def test_receive_times_out_returns_empty():
    s = ChannelStore.instance()
    start = time.monotonic()
    got = s.receive("main", wait_seconds=0.3)
    elapsed = time.monotonic() - start
    assert got["text"] is None and got["image_path"] is None
    assert elapsed >= 0.3
