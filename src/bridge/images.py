import glob
import os
import time
import uuid
import numpy as np
import torch
from PIL import Image


def _reap_old(out_dir: str, keep: str) -> None:
    """Delete img_*.png in out_dir older than COMFY_BRIDGE_TMP_TTL (default
    3600s) so the temp dir doesn't grow forever. Never touches `keep`."""
    ttl = float(os.environ.get("COMFY_BRIDGE_TMP_TTL", "3600"))
    cutoff = time.time() - ttl
    for f in glob.glob(os.path.join(out_dir, "img_*.png")):
        if f == keep:
            continue
        try:
            if os.path.getmtime(f) < cutoff:
                os.unlink(f)
        except (FileNotFoundError, OSError):
            pass  # races / permission churn -> best-effort


def save_tensor_png(tensor: torch.Tensor, out_dir: str) -> str:
    """ComfyUI IMAGE [B,H,W,C] float 0..1 -> PNG file, returns path."""
    os.makedirs(out_dir, exist_ok=True)
    if tensor.ndim == 4:
        tensor = tensor[0]
    arr = (tensor.clamp(0, 1).cpu().numpy() * 255.0).round().astype(np.uint8)
    img = Image.fromarray(arr)  # arr shape (H,W,3) already implies RGB
    path = os.path.join(out_dir, f"img_{uuid.uuid4().hex}.png")
    img.save(path)
    _reap_old(out_dir, keep=path)
    return path


def load_png_tensor(path: str) -> torch.Tensor:
    """PNG file -> ComfyUI IMAGE [1,H,W,C] float 0..1."""
    img = Image.open(path).convert("RGB")
    arr = np.asarray(img).astype(np.float32) / 255.0
    return torch.from_numpy(arr)[None, ...]


def empty_image() -> torch.Tensor:
    """Placeholder IMAGE output when no image is available (64x64 black)."""
    return torch.zeros(1, 64, 64, 3)
