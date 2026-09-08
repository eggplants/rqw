""".. include:: ../README.md"""

from __future__ import annotations

import importlib.metadata

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0"

from .client import USER_AGENT, AsyncSparqlClient, SparqlClient
from .exceptions import (
    BadQueryError,
    EndpointError,
    EndpointNotFoundError,
    ForbiddenError,
    QueryFormError,
    QuerySyntaxError,
    ResponseError,
    RqwError,
    SparqlHttpError,
    UnauthorizedError,
    UnsupportedMediaTypeError,
    UriTooLongError,
)
from .lexer import Token, TokenKind, tokenize
from .parser import Query, QuerySource, detect_form, parse, render_value
from .protocol import (
    EndpointConfig,
    GraphFormat,
    HttpMethod,
    QueryForm,
    RequestEncoding,
    ResultFormat,
    SolutionFormat,
    parse_format,
)
from .results import AskResult, GraphResult, QueryResult, RawResult, Row, SelectResult, UpdateResult
from .terms import BlankNode, Literal, QuotedTriple, Scalar, Term, Uri

__all__ = [
    "USER_AGENT",
    "AskResult",
    "AsyncSparqlClient",
    "BadQueryError",
    "BlankNode",
    "EndpointConfig",
    "EndpointError",
    "EndpointNotFoundError",
    "ForbiddenError",
    "GraphFormat",
    "GraphResult",
    "HttpMethod",
    "Literal",
    "Query",
    "QueryForm",
    "QueryFormError",
    "QueryResult",
    "QuerySource",
    "QuerySyntaxError",
    "QuotedTriple",
    "RawResult",
    "RequestEncoding",
    "ResponseError",
    "ResultFormat",
    "Row",
    "RqwError",
    "Scalar",
    "SelectResult",
    "SolutionFormat",
    "SparqlClient",
    "SparqlHttpError",
    "Term",
    "Token",
    "TokenKind",
    "UnauthorizedError",
    "UnsupportedMediaTypeError",
    "UpdateResult",
    "Uri",
    "UriTooLongError",
    "__version__",
    "detect_form",
    "parse",
    "parse_format",
    "render_value",
    "tokenize",
]
