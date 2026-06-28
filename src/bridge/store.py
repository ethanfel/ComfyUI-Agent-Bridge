import builtins
import threading
import time
from collections import deque
from dataclasses import dataclass, field

# The singleton is stashed on `builtins` (one object per process, shared by every
# import) rather than on the class. ComfyUI can load this module under two
# different identities (e.g. `<pkg>.src.bridge.store` for the nodes and a second
# path for the MCP server), which would give each its own class object — and thus
# its own class-level singleton — so the MCP server and the nodes would silently
# use different stores. Keying off builtins guarantees one shared instance.
_GLOBAL_ATTR = "_comfyui_agent_bridge_channel_store"


def _empty() -> dict:
    return {"turn": 0, "text": None, "image_path": None, "seed": None}


def _msg(turn, text, image_path, seed) -> dict:
    return {"turn": turn, "text": text, "image_path": image_path, "seed": seed}


@dataclass
class _Channel:
    # FIFO queues: every emit/push is kept and delivered oldest-first.
    inbox: deque = field(default_factory=deque)   # graph -> agent
    outbox: deque = field(default_factory=deque)  # agent -> graph
    in_seq: int = 0          # total emitted (monotonic id)
    out_seq: int = 0         # total pushed (monotonic id)
    last_out: dict | None = None  # last delivered outbox message (for keep_last)


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

    # --- inbox: graph -> agent (FIFO) ---
    def emit(self, channel: str, text: str | None = None,
             image_path: str | None = None, seed: int | None = None) -> int:
        with self._cond:
            ch = self._chan(channel)
            ch.in_seq += 1
            ch.inbox.append(_msg(ch.in_seq, text, image_path, seed))
            self._cond.notify_all()
            return ch.in_seq

    def pull(self, channel: str) -> dict:
        """Pop the oldest emitted message (FIFO); empty when drained."""
        with self._lock:
            ch = self._channels.get(channel)
            if ch is None or not ch.inbox:
                return _empty()
            return ch.inbox.popleft()

    # --- outbox: agent -> graph (FIFO) ---
    def push(self, channel: str, text: str | None = None,
             image_path: str | None = None, seed: int | None = None) -> int:
        with self._cond:
            ch = self._chan(channel)
            ch.out_seq += 1
            ch.outbox.append(_msg(ch.out_seq, text, image_path, seed))
            self._cond.notify_all()
            return ch.out_seq

    def receive(self, channel: str, wait_seconds: float = 0.0,
                should_abort=None, poll_interval: float = 0.1) -> dict:
        """Pop the oldest pushed message (FIFO), waiting up to wait_seconds."""
        deadline = time.monotonic() + max(0.0, wait_seconds)
        with self._cond:
            while True:
                ch = self._channels.get(channel)
                if ch is not None and ch.outbox:
                    msg = ch.outbox.popleft()
                    ch.last_out = msg
                    return msg
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return _empty()
                if should_abort is not None:
                    # may raise (e.g. ComfyUI interrupt) to break the wait early;
                    # wake in short slices so an interrupt is noticed promptly.
                    should_abort()
                    wait_for = min(poll_interval, remaining)
                else:
                    wait_for = remaining
                self._cond.wait(timeout=wait_for)

    def peek(self, channel: str) -> dict:
        """Last *delivered* outbox message, WITHOUT touching the queue (keep_last)."""
        with self._lock:
            ch = self._channels.get(channel)
            if ch is None or ch.last_out is None:
                return _empty()
            return ch.last_out

    def list_channels(self) -> list[dict]:
        with self._lock:
            return [
                {"name": name,
                 "in_turn": ch.in_seq, "out_turn": ch.out_seq,
                 "in_pending": len(ch.inbox), "out_pending": len(ch.outbox)}
                for name, ch in sorted(self._channels.items())
            ]
