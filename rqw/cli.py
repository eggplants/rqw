"""Command line entry point for rqw."""

from __future__ import annotations

import json
import shutil
import sys
import warnings
from argparse import (
    ArgumentDefaultsHelpFormatter,
    ArgumentParser,
    ArgumentTypeError,
    Namespace,
    RawDescriptionHelpFormatter,
)
from pathlib import Path
from typing import TYPE_CHECKING, Final

import httpx

from . import __version__
from .client import SparqlClient
from .exceptions import QueryFormError, RqwError
from .protocol import GraphFormat, HttpMethod, RequestEncoding, SolutionFormat, parse_format
from .results import SelectResult

if TYPE_CHECKING:
    from .protocol import ResultFormat

DEFAULT_ENDPOINT: Final = "https://dbpedia.org/sparql"
FORMATS: Final = (*SolutionFormat, *GraphFormat)
AUTHS: Final = ("BASIC", "DIGEST")


class HelpFormatter(ArgumentDefaultsHelpFormatter, RawDescriptionHelpFormatter):
    """Show argument defaults while keeping the description's own line breaks."""


def _read_query(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        msg = f"cannot read {path}: {exc.strerror}"
        raise ArgumentTypeError(msg) from exc


def _pair(text: str) -> tuple[str, str]:
    key, sep, value = text.partition("=")
    if not sep:
        msg = f"expected KEY=VALUE, got {text!r}"
        raise ArgumentTypeError(msg)
    return key, value


def format_table(result: SelectResult) -> str:
    """Lay a solution sequence out as a fixed-width table.

    Args:
        result: The solutions to render.

    Returns:
        The table, without a trailing newline.
    """
    header = list(result.variables)
    rows = [[str(row[name]) if name in row else "" for name in header] for row in result]
    widths = [max(len(name), *(len(row[i]) for row in rows)) if rows else len(name) for i, name in enumerate(header)]
    line = "-+-".join("-" * width for width in widths)
    body = [" | ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True)) for row in rows]
    return "\n".join([" | ".join(name.ljust(width) for name, width in zip(header, widths, strict=True)), line, *body])


def parse_args(args: list[str] | None = None) -> Namespace:
    """Parse the command line.

    Args:
        args: Arguments to parse instead of `sys.argv[1:]`. Used by the tests.

    Returns:
        The parsed arguments.
    """
    parser = ArgumentParser(
        prog="rqw",
        description="Query a SPARQL endpoint.",
        epilog="allowed FORMAT:\n  - " + "\n  - ".join(FORMATS),
        formatter_class=lambda prog: HelpFormatter(
            prog,
            width=shutil.get_terminal_size(fallback=(120, 50)).columns,
            max_help_position=40,
        ),
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("-Q", "--query", metavar="QUERY", help="query text")
    source.add_argument(
        "-f", "--file", metavar="FILE", type=_read_query, dest="query", help="read the query from a file (stdin: -)"
    )
    parser.add_argument("-e", "--endpoint", metavar="URI", default=DEFAULT_ENDPOINT, help="SPARQL endpoint")
    parser.add_argument("--update-endpoint", metavar="URI", help="endpoint for update operations, when it differs")
    parser.add_argument(
        "-F", "--format", metavar="FORMAT", type=parse_format, default=SolutionFormat.JSON, help="response format"
    )
    parser.add_argument(
        "-m",
        "--method",
        metavar="METHOD",
        type=HttpMethod,
        choices=tuple(HttpMethod),
        help="HTTP method (default: GET, POST for long queries)",
    )
    parser.add_argument(
        "--encoding",
        type=RequestEncoding,
        choices=tuple(RequestEncoding),
        default=RequestEncoding.URL_ENCODED,
        help="how a POST carries the query",
    )
    parser.add_argument("-a", "--auth", metavar="AUTH", choices=AUTHS, help="HTTP auth scheme")
    parser.add_argument("-u", "--username", metavar="ID", default="", help="username for auth")
    parser.add_argument("-p", "--password", metavar="PW", default="", help="password for auth")
    parser.add_argument(
        "-g", "--default-graph", metavar="URI", action="append", default=[], help="default-graph-uri (repeatable)"
    )
    parser.add_argument(
        "-n", "--named-graph", metavar="URI", action="append", default=[], help="named-graph-uri (repeatable)"
    )
    parser.add_argument(
        "-H",
        "--header",
        metavar="KEY=VALUE",
        type=_pair,
        action="append",
        default=[],
        help="extra HTTP header (repeatable)",
    )
    parser.add_argument(
        "-P",
        "--param",
        metavar="KEY=VALUE",
        type=_pair,
        action="append",
        default=[],
        help="extra query-string parameter (repeatable)",
    )
    parser.add_argument("-t", "--timeout", metavar="SEC", type=float, default=30.0, help="request timeout")
    parser.add_argument("-T", "--table", action="store_true", help="print SELECT results as a table")
    parser.add_argument("-q", "--quiet", action="store_true", help="suppress warnings")
    parser.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    return parser.parse_args(args)


def _render(client: SparqlClient, parsed: Namespace) -> str:
    if parsed.table:
        result = client.execute(parsed.query)
        if not isinstance(result, SelectResult):
            msg = "--table needs a SELECT query"
            raise QueryFormError(msg)
        return format_table(result)
    result_format: ResultFormat = parsed.format
    body = client.execute(parsed.query, result_format=result_format, raw=True)
    if result_format in {SolutionFormat.JSON, GraphFormat.JSONLD} and body.data.strip():
        return json.dumps(body.json(), indent=2, ensure_ascii=False)
    return body.text


def main(args: list[str] | None = None) -> None:
    """Run the command.

    Args:
        args: Arguments to parse instead of `sys.argv[1:]`. Used by the tests.

    Raises:
        SystemExit: With status 1 when the endpoint or the query is at fault.
    """
    parsed = parse_args(args)
    if parsed.quiet:
        warnings.simplefilter("ignore")
    auth = None
    if parsed.auth == "DIGEST":
        auth = httpx.DigestAuth(parsed.username, parsed.password)
    elif parsed.auth == "BASIC":
        auth = httpx.BasicAuth(parsed.username, parsed.password)

    try:
        with SparqlClient(
            parsed.endpoint,
            update_endpoint=parsed.update_endpoint,
            default_graph=parsed.default_graph,
            named_graph=parsed.named_graph,
            method=parsed.method,
            encoding=parsed.encoding,
            params=parsed.param,
            timeout=parsed.timeout,
            headers=dict(parsed.header),
            auth=auth,
        ) as client:
            print(_render(client, parsed))
    except (RqwError, httpx.HTTPError) as exc:
        print(f"rqw: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
