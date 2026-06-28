from ..bridge.store import ChannelStore
from ..bridge import images, paths


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
            image_path = images.save_tensor_png(image, paths.tmp_dir())
        text_val = text if text else None
        ChannelStore.instance().emit(channel, text=text_val, image_path=image_path)
        return (text_val, image)
