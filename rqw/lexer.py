"""A tokenizer for SPARQL 1.1, following the terminal productions of the grammar.

Productions [139]-[173] of `SPARQL 1.1 Query Language
<https://www.w3.org/TR/sparql11-query/#rTerminals>`_ are transcribed here as
regular expressions, in an order that gives the longest match the spec asks for.
Whitespace and `#` comments separate tokens and are dropped; both are only
significant inside a string or an IRI, which the string and IRI patterns consume
whole, so the tokenizer never mistakes their contents for syntax.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from .exceptions import QuerySyntaxError

__all__ = ["Token", "TokenKind", "tokenize", "unescape_codepoints"]


class TokenKind(StrEnum):
    """The terminal a token was recognized as."""

    IRIREF = "IRIREF"
    """`<http://example.org/>`, production [139]."""
    PNAME = "PNAME"
    """A prefixed name, `foaf:name` or the bare `foaf:`, productions [140]-[141]."""
    BLANK_NODE_LABEL = "BLANK_NODE_LABEL"
    """`_:b0`, production [142]."""
    VAR = "VAR"
    """`?name` or `$name`, productions [143]-[144]."""
    LANGTAG = "LANGTAG"
    """`@en-GB`, production [145]."""
    INTEGER = "INTEGER"
    """Productions [146], [149] and [152]."""
    DECIMAL = "DECIMAL"
    """Productions [147], [150] and [153]."""
    DOUBLE = "DOUBLE"
    """Productions [148], [151] and [154]."""
    STRING = "STRING"
    """A quoted string in any of its four forms, productions [156]-[159]."""
    NIL = "NIL"
    """`()`, production [161]."""
    ANON = "ANON"
    """`[]`, production [163]."""
    WORD = "WORD"
    """A bare name: a keyword, `a`, `true` or `false`."""
    PUNCT = "PUNCT"
    """Punctuation and operators."""


# Productions [164]-[173], as character-class bodies.
_PN_CHARS_BASE: Final = (
    "A-Za-z"
    "\u00c0-\u00d6\u00d8-\u00f6\u00f8-\u02ff\u0370-\u037d\u037f-\u1fff"
    "\u200c-\u200d\u2070-\u218f\u2c00-\u2fef\u3001-\ud7ff\uf900-\ufdcf\ufdf0-\ufffd"
    "\U00010000-\U000effff"
)
_PN_CHARS_U: Final = _PN_CHARS_BASE + "_"
_VARNAME_TAIL: Final = _PN_CHARS_U + "0-9\u00b7\u0300-\u036f\u203f-\u2040"
_PN_CHARS: Final = _VARNAME_TAIL + r"\-"

_PLX: Final = r"%[0-9A-Fa-f]{2}|\\[_~.\-!$&'()*+,;=/?#@%]"
_PN_PREFIX: Final = f"[{_PN_CHARS_BASE}](?:[{_PN_CHARS}.]*[{_PN_CHARS}])?"
_PN_LOCAL: Final = f"(?:[{_PN_CHARS_U}:0-9]|{_PLX})(?:(?:[{_PN_CHARS}.:]|{_PLX})*(?:[{_PN_CHARS}:]|{_PLX}))?"
_VARNAME: Final = f"[{_PN_CHARS_U}0-9][{_VARNAME_TAIL}]*"
_ECHAR: Final = r"\\[tbnrf\\\"']"
_WS: Final = r"[\x20\x09\x0d\x0a]"

# Ordered so that the longest match wins, as [19.2] requires: the long string forms
# before the short ones, DOUBLE before DECIMAL before INTEGER, and IRIREF before the
# `<` operator so that `?a<?b&&?c>?d` reads as a variable, an IRI and a variable.
_TOKEN: Final = re.compile(
    "|".join(
        (
            rf"(?P<skip>{_WS}+|\#[^\x0a\x0d]*)",
            r"(?P<IRIREF><[^<>\"{}|^`\\\x00-\x20]*>)",
            (
                rf"(?P<STRING>\"\"\"(?:(?:\"|\"\")?(?:[^\"\\]|{_ECHAR}))*\"\"\""
                rf"|'''(?:(?:'|'')?(?:[^'\\]|{_ECHAR}))*'''"
                rf"|\"(?:[^\x22\x5c\x0a\x0d]|{_ECHAR})*\""
                rf"|'(?:[^\x27\x5c\x0a\x0d]|{_ECHAR})*')"
            ),
            rf"(?P<BLANK_NODE_LABEL>_:[{_PN_CHARS_U}0-9](?:[{_PN_CHARS}.]*[{_PN_CHARS}])?)",
            rf"(?P<ANON>\[{_WS}*\])",
            rf"(?P<NIL>\({_WS}*\))",
            r"(?P<LANGTAG>@[A-Za-z]+(?:-[A-Za-z0-9]+)*)",
            (
                r"(?P<DOUBLE>[+-]?(?:[0-9]+\.[0-9]*[eE][+-]?[0-9]+"
                r"|\.[0-9]+[eE][+-]?[0-9]+|[0-9]+[eE][+-]?[0-9]+))"
            ),
            r"(?P<DECIMAL>[+-]?[0-9]*\.[0-9]+)",
            r"(?P<INTEGER>[+-]?[0-9]+)",
            rf"(?P<VAR>[?$]{_VARNAME})",
            rf"(?P<PNAME>(?:{_PN_PREFIX})?:(?:{_PN_LOCAL})?)",
            rf"(?P<WORD>{_PN_PREFIX})",
            r"(?P<PUNCT>\^\^|\|\||&&|!=|<=|>=|[{}()\[\].,;*+\-/!<>=?$^|])",
        ),
    ),
)

_CODEPOINT: Final = re.compile(r"\\\\|\\u([0-9A-Fa-f]{4})|\\U([0-9A-Fa-f]{8})")


@dataclass(frozen=True, slots=True)
class Token:
    """One terminal, with the span it occupies in the query text."""

    kind: TokenKind
    text: str
    start: int
    end: int

    @property
    def word(self) -> str:
        """The token upper-cased, for comparing against a keyword.

        SPARQL matches keywords case-insensitively, with the sole exception of
        `a`, which the grammar treats as an IRI rather than a keyword.
        """
        return self.text.upper()


def unescape_codepoints(text: str) -> str:
    """Apply the `\\uXXXX` and `\\UXXXXXXXX` escapes the grammar resolves before parsing.

    An escaped backslash is consumed as a pair, so the `\\\\u0041` inside a string
    literal keeps its literal `u0041` rather than turning into an `A`.

    Args:
        text: The raw query text.

    Returns:
        The text with codepoint escapes resolved.

    Raises:
        QuerySyntaxError: If an escape names a codepoint that does not exist.
    """
    if "\\" not in text:
        return text

    def replace(match: re.Match[str]) -> str:
        short, long = match.groups()
        if short is None and long is None:
            return match.group()
        try:
            return chr(int(short or long, 16))
        except ValueError as exc:
            msg = f"{match.group()!r} is not a Unicode codepoint"
            raise QuerySyntaxError(msg, match.start()) from exc

    return _CODEPOINT.sub(replace, text)


def tokenize(text: str) -> list[Token]:
    """Split SPARQL text into terminals.

    Args:
        text: The query text, with codepoint escapes already resolved.

    Returns:
        The tokens, with whitespace and comments dropped.

    Raises:
        QuerySyntaxError: At the first character that starts no terminal, which
            is also how an unterminated string or IRI is reported.
    """
    tokens: list[Token] = []
    position = 0
    length = len(text)
    while position < length:
        match = _TOKEN.match(text, position)
        if match is None:
            msg = f"unexpected {text[position]!r}"
            raise QuerySyntaxError(msg, position)
        position = match.end()
        kind = match.lastgroup
        if kind != "skip":
            tokens.append(Token(TokenKind(kind), match.group(), match.start(), match.end()))
    return tokens
