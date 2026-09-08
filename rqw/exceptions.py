"""Every error `rqw` raises, plus the HTTP status to exception mapping."""

from __future__ import annotations

from typing import Final

__all__ = [
    "BadQueryError",
    "EndpointError",
    "EndpointNotFoundError",
    "ForbiddenError",
    "QueryFormError",
    "QuerySyntaxError",
    "ResponseError",
    "RqwError",
    "SparqlHttpError",
    "UnauthorizedError",
    "UnsupportedMediaTypeError",
    "UriTooLongError",
    "raise_for_status",
]

_EXCERPT = 512


class RqwError(Exception):
    """Base class of every exception raised by this package."""


class QueryFormError(RqwError, ValueError):
    """The query form could not be detected, or is not the one that was asked for."""


class QuerySyntaxError(RqwError, ValueError):
    """The query text is not well-formed SPARQL.

    Attributes:
        position: Index into the query text where the problem starts, or `None`
            when the problem is not tied to one spot.
    """

    def __init__(self, message: str, position: int | None = None) -> None:
        """Build the exception.

        Args:
            message: What is wrong.
            position: Index into the query text where the problem starts.
        """
        self.position = position
        super().__init__(message if position is None else f"{message} at position {position}")


class ResponseError(RqwError, ValueError):
    """The endpoint answered with a body that does not match the requested format."""


class SparqlHttpError(RqwError):
    """The endpoint answered with an HTTP error status.

    Attributes:
        status: The HTTP status code.
        url: The URL that was requested.
        body: The raw response body, useful because endpoints put the parser
            error of a malformed query in there.
    """

    def __init__(self, status: int, url: str, body: bytes = b"") -> None:
        """Build the exception from the failed response.

        Args:
            status: The HTTP status code.
            url: The URL that was requested.
            body: The raw response body.
        """
        self.status = status
        self.url = url
        self.body = body
        excerpt = body[:_EXCERPT].decode("utf-8", "replace").strip()
        detail = f": {excerpt}" if excerpt else ""
        super().__init__(f"{url} returned HTTP {status}{detail}")


class BadQueryError(SparqlHttpError):
    """`400 Bad Request`, usually a syntax error in the query."""


class UnauthorizedError(SparqlHttpError):
    """`401 Unauthorized`, the endpoint wants credentials rqw did not send."""


class ForbiddenError(SparqlHttpError):
    """`403 Forbidden`, the credentials are not allowed to run this operation."""


class EndpointNotFoundError(SparqlHttpError):
    """`404 Not Found`, most likely a typo in the endpoint URL."""


class UriTooLongError(SparqlHttpError):
    """`414 URI Too Long`; retry with `method=HttpMethod.POST`."""


class UnsupportedMediaTypeError(SparqlHttpError):
    """`415 Unsupported Media Type`; retry with `encoding=RequestEncoding.URL_ENCODED`."""


class EndpointError(SparqlHttpError):
    """The endpoint failed on its side, any `5xx` status."""


_BY_STATUS: Final[dict[int, type[SparqlHttpError]]] = {
    400: BadQueryError,
    401: UnauthorizedError,
    403: ForbiddenError,
    404: EndpointNotFoundError,
    414: UriTooLongError,
    415: UnsupportedMediaTypeError,
}


def raise_for_status(status: int, url: str, body: bytes = b"") -> None:
    """Turn an error status into the matching `SparqlHttpError` subclass.

    Args:
        status: The HTTP status code of the response.
        url: The URL that was requested.
        body: The raw response body, carried into the exception.

    Raises:
        SparqlHttpError: If `status` is 400 or above.
    """
    if status < 400:  # noqa: PLR2004
        return
    if (found := _BY_STATUS.get(status)) is not None:
        raise found(status, url, body)
    raise (EndpointError if status >= 500 else SparqlHttpError)(status, url, body)  # noqa: PLR2004
