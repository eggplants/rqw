from __future__ import annotations

from urllib.parse import parse_qs

import pytest
from conftest import ASK_JSON, SELECT_JSON

from rqw import (
    AskResult,
    AsyncSparqlClient,
    BadQueryError,
    EndpointError,
    GraphFormat,
    GraphResult,
    HttpMethod,
    QueryForm,
    QueryFormError,
    RequestEncoding,
    SelectResult,
    SolutionFormat,
    SparqlClient,
    UpdateResult,
    Uri,
)
from rqw.client import USER_AGENT
from rqw.exceptions import QuerySyntaxError
from rqw.parser import parse

ENDPOINT = "http://example.org/sparql"
SELECT = "SELECT ?s ?n WHERE { ?s ?p ?n }"


@pytest.fixture
def sparql(sync_client) -> SparqlClient:
    return SparqlClient(ENDPOINT, client=sync_client)


def test_a_select_comes_back_as_a_select_result(sparql, recorder):
    result = sparql.execute(SELECT)
    assert isinstance(result, SelectResult)
    assert result.variables == ("s", "n")
    assert result[0]["s"] == Uri("http://example.org/a")
    assert parse_qs(recorder.last.url.query.decode()) == {"query": [SELECT]}
    assert recorder.last.method == "GET"


def test_an_ask_comes_back_as_an_ask_result(sparql, recorder):
    recorder.reply(content=ASK_JSON, content_type="application/sparql-results+json")
    result = sparql.execute("ASK { ?s ?p ?o }")
    assert result == AskResult(value=True)
    assert bool(result) is True


def test_a_construct_comes_back_as_a_graph_result(sparql, recorder):
    recorder.reply(content=b"<a> <b> <c> .", content_type="text/turtle;charset=utf-8")
    result = sparql.execute("CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }")
    assert isinstance(result, GraphResult)
    assert result.format is GraphFormat.TURTLE
    assert result.text == "<a> <b> <c> ."
    assert recorder.last.headers["accept"].startswith("text/turtle")


def test_a_graph_query_can_pick_its_serialization(sparql, recorder):
    sparql.execute("DESCRIBE <http://example.org/a>", result_format=GraphFormat.NTRIPLES)
    assert recorder.last.headers["accept"].startswith("application/n-triples")


def test_an_update_comes_back_as_an_update_result(sync_client, recorder):
    recorder.reply(status=204)
    client = SparqlClient(ENDPOINT, update_endpoint="http://example.org/update", client=sync_client)
    assert client.execute("INSERT DATA { <a> <b> <c> }") == UpdateResult(status=204)
    assert recorder.last.method == "POST"
    assert str(recorder.last.url) == "http://example.org/update"
    assert parse_qs(recorder.last.content.decode()) == {"update": ["INSERT DATA { <a> <b> <c> }"]}


def test_raw_hands_the_body_over_unparsed(sync_client, recorder):
    recorder.reply(content=b"s,n\n1,2\n", content_type="text/csv")
    body = SparqlClient(ENDPOINT, client=sync_client).execute(SELECT, result_format=SolutionFormat.CSV, raw=True)
    assert body.text == "s,n\n1,2\n"
    assert body.format is SolutionFormat.CSV
    assert recorder.last.headers["accept"] == "text/csv"


def test_raw_falls_back_to_the_format_the_form_would_have_used(sparql):
    body = sparql.execute(SELECT, raw=True)
    assert body.format is SolutionFormat.JSON
    assert body.data == SELECT_JSON


def test_a_format_the_form_cannot_answer_in_is_refused_before_any_request(sparql, recorder):
    with pytest.raises(QueryFormError, match="pass raw=True"):
        sparql.execute(SELECT, result_format=GraphFormat.TURTLE)
    assert recorder.requests == []


def test_an_unreadable_query_is_refused_before_any_request(sparql, recorder):
    with pytest.raises(QueryFormError, match="cannot tell the query form"):
        sparql.execute("not a query")
    assert recorder.requests == []


def test_every_request_carries_the_user_agent_and_accept_headers(sparql, recorder):
    sparql.execute(SELECT)
    assert recorder.last.headers["user-agent"] == USER_AGENT
    assert recorder.last.headers["accept"].startswith("application/sparql-results+json")


def test_extra_headers_are_merged_in(sync_client, recorder):
    SparqlClient(ENDPOINT, client=sync_client, user_agent="me/1", headers={"X-Trace": "1"}).execute(SELECT)
    assert recorder.last.headers["user-agent"] == "me/1"
    assert recorder.last.headers["x-trace"] == "1"


def test_an_error_status_becomes_a_typed_exception(sync_client, recorder):
    recorder.reply(status=400, content=b"Parse error")
    with pytest.raises(BadQueryError, match="Parse error") as excinfo:
        SparqlClient(ENDPOINT, client=sync_client).execute(SELECT)
    assert excinfo.value.status == 400


def test_forcing_post_moves_the_query_into_the_body(sync_client, recorder):
    SparqlClient(ENDPOINT, client=sync_client, method=HttpMethod.POST).execute(SELECT)
    assert recorder.last.method == "POST"
    assert parse_qs(recorder.last.content.decode()) == {"query": [SELECT]}


