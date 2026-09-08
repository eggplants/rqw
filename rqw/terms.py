"""RDF terms, as they come back inside SPARQL result bindings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Final

from .exceptions import ResponseError

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

__all__ = [
    "XSD",
    "BlankNode",
    "Literal",
    "QuotedTriple",
    "Scalar",
    "Term",
    "Uri",
    "parse_term",
]

XSD: Final = "http://www.w3.org/2001/XMLSchema#"
"""Namespace every built-in SPARQL datatype lives in."""


@dataclass(frozen=True, slots=True)
class Uri:
    """An IRI."""

    value: str

    def __str__(self) -> str:
        """Return the IRI itself."""
        return self.value


@dataclass(frozen=True, slots=True)
class BlankNode:
    """A blank node, identified by a label that is only stable within one result set."""

    value: str

    def __str__(self) -> str:
        """Return the label in Turtle notation."""
        return f"_:{self.value}"


@dataclass(frozen=True, slots=True)
class Literal:
    """A literal, with at most one of a language tag or a datatype IRI."""

    value: str
    language: str | None = None
    datatype: str | None = None

    def __str__(self) -> str:
        """Return the lexical form."""
        return self.value

    def as_python(self) -> Scalar:
        """Decode the lexical form according to the literal's datatype.

        Literals with no datatype, a language tag, or a datatype rqw does not
        know about are returned unchanged as `str`.

        Returns:
            The decoded value.

        Raises:
            ValueError: If the lexical form is not valid for the datatype.
        """
        decode = _DECODERS.get(self.datatype or "")
        return self.value if decode is None else decode(self.value)


@dataclass(frozen=True, slots=True)
class QuotedTriple:
    """A quoted triple, the term type SPARQL 1.2 adds for RDF-star."""

    subject: Term
    predicate: Uri
    object: Term

    def __str__(self) -> str:
        """Return the triple in the `<< s p o >>` notation."""
        return f"<< {self.subject} {self.predicate} {self.object} >>"


type Term = Uri | BlankNode | Literal | QuotedTriple
"""Anything that can be bound to a variable."""

type Scalar = str | bool | int | float | Decimal | date | time | datetime
"""What `Literal.as_python` can hand back."""


def _decode_boolean(lexical: str) -> bool:
    if lexical in {"true", "1"}:
        return True
    if lexical in {"false", "0"}:
        return False
    msg = f"{lexical!r} is not a valid xsd:boolean"
    raise ValueError(msg)


_INTEGERS = (
    "integer",
    "int",
    "long",
    "short",
    "byte",
    "nonNegativeInteger",
    "nonPositiveInteger",
    "negativeInteger",
    "positiveInteger",
    "unsignedInt",
    "unsignedLong",
    "unsignedShort",
    "unsignedByte",
)

_DECODERS: Final[Mapping[str, Callable[[str], Scalar]]] = {
    f"{XSD}string": str,
    f"{XSD}boolean": _decode_boolean,
    f"{XSD}decimal": Decimal,
    f"{XSD}double": float,
    f"{XSD}float": float,
    f"{XSD}date": date.fromisoformat,
    f"{XSD}time": time.fromisoformat,
    f"{XSD}dateTime": datetime.fromisoformat,
    f"{XSD}dateTimeStamp": datetime.fromisoformat,
} | {f"{XSD}{name}": int for name in _INTEGERS}


def parse_term(node: Mapping[str, Any]) -> Term:
    """Build a term from one node of the SPARQL JSON results format.

    Args:
        node: A binding node, e.g. `{"type": "uri", "value": "http://..."}`.

    Returns:
        The matching term.

    Raises:
        ResponseError: If the node has an unknown type or is missing a value.
    """
    try:
        match node["type"]:
            case "uri":
                return Uri(node["value"])
            case "bnode":
                return BlankNode(node["value"])
            case "literal" | "typed-literal":
                return Literal(node["value"], node.get("xml:lang"), node.get("datatype"))
            case "triple" | "statement":
                inner = node["value"]
                return QuotedTriple(
                    parse_term(inner["subject"]),
                    Uri(inner["predicate"]["value"]),
                    parse_term(inner["object"]),
                )
            case unknown:
                msg = f"unknown RDF term type {unknown!r}"
                raise ResponseError(msg)
    except (KeyError, TypeError) as exc:
        msg = f"malformed RDF term {node!r}"
        raise ResponseError(msg) from exc
