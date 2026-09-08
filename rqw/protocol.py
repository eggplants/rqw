"""The SPARQL 1.1 Protocol: query forms, result formats and request shaping.

Everything in here is pure: it turns a configuration plus a query string into a
`RequestSpec`, which `rqw.client` then hands to `httpx`. Keeping it free of I/O
is what lets the sync and the async client share one implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Final
from urllib.parse import urlencode

from .exceptions import QueryFormError

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "ACCEPT",
    "GRAPH_FORMS",
    "READ_FORMS",
    "EndpointConfig",
    "GraphFormat",
    "HttpMethod",
    "QueryForm",
    "RequestEncoding",
    "RequestSpec",
    "ResultFormat",
    "SolutionFormat",
    "build_request",
    "choose_format",
    "parse_format",
]


class QueryForm(StrEnum):
    """The keyword a SPARQL query or update operation starts with."""

    SELECT = "SELECT"
    ASK = "ASK"
    CONSTRUCT = "CONSTRUCT"
    DESCRIBE = "DESCRIBE"
    INSERT = "INSERT"
    DELETE = "DELETE"
    WITH = "WITH"
    LOAD = "LOAD"
    CLEAR = "CLEAR"
    CREATE = "CREATE"
    DROP = "DROP"
    COPY = "COPY"
    MOVE = "MOVE"
    ADD = "ADD"

    @property
    def is_update(self) -> bool:
        """Whether this form mutates the store and must go to the update endpoint."""
        return self not in READ_FORMS


READ_FORMS: Final = frozenset(
    {QueryForm.SELECT, QueryForm.ASK, QueryForm.CONSTRUCT, QueryForm.DESCRIBE},
)
"""The four query forms; every other form is an update operation."""

GRAPH_FORMS: Final = frozenset({QueryForm.CONSTRUCT, QueryForm.DESCRIBE})
"""The query forms that answer with an RDF graph instead of a solution sequence."""


class SolutionFormat(StrEnum):
    """Serializations of a `SELECT`/`ASK` solution sequence."""

    JSON = "json"
    XML = "xml"
    CSV = "csv"
    TSV = "tsv"


class GraphFormat(StrEnum):
    """Serializations of the RDF graph a `CONSTRUCT`/`DESCRIBE` answers with."""

    TURTLE = "turtle"
    NTRIPLES = "ntriples"
    RDFXML = "rdfxml"
    JSONLD = "jsonld"
    N3 = "n3"
    TRIG = "trig"


type ResultFormat = SolutionFormat | GraphFormat
"""Either kind of result serialization."""


class HttpMethod(StrEnum):
    """The HTTP verb used to carry the query."""

    GET = "GET"
    POST = "POST"


class RequestEncoding(StrEnum):
    """How a `POST` carries the query."""

    URL_ENCODED = "urlencoded"
    """`application/x-www-form-urlencoded`; understood by every endpoint."""
    DIRECT = "direct"
    """`application/sparql-query`; skips percent-encoding the whole query."""


ACCEPT: Final[Mapping[ResultFormat, str]] = {
    SolutionFormat.JSON: "application/sparql-results+json,application/json;q=0.9",
    SolutionFormat.XML: "application/sparql-results+xml,application/xml;q=0.9",
    SolutionFormat.CSV: "text/csv",
    SolutionFormat.TSV: "text/tab-separated-values",
    GraphFormat.TURTLE: "text/turtle,application/x-turtle;q=0.9",
    GraphFormat.NTRIPLES: "application/n-triples,text/plain;q=0.9",
    GraphFormat.RDFXML: "application/rdf+xml",
    GraphFormat.JSONLD: "application/ld+json",
    GraphFormat.N3: "text/n3,text/turtle;q=0.9",
    GraphFormat.TRIG: "application/trig",
}
"""The `Accept` header sent for each result format."""


def parse_format(name: str) -> ResultFormat:
    """Look a result format up by its name.

    Args:
        name: A member value of `SolutionFormat` or `GraphFormat`.

    Returns:
        The matching format.

    Raises:
        ValueError: If no format goes by that name.
    """
    try:
        return SolutionFormat(name)
    except ValueError:
        return GraphFormat(name)


@dataclass(frozen=True, slots=True)
class EndpointConfig:
    """Everything about an endpoint that does not change from query to query."""

    endpoint: str
    """URL that query operations are sent to."""
    update_endpoint: str | None = None
    """URL that update operations are sent to; defaults to `endpoint`."""
    default_graph: tuple[str, ...] = ()
    """Graphs making up the RDF dataset's default graph."""
    named_graph: tuple[str, ...] = ()
    """Graphs making up the RDF dataset's named graphs."""
    method: HttpMethod | None = None
    """Verb to use; `None` picks `GET` while the URL stays under `max_get_length`."""
    encoding: RequestEncoding = RequestEncoding.URL_ENCODED
    """How a `POST` carries the query."""
    params: tuple[tuple[str, str], ...] = ()
    """Extra query-string parameters, for endpoint-specific knobs."""
    max_get_length: int = 2048
    """URL length above which `method=None` switches to `POST`."""