def test_direct_encoding_sends_the_query_verbatim(sync_client, recorder):
    client = SparqlClient(ENDPOINT, client=sync_client, method=HttpMethod.POST, encoding=RequestEncoding.DIRECT)
    client.execute(SELECT)
    assert recorder.last.content == SELECT.encode()
    assert recorder.last.headers["content-type"] == "application/sparql-query"


def test_the_dataset_and_extra_parameters_reach_the_url(sync_client, recorder):
    SparqlClient(
        ENDPOINT,
        client=sync_client,
        default_graph=["http://g/1"],
        named_graph=["http://n/1"],
        params={"timeout": "5"},
    ).execute(SELECT)
    assert parse_qs(recorder.last.url.query.decode()) == {
        "timeout": ["5"],
        "default-graph-uri": ["http://g/1"],
        "named-graph-uri": ["http://n/1"],
        "query": [SELECT],
    }


def test_the_config_is_readable(sparql):
    assert sparql.config.endpoint == ENDPOINT


def test_an_injected_client_is_left_open(sync_client):
    with SparqlClient(ENDPOINT, client=sync_client):
        pass
    assert not sync_client.is_closed


def test_an_owned_client_is_closed_on_exit():
    with SparqlClient(ENDPOINT) as client:
        transport = client._client  # noqa: SLF001
    assert transport.is_closed


@pytest.mark.asyncio
async def test_the_async_client_mirrors_the_sync_one(async_client, recorder):
    async with AsyncSparqlClient(ENDPOINT, client=async_client) as sparql:
        result = await sparql.execute(SELECT)
        assert isinstance(result, SelectResult)
        assert result[0]["s"] == Uri("http://example.org/a")

        recorder.reply(content=ASK_JSON, content_type="application/sparql-results+json")
        assert await sparql.execute("ASK { ?s ?p ?o }") == AskResult(value=True)

        recorder.reply(content=b"<a> <b> <c> .", content_type="text/turtle")
        graph = await sparql.execute("CONSTRUCT { } WHERE { }")
        assert isinstance(graph, GraphResult)
        assert graph.text == "<a> <b> <c> ."

        recorder.reply(content=SELECT_JSON, content_type="application/sparql-results+json")
        body = await sparql.execute(SELECT, result_format=SolutionFormat.JSON, raw=True)
        assert body.data == SELECT_JSON

        recorder.reply(status=204)
        assert await sparql.execute("DROP ALL") == UpdateResult(status=204)

    assert not async_client.is_closed


@pytest.mark.asyncio
async def test_the_async_client_refuses_a_format_the_form_cannot_answer_in(async_client):
    async with AsyncSparqlClient(ENDPOINT, client=async_client) as sparql:
        with pytest.raises(QueryFormError):
            await sparql.execute("ASK { }", result_format=GraphFormat.TURTLE)


@pytest.mark.asyncio
async def test_the_async_client_raises_on_an_error_status(async_client, recorder):
    recorder.reply(status=500, content=b"boom")
    async with AsyncSparqlClient(ENDPOINT, client=async_client) as sparql:
        with pytest.raises(EndpointError, match="boom"):
            await sparql.execute(SELECT)


@pytest.mark.asyncio
async def test_an_owned_async_client_is_closed_on_exit():
    async with AsyncSparqlClient(ENDPOINT) as sparql:
        transport = sparql._client  # noqa: SLF001
    assert transport.is_closed


def test_expect_lets_a_matching_query_through(sparql):
    result = sparql.execute(SELECT, expect=QueryForm.SELECT)
    assert isinstance(result, SelectResult)


@pytest.mark.parametrize(
    ("query", "expect"),
    [
        (SELECT, "ASK"),
        ("ASK { ?s ?p ?o }", "SELECT"),
        ("CONSTRUCT { } WHERE { }", "DESCRIBE"),
        ("DROP ALL", "SELECT"),
        (SELECT, "INSERT"),
    ],
)
def test_expect_refuses_another_form_before_any_request(sparql, recorder, query, expect):
    with pytest.raises(QueryFormError, match=f"expected a {expect} query"):
        sparql.execute(query, expect=QueryForm(expect))
    assert recorder.requests == []


def test_a_t_string_query_is_rendered_and_sent(sparql, recorder):
    subject = Uri("http://example.org/a")
    name = 'O"Brien'
    sparql.execute(t"SELECT ?s WHERE {{ {subject} <http://e/name> {name} }}")
    assert recorder.last.url.params["query"] == (
        'SELECT ?s WHERE { <http://example.org/a> <http://e/name> "O\\"Brien" }'
    )


def test_a_malformed_query_never_reaches_the_endpoint(sparql, recorder):
    with pytest.raises(QuerySyntaxError, match="unclosed"):
        sparql.execute("SELECT ?s WHERE { ?s ?p ?o")
    assert recorder.requests == []


def test_a_parsed_query_can_be_reused(sparql, recorder):
    parsed = parse(SELECT)
    sparql.execute(parsed)
    sparql.execute(parsed)
    assert [str(request.url.params["query"]) for request in recorder.requests] == [SELECT, SELECT]


@pytest.mark.asyncio
async def test_the_async_client_honours_expect(async_client, recorder):
    async with AsyncSparqlClient(ENDPOINT, client=async_client) as sparql:
        assert isinstance(await sparql.execute(SELECT, expect=QueryForm.SELECT), SelectResult)
        with pytest.raises(QueryFormError, match="expected a ASK query"):
            await sparql.execute(SELECT, expect=QueryForm.ASK)
