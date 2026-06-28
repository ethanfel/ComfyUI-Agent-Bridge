---
name: comfyui-bridge
description: Use when exchanging text or images with a running ComfyUI graph or triggering a ComfyUI workflow run from the agent. Trigger terms - ComfyUI, comfy_pull, comfy_push, comfy_run_workflow, named channel, inbox, outbox, render a prompt, edit the graph's image.
license: MIT
---

# ComfyUI Agent Bridge

Connects you to a running ComfyUI graph through the `comfy` MCP server
(HTTP at `http://127.0.0.1:9188/mcp`). You exchange text and images with the
graph on **named channels** and can trigger saved workflow runs.

ComfyUI must be running with the `ComfyUI-Nodes-Agents` custom node installed,
or the tools below will fail to connect.

## Named-channel model

Each channel name (default `main`) has two directions:

- **inbox** = graph -> agent: `Agent Emit` nodes enqueue text/image/seed; you
  dequeue the oldest with `comfy_pull` (FIFO, empty when drained).
- **outbox** = agent -> graph: you enqueue with `comfy_push`; an `Agent Receive`
  node dequeues the oldest (FIFO). Every message is delivered exactly once, in
  order — nothing is overwritten or dropped.

Use distinct channel names for distinct streams (e.g. `in`, `out`, `prompt`,
`render`); two `Agent Receive` nodes on one channel split the same queue.

## The five tools

- `comfy_pull(channel="main")` -> `{turn, text, image_path}`: read what the graph
  emitted on a channel.
- `comfy_push(channel="main", text=None, image_path=None)`: send text/image to
  the graph's `Agent Receive` node on a channel.
- `comfy_list_channels()`: list active channels and their turn counters.
- `comfy_run_workflow(name, inputs=None, wait=True)`: load `workflows/<name>.json`
  (API-format export), optionally inject `inputs` keyed `"<node_id>.<field>"`
  (e.g. `{"6.text": "a red fox"}`), queue it, and (with `wait=True`) poll until
  outputs appear.
- `comfy_get_result(prompt_id)`: fetch produced images/outputs for a queued
  prompt id.

Images cross by file path: `comfy_pull` returns an `image_path` you can read;
pass a local PNG path to `comfy_push(image_path=...)`.

## The core loop

1. `comfy_push(channel, text=..., image_path=...)` — stage inputs for the graph.
2. `comfy_run_workflow(name, wait=True)` — trigger the run and wait for outputs.
3. `comfy_pull(channel)` — read the text/image the graph emitted back.

Full render round-trip: with a workflow whose `Agent Receive(channel=prompt)`
feeds the prompt and whose output goes to `Agent Emit(channel=render)`:
`comfy_push("prompt", "a red fox")` -> `comfy_run_workflow("txt2img", wait=True)`
-> `comfy_pull("render")`.
