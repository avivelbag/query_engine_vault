"""Tests for the IS NULL / IS NOT NULL predicate (expression type 'isnull').

Coverage:
- Lexer: IS and NULL tokens recognised as keywords
- Parser: IS NULL and IS NOT NULL produce correct AST node
- Executor eval_expr: isnull semantics, negation, non-NULL values
- Storage: empty CSV cell coerces to None
- Integration: full SQL round-trip via plan() + execute()
- Edge cases: literal NULL expr, non-nullable column, combined with ORDER BY
- Failure modes: IS followed by non-NULL token raises ValueError
"""
import pytest

from frontend.lexer import tokenize, TK_IS, TK_NULL, TK_NOT
from frontend.parser import parse
from frontend.planner import plan
from engine.executor import execute, eval_expr
from engine.storage import load_table


# ---------------------------------------------------------------------------
# Lexer tests
# ---------------------------------------------------------------------------


def test_lexer_recognises_is_keyword():
    """IS must be emitted as TK_IS, not as a bare IDENT."""
    tokens = tokenize("WHERE manager_id IS NULL")
    types = [t.type for t in tokens]
    assert TK_IS in types


def test_lexer_recognises_null_keyword():
    """NULL must be emitted as TK_NULL, not as a bare IDENT."""
    tokens = tokenize("WHERE manager_id IS NULL")
    types = [t.type for t in tokens]
    assert TK_NULL in types


def test_lexer_is_not_null_produces_three_tokens():
    """IS NOT NULL must lex as IS, NOT, NULL (three separate tokens)."""
    tokens = tokenize("IS NOT NULL")
    types = [t.type for t in tokens]
    assert types[:3] == [TK_IS, TK_NOT, TK_NULL]


def test_lexer_is_null_case_insensitive():
    """IS and NULL keywords are case-insensitive."""
    for sql in ("is null", "Is Null", "IS NULL"):
        tokens = tokenize(f"WHERE x {sql}")
        types = [t.type for t in tokens]
        assert TK_IS in types and TK_NULL in types, f"Failed for: {sql!r}"


# ---------------------------------------------------------------------------
# Parser: AST shape tests
# ---------------------------------------------------------------------------


def test_parser_is_null_basic():
    """WHERE col IS NULL emits a correct 'isnull' predicate node."""
    ast = parse("SELECT * FROM employees WHERE manager_id IS NULL;")
    pred = ast["where"]
    assert pred["type"] == "isnull"
    assert pred["negated"] is False
    assert pred["expr"] == {"type": "col", "name": "manager_id"}


def test_parser_is_not_null():
    """WHERE col IS NOT NULL emits a negated 'isnull' node."""
    ast = parse("SELECT * FROM employees WHERE manager_id IS NOT NULL;")
    pred = ast["where"]
    assert pred["type"] == "isnull"
    assert pred["negated"] is True
    assert pred["expr"] == {"type": "col", "name": "manager_id"}


def test_parser_is_null_on_arbitrary_column():
    """IS NULL works on any column name, not just manager_id."""
    ast = parse("SELECT * FROM t WHERE some_col IS NULL;")
    pred = ast["where"]
    assert pred["type"] == "isnull"
    assert pred["expr"] == {"type": "col", "name": "some_col"}


def test_parser_is_followed_by_non_null_raises():
    """IS followed by something other than NULL or NOT NULL must raise ValueError."""
    with pytest.raises(ValueError):
        parse("SELECT * FROM t WHERE x IS 1;")


def test_parser_is_not_followed_by_null_raises():
    """IS NOT followed by something other than NULL must raise ValueError."""
    with pytest.raises(ValueError):
        parse("SELECT * FROM t WHERE x IS NOT 1;")


def test_parser_is_null_no_where_is_none():
    """Query without WHERE still returns None for the where field."""
    ast = parse("SELECT * FROM employees;")
    assert ast["where"] is None


# ---------------------------------------------------------------------------
# Executor: eval_expr unit tests
# ---------------------------------------------------------------------------


_ROW_WITH_NULL = {"manager_id": None, "name": "Alice", "salary": 95000}
_ROW_WITHOUT_NULL = {"manager_id": 1, "name": "Bob", "salary": 72000}


def test_eval_expr_isnull_none_returns_true():
    """IS NULL on a None-valued column returns True."""
    expr = {"type": "isnull", "negated": False, "expr": {"type": "col", "name": "manager_id"}}
    assert eval_expr(expr, _ROW_WITH_NULL) is True


def test_eval_expr_isnull_non_none_returns_false():
    """IS NULL on a non-None value returns False."""
    expr = {"type": "isnull", "negated": False, "expr": {"type": "col", "name": "manager_id"}}
    assert eval_expr(expr, _ROW_WITHOUT_NULL) is False


def test_eval_expr_is_not_null_none_returns_false():
    """IS NOT NULL on a None-valued column returns False."""
    expr = {"type": "isnull", "negated": True, "expr": {"type": "col", "name": "manager_id"}}
    assert eval_expr(expr, _ROW_WITH_NULL) is False


def test_eval_expr_is_not_null_non_none_returns_true():
    """IS NOT NULL on a non-None value returns True."""
    expr = {"type": "isnull", "negated": True, "expr": {"type": "col", "name": "manager_id"}}
    assert eval_expr(expr, _ROW_WITHOUT_NULL) is True


