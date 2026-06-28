# ComfyUI-Nodes-Agents

In-graph **Agent Emit** / **Agent Receive** nodes on named channels, plus an
in-process **MCP server**, so an externally-running coding agent (Claude Code /
Codex) can exchange text and images with a ComfyUI workflow mid-pipeline and
trigger runs.

## How it works

A thread-safe singleton `ChannelStore` holds, per named channel, two **FIFO
queues**: an **inbox** (graph -> agent) and an **outbox** (agent -> graph). Every
emit/push is kept and delivered oldest-first — nothing is overwritten or dropped.
ComfyUI nodes touch the store directly (same process). A `FastMCP`
streamable-HTTP server runs in a daemon thread on a side port; its tools touch
the same singleton. Text/seed cross inline; images cross by file path through a
temp dir.

- **inbox** = graph -> agent: `Agent Emit` enqueues, `comfy_pull` dequeues (oldest first).
- **outbox** = agent -> graph: `comfy_push` enqueues, `Agent Receive` dequeues (oldest first).
- Each message is delivered exactly once; when a queue is drained, reads return empty.

## Install

Clone (or symlink) this repo into your ComfyUI `custom_nodes` directory and
install the dependency, then restart ComfyUI:

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/ethanfel/ComfyUI-Agent-Bridge
pip install -r ComfyUI-Agent-Bridge/requirements.txt   # mcp>=1.2.0 (validated on 1.28.1)
```

(The `custom_nodes` subdirectory name is arbitrary — ComfyUI loads the package regardless.)

On startup ComfyUI loads the package and the bridge logs its URL:

```
[comfyui-nodes-agents] MCP bridge on http://127.0.0.1:9188/mcp  (claude mcp add --transport http comfy http://127.0.0.1:9188/mcp)
```

The bridge autostarts from `__init__.py` and is wrapped in try/except, so a
bridge failure never blocks ComfyUI from loading the nodes.

## The two nodes (category `agents/bridge`)

**Agent Emit (-> agent)** — send from the graph to the agent.
- Inputs: `channel` (STRING, default `main`); optional `text` (multiline STRING),
  `image` (IMAGE), `seed` (INT, socket input — e.g. wire a KSampler seed).
- Enqueues text/image/seed onto the channel inbox (image is saved to a PNG in the
  temp dir and the path is stored). Passes `(text, image, seed)` straight through
  as outputs, so you can wire it inline. Multiple emits queue up (FIFO).

**Agent Receive (<- agent)** — receive from the agent into the graph.
- Inputs: `channel` (STRING, default `main`); `wait_seconds` (FLOAT, default
  `30.0`, max `86400`); `keep_last` (BOOLEAN, default `true`); `stop_on_timeout`
  (BOOLEAN, default `true`).
- Outputs `(text, image, seed)` — `seed` (INT) is whatever the agent passed to
  `comfy_push(seed=...)`, or `0` if none. Wire it into a KSampler, etc.
- Dequeues the **oldest** unread `comfy_push` on the channel (FIFO), blocking up
  to `wait_seconds` for one to arrive. Every push is delivered exactly once and in
  order, so in Auto Queue successive runs drain the queue message-by-message
  (push A,B,C → receive A, then B, then C). No drops, no replays.
- **`keep_last`** — on timeout (no new message), output the *last* message again
  instead of blanking. Great for Auto Queue so the display holds steady between
  evals. Off → returns `""` + a 64x64 black placeholder on timeout.
- **`stop_on_timeout`** — on timeout, signal the ComfyUI frontend to switch
  **Auto Queue off**, so the loop halts when the message stream goes quiet
  instead of spinning. (Handled by the bundled `web/agent_bridge.js`; best-effort
  across ComfyUI frontend versions.)

> One consumer per channel: each queued message goes to exactly one reader, so two
> `Agent Receive` nodes on the same channel split the queue between them. Use
> distinct channel names unless you deliberately want that fan-out.

> `wait_seconds` blocks a ComfyUI execution worker for its whole duration.
> Outside interactive use, keep it modest (seconds, not hours) so you don't tie
> up a worker waiting on an agent.

## Connecting an agent

The bridge speaks **MCP over streamable HTTP** at `http://127.0.0.1:9188/mcp`.

### Codex (plugin — recommended)

This repo ships as a **Codex plugin**. Point Codex at the repo as a marketplace,
then install the plugin; Codex auto-registers the `comfy` MCP server (HTTP, no
auth) and the `comfyui-bridge` skill. Verified on Codex CLI 0.142.3:

```bash
# from GitHub:
codex plugin marketplace add ethanfel/ComfyUI-Agent-Bridge
# ...or from a local clone:
codex plugin marketplace add /path/to/ComfyUI-Agent-Bridge

codex plugin add comfyui-agents@comfyui-agents
```

Confirm registration:

```bash
codex mcp get comfy
# transport: streamable_http
# url: http://127.0.0.1:9188/mcp
```

The plugin only *declares* the HTTP server URL, so ComfyUI (and the bridge) must
be running for the tools to connect.

