"""Tests for scalar arithmetic expressions (+, -, *, /) and AS column aliases."""
import pytest

from engine.executor import eval_expr, execute, _normalise_col_desc
from frontend.lexer import (
    Token,
    TK_PLUS,
    TK_MINUS,
    TK_SLASH,
    TK_AS,
    TK_IDENT,
    TK_INT_LIT,
    TK_FLOAT_LIT,
    TK_STAR,
    TK_EOF,
    tokenize,
)
from frontend.parser import parse
from frontend.planner import plan


# ---------------------------------------------------------------------------
# Lexer — new arithmetic and AS tokens
# ---------------------------------------------------------------------------


def test_lexer_plus_token():
    tokens = tokenize("+")
    assert tokens[0] == Token(TK_PLUS, "+")


def test_lexer_minus_standalone():
    tokens = tokenize("a - b")
    types = [t.type for t in tokens]
    assert TK_MINUS in types


def test_lexer_slash_token():
    tokens = tokenize("/")
    assert tokens[0] == Token(TK_SLASH, "/")


def test_lexer_as_keyword():
    tokens = tokenize("AS")
    assert tokens[0] == Token(TK_AS, "AS")


def test_lexer_as_case_insensitive():
    tokens = tokenize("as")
    assert tokens[0].type == TK_AS


def test_lexer_arithmetic_expression():
    tokens = tokenize("salary * 1.1")
    types = [t.type for t in tokens]
    assert types == [TK_IDENT, TK_STAR, TK_FLOAT_LIT, TK_EOF]


def test_lexer_arithmetic_full_select_contains_as():
    tokens = tokenize("SELECT salary * 1.1 AS raised_salary FROM employees;")
    types = [t.type for t in tokens]
    assert TK_AS in types


def test_lexer_negative_literal_preserved():
    tokens = tokenize("-7")
    assert tokens[0] == Token(TK_INT_LIT, "-7")


def test_lexer_minus_subtraction():
    tokens = tokenize("age - 10")
    types = [t.type for t in tokens[:-1]]
    assert types == [TK_IDENT, TK_MINUS, TK_INT_LIT]


def test_lexer_division():
    tokens = tokenize("salary / 12")
    types = [t.type for t in tokens[:-1]]
    assert types == [TK_IDENT, TK_SLASH, TK_INT_LIT]


def test_lexer_addition():
    tokens = tokenize("age + 5")
    types = [t.type for t in tokens[:-1]]
    assert types == [TK_IDENT, TK_PLUS, TK_INT_LIT]


# ---------------------------------------------------------------------------
# Parser — arithmetic expressions
# ---------------------------------------------------------------------------


def test_parser_arithmetic_multiply_in_select():
    ast = parse("SELECT salary * 1.1 AS raised_salary FROM employees")
    cols = ast["columns"]
    assert len(cols) == 1
    desc = cols[0]
    assert desc["alias"] == "raised_salary"
    assert desc["expr"]["type"] == "binop"
    assert desc["expr"]["op"] == "*"
    assert desc["expr"]["left"] == {"type": "col", "name": "salary"}
    assert desc["expr"]["right"]["value"] == pytest.approx(1.1)


def test_parser_plain_column_stays_bare_string():
    ast = parse("SELECT name FROM employees")
    assert ast["columns"] == ["name"]


def test_parser_two_plain_columns_stay_bare_strings():
    ast = parse("SELECT name, age FROM employees")
    assert ast["columns"] == ["name", "age"]


def test_parser_mixed_plain_and_arithmetic():
    ast = parse("SELECT name, salary * 1.1 AS raised_salary FROM employees")
    cols = ast["columns"]
    assert cols[0] == "name"
    assert cols[1]["alias"] == "raised_salary"


def test_parser_as_alias_plain_column():
    ast = parse("SELECT name AS employee_name FROM employees")
    col = ast["columns"][0]
    assert col["expr"] == {"type": "col", "name": "name"}
    assert col["alias"] == "employee_name"


def test_parser_arithmetic_precedence_mul_before_add():
    """2 + 3 * 4 must parse as 2 + (3 * 4), not (2 + 3) * 4."""
    ast = parse("SELECT 2 + 3 * 4 AS result FROM t")
    expr = ast["columns"][0]["expr"]
    assert expr["op"] == "+"
    assert expr["left"] == {"type": "lit", "value": 2}
    right = expr["right"]
    assert right["op"] == "*"
    assert right["left"] == {"type": "lit", "value": 3}
    assert right["right"] == {"type": "lit", "value": 4}


