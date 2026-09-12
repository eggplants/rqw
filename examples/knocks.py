"""SPARQL 50 knocks: <https://babibubebo.org/lab/> (CC BY-NC-SA 4.0)"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from rqw import (
    QueryForm,
    QueryResult,
    SelectResult,
)

if TYPE_CHECKING:
    from collections.abc import Callable

DBPEDIA_JA = "https://ja-dbpedia.egpl.dev/sparql"
NDLA = "http://id.ndl.go.jp/auth/ndla/sparql"

NO_BIF = "bif:* is a Virtuoso extension, and the mirror runs Oxigraph"
TIME_LIMIT = "the mirror cancels a query after 20 seconds, and this one needs longer"
BUILT_IRI_JOIN = (
    "on the mirror, joining a pattern with an IRI built by IRI() costs seconds per IRI rather than an index"
    " lookup, and this one builds hundreds of them"
)


@dataclass(frozen=True, kw_only=True)
class Knock:
    no: int
    title: str
    query: str
    endpoint: str = DBPEDIA_JA
    form: QueryForm = QueryForm.SELECT
    allow_empty: bool = False
    xfail: str = ""
    check: Callable[[Knock, QueryResult], str] | None = field(default=None, compare=False)


def _quine(knock: Knock, result: QueryResult) -> str:
    if not isinstance(result, SelectResult) or not len(result):
        return "empty result"
    printed = result[0].get("query")
    if printed is None or str(printed) != knock.query:
        return "the output does not match the query itself"
    return ""


_QUINE_HEAD = (
    "SELECT (REPLACE(REPLACE(?s, SUBSTR(STR(?etc), 216, 1), SUBSTR(STR(?etc), 245, 1)), "
    "SUBSTR(STR(?etc), 74, 1), ?s) AS ?query) WHERE { "
    "<http://ja.dbpedia.org/resource/D.C.P.S._〜ダ・カーポ〜_プラスシチュエーション> "
    "<http://ja.dbpedia.org/property/etc> ?etc . } "
)
QUINE = f"""{_QUINE_HEAD}GROUP BY ?etc ('{_QUINE_HEAD}GROUP BY ?etc ("&" AS ?s)' AS ?s)"""


KNOCKS: tuple[Knock, ...] = (
    Knock(
        no=1,
        title="List the class IRIs",
        query="""
SELECT DISTINCT ?class
WHERE {
  ?s a ?class .
}
""",
    ),
    Knock(
        no=2,
        title="List the graph IRIs",
        query="""
SELECT DISTINCT ?g
WHERE {
  GRAPH ?g {
    ?s ?p ?o .
  }
}
""",
        xfail=TIME_LIMIT,
    ),
    Knock(
        no=3,
        title="Test whether a query pattern matches, with ASK",
        query="""
ASK {
  <http://example.com/foo> ?p ?o .
}
""",
        form=QueryForm.ASK,
    ),
    Knock(
        no=4,
        title="Fetch the data about a given URI, with DESCRIBE",
        query="""
DESCRIBE ?s
WHERE {
  ?s <http://www.w3.org/2000/01/rdf-schema#label> "ペタンク"@ja .
}
""",
        form=QueryForm.DESCRIBE,
    ),
    Knock(
        no=5,
        title="Fetch the resources whose value falls in a range, with FILTER",
        query="""
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
SELECT *
WHERE {
  ?s <http://ja.dbpedia.org/property/生年> ?date .
  FILTER (?date > "1950-01-01"^^xsd:date && ?date < "1959-12-31"^^xsd:date)
}
ORDER BY (?date)
""",
    ),
    Knock(
        no=6,
        title="Fetch the language tags of literals",
        query="""
SELECT DISTINCT (LANG(?label) AS ?langtag)
WHERE {
  ?s <http://www.w3.org/2000/01/rdf-schema#label> ?label .
}
""",
    ),
    Knock(
        no=7,
        title="Branch on a condition, with IF",
        query="""
