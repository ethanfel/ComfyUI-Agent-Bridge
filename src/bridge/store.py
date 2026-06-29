import builtins
import threading
import time
from dataclasses import dataclass, field

# The singleton is stashed on `builtins` (one object per process, shared by every
# import) rather than on the class. ComfyUI can load this module under two
# different identities (e.g. `<pkg>.src.bridge.store` for the nodes and a second
# path for the MCP server), which would give each its own class object — and thus
# its own class-level singleton — so the MCP server and the nodes would silently
# use different stores. Keying off builtins guarantees one shared instance.
_GLOBAL_ATTR = "_comfyui_agent_bridge_channel_store"


@dataclass
class _Slot:
    text: str | None = None
    image_path: str | None = None
    seed: int | None = None
    turn: int = 0


@dataclass
class _Channel:
    inbox: _Slot = field(default_factory=_Slot)
    outbox: _Slot = field(default_factory=_Slot)
    last_consumed_out_turn: int = 0


class ChannelStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._channels: dict[str, _Channel] = {}

    # --- singleton plumbing (process-global; see _GLOBAL_ATTR note above) ---
    @classmethod
    def instance(cls) -> "ChannelStore":
        inst = getattr(builtins, _GLOBAL_ATTR, None)
        if inst is None:
            inst = cls()
            setattr(builtins, _GLOBAL_ATTR, inst)
        return inst

    @classmethod
    def reset(cls) -> None:
        setattr(builtins, _GLOBAL_ATTR, cls())

    def _chan(self, name: str) -> _Channel:
        ch = self._channels.get(name)
        if ch is None:
            ch = _Channel()
            self._channels[name] = ch
        return ch

    @staticmethod
    def _payload(s: "_Slot") -> dict:
        return {"turn": s.turn, "text": s.text, "image_path": s.image_path,
                "seed": s.seed}

    # --- inbox: graph -> agent ---
    def emit(self, channel: str, text: str | None = None,
             image_path: str | None = None, seed: int | None = None) -> int:
        with self._cond:
            ch = self._chan(channel)
            ch.inbox.turn += 1
            ch.inbox.text = text
            ch.inbox.image_path = image_path
            ch.inbox.seed = seed
            self._cond.notify_all()
            return ch.inbox.turn

    def pull(self, channel: str) -> dict:
        with self._lock:
            ch = self._channels.get(channel)
            if ch is None:
                return {"turn": 0, "text": None, "image_path": None, "seed": None}
            return self._payload(ch.inbox)

    # --- outbox: agent -> graph ---
    def push(self, channel: str, text: str | None = None,
             image_path: str | None = None, seed: int | None = None) -> int:
        with self._cond:
            ch = self._chan(channel)
            ch.outbox.turn += 1
            ch.outbox.text = text
            ch.outbox.image_path = image_path
            ch.outbox.seed = seed
            self._cond.notify_all()
            return ch.outbox.turn

    def receive(self, channel: str, wait_seconds: float = 0.0,
                should_abort=None, poll_interval: float = 0.1) -> dict:
        empty = {"turn": 0, "text": None, "image_path": None, "seed": None}
        deadline = time.monotonic() + max(0.0, wait_seconds)
        with self._cond:
            while True:
                ch = self._channels.get(channel)
                if ch is not None and ch.outbox.turn > ch.last_consumed_out_turn:
                    ch.last_consumed_out_turn = ch.outbox.turn
                    return self._payload(ch.outbox)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return empty
                if should_abort is not None:
                    # may raise (e.g. ComfyUI interrupt) to break the wait early;
                    # wake in short slices so an interrupt is noticed promptly.
                    should_abort()
                    wait_for = min(poll_interval, remaining)
                else:
                    wait_for = remaining
                self._cond.wait(timeout=wait_for)

    def peek(self, channel: str) -> dict:
        """Last pushed outbox value, WITHOUT consuming it (for keep-last)."""
        with self._lock:
            ch = self._channels.get(channel)
            if ch is None:
                return {"turn": 0, "text": None, "image_path": None, "seed": None}
            return self._payload(ch.outbox)

    def list_channels(self) -> list[dict]:
        with self._lock:
            return [
                {"name": name, "in_turn": ch.inbox.turn,
                 "out_turn": ch.outbox.turn,
                 "consumed_out_turn": ch.last_consumed_out_turn}
                for name, ch in sorted(self._channels.items())
            ]
