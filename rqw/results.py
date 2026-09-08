"""Typed views over what an endpoint sends back."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast, overload

from .exceptions import ResponseError
from .protocol import GraphFormat, QueryForm, ResultFormat
from .terms import parse_term

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from .terms import Term

__all__ = [
    "AskResult",
    "GraphResult",
    "QueryResult",
    "RawResult",
    "Row",
    "SelectResult",
    "UpdateResult",
    "interpret",
    "parse_ask",
    "parse_select",
]

type Row = Mapping[str, Term]
"""One solution. Variables left unbound by the query are simply absent."""


@dataclass(frozen=True, slots=True)
class SelectResult(Sequence[Row]):
    """The solution sequence of a `SELECT` query, as a sequence of `Row`."""

    variables: tuple[str, ...]
    """The projected variables, in the order the endpoint reported them."""
    rows: tuple[Row, ...]
    """The solutions."""

    def __len__(self) -> int:
        """Return the number of solutions."""
        return len(self.rows)

    @overload
    def __getitem__(self, index: int) -> Row: ...
    @overload
    def __getitem__(self, index: slice) -> tuple[Row, ...]: ...

    def __getitem__(self, index: int | slice) -> Row | tuple[Row, ...]:
        """Return the solution, or the slice of solutions, at `index`."""
        return self.rows[index]

    def __iter__(self) -> Iterator[Row]:
        """Iterate over the solutions."""
        return iter(self.rows)

    def column(self, variable: str) -> tuple[Term | None, ...]:
        """Collect one variable's binding across every solution.

        Args:
            variable: The variable name, without the leading `?`.

        Returns:
            One entry per solution, `None` where the variable is unbound.

        Raises:
            KeyError: If the query did not project `variable`.
        """
        if variable not in self.variables:
            raise KeyError(variable)
        return tuple(row.get(variable) for row in self.rows)


@dataclass(frozen=True, slots=True)
class RawResult[F: ResultFormat]:
    """A response body handed over exactly as the endpoint serialized it.

    The type parameter records which family of formats was asked for, so
    `SparqlClient.graph` can promise a `RawResult[GraphFormat]`.
    """

    format: F
    """The format that was requested."""
    content_type: str
    """The `Content-Type` header the endpoint answered with."""
    data: bytes
    """The undecoded body."""

    @property
    def charset(self) -> str:
        """The charset from the `Content-Type` header, `utf-8` when it says nothing."""
        _, _, rest = self.content_type.partition("charset=")
        return rest.partition(";")[0].strip().strip('"') or "utf-8"

    @property
    def text(self) -> str:
        """The body decoded with `charset`."""
        return self.data.decode(self.charset, "replace")

    def json(self) -> Any:  # noqa: ANN401
        """Parse the body as JSON, for the `json` and `jsonld` formats.

        Returns:
            Whatever the body decodes to.

        Raises:
            ResponseError: If the body is not valid JSON.
        """
        try:
            return json.loads(self.data)
        except ValueError as exc:
            msg = f"expected {self.format} but the body is not JSON"
            raise ResponseError(msg) from exc


def _load(data: bytes) -> Mapping[str, Any]:
    try:
        payload = json.loads(data)
    except ValueError as exc:
        msg = "expected SPARQL JSON results but the body is not JSON"
        raise ResponseError(msg) from exc
    if not isinstance(payload, dict):
        msg = f"expected a SPARQL JSON results object, got {type(payload).__name__}"
        raise ResponseError(msg)
    return payload


def parse_select(data: bytes) -> SelectResult:
    """Read a `SELECT` answer in the SPARQL 1.1 Query Results JSON Format.

    Args:
        data: The raw response body.

    Returns:
        The solution sequence.

    Raises:
        ResponseError: If the body is not a well-formed results object.
    """
    payload = _load(data)
    try:
        variables = tuple(payload["head"]["vars"])
        bindings = payload["results"]["bindings"]
        rows = tuple({name: parse_term(node) for name, node in binding.items()} for binding in bindings)
    except (KeyError, TypeError, AttributeError) as exc:
        msg = "the body is JSON but not a SPARQL SELECT result"
        raise ResponseError(msg) from exc
    return SelectResult(variables, rows)


def parse_ask(data: bytes) -> bool:
    """Read an `ASK` answer in the SPARQL 1.1 Query Results JSON Format.

    Args:
        data: The raw response body.

    Returns:
        The boolean the endpoint reported.

    Raises:
        ResponseError: If the body carries no `boolean` member.
    """
    value = _load(data).get("boolean")
    if not isinstance(value, bool):
        msg = "the body is JSON but carries no ASK boolean"
        raise ResponseError(msg)
    return value


@dataclass(frozen=True, slots=True)
class AskResult:
    """What an `ASK` query answered."""

    value: bool
    """The endpoint's answer."""

    def __bool__(self) -> bool:
        """Return the answer, so the result can be tested directly."""
        return self.value


@dataclass(frozen=True, slots=True)
class GraphResult(RawResult[GraphFormat]):
    """The RDF graph a `CONSTRUCT` or `DESCRIBE` answered with, still serialized."""


@dataclass(frozen=True, slots=True)
class UpdateResult:
    """The endpoint's acknowledgement of an update operation."""

    status: int
    """The HTTP status the endpoint accepted the operation with."""


type QueryResult = SelectResult | AskResult | GraphResult | UpdateResult
"""What `SparqlClient.execute` returns, one member per query form."""


def interpret[F: ResultFormat](form: QueryForm, body: RawResult[F], status: int) -> QueryResult:
    """Read a response body as the result type its query form calls for.

    Args:
        form: The form of the query that produced this response.
        body: The response body, with the format that was requested.
        status: The HTTP status the endpoint answered with.

    Returns:
        The parsed result.

    Raises:
        ResponseError: If the body does not match the form it should have.
    """
    match form:
        case QueryForm.SELECT:
            return parse_select(body.data)
        case QueryForm.ASK:
            return AskResult(parse_ask(body.data))
        case QueryForm.CONSTRUCT | QueryForm.DESCRIBE:
            # choose_format only ever hands these two forms a GraphFormat.
            return GraphResult(cast("GraphFormat", body.format), body.content_type, body.data)
        case _:
            return UpdateResult(status)