SELECT DISTINCT ?name
  (IF(isIRI(?kamon), STRAFTER(STR(?kamon), "resource/"), STR(?kamon)) AS ?kamonStr)
WHERE {
  ?s <http://ja.dbpedia.org/property/家紋> ?page ;
     <http://www.w3.org/2000/01/rdf-schema#label> ?name ;
     <http://ja.dbpedia.org/property/家紋名称> ?kamon .
}
""",
    ),
    Knock(
        no=8,
        title="Bind a value to a variable, with BIND",
        query="""
SELECT DISTINCT ?name ?kamonStr
WHERE {
  ?s <http://ja.dbpedia.org/property/家紋> ?page ;
     <http://www.w3.org/2000/01/rdf-schema#label> ?name ;
     <http://ja.dbpedia.org/property/家紋名称> ?kamon .
  BIND (IF(isIRI(?kamon), STRAFTER(STR(?kamon), "resource/"), STR(?kamon))
    AS ?kamonStr)
}
""",
    ),
    Knock(
        no=9,
        title="Replace text by regular expression, with REPLACE",
        query="""
SELECT DISTINCT ?name ?kamonStr
WHERE {
  ?s <http://ja.dbpedia.org/property/家紋> ?page ;
     <http://www.w3.org/2000/01/rdf-schema#label> ?name ;
     <http://ja.dbpedia.org/property/家紋名称> ?kamon .
  BIND (IF(isIRI(?kamon), REPLACE(STR(?kamon), ".+/resource/([^/]+)$", "$1"), STR(?kamon)) AS ?kamonStr)
}
""",
    ),
    Knock(
        no=10,
        title="Match text against a regular expression, with REGEX",
        query="""
SELECT ?s ?label
WHERE {
  ?s <http://www.w3.org/2000/01/rdf-schema#label> ?label .
  FILTER REGEX(?label, "QL$", "i")
}
""",
    ),
    Knock(
        no=11,
        title="List the DBpedia categories",
        query="""
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
SELECT ?s
WHERE {
  ?s a skos:Concept.
  FILTER CONTAINS(STR(?s), "resource/Category:")
}
""",
    ),
    Knock(
        no=12,
        title="Fetch the articles that share a name with a category",
        query="""
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
SELECT ?article ?category
WHERE {
  ?article rdfs:label ?labelArticle .
  ?category a skos:Concept ;
    rdfs:label ?labelConcept .
  FILTER (CONTAINS(STR(?category), "resource/Category:"))
  FILTER (?article != ?category)
  FILTER (?labelArticle = ?labelConcept)
}
ORDER BY ?labelArticle
""",
        xfail=TIME_LIMIT,
    ),
    Knock(
        no=13,
        title="List the prefectures",
        query="""
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX dcterms: <http://purl.org/dc/terms/>
SELECT ?pref ?code
WHERE {
  ?pref dcterms:subject <http://ja.dbpedia.org/resource/Category:日本の都道府県> ;
        <http://ja.dbpedia.org/property/区分> ?category ;
        <http://dbpedia.org/ontology/areaCode> ?code .
  FILTER REGEX(?category, "[都道府県]")
  FILTER REGEX(?code, "^JP")
}
ORDER BY (xsd:integer(STRAFTER(?code, "JP-")))
""",
    ),
    Knock(
        no=14,
        title="Fetch the anime works about volleyball",
        query="""
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX category-ja: <http://ja.dbpedia.org/resource/Category:>
SELECT DISTINCT ?s WHERE {
  ?s dcterms:subject ?volley ;
     dcterms:subject ?cat .
  VALUES ?volley {category-ja:バレーボールを題材とした作品 category-ja:女子バレーボールを題材とした作品 category-ja:バレーボール漫画}
  FILTER CONTAINS(STR(?cat), "アニメ作品")
}
""",
    ),
    Knock(
        no=15,
        title="List the programming languages",
        query="""
