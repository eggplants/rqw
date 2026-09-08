from __future__ import annotations

import pytest

from rqw.exceptions import (
    BadQueryError,
    EndpointError,
    EndpointNotFoundError,
    ForbiddenError,
    RqwError,
    SparqlHttpError,
    UnauthorizedError,
    UnsupportedMediaTypeError,
    UriTooLongError,
    raise_for_status,
)


@pytest.mark.parametrize("status", [200, 204, 302, 399])
def test_a_non_error_status_raises_nothing(status):
    assert raise_for_status(status, "http://e/") is None


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (400, BadQueryError),
        (401, UnauthorizedError),
        (403, ForbiddenError),
        (404, EndpointNotFoundError),
        (414, UriTooLongError),
        (415, UnsupportedMediaTypeError),
        (418, SparqlHttpError),
        (500, EndpointError),
        (503, EndpointError),
    ],
)
def test_each_status_maps_to_its_exception(status, expected):
    with pytest.raises(expected) as excinfo:
        raise_for_status(status, "http://e/", b"boom")
    assert type(excinfo.value) is expected
    assert isinstance(excinfo.value, RqwError)


def test_the_exception_carries_the_response_body():
    with pytest.raises(BadQueryError) as excinfo:
        raise_for_status(400, "http://e/", b"Parse error at line 1")
    error = excinfo.value
    assert error.status == 400
    assert error.url == "http://e/"
    assert error.body == b"Parse error at line 1"
    assert str(error) == "http://e/ returned HTTP 400: Parse error at line 1"


def test_an_empty_body_leaves_the_message_bare():
    assert str(SparqlHttpError(418, "http://e/")) == "http://e/ returned HTTP 418"


def test_a_long_body_is_cut_down():
    error = SparqlHttpError(500, "http://e/", b"x" * 5000)
    assert len(str(error)) < 600
    assert error.body == b"x" * 5000
