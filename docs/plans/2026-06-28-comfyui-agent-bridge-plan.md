# ComfyUI Agent Bridge Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build `ComfyUI-Nodes-Agents` — in-graph `Agent Emit` / `Agent Receive` nodes on named channels, plus an in-process MCP server, so an externally-running agent (Claude Code / Codex) can exchange text + images with a ComfyUI workflow mid-pipeline and trigger runs.

**Architecture:** A thread-safe singleton `ChannelStore` holds per-channel inbox/outbox slots with turn counters. ComfyUI nodes touch the store directly (same process). A `FastMCP` streamable-HTTP server runs in a daemon thread on a side port; its tools (`comfy_pull` / `comfy_push` / `comfy_list_channels` / `comfy_run_workflow` / `comfy_get_result`) touch the same singleton. Images cross by file path (temp dir); text inline.

**Tech Stack:** Python 3.10+, ComfyUI custom-node API (`NODE_CLASS_MAPPINGS`), `torch` + `numpy` + `Pillow` (shipped by ComfyUI), `mcp` (official MCP Python SDK / `FastMCP`), `aiohttp` (shipped), `pytest`.

**Design doc:** `docs/plans/2026-06-28-comfyui-agent-bridge-design.md`

---

## Conventions

- TDD throughout: failing test → run-fail → minimal impl → run-pass → commit.
- Run tests with: `python -m pytest <path> -v` from repo root.
- The store is a process singleton: every test that touches it calls `ChannelStore.reset()` in a fixture so tests don't leak state.
- `torch` is assumed present (ComfyUI ships it). If a CI box lacks it, image tests are marked `@pytest.mark.skipif(torch is None)`.
- Channel terminology: **inbox** = graph→agent (set by `Agent Emit`, read by `comfy_pull`). **outbox** = agent→graph (set by `comfy_push`, read by `Agent Receive`).

---

## Task 0: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `requirements.txt`
- Create: `src/__init__.py`, `src/bridge/__init__.py`, `src/nodes/__init__.py`
- Create: `tests/__init__.py`, `tests/conftest.py`
- Create: `.gitignore`

**Step 1: Write `pyproject.toml`**

```toml
[project]
name = "comfyui-nodes-agents"
version = "0.1.0"
description = "In-graph ComfyUI nodes + MCP bridge for external coding agents (Claude Code / Codex)"
requires-python = ">=3.10"
dependencies = ["mcp>=1.2.0"]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

**Step 2: Write `requirements.txt`**

```
mcp>=1.2.0
```

**Step 3: Write `.gitignore`**

```
__pycache__/
*.pyc
.pytest_cache/
.comfy_bridge_tmp/
```

**Step 4: Create empty package `__init__.py` files** (`src/__init__.py`, `src/bridge/__init__.py`, `src/nodes/__init__.py`, `tests/__init__.py`).

**Step 5: Write `tests/conftest.py`**

```python
import pytest
from src.bridge.store import ChannelStore

@pytest.fixture(autouse=True)
def _reset_store():
    ChannelStore.reset()
    yield
    ChannelStore.reset()
```

**Step 6: Verify pytest collects nothing yet**

Run: `python -m pytest -q`
Expected: `no tests ran` (conftest import will fail until Task 1 creates `store.py` — that's expected; proceed to Task 1).

**Step 7: Commit**

```bash
git add pyproject.toml requirements.txt .gitignore src tests
git commit -m "chore: scaffold comfyui-nodes-agents package"
```

---

## Task 1: ChannelStore — inbox (graph→agent)

**Files:**
- Create: `src/bridge/store.py`
- Test: `tests/bridge/test_store_inbox.py`

**Step 1: Write the failing test** (`tests/bridge/test_store_inbox.py`, also create `tests/bridge/__init__.py`)

```python
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
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/bridge/test_store_inbox.py -v`
Expected: FAIL (`ModuleNotFoundError` / `AttributeError`).

**Step 3: Write minimal implementation** (`src/bridge/store.py`)

```python
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
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/bridge/test_store_inbox.py -v`
Expected: PASS (3 passed).

**Step 5: Commit**

```bash
git add src/bridge/store.py tests/bridge
git commit -m "feat: ChannelStore inbox (graph->agent) with emit/pull"
```

---

## Task 2: ChannelStore — outbox (agent→graph) with consume + wait/timeout

**Files:**
- Modify: `src/bridge/store.py`
- Test: `tests/bridge/test_store_outbox.py`

**Step 1: Write the failing test**

```python
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
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/bridge/test_store_outbox.py -v`
Expected: FAIL (`AttributeError: 'ChannelStore' object has no attribute 'push'`).

**Step 3: Add `push` and `receive` to `ChannelStore`**

```python
    # --- outbox: agent -> graph ---
    def push(self, channel: str, text: Optional[str] = None,
             image_path: Optional[str] = None) -> int:
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
```

Add `import time` at the top of `store.py`.

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/bridge/test_store_outbox.py -v`
Expected: PASS (4 passed).

