# ComfyUI-Nodes-Agents

In-graph **Agent Emit** / **Agent Receive** nodes on named channels, plus an
in-process **MCP server**, so an externally-running coding agent (Claude Code /
Codex) can exchange text and images with a ComfyUI workflow mid-pipeline and
trigger runs.

## How it works

A thread-safe singleton `ChannelStore` holds, per named channel, an **inbox**
(graph -> agent) and an **outbox** (agent -> graph), each with a turn counter.
ComfyUI nodes touch the store directly (same process). A `FastMCP`
streamable-HTTP server runs in a daemon thread on a side port; its tools touch
the same singleton. Text crosses inline; images cross by file path through a
temp dir.

- **inbox** = graph -> agent: written by `Agent Emit`, read by the `comfy_pull` tool.
- **outbox** = agent -> graph: written by the `comfy_push` tool, read by `Agent Receive`.

## Install

Clone (or symlink) this repo into your ComfyUI `custom_nodes` directory and
install the dependency, then restart ComfyUI:

```bash
cd ComfyUI/custom_nodes
git clone <this-repo> ComfyUI-Nodes-Agents
pip install -r ComfyUI-Nodes-Agents/requirements.txt   # mcp>=1.2.0 (validated on 1.28.1)
```

On startup ComfyUI loads the package and the bridge logs its URL:

```
[comfyui-nodes-agents] MCP bridge on http://127.0.0.1:9188/mcp  (claude mcp add --transport http comfy http://127.0.0.1:9188/mcp)
```

The bridge autostarts from `__init__.py` and is wrapped in try/except, so a
bridge failure never blocks ComfyUI from loading the nodes.

## The two nodes (category `agents/bridge`)

**Agent Emit (-> agent)** — send from the graph to the agent.
- Inputs: `channel` (STRING, default `main`); optional `text` (multiline STRING),
  `image` (IMAGE).
- Writes the latest text/image to the channel inbox (image is saved to a PNG in
  the temp dir and the path is stored). Passes `(text, image)` straight through
  as outputs, so you can wire it inline.

**Agent Receive (<- agent)** — receive from the agent into the graph.
- Inputs: `channel` (STRING, default `main`); `wait_seconds` (FLOAT, default
  `30.0`, max `86400`).
- Blocks up to `wait_seconds` for a new `comfy_push` on the channel, then
  outputs `(text, image)`. On timeout/empty it returns `""` and a 64x64 black
  placeholder image. Each pushed value is **consumed once** (turn-based), so a
  second receive with no new push returns empty.

> Single Receive per channel: the consume-once model means two `Agent Receive`
> nodes on the same channel compete for pushes. Use distinct channel names.

## Connecting an agent

The bridge speaks **MCP over streamable HTTP** at `http://127.0.0.1:9188/mcp`.

**Claude Code (HTTP, recommended):**

```bash
claude mcp add --transport http comfy http://127.0.0.1:9188/mcp
```

Then in Claude Code, `/mcp` should list the five tools.

**Codex (HTTP):** add an MCP server pointing at the same URL, e.g. in
`~/.codex/config.toml`:

```toml
[mcp_servers.comfy]
url = "http://127.0.0.1:9188/mcp"
```

**Codex (stdio only):** if your Codex build cannot use HTTP MCP, point it at
`scripts/codex_stdio_shim.py`. Note: the shim is a documented scaffold and is
**not** implemented for the installed MCP SDK (mcp 1.28.1 ships no proxy
helper) — it prints guidance and exits non-zero. Prefer HTTP MCP.

## MCP tools

| Tool | Direction | Purpose |
| --- | --- | --- |
| `comfy_pull(channel="main")` | graph -> agent | Read the latest text/image emitted on a channel (returns `{turn, text, image_path}`). |
| `comfy_push(channel="main", text=None, image_path=None)` | agent -> graph | Send text/image to the channel's `Agent Receive` node. |
| `comfy_list_channels()` | — | List active channels and their turn counters. |
| `comfy_run_workflow(name, inputs=None, wait=True)` | — | Load a saved workflow from `workflows/`, optionally inject inputs, queue it via the ComfyUI API, optionally poll for results. |
| `comfy_get_result(prompt_id)` | — | Fetch produced images/outputs for a queued prompt id. |

`comfy_run_workflow` reads `workflows/<name>.json` (API-format export). `inputs`
overrides node fields keyed as `"<node_id>.<field>"`, e.g.
`{"6.text": "a red fox"}`. With `wait=True` it polls the ComfyUI `/history`
endpoint (bounded ~60s) until outputs appear.

## The core loop

1. Graph: `Load Image -> Agent Emit (channel=in)`. Queue the prompt.
2. Agent: `comfy_pull("in")` -> get the image path; inspect/edit it.
3. Agent: `comfy_push("out", text="...", image_path="<edited>.png")`.
4. Graph: `Agent Receive (channel=out, wait_seconds=30) -> Preview/Save`. Queue;
   the text + image arrive.

For a full render round-trip: save an API-format workflow to
`workflows/txt2img.json` with an `Agent Receive(channel=prompt)` feeding the
prompt and an `Agent Emit(channel=render)` on the output, then from the agent:
`comfy_push("prompt", "a red fox")` -> `comfy_run_workflow("txt2img", wait=true)`
-> `comfy_pull("render")`.

## Environment variables

| Variable | Default | Effect |
| --- | --- | --- |
| `COMFY_BRIDGE_MCP_PORT` | `9188` | Port the MCP bridge binds (use `0` for an ephemeral port, e.g. in tests). |
| `COMFY_BRIDGE_TMP` | `.comfy_bridge_tmp` | Temp dir where `Agent Emit` writes image PNGs. |
| `COMFY_BRIDGE_WORKFLOWS` | `workflows` | Dir that `comfy_run_workflow` loads `<name>.json` from. |
| `COMFY_BASE_URL` | `http://127.0.0.1:8188` | ComfyUI HTTP API base URL used by `comfy_run_workflow` / `comfy_get_result`. |

## Development

```bash
COMFY_BRIDGE_MCP_PORT=0 python -m pytest tests/ -v
```

`COMFY_BRIDGE_MCP_PORT=0` makes the entrypoint import (which autostarts the
bridge) bind an ephemeral port instead of the fixed `9188`. The test suite
includes a real MCP round-trip (`tests/bridge/test_mcp_roundtrip.py`) that boots
the streamable-HTTP server on a free port and drives it with a real MCP client.
