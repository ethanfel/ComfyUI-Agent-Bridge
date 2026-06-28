# ComfyUI Agent Bridge — Design

**Date:** 2026-06-28
**Status:** Approved (design)
**Package:** `ComfyUI-Nodes-Agents`

## Problem

Let a coding agent (Claude Code / Codex) running in the user's own terminal exchange
**text and images** with a ComfyUI workflow, at arbitrary points in the graph, and
optionally trigger workflow runs — without ComfyUI having to own/spawn the agent.

## Prior art (why this is worth building)

A web search (2026-06-28) showed the **control plane is already solved** but the
**in-graph data plane is not**:

| Project | Provides | In-graph channel nodes? |
|---|---|---|
| [artokun/comfyui-mcp](https://github.com/artokun/comfyui-mcp) | 108 MCP tools: generate, run/edit workflows, model/node mgmt. Claude + Codex. stdio default, HTTP opt-in. | No — control-plane only |
| [Comfy-Pilot](https://github.com/ConstantineB6/Comfy-Pilot) | MCP (`edit_graph`/`run`/`view_image`) + embedded xterm.js terminal. stdio. | No |
| [Acly/comfyui-tooling-nodes](https://github.com/Acly/comfyui-tooling-nodes) | In-graph image/mask I/O over WebSocket/base64 (ComfyUI as backend). | Partial — no channels, no MCP, no agent |

**Gap filled by this project:** in-graph `Agent Emit` / `Agent Receive` nodes on
**named channels** that let an externally-running agent inject/extract **text + image
mid-pipeline** via MCP `pull`/`push`. No existing tool combines in-graph nodes +
named channels + MCP agent I/O.

## Scope (standalone-lean)

**Build:**
- In-graph nodes: `Agent Emit`, `Agent Receive`.
- In-process MCP server (HTTP/streamable) hosted inside ComfyUI exposing:
  - `comfy_pull(channel)` → `{turn, text, image_path|null}`
  - `comfy_push(channel, text?, image_path?)` → delivers to outbox, bumps turn
  - `comfy_list_channels()` → channel names + state
  - `comfy_run_workflow(name, inputs?, wait?)` — **thin**: load saved workflow JSON,
    POST to `/prompt`, optionally block for outputs
  - `comfy_get_result(run_id)` → produced images/text from history

**Do NOT build (defer to artokun/comfyui-mcp for power users):** model management,
graph editing, custom-node install, the full 100+ tool control surface.

**Out of scope entirely:** owning/spawning the agent, PTY/TUI scraping, a chat
widget, permission handling, session/resume/cwd management — all of that is the
user's own terminal. `comfy_notify` (UI toast) is a possible later stretch.

## Architecture

```
┌─ ComfyUI Graph ─────────────────────────────────────────┐
│  [Agent Emit ch=X]  ... pipeline ...  [Agent Receive ch=Y]│
└───────────────┬─────────────────────────────────────────┘
                │ in-process calls
┌───────────────▼─────────────────────────────────────────┐
│  ChannelStore (singleton, thread-safe)                   │
│   per channel: inbox · outbox · monotonic turn · events  │
│   images written to bridge temp dir, passed BY PATH       │
└───────────────┬───────────────────────┬─────────────────┘
                │                        │
        MCP tool handlers          /prompt + /history (run_workflow)
                │
┌───────────────▼─────────────────────────────────────────┐
│  In-process HTTP/streamable MCP server                   │
│   mounted on ComfyUI PromptServer (e.g. /comfy-bridge/mcp)│
└───────────────┬─────────────────────────────────────────┘
                │ HTTP MCP
┌───────────────▼─────────────────────────────────────────┐
│  Agent in the user's terminal (claude / codex)           │
│   user owns folder, session/resume, permissions           │
└──────────────────────────────────────────────────────────┘
```

### Components

1. **`ChannelStore` (singleton, thread-safe).** Dict keyed by channel name. Each
   channel has an `inbox` (graph→agent), `outbox` (agent→graph), and a monotonic
   `turn` counter. Backed by locks + asyncio `Event`s so `Agent Receive` can block
   for a *fresher* turn. Images materialized to a bridge temp dir and referenced by
   path; text inline. Temp images garbage-collected by age.

2. **`Agent Emit` node.** Inputs: `IMAGE?`, `STRING?` (text), `channel`. On run:
   write payload to the channel inbox (image → temp PNG path). Optional passthrough
   outputs so it can sit inline.

3. **`Agent Receive` node.** Inputs: `channel`, `wait_seconds`. Outputs: `STRING`,
   `IMAGE`. `wait_seconds=0` → return latest outbox value immediately (or empty);
   `>0` → block for a result with `turn` newer than last seen, up to timeout, else
   return empty/passthrough. **Never deadlocks the graph.**

4. **MCP server (HTTP/streamable, in-process).** Mounted on ComfyUI's `PromptServer`.
   Handlers read/write the same `ChannelStore`. Connect once:
   `claude mcp add --transport http comfy http://127.0.0.1:8188/comfy-bridge/mcp`.
   **Risk:** if the user's Codex build is stdio-only for MCP, ship a ~30-line
   stdio→HTTP shim Codex can spawn. Verify both at build time.

5. **`run_workflow` (thin).** Saved workflow API-format JSON in a known dir. Load,
   (optionally) inject `inputs`, POST to `/prompt`. Channels double as the parameter
   mechanism: agent `comfy_push`es to channels that feed `Agent Receive` nodes inside
   the workflow; `Agent Emit` nodes inside it push results to the outbox. With
   `wait=true`, block for outputs via history/websocket.

### The core loop

```
agent: comfy_push("a red fox", channel="prompt")
agent: comfy_run_workflow("txt2img", wait=true)
         └─ [Agent Receive ch=prompt] → CLIP → KSampler → [Agent Emit ch=out]
agent: comfy_pull(channel="out")  → rendered image
```

## Data formats

- **Text:** inline UTF-8 strings.
- **Images graph→agent:** ComfyUI tensor → PNG in bridge temp dir → path returned by
  `comfy_pull` (so the agent can open/edit with its own file tools).
- **Images agent→graph:** agent passes a file path to `comfy_push`; `Agent Receive`
  loads it back into a tensor.

## Error handling

- `Agent Receive` timeout → return empty/passthrough; graph never deadlocks.
- `comfy_run_workflow`: missing workflow / queue error / failed run → structured error
  back to the agent.
- `comfy_pull` on empty/unknown channel → empty result (not an error).
- Concurrency: `ChannelStore` guarded for node-thread + asyncio-loop access.
- Temp images garbage-collected by age to avoid unbounded growth.

## Testing

- **Unit:** `ChannelStore` push/pull/turn semantics; `wait_seconds` block/timeout.
- **Handlers:** MCP tools against a fake store.
- **Nodes:** `Agent Emit` / `Agent Receive` `execute()` with a mocked store.
- **Integration:** boot the HTTP MCP server, drive `pull`/`push`/`run_workflow` with a
  mock MCP client against a stub queue.
- **Manual:** real Claude Code via `claude mcp add` running a real txt2img workflow.

## Project layout

```
__init__.py                 # NODE_CLASS_MAPPINGS, WEB_DIRECTORY, mounts MCP routes + store
pyproject.toml
src/bridge/  store.py · mcp_server.py · workflows.py · images.py
src/nodes/   emit.py · receive.py
web/         bridge.js      # optional: shows bridge URL + "copy mcp add" button
tests/
docs/plans/2026-06-28-comfyui-agent-bridge-design.md
```

## Decisions log

- Bridge model (agent runs externally), **not** a PTY-owned terminal node — avoids
  TUI scraping, lifecycle, permissions, chat-widget complexity.
- Transport: **MCP**, hosted **HTTP/in-process** in ComfyUI (shared store, no second
  hop). Codex stdio-shim fallback if needed.
- Named **channels** (replaces session_id); independent conversations = independent
  channels.
- `wait_seconds` on `Agent Receive` covers both blocking and non-blocking turns.
- Images passed **by path**; text inline.
- **Standalone-lean** scope: don't reinvent the 108-tool control surface.
