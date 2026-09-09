# rqw

[![PyPI](
  <https://img.shields.io/pypi/v/rqw?color=blue>
  )](
  <https://pypi.org/project/rqw/>
) [![CI](
  <https://github.com/eggplants/rqw/actions/workflows/ci.yml/badge.svg>
  )](
  <https://github.com/eggplants/rqw/actions/workflows/ci.yml>
) [![ghcr size](
  <https://ghcr-badge.egpl.dev/eggplants/rqw/size>
)](
  <https://github.com/eggplants/rqw/pkgs/container/rqw>
)

SPARQL Endpoint interface, inspired by [SPARQLWrapper](https://github.com/RDFLib/sparqlwrapper)

- A typed result per query form, and a typed error per SPARQL HTTP status
- t-string queries, checked against [the SPARQL 1.1 grammar](https://www.w3.org/TR/sparql11-query/)
- `httpx` only: one connection pool per client, `asyncio` support, no RDF parsing

## Install

```bash
# pip
pip install rqw

# pipx
pipx install rqw

# mise
mise use -g github:eggplants/rqw

# docker
docker pull ghcr.io/eggplants/rqw
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

Use `rqw --help` for more information.

## Library

### Overview

```python
# sync
from rqw import SelectResult, SparqlClient

with SparqlClient("https://dbpedia.org/sparql") as sparql:
    match sparql.execute("SELECT ?s ?p WHERE { ?s ?p ?o } LIMIT 5"):
        case SelectResult() as rows:
            for row in rows:
                print(row["s"], row["p"])

# async
from rqw import AsyncSparqlClient

async def main() -> None:
    async with AsyncSparqlClient("https://dbpedia.org/sparql") as sparql:
        a, b = await asyncio.gather(
            sparql.execute("SELECT * WHERE { ?s ?p ?o } LIMIT 10"),
            sparql.execute("ASK { ?s ?p ?o }"),
        )

asyncio.run(main())
```

`execute()` is the only entry point. It reads the query form off the query and
returns the matching member of `QueryResult`:

| query form | result | |
| --- | --- | --- |
| `SELECT` | `SelectResult` | a sequence of rows |
| `ASK` | `AskResult` | `.value`, and truthy on its own |
| `CONSTRUCT`, `DESCRIBE` | `GraphResult` | the serialized graph, `.text` or `.data` |
| `INSERT`, `DELETE`, `DROP`, ... | `UpdateResult` | `.status`, POSTed to the update endpoint |

### Narrowing with expect

`expect` names the form the query must take. The return type follows, and any
other form is refused before the request goes out:

```python
rows = sparql.execute(query, expect=QueryForm.SELECT)   # -> SelectResult
answer = sparql.execute(query, expect=QueryForm.ASK)    # -> AskResult

sparql.execute("ASK { ?s ?p ?o }", expect=QueryForm.SELECT)
# QueryFormError: expected a SELECT query, got ASK
```

### Formats and raw bodies

`CONSTRUCT` and `DESCRIBE` are the only forms that leave the serialization open;
the rest are read out of the SPARQL JSON results format. `raw=True` skips
parsing and hands back a `RawResult` in whatever format you ask for:

```python
sparql.execute("DESCRIBE <http://dbpedia.org/resource/Tuna>", result_format=GraphFormat.NTRIPLES)

csv = sparql.execute(query, result_format=SolutionFormat.CSV, raw=True)
csv.text  # 's,n\r\n...'
```

Asking for a format a form cannot answer in is a `QueryFormError`, raised before
the request goes out.

### Terms

```python
from rqw import Literal, Uri

match row["name"]:
    case Literal(value=value, language="en"):
        ...
    case Uri(value=uri):
        ...

row["count"].as_python()  # 42, from an xsd:integer literal
```

### [t-strings](https://docs.python.org/3/reference/lexical_analysis.html#t-strings) support

```python
from rqw import Uri

subject, name = Uri("http://example.org/a"), 'O"Brien'
sparql.execute(t"SELECT ?s WHERE {{ {subject} <http://e/name> {name} }}")
# sent as: SELECT ?s WHERE { <http://example.org/a> <http://e/name> "O\"Brien" }
```

| Python | SPARQL |
| --- | --- |
| `Uri`, `BlankNode`, `Literal`, `QuotedTriple` | the term itself |
| `str` | a quoted literal, `"..."` |
| `bool` | `true` / `false` |
| `int`, `float`, `Decimal` | a numeric literal |
| `date`, `time`, `datetime` | `"..."^^xsd:...` |
| a list or tuple | its items, space separated -- what `VALUES` wants |
| a nested `t"..."` | spliced in, values and all |

A `str` becomes a literal, never an IRI. Ask for another reading with a format
spec: `{value:iri}`, `{value:var}`.

After rendering, the whole query is tokenized and every spliced value is checked
to still line up with a token boundary, so a value that tried to break out of a
literal is refused rather than sent:

```python
evil = '" } INSERT DATA { <a> <b> "pwned'
sparql.execute(t"SELECT ?s WHERE {{ ?s ?p {evil} }}")
# one literal, no second operation:
#   SELECT ?s WHERE { ?s ?p "\" } INSERT DATA { <a> <b> \"pwned" }

sparql.execute(t'SELECT ?s WHERE {{ ?s ?p "{evil}" }}')
# QuerySyntaxError: an interpolated value cannot appear inside a token
```

`rqw.parse` gives the same `Query` on its own, which `execute` accepts directly
when you send one query many times.

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

Passing `client=httpx.Client(...)` swaps in your own transport; closing it then
stays your job.

### Errors

```python
from rqw import BadQueryError

try:
    sparql.execute("SELECT ?s WHERE {")
except BadQueryError as error:
    print(error.status, error.body)  # 400, the endpoint's own parser message
```

`BadQueryError`, `UnauthorizedError`, `ForbiddenError`, `EndpointNotFoundError`,
`UriTooLongError`, `UnsupportedMediaTypeError` and `EndpointError` derive from
`SparqlHttpError`; everything `rqw` raises derives from `RqwError`.

## License

[MIT License](
  <https://github.com/eggplants/rqw/blob/master/LICENSE.txt>
)
