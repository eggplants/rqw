from __future__ import annotations

import json

import pytest
from conftest import SELECT_JSON

from rqw import __version__
from rqw.cli import format_table, main, parse_args
from rqw.protocol import GraphFormat, HttpMethod, SolutionFormat
from rqw.results import parse_select

SELECT = "SELECT ?s ?n WHERE { ?s ?p ?n }"


@pytest.fixture(autouse=True)
def _stub_client(monkeypatch, sync_client):
    """Give every CLI invocation the mock transport instead of a real socket."""
    import rqw.cli  # noqa: PLC0415

    original = rqw.cli.SparqlClient

    def build(endpoint, **kwargs):
        # An injected client owns its own auth, so hand the CLI's credentials over to it.
        if (auth := kwargs.get("auth")) is not None:
            sync_client.auth = auth
        return original(endpoint, **{**kwargs, "client": sync_client})

    monkeypatch.setattr(rqw.cli, "SparqlClient", build)


def test_version_flag_prints_the_version(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_a_query_source_is_required(capsys):
    with pytest.raises(SystemExit):
        main([])
    assert "one of the arguments" in capsys.readouterr().err


def test_a_query_is_sent_and_the_json_is_pretty_printed(capsys, recorder):
    main(["-Q", SELECT])
    assert json.loads(capsys.readouterr().out)["head"]["vars"] == ["s", "n"]
    assert recorder.last.url.params["query"] == SELECT


def test_the_endpoint_and_dataset_come_from_the_command_line(recorder):
    main(["-Q", SELECT, "-e", "http://example.org/other", "-g", "http://g/", "-P", "timeout=5"])
    assert recorder.last.url.host == "example.org"
    assert recorder.last.url.params["default-graph-uri"] == "http://g/"
    assert recorder.last.url.params["timeout"] == "5"


def test_a_query_can_be_read_from_a_file(tmp_path, recorder):
    path = tmp_path / "q.rq"
    path.write_text(SELECT, encoding="utf-8")
    main(["-f", str(path)])
    assert recorder.last.url.params["query"] == SELECT


def test_a_query_can_be_read_from_stdin(monkeypatch, recorder):
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(SELECT))
    main(["-f", "-"])
    assert recorder.last.url.params["query"] == SELECT


def test_a_missing_file_is_reported(capsys):
    with pytest.raises(SystemExit):
        main(["-f", "/nonexistent/q.rq"])
    assert "cannot read" in capsys.readouterr().err


def test_a_non_json_format_is_printed_verbatim(capsys, recorder):
    recorder.reply(content=b"s,n\r\n1,2\r\n", content_type="text/csv")
    main(["-Q", SELECT, "-F", "csv"])
    assert capsys.readouterr().out.strip() == "s,n\r\n1,2"
    assert recorder.last.headers["accept"] == "text/csv"


def test_the_table_flag_renders_a_table(capsys, recorder):
    recorder.reply(content=SELECT_JSON, content_type="application/sparql-results+json")
    main(["-Q", SELECT, "--table"])
    assert capsys.readouterr().out == (
        "s                    | n\n---------------------+--\nhttp://example.org/a | 1\n_:b0                 |  \n"
    )


def test_basic_auth_reaches_the_request(recorder):
    main(["-Q", SELECT, "-a", "BASIC", "-u", "alice", "-p", "secret"])
    assert recorder.last.headers["authorization"].startswith("Basic ")


def test_an_endpoint_error_exits_with_one(capsys, recorder):
    recorder.reply(status=400, content=b"Parse error")
    with pytest.raises(SystemExit) as excinfo:
        main(["-Q", SELECT])
    assert excinfo.value.code == 1
    assert "rqw: " in capsys.readouterr().err


def test_an_undetectable_query_form_exits_with_one(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["-Q", "not a query"])
    assert excinfo.value.code == 1
    assert "cannot tell the query form" in capsys.readouterr().err


def test_an_update_is_posted(recorder):
    recorder.reply(status=204)
    main(["-Q", "DROP ALL", "--update-endpoint", "http://example.org/update"])
    assert recorder.last.method == "POST"


def test_the_parser_maps_the_option_values():
    parsed = parse_args(["-Q", SELECT, "-F", "turtle", "-m", "POST", "-H", "X-A=1"])
    assert parsed.format is GraphFormat.TURTLE
    assert parsed.method is HttpMethod.POST
    assert parsed.header == [("X-A", "1")]


def test_the_parser_rejects_a_header_without_an_equals_sign(capsys):
    with pytest.raises(SystemExit):
        parse_args(["-Q", SELECT, "-H", "nope"])
    assert "KEY=VALUE" in capsys.readouterr().err


def test_the_default_format_is_json():
    assert parse_args(["-Q", SELECT]).format is SolutionFormat.JSON


def test_format_table_handles_a_result_with_no_rows():
    empty = parse_select(b'{"head": {"vars": ["a", "bb"]}, "results": {"bindings": []}}')
    assert format_table(empty) == "a | bb\n--+---"


def test_digest_auth_is_offered(recorder):
    main(["-Q", SELECT, "-a", "DIGEST", "-u", "alice", "-p", "secret"])
    assert recorder.requests


def test_quiet_silences_warnings(recorder):
    import warnings  # noqa: PLC0415

    with warnings.catch_warnings():
        main(["-Q", SELECT, "-q"])
        with warnings.catch_warnings(record=True) as caught:
            warnings.warn("hush", RuntimeWarning, stacklevel=1)
    assert caught == []


def test_table_refuses_a_query_that_is_not_a_select(capsys, recorder):
    recorder.reply(content=b"<a> <b> <c> .", content_type="text/turtle")
    with pytest.raises(SystemExit) as excinfo:
        main(["-Q", "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }", "--table"])
    assert excinfo.value.code == 1
    assert "--table needs a SELECT query" in capsys.readouterr().err
