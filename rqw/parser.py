"""Turn a t-string, or plain text, into a query that is safe to send.

A `t"..."` template keeps its interpolations apart from its text, so the values
never reach the query as text the caller wrote. `parse` renders each one as a
complete RDF term -- escaped, quoted and typed -- splices it in, tokenizes the
result, and then checks that every value it spliced still lines up with a token
boundary. A value that tried to end a string literal early, or open a comment,
lands in the middle of a token and is refused.

What is checked here is the lexical grammar, the prologue, the query form and
the nesting of `{}`, `()` and `[]`. The rest of the 173 productions are left to
the endpoint, which has to parse the query anyway.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from string.templatelib import Interpolation, Template
from typing import Final

from .exceptions import QueryFormError, QuerySyntaxError
from .lexer import Token, TokenKind, tokenize, unescape_codepoints
from .protocol import QueryForm
from .terms import XSD, BlankNode, Literal, QuotedTriple, Uri

__all__ = ["Query", "QuerySource", "detect_form", "parse", "render_value"]

type QuerySource = str | Template | Query
"""Anything `parse` accepts: a t-string, plain text, or an already parsed query."""

_FORMS: Final = {form.value: form for form in QueryForm}
_OPENING: Final = {"{": "}", "(": ")", "[": "]"}
_IRI_FORBIDDEN: Final = frozenset('<>"{}|^`\\')
_STRING_ESCAPES: Final = str.maketrans(
    {"\\": "\\\\", '"': '\\"', "\n": "\\n", "\r": "\\r", "\t": "\\t"},
)


@dataclass(frozen=True, slots=True)
class Query:
    """A query whose form is known and whose text is ready to send."""

    form: QueryForm
    """The form the query text starts with, once its prologue is skipped."""
    text: str
    """The query text, with every interpolation rendered in."""

    def __str__(self) -> str:
        """Return the query text."""
        return self.text


def _quote(value: str) -> str:
    return f'"{value.translate(_STRING_ESCAPES)}"'


def _render_iri(value: str) -> str:
    bad = _IRI_FORBIDDEN.intersection(value) or {c for c in value if c <= "\x20"}
    if bad:
        listed = ", ".join(repr(c) for c in sorted(bad))
        msg = f"an IRI cannot contain {listed}"
        raise QuerySyntaxError(msg)
    return f"<{value}>"


def _render_number(value: float | Decimal) -> str:
    if not math.isfinite(value):
        msg = f"{value} has no SPARQL numeric literal"
        raise QuerySyntaxError(msg)
    return str(value)


def _render_temporal(value: date | time) -> str:
    if isinstance(value, datetime):
        name = "dateTime"
    elif isinstance(value, date):
        name = "date"
    else:
        name = "time"
    return f"{_quote(value.isoformat())}^^{_render_iri(f'{XSD}{name}')}"


def _render_term(value: Uri | BlankNode | Literal | QuotedTriple) -> str:
    match value:
        case Uri(iri):
            return _render_iri(iri)
        case BlankNode(label):
            return f"_:{label}"
        case Literal(lexical, language, datatype):
            suffix = f"@{language}" if language else f"^^{_render_iri(datatype)}" if datatype else ""
            return _quote(lexical) + suffix
        case QuotedTriple(subject, predicate, obj):
            return f"<< {_render_term(subject)} {_render_term(predicate)} {_render_term(obj)} >>"


def _render_with_spec(value: object, spec: str) -> str:
    if not isinstance(value, str):
        msg = f"format spec {spec!r} needs a str, got {type(value).__name__}"
        raise QuerySyntaxError(msg)
    if spec == "iri":
        return _render_iri(value)
    if spec == "var":
        name = value.removeprefix("?").removeprefix("$")
        return f"?{name}"
    msg = f"unknown format spec {spec!r}; expected 'iri' or 'var'"
    raise QuerySyntaxError(msg)


def render_value(value: object, spec: str = "") -> str:  # noqa: PLR0911
    """Render a Python value as the SPARQL text of one or more terms.

    `str` becomes a quoted literal rather than an IRI, which is the safe way
    round; ask for an IRI with `{value:iri}` or by passing a `Uri`. A sequence
    renders as its items separated by spaces, which is what a `VALUES` block
    wants.

    Args:
        value: The value to render.
        spec: The t-string format spec, `iri` or `var`, or empty to go by type.

    Returns:
        The SPARQL text for the value.

    Raises:
        QuerySyntaxError: If the value has no SPARQL term, or cannot be written
            as one without changing what it means.
    """
    if spec:
        return _render_with_spec(value, spec)
    match value:
        case Uri() | BlankNode() | Literal() | QuotedTriple():
            return _render_term(value)
        case bool():
            return "true" if value else "false"
        case str():
            return _quote(value)
        case bytes() | bytearray():
            msg = "bytes have no SPARQL term; decode them first"
            raise QuerySyntaxError(msg)
        case int():
            return str(value)
        case float() | Decimal():
            return _render_number(value)
        case date() | time():
            return _render_temporal(value)
        case Sequence():
            return " ".join(render_value(item) for item in value)
        case _:
            msg = f"{type(value).__name__} has no SPARQL term"
            raise QuerySyntaxError(msg)


@dataclass(frozen=True, slots=True)
class _Hole:
    """The text one interpolation rendered to, before it is placed."""

    text: str


def _segments(template: Template, out: list[str | _Hole]) -> None:
    """Flatten a template, and any template nested in it, into text and holes."""
    for item in template:
        if isinstance(item, str):
            out.append(unescape_codepoints(item))
            continue
        interpolation: Interpolation = item
        if interpolation.conversion is not None:
            msg = f"!{interpolation.conversion} is not supported in a SPARQL template"
            raise QuerySyntaxError(msg)
        if isinstance(interpolation.value, Template):
            _segments(interpolation.value, out)
        else:
            out.append(_Hole(render_value(interpolation.value, interpolation.format_spec)))


def _assemble(segments: Sequence[str | _Hole]) -> tuple[str, list[tuple[int, int]]]:
    """Join segments into query text, noting the span each rendered value occupies.

    A space goes in wherever a value would otherwise fuse with the text beside
    it; the recorded span covers the value alone, so `_check_holes` can insist
    that it still lines up with a token.
    """
    pieces: list[str] = []
    holes: list[tuple[int, int]] = []
    offset = 0
    for index, segment in enumerate(segments):
        if isinstance(segment, str):
            pieces.append(segment)
            offset += len(segment)
            continue
        if pieces and not pieces[-1][-1:].isspace():
            pieces.append(" ")
            offset += 1
        holes.append((offset, offset + len(segment.text)))
        pieces.append(segment.text)
        offset += len(segment.text)
        following = segments[index + 1] if index + 1 < len(segments) else None
        if isinstance(following, str) and following[:1] and not following[0].isspace():
            pieces.append(" ")
            offset += 1
    return "".join(pieces), holes


def _check_holes(tokens: Sequence[Token], holes: Sequence[tuple[int, int]]) -> None:
    starts = {token.start for token in tokens}
    ends = {token.end for token in tokens}
    for start, end in holes:
        if start not in starts or end not in ends:
            msg = "an interpolated value cannot appear inside a token"
            raise QuerySyntaxError(msg, start)


def _check_nesting(tokens: Sequence[Token]) -> None:
    stack: list[Token] = []
    for token in tokens:
        if token.kind is not TokenKind.PUNCT:
            continue
        if token.text in _OPENING:
            stack.append(token)
        elif token.text in {"}", ")", "]"}:
            if not stack:
                msg = f"unmatched {token.text!r}"
                raise QuerySyntaxError(msg, token.start)
            opened = stack.pop()
            if _OPENING[opened.text] != token.text:
                msg = f"{opened.text!r} closed by {token.text!r}"
                raise QuerySyntaxError(msg, token.start)
    if stack:
        msg = f"unclosed {stack[-1].text!r}"
        raise QuerySyntaxError(msg, stack[-1].start)


def _skip_prologue(tokens: Sequence[Token]) -> int:
    """Return the index of the first token after `Prologue`, production [4]."""
    index = 0
    while index < len(tokens) and tokens[index].kind is TokenKind.WORD:
        match tokens[index].word:
            case "BASE":
                shape, step = (TokenKind.IRIREF,), 2
            case "PREFIX":
                shape, step = (TokenKind.PNAME, TokenKind.IRIREF), 3
            case _:
                return index
        declaration = tokens[index + 1 : index + step]
        if len(declaration) != len(shape) or any(
            token.kind is not kind for token, kind in zip(declaration, shape, strict=True)
        ):
            msg = f"malformed {tokens[index].word} declaration"
            raise QuerySyntaxError(msg, tokens[index].start)
        index += step
    return index


def _detect_form(tokens: Sequence[Token], text: str) -> QueryForm:
    index = _skip_prologue(tokens)
    if index < len(tokens) and tokens[index].kind is TokenKind.WORD:
        found = _FORMS.get(tokens[index].word)
        if found is not None:
            return found
    msg = f"cannot tell the query form of {text.strip()[:80]!r}"
    raise QueryFormError(msg)


def parse(source: QuerySource) -> Query:
    """Read a query, rendering any interpolations, and work out its form.

    Args:
        source: A t-string, plain query text, or an already parsed `Query`.

    Returns:
        The parsed query.

    Raises:
        QuerySyntaxError: If the text is not well-formed SPARQL, a value has no
            SPARQL term, or an interpolation would land inside a token.
        QueryFormError: If nothing after the prologue names a query form.
    """
    if isinstance(source, Query):
        return source
    holes: list[tuple[int, int]] = []
    if isinstance(source, Template):
        segments: list[str | _Hole] = []
        _segments(source, segments)
        text, holes = _assemble(segments)
    else:
        text = unescape_codepoints(source)
    tokens = tokenize(text)
    _check_holes(tokens, holes)
    _check_nesting(tokens)
    return Query(_detect_form(tokens, text), text)


def detect_form(source: QuerySource) -> QueryForm:
    """Work out which form a query is written in.

    Args:
        source: A t-string, plain query text, or an already parsed `Query`.

    Returns:
        The query form.

    Raises:
        QuerySyntaxError: If the text is not well-formed SPARQL.
        QueryFormError: If nothing after the prologue names a query form.
    """
    return parse(source).form
