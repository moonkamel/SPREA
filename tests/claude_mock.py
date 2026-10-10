"""Answers of the Anthropic API for the tests: a streamed message whose text
is the given JSON, through an httpx2 transport given to api.claude."""
import json
from typing import Any, Callable, Dict, List, Optional

import httpx2

from api import claude


def sse(data: Any, stop_reason: str = "end_turn") -> bytes:
    text = json.dumps(data, ensure_ascii=False)
    events = [
        ("message_start", {"type": "message_start", "message": {
            "id": "msg_test", "type": "message", "role": "assistant", "model": claude.MODEL, "content": [],
            "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 0}}}),
        ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                           "usage": {"output_tokens": 20}}),
        ("message_stop", {"type": "message_stop"}),
    ]
    return "".join(f"event: {e}\ndata: {json.dumps(d)}\n\n" for e, d in events).encode()


class Mock:
    """Records the requests; answers with `answer(body)` (a JSON-able value),
    or an HTTP error status."""
    def __init__(self, answer: Callable[[Dict], Any], status: int = 200, stop_reason: str = "end_turn"):
        self.answer, self.status, self.stop_reason = answer, status, stop_reason
        self.requests: List[Dict] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        self.requests.append({"headers": dict(request.headers), "body": body})
        if self.status != 200:
            return httpx2.Response(self.status, json={"type": "error", "error": {"type": "overloaded_error", "message": "busy"}})
        return httpx2.Response(200, content=sse(self.answer(body), self.stop_reason),
                               headers={"content-type": "text/event-stream"})


def install(monkeypatch, answer: Callable[[Dict], Any], status: int = 200, stop_reason: str = "end_turn") -> Mock:
    mock = Mock(answer, status, stop_reason)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setattr(claude, "TRANSPORT", httpx2.MockTransport(mock))
    return mock
