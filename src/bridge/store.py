import threading
import time
from dataclasses import dataclass, field


@dataclass
class _Slot:
    text: str | None = None
    image_path: str | None = None
    turn: int = 0


@dataclass
class _Channel:
    inbox: _Slot = field(default_factory=_Slot)
    outbox: _Slot = field(default_factory=_Slot)
    last_consumed_out_turn: int = 0


class ChannelStore:
    _singleton: "ChannelStore | None" = None

    def __init__(self):
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._channels: dict[str, _Channel] = {}

    # --- singleton plumbing ---
    @classmethod
    def instance(cls) -> "ChannelStore":
        if cls._singleton is None:
            cls._singleton = cls()
        return cls._singleton

    @classmethod
    def reset(cls) -> None:
        cls._singleton = cls()

    def _chan(self, name: str) -> _Channel:
        ch = self._channels.get(name)
        if ch is None:
            ch = _Channel()
            self._channels[name] = ch
        return ch

    # --- inbox: graph -> agent ---
    def emit(self, channel: str, text: str | None = None,
             image_path: str | None = None) -> int:
        with self._cond:
            ch = self._chan(channel)
            ch.inbox.turn += 1
            ch.inbox.text = text
            ch.inbox.image_path = image_path
            self._cond.notify_all()
            return ch.inbox.turn

    def pull(self, channel: str) -> dict:
        with self._lock:
            ch = self._channels.get(channel)
            if ch is None:
                return {"turn": 0, "text": None, "image_path": None}
            s = ch.inbox
            return {"turn": s.turn, "text": s.text, "image_path": s.image_path}

    # --- outbox: agent -> graph ---
    def push(self, channel: str, text: str | None = None,
             image_path: str | None = None) -> int:
        with self._cond:
            ch = self._chan(channel)
            ch.outbox.turn += 1
            ch.outbox.text = text
            ch.outbox.image_path = image_path
            self._cond.notify_all()
            return ch.outbox.turn

    def receive(self, channel: str, wait_seconds: float = 0.0) -> dict:
        empty = {"turn": 0, "text": None, "image_path": None}
        deadline = time.monotonic() + max(0.0, wait_seconds)
        with self._cond:
            while True:
                ch = self._channels.get(channel)
                if ch is not None and ch.outbox.turn > ch.last_consumed_out_turn:
                    ch.last_consumed_out_turn = ch.outbox.turn
                    s = ch.outbox
                    return {"turn": s.turn, "text": s.text,
                            "image_path": s.image_path}
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return empty
                self._cond.wait(timeout=remaining)

    def list_channels(self) -> list[dict]:
        with self._lock:
            return [
                {"name": name, "in_turn": ch.inbox.turn,
                 "out_turn": ch.outbox.turn,
                 "consumed_out_turn": ch.last_consumed_out_turn}
                for name, ch in sorted(self._channels.items())
            ]
