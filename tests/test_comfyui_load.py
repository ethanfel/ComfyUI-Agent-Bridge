"""Regression: the package must import the way ComfyUI loads custom nodes —
as a package via spec_from_file_location, from a CWD where the repo root is NOT
on sys.path (so absolute `from src...` imports would fail). Run in a subprocess
so the parallel module tree / server thread don't touch the test interpreter.
"""
import os
import subprocess
import sys
import textwrap


def test_loads_like_comfyui(tmp_path):
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    code = textwrap.dedent(
        f"""
        import importlib.util, os, sys
        repo = {repo!r}
        name = "ComfyUI_Agent_Bridge_under_test"
        spec = importlib.util.spec_from_file_location(
            name, os.path.join(repo, "__init__.py"),
            submodule_search_locations=[repo])
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        assert "AgentEmit" in mod.NODE_CLASS_MAPPINGS, "AgentEmit missing"
        assert "AgentReceive" in mod.NODE_CLASS_MAPPINGS, "AgentReceive missing"
        # Relative imports must not leak a generic top-level `src` (collision risk
        # with other custom nodes that also ship a `src` package).
        assert "src" not in sys.modules, "top-level `src` leaked onto sys.modules"
        print("COMFY_LOAD_OK")
        """
    )
    env = dict(os.environ, COMFY_BRIDGE_MCP_PORT="0")
    env.pop("PYTHONPATH", None)  # ensure repo isn't importable as top-level `src`
    r = subprocess.run([sys.executable, "-c", code], cwd=str(tmp_path),
                       env=env, capture_output=True, text=True)
    assert r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}"
    assert "COMFY_LOAD_OK" in r.stdout
