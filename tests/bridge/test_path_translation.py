import sys
import types

from src.bridge import paths, mcp_tools
from src.bridge.store import ChannelStore


def test_tmp_dir_env_override_wins(monkeypatch):
    monkeypatch.setenv("COMFY_BRIDGE_TMP", "/explicit/dir")
    assert paths.tmp_dir() == "/explicit/dir"


def test_tmp_dir_defaults_to_comfyui_output(monkeypatch):
    monkeypatch.delenv("COMFY_BRIDGE_TMP", raising=False)
    fake = types.ModuleType("folder_paths")
    fake.get_output_directory = lambda: "/media/unraid/comfyui/output"
    monkeypatch.setitem(sys.modules, "folder_paths", fake)
    assert paths.tmp_dir() == "/media/unraid/comfyui/output/agent_bridge"


def test_tmp_dir_fallback_without_comfyui(monkeypatch):
    monkeypatch.delenv("COMFY_BRIDGE_TMP", raising=False)
    monkeypatch.setitem(sys.modules, "folder_paths", None)  # import -> ImportError
    assert paths.tmp_dir() == ".comfy_bridge_tmp"


def test_no_public_prefix_is_identity(monkeypatch):
    monkeypatch.delenv("COMFY_BRIDGE_TMP_PUBLIC", raising=False)
    monkeypatch.setenv("COMFY_BRIDGE_TMP", "/ComfyUI/output/mcp")
    p = "/ComfyUI/output/mcp/img_1.png"
    assert paths.to_public(p) == p
    assert paths.to_local(p) == p


def test_to_public_remaps_container_path(monkeypatch):
    monkeypatch.setenv("COMFY_BRIDGE_TMP", "/ComfyUI/output/mcp")
    monkeypatch.setenv("COMFY_BRIDGE_TMP_PUBLIC", "/media/unraid/comfyui/output/mcp")
    assert paths.to_public("/ComfyUI/output/mcp/img_1.png") == \
        "/media/unraid/comfyui/output/mcp/img_1.png"


def test_to_local_remaps_agent_path(monkeypatch):
    monkeypatch.setenv("COMFY_BRIDGE_TMP", "/ComfyUI/output/mcp")
    monkeypatch.setenv("COMFY_BRIDGE_TMP_PUBLIC", "/media/unraid/comfyui/output/mcp")
    assert paths.to_local("/media/unraid/comfyui/output/mcp/img_1.png") == \
        "/ComfyUI/output/mcp/img_1.png"


def test_remap_leaves_unrelated_paths_untouched(monkeypatch):
    monkeypatch.setenv("COMFY_BRIDGE_TMP", "/ComfyUI/output/mcp")
    monkeypatch.setenv("COMFY_BRIDGE_TMP_PUBLIC", "/media/unraid/comfyui/output/mcp")
    assert paths.to_public("/somewhere/else/x.png") == "/somewhere/else/x.png"


def test_roundtrip(monkeypatch):
    monkeypatch.setenv("COMFY_BRIDGE_TMP", "/ComfyUI/output/mcp")
    monkeypatch.setenv("COMFY_BRIDGE_TMP_PUBLIC", "/media/unraid/comfyui/output/mcp")
    real = "/ComfyUI/output/mcp/img_9.png"
    assert paths.to_local(paths.to_public(real)) == real


def test_comfy_pull_advertises_public_path(monkeypatch):
    monkeypatch.setenv("COMFY_BRIDGE_TMP", "/ComfyUI/output/mcp")
    monkeypatch.setenv("COMFY_BRIDGE_TMP_PUBLIC", "/media/unraid/comfyui/output/mcp")
    # graph emitted a container-side path
    ChannelStore.instance().emit("main", image_path="/ComfyUI/output/mcp/in_0.png")
    got = mcp_tools.comfy_pull("main")
    assert got["image_path"] == "/media/unraid/comfyui/output/mcp/in_0.png"


def test_comfy_push_stores_container_path(monkeypatch):
    monkeypatch.setenv("COMFY_BRIDGE_TMP", "/ComfyUI/output/mcp")
    monkeypatch.setenv("COMFY_BRIDGE_TMP_PUBLIC", "/media/unraid/comfyui/output/mcp")
    # agent pushes the path IT sees
    mcp_tools.comfy_push("main", image_path="/media/unraid/comfyui/output/mcp/out_0.png")
    # the graph-side receive must get the container path
    stored = ChannelStore.instance().receive("main", wait_seconds=0)
    assert stored["image_path"] == "/ComfyUI/output/mcp/out_0.png"