def test_parser_arithmetic_precedence_div_before_sub():
    """10 - 6 / 2 must parse as 10 - (6 / 2)."""
    ast = parse("SELECT 10 - 6 / 2 AS result FROM t")
    expr = ast["columns"][0]["expr"]
    assert expr["op"] == "-"
    assert expr["left"] == {"type": "lit", "value": 10}
    right = expr["right"]
    assert right["op"] == "/"
    assert right["left"] == {"type": "lit", "value": 6}
    assert right["right"] == {"type": "lit", "value": 2}


def test_parser_arithmetic_left_associative():
    """a - b - c must parse as (a - b) - c."""
    ast = parse("SELECT 10 - 3 - 2 AS result FROM t")
    expr = ast["columns"][0]["expr"]
    assert expr["op"] == "-"
    assert expr["right"] == {"type": "lit", "value": 2}
    left = expr["left"]
    assert left["op"] == "-"
    assert left["left"] == {"type": "lit", "value": 10}
    assert left["right"] == {"type": "lit", "value": 3}


def test_parser_arithmetic_in_where():
    ast = parse("SELECT * FROM employees WHERE age * 2 > 50")
    pred = ast["where"]
    assert pred["op"] == ">"
    assert pred["left"]["op"] == "*"
    assert pred["left"]["left"] == {"type": "col", "name": "age"}
    assert pred["left"]["right"] == {"type": "lit", "value": 2}
    assert pred["right"] == {"type": "lit", "value": 50}


def test_parser_arithmetic_add_in_where():
    ast = parse("SELECT * FROM t WHERE age + 5 < 40")
    pred = ast["where"]
    assert pred["op"] == "<"
    assert pred["left"]["op"] == "+"


def test_parser_parenthesised_expr():
    """(2 + 3) * 4 must respect parentheses and override default precedence."""
    ast = parse("SELECT (2 + 3) * 4 AS result FROM t")
    expr = ast["columns"][0]["expr"]
    assert expr["op"] == "*"
    assert expr["right"] == {"type": "lit", "value": 4}
    inner = expr["left"]
    assert inner["op"] == "+"


# ---------------------------------------------------------------------------
# Planner — Project with arithmetic/alias descriptors
# ---------------------------------------------------------------------------


def test_planner_arithmetic_select_emits_project():
    p = plan("SELECT name, salary * 1.1 AS raised_salary FROM employees")
    assert p["type"] == "Project"
    assert p["source"]["type"] == "Scan"


def test_planner_arithmetic_column_descriptor():
    p = plan("SELECT salary * 1.1 AS raised_salary FROM employees")
    col_desc = p["columns"][0]
    assert col_desc["alias"] == "raised_salary"
    assert col_desc["expr"]["op"] == "*"


def test_planner_plain_columns_still_bare_strings():
    p = plan("SELECT name, age FROM employees")
    assert p["columns"] == ["name", "age"]


def test_planner_arithmetic_with_where():
    p = plan("SELECT name FROM employees WHERE age * 2 > 50")
    assert p["type"] == "Project"
    assert p["source"]["type"] == "Filter"
    pred = p["source"]["predicate"]
    assert pred["op"] == ">"
    assert pred["left"]["op"] == "*"


def test_planner_arithmetic_with_order_by():
    p = plan(
        "SELECT name, salary * 1.1 AS raised_salary FROM employees ORDER BY raised_salary DESC"
    )
    assert p["type"] == "Sort"
    assert p["keys"][0] == {"column": "raised_salary", "direction": "desc"}
    assert p["source"]["type"] == "Project"


# ---------------------------------------------------------------------------
# eval_expr — arithmetic operators
# ---------------------------------------------------------------------------


def test_eval_expr_add_int():
    expr = {
        "type": "binop", "op": "+",
        "left": {"type": "lit", "value": 3},
        "right": {"type": "lit", "value": 4},
    }
    result = eval_expr(expr, {})
    assert result == 7
    assert isinstance(result, int)


def test_eval_expr_sub_int():
    expr = {
        "type": "binop", "op": "-",
        "left": {"type": "lit", "value": 10},
        "right": {"type": "lit", "value": 3},
    }
    result = eval_expr(expr, {})
    assert result == 7
    assert isinstance(result, int)