**Step 5: Commit**

```bash
git add src/bridge/store.py tests/bridge/test_store_outbox.py
git commit -m "feat: ChannelStore outbox (agent->graph) with consume + blocking receive"
```

---

## Task 3: ChannelStore — list_channels

**Files:**
- Modify: `src/bridge/store.py`
- Test: `tests/bridge/test_store_list.py`

**Step 1: Write the failing test**

```python
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
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/bridge/test_store_list.py -v`
Expected: FAIL (`AttributeError: list_channels`).

**Step 3: Add `list_channels`**

```python
    def list_channels(self) -> list[dict]:
        with self._lock:
            return [
                {"name": name, "in_turn": ch.inbox.turn,
                 "out_turn": ch.outbox.turn,
                 "consumed_out_turn": ch.last_consumed_out_turn}
                for name, ch in sorted(self._channels.items())
            ]
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/bridge/test_store_list.py -v`
Expected: PASS (2 passed).

**Step 5: Commit**

```bash
git add src/bridge/store.py tests/bridge/test_store_list.py
git commit -m "feat: ChannelStore.list_channels"
```

---

## Task 4: Image helpers (tensor ↔ PNG)

**Files:**
- Create: `src/bridge/images.py`
- Test: `tests/bridge/test_images.py`

**Step 1: Write the failing test**

```python
import os
import numpy as np
import torch
from src.bridge import images

def test_save_then_load_roundtrip(tmp_path):
    # ComfyUI IMAGE tensor: [B, H, W, C] float 0..1
    t = torch.zeros(1, 8, 8, 3)
    t[0, 0, 0, 0] = 1.0  # red corner
    path = images.save_tensor_png(t, str(tmp_path))
    assert os.path.exists(path)
    back = images.load_png_tensor(path)
    assert back.shape == (1, 8, 8, 3)
    assert back[0, 0, 0, 0].item() > 0.9  # red preserved

def test_empty_image_shape():
    e = images.empty_image()
    assert e.ndim == 4 and e.shape[0] == 1 and e.shape[3] == 3
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/bridge/test_images.py -v`
Expected: FAIL (`ModuleNotFoundError: src.bridge.images`).

**Step 3: Write implementation** (`src/bridge/images.py`)

```python
import os
import uuid
import numpy as np
import torch
from PIL import Image


def save_tensor_png(tensor: torch.Tensor, out_dir: str) -> str:
    """ComfyUI IMAGE [B,H,W,C] float 0..1 -> PNG file, returns path."""
    os.makedirs(out_dir, exist_ok=True)
    if tensor.ndim == 4:
        tensor = tensor[0]
    arr = (tensor.clamp(0, 1).cpu().numpy() * 255.0).round().astype(np.uint8)
    img = Image.fromarray(arr, mode="RGB")
    path = os.path.join(out_dir, f"img_{uuid.uuid4().hex}.png")
    img.save(path)
    return path


def load_png_tensor(path: str) -> torch.Tensor:
    """PNG file -> ComfyUI IMAGE [1,H,W,C] float 0..1."""
    img = Image.open(path).convert("RGB")
    arr = np.asarray(img).astype(np.float32) / 255.0
    return torch.from_numpy(arr)[None, ...]


def empty_image() -> torch.Tensor:
    """Placeholder IMAGE output when no image is available (64x64 black)."""
    return torch.zeros(1, 64, 64, 3)
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/bridge/test_images.py -v`
Expected: PASS (2 passed).