SELECT *
WHERE {
  ?s a <http://dbpedia.org/ontology/ProgrammingLanguage> ;
     <http://www.w3.org/2000/01/rdf-schema#label> ?label .
}
ORDER BY ?label
""",
    ),
    Knock(
        no=16,
        title="Tally the programming languages by initial letter, in descending order",
        query="""
SELECT ?initial (COUNT(?s) AS ?count) (GROUP_CONCAT(?label; SEPARATOR=", ") AS ?list)
WHERE {
  ?s a <http://dbpedia.org/ontology/ProgrammingLanguage> ;
     <http://www.w3.org/2000/01/rdf-schema#label> ?label .
  BIND (SUBSTR(?label, 1, 1) AS ?initial)
}
GROUP BY ?initial
ORDER BY DESC(COUNT(?initial))
""",
    ),
    Knock(
        no=17,
        title="Fetch the resources holding N or more of a property",
        query="""
SELECT ?s (COUNT(?class) AS ?count)
WHERE {
  ?s a ?class .
}
GROUP BY ?s
HAVING (COUNT(?class) > 14)
ORDER BY DESC(COUNT(?class))
""",
    ),
    Knock(
        no=18,
        title="Fetch the people whose birthday is today",
        query="""
SELECT *
WHERE {
 ?s <http://ja.dbpedia.org/property/生月> ?month;
    <http://ja.dbpedia.org/property/生日> ?day .
 FILTER (?month = MONTH(NOW()) && ?day = DAY(NOW()))
}
""",
    ),
    Knock(
        no=19,
        title="Fetch the actors from Tokyo aged 50 or under",
        query="""
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX category-ja: <http://ja.dbpedia.org/resource/Category:>
PREFIX prop-ja: <http://ja.dbpedia.org/property/>
PREFIX dbpedia-ja: <http://ja.dbpedia.org/resource/>
SELECT * WHERE {
  ?actor prop-ja:職業 dbpedia-ja:俳優 ;
     dcterms:subject category-ja:東京都出身の人物 ;
     prop-ja:生年 ?year.
  OPTIONAL {?actor prop-ja:出生地 ?birthplace}
  FILTER (?year >= (YEAR(NOW()) - 50))
  FILTER (DATATYPE(?year) = xsd:integer)
}
ORDER BY ?year
""",
    ),
    Knock(
        no=20,
        title="Fetch the name authorities whose occupation mentions voice acting",
        endpoint=NDLA,
        query="""
PREFIX rda: <http://RDVocab.info/ElementsGr2/>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>

SELECT *
WHERE {
  ?concept foaf:primaryTopic ?topic .
  ?topic a foaf:Person ;
     foaf:name ?name ;
     rda:biographicalInformation ?work .
  FILTER CONTAINS(?work, "声優")
}
""",
    ),
    Knock(
        no=21,
        title="Use the InversePath property path",
        query="""
SELECT ?s
WHERE {
  <http://ja.dbpedia.org/resource/Category:日本の山>
    ^<http://www.w3.org/2004/02/skos/core#broader>/^<http://purl.org/dc/terms/subject> ?s .
}
""",
    ),
    Knock(
        no=22,
        title="Generate random numbers",
        query="""
SELECT (RAND() AS ?rand)
WHERE {
  ?s ?p ?o .
}
LIMIT 10
""",
    ),
    Knock(
        no=23,
        title="Fetch the DBpedia categories that have no broader category",
        query="""
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
SELECT distinct ?s WHERE {
  ?s a skos:Concept .
  FILTER NOT EXISTS {?s skos:broader ?bc}
  FILTER REGEX(STR(?s), 'dbpedia.org/resource/Category')
}
""",
    ),
    Knock(
        no=24,
        title="List the local-name-ish part of the class IRIs",
        query="""
SELECT DISTINCT
   ?prefix (COUNT(DISTINCT(?local)) AS ?num)
   (GROUP_CONCAT(DISTINCT ?local; SEPARATOR=", ") AS ?localNames)
