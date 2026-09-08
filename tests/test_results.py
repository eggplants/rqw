from __future__ import annotations

import pytest
from conftest import ASK_JSON, SELECT_JSON

from rqw.exceptions import ResponseError
from rqw.protocol import GraphFormat, QueryForm, SolutionFormat
from rqw.results import (
    AskResult,
    GraphResult,
    RawResult,
    SelectResult,
    UpdateResult,
    interpret,
    parse_ask,
    parse_select,
)
from rqw.terms import BlankNode, Literal, Uri


@pytest.fixture
def result() -> SelectResult:
    return parse_select(SELECT_JSON)


def test_parse_select_reads_variables_and_rows(result):
    assert result.variables == ("s", "n")
    assert len(result) == 2
    assert result[0]["s"] == Uri("http://example.org/a")
    assert result[0]["n"] == Literal("1", datatype="http://www.w3.org/2001/XMLSchema#integer")
    assert result[1] == {"s": BlankNode("b0")}


def test_a_select_result_is_a_sequence(result):
    assert [row["s"] for row in result] == [Uri("http://example.org/a"), BlankNode("b0")]
    assert result[:1] == (result[0],)
    assert result[0] in result


def test_column_reports_unbound_variables_as_none(result):
    assert result.column("n") == (Literal("1", datatype="http://www.w3.org/2001/XMLSchema#integer"), None)


def test_column_rejects_a_variable_the_query_never_projected(result):
    with pytest.raises(KeyError):
        result.column("missing")


def test_parse_select_rejects_a_body_that_is_not_json():
    with pytest.raises(ResponseError, match="not JSON"):
        parse_select(b"<html>")


def test_parse_select_rejects_json_that_is_not_an_object():
    with pytest.raises(ResponseError, match="got list"):
        parse_select(b"[]")


def test_parse_select_rejects_an_object_without_bindings():
    with pytest.raises(ResponseError, match="not a SPARQL SELECT result"):
        parse_select(b'{"head": {}, "boolean": true}')


def test_parse_ask_reads_the_boolean():
    assert parse_ask(ASK_JSON) is True


def test_parse_ask_rejects_a_result_without_a_boolean():
    with pytest.raises(ResponseError, match="no ASK boolean"):
        parse_ask(SELECT_JSON)


def test_raw_result_decodes_with_the_declared_charset():
    raw = RawResult(GraphFormat.TURTLE, 'text/turtle; charset="latin-1"', "café".encode("latin-1"))
    assert raw.charset == "latin-1"
    assert raw.text == "café"


def test_raw_result_falls_back_to_utf_8():
    assert RawResult(GraphFormat.TURTLE, "text/turtle", "café".encode()).text == "café"


def test_raw_result_parses_json():
    assert RawResult(SolutionFormat.JSON, "application/json", b'{"a": 1}').json() == {"a": 1}


def test_raw_result_rejects_a_body_that_is_not_json():
    with pytest.raises(ResponseError, match="not JSON"):
        RawResult(SolutionFormat.JSON, "application/json", b"nope").json()


def test_interpret_dispatches_on_the_query_form():
    json_body = RawResult(SolutionFormat.JSON, "application/sparql-results+json", SELECT_JSON)
    assert interpret(QueryForm.SELECT, json_body, 200) == parse_select(SELECT_JSON)

    ask_body = RawResult(SolutionFormat.JSON, "application/sparql-results+json", ASK_JSON)
    assert interpret(QueryForm.ASK, ask_body, 200) == AskResult(value=True)

    turtle = RawResult(GraphFormat.TURTLE, "text/turtle", b"<a> <b> <c> .")
    graph = interpret(QueryForm.DESCRIBE, turtle, 200)
    assert graph == GraphResult(GraphFormat.TURTLE, "text/turtle", b"<a> <b> <c> .")
    assert graph.text == "<a> <b> <c> ."

    assert interpret(QueryForm.INSERT, json_body, 204) == UpdateResult(status=204)


def test_an_ask_result_is_truthy_on_true_only():
    assert bool(AskResult(value=True)) is True
    assert bool(AskResult(value=False)) is False