**Step 5: Commit**

```bash
git add src/bridge/images.py tests/bridge/test_images.py
git commit -m "feat: tensor<->PNG image helpers"
```

---

## Task 5: `Agent Emit` node

**Files:**
- Create: `src/nodes/emit.py`
- Test: `tests/nodes/test_emit.py` (+ `tests/nodes/__init__.py`)

**Step 1: Write the failing test**

```python
import torch
from src.bridge.store import ChannelStore
from src.nodes.emit import AgentEmit

def test_emit_text_only_writes_inbox():
    node = AgentEmit()
    node.run(channel="main", text="hi", image=None)
    got = ChannelStore.instance().pull("main")
    assert got["text"] == "hi"
    assert got["image_path"] is None

def test_emit_image_materializes_path(tmp_path, monkeypatch):
    monkeypatch.setenv("COMFY_BRIDGE_TMP", str(tmp_path))
    node = AgentEmit()
    img = torch.zeros(1, 4, 4, 3)
    node.run(channel="main", text=None, image=img)
    got = ChannelStore.instance().pull("main")
    assert got["image_path"] is not None
    assert got["image_path"].endswith(".png")

def test_emit_returns_passthrough():
    node = AgentEmit()
    out = node.run(channel="main", text="hi", image=None)
    assert out == ("hi", None)  # (text, image) passthrough
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/nodes/test_emit.py -v`
Expected: FAIL (`ModuleNotFoundError: src.nodes.emit`).

**Step 3: Write implementation** (`src/nodes/emit.py`)

```python
import os
from src.bridge.store import ChannelStore
from src.bridge import images


def _tmp_dir() -> str:
    return os.environ.get("COMFY_BRIDGE_TMP", ".comfy_bridge_tmp")


class AgentEmit:
    """Send text/image from the graph to an external agent on a named channel."""

    CATEGORY = "agents/bridge"
    FUNCTION = "run"
    RETURN_TYPES = ("STRING", "IMAGE")
    RETURN_NAMES = ("text", "image")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "channel": ("STRING", {"default": "main"}),
            },
            "optional": {
                "text": ("STRING", {"default": "", "multiline": True}),
                "image": ("IMAGE",),
            },
        }

    def run(self, channel="main", text=None, image=None):
        image_path = None
        if image is not None:
            image_path = images.save_tensor_png(image, _tmp_dir())
        text_val = text if text else None
        ChannelStore.instance().emit(channel, text=text_val, image_path=image_path)
        return (text_val, image)
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/nodes/test_emit.py -v`
Expected: PASS (3 passed).

**Step 5: Commit**

```bash
git add src/nodes/emit.py tests/nodes
git commit -m "feat: Agent Emit node (graph->agent)"
```

---

## Task 6: `Agent Receive` node

**Files:**
- Create: `src/nodes/receive.py`
- Test: `tests/nodes/test_receive.py`

**Step 1: Write the failing test**

```python
import torch
from src.bridge.store import ChannelStore
from src.bridge import images
from src.nodes.receive import AgentReceive

def test_receive_text(monkeypatch):
    ChannelStore.instance().push("main", text="done")
    node = AgentReceive()
    text, image = node.run(channel="main", wait_seconds=0.0)
    assert text == "done"
    # no image pushed -> placeholder empty image
    assert image.shape[0] == 1 and image.shape[3] == 3

def test_receive_image(tmp_path):
    p = images.save_tensor_png(torch.zeros(1, 4, 4, 3), str(tmp_path))
    ChannelStore.instance().push("main", image_path=p)
    node = AgentReceive()
    text, image = node.run(channel="main", wait_seconds=0.0)
    assert text == ""  # no text -> empty string for STRING output
    assert image.shape == (1, 4, 4, 3)

def test_receive_timeout_returns_empty():
    node = AgentReceive()
    text, image = node.run(channel="main", wait_seconds=0.2)
    assert text == ""
    assert image.shape[0] == 1
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/nodes/test_receive.py -v`
Expected: FAIL (`ModuleNotFoundError: src.nodes.receive`).

