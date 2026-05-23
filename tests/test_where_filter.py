"""Tests for WHERE clause: lexer tokens, parser AST, planner Filter node,
executor Filter execution, and eval_expr expression evaluation."""
import pytest

from engine.executor import eval_expr, execute
from frontend.lexer import (
    Token,
    TK_EOF,
    TK_EQ,
    TK_NEQ,
    TK_LT,
    TK_LTE,
    TK_GT,
    TK_GTE,
    TK_FLOAT_LIT,
    TK_IDENT,
    TK_INT_LIT,
    TK_SELECT,
    TK_FROM,
    TK_WHERE,
    TK_SEMI,
    TK_STAR,
    TK_STRING_LIT,
    tokenize,
)
from frontend.parser import parse
from frontend.planner import plan


# ---------------------------------------------------------------------------
# Lexer — new tokens
# ---------------------------------------------------------------------------


def test_lexer_where_keyword():
    tokens = tokenize("WHERE")
    assert tokens[0] == Token(TK_WHERE, "WHERE")


def test_lexer_where_case_insensitive():
    tokens = tokenize("where")
    assert tokens[0].type == TK_WHERE


def test_lexer_eq_operator():
    tokens = tokenize("=")
    assert tokens[0] == Token(TK_EQ, "=")


def test_lexer_neq_operator():
    tokens = tokenize("!=")
    assert tokens[0] == Token(TK_NEQ, "!=")


def test_lexer_lt_operator():
    tokens = tokenize("<")
    assert tokens[0] == Token(TK_LT, "<")


def test_lexer_lte_operator():
    tokens = tokenize("<=")
    assert tokens[0] == Token(TK_LTE, "<=")


def test_lexer_gt_operator():
    tokens = tokenize(">")
    assert tokens[0] == Token(TK_GT, ">")


def test_lexer_gte_operator():
    tokens = tokenize(">=")
    assert tokens[0] == Token(TK_GTE, ">=")


def test_lexer_string_literal_single_quoted():
    tokens = tokenize("'Engineering'")
    assert tokens[0] == Token(TK_STRING_LIT, "Engineering")


def test_lexer_string_literal_strips_quotes():
    tokens = tokenize("'hello world'")
    assert tokens[0].value == "hello world"


def test_lexer_int_literal():
    tokens = tokenize("42")
    assert tokens[0] == Token(TK_INT_LIT, "42")


def test_lexer_float_literal():
    tokens = tokenize("3.14")
    assert tokens[0] == Token(TK_FLOAT_LIT, "3.14")


def test_lexer_unterminated_string_raises():
    with pytest.raises(ValueError, match="Unterminated string literal"):
        tokenize("'oops")


def test_lexer_bare_exclamation_raises():
    with pytest.raises(ValueError, match="Unexpected character"):
        tokenize("!")


def test_lexer_full_where_clause():
    tokens = tokenize("SELECT * FROM employees WHERE department = 'Engineering';")
    types = [t.type for t in tokens]
    assert types == [
        TK_SELECT, TK_STAR, TK_FROM, TK_IDENT, TK_WHERE,
        TK_IDENT, TK_EQ, TK_STRING_LIT, TK_SEMI, TK_EOF,
    ]


def test_lexer_where_with_int_literal():
    tokens = tokenize("WHERE age > 30")
    types = [t.type for t in tokens]
    assert types == [TK_WHERE, TK_IDENT, TK_GT, TK_INT_LIT, TK_EOF]


# ---------------------------------------------------------------------------
# Parser — WHERE clause
# ---------------------------------------------------------------------------


def test_parser_where_equality_string():
    ast = parse("SELECT * FROM employees WHERE department = 'Engineering'")
    assert ast["where"] == {
        "type": "binop",
        "op": "=",
        "left": {"type": "col", "name": "department"},
        "right": {"type": "lit", "value": "Engineering"},
    }


def test_parser_where_range_int():
    ast = parse("SELECT * FROM employees WHERE age > 30")
    assert ast["where"] == {
        "type": "binop",
        "op": ">",
        "left": {"type": "col", "name": "age"},
        "right": {"type": "lit", "value": 30},
    }


def test_parser_where_int_literal_is_int():
    ast = parse("SELECT * FROM t WHERE x = 5")
    assert isinstance(ast["where"]["right"]["value"], int)
    assert ast["where"]["right"]["value"] == 5


def test_parser_where_float_literal_is_float():
    ast = parse("SELECT * FROM t WHERE x <= 2.5")
    assert isinstance(ast["where"]["right"]["value"], float)
    assert ast["where"]["right"]["value"] == pytest.approx(2.5)


def test_parser_no_where_yields_none():
    ast = parse("SELECT * FROM employees")
    assert ast["where"] is None