def test_eval_expr_mul_int():
    expr = {
        "type": "binop", "op": "*",
        "left": {"type": "lit", "value": 6},
        "right": {"type": "lit", "value": 7},
    }
    result = eval_expr(expr, {})
    assert result == 42
    assert isinstance(result, int)


def test_eval_expr_div_int_yields_float():
    """int / int → float (Python 3 true division)."""
    expr = {
        "type": "binop", "op": "/",
        "left": {"type": "lit", "value": 10},
        "right": {"type": "lit", "value": 4},
    }
    result = eval_expr(expr, {})
    assert result == pytest.approx(2.5)
    assert isinstance(result, float)


def test_eval_expr_mul_float():
    expr = {
        "type": "binop", "op": "*",
        "left": {"type": "col", "name": "salary"},
        "right": {"type": "lit", "value": 1.1},
    }
    result = eval_expr(expr, {"salary": 95000})
    assert isinstance(result, float)
    assert result == pytest.approx(104500.0, rel=1e-9)


def test_eval_expr_null_left_arithmetic_propagates():
    """NULL on the left side of arithmetic returns None, not False."""
    expr = {
        "type": "binop", "op": "*",
        "left": {"type": "col", "name": "x"},
        "right": {"type": "lit", "value": 2},
    }
    assert eval_expr(expr, {"x": None}) is None


def test_eval_expr_null_right_arithmetic_propagates():
    expr = {
        "type": "binop", "op": "+",
        "left": {"type": "lit", "value": 5},
        "right": {"type": "col", "name": "x"},
    }
    assert eval_expr(expr, {"x": None}) is None


def test_eval_expr_division_by_zero_raises():
    expr = {
        "type": "binop", "op": "/",
        "left": {"type": "lit", "value": 10},
        "right": {"type": "lit", "value": 0},
    }
    with pytest.raises(ZeroDivisionError):
        eval_expr(expr, {})


def test_eval_expr_nested_arithmetic_in_comparison_true():
    """age * 2 > 50 for age=28 should be True (56 > 50)."""
    outer = {
        "type": "binop", "op": ">",
        "left": {
            "type": "binop", "op": "*",
            "left": {"type": "col", "name": "age"},
            "right": {"type": "lit", "value": 2},
        },
        "right": {"type": "lit", "value": 50},
    }
    assert eval_expr(outer, {"age": 28}) is True


def test_eval_expr_nested_arithmetic_in_comparison_false():
    """age * 2 > 50 for age=24 should be False (48 > 50 is false)."""
    outer = {
        "type": "binop", "op": ">",
        "left": {
            "type": "binop", "op": "*",
            "left": {"type": "col", "name": "age"},
            "right": {"type": "lit", "value": 2},
        },
        "right": {"type": "lit", "value": 50},
    }
    assert eval_expr(outer, {"age": 24}) is False


def test_eval_expr_arithmetic_null_propagates_through_comparison():
    """If arithmetic yields None, the enclosing comparison must return False."""
    outer = {
        "type": "binop", "op": ">",
        "left": {
            "type": "binop", "op": "*",
            "left": {"type": "col", "name": "age"},
            "right": {"type": "lit", "value": 2},
        },
        "right": {"type": "lit", "value": 50},
    }
    assert eval_expr(outer, {"age": None}) is False


# ---------------------------------------------------------------------------
# _normalise_col_desc
# ---------------------------------------------------------------------------


def test_normalise_bare_string():
    desc = _normalise_col_desc("salary")
    assert desc == {"expr": {"type": "col", "name": "salary"}, "alias": None}


def test_normalise_dict_passthrough():
    d = {"expr": {"type": "lit", "value": 1}, "alias": "one"}
    assert _normalise_col_desc(d) is d


# ---------------------------------------------------------------------------
# Executor — Project with arithmetic / alias
# ---------------------------------------------------------------------------


def test_execute_project_arithmetic_column():
    p = {
        "type": "Project",
        "source": {"type": "Scan", "table": "employees", "columns": "*"},
        "columns": [
            "name",
            {
                "expr": {
                    "type": "binop", "op": "*",
                    "left": {"type": "col", "name": "salary"},
                    "right": {"type": "lit", "value": 1.1},
                },
                "alias": "raised_salary",
            },
        ],
    }
    rows = execute(p)
    assert len(rows) == 5
    assert set(rows[0].keys()) == {"name", "raised_salary"}
    alice = next(r for r in rows if r["name"] == "Alice")
    assert alice["raised_salary"] == pytest.approx(104500.0, rel=1e-9)