def test_eval_expr_isnull_result_is_always_bool():
    """isnull always returns a Python bool, never None."""
    expr_null = {"type": "isnull", "negated": False, "expr": {"type": "col", "name": "manager_id"}}
    expr_not_null = {"type": "isnull", "negated": True, "expr": {"type": "col", "name": "manager_id"}}
    for row in (_ROW_WITH_NULL, _ROW_WITHOUT_NULL):
        assert isinstance(eval_expr(expr_null, row), bool)
        assert isinstance(eval_expr(expr_not_null, row), bool)


def test_eval_expr_isnull_literal_none():
    """IS NULL on a literal None value returns True."""
    expr = {"type": "isnull", "negated": False, "expr": {"type": "lit", "value": None}}
    assert eval_expr(expr, {}) is True


def test_eval_expr_isnull_literal_zero_is_not_null():
    """IS NULL on the integer 0 returns False — 0 is not NULL."""
    expr = {"type": "isnull", "negated": False, "expr": {"type": "lit", "value": 0}}
    assert eval_expr(expr, {}) is False


def test_eval_expr_isnull_literal_empty_string_is_not_null():
    """IS NULL on an empty string returns False — '' is a valid string, not NULL."""
    expr = {"type": "isnull", "negated": False, "expr": {"type": "lit", "value": ""}  }
    assert eval_expr(expr, {}) is False


# ---------------------------------------------------------------------------
# Storage: empty cell → None
# ---------------------------------------------------------------------------


def test_storage_empty_cell_loads_as_none():
    """Employees with empty manager_id cell load as None."""
    rows = load_table("employees")
    alice = next(r for r in rows if r["name"] == "Alice")
    assert alice["manager_id"] is None


def test_storage_non_empty_manager_id_loads_as_int():
    """Employees with a manager_id value load it as an integer."""
    rows = load_table("employees")
    bob = next(r for r in rows if r["name"] == "Bob")
    assert bob["manager_id"] == 1
    assert isinstance(bob["manager_id"], int)


# ---------------------------------------------------------------------------
# Integration: full SQL round-trip
# ---------------------------------------------------------------------------


def test_integration_is_null_happy_path():
    """SELECT name FROM employees WHERE manager_id IS NULL ORDER BY name ASC."""
    rows = execute(plan("SELECT name FROM employees WHERE manager_id IS NULL ORDER BY name ASC;"))
    names = [r["name"] for r in rows]
    assert names == ["Alice", "Carol"]


def test_integration_is_not_null_happy_path():
    """SELECT name FROM employees WHERE manager_id IS NOT NULL ORDER BY name ASC."""
    rows = execute(plan("SELECT name FROM employees WHERE manager_id IS NOT NULL ORDER BY name ASC;"))
    names = [r["name"] for r in rows]
    assert names == ["Bob", "Dave", "Eve"]


def test_integration_is_null_and_is_not_null_are_complements():
    """IS NULL and IS NOT NULL results together cover all rows exactly once."""
    null_rows = execute(plan("SELECT name FROM employees WHERE manager_id IS NULL;"))
    not_null_rows = execute(plan("SELECT name FROM employees WHERE manager_id IS NOT NULL;"))
    all_rows = execute(plan("SELECT name FROM employees;"))
    assert len(null_rows) + len(not_null_rows) == len(all_rows)
    combined_names = sorted(r["name"] for r in null_rows + not_null_rows)
    all_names = sorted(r["name"] for r in all_rows)
    assert combined_names == all_names


def test_integration_is_null_empty_result(tmp_path, monkeypatch):
    """IS NULL on a fully-populated integer column returns no rows."""
    (tmp_path / "t.csv").write_text("x,y\n1,10\n2,20\n")
    import engine.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_DATA_DIR", tmp_path)
    rows = execute(plan("SELECT x FROM t WHERE y IS NULL;"))
    assert rows == []


def test_integration_is_not_null_all_rows(tmp_path, monkeypatch):
    """IS NOT NULL on a fully-populated column returns all rows."""
    (tmp_path / "t.csv").write_text("x,y\n1,10\n2,20\n")
    import engine.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_DATA_DIR", tmp_path)
    rows = execute(plan("SELECT x FROM t WHERE y IS NOT NULL;"))
    assert len(rows) == 2


def test_integration_is_null_all_null_column(tmp_path, monkeypatch):
    """IS NULL on an all-NULL column returns all rows."""
    (tmp_path / "t.csv").write_text("x,y\n1,\n2,\n3,\n")
    import engine.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_DATA_DIR", tmp_path)
    rows = execute(plan("SELECT x FROM t WHERE y IS NULL;"))
    assert len(rows) == 3


def test_integration_is_null_plan_emits_isnull_node():
    """The planner must preserve the 'isnull' expression node in the Filter predicate."""
    p = plan("SELECT * FROM employees WHERE manager_id IS NULL;")
    node = p
    while node.get("type") != "Filter":
        node = node.get("source", {})
    assert node["predicate"]["type"] == "isnull"
    assert node["predicate"]["negated"] is False


def test_integration_is_not_null_plan_emits_negated_isnull_node():
    """IS NOT NULL produces a negated isnull node in the Filter predicate."""
    p = plan("SELECT * FROM employees WHERE manager_id IS NOT NULL;")
    node = p
    while node.get("type") != "Filter":
        node = node.get("source", {})
    assert node["predicate"]["type"] == "isnull"
    assert node["predicate"]["negated"] is True
