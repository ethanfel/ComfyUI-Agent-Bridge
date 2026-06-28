import os
import uuid
import numpy as np
import torch
from PIL import Image


def save_tensor_png(tensor: torch.Tensor, out_dir: str) -> str:
    """ComfyUI IMAGE [B,H,W,C] float 0..1 -> PNG file, returns path."""
    os.makedirs(out_dir, exist_ok=True)
    if tensor.ndim == 4:
        tensor = tensor[0]
    arr = (tensor.clamp(0, 1).cpu().numpy() * 255.0).round().astype(np.uint8)
    img = Image.fromarray(arr, mode="RGB")
    path = os.path.join(out_dir, f"img_{uuid.uuid4().hex}.png")
    img.save(path)
    return path


def load_png_tensor(path: str) -> torch.Tensor:
    """PNG file -> ComfyUI IMAGE [1,H,W,C] float 0..1."""
    img = Image.open(path).convert("RGB")
    arr = np.asarray(img).astype(np.float32) / 255.0
    return torch.from_numpy(arr)[None, ...]


def empty_image() -> torch.Tensor:
    """Placeholder IMAGE output when no image is available (64x64 black)."""
    return torch.zeros(1, 64, 64, 3)