def test_execute_project_alias_is_used_as_key():
    p = {
        "type": "Project",
        "source": {"type": "Scan", "table": "employees", "columns": "*"},
        "columns": [
            {"expr": {"type": "col", "name": "name"}, "alias": "employee_name"},
        ],
    }
    rows = execute(p)
    assert "employee_name" in rows[0]
    assert "name" not in rows[0]


def test_execute_project_backward_compat_bare_strings():
    """Bare string columns must still work after _normalise_col_desc was introduced."""
    p = {
        "type": "Project",
        "source": {"type": "Scan", "table": "employees", "columns": "*"},
        "columns": ["id", "name"],
    }
    rows = execute(p)
    assert rows[0] == {"id": 1, "name": "Alice"}


def test_execute_project_empty_source_arithmetic(tmp_path, monkeypatch):
    (tmp_path / "empty.csv").write_text("salary\n")
    import engine.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_DATA_DIR", tmp_path)
    p = {
        "type": "Project",
        "source": {"type": "Scan", "table": "empty", "columns": "*"},
        "columns": [
            {
                "expr": {
                    "type": "binop", "op": "*",
                    "left": {"type": "col", "name": "salary"},
                    "right": {"type": "lit", "value": 1.1},
                },
                "alias": "raised_salary",
            },
        ],
    }
    assert execute(p) == []


# ---------------------------------------------------------------------------
# End-to-end: plan → execute
# ---------------------------------------------------------------------------


def test_e2e_arithmetic_select_order():
    """SELECT name, salary * 1.1 AS raised_salary ORDER BY raised_salary DESC."""
    rows = execute(plan(
        "SELECT name, salary * 1.1 AS raised_salary FROM employees ORDER BY raised_salary DESC"
    ))
    names = [r["name"] for r in rows]
    assert names == ["Carol", "Alice", "Eve", "Bob", "Dave"]
    assert rows[0]["raised_salary"] == pytest.approx(121000.0, rel=1e-4)


def test_e2e_arithmetic_where_all_pass():
    """WHERE age * 2 > 50 — all 5 employees pass (min age 28 → 56 > 50)."""
    rows = execute(plan(
        "SELECT name, age FROM employees WHERE age * 2 > 50 ORDER BY name ASC"
    ))
    assert len(rows) == 5
    names = [r["name"] for r in rows]
    assert names == ["Alice", "Bob", "Carol", "Dave", "Eve"]


def test_e2e_arithmetic_where_partial_match():
    """WHERE age + 10 > 45 — Carol (42+10=52) and Eve (38+10=48) qualify; Bob (35+10=45) does not."""
    rows = execute(plan(
        "SELECT name FROM employees WHERE age + 10 > 45 ORDER BY name ASC"
    ))
    names = [r["name"] for r in rows]
    assert names == ["Carol", "Eve"]


def test_e2e_division_in_select():
    """salary / 12 produces float monthly values."""
    rows = execute(plan(
        "SELECT name, salary / 12 AS monthly FROM employees ORDER BY name ASC"
    ))
    alice = rows[0]
    assert "monthly" in alice
    assert isinstance(alice["monthly"], float)
    assert alice["monthly"] == pytest.approx(95000 / 12, rel=1e-9)


def test_e2e_subtraction_in_select():
    rows = execute(plan(
        "SELECT name, age - 20 AS years_over_20 FROM employees ORDER BY name ASC"
    ))
    alice = rows[0]
    assert alice["years_over_20"] == 8


def test_e2e_addition_in_where_single_match():
    """WHERE salary + 5000 > 100000 — only Carol (110000+5000=115000) qualifies."""
    rows = execute(plan(
        "SELECT name FROM employees WHERE salary + 5000 > 100000 ORDER BY name ASC"
    ))
    names = [r["name"] for r in rows]
    assert names == ["Carol"]


def test_e2e_large_arithmetic():
    """Large integer arithmetic stays numerically correct."""
    rows = execute(plan(
        "SELECT salary * 1000 AS big FROM employees ORDER BY big DESC"
    ))
    assert rows[0]["big"] == 110000 * 1000


def test_e2e_plain_columns_unaffected_by_arithmetic_feature():
    """Plain column projections still work correctly after the arithmetic changes."""
    rows = execute(plan("SELECT name, age FROM employees ORDER BY age ASC"))
    assert rows[0]["name"] == "Alice"
    assert "salary" not in rows[0]
