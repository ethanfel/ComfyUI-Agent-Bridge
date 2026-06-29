#!/usr/bin/env bash
# console_relay.sh — interactive launcher for console_relay.py
#
# Run this on the machine where your console/tmux lives. It checks prereqs,
# lets you pick the target tmux pane from a menu, confirms the bridge channel
# and URL, then starts relaying: each message an `Agent Emit` node writes to the
# channel gets typed into the chosen pane.
#
# Env overrides (skip the matching prompt): COMFY_BRIDGE_URL, CHANNEL, TARGET,
# POLL, PYTHON.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PYTHON:-python3}"
URL="${COMFY_BRIDGE_URL:-http://127.0.0.1:9188/mcp}"
CHANNEL="${CHANNEL:-console}"
POLL="${POLL:-1.0}"

# --- prereqs ---
command -v tmux >/dev/null 2>&1 || { echo "error: tmux not found on PATH." >&2; exit 1; }
if ! "$PY" -c 'import mcp' >/dev/null 2>&1; then
  echo "Python package 'mcp' is missing for: $PY"
  read -rp "Install it now (pip install 'mcp>=1.2.0')? [y/N] " a
  if [[ "${a:-}" == [yY]* ]]; then "$PY" -m pip install "mcp>=1.2.0";
  else echo "Install mcp and re-run."; exit 1; fi
fi

# --- pick the target pane (unless TARGET is preset) ---
TARGET="${TARGET:-}"
if [[ -z "$TARGET" ]]; then
  mapfile -t PANES < <(tmux list-panes -a \
      -F '#{session_name}:#{window_index}.#{pane_index}  [#{pane_current_command}]  #{pane_title}')
  if [[ ${#PANES[@]} -eq 0 ]]; then
    echo "No tmux panes found — start your console inside tmux first." >&2; exit 1
  fi
  echo "Select the target console pane:"
  select choice in "${PANES[@]}"; do
    [[ -n "${choice:-}" ]] && break
  done
  TARGET="${choice%% *}"   # first field is session:window.pane
fi

# --- confirm settings ---
read -rp "Bridge URL [$URL]: " x; URL="${x:-$URL}"
read -rp "Channel [$CHANNEL]: " x; CHANNEL="${x:-$CHANNEL}"
read -rp "Press Enter to submit each message? [Y/n] " x
SUBMIT=(); [[ "${x:-}" == [nN]* ]] && SUBMIT=(--no-submit)

echo
echo "Relaying  channel='$CHANNEL'  $URL  ->  tmux '$TARGET'  (Ctrl-C to stop)"
exec "$PY" "$HERE/console_relay.py" \
    --target "$TARGET" --channel "$CHANNEL" --url "$URL" --poll "$POLL" "${SUBMIT[@]}"
