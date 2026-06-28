import os
import numpy as np
import torch
from src.bridge import images

def test_save_then_load_roundtrip(tmp_path):
    # ComfyUI IMAGE tensor: [B, H, W, C] float 0..1
    t = torch.zeros(1, 8, 8, 3)
    t[0, 0, 0, 0] = 1.0  # red corner
    path = images.save_tensor_png(t, str(tmp_path))
    assert os.path.exists(path)
    back = images.load_png_tensor(path)
    assert back.shape == (1, 8, 8, 3)
    assert back[0, 0, 0, 0].item() > 0.9  # red preserved

def test_empty_image_shape():
    e = images.empty_image()
    assert e.ndim == 4 and e.shape[0] == 1 and e.shape[3] == 3