### Codex (single MCP server, no plugin)

If you'd rather not install the plugin, add just the MCP server:

```bash
codex mcp add comfy --url http://127.0.0.1:9188/mcp
```

This writes a streamable-HTTP entry equivalent to:

```toml
[mcp_servers.comfy]
url = "http://127.0.0.1:9188/mcp"
```

**Codex (stdio only):** if your Codex build can *only* speak stdio MCP, point it
at `scripts/codex_stdio_shim.py` — a real stdio<->HTTP MCP proxy that connects
to the same bridge URL and forwards tool calls. Equivalent to
`codex mcp add comfy --env COMFY_BRIDGE_URL=http://127.0.0.1:9188/mcp -- python /abs/path/scripts/codex_stdio_shim.py`:

```toml
[mcp_servers.comfy]
command = "python"
args = ["/abs/path/ComfyUI-Nodes-Agents/scripts/codex_stdio_shim.py"]
env = { COMFY_BRIDGE_URL = "http://127.0.0.1:9188/mcp" }
```

The shim requires ComfyUI (and the bridge) to be running; if it can't reach the
HTTP bridge it exits non-zero with a clear stderr message so Codex surfaces the
error. Use an absolute path to the shim.

### Claude Code (HTTP)

```bash
claude mcp add --transport http comfy http://127.0.0.1:9188/mcp
```

Then in Claude Code, `/mcp` should list the five tools.

## Running ComfyUI in Docker / on another host

The bridge binds `127.0.0.1` by default, reachable only from the same host (inside
the container). To reach it from an agent on another machine:

1. **Bind all interfaces** — set `COMFY_BRIDGE_MCP_HOST=0.0.0.0` in the container.
2. **Publish the port** — `-p 9188:9188` (or `ports: ["9188:9188"]` in compose).
3. **Point the agent at the server IP**, not localhost:
   ```bash
   claude mcp add --transport http comfy http://192.168.1.12:9188/mcp
   codex  mcp add comfy --url        http://192.168.1.12:9188/mcp
   ```
   For the Codex *plugin*, edit `.codex-plugin/mcp.json`'s `url` to the server IP
   (or just use `codex mcp add` above).

`COMFY_BASE_URL` stays `http://127.0.0.1:8188` — the bridge runs *inside* the
ComfyUI container and reaches ComfyUI over the container's own localhost.

**Images across hosts.** Images cross **by file path**. By default the bridge
writes them into ComfyUI's **output directory** (`output/agent_bridge/`), which in
a typical setup is a shared mount visible at the *same path* to both ComfyUI and
the agent — so paths resolve on both sides with **no configuration**.

If your container mounts that folder at a **different internal path** than the
agent sees, set both:

- `COMFY_BRIDGE_TMP` — dir the bridge writes, container-side (e.g. `/ComfyUI/output/agent_bridge`)
- `COMFY_BRIDGE_TMP_PUBLIC` — the path the agent sees for it (e.g. `/media/unraid/comfyui/output/agent_bridge`)

`comfy_pull` then advertises the agent-visible path and `comfy_push` translates it
back to the container path before `Agent Receive` loads it. Text needs none of
this — it's inline.

> **Security:** binding `0.0.0.0` exposes the bridge — including `comfy_run_workflow`
> (runs saved workflows) and file-path reads — to your LAN with no authentication.
> Keep it on a trusted network or firewall the port.

## MCP tools

| Tool | Direction | Purpose |
| --- | --- | --- |
| `comfy_pull(channel="main")` | graph -> agent | Dequeue the oldest emitted message (FIFO; returns `{turn, text, image_path, seed}`, empty when drained). |
| `comfy_push(channel="main", text=None, image_path=None, seed=None)` | agent -> graph | Send text/image/seed to the channel's `Agent Receive` node. |
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
| `COMFY_BRIDGE_MCP_HOST` | `127.0.0.1` | Interface the MCP bridge binds. Set `0.0.0.0` to reach it from another host (e.g. ComfyUI in Docker). See [Running ComfyUI in Docker](#running-comfyui-in-docker--on-another-host). |
| `COMFY_BRIDGE_MCP_PORT` | `9188` | Port the MCP bridge binds (use `0` for an ephemeral port, e.g. in tests). |
| `COMFY_BRIDGE_TMP` | ComfyUI `output/agent_bridge` | Dir where `Agent Emit` writes image PNGs. Defaults to ComfyUI's output dir (a shared, same-path mount in typical setups); falls back to `.comfy_bridge_tmp` outside ComfyUI. |
| `COMFY_BRIDGE_TMP_PUBLIC` | _(unset)_ | If the container mounts the temp dir at a different path than the agent sees, the prefix the agent should see. `comfy_pull` advertises it; `comfy_push` translates back. See [Docker](#running-comfyui-in-docker--on-another-host). |
| `COMFY_BRIDGE_TMP_TTL` | `3600` | Age (seconds) after which `save_tensor_png` reaps old `img_*.png` temp files. |
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