**Step 3: Write implementation** (`src/nodes/receive.py`)

```python
from src.bridge.store import ChannelStore
from src.bridge import images


class AgentReceive:
    """Receive text/image pushed by an external agent on a named channel."""

    CATEGORY = "agents/bridge"
    FUNCTION = "run"
    RETURN_TYPES = ("STRING", "IMAGE")
    RETURN_NAMES = ("text", "image")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "channel": ("STRING", {"default": "main"}),
                "wait_seconds": ("FLOAT", {"default": 30.0, "min": 0.0,
                                           "max": 86400.0, "step": 1.0}),
            },
        }

    def run(self, channel="main", wait_seconds=30.0):
        got = ChannelStore.instance().receive(channel, wait_seconds=wait_seconds)
        text = got["text"] if got["text"] is not None else ""
        if got["image_path"]:
            image = images.load_png_tensor(got["image_path"])
        else:
            image = images.empty_image()
        return (text, image)
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/nodes/test_receive.py -v`
Expected: PASS (3 passed).

**Step 5: Commit**

```bash
git add src/nodes/receive.py tests/nodes/test_receive.py
git commit -m "feat: Agent Receive node (agent->graph)"
```

---

## Task 7: Workflow trigger logic (pure functions)

**Files:**
- Create: `src/bridge/workflows.py`
- Test: `tests/bridge/test_workflows.py`

> Keep ComfyUI HTTP I/O thin and mockable. `load_workflow` + `apply_inputs`
> are pure; `submit_prompt` / `fetch_result` are thin async wrappers tested
> with a fake HTTP client.

**Step 1: Write the failing test**

```python
import json
import pytest
from src.bridge import workflows

def test_load_workflow_reads_json(tmp_path):
    wf = {"3": {"class_type": "KSampler", "inputs": {"seed": 1}}}
    d = tmp_path / "wf"
    d.mkdir()
    (d / "txt2img.json").write_text(json.dumps(wf))
    got = workflows.load_workflow("txt2img", str(d))
    assert got == wf

def test_load_workflow_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        workflows.load_workflow("nope", str(tmp_path))

def test_apply_inputs_overrides_node_field():
    wf = {"3": {"class_type": "KSampler", "inputs": {"seed": 1}}}
    out = workflows.apply_inputs(wf, {"3.seed": 42})
    assert out["3"]["inputs"]["seed"] == 42
    # original not mutated
    assert wf["3"]["inputs"]["seed"] == 1

def test_apply_inputs_unknown_target_raises():
    wf = {"3": {"class_type": "KSampler", "inputs": {}}}
    with pytest.raises(KeyError):
        workflows.apply_inputs(wf, {"9.seed": 1})
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/bridge/test_workflows.py -v`
Expected: FAIL (`ModuleNotFoundError: src.bridge.workflows`).

**Step 3: Write implementation** (`src/bridge/workflows.py`)

```python
import copy
import json
import os
from typing import Optional


def workflows_dir() -> str:
    return os.environ.get("COMFY_BRIDGE_WORKFLOWS", "workflows")


def load_workflow(name: str, base_dir: Optional[str] = None) -> dict:
    base = base_dir or workflows_dir()
    path = os.path.join(base, f"{name}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"workflow not found: {path}")
    with open(path) as fh:
        return json.load(fh)


def apply_inputs(workflow: dict, inputs: Optional[dict]) -> dict:
    """inputs: {"<node_id>.<field>": value}. Returns a new dict (no mutation)."""
    wf = copy.deepcopy(workflow)
    for key, value in (inputs or {}).items():
        node_id, _, field = key.partition(".")
        if node_id not in wf:
            raise KeyError(f"unknown node id in inputs: {node_id}")
        wf[node_id].setdefault("inputs", {})[field] = value
    return wf
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/bridge/test_workflows.py -v`
Expected: PASS (4 passed).

**Step 5: Commit**

```bash
git add src/bridge/workflows.py tests/bridge/test_workflows.py
git commit -m "feat: workflow load + input injection (pure)"
```

---

