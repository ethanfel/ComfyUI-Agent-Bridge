"""Regression: ComfyUI can import this package's `store` module under two
different identities (one for the nodes, one for the MCP server). The singleton
must be process-global so both sides share ONE store — otherwise an MCP push
never reaches the node-side Receive.
"""
import importlib.util
import sys


def _load(name):
    spec = importlib.util.spec_from_file_location(name, "src/bridge/store.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


def test_singleton_shared_across_module_identities():
    A = _load("store_identity_a")
    B = _load("store_identity_b")
    A.ChannelStore.reset()
    assert A.ChannelStore.instance() is B.ChannelStore.instance()


def test_cross_identity_push_reaches_receive():
    A = _load("store_identity_a2")
    B = _load("store_identity_b2")
    A.ChannelStore.reset()
    A.ChannelStore.instance().push("xc", text="cross")
    got = B.ChannelStore.instance().receive("xc", 0.0)
    assert got["text"] == "cross"
