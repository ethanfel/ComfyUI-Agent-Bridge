"""Age-based GC of temp PNGs: save_tensor_png reaps img_*.png older than the
TTL (env COMFY_BRIDGE_TMP_TTL, default 3600s) while keeping recent files and
the file it just wrote."""
import os
import time

import torch

from src.bridge import images


def _tensor():
    return torch.zeros(1, 4, 4, 3)


def test_old_temp_image_is_reaped(tmp_path, monkeypatch):
    monkeypatch.setenv("COMFY_BRIDGE_TMP_TTL", "3600")
    old = tmp_path / "img_old.png"
    old.write_bytes(b"stale")
    backdated = time.time() - 7200  # 2h old, past the 1h TTL
    os.utime(old, (backdated, backdated))

    new_path = images.save_tensor_png(_tensor(), str(tmp_path))

    assert not old.exists(), "stale temp image should have been reaped"
    assert os.path.exists(new_path), "freshly written image must survive"


def test_recent_temp_image_is_kept(tmp_path, monkeypatch):
    monkeypatch.setenv("COMFY_BRIDGE_TMP_TTL", "3600")
    recent = tmp_path / "img_recent.png"
    recent.write_bytes(b"fresh")
    recent_mtime = time.time() - 60  # 1 min old, within TTL
    os.utime(recent, (recent_mtime, recent_mtime))

    new_path = images.save_tensor_png(_tensor(), str(tmp_path))

    assert recent.exists(), "recent temp image within TTL must be kept"
    assert os.path.exists(new_path)