## Task 8: Workflow submit/fetch (thin async HTTP)

**Files:**
- Modify: `src/bridge/workflows.py`
- Test: `tests/bridge/test_workflows_http.py`

**Step 1: Write the failing test** (uses a fake client, no real network)

```python
import asyncio
from src.bridge import workflows

class FakeResp:
    def __init__(self, payload): self._payload = payload
    async def json(self): return self._payload
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False

class FakeSession:
    def __init__(self, prompt_resp, history_resp):
        self._prompt_resp = prompt_resp
        self._history_resp = history_resp
        self.posted = None
    def post(self, url, json=None):
        self.posted = (url, json)
        return FakeResp(self._prompt_resp)
    def get(self, url):
        return FakeResp(self._history_resp)
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False

def test_submit_prompt_posts_and_returns_id():
    session = FakeSession({"prompt_id": "abc123"}, {})
    wf = {"3": {"class_type": "X", "inputs": {}}}
    pid = asyncio.run(workflows.submit_prompt(wf, base_url="http://h:8188", session=session))
    assert pid == "abc123"
    url, body = session.posted
    assert url == "http://h:8188/prompt"
    assert body["prompt"] == wf

def test_fetch_result_extracts_images():
    history = {"abc": {"outputs": {"9": {"images": [
        {"filename": "ComfyUI_0001.png", "subfolder": "", "type": "output"}]}}}}
    session = FakeSession({}, history)
    res = asyncio.run(workflows.fetch_result("abc", base_url="http://h:8188", session=session))
    assert res["images"][0]["filename"] == "ComfyUI_0001.png"
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/bridge/test_workflows_http.py -v`
Expected: FAIL (`AttributeError: submit_prompt`).

**Step 3: Add async helpers to `workflows.py`**

```python
async def submit_prompt(workflow: dict, base_url: str = "http://127.0.0.1:8188",
                        session=None) -> str:
    import aiohttp
    owns = session is None
    session = session or aiohttp.ClientSession()
    try:
        async with session.post(f"{base_url}/prompt", json={"prompt": workflow}) as r:
            data = await r.json()
        return data["prompt_id"]
    finally:
        if owns:
            await session.close()


async def fetch_result(prompt_id: str, base_url: str = "http://127.0.0.1:8188",
                       session=None) -> dict:
    import aiohttp
    owns = session is None
    session = session or aiohttp.ClientSession()
    try:
        async with session.get(f"{base_url}/history/{prompt_id}") as r:
            history = await r.json()
        entry = history.get(prompt_id, {})
        images = []
        for node_out in entry.get("outputs", {}).values():
            images.extend(node_out.get("images", []))
        return {"prompt_id": prompt_id, "images": images,
                "raw": entry.get("outputs", {})}
    finally:
        if owns:
            await session.close()
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/bridge/test_workflows_http.py -v`
Expected: PASS (2 passed).

**Step 5: Commit**

```bash
git add src/bridge/workflows.py tests/bridge/test_workflows_http.py
git commit -m "feat: thin async submit_prompt + fetch_result"
```

---

## Task 9: MCP tool layer (SDK-independent functions)

> The MCP tools are thin wrappers. Put the real logic in `mcp_tools.py` as plain
> functions so they're testable without booting a server, then bind them to
> `FastMCP` in Task 10.

**Files:**
- Create: `src/bridge/mcp_tools.py`
- Test: `tests/bridge/test_mcp_tools.py`

**Step 1: Write the failing test**

```python
from src.bridge.store import ChannelStore
from src.bridge import mcp_tools

def test_tool_push_then_graph_receives():
    mcp_tools.comfy_push(channel="main", text="hello")
    got = ChannelStore.instance().receive("main", wait_seconds=0)
    assert got["text"] == "hello"

def test_tool_pull_reads_graph_emit():
    ChannelStore.instance().emit("main", text="from-graph")
    got = mcp_tools.comfy_pull(channel="main")
    assert got["text"] == "from-graph"

def test_tool_list_channels():
    ChannelStore.instance().emit("a", text="x")
    names = [c["name"] for c in mcp_tools.comfy_list_channels()]
    assert "a" in names
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/bridge/test_mcp_tools.py -v`
Expected: FAIL (`ModuleNotFoundError: src.bridge.mcp_tools`).