def test_parser_where_with_semicolon():
    ast = parse("SELECT * FROM employees WHERE department = 'Engineering';")
    assert ast["where"] is not None
    assert ast["from"] == "employees"


def test_parser_where_all_ops():
    for op_str, sql_op in [("=", "="), ("!=", "!="), ("<", "<"), ("<=", "<="), (">", ">"), (">=", ">=")]:
        ast = parse(f"SELECT * FROM t WHERE x {op_str} 1")
        assert ast["where"]["op"] == op_str


def test_parser_where_missing_literal_raises():
    with pytest.raises(ValueError):
        parse("SELECT * FROM t WHERE x =")


def test_parser_where_missing_operator_raises():
    with pytest.raises(ValueError):
        parse("SELECT * FROM t WHERE x x")


# ---------------------------------------------------------------------------
# Planner — Filter wrapping
# ---------------------------------------------------------------------------


def test_planner_where_wraps_scan_in_filter():
    p = plan("SELECT * FROM employees WHERE department = 'Engineering'")
    assert p["type"] == "Filter"
    assert p["source"] == {"type": "Scan", "table": "employees", "columns": "*"}


def test_planner_filter_predicate_shape():
    p = plan("SELECT * FROM employees WHERE department = 'Engineering'")
    pred = p["predicate"]
    assert pred["type"] == "binop"
    assert pred["op"] == "="
    assert pred["left"] == {"type": "col", "name": "department"}
    assert pred["right"] == {"type": "lit", "value": "Engineering"}


def test_planner_where_with_projection():
    p = plan("SELECT id, name FROM employees WHERE department = 'Engineering'")
    assert p["type"] == "Project"
    assert p["source"]["type"] == "Filter"
    assert p["source"]["source"]["type"] == "Scan"


def test_planner_no_where_no_filter():
    p = plan("SELECT * FROM employees")
    assert p["type"] == "Scan"
    assert "predicate" not in p


def test_planner_no_where_project_no_filter():
    p = plan("SELECT id FROM employees")
    assert p["type"] == "Project"
    assert p["source"]["type"] == "Scan"


# ---------------------------------------------------------------------------
# eval_expr
# ---------------------------------------------------------------------------


def test_eval_expr_col_ref():
    row = {"age": 28, "name": "Alice"}
    assert eval_expr({"type": "col", "name": "age"}, row) == 28


def test_eval_expr_literal_int():
    assert eval_expr({"type": "lit", "value": 42}, {}) == 42


def test_eval_expr_literal_string():
    assert eval_expr({"type": "lit", "value": "hello"}, {}) == "hello"


def test_eval_expr_eq_true():
    expr = {"type": "binop", "op": "=", "left": {"type": "lit", "value": 1}, "right": {"type": "lit", "value": 1}}
    assert eval_expr(expr, {}) is True


def test_eval_expr_eq_false():
    expr = {"type": "binop", "op": "=", "left": {"type": "lit", "value": 1}, "right": {"type": "lit", "value": 2}}
    assert eval_expr(expr, {}) is False


def test_eval_expr_neq():
    expr = {"type": "binop", "op": "!=", "left": {"type": "lit", "value": 1}, "right": {"type": "lit", "value": 2}}
    assert eval_expr(expr, {}) is True


def test_eval_expr_lt():
    expr = {"type": "binop", "op": "<", "left": {"type": "lit", "value": 1}, "right": {"type": "lit", "value": 2}}
    assert eval_expr(expr, {}) is True


def test_eval_expr_lte_equal():
    expr = {"type": "binop", "op": "<=", "left": {"type": "lit", "value": 2}, "right": {"type": "lit", "value": 2}}
    assert eval_expr(expr, {}) is True


def test_eval_expr_gt():
    expr = {"type": "binop", "op": ">", "left": {"type": "lit", "value": 5}, "right": {"type": "lit", "value": 3}}
    assert eval_expr(expr, {}) is True


def test_eval_expr_gte_equal():
    expr = {"type": "binop", "op": ">=", "left": {"type": "lit", "value": 3}, "right": {"type": "lit", "value": 3}}
    assert eval_expr(expr, {}) is True


def test_eval_expr_null_left_yields_false():
    expr = {"type": "binop", "op": "=", "left": {"type": "col", "name": "x"}, "right": {"type": "lit", "value": 1}}
    assert eval_expr(expr, {"x": None}) is False


def test_eval_expr_null_right_yields_false():
    expr = {"type": "binop", "op": "=", "left": {"type": "lit", "value": 1}, "right": {"type": "col", "name": "x"}}
    assert eval_expr(expr, {"x": None}) is False


def test_eval_expr_null_eq_null_yields_false():
    expr = {
        "type": "binop", "op": "=",
        "left": {"type": "col", "name": "x"},
        "right": {"type": "col", "name": "y"},
    }
    assert eval_expr(expr, {"x": None, "y": None}) is False


