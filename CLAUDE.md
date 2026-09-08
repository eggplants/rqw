# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

SPARQL Endpoint interface, compatible with SPARQLWrapper.

<!-- Replace this with what the project actually is: the problem it solves, the
     shape of its public surface, and the constraints worth knowing up front
     (required dependencies you deliberately do or do not have, and why). -->

`TODO.md` tracks the one-time repository setup that still has to be done by hand.

## Commands

Dependencies are managed with [uv](https://docs.astral.sh/uv/) and every task is
defined in `mise.toml`, which is the canonical list.

```bash
uv sync --all-groups                   # install runtime + dev + docs groups
mise run pytest                        # run the test suite
uv run pytest tests/test_rqw.py::test_version_is_available  # a single test
mise run ruff                          # format + autofix (uv format)
mise run ty                            # type check (uvx ty check)
mise run pymarkdown                    # markdown lint
mise run pyproject-fmt                 # normalize pyproject.toml
mise run pre-commit                    # ruff + ty + pymarkdown + pyproject-fmt
mise run ci                            # pre-commit + pytest-cov -- what CI runs
mise run build                         # build sdist + wheel
mise run docs                          # pdoc API docs into ./docs
mise run pinup                         # update the pinned action/image digests
mise run build-binary                  # PyInstaller standalone binary into ./dist
```

The venv is tied to the absolute repo path (`uv sync` bakes it into script shebangs). If the
repo directory gets renamed or moved, delete `.venv/` and `uv sync` again rather than debugging
"No such file or directory" / `ModuleNotFoundError` -- it is a stale interpreter path, not a
code bug.

Lint config lives in `pyproject.toml`: Ruff with `lint.select = ["ALL"]` and `line-length = 120`.
Prefer a targeted `lint.per-file-ignores` entry with a comment over a scattered `# noqa`.

## Architecture

<!-- Describe the modules and how they are layered, in dependency order, and say
     what each one is responsible for. Name the invariants that are easy to break
     and the reason they exist -- that is the part that is not in the code. -->

`httpx` is the only runtime dependency; RDF payloads are handed back as text and never parsed.

- **`rqw/exceptions.py`** -- the `RqwError` hierarchy and `raise_for_status`, which maps an
  HTTP status onto the exception the SPARQL protocol gives it. Imported by everything else.
- **`rqw/terms.py`** -- `Uri`/`BlankNode`/`Literal`/`QuotedTriple` and the `xsd` decoders
  behind `Literal.as_python`.
- **`rqw/protocol.py`** -- `QueryForm`, result formats and `Accept` headers, `choose_format`,
  and `build_request`, which turns an `EndpointConfig` plus a query into a `RequestSpec`.
  Everything here is pure, and it has to stay that way: that is what lets the sync and the
  async client share one implementation instead of drifting apart.
- **`rqw/lexer.py`** -- the terminal productions [139]-[173] of [SPARQL 1.1][sparql] as one
  alternation, ordered so the longest match wins. The order is load-bearing: the long string
  forms before the short ones, `DOUBLE` before `DECIMAL` before `INTEGER`, and `IRIREF` before
  the `<` operator. Reach for the spec before touching it.
- **`rqw/parser.py`** -- `parse`, which takes a t-string or plain text and returns a `Query`
  carrying its form and its rendered text. Interpolated values are rendered as whole RDF terms
  and then checked to still occupy exactly one token; that check is the safety property, not
  the escaping, so do not drop it when adding a value type to `render_value`. Only the lexical
  grammar, the prologue, the form and delimiter nesting are validated -- the endpoint parses
  the rest.
- **`rqw/results.py`** -- the `QueryResult` union (`SelectResult`, `AskResult`, `GraphResult`,
  `UpdateResult`), `RawResult`, the SPARQL JSON parsers, and `interpret`, which picks the
  member a query form calls for.
- **`rqw/client.py`** -- `SparqlClient` and `AsyncSparqlClient`, thin transport layers over
  `protocol` and `results`. Each exposes a single `execute`, overloaded on `raw` so that
  `raw=True` returns `RawResult` alone rather than widening the union -- keep the two
  overloads and the implementation signature in step, and mirror any change in both clients.
  `expect` adds one overload per form on top of that, so the six overloads have to stay in
  step with `QueryForm`. Either accepts `client=` so callers (and the tests) can inject their
  own `httpx` client, in which case closing it stays the caller's job.
- **`rqw/__init__.py`** -- package version, read from the installed
  distribution metadata (`0.0.0` when running from a source tree with no tags), plus the
  public re-exports.
- **`rqw/cli.py`** -- argparse entry point (`rqw`). Flag names follow the `rqw` CLI that
  SPARQLWrapper ships, so `-Q`/`-f`/`-F`/`-e`/`-m`/`-a`/`-u`/`-p`/`-q` keep their meaning.
  `main()` takes an optional argument list so the tests can drive it without touching `sys.argv`.
- **`rqw/__main__.py`** -- makes `python -m rqw` work.

## Versioning and releases

Versions come from git tags via `uv-dynamic-versioning`; nothing in the repo hard-codes one.
Pushing a `v*.*.*` tag runs `build-binaries.yml`, which builds one binary per OS/arch on native
runners (PyInstaller cannot cross-compile), attaches them to a **draft** release and publishes it
afterwards -- immutable releases lock the assets of an already published release. `release.yml`
then reacts to `release: [published]` and does the PyPI and GHCR publish.

## Testing conventions

Tests live in `tests/` and mirror the module split 1:1. `tests/**` has its own
`lint.per-file-ignores` block, so assertions and missing annotations are fine there.

Nothing in the suite touches the network: `tests/conftest.py` hands out an `httpx.MockTransport`
wrapped in a `Recorder` that captures each outgoing request and replays a canned response.
Inject it with `SparqlClient(..., client=sync_client)` and assert on `recorder.last`.

[sparql]: https://www.w3.org/TR/sparql11-query/
