import asyncio
from src.bridge import workflows

class FakeResp:
    def __init__(self, payload): self._payload = payload
    async def json(self): return self._payload
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False

class FakeSession:
    def __init__(self, prompt_resp, history_resp):
        self._prompt_resp = prompt_resp
        self._history_resp = history_resp
        self.posted = None
    def post(self, url, json=None):
        self.posted = (url, json)
        return FakeResp(self._prompt_resp)
    def get(self, url):
        return FakeResp(self._history_resp)
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False

def test_submit_prompt_posts_and_returns_id():
    session = FakeSession({"prompt_id": "abc123"}, {})
    wf = {"3": {"class_type": "X", "inputs": {}}}
    pid = asyncio.run(workflows.submit_prompt(wf, base_url="http://h:8188", session=session))
    assert pid == "abc123"
    url, body = session.posted
    assert url == "http://h:8188/prompt"
    assert body["prompt"] == wf

def test_fetch_result_extracts_images():
    history = {"abc": {"outputs": {"9": {"images": [
        {"filename": "ComfyUI_0001.png", "subfolder": "", "type": "output"}]}}}}
    session = FakeSession({}, history)
    res = asyncio.run(workflows.fetch_result("abc", base_url="http://h:8188", session=session))
    assert res["images"][0]["filename"] == "ComfyUI_0001.png"
