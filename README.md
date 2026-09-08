# SPARQL Endpoint Wrapper

[![PyPI](
  <https://img.shields.io/pypi/v/rqw?color=blue>
  )](
  <https://pypi.org/project/rqw/>
) [![CI](
  <https://github.com/eggplants/rqw/actions/workflows/ci.yml/badge.svg>
  )](
  <https://github.com/eggplants/rqw/actions/workflows/ci.yml>
)

[![ghcr size](
  <https://ghcr-badge.egpl.dev/eggplants/rqw/size>
)](
  <https://github.com/eggplants/rqw/pkgs/container/rqw>
)

SPARQL Endpoint interface, inspired by [SPARQLWrapper](https://github.com/RDFLib/sparqlwrapper).

- **One entry point, typed results.** `execute()` reads the query form and
  answers with `SelectResult`, `AskResult`, `GraphResult` or `UpdateResult` --
  a union you `match` on, or narrow up front with `expect=`. Rows hold `Uri`,
  `BlankNode`, `Literal` or `QuotedTriple`, not nested `dict`s, and literals
  decode their own `xsd` datatype on request.
- **t-strings, parsed here.** `execute(t"...")` renders each interpolated value
  as a complete RDF term and then proves it still occupies one token, so a value
  cannot end a literal early or start a comment. Queries are tokenized against
  the SPARQL 1.1 grammar before they are sent.
- **Typed errors.** Every HTTP status the SPARQL protocol gives meaning to has
  its own exception, carrying the endpoint's own parser message.
- **Fast.** One `httpx` connection pool per client, `asyncio` support, and no RDF
  parsing you did not ask for.
- **The query decides.** `rqw` routes updates to the update endpoint on their
  own, picks `GET` or `POST` by URL length, and refuses a result format the
  query form cannot answer in before a single byte goes out.

## Installation

```bash
# mise via github release
mise use -g github:eggplants/rqw

# mise via pipx
mise use -g pipx:rqw

# pipx
pipx install rqw

# pip
pip install rqw
```

### Docker

```bash
docker pull ghcr.io/eggplants/rqw

docker run --rm ghcr.io/eggplants/rqw -Q 'SELECT * WHERE { ?s ?p ?o } LIMIT 1'
```

## CLI

```shellsession
$ rqw -Q 'SELECT ?s WHERE { ?s a <http://dbpedia.org/ontology/Fish> } LIMIT 3' --table
s
--------------------------------------
http://dbpedia.org/resource/Actinopoda
http://dbpedia.org/resource/Alfonsino
http://dbpedia.org/resource/Amberjack

$ rqw -e https://query.wikidata.org/sparql -f query.rq -F csv

$ echo 'ASK { ?s ?p ?o }' | rqw -f -
{
  "head": {},
  "boolean": true
}
```

`--help` lists the rest: `-F/--format`, `-m/--method`, `-a/--auth`, `-g/--default-graph`,
`-H/--header`, `-P/--param`, `-t/--timeout`.

## Library

```python
from rqw import SelectResult, SparqlClient

with SparqlClient("https://dbpedia.org/sparql") as sparql:
    match sparql.execute("""
        SELECT ?fish ?name WHERE {
          ?fish a <http://dbpedia.org/ontology/Fish> ; rdfs:label ?name .
          FILTER (lang(?name) = 'en')
        } LIMIT 5
    """):
        case SelectResult() as rows:
            for row in rows:
                print(row["fish"], row["name"])
```

`execute()` is the only way in. It reads the query form off the query itself and
answers with the member of `QueryResult` that form calls for:

| query form | result | |
| --- | --- | --- |
| `SELECT` | `SelectResult` | a sequence of rows |
| `ASK` | `AskResult` | `.value`, and truthy on its own |
| `CONSTRUCT`, `DESCRIBE` | `GraphResult` | the serialized graph, `.text` or `.data` |
| `INSERT`, `DELETE`, `DROP`, ... | `UpdateResult` | `.status`, POSTed to the update endpoint |

```python
match sparql.execute(query):
    case SelectResult() as rows:
        print(len(rows))
    case AskResult(value=answer):
        print(answer)
    case GraphResult() as graph:
        print(graph.text)
    case UpdateResult(status=status):
        print(status)
```

Rows are mappings from variable name to term; a variable the query left unbound
is simply absent, so `"name" in row` is the way to ask. Every term prints as
itself, so `str(row["fish"])` always works -- but a term is one of four things,
and reaching past `str` means saying which:

```python
from rqw import Literal, Uri

match row["name"]:
    case Literal(value=value, language="en"):
        ...
    case Uri(value=uri):
        ...

match row["count"]:
    case Literal() as count:
        count.as_python()  # 42, from an xsd:integer literal
```

### t-strings

`execute` takes a `t"..."` template. Values interpolated into it are rendered as
RDF terms -- quoted, escaped and typed -- never as query text:

```python
from rqw import Uri

subject, name = Uri("http://example.org/a"), 'O"Brien'
sparql.execute(t"SELECT ?s WHERE {{ {subject} <http://e/name> {name} }}")
# sent as: SELECT ?s WHERE { <http://example.org/a> <http://e/name> "O\"Brien" }
```

SPARQL braces have to be doubled, because `{` is how a template marks an
interpolation. That is the one piece of friction and there is no way around it:
it is Python's own syntax.

| Python | SPARQL |
| --- | --- |
| `Uri`, `BlankNode`, `Literal`, `QuotedTriple` | the term itself |
| `str` | a quoted literal, `"..."` |
| `bool` | `true` / `false` |
| `int`, `float`, `Decimal` | a numeric literal |
| `date`, `time`, `datetime` | `"..."^^xsd:...` |
| a list or tuple | its items, space separated -- what `VALUES` wants |
| a nested `t"..."` | spliced in, values and all |

A `str` becomes a literal, never an IRI, because that is the safe way round.
Ask for the other reading explicitly with a format spec: `{value:iri}` for an
IRI, `{value:var}` for a variable.

The safety does not rest on the escaping alone. After rendering, `rqw` tokenizes
the whole query and checks that every value it spliced in still lines up with a
token boundary, so a value that tried to break out of a literal is refused
rather than sent:

```python
evil = '" } INSERT DATA { <a> <b> "pwned'
sparql.execute(t"SELECT ?s WHERE {{ ?s ?p {evil} }}")
# one literal, no second operation:
#   SELECT ?s WHERE { ?s ?p "\" } INSERT DATA { <a> <b> \"pwned" }

sparql.execute(t'SELECT ?s WHERE {{ ?s ?p "{evil}" }}')
# QuerySyntaxError: an interpolated value cannot appear inside a token
```

`rqw.parse` gives you the same `Query` on its own, which `execute` accepts
directly when you want to send one query many times.

### Narrowing with expect

`expect` names the form the query must be written in. The return type follows,
and a query of any other form is refused before the request goes out:

```python
rows = sparql.execute(query, expect=QueryForm.SELECT)   # -> SelectResult
answer = sparql.execute(query, expect=QueryForm.ASK)    # -> AskResult
graph = sparql.execute(query, expect=QueryForm.DESCRIBE, result_format=GraphFormat.NTRIPLES)

sparql.execute("ASK { ?s ?p ?o }", expect=QueryForm.SELECT)
# QueryFormError: expected a SELECT query, got ASK
```

### What is checked before sending

The query is tokenized against the terminal productions of `SPARQL 1.1
<https://www.w3.org/TR/sparql11-query/>`, which catches an unterminated literal,
a stray character, an unbalanced `{}`, `()` or `[]`, a malformed `BASE` or
`PREFIX`, and text that names no query form. Everything past that -- whether the
`WHERE` clause makes sense, whether a function takes those arguments -- is left
to the endpoint, which has to parse the query anyway.

### Formats, and taking the body unparsed

`CONSTRUCT` and `DESCRIBE` are the only forms that leave the serialization open,
since the rest are read out of the SPARQL JSON results format:

```python
sparql.execute("DESCRIBE <http://dbpedia.org/resource/Tuna>", result_format=GraphFormat.NTRIPLES)
```

`raw=True` skips parsing entirely and hands back a `RawResult` -- one type, no
union to narrow -- in whatever format you ask for:

```python
csv = sparql.execute(query, result_format=SolutionFormat.CSV, raw=True)
csv.text          # 's,n\r\n...'
turtle = sparql.execute("CONSTRUCT { } WHERE { }", raw=True).data  # feed it to rdflib
```

Asking for a format a form cannot answer in is a `QueryFormError`, raised before
the request goes out -- `result_format=SolutionFormat.CSV` without `raw=True`
does not even type-check.

### asyncio

`AsyncSparqlClient` has the same surface with `execute` awaitable. Queries sent
through one client share its connection pool, so `gather` really does run them
at once.

```python
import asyncio

from rqw import AsyncSparqlClient

async def main() -> None:
    async with AsyncSparqlClient("https://dbpedia.org/sparql") as sparql:
        a, b = await asyncio.gather(
            sparql.execute("SELECT * WHERE { ?s ?p ?o } LIMIT 10"),
            sparql.execute("ASK { ?s ?p ?o }"),
        )

asyncio.run(main())
```

### Errors

```python
from rqw import BadQueryError, EndpointError, SparqlHttpError

try:
    sparql.execute("SELECT ?s WHERE {")
except BadQueryError as error:
    print(error.status, error.body)  # 400, the endpoint's own parser message
```

`BadQueryError`, `UnauthorizedError`, `ForbiddenError`, `EndpointNotFoundError`,
`UriTooLongError`, `UnsupportedMediaTypeError` and `EndpointError` all derive from
`SparqlHttpError`, and everything `rqw` raises derives from `RqwError`.

### Endpoint settings

```python
SparqlClient(
    "https://example.org/sparql",
    update_endpoint="https://example.org/update",
    default_graph=["http://example.org/g1"],
    method=HttpMethod.POST,          # default: GET while the URL is short enough
    encoding=RequestEncoding.DIRECT, # application/sparql-query, skips form encoding
    params={"timeout": "5000"},      # endpoint-specific knobs
    headers={"X-Trace": "1"},
    auth=("user", "password"),
    timeout=30.0,
)
```

Passing `client=httpx.Client(...)` swaps in your own transport, retries and
proxies; `rqw` then leaves closing it to you.

## License

[MIT License](
  <https://github.com/eggplants/rqw/blob/master/LICENSE.txt>
)
