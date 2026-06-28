from ..bridge.store import ChannelStore
from ..bridge import images


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
                "keep_last": ("BOOLEAN", {"default": True}),
                "stop_on_timeout": ("BOOLEAN", {"default": True}),
            },
        }

    @classmethod
    def IS_CHANGED(cls, *args, **kwargs):
        # The agent pushes new messages independently of this node's inputs, so
        # ComfyUI must re-run it on every queue rather than serve a cached output.
        # NaN != NaN, so the node is always considered "changed" (always dirty).
        return float("nan")

    @staticmethod
    def _format(payload):
        text = payload["text"] if payload["text"] is not None else ""
        if payload["image_path"]:
            image = images.load_png_tensor(payload["image_path"])
        else:
            image = images.empty_image()
        return (text, image)

    @staticmethod
    def _interrupt_check():
        # Raises ComfyUI's InterruptProcessingException when the user hits Cancel,
        # so the blocking wait can be aborted. No-op outside ComfyUI (tests).
        try:
            from comfy import model_management as mm
            check = mm.throw_exception_if_processing_interrupted
        except (ImportError, AttributeError):
            return
        check()

    @staticmethod
    def _signal_stop_autoqueue(channel):
        # Only the browser can toggle Auto Queue, so ask the frontend to stop.
        # Lazy import + best-effort: ComfyUI's `server` isn't available in tests.
        try:
            from server import PromptServer
            PromptServer.instance.send_sync(
                "agent-bridge-stop-autoqueue", {"channel": channel})
        except Exception:
            pass

    def run(self, channel="main", wait_seconds=30.0, keep_last=True,
            stop_on_timeout=True):
        store = ChannelStore.instance()
        got = store.receive(channel, wait_seconds=wait_seconds,
                            should_abort=self._interrupt_check)
        if got["turn"] > 0:
            # a fresh message arrived
            return self._format(got)
        # timeout: nothing new within wait_seconds
        if stop_on_timeout:
            self._signal_stop_autoqueue(channel)
        if keep_last:
            last = store.peek(channel)
            if last["turn"] > 0:
                return self._format(last)
        return ("", images.empty_image())