WHERE {
  ?s a ?o .
  BIND (STR(?o) AS ?oStr)
  BIND (REPLACE(?oStr, ".+[^a-zA-Z_0-9-]([A-Za-z0-9_-]*)$", "$1") AS ?local)
  BIND (STRBEFORE(?oStr, ?local) AS ?prefix)
}
GROUP BY ?prefix
ORDER BY DESC(?num)
""",
        xfail=TIME_LIMIT,
    ),
    Knock(
        no=25,
        title="Fetch the resources holding N or more of a property (subquery version)",
        query="""
SELECT ?s ?count
WHERE {
  FILTER (?count > 14)
  {
    SELECT ?s (COUNT(?type) AS ?count)
    WHERE {
      ?s a ?type .
    }
    GROUP BY ?s
  }
}
ORDER BY DESC(?count)
""",
    ),
    Knock(
        no=26,
        title="List the Olympic gold medalists by birthplace",
        query="""
SELECT ?pref (count(?name) AS ?count) (GROUP_CONCAT(?name; separator=',') AS ?people)
WHERE {
  ?person <http://purl.org/dc/terms/subject> <http://ja.dbpedia.org/resource/Category:日本のオリンピック金メダリスト> ;
          <http://purl.org/dc/terms/subject> ?bplace ;
          <http://www.w3.org/2000/01/rdf-schema#label> ?name .
  ?bplace <http://www.w3.org/2000/01/rdf-schema#label> ?pref .
  FILTER REGEX(?pref, "[都道府県州国]出身の人物", "i")
}
GROUP BY (?pref)
ORDER BY DESC (count(?person))
""",
    ),
    Knock(
        no=27,
        title="Pull out the (apparent) family names of Japanese people and tally them",
        query="""
