"""Synchronous and asynchronous SPARQL clients."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Final, Literal, Self, cast, overload

import httpx

from . import __version__
from .exceptions import QueryFormError, raise_for_status
from .parser import Query, QuerySource, parse
from .protocol import (
    ACCEPT,
    EndpointConfig,
    GraphFormat,
    HttpMethod,
    QueryForm,
    RequestEncoding,
    RequestSpec,
    ResultFormat,
    build_request,
    choose_format,
)
from .results import (
    AskResult,
    GraphResult,
    QueryResult,
    RawResult,
    SelectResult,
    UpdateResult,
    interpret,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ["USER_AGENT", "AsyncSparqlClient", "SparqlClient"]

USER_AGENT: Final = f"rqw/{__version__} (+https://github.com/eggplants/rqw)"
"""Default `User-Agent`; endpoints use it for rate limiting, so keep it honest."""


class _BaseClient[C: (httpx.Client, httpx.AsyncClient)]:
    """Configuration and request shaping shared by both clients."""

    _factory: type[httpx.Client | httpx.AsyncClient] = httpx.Client

    def __init__(
        self,
        endpoint: str,
        *,
        update_endpoint: str | None = None,
        default_graph: Sequence[str] = (),
        named_graph: Sequence[str] = (),
        method: HttpMethod | None = None,
        encoding: RequestEncoding = RequestEncoding.URL_ENCODED,
        params: Mapping[str, str] | Sequence[tuple[str, str]] = (),
        max_get_length: int = 2048,
        timeout: float | None = 30.0,
        user_agent: str = USER_AGENT,
        headers: Mapping[str, str] | None = None,
        auth: httpx.Auth | tuple[str, str] | None = None,
        client: C | None = None,
    ) -> None:
        """Configure a client.

        Args:
            endpoint: URL of the SPARQL query endpoint.
            update_endpoint: URL for update operations, when it differs.
            default_graph: `default-graph-uri` values for the RDF dataset.
            named_graph: `named-graph-uri` values for the RDF dataset.
            method: Force `GET` or `POST`. The default picks `GET` while the URL
                stays under `max_get_length` and `POST` past it.
            encoding: How a `POST` carries the query.
            params: Extra query-string parameters, for endpoint-specific knobs.
            max_get_length: URL length at which the default `method` gives up on `GET`.
            timeout: Per-request timeout in seconds, `None` to wait forever.
            user_agent: Value of the `User-Agent` header.
            headers: Extra headers sent with every request.
            auth: Credentials, either an `httpx.Auth` or a `(user, password)` pair
                for HTTP Basic.
            client: An `httpx` client to send through. When given, its own
                timeout and auth settings win and closing it stays your job.
        """
        self._config = EndpointConfig(
            endpoint=endpoint,
            update_endpoint=update_endpoint,
            default_graph=tuple(default_graph),
            named_graph=tuple(named_graph),
            method=method,
            encoding=encoding,
            params=tuple(params.items() if isinstance(params, Mapping) else params),
            max_get_length=max_get_length,
        )
        self._headers = {"User-Agent": user_agent, **(headers or {})}
        self._owns_client = client is None
        self._client: C = (
            client
            if client is not None
            else cast("C", self._factory(timeout=timeout, auth=auth, follow_redirects=True))
        )

    @property
    def config(self) -> EndpointConfig:
        """The endpoint settings this client was built with."""
        return self._config

    def _plan(
        self,
        query: QuerySource,
        expect: QueryForm | None,
        result_format: ResultFormat | None,
        *,
        raw: bool,
    ) -> tuple[Query, ResultFormat, RequestSpec]:
        parsed = parse(query)
        if expect is not None and parsed.form is not expect:
            msg = f"expected a {expect} query, got {parsed.form}"
            raise QueryFormError(msg)
        chosen = choose_format(parsed.form, result_format, raw=raw)
        return parsed, chosen, build_request(self._config, parsed.text, parsed.form, ACCEPT[chosen])

    def _request(self, spec: RequestSpec) -> httpx.Request:
        return self._client.build_request(
            spec.method,
            spec.url,
            params=list(spec.params) or None,
            headers=self._headers | dict(spec.headers),
            content=spec.content,
        )


class SparqlClient(_BaseClient[httpx.Client]):
    """A SPARQL endpoint, queried synchronously.

    The underlying connection is pooled and kept alive, so reusing one client
    for many queries is much cheaper than building one per query.

    Every query form goes through `execute`, which reads the form off the query
    and answers with the result type that form calls for.

    Example:
        >>> with SparqlClient("https://dbpedia.org/sparql") as sparql:  # doctest: +SKIP
        ...     match sparql.execute("SELECT ?s WHERE { ?s ?p ?o } LIMIT 10"):
        ...         case SelectResult() as rows:
        ...             for row in rows:
        ...                 print(row["s"])
    """

    _factory = httpx.Client

    def __enter__(self) -> Self:
        """Enter a context that closes the client on the way out."""
        return self

    def __exit__(self, *_: object) -> None:
        """Close the client unless it was passed in from outside."""
        self.close()

    def close(self) -> None:
        """Close the pooled connections, unless the client was passed in."""
        if self._owns_client:
            self._client.close()

    def _send(self, spec: RequestSpec) -> httpx.Response:
        response = self._client.send(self._request(spec))
        raise_for_status(response.status_code, str(response.url), response.content)
        return response

    @overload
    def execute(
        self,
        query: QuerySource,
        *,
        expect: Literal[QueryForm.SELECT],
        result_format: None = None,
        raw: Literal[False] = False,
    ) -> SelectResult: ...

    @overload
    def execute(
        self,
        query: QuerySource,
        *,
        expect: Literal[QueryForm.ASK],
        result_format: None = None,
        raw: Literal[False] = False,
    ) -> AskResult: ...

    @overload
    def execute(
        self,
        query: QuerySource,
        *,
        expect: Literal[QueryForm.CONSTRUCT, QueryForm.DESCRIBE],
        result_format: GraphFormat | None = None,
        raw: Literal[False] = False,
    ) -> GraphResult: ...

    @overload
    def execute(
        self,
        query: QuerySource,
        *,
        expect: Literal[
            QueryForm.INSERT,
            QueryForm.DELETE,
            QueryForm.WITH,
            QueryForm.LOAD,
            QueryForm.CLEAR,
            QueryForm.CREATE,
            QueryForm.DROP,
            QueryForm.COPY,
            QueryForm.MOVE,
            QueryForm.ADD,
        ],
        result_format: None = None,
        raw: Literal[False] = False,
    ) -> UpdateResult: ...

    @overload
    def execute(
        self,
        query: QuerySource,
        *,
        expect: QueryForm | None = None,
        result_format: GraphFormat | None = None,
        raw: Literal[False] = False,
    ) -> QueryResult: ...

    @overload
    def execute(
        self,
        query: QuerySource,
        *,
        expect: QueryForm | None = None,
        result_format: ResultFormat | None = None,
        raw: Literal[True],
    ) -> RawResult[ResultFormat]: ...

    def execute(
        self,
        query: QuerySource,
        *,
        expect: QueryForm | None = None,
        result_format: ResultFormat | None = None,
        raw: bool = False,
    ) -> QueryResult | RawResult[ResultFormat]:
        """Run any SPARQL query or update operation.

        The query form decides what comes back, so narrow the result before
        using it -- `match` on the member you expect:

            match sparql.execute(query):
                case SelectResult() as rows:
                    ...
                case AskResult(value=answer):
                    ...
                case GraphResult() as graph:
                    graph.text
                case UpdateResult():
                    ...

        Passing `expect` skips the narrowing: the return type is the one that
        form calls for, and a query of any other form is refused before the
        request goes out. With `raw=True` nothing is parsed and a `RawResult`
        comes back on its own.

        Args:
            query: A `t"..."` template, plain query text, or a parsed `Query`.
                Interpolated values are rendered as RDF terms, never as text.
                Updates are routed to the update endpoint on their own.
            expect: The form the query must be written in.
            result_format: The serialization to ask for. Only `CONSTRUCT` and
                `DESCRIBE` leave a choice unless `raw` is set, since the other
                forms are parsed out of the SPARQL JSON results format.
            raw: Hand the body back exactly as the endpoint serialized it.

        Returns:
            A `RawResult` when `raw` is set, otherwise the result type the
            query form calls for.

        Raises:
            QuerySyntaxError: If the query text is not well-formed SPARQL.
            QueryFormError: If the query form cannot be read, does not match
                `expect`, or cannot answer in `result_format`.
        """
        parsed, chosen, spec = self._plan(query, expect, result_format, raw=raw)
        response = self._send(spec)
        body = RawResult(chosen, response.headers.get("content-type", ""), response.content)
        return body if raw else interpret(parsed.form, body, response.status_code)


class AsyncSparqlClient(_BaseClient[httpx.AsyncClient]):
    """A SPARQL endpoint, queried with `asyncio`.

    Same surface as `SparqlClient`, with `execute` awaitable. Running independent
    queries through `asyncio.gather` on one client is the fastest way to get a
    batch of results, since they share the connection pool.

    Example:
        >>> async with AsyncSparqlClient("https://dbpedia.org/sparql") as sparql:  # doctest: +SKIP
        ...     result = await sparql.execute("SELECT ?s WHERE { ?s ?p ?o } LIMIT 10")
    """

    _factory = httpx.AsyncClient

    async def __aenter__(self) -> Self:
        """Enter a context that closes the client on the way out."""
        return self

    async def __aexit__(self, *_: object) -> None:
        """Close the client unless it was passed in from outside."""
        await self.aclose()

    async def aclose(self) -> None:
        """Close the pooled connections, unless the client was passed in."""
        if self._owns_client:
            await self._client.aclose()

    async def _send(self, spec: RequestSpec) -> httpx.Response:
        response = await self._client.send(self._request(spec))
        raise_for_status(response.status_code, str(response.url), response.content)
        return response

    @overload
    async def execute(
        self,
        query: QuerySource,
        *,
        expect: Literal[QueryForm.SELECT],
        result_format: None = None,
        raw: Literal[False] = False,
    ) -> SelectResult: ...

    @overload
    async def execute(
        self,
        query: QuerySource,
        *,
        expect: Literal[QueryForm.ASK],
        result_format: None = None,
        raw: Literal[False] = False,
    ) -> AskResult: ...

    @overload
    async def execute(
        self,
        query: QuerySource,
        *,
        expect: Literal[QueryForm.CONSTRUCT, QueryForm.DESCRIBE],
        result_format: GraphFormat | None = None,
        raw: Literal[False] = False,
    ) -> GraphResult: ...

    @overload
    async def execute(
        self,
        query: QuerySource,
        *,
        expect: Literal[
            QueryForm.INSERT,
            QueryForm.DELETE,
            QueryForm.WITH,
            QueryForm.LOAD,
            QueryForm.CLEAR,
            QueryForm.CREATE,
            QueryForm.DROP,
            QueryForm.COPY,
            QueryForm.MOVE,
            QueryForm.ADD,
        ],
        result_format: None = None,
        raw: Literal[False] = False,
    ) -> UpdateResult: ...

    @overload
    async def execute(
        self,
        query: QuerySource,
        *,
        expect: QueryForm | None = None,
        result_format: GraphFormat | None = None,
        raw: Literal[False] = False,
    ) -> QueryResult: ...

    @overload
    async def execute(
        self,
        query: QuerySource,
        *,
        expect: QueryForm | None = None,
        result_format: ResultFormat | None = None,
        raw: Literal[True],
    ) -> RawResult[ResultFormat]: ...

    async def execute(
        self,
        query: QuerySource,
        *,
        expect: QueryForm | None = None,
        result_format: ResultFormat | None = None,
        raw: bool = False,
    ) -> QueryResult | RawResult[ResultFormat]:
        """Run any SPARQL query or update operation.

        The query form decides what comes back, so narrow the result before
        using it -- `match` on the member you expect:

            match sparql.execute(query):
                case SelectResult() as rows:
                    ...
                case AskResult(value=answer):
                    ...
                case GraphResult() as graph:
                    graph.text
                case UpdateResult():
                    ...

        Passing `expect` skips the narrowing: the return type is the one that
        form calls for, and a query of any other form is refused before the
        request goes out. With `raw=True` nothing is parsed and a `RawResult`
        comes back on its own.

        Args:
            query: A `t"..."` template, plain query text, or a parsed `Query`.
                Interpolated values are rendered as RDF terms, never as text.
                Updates are routed to the update endpoint on their own.
            expect: The form the query must be written in.
            result_format: The serialization to ask for. Only `CONSTRUCT` and
                `DESCRIBE` leave a choice unless `raw` is set, since the other
                forms are parsed out of the SPARQL JSON results format.
            raw: Hand the body back exactly as the endpoint serialized it.

        Returns:
            A `RawResult` when `raw` is set, otherwise the result type the
            query form calls for.

        Raises:
            QuerySyntaxError: If the query text is not well-formed SPARQL.
            QueryFormError: If the query form cannot be read, does not match
                `expect`, or cannot answer in `result_format`.
        """
        parsed, chosen, spec = self._plan(query, expect, result_format, raw=raw)
        response = await self._send(spec)
        body = RawResult(chosen, response.headers.get("content-type", ""), response.content)
        return body if raw else interpret(parsed.form, body, response.status_code)
