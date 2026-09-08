from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from rqw.exceptions import ResponseError
from rqw.terms import XSD, BlankNode, Literal, QuotedTriple, Uri, parse_term


def test_uri_renders_as_itself():
    assert str(Uri("http://example.org/a")) == "http://example.org/a"


def test_blank_node_renders_in_turtle_notation():
    assert str(BlankNode("b0")) == "_:b0"


def test_literal_renders_as_its_lexical_form():
    assert str(Literal("hello", language="en")) == "hello"


@pytest.mark.parametrize(
    ("datatype", "lexical", "expected"),
    [
        ("integer", "42", 42),
        ("int", "-1", -1),
        ("unsignedByte", "7", 7),
        ("decimal", "1.5", Decimal("1.5")),
        ("double", "1e3", 1000.0),
        ("boolean", "true", True),
        ("boolean", "0", False),
        ("date", "2026-09-09", date(2026, 9, 9)),
        ("dateTime", "2026-09-09T01:02:03", datetime(2026, 9, 9, 1, 2, 3)),  # noqa: DTZ001
        ("string", "x", "x"),
    ],
)
def test_as_python_decodes_known_datatypes(datatype, lexical, expected):
    assert Literal(lexical, datatype=f"{XSD}{datatype}").as_python() == expected


def test_as_python_leaves_unknown_datatypes_alone():
    assert Literal("x", datatype="http://example.org/weird").as_python() == "x"
    assert Literal("x", language="en").as_python() == "x"


def test_as_python_rejects_a_malformed_boolean():
    with pytest.raises(ValueError, match="xsd:boolean"):
        Literal("maybe", datatype=f"{XSD}boolean").as_python()


def test_parse_term_reads_every_node_type():
    assert parse_term({"type": "uri", "value": "http://example.org/a"}) == Uri("http://example.org/a")
    assert parse_term({"type": "bnode", "value": "b0"}) == BlankNode("b0")
    assert parse_term({"type": "literal", "value": "x", "xml:lang": "en"}) == Literal("x", language="en")
    assert parse_term({"type": "typed-literal", "value": "1", "datatype": "d"}) == Literal("1", datatype="d")


def test_parse_term_reads_a_quoted_triple():
    node = {
        "type": "triple",
        "value": {
            "subject": {"type": "uri", "value": "http://example.org/s"},
            "predicate": {"type": "uri", "value": "http://example.org/p"},
            "object": {"type": "literal", "value": "o"},
        },
    }
    triple = parse_term(node)
    assert triple == QuotedTriple(Uri("http://example.org/s"), Uri("http://example.org/p"), Literal("o"))
    assert str(triple) == "<< http://example.org/s http://example.org/p o >>"


def test_parse_term_rejects_an_unknown_type():
    with pytest.raises(ResponseError, match="unknown RDF term type"):
        parse_term({"type": "quad", "value": "x"})


def test_parse_term_rejects_a_node_without_a_value():
    with pytest.raises(ResponseError, match="malformed RDF term"):
        parse_term({"type": "uri"})