**Step 3: Write implementation** (`src/bridge/mcp_tools.py`)

```python
"""SDK-independent MCP tool logic. Bound to FastMCP in mcp_server.py."""
import os
from src.bridge.store import ChannelStore
from src.bridge import workflows

COMFY_BASE_URL = os.environ.get("COMFY_BASE_URL", "http://127.0.0.1:8188")


def comfy_pull(channel: str = "main") -> dict:
    """Read the latest text/image the graph emitted on a channel."""
    return ChannelStore.instance().pull(channel)


def comfy_push(channel: str = "main", text: str = None,
               image_path: str = None) -> dict:
    """Send text/image to the graph's Agent Receive node on a channel."""
    turn = ChannelStore.instance().push(channel, text=text, image_path=image_path)
    return {"channel": channel, "out_turn": turn}


def comfy_list_channels() -> list:
    """List active channels and their turn counters."""
    return ChannelStore.instance().list_channels()


async def comfy_run_workflow(name: str, inputs: dict = None,
                             wait: bool = True) -> dict:
    """Load a saved workflow, optionally inject inputs, queue it, optionally wait."""
    wf = workflows.apply_inputs(workflows.load_workflow(name), inputs)
    prompt_id = await workflows.submit_prompt(wf, base_url=COMFY_BASE_URL)
    if not wait:
        return {"prompt_id": prompt_id, "status": "queued"}
    # poll history until outputs appear (bounded)
    import asyncio
    for _ in range(600):  # ~60s at 0.1s
        res = await workflows.fetch_result(prompt_id, base_url=COMFY_BASE_URL)
        if res["images"] or res["raw"]:
            return {"prompt_id": prompt_id, "status": "done", **res}
        await asyncio.sleep(0.1)
    return {"prompt_id": prompt_id, "status": "timeout"}


async def comfy_get_result(prompt_id: str) -> dict:
    """Fetch produced images/outputs for a prompt id."""
    return await workflows.fetch_result(prompt_id, base_url=COMFY_BASE_URL)
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/bridge/test_mcp_tools.py -v`
Expected: PASS (3 passed). (`comfy_run_workflow`/`comfy_get_result` are covered via `workflows` tests; async run-workflow integration is exercised manually in Task 12.)

**Step 5: Commit**

```bash
git add src/bridge/mcp_tools.py tests/bridge/test_mcp_tools.py
git commit -m "feat: SDK-independent MCP tool functions"
```

---

## Task 10: FastMCP server + lifecycle

**Files:**
- Create: `src/bridge/mcp_server.py`
- Test: `tests/bridge/test_mcp_server_smoke.py`

**Step 1: Write the failing test** (construction smoke test — no network)

```python
from src.bridge import mcp_server

def test_build_server_registers_tools():
    mcp = mcp_server.build_server()
    # FastMCP stores tools; assert our names are present
    tool_names = mcp_server.registered_tool_names(mcp)
    for name in ["comfy_pull", "comfy_push", "comfy_list_channels",
                 "comfy_run_workflow", "comfy_get_result"]:
        assert name in tool_names

def test_start_is_idempotent():
    mcp_server.start_in_background(port=0, _test_no_serve=True)
    mcp_server.start_in_background(port=0, _test_no_serve=True)  # no crash
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/bridge/test_mcp_server_smoke.py -v`
Expected: FAIL (`ModuleNotFoundError: src.bridge.mcp_server`).

**Step 3: Write implementation** (`src/bridge/mcp_server.py`)

