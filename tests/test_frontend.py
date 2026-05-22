"""Unit tests for frontend: lexer, parser, planner."""
import pytest

from frontend.lexer import (
    Token,
    TK_EOF,
    TK_FROM,
    TK_IDENT,
    TK_SELECT,
    TK_SEMI,
    TK_STAR,
    tokenize,
)
from frontend.parser import parse
from frontend.planner import plan


# ---------------------------------------------------------------------------
# Lexer
# ---------------------------------------------------------------------------


def test_lexer_select_star_from():
    tokens = tokenize("SELECT * FROM employees;")
    assert tokens == [
        Token(TK_SELECT, "SELECT"),
        Token(TK_STAR, "*"),
        Token(TK_FROM, "FROM"),
        Token(TK_IDENT, "employees"),
        Token(TK_SEMI, ";"),
        Token(TK_EOF, ""),
    ]


def test_lexer_case_insensitive_keywords():
    tokens = tokenize("select * from employees")
    assert tokens[0].type == TK_SELECT
    assert tokens[2].type == TK_FROM


def test_lexer_extra_whitespace():
    tokens = tokenize("  SELECT   *   FROM   employees  ")
    types = [t.type for t in tokens]
    assert types == [TK_SELECT, TK_STAR, TK_FROM, TK_IDENT, TK_EOF]


def test_lexer_no_semicolon():
    tokens = tokenize("SELECT * FROM t")
    assert tokens[-1].type == TK_EOF
    assert tokens[-2].type == TK_IDENT


def test_lexer_underscore_identifier():
    tokens = tokenize("SELECT * FROM my_table")
    ident = tokens[3]
    assert ident.type == TK_IDENT
    assert ident.value == "my_table"


def test_lexer_unexpected_character():
    with pytest.raises(ValueError, match="Unexpected character"):
        tokenize("SELECT $ FROM t")


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def test_parser_select_star():
    ast = parse("SELECT * FROM employees;")
    assert ast == {"type": "select", "columns": ["*"], "from": "employees"}


def test_parser_no_semicolon():
    ast = parse("SELECT * FROM employees")
    assert ast["from"] == "employees"


def test_parser_lowercase():
    ast = parse("select * from orders")
    assert ast == {"type": "select", "columns": ["*"], "from": "orders"}


def test_parser_missing_from_raises():
    with pytest.raises(ValueError):
        parse("SELECT *")


def test_parser_trailing_garbage_raises():
    with pytest.raises(ValueError):
        parse("SELECT * FROM t extra_token")


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------


def test_planner_select_star_emits_scan():
    p = plan("SELECT * FROM employees")
    assert p == {"type": "Scan", "table": "employees", "columns": "*"}


def test_planner_table_name_preserved():
    p = plan("SELECT * FROM orders")
    assert p["table"] == "orders"


def test_planner_unsupported_statement_raises():
    """Planner must raise if the parser somehow returns an unknown statement type."""
    import frontend.planner as planner_mod
    from unittest.mock import patch

    fake_ast = {"type": "insert", "columns": ["*"], "from": "t"}
    with patch("frontend.planner.parse", return_value=fake_ast):
        with pytest.raises(ValueError, match="Unsupported statement type"):
            planner_mod.plan("irrelevant sql")