SELECT ?family (COUNT(?family) AS ?count)
WHERE {
  ?s a <http://dbpedia.org/ontology/Person>;
     <http://ja.dbpedia.org/property/国籍> ?nationality ;
     <http://www.w3.org/2000/01/rdf-schema#comment> ?comment .
  VALUES ?nationality { <http://ja.dbpedia.org/resource/日本> "日本"@ja }
  BIND (REPLACE(?comment, "([・(（ ]|は、|は日本).*$", "") AS ?family)
  FILTER (STRLEN(?family) > 0)
}
GROUP BY ?family
ORDER BY DESC(COUNT(?family))
""",
    ),
    Knock(
        no=28,
        title="List the World Heritage sites",
        query="""
SELECT ?heritage ?name ?country ?lat ?long
WHERE {
  ?heritage <http://purl.org/dc/terms/subject> ?category ;
            <http://www.w3.org/2000/01/rdf-schema#label> ?name ;
            <http://ja.dbpedia.org/property/country> ?country .
  ?category <http://www.w3.org/2004/02/skos/core#broader> <http://ja.dbpedia.org/resource/Category:五十音順の世界遺産> .
  OPTIONAL {
    ?heritage <http://www.w3.org/2003/01/geo/wgs84_pos#lat> ?lat ;
              <http://www.w3.org/2003/01/geo/wgs84_pos#long> ?long .
  }
}
ORDER BY (?country)
""",
    ),
    Knock(
        no=29,
        title="List the loanwords",
        query="""
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

SELECT ?category (COUNT(?word) AS ?count)
  (GROUP_CONCAT(?word; SEPARATOR=', ') AS ?wordList)
WHERE {
  ?s dcterms:subject ?category ;
     rdfs:label ?word .
  ?category skos:broader <http://ja.dbpedia.org/resource/Category:借用語> ;
            rdfs:label ?country .
  FILTER NOT EXISTS {
    ?s dcterms:subject <http://ja.dbpedia.org/resource/Category:日本語における借用語> .
  }
}
GROUP BY (?category)
ORDER BY DESC(COUNT(?s))
""",
    ),
    Knock(
        no=30,
        title="Fetch the ideologies and political positions of the parties",
        query="""
SELECT ?s ?name (COUNT(DISTINCT(?ideology)) AS ?count)
  (GROUP_CONCAT(DISTINCT ?ideology; separator=", ") AS ?ideologies)
WHERE {
  ?s <http://ja.dbpedia.org/property/政治的思想・立場> ?i ;
     <http://www.w3.org/2000/01/rdf-schema#label> ?name .
  ?i <http://www.w3.org/2000/01/rdf-schema#label> ?ideology .
}
GROUP BY ?s ?name
ORDER BY DESC(COUNT(DISTINCT(?ideology)))
""",
    ),
    Knock(
        no=31,
        title="List the Japanese mountains spanning several prefectures",
        query="""
SELECT ?s (COUNT(DISTINCT(?pref)) AS ?count)
   (GROUP_CONCAT(DISTINCT ?pref; SEPARATOR=', ') AS ?prefList)
WHERE {
  ?s a <http://dbpedia.org/ontology/Mountain> ;
     <http://dbpedia.org/ontology/address> ?address ;
     <http://www.w3.org/2000/01/rdf-schema#label> ?name ;
     <http://purl.org/dc/terms/subject>/<http://www.w3.org/2004/02/skos/core#broader> <http://ja.dbpedia.org/resource/Category:日本の山> .
  BIND (REPLACE(STR(REPLACE(?address, "([（）]|藤津郡太良町・)", "")), "(京都府|[都道府県]).*$", "$1") AS ?pref)
  FILTER (REGEX(?pref, "[都道府県]"))
  FILTER (!REGEX(?pref, "(同県|小県)"))
}
GROUP BY ?s
HAVING (COUNT(DISTINCT(?pref)) > 1)
ORDER BY DESC (COUNT(DISTINCT(?pref)))
""",
    ),
    Knock(
        no=32,
        title="Take the members (rdf:first) out of a collection (rdf:List)",
        query="""
PREFIX ex: <http://example.org/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT *
WHERE {
  ?s ex:member/rdf:rest*/rdf:first ?o .
}
""",
        allow_empty=True,
    ),
    Knock(
        no=33,
        title="Take the member at an arbitrary position out of a collection",
        query="""
PREFIX ex: <http://example.org/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT *
WHERE {
  ?s ex:member/rdf:rest/rdf:rest/rdf:first ?o .
}
""",
        allow_empty=True,
    ),
    Knock(
        no=34,
        title="Fetch the articles filed under the subcategories of a category",
        query="""
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX dcterms: <http://purl.org/dc/terms/>

SELECT DISTINCT ?s ?category
WHERE {
  ?s dcterms:subject ?category .
  <http://ja.dbpedia.org/resource/Category:アニメ> ^skos:broader+ ?category .
}
""",
        xfail=TIME_LIMIT,
    ),
    Knock(
        no=35,
        title="Query the graph formed by merging several graphs",
        query="""
SELECT ?s ?o
FROM <http://example.org/foo>
FROM <http://example.org/bar>
FROM <http://example.org/baz>
WHERE {
  ?s <http://example.org/term> ?o .
}
""",
        allow_empty=True,
    ),
    Knock(
        no=36,
        title="Fetch the people who co-starred 4 or more times with a Johnny's talent",
        query="""
SELECT DISTINCT ?p1 ?p2
WHERE {
  ?work1 <http://ja.dbpedia.org/property/出演者> ?p1 ;
         <http://ja.dbpedia.org/property/出演者> ?p2 .
  ?work2 <http://ja.dbpedia.org/property/出演者> ?p1 ;
         <http://ja.dbpedia.org/property/出演者> ?p2 .
  ?work3 <http://ja.dbpedia.org/property/出演者> ?p1 ;
         <http://ja.dbpedia.org/property/出演者> ?p2 .
  ?work4 <http://ja.dbpedia.org/property/出演者> ?p1 ;
         <http://ja.dbpedia.org/property/出演者> ?p2 .
  ?p1 <http://ja.dbpedia.org/property/production> <http://ja.dbpedia.org/resource/ジャニーズ事務所> .
  FILTER (?work1 != ?work2)
  FILTER (?work1 != ?work3)
  FILTER (?work1 != ?work4)
  FILTER (?work2 != ?work3)
  FILTER (?work2 != ?work4)
  FILTER (?work3 != ?work4)
  FILTER (?p1 != ?p2)
}
""",
    ),
    Knock(
        no=37,
        title="Fetch the people who co-starred 4 or more times with a Johnny's talent (deduplicated)",
        query="""
SELECT DISTINCT ?pp1 ?pp2
WHERE {
  ?work1 <http://ja.dbpedia.org/property/出演者> ?p1 ;
         <http://ja.dbpedia.org/property/出演者> ?p2 .
  ?work2 <http://ja.dbpedia.org/property/出演者> ?p1 ;
         <http://ja.dbpedia.org/property/出演者> ?p2 .
  ?work3 <http://ja.dbpedia.org/property/出演者> ?p1 ;
         <http://ja.dbpedia.org/property/出演者> ?p2 .
  ?work4 <http://ja.dbpedia.org/property/出演者> ?p1 ;
         <http://ja.dbpedia.org/property/出演者> ?p2 .
  ?p1 <http://ja.dbpedia.org/property/production> <http://ja.dbpedia.org/resource/ジャニーズ事務所> .
  FILTER (?work1 NOT IN (?work2, ?work3, ?work4))
  FILTER (?work2 NOT IN (?work3, ?work4))
  FILTER (?work3 != ?work4)
  FILTER (?p1 != ?p2)
  BIND (IF(STR(?p1) <= STR(?p2), ?p1, ?p2) AS ?pp1)
  BIND (IF(STR(?p1) > STR(?p2), ?p1, ?p2) AS ?pp2)
}
""",
    ),
    Knock(
        no=38,
        title="Generate random numbers (for Virtuoso)",
        query="""
SELECT (bif:rnd(10, ?s, ?p, ?o) AS ?rand)
WHERE {
  ?s ?p ?o .
}
LIMIT 10
""",
        xfail=NO_BIF,
    ),
    Knock(
        no=39,
        title="SPARQL Dou Deshou: the dice journey",
        query="""
SELECT ?line ?stations
WHERE {
  <http://ja.dbpedia.org/resource/秋葉原駅> <http://ja.dbpedia.org/property/所属路線> ?line .
  ?stations <http://ja.dbpedia.org/property/所属路線> ?line .
}
ORDER BY RAND()
LIMIT 1
""",
    ),
    Knock(
        no=40,
        title="Count the depth of a path",
        query="""
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
SELECT ?gchild (COUNT(?child)-1 AS ?depth)
WHERE {
  <http://ja.dbpedia.org/resource/Category:アニメ> ^skos:broader* ?child .
  ?child ^skos:broader* ?gchild .
}
GROUP BY ?gchild
ORDER BY ?depth
""",
    ),
    Knock(
        no=41,
        title="List the results of knock 31 by prefecture",
        query="""
SELECT ?pref (COUNT(?mount) AS ?count)
   (GROUP_CONCAT(?name; SEPARATOR=', ') AS ?mountList)
WHERE {
  ?s a <http://dbpedia.org/ontology/AdministrativeRegion> ;
     <http://www.w3.org/2000/01/rdf-schema#label> ?pref .
  FILTER CONTAINS(?mountPref, STR(?pref))
  {
    SELECT ?mount ?name (GROUP_CONCAT(DISTINCT(?pref); SEPARATOR=', ') AS ?mountPref)
    WHERE {
      ?mount a <http://dbpedia.org/ontology/Mountain> ;
         <http://dbpedia.org/ontology/address> ?address ;
         <http://www.w3.org/2000/01/rdf-schema#label> ?name ;
         <http://purl.org/dc/terms/subject>/<http://www.w3.org/2004/02/skos/core#broader> <http://ja.dbpedia.org/resource/Category:日本の山> .
      BIND (REPLACE(STR(REPLACE(?address, "([（）]|藤津郡太良町・)", "")), "(京都府|[都道府県]).*$", "$1") AS ?pref)
      FILTER (REGEX(?pref, "[都道府県]"))
      FILTER (!REGEX(?pref, "(同県|小県)"))
    }
    GROUP BY ?mount ?name
    HAVING (COUNT(DISTINCT(?pref)) > 1)
  }
}
GROUP BY ?pref
ORDER BY DESC(COUNT(?mount))
""",
    ),
    Knock(
        no=42,
        title="Build IRIs dynamically",
        query="""
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
SELECT DISTINCT ?nameProp ?name
WHERE {
  ?location ?nameProp ?name .
  {
    SELECT DISTINCT (IRI(?prop) AS ?nameProp)
    WHERE {
      ?s <http://ja.dbpedia.org/property/subdivisionType> ?o .
      BIND (CONCAT(REPLACE(STR(?o), "resource", "property"), "名"^^xsd:string) AS ?prop)
    }
  }
}
""",
        xfail=TIME_LIMIT,
    ),
    Knock(
        no=43,
        title="Fetch the anime works about sports",
        query="""
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX category-ja: <http://ja.dbpedia.org/resource/Category:>

SELECT DISTINCT ?title ?category
WHERE {
  ?s dcterms:subject ?category, ?categories ;
     rdfs:label ?title .
  FILTER CONTAINS(STR(?categories), "アニメ")
  {
    SELECT ?category
    WHERE {
      {
        ?sport dcterms:subject category-ja:オリンピック競技 ; rdfs:label ?label .
        BIND (IRI(CONCAT("http://ja.dbpedia.org/resource/Category:"^^xsd:string, REPLACE(?label, " ", "_"), "アニメ"^^xsd:string)) AS ?category)
      } UNION {
        ?sport dcterms:subject category-ja:オリンピック競技 ; rdfs:label ?label .
        BIND (IRI(CONCAT("http://ja.dbpedia.org/resource/Category:男子"^^xsd:string, REPLACE(?label, " ", "_"), "アニメ"^^xsd:string)) AS ?category)
      } UNION {
        ?sport dcterms:subject category-ja:オリンピック競技 ; rdfs:label ?label .
        BIND (IRI(CONCAT("http://ja.dbpedia.org/resource/Category:女子"^^xsd:string, REPLACE(?label, " ", "_"), "アニメ"^^xsd:string)) AS ?category)
      } UNION {
        ?sport dcterms:subject category-ja:オリンピック競技 ; rdfs:label ?label .
        BIND (IRI(CONCAT("http://ja.dbpedia.org/resource/Category:"^^xsd:string, REPLACE(?label, " ", "_"), "を題材とした作品"^^xsd:string)) AS ?category)
      } UNION {
        ?sport dcterms:subject category-ja:オリンピック競技 ; rdfs:label ?label .
        BIND (IRI(CONCAT("http://ja.dbpedia.org/resource/Category:男子"^^xsd:string, REPLACE(?label, " ", "_"), "を題材とした作品"^^xsd:string)) AS ?category)
      } UNION {
        ?sport dcterms:subject category-ja:オリンピック競技 ; rdfs:label ?label .
        BIND (IRI(CONCAT("http://ja.dbpedia.org/resource/Category:女子"^^xsd:string, REPLACE(?label, " ", "_"), "を題材とした作品"^^xsd:string)) AS ?category)
      }
    }
  }
}
""",
        xfail=BUILT_IRI_JOIN,
    ),
    Knock(
        no=44,
        title="Build IRIs from the cross product of several patterns",
        query="""
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX category-ja: <http://ja.dbpedia.org/resource/Category:>

SELECT (IRI(
  CONCAT("http://ja.dbpedia.org/resource/Category:", ?x, REPLACE(?label, " ", "_"), ?y)
 ) AS ?category)
WHERE {
 ?sport dcterms:subject category-ja:オリンピック競技 ; rdfs:label ?label .
 VALUES ?x {"" "男子" "女子"}
 VALUES ?y {"アニメ" "を題材とした作品"}
}
""",
    ),
    Knock(
        no=45,
        title="Fetch the anime works about sports (using the method of knock 44)",
        query="""
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX category-ja: <http://ja.dbpedia.org/resource/Category:>
SELECT DISTINCT ?title ?category
WHERE {
  ?s dcterms:subject ?category, ?categories ;
     rdfs:label ?title .
     FILTER CONTAINS(STR(?categories), "アニメ")
  {
    SELECT (IRI(
      CONCAT("http://ja.dbpedia.org/resource/Category:", ?x, REPLACE(?label, " ", "_"), ?y)
     ) AS ?category)
    WHERE {
      ?sport dcterms:subject category-ja:オリンピック競技 ; rdfs:label ?label .
      VALUES ?x {"" "男子" "女子"}
      VALUES ?y {"アニメ" "を題材とした作品"}
    }
  }
}
""",
        xfail=BUILT_IRI_JOIN,
    ),
    Knock(
        no=46,
        title="Fetch the information about the Virtuoso server",
        query="""
SELECT
  (bif:sys_stat('st_dbms_name')          AS ?name)
  (bif:sys_stat('st_dbms_ver')           AS ?version)
  (bif:sys_stat('st_build_date')         AS ?date)
  (bif:sys_stat('st_build_thread_model') AS ?thread)
  (bif:sys_stat('st_build_opsys_id')     AS ?opsys)
WHERE {?s ?p ?o}
LIMIT 1
""",
        xfail=NO_BIF,
    ),
    Knock(
        no=47,
        title="Fizz Buzz",
        query="""
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
SELECT ?out
WHERE {
  ?s <http://www.w3.org/2000/01/rdf-schema#label> ?label .
  BIND (xsd:integer(STR(?label)) AS ?num)
  FILTER (REGEX(?label, "^\\\\d+$") && ?num > 0)
  BIND (CONCAT(IF(FLOOR(?num / 3) * 3 = ?num, "Fizz", ""), IF(FLOOR(?num / 5) * 5 = ?num, "Buzz", "")) AS ?str)
  BIND (IF(STRLEN(?str) = 0, ?num, ?str) AS ?out)
}
GROUP BY ?num ?out
ORDER BY ASC(?num)
LIMIT 100
""",
    ),
    Knock(
        no=48,
        title="Generate a running number",
        query="""
SELECT (bif:sequence_next('my_unique_key', 1, ?s, ?p, ?o) AS ?id) # runs every time
       ?call_once
WHERE {
  ?s ?p ?o .
  BIND (bif:sequence_set('my_unique_key', 1, 0) AS ?call_once) # runs only once
}
LIMIT 100
""",
        xfail=NO_BIF,
    ),
    Knock(
        no=49,
        title="A query that runs a query",
        query="""
SELECT ?sparql ?sql ?exec ?state ?message (bif:length(?rows) AS ?length)
   (bif:aref(bif:aref(?rows, 0), 0) AS ?concept0) (bif:aref(bif:aref(?rows, 0), 1) AS ?label0)
   (bif:aref(bif:aref(?rows, 1), 0) AS ?concept1) (bif:aref(bif:aref(?rows, 1), 1) AS ?label1)
   (bif:aref(bif:aref(?rows, 2), 0) AS ?concept2) (bif:aref(bif:aref(?rows, 2), 1) AS ?label2)
WHERE {
  ?s ?p ?o .
  BIND ('SELECT * WHERE {?concept a skos:Concept; rdfs:label ?label}' AS ?sparql)
  BIND (STR(bif:sparql_to_sql_text(?sparql)) AS ?sql)
  BIND ("" AS ?state)
  BIND ("no error" AS ?message)
  BIND (bif:vector() AS ?meta)
  BIND (bif:vector() AS ?rows)
  BIND (bif:exec(?sql, ?state, ?message, bif:vector(), 3, ?meta, ?rows) AS ?exec)
} LIMIT 1
""",
        xfail=NO_BIF,
    ),
    Knock(
        no=50,
        title="Quine",
        query=QUINE,
        check=_quine,
    ),
)
