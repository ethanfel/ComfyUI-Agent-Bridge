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
