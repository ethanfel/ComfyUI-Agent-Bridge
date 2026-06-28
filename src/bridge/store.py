import threading
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class _Slot:
    text: Optional[str] = None
    image_path: Optional[str] = None
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
    def emit(self, channel: str, text: Optional[str] = None,
             image_path: Optional[str] = None) -> int:
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
