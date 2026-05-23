"""Tests for the IN / NOT IN predicate (expression type 'in').

Coverage:
- Lexer: IN and NOT tokens recognised as keywords
- Parser: IN and NOT IN produce correct AST node
- Executor eval_expr: membership test, negation, NULL-expr, NULL-in-values
- Integration: full SQL round-trip via plan() + execute()
- Edge cases: single-value list, empty result, numeric literals, column refs in list
- Failure modes: syntax errors, wrong grammar usage
"""
import pytest

from frontend.lexer import tokenize, TK_IN, TK_NOT
from frontend.parser import parse
from frontend.planner import plan
from engine.executor import execute, eval_expr


# ---------------------------------------------------------------------------
# Lexer tests
# ---------------------------------------------------------------------------


def test_lexer_recognises_in_keyword():
    """IN must be emitted as TK_IN, not as a bare IDENT."""
    tokens = tokenize("WHERE department IN ('X')")
    types = [t.type for t in tokens]
    assert TK_IN in types


def test_lexer_recognises_not_keyword():
    """NOT must be emitted as TK_NOT, not as a bare IDENT."""
    tokens = tokenize("WHERE department NOT IN ('X')")
    types = [t.type for t in tokens]
    assert TK_NOT in types


def test_lexer_in_case_insensitive():
    """IN is case-insensitive — 'in' and 'In' must both lex to TK_IN."""
    for word in ("in", "In", "iN"):
        tokens = tokenize(f"WHERE x {word} (1)")
        types = [t.type for t in tokens]
        assert TK_IN in types, f"Expected TK_IN for {word!r}"


# ---------------------------------------------------------------------------
# Parser: AST shape tests
# ---------------------------------------------------------------------------


def test_parser_in_basic():
    """WHERE col IN (v1, v2) emits a correct 'in' predicate node."""
    ast = parse("SELECT * FROM employees WHERE department IN ('Engineering', 'Marketing');")
    pred = ast["where"]
    assert pred["type"] == "in"
    assert pred["negated"] is False
    assert pred["expr"] == {"type": "col", "name": "department"}
    assert len(pred["values"]) == 2
    assert pred["values"][0] == {"type": "lit", "value": "Engineering"}
    assert pred["values"][1] == {"type": "lit", "value": "Marketing"}


def test_parser_not_in():
    """WHERE col NOT IN (...) emits a negated 'in' node."""
    ast = parse("SELECT * FROM employees WHERE department NOT IN ('HR');")
    pred = ast["where"]
    assert pred["type"] == "in"
    assert pred["negated"] is True
    assert pred["expr"] == {"type": "col", "name": "department"}
    assert pred["values"] == [{"type": "lit", "value": "HR"}]


def test_parser_in_integer_literals():
    """IN list may contain integer literals."""
    ast = parse("SELECT * FROM employees WHERE id IN (1, 3, 5);")
    pred = ast["where"]
    assert pred["type"] == "in"
    assert pred["values"] == [
        {"type": "lit", "value": 1},
        {"type": "lit", "value": 3},
        {"type": "lit", "value": 5},
    ]


def test_parser_in_float_literals():
    """IN list may contain float literals."""
    ast = parse("SELECT * FROM t WHERE score IN (1.5, 2.5);")
    pred = ast["where"]
    assert pred["type"] == "in"
    assert pred["values"][0] == {"type": "lit", "value": 1.5}


def test_parser_in_single_value():
    """IN with a single value in the list is valid."""
    ast = parse("SELECT * FROM employees WHERE department IN ('HR');")
    pred = ast["where"]
    assert pred["type"] == "in"
    assert len(pred["values"]) == 1


def test_parser_in_with_column_ref():
    """IN values may be column references (for row-comparison use cases)."""
    ast = parse("SELECT * FROM t WHERE a IN (b, c);")
    pred = ast["where"]
    assert pred["values"][0] == {"type": "col", "name": "b"}
    assert pred["values"][1] == {"type": "col", "name": "c"}


def test_parser_invalid_not_without_in():
    """NOT not followed by IN should raise ValueError."""
    with pytest.raises(ValueError):
        parse("SELECT * FROM t WHERE x NOT = 1;")


# ---------------------------------------------------------------------------
# Executor: eval_expr unit tests
# ---------------------------------------------------------------------------

_ROW = {"department": "Engineering", "salary": 95000, "name": "Alice", "x": None}


def test_eval_expr_in_match():
    """eval_expr returns True when lhs equals a value in the list."""
    expr = {
        "type": "in",
        "negated": False,
        "expr": {"type": "col", "name": "department"},
        "values": [
            {"type": "lit", "value": "Engineering"},
            {"type": "lit", "value": "Marketing"},
        ],
    }
    assert eval_expr(expr, _ROW) is True


def test_eval_expr_in_no_match():
    """eval_expr returns False when lhs does not appear in the list."""
    expr = {
        "type": "in",
        "negated": False,
        "expr": {"type": "col", "name": "department"},
        "values": [{"type": "lit", "value": "HR"}, {"type": "lit", "value": "Finance"}],
    }
    assert eval_expr(expr, _ROW) is False


def test_eval_expr_not_in_match_returns_false():
    """NOT IN returns False when lhs IS in the list."""
    expr = {
        "type": "in",
        "negated": True,
        "expr": {"type": "col", "name": "department"},
        "values": [{"type": "lit", "value": "Engineering"}],
    }
    assert eval_expr(expr, _ROW) is False


