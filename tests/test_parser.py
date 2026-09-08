from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

import pytest

from rqw.exceptions import QueryFormError, QuerySyntaxError
from rqw.parser import Query, detect_form, parse, render_value
from rqw.protocol import QueryForm
from rqw.terms import BlankNode, Literal, QuotedTriple, Uri

IRI = Uri("http://example.org/a")


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("SELECT * WHERE { ?s ?p ?o }", QueryForm.SELECT),
        ("  ask   { ?s ?p ?o }", QueryForm.ASK),
        ("# a comment\nCONSTRUCT { } WHERE { }", QueryForm.CONSTRUCT),
        ("BASE <http://e/>\nPREFIX f: <http://f/>\nDESCRIBE ?s", QueryForm.DESCRIBE),
        ("prefix f: <http://f/> insert data { <a> <b> <c> }", QueryForm.INSERT),
        ("WITH <http://g/> DELETE { ?s ?p ?o } WHERE { ?s ?p ?o }", QueryForm.WITH),
        ("#c1\n\n  #c2\nLOAD <http://g/>", QueryForm.LOAD),
        ("DELETE WHERE { ?s ?p ?o }", QueryForm.DELETE),
        ("DROP SILENT GRAPH <http://g/>", QueryForm.DROP),
    ],
)
def test_the_form_is_read_after_the_prologue(query, expected):
    assert detect_form(query) is expected


def test_a_keyword_named_prefix_does_not_confuse_the_prologue():
    assert detect_form("PREFIX select: <http://e/> ASK { ?s ?p ?o }") is QueryForm.ASK


def test_a_subquery_does_not_change_the_outer_form():
    query = "CONSTRUCT { ?s ?p ?o } WHERE { { SELECT ?s WHERE { ?s ?p ?o } } ?s ?p ?o }"
    assert detect_form(query) is QueryForm.CONSTRUCT


@pytest.mark.parametrize("query", ["", "   ", "SELEKT *", "# only a comment\n"])
def test_text_naming_no_form_is_rejected(query):
    with pytest.raises(QueryFormError, match="cannot tell the query form"):
        detect_form(query)


@pytest.mark.parametrize(
    "query",
    ["BASE SELECT *", "PREFIX <http://e/> SELECT *", "PREFIX f: SELECT *"],
)
def test_a_malformed_prologue_declaration_is_rejected(query):
    with pytest.raises(QuerySyntaxError, match="malformed"):
        detect_form(query)


@pytest.mark.parametrize(
    ("query", "message"),
    [
        ("SELECT * WHERE { ?s ?p ?o", "unclosed"),
        ("SELECT * WHERE { ?s ?p ?o } }", "unmatched"),
        ("SELECT * WHERE ( ?s ?p ?o }", "closed by"),
    ],
)
def test_unbalanced_delimiters_are_rejected(query, message):
    with pytest.raises(QuerySyntaxError, match=message):
        parse(query)


def test_a_parsed_query_passes_through_unchanged():
    parsed = parse("ASK { ?s ?p ?o }")
    assert parse(parsed) is parsed
    assert str(parsed) == parsed.text
    assert parsed == Query(QueryForm.ASK, "ASK { ?s ?p ?o }")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (IRI, "<http://example.org/a>"),
        (BlankNode("b0"), "_:b0"),
        (Literal("x"), '"x"'),
        (Literal("x", language="en"), '"x"@en'),
        (Literal("1", datatype="http://e/d"), '"1"^^<http://e/d>'),
        (QuotedTriple(IRI, Uri("http://e/p"), Literal("o")), '<< <http://example.org/a> <http://e/p> "o" >>'),
        (True, "true"),
        (False, "false"),
        (42, "42"),
        (-1, "-1"),
        (1.5, "1.5"),
        (Decimal("1.50"), "1.50"),
        ("plain", '"plain"'),
        ('say "hi"\n', '"say \\"hi\\"\\n"'),
        (date(2026, 9, 9), '"2026-09-09"^^<http://www.w3.org/2001/XMLSchema#date>'),
        (time(1, 2, 3), '"01:02:03"^^<http://www.w3.org/2001/XMLSchema#time>'),
        (datetime(2026, 9, 9, 1, 2, 3), '"2026-09-09T01:02:03"^^<http://www.w3.org/2001/XMLSchema#dateTime>'),  # noqa: DTZ001
        ([IRI, 42], "<http://example.org/a> 42"),
        ((), ""),
    ],
)
def test_render_value_writes_each_python_type_as_a_term(value, expected):
    assert render_value(value) == expected


