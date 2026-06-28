"""Image temp dir + path translation for remote/Docker setups.

By default the bridge writes images into ComfyUI's own output directory under
`agent_bridge/` (resolved at runtime via ComfyUI's `folder_paths`). That folder
is typically already a shared mount visible at the same path to both ComfyUI and
the agent, so image paths resolve on both sides with no configuration.

When ComfyUI runs in a container that mounts that folder at a *different*
internal path than the agent sees, set both env vars to bridge the two views:

  COMFY_BRIDGE_TMP         dir the bridge actually reads/writes (container-side)
  COMFY_BRIDGE_TMP_PUBLIC  prefix the agent sees for that same dir (optional)

If COMFY_BRIDGE_TMP_PUBLIC is unset, paths pass through unchanged. Both should be
absolute paths when translation is used.
"""
import os


def tmp_dir() -> str:
    env = os.environ.get("COMFY_BRIDGE_TMP")
    if env:
        return env
    try:  # inside ComfyUI: default to its output dir (a shared, same-path mount)
        import folder_paths
        return os.path.join(folder_paths.get_output_directory(), "agent_bridge")
    except Exception:  # outside ComfyUI (e.g. tests)
        return ".comfy_bridge_tmp"


def public_prefix():
    return os.environ.get("COMFY_BRIDGE_TMP_PUBLIC") or None


def _remap(path, src, dst):
    if not path or not dst:
        return path
    src_n = os.path.normpath(src)
    p_n = os.path.normpath(path)
    if p_n == src_n:
        return os.path.normpath(dst)
    if p_n.startswith(src_n + os.sep):
        return os.path.normpath(os.path.join(dst, os.path.relpath(p_n, src_n)))
    return path


def to_public(path):
    """Container temp path -> the path the agent should see (for comfy_pull)."""
    pub = public_prefix()
    return _remap(path, tmp_dir(), pub) if pub else path


def to_local(path):
    """Agent-visible path -> the container temp path (for comfy_push)."""
    pub = public_prefix()
    return _remap(path, pub, tmp_dir()) if pub else path