def test_eval_expr_not_in_no_match_returns_true():
    """NOT IN returns True when lhs is NOT in the list."""
    expr = {
        "type": "in",
        "negated": True,
        "expr": {"type": "col", "name": "department"},
        "values": [{"type": "lit", "value": "HR"}],
    }
    assert eval_expr(expr, _ROW) is True


def test_eval_expr_in_null_lhs_returns_false():
    """NULL lhs returns False for IN (not unknown)."""
    expr = {
        "type": "in",
        "negated": False,
        "expr": {"type": "col", "name": "x"},
        "values": [{"type": "lit", "value": None}, {"type": "lit", "value": "Engineering"}],
    }
    assert eval_expr(expr, _ROW) is False


def test_eval_expr_not_in_null_lhs_returns_false():
    """NULL lhs returns False for NOT IN as well (consistent rule)."""
    expr = {
        "type": "in",
        "negated": True,
        "expr": {"type": "col", "name": "x"},
        "values": [{"type": "lit", "value": "Engineering"}],
    }
    assert eval_expr(expr, _ROW) is False


def test_eval_expr_in_null_value_skipped():
    """NULL inside the values list is silently skipped and never matches."""
    expr = {
        "type": "in",
        "negated": False,
        "expr": {"type": "col", "name": "department"},
        "values": [
            {"type": "lit", "value": None},
            {"type": "lit", "value": "HR"},
        ],
    }
    # department == 'Engineering', which is not HR and None is skipped
    assert eval_expr(expr, _ROW) is False


def test_eval_expr_in_null_value_does_not_prevent_match():
    """NULL in values list does not prevent matching other values."""
    expr = {
        "type": "in",
        "negated": False,
        "expr": {"type": "col", "name": "department"},
        "values": [
            {"type": "lit", "value": None},
            {"type": "lit", "value": "Engineering"},
        ],
    }
    assert eval_expr(expr, _ROW) is True


def test_eval_expr_in_numeric():
    """IN works with integer values (type coercion via ==)."""
    row = {"salary": 95000}
    expr = {
        "type": "in",
        "negated": False,
        "expr": {"type": "col", "name": "salary"},
        "values": [{"type": "lit", "value": 72000}, {"type": "lit", "value": 95000}],
    }
    assert eval_expr(expr, row) is True


# ---------------------------------------------------------------------------
# Integration: full SQL round-trip
# ---------------------------------------------------------------------------


def test_integration_in_operator_happy_path():
    """Full round-trip: WHERE department IN (...) filters correct rows."""
    sql = "SELECT name, department FROM employees WHERE department IN ('Engineering', 'Marketing') ORDER BY name ASC;"
    rows = execute(plan(sql))
    names = [r["name"] for r in rows]
    assert names == ["Alice", "Bob", "Carol", "Eve"]
    depts = {r["department"] for r in rows}
    assert depts == {"Engineering", "Marketing"}


def test_integration_not_in_operator():
    """WHERE department NOT IN ('Engineering', 'Marketing') keeps only other depts."""
    sql = "SELECT name FROM employees WHERE department NOT IN ('Engineering', 'Marketing') ORDER BY name ASC;"
    rows = execute(plan(sql))
    names = [r["name"] for r in rows]
    assert names == ["Dave"]


def test_integration_in_single_value():
    """IN with a single value behaves like equality."""
    sql = "SELECT name FROM employees WHERE department IN ('HR');"
    rows = execute(plan(sql))
    assert len(rows) == 1
    assert rows[0]["name"] == "Dave"


def test_integration_in_no_match_empty_result():
    """IN with values that match nothing returns an empty result set."""
    sql = "SELECT name FROM employees WHERE department IN ('Finance', 'Legal');"
    rows = execute(plan(sql))
    assert rows == []


def test_integration_in_integer_column():
    """IN works on integer-typed columns loaded from CSV."""
    sql = "SELECT name FROM employees WHERE id IN (1, 3);"
    rows = execute(plan(sql))
    names = sorted(r["name"] for r in rows)
    assert names == ["Alice", "Carol"]


def test_integration_in_all_match():
    """IN that matches all rows returns all rows."""
    sql = "SELECT name FROM employees WHERE department IN ('Engineering', 'Marketing', 'HR') ORDER BY name ASC;"
    rows = execute(plan(sql))
    names = [r["name"] for r in rows]
    assert names == ["Alice", "Bob", "Carol", "Dave", "Eve"]


def test_integration_in_with_having():
    """IN can be combined with GROUP BY / HAVING (IN in WHERE, HAVING separately)."""
    sql = (
        "SELECT department, COUNT(*) AS cnt FROM employees "
        "WHERE department IN ('Engineering', 'Marketing') "
        "GROUP BY department HAVING cnt > 1 ORDER BY department ASC;"
    )
    rows = execute(plan(sql))
    depts = [r["department"] for r in rows]
    assert depts == ["Engineering", "Marketing"]


def test_integration_plan_emits_in_node():
    """The planner must preserve the 'in' expression node in the Filter predicate."""
    p = plan("SELECT * FROM employees WHERE department IN ('HR');")
    # Walk the plan to find the Filter node
    node = p
    while node.get("type") != "Filter":
        node = node.get("source", {})
    assert node["predicate"]["type"] == "in"
    assert node["predicate"]["negated"] is False
