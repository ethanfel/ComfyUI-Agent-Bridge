import pytest
from src.bridge.store import ChannelStore

@pytest.fixture(autouse=True)
def _reset_store():
    ChannelStore.reset()
    yield
    ChannelStore.reset()
