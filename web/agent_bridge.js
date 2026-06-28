import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// Agent Receive sends "agent-bridge-stop-autoqueue" when it times out with no
// new message. Only the browser can toggle Auto Queue, so we do it here.
// ComfyUI's Auto-Queue control has moved between frontend versions, so this is
// best-effort across the known mechanisms.

function stopAutoQueue() {
  const tried = [];

  // 1) Legacy menu checkbox (#autoQueueCheckbox)
  try {
    const cb = document.getElementById("autoQueueCheckbox");
    if (cb && cb.checked) {
      cb.checked = false;
      cb.dispatchEvent(new Event("change", { bubbles: true }));
      tried.push("legacy-checkbox");
    }
  } catch (e) {}

  // 2) Older app.ui flag
  try {
    if (app?.ui && "autoQueueEnabled" in app.ui) {
      app.ui.autoQueueEnabled = false;
      tried.push("app.ui.autoQueueEnabled");
    }
  } catch (e) {}

  // 3) New frontend: queue-mode setting (disabled | instant | change)
  try {
    const ss = app?.extensionManager?.setting ?? app?.ui?.settings;
    if (ss?.set) {
      for (const key of ["Comfy.QueueButton.Mode", "Comfy.Queue.Mode"]) {
        try { ss.set(key, "disabled"); tried.push(`setting:${key}`); } catch (e) {}
      }
    }
  } catch (e) {}

  return tried;
}

app.registerExtension({
  name: "agent_bridge.autoqueue_stop",
  setup() {
    api.addEventListener("agent-bridge-stop-autoqueue", (event) => {
      const channel = event?.detail?.channel ?? "";
      const tried = stopAutoQueue();
      const msg = `No new message on '${channel}' — Auto Queue stopped`;
      try {
        app.extensionManager?.toast?.add?.({
          severity: "info",
          summary: "Agent Bridge",
          detail: msg,
          life: 4000,
        });
      } catch (e) {}
      console.log(`[agent-bridge] ${msg} (mechanisms: ${tried.join(", ") || "none matched"})`);
    });
  },
});
