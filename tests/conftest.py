from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx2
import pytest

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

SELECT_JSON = b"""{
  "head": {"vars": ["s", "n"]},
  "results": {"bindings": [
    {"s": {"type": "uri", "value": "http://example.org/a"},
     "n": {"type": "literal", "value": "1", "datatype": "http://www.w3.org/2001/XMLSchema#integer"}},
    {"s": {"type": "bnode", "value": "b0"}}
  ]}
}"""

ASK_JSON = b'{"head": {}, "boolean": true}'


class Recorder:
    """Captures every request a client sends and replays a canned response."""

    def __init__(self) -> None:
        self.requests: list[httpx2.Request] = []
        self.respond: Callable[[httpx2.Request], httpx2.Response] = lambda _: httpx2.Response(
            200,
            content=SELECT_JSON,
            headers={"content-type": "application/sparql-results+json"},
        )

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        request.read()
        self.requests.append(request)
        return self.respond(request)

    @property
    def last(self) -> httpx2.Request:
        return self.requests[-1]

    def reply(self, *, status: int = 200, content: bytes = b"", content_type: str = "text/plain") -> None:
        def respond(_: httpx2.Request) -> httpx2.Response:
            return httpx2.Response(status, content=content, headers={"content-type": content_type})

        self.respond = respond


@pytest.fixture
def recorder() -> Recorder:
    return Recorder()


@pytest.fixture
def sync_client(recorder: Recorder) -> Iterator[httpx2.Client]:
    with httpx2.Client(transport=httpx2.MockTransport(recorder.handle)) as client:
        yield client


@pytest.fixture
def async_client(recorder: Recorder) -> httpx2.AsyncClient:
    return httpx2.AsyncClient(transport=httpx2.MockTransport(recorder.handle))


@pytest.fixture
def anyio_backend() -> Any:
    return "asyncio"