```python
import os
import threading
from mcp.server.fastmcp import FastMCP
from src.bridge import mcp_tools

_started = False
_lock = threading.Lock()


def build_server(host: str = "127.0.0.1", port: int = 9188) -> FastMCP:
    mcp = FastMCP("comfy-bridge", host=host, port=port)
    mcp.tool()(mcp_tools.comfy_pull)
    mcp.tool()(mcp_tools.comfy_push)
    mcp.tool()(mcp_tools.comfy_list_channels)
    mcp.tool()(mcp_tools.comfy_run_workflow)
    mcp.tool()(mcp_tools.comfy_get_result)
    return mcp


def registered_tool_names(mcp: FastMCP) -> list:
    # FastMCP exposes a tool manager; fall back across SDK versions
    mgr = getattr(mcp, "_tool_manager", None)
    if mgr is not None and hasattr(mgr, "_tools"):
        return list(mgr._tools.keys())
    return [t.name for t in getattr(mcp, "list_tools", lambda: [])()]


def start_in_background(host: str = "127.0.0.1", port: int = None,
                        _test_no_serve: bool = False) -> None:
    global _started
    with _lock:
        if _started:
            return
        _started = True
    port = port or int(os.environ.get("COMFY_BRIDGE_MCP_PORT", "9188"))
    mcp = build_server(host=host, port=port)
    if _test_no_serve:
        return

    def _serve():
        mcp.run(transport="streamable-http")

    threading.Thread(target=_serve, name="comfy-bridge-mcp",
                     daemon=True).start()
    print(f"[comfyui-nodes-agents] MCP bridge on "
          f"http://{host}:{port}/mcp  (claude mcp add --transport http "
          f"comfy http://{host}:{port}/mcp)")
```

> Note: `registered_tool_names` reaches into FastMCP internals which vary by SDK
> version. If the test fails on the installed `mcp` version, inspect the actual
> attribute (`dir(mcp)`) and adjust — this is the one spot allowed to be
> version-pinned. Pin `mcp` in `requirements.txt` to the version you validate.

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/bridge/test_mcp_server_smoke.py -v`
Expected: PASS (2 passed). If `registered_tool_names` fails, adjust per the note, re-run.

**Step 5: Commit**

```bash
git add src/bridge/mcp_server.py tests/bridge/test_mcp_server_smoke.py
git commit -m "feat: FastMCP server build + background lifecycle"
```

---

## Task 11: ComfyUI entrypoint (`__init__.py`)

**Files:**
- Create: `__init__.py` (repo root — this is what ComfyUI imports)
- Test: `tests/test_entrypoint.py`

**Step 1: Write the failing test**

```python
import importlib

def test_node_mappings_exported():
    mod = importlib.import_module("__init__")
    assert "AgentEmit" in mod.NODE_CLASS_MAPPINGS
    assert "AgentReceive" in mod.NODE_CLASS_MAPPINGS
    assert mod.NODE_DISPLAY_NAME_MAPPINGS["AgentEmit"]
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_entrypoint.py -v`
Expected: FAIL (`ModuleNotFoundError: __init__` or `AttributeError`).

**Step 3: Write implementation** (`__init__.py`)

```python
"""ComfyUI-Nodes-Agents: in-graph bridge nodes + MCP server for coding agents."""
from src.nodes.emit import AgentEmit
from src.nodes.receive import AgentReceive
from src.bridge import mcp_server

NODE_CLASS_MAPPINGS = {
    "AgentEmit": AgentEmit,
    "AgentReceive": AgentReceive,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "AgentEmit": "Agent Emit (→ agent)",
    "AgentReceive": "Agent Receive (← agent)",
}

# Start the MCP bridge when ComfyUI loads this package.
try:
    mcp_server.start_in_background()
except Exception as exc:  # never block ComfyUI startup
    print(f"[comfyui-nodes-agents] MCP bridge failed to start: {exc}")

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
```

**Step 4: Run test to verify it passes**

Run: `COMFY_BRIDGE_MCP_PORT=0 python -m pytest tests/test_entrypoint.py -v`
Expected: PASS. (Import triggers `start_in_background`; the daemon thread binding is harmless in test. If port bind is flaky in CI, set `COMFY_BRIDGE_MCP_PORT` to an unused port.)

**Step 5: Commit**

```bash
git add __init__.py tests/test_entrypoint.py
git commit -m "feat: ComfyUI entrypoint with node mappings + MCP autostart"
```

---

## Task 12: Codex stdio shim + README

**Files:**
- Create: `scripts/codex_stdio_shim.py`
- Create: `README.md`

**Step 1: Write the stdio→HTTP shim** (`scripts/codex_stdio_shim.py`)

```python
#!/usr/bin/env python3
"""Stdio MCP proxy -> the in-process HTTP bridge, for Codex builds that only
speak stdio MCP. Codex spawns this; it forwards to http://127.0.0.1:9188/mcp."""
import os
import sys
try:
    from mcp.client.streamable_http import streamablehttp_client
    from mcp.server.stdio import stdio_server
    from mcp.shared.proxy import create_proxy_server  # if available in SDK
