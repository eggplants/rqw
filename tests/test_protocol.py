from __future__ import annotations

from urllib.parse import parse_qs

import pytest

from rqw.exceptions import QueryFormError
from rqw.protocol import (
    ACCEPT,
    EndpointConfig,
    GraphFormat,
    HttpMethod,
    QueryForm,
    RequestEncoding,
    SolutionFormat,
    build_request,
    choose_format,
    parse_format,
)

ACCEPT_JSON = ACCEPT[SolutionFormat.JSON]


@pytest.mark.parametrize(
    ("form", "is_update"),
    [(QueryForm.SELECT, False), (QueryForm.DESCRIBE, False), (QueryForm.INSERT, True), (QueryForm.DROP, True)],
)
def test_is_update_separates_queries_from_updates(form, is_update):
    assert form.is_update is is_update


@pytest.mark.parametrize(
    ("form", "expected"),
    [
        (QueryForm.SELECT, SolutionFormat.JSON),
        (QueryForm.ASK, SolutionFormat.JSON),
        (QueryForm.CONSTRUCT, GraphFormat.TURTLE),
        (QueryForm.DESCRIBE, GraphFormat.TURTLE),
        (QueryForm.INSERT, SolutionFormat.JSON),
    ],
)
def test_choose_format_defaults_by_form(form, expected):
    assert choose_format(form, None, raw=False) is expected


def test_choose_format_lets_graph_queries_pick_a_serialization():
    assert choose_format(QueryForm.CONSTRUCT, GraphFormat.NTRIPLES, raw=False) is GraphFormat.NTRIPLES


@pytest.mark.parametrize(
    ("form", "requested"),
    [
        (QueryForm.SELECT, SolutionFormat.CSV),
        (QueryForm.ASK, GraphFormat.TURTLE),
        (QueryForm.DROP, SolutionFormat.XML),
        (QueryForm.CONSTRUCT, SolutionFormat.CSV),
    ],
)
def test_choose_format_refuses_a_format_the_form_cannot_answer_in(form, requested):
    with pytest.raises(QueryFormError, match="pass raw=True"):
        choose_format(form, requested, raw=False)


@pytest.mark.parametrize(
    ("form", "requested"),
    [(QueryForm.SELECT, SolutionFormat.CSV), (QueryForm.CONSTRUCT, GraphFormat.JSONLD)],
)
def test_raw_frees_the_choice_of_format(form, requested):
    assert choose_format(form, requested, raw=True) is requested


def test_parse_format_covers_both_families():
    assert parse_format("tsv") is SolutionFormat.TSV
    assert parse_format("jsonld") is GraphFormat.JSONLD
    with pytest.raises(ValueError, match="nope"):
        parse_format("nope")


def test_every_format_has_an_accept_header():
    assert set(ACCEPT) == {*SolutionFormat, *GraphFormat}


def test_a_short_query_goes_out_as_a_get():
    spec = build_request(EndpointConfig("http://e/"), "ASK { }", QueryForm.ASK, ACCEPT_JSON)
    assert spec.method is HttpMethod.GET
    assert spec.params == (("query", "ASK { }"),)
    assert spec.content is None


def test_a_long_query_falls_back_to_post():
    query = "SELECT * WHERE { ?s ?p ?o } #" + "x" * 3000
    spec = build_request(EndpointConfig("http://e/"), query, QueryForm.SELECT, ACCEPT_JSON)
    assert spec.method is HttpMethod.POST
    assert spec.content is not None
    assert parse_qs(spec.content.decode())["query"] == [query]
    assert dict(spec.headers)["Content-Type"] == "application/x-www-form-urlencoded"


def test_the_method_can_be_forced():
    config = EndpointConfig("http://e/", method=HttpMethod.POST)
    assert build_request(config, "ASK { }", QueryForm.ASK, ACCEPT_JSON).method is HttpMethod.POST


def test_direct_encoding_sends_the_query_as_the_body():
    config = EndpointConfig("http://e/", method=HttpMethod.POST, encoding=RequestEncoding.DIRECT)
    spec = build_request(config, "ASK { }", QueryForm.ASK, ACCEPT_JSON)
    assert spec.content == b"ASK { }"
    assert dict(spec.headers)["Content-Type"] == "application/sparql-query"


def test_a_get_carries_the_dataset_and_the_extra_parameters():
    config = EndpointConfig(
        "http://e/",
        default_graph=("http://g/1", "http://g/2"),
        named_graph=("http://n/1",),
        params=(("timeout", "5"),),
    )
    spec = build_request(config, "ASK { }", QueryForm.ASK, ACCEPT_JSON)
    assert spec.params == (
        ("timeout", "5"),
        ("default-graph-uri", "http://g/1"),
        ("default-graph-uri", "http://g/2"),
        ("named-graph-uri", "http://n/1"),
        ("query", "ASK { }"),
    )


def test_an_update_posts_to_the_update_endpoint_with_using_graphs():
    config = EndpointConfig("http://e/", update_endpoint="http://u/", default_graph=("http://g/",))
    spec = build_request(config, "DROP ALL", QueryForm.DROP, ACCEPT_JSON)
    assert spec.method is HttpMethod.POST
    assert spec.url == "http://u/"
    assert spec.content is not None
    assert parse_qs(spec.content.decode()) == {"using-graph-uri": ["http://g/"], "update": ["DROP ALL"]}


def test_a_direct_update_uses_the_update_content_type():
    config = EndpointConfig("http://e/", encoding=RequestEncoding.DIRECT, named_graph=("http://n/",))
    spec = build_request(config, "DROP ALL", QueryForm.DROP, ACCEPT_JSON)
    assert spec.content == b"DROP ALL"
    assert spec.params == (("using-named-graph-uri", "http://n/"),)
    assert dict(spec.headers)["Content-Type"] == "application/sparql-update"