@pytest.mark.parametrize(
    ("value", "spec", "expected"),
    [("http://e/a", "iri", "<http://e/a>"), ("x", "var", "?x"), ("?x", "var", "?x"), ("$x", "var", "?x")],
)
def test_a_format_spec_overrides_the_type(value, spec, expected):
    assert render_value(value, spec) == expected


@pytest.mark.parametrize(
    ("value", "spec", "message"),
    [
        (42, "iri", "needs a str"),
        ("x", "nope", "unknown format spec"),
        ("http://e/ a", "iri", "cannot contain"),
        ("http://e/<a>", "iri", "cannot contain"),
    ],
)
def test_a_bad_format_spec_or_iri_is_rejected(value, spec, message):
    with pytest.raises(QuerySyntaxError, match=message):
        render_value(value, spec)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), Decimal("NaN")])
def test_a_number_with_no_sparql_literal_is_rejected(value):
    with pytest.raises(QuerySyntaxError, match="no SPARQL numeric literal"):
        render_value(value)


@pytest.mark.parametrize(("value", "message"), [(b"x", "decode them first"), (object(), "no SPARQL term")])
def test_a_value_with_no_term_is_rejected(value, message):
    with pytest.raises(QuerySyntaxError, match=message):
        render_value(value)


def test_a_template_renders_its_values_as_terms():
    name = "Alice"
    parsed = parse(t"SELECT ?s WHERE {{ {IRI} <http://e/name> {name} }}")
    assert parsed.form is QueryForm.SELECT
    assert parsed.text == 'SELECT ?s WHERE { <http://example.org/a> <http://e/name> "Alice" }'


def test_a_template_only_spaces_a_value_when_it_would_otherwise_fuse():
    values = [Uri("http://e/1"), Uri("http://e/2")]
    assert parse(t"SELECT ?s {{ VALUES ?s {{ {values} }} }}").text == (
        "SELECT ?s { VALUES ?s { <http://e/1> <http://e/2> } }"
    )


def test_a_nested_template_is_flattened():
    inner = t"?s ?p {42}"
    assert parse(t"ASK {{ {inner} }}").text == "ASK { ?s ?p 42 }"


def test_a_value_that_tries_to_break_out_stays_one_literal():
    evil = '" } INSERT DATA { <a> <b> "pwned'
    parsed = parse(t"SELECT ?s WHERE {{ ?s ?p {evil} }}")
    assert parsed.form is QueryForm.SELECT
    assert parsed.text == 'SELECT ?s WHERE { ?s ?p "\\" } INSERT DATA { <a> <b> \\"pwned" }'


def test_a_value_that_would_close_a_comment_stays_one_literal():
    evil = "\n} DROP ALL"
    assert parse(t"ASK {{ ?s ?p {evil} }}").text == 'ASK { ?s ?p "\\n} DROP ALL" }'


@pytest.mark.parametrize(
    "build",
    [
        lambda v: t'SELECT ?s WHERE {{ ?s ?p "{v}" }}',
        lambda v: t"SELECT ?s WHERE {{ ?s ?p '{v}' }}",
        lambda v: t"SELECT ?s WHERE {{ ?s ?p ?o }} # {v}",
    ],
)
def test_a_value_landing_inside_a_token_is_refused(build):
    with pytest.raises(QuerySyntaxError, match="inside a token"):
        parse(build("x"))


def test_a_conversion_is_refused():
    value = "x"
    with pytest.raises(QuerySyntaxError, match="not supported"):
        parse(t"ASK {{ ?s ?p {value!r} }}")


def test_a_codepoint_escape_in_a_template_is_resolved():
    # A raw t-string keeps the backslash, so the grammar's own escape does the work.
    assert parse(rt"ASK {{ <http://e/caf\u00E9> ?p ?o }}").text == "ASK { <http://e/café> ?p ?o }"