def test_eval_expr_int_float_coercion():
    expr = {
        "type": "binop", "op": "=",
        "left": {"type": "lit", "value": 1},
        "right": {"type": "lit", "value": 1.0},
    }
    assert eval_expr(expr, {}) is True


def test_eval_expr_unknown_type_raises():
    with pytest.raises(ValueError, match="Unknown expression type"):
        eval_expr({"type": "unknown"}, {})


def test_eval_expr_unknown_op_raises():
    expr = {"type": "binop", "op": "??", "left": {"type": "lit", "value": 1}, "right": {"type": "lit", "value": 1}}
    with pytest.raises(ValueError, match="Unknown operator"):
        eval_expr(expr, {})


# ---------------------------------------------------------------------------
# Executor — Filter node
# ---------------------------------------------------------------------------


def test_execute_filter_equality():
    p = {
        "type": "Filter",
        "source": {"type": "Scan", "table": "employees", "columns": "*"},
        "predicate": {
            "type": "binop", "op": "=",
            "left": {"type": "col", "name": "department"},
            "right": {"type": "lit", "value": "Engineering"},
        },
    }
    rows = execute(p)
    assert len(rows) == 2
    assert all(r["department"] == "Engineering" for r in rows)


def test_execute_filter_range():
    p = {
        "type": "Filter",
        "source": {"type": "Scan", "table": "employees", "columns": "*"},
        "predicate": {
            "type": "binop", "op": ">",
            "left": {"type": "col", "name": "age"},
            "right": {"type": "lit", "value": 30},
        },
    }
    rows = execute(p)
    assert len(rows) == 3
    assert all(r["age"] > 30 for r in rows)


def test_execute_filter_no_matches(tmp_path, monkeypatch):
    """Filter that matches no rows returns empty list."""
    (tmp_path / "t.csv").write_text("x\n1\n2\n")
    import engine.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_DATA_DIR", tmp_path)
    p = {
        "type": "Filter",
        "source": {"type": "Scan", "table": "t", "columns": "*"},
        "predicate": {
            "type": "binop", "op": ">",
            "left": {"type": "col", "name": "x"},
            "right": {"type": "lit", "value": 100},
        },
    }
    assert execute(p) == []


def test_execute_filter_empty_source(tmp_path, monkeypatch):
    """Filter over an empty table returns empty list."""
    (tmp_path / "empty.csv").write_text("x\n")
    import engine.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_DATA_DIR", tmp_path)
    p = {
        "type": "Filter",
        "source": {"type": "Scan", "table": "empty", "columns": "*"},
        "predicate": {
            "type": "binop", "op": "=",
            "left": {"type": "col", "name": "x"},
            "right": {"type": "lit", "value": 1},
        },
    }
    assert execute(p) == []


def test_execute_filter_preserves_all_columns():
    p = {
        "type": "Filter",
        "source": {"type": "Scan", "table": "employees", "columns": "*"},
        "predicate": {
            "type": "binop", "op": "=",
            "left": {"type": "col", "name": "department"},
            "right": {"type": "lit", "value": "Engineering"},
        },
    }
    rows = execute(p)
    assert set(rows[0].keys()) == {"id", "name", "department", "salary", "age", "dept_id", "manager_id"}


# ---------------------------------------------------------------------------
# End-to-end: plan → execute
# ---------------------------------------------------------------------------


def test_e2e_where_equality():
    rows = execute(plan("SELECT * FROM employees WHERE department = 'Engineering'"))
    names = [r["name"] for r in rows]
    assert names == ["Alice", "Carol"]


def test_e2e_where_range():
    rows = execute(plan("SELECT * FROM employees WHERE age > 30"))
    names = [r["name"] for r in rows]
    assert names == ["Bob", "Carol", "Eve"]


def test_e2e_where_with_projection():
    rows = execute(plan("SELECT name FROM employees WHERE department = 'Engineering'"))
    assert rows == [{"name": "Alice"}, {"name": "Carol"}]


def test_e2e_where_neq():
    rows = execute(plan("SELECT * FROM employees WHERE department != 'Engineering'"))
    names = [r["name"] for r in rows]
    assert names == ["Bob", "Dave", "Eve"]


def test_e2e_where_lte():
    rows = execute(plan("SELECT * FROM employees WHERE age <= 29"))
    names = [r["name"] for r in rows]
    assert names == ["Alice", "Dave"]


def test_e2e_where_gte():
    rows = execute(plan("SELECT * FROM employees WHERE salary >= 95000"))
    names = [r["name"] for r in rows]
    assert names == ["Alice", "Carol"]


def test_e2e_where_case_insensitive_keywords():
    rows_upper = execute(plan("SELECT * FROM employees WHERE department = 'Engineering'"))
    rows_lower = execute(plan("select * from employees where department = 'Engineering'"))
    assert rows_upper == rows_lower
