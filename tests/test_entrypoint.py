import importlib


def test_node_mappings_exported():
    mod = importlib.import_module("__init__")
    assert "AgentEmit" in mod.NODE_CLASS_MAPPINGS
    assert "AgentReceive" in mod.NODE_CLASS_MAPPINGS
    assert mod.NODE_DISPLAY_NAME_MAPPINGS["AgentEmit"]
