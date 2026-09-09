from __future__ import annotations

import pytest

from rqw.exceptions import QuerySyntaxError
from rqw.lexer import TokenKind, tokenize, unescape_codepoints


def kinds(text):
    return [(token.kind, token.text) for token in tokenize(text)]


def test_whitespace_and_comments_separate_tokens_and_are_dropped():
    assert kinds("  ?s # a comment\n ?p\t?o ") == [
        (TokenKind.VAR, "?s"),
        (TokenKind.VAR, "?p"),
        (TokenKind.VAR, "?o"),
    ]


def test_a_hash_inside_an_iri_or_string_is_not_a_comment():
    assert kinds("<http://e/#frag> '# not a comment'") == [
        (TokenKind.IRIREF, "<http://e/#frag>"),
        (TokenKind.STRING, "'# not a comment'"),
    ]


def test_the_longest_match_wins_on_the_specs_own_example():
    # 19.2: `?a<?b&&?c>?d` is a variable, an IRI and a variable, not `<` and `>`.
    assert kinds("?a<?b&&?c>?d") == [
        (TokenKind.VAR, "?a"),
        (TokenKind.IRIREF, "<?b&&?c>"),
        (TokenKind.VAR, "?d"),
    ]


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("<http://e/a>", TokenKind.IRIREF),
        ("foaf:name", TokenKind.PNAME),
        ("foaf:", TokenKind.PNAME),
        (":", TokenKind.PNAME),
        (":local", TokenKind.PNAME),
        ("_:b0", TokenKind.BLANK_NODE_LABEL),
        ("?var", TokenKind.VAR),
        ("$var", TokenKind.VAR),
        ("@en-GB", TokenKind.LANGTAG),
        ("42", TokenKind.INTEGER),
        ("-42", TokenKind.INTEGER),
        ("+42", TokenKind.INTEGER),
        ("1.5", TokenKind.DECIMAL),
        (".5", TokenKind.DECIMAL),
        ("-1.5", TokenKind.DECIMAL),
        ("1.5e3", TokenKind.DOUBLE),
        ("1e3", TokenKind.DOUBLE),
        (".5E-3", TokenKind.DOUBLE),
        ("'x'", TokenKind.STRING),
        ('"x"', TokenKind.STRING),
        ("'''x'''", TokenKind.STRING),
        ('"""x"""', TokenKind.STRING),
        ('"a\\"b"', TokenKind.STRING),
        ("()", TokenKind.NIL),
        ("(  )", TokenKind.NIL),
        ("[]", TokenKind.ANON),
        ("SELECT", TokenKind.WORD),
        ("a", TokenKind.WORD),
        ("^^", TokenKind.PUNCT),
        ("&&", TokenKind.PUNCT),
        ("!=", TokenKind.PUNCT),
        ("<=", TokenKind.PUNCT),
    ],
)
def test_each_terminal_is_recognized(text, kind):
    assert kinds(text) == [(kind, text)]


def test_a_number_binds_its_sign_but_a_dot_stays_punctuation():
    assert kinds("?s ?p 1 . ?s ?p -2") == [
        (TokenKind.VAR, "?s"),
        (TokenKind.VAR, "?p"),
        (TokenKind.INTEGER, "1"),
        (TokenKind.PUNCT, "."),
        (TokenKind.VAR, "?s"),
        (TokenKind.VAR, "?p"),
        (TokenKind.INTEGER, "-2"),
    ]


def test_a_parenthesis_with_something_in_it_is_not_nil():
    assert kinds("(?x)") == [
        (TokenKind.PUNCT, "("),
        (TokenKind.VAR, "?x"),
        (TokenKind.PUNCT, ")"),
    ]


def test_tokens_carry_their_span():
    token = tokenize("  ?s")[0]
    assert (token.start, token.end) == (2, 4)


def test_word_upper_cases_for_keyword_comparison():
    assert tokenize("select")[0].word == "SELECT"


@pytest.mark.parametrize("text", ['"unterminated', "'''unterminated", "\x00"])
def test_an_unterminated_or_unknown_token_is_rejected(text):
    with pytest.raises(QuerySyntaxError):
        tokenize(text)


def test_a_lone_angle_bracket_is_the_less_than_operator():
    # `<` only opens an IRI when a `>` closes it, so this is a comparison.
    assert kinds("?a < ?b") == [
        (TokenKind.VAR, "?a"),
        (TokenKind.PUNCT, "<"),
        (TokenKind.VAR, "?b"),
    ]


def test_the_error_carries_the_position():
    with pytest.raises(QuerySyntaxError) as excinfo:
        tokenize("?s ?p \x00")
    assert excinfo.value.position == 6
    assert "position 6" in str(excinfo.value)


def test_codepoint_escapes_are_resolved_before_parsing():
    assert unescape_codepoints(r"<ab\u00E9xy>") == "<abéxy>"
    assert unescape_codepoints(r"\u03B1:a") == "\u03b1:a"
    assert unescape_codepoints(r"a\u003Ab") == "a:b"
    assert unescape_codepoints(r"\U0001F600") == "😀"


def test_an_escaped_backslash_is_not_a_codepoint_escape():
    assert unescape_codepoints(r'"a\\u0041"') == r'"a\\u0041"'


def test_text_without_a_backslash_is_returned_unchanged():
    assert unescape_codepoints("SELECT * {}") == "SELECT * {}"


def test_an_impossible_codepoint_is_rejected():
    with pytest.raises(QuerySyntaxError, match="not a Unicode codepoint"):
        unescape_codepoints(r"\U0011FFFF")
