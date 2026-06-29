import os
import traceback

from ..bridge.store import ChannelStore
from ..bridge import images
from ..bridge.logutil import log, short


class AgentReceive:
    """Receive text/image pushed by an external agent on a named channel."""

    CATEGORY = "agents/bridge"
    FUNCTION = "run"
    RETURN_TYPES = ("STRING", "IMAGE", "INT")
    RETURN_NAMES = ("text", "image", "seed")

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
    def _load_image(image_path, channel):
        """Load the sender's image path, logging clearly if it's unusable."""
        if not image_path:
            return images.empty_image()
        if not isinstance(image_path, str):
            log(f"Agent Receive[{channel}] ⚠ SENDER PROBLEM: image_path is "
                f"{type(image_path).__name__}, not a path -> blank image")
            return images.empty_image()
        if not os.path.exists(image_path):
            log(f"Agent Receive[{channel}] ⚠ SENDER PROBLEM: image_path does not "
                f"exist on this host: {image_path!r} -> blank image. The sender "
                "pushed a path this ComfyUI can't open (shared-folder / "
                "COMFY_BRIDGE_TMP_PUBLIC mapping?).")
            return images.empty_image()
        try:
            img = images.load_png_tensor(image_path)
            log(f"Agent Receive[{channel}] image loaded: {image_path!r} "
                f"shape={tuple(img.shape)}")
            return img
        except Exception as exc:
            log(f"Agent Receive[{channel}] ⚠ SENDER PROBLEM: failed to load image "
                f"{image_path!r}: {type(exc).__name__}: {exc} -> blank image")
            log(traceback.format_exc())
            return images.empty_image()

    def _format(self, payload, channel, source):
        text = payload["text"] if payload["text"] is not None else ""
        raw_seed = payload.get("seed")
        if raw_seed is not None and not isinstance(raw_seed, int):
            log(f"Agent Receive[{channel}] ⚠ SENDER PROBLEM: seed is "
                f"{type(raw_seed).__name__}={raw_seed!r}, not an int -> using 0")
        seed = raw_seed if isinstance(raw_seed, int) else 0
        image = self._load_image(payload.get("image_path"), channel)
        log(f"Agent Receive[{channel}] OUTPUT ({source}): text={short(text)!r} "
            f"(len={len(text)}) image_shape={tuple(image.shape)} seed={seed}")
        return (text, image, seed)

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
        log(f"Agent Receive[{channel}] waiting up to {wait_seconds}s "
            f"(keep_last={keep_last}, stop_on_timeout={stop_on_timeout})")
        store = ChannelStore.instance()
        got = store.receive(channel, wait_seconds=wait_seconds,
                            should_abort=self._interrupt_check)
        if got["turn"] > 0:
            # a fresh message arrived
            log(f"Agent Receive[{channel}] GOT message turn={got['turn']}")
            return self._format(got, channel, "fresh")
        # timeout: nothing new within wait_seconds
        log(f"Agent Receive[{channel}] timeout — no new message in {wait_seconds}s")
        if stop_on_timeout:
            self._signal_stop_autoqueue(channel)
        if keep_last:
            last = store.peek(channel)
            if last["turn"] > 0:
                log(f"Agent Receive[{channel}] keep_last -> replaying turn={last['turn']}")
                return self._format(last, channel, "keep_last")
        log(f"Agent Receive[{channel}] returning empty")
        return ("", images.empty_image(), 0)