except Exception as exc:
    sys.stderr.write(f"shim import error: {exc}\n")
    raise

URL = os.environ.get("COMFY_BRIDGE_URL", "http://127.0.0.1:9188/mcp")
# Implementation note: if the installed mcp SDK lacks a ready-made proxy helper,
# implement a minimal JSON-RPC pump: read stdio frames -> POST to URL -> stream
# responses back. Keep it ~30 lines. Validate against the installed SDK version.
```

> This task is **conditional**: only finish the shim if the user's Codex build
> rejects HTTP MCP. Claude Code supports HTTP MCP directly, so for Claude this
> file is unused. Validate the exact SDK proxy API at implementation time.

**Step 2: Write `README.md`** covering: install (clone into `ComfyUI/custom_nodes/`, `pip install -r requirements.txt`), the two nodes, the channel model, connecting the agent:

```
# Claude Code
claude mcp add --transport http comfy http://127.0.0.1:9188/mcp
# Codex (HTTP):  add to ~/.codex/config.toml [mcp_servers] with url
# Codex (stdio): point at scripts/codex_stdio_shim.py
```

Document the core loop, `wait_seconds`, the `workflows/` dir for `comfy_run_workflow`, and env vars (`COMFY_BRIDGE_MCP_PORT`, `COMFY_BRIDGE_TMP`, `COMFY_BRIDGE_WORKFLOWS`, `COMFY_BASE_URL`).

**Step 3: Commit**

```bash
git add scripts/codex_stdio_shim.py README.md
git commit -m "docs: README + Codex stdio shim scaffold"
```

---

## Task 13: Full suite + manual verification

**Step 1: Run the whole suite**

Run: `COMFY_BRIDGE_MCP_PORT=0 python -m pytest -v`
Expected: all green.

**Step 2: Manual smoke (real ComfyUI)** — checklist for the user:

1. Symlink/clone repo into `ComfyUI/custom_nodes/`, `pip install -r requirements.txt`, restart ComfyUI. Confirm the startup log prints the MCP bridge URL.
2. `claude mcp add --transport http comfy http://127.0.0.1:9188/mcp`; in Claude Code run `/mcp` and confirm `comfy_pull/push/list_channels/run_workflow/get_result` appear.
3. Graph: `Load Image → Agent Emit (ch=in)`. Queue. In Claude: `comfy_pull("in")` → returns the image path; open it.
4. In Claude: `comfy_push("out", text="hi", image_path="<edited>.png")`. Graph: `Agent Receive (ch=out, wait_seconds=30) → Preview/Save`. Queue → confirm text + image arrive.
5. Save an API-format workflow to `workflows/txt2img.json` with an `Agent Receive(ch=prompt)` feeding CLIP and an `Agent Emit(ch=render)`. In Claude: `comfy_push("prompt","a red fox")` → `comfy_run_workflow("txt2img", wait=true)` → `comfy_pull("render")`. Confirm the render returns.

**Step 3: Final commit / tag**

```bash
git add -A && git commit -m "test: full suite green + manual verification notes" || true
```

---

## Risks & open validations

- **`mcp` SDK surface** (`FastMCP` tool registration introspection, streamable-http run, proxy helper) varies by version — pin the validated version in `requirements.txt`; Task 10 note flags the one version-sensitive spot.
- **Codex HTTP MCP support** — verify; fall back to the Task 12 stdio shim only if needed.
- **`comfy_run_workflow` poll loop** is a simple bounded poll; if runs exceed ~60s, raise the bound or switch to the ComfyUI websocket `executed` event. Out of scope for v1 unless needed.
- **Single Receive per channel** — the consume-once model means two Receive nodes on one channel compete; documented, acceptable for v1.