@dataclass(frozen=True, slots=True)
class RequestSpec:
    """A ready-to-send HTTP request, described without depending on any HTTP client."""

    method: HttpMethod
    url: str
    params: tuple[tuple[str, str], ...] = ()
    headers: tuple[tuple[str, str], ...] = ()
    content: bytes | None = field(default=None, repr=False)


def _graph_params(config: EndpointConfig, *, update: bool) -> list[tuple[str, str]]:
    default, named = (
        ("using-graph-uri", "using-named-graph-uri") if update else ("default-graph-uri", "named-graph-uri")
    )
    return [
        *((default, uri) for uri in config.default_graph),
        *((named, uri) for uri in config.named_graph),
    ]


def build_request(config: EndpointConfig, query: str, form: QueryForm, accept: str) -> RequestSpec:
    """Lay out the HTTP request that carries `query` to the endpoint.

    Args:
        config: The endpoint settings.
        query: The SPARQL query or update text.
        form: The form of `query`, as returned by `detect_form`.
        accept: The `Accept` header to ask the result format with.

    Returns:
        The request to send.
    """
    update = form.is_update
    url = (config.update_endpoint or config.endpoint) if update else config.endpoint
    key = "update" if update else "query"
    params = [*config.params, *_graph_params(config, update=update)]
    headers = [("Accept", accept)]

    if update:
        method = HttpMethod.POST
    elif config.method is not None:
        method = config.method
    elif len(url) + len(urlencode([*params, (key, query)])) < config.max_get_length:
        method = HttpMethod.GET
    else:
        method = HttpMethod.POST

    if method is HttpMethod.GET:
        return RequestSpec(method, url, (*params, (key, query)), tuple(headers))

    if config.encoding is RequestEncoding.DIRECT:
        headers.append(("Content-Type", f"application/sparql-{'update' if update else 'query'}"))
        return RequestSpec(method, url, tuple(params), tuple(headers), query.encode())

    headers.append(("Content-Type", "application/x-www-form-urlencoded"))
    body = urlencode([*params, (key, query)]).encode("ascii")
    return RequestSpec(method, url, (), tuple(headers), body)


def choose_format(form: QueryForm, requested: ResultFormat | None, *, raw: bool) -> ResultFormat:
    """Settle on the result format to ask the endpoint for.

    Without `raw`, the format is not free: `SELECT` and `ASK` are parsed out of
    the SPARQL JSON results format, and an update has no result to serialize, so
    only `CONSTRUCT` and `DESCRIBE` leave a choice to make.

    Args:
        form: The form of the query being sent.
        requested: The format the caller asked for, if any.
        raw: Whether the body is handed back unparsed, which frees the choice.

    Returns:
        The format to send in the `Accept` header.

    Raises:
        QueryFormError: If a format was requested that this form cannot answer in.
    """
    if requested is None:
        return GraphFormat.TURTLE if form in GRAPH_FORMS else SolutionFormat.JSON
    if not raw and (form not in GRAPH_FORMS or not isinstance(requested, GraphFormat)):
        msg = f"a {form} query cannot answer in {requested}; pass raw=True to take the body unparsed"
        raise QueryFormError(msg)
    return requested
