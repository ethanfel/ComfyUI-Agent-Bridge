"""Tiny logging helper so channel ops show up in the ComfyUI console."""


def short(value, n: int = 80):
    if value is None:
        return None
    s = str(value)
    return s if len(s) <= n else s[:n] + "…"


def log(msg: str) -> None:
    print(f"[agent-bridge] {msg}", flush=True)
