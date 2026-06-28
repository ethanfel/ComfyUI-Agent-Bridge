from src.bridge import mcp_server


def test_resolve_bind_defaults(monkeypatch):
    monkeypatch.delenv("COMFY_BRIDGE_MCP_HOST", raising=False)
    monkeypatch.delenv("COMFY_BRIDGE_MCP_PORT", raising=False)
    assert mcp_server._resolve_bind(None, None) == ("127.0.0.1", 9188)


def test_resolve_bind_reads_env(monkeypatch):
    monkeypatch.setenv("COMFY_BRIDGE_MCP_HOST", "0.0.0.0")
    monkeypatch.setenv("COMFY_BRIDGE_MCP_PORT", "9999")
    assert mcp_server._resolve_bind(None, None) == ("0.0.0.0", 9999)


def test_resolve_bind_explicit_args_override_env(monkeypatch):
    monkeypatch.setenv("COMFY_BRIDGE_MCP_HOST", "0.0.0.0")
    monkeypatch.setenv("COMFY_BRIDGE_MCP_PORT", "9999")
    assert mcp_server._resolve_bind("127.0.0.1", 1234) == ("127.0.0.1", 1234)
