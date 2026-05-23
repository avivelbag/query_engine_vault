"""Tests for aggregate functions: lexer, parser, planner, and executor."""
import pytest

from engine.executor import execute
from frontend.lexer import (
    Token,
    TK_COUNT,
    TK_SUM,
    TK_AVG,
    TK_MIN,
    TK_MAX,
    TK_LPAREN,
    TK_RPAREN,
    TK_STAR,
    TK_FROM,
    TK_IDENT,
    TK_SELECT,
    TK_EOF,
    TK_SEMI,
    tokenize,
)
from frontend.parser import parse
from frontend.planner import plan


# ---------------------------------------------------------------------------
# Lexer — aggregate keywords and parentheses
# ---------------------------------------------------------------------------


def test_lexer_count_star():
    tokens = tokenize("SELECT COUNT(*) FROM t;")
    assert tokens == [
        Token(TK_SELECT, "SELECT"),
        Token(TK_COUNT, "COUNT"),
        Token(TK_LPAREN, "("),
        Token(TK_STAR, "*"),
        Token(TK_RPAREN, ")"),
        Token(TK_FROM, "FROM"),
        Token(TK_IDENT, "t"),
        Token(TK_SEMI, ";"),
        Token(TK_EOF, ""),
    ]


def test_lexer_sum_ident():
    tokens = tokenize("SELECT SUM(salary) FROM t")
    types = [tok.type for tok in tokens]
    assert types == [TK_SELECT, TK_SUM, TK_LPAREN, TK_IDENT, TK_RPAREN, TK_FROM, TK_IDENT, TK_EOF]


def test_lexer_avg_keyword():
    tokens = tokenize("avg")
    assert tokens[0].type == TK_AVG


def test_lexer_min_max_keywords():
    tokens = tokenize("MIN MAX")
    assert tokens[0].type == TK_MIN
    assert tokens[1].type == TK_MAX


def test_lexer_keywords_case_insensitive():
    tokens = tokenize("count sum avg min max")
    types = [tok.type for tok in tokens[:-1]]
    assert types == [TK_COUNT, TK_SUM, TK_AVG, TK_MIN, TK_MAX]


# ---------------------------------------------------------------------------
# Parser — aggregate SELECT lists
# ---------------------------------------------------------------------------


def test_parser_count_star():
    """COUNT(*) produces a FuncCall with col name '*'."""
    ast = parse("SELECT COUNT(*) FROM employees")
    assert ast["columns"] == [{"type": "func", "name": "count", "args": [{"type": "col", "name": "*"}]}]
    assert ast["from"] == "employees"


def test_parser_multi_aggregate():
    ast = parse("SELECT MIN(age), MAX(age), AVG(age) FROM employees")
    cols = ast["columns"]
    assert len(cols) == 3
    assert cols[0] == {"type": "func", "name": "min", "args": [{"type": "col", "name": "age"}]}
    assert cols[1] == {"type": "func", "name": "max", "args": [{"type": "col", "name": "age"}]}
    assert cols[2] == {"type": "func", "name": "avg", "args": [{"type": "col", "name": "age"}]}


def test_parser_sum_column():
    ast = parse("SELECT SUM(salary) FROM employees")
    assert ast["columns"][0]["name"] == "sum"
    assert ast["columns"][0]["args"][0]["name"] == "salary"


def test_parser_aggregate_with_where():
    """WHERE clause is preserved alongside aggregate SELECT list."""
    ast = parse("SELECT COUNT(*) FROM employees WHERE department = 'Engineering'")
    assert ast["columns"][0]["name"] == "count"
    assert ast["where"] is not None
    assert ast["where"]["type"] == "binop"


def test_planner_mixed_aggregate_plain_raises():
    """Mixing aggregate functions and plain columns without GROUP BY must raise at plan time."""
    with pytest.raises(ValueError, match="mix"):
        plan("SELECT COUNT(*), name FROM employees")


def test_planner_plain_then_aggregate_raises():
    with pytest.raises(ValueError, match="mix"):
        plan("SELECT name, COUNT(*) FROM employees")


def test_parser_aggregate_lowercase_keyword():
    """Lower-case aggregate keywords are accepted."""
    ast = parse("select count(*) from t")
    assert ast["columns"][0]["name"] == "count"


# ---------------------------------------------------------------------------
# Planner — Aggregate node emission
# ---------------------------------------------------------------------------


def test_planner_count_star_emits_aggregate():
    p = plan("SELECT COUNT(*) FROM employees")
    assert p["type"] == "Aggregate"
    assert p["aggregates"] == [{"function": "count", "column": "*", "alias": "COUNT(*)"}]
    assert p["source"]["type"] == "Scan"


def test_planner_multi_aggregate_aliases():
    p = plan("SELECT MIN(age), MAX(age), AVG(age) FROM employees")
    aggs = p["aggregates"]
    assert aggs[0] == {"function": "min", "column": "age", "alias": "MIN(age)"}
    assert aggs[1] == {"function": "max", "column": "age", "alias": "MAX(age)"}
    assert aggs[2] == {"function": "avg", "column": "age", "alias": "AVG(age)"}


def test_planner_aggregate_with_filter():
    """WHERE clause inserts a Filter node between Scan and Aggregate."""
    p = plan("SELECT AVG(salary) FROM employees WHERE department = 'Engineering'")
    assert p["type"] == "Aggregate"
    assert p["source"]["type"] == "Filter"
    assert p["source"]["source"]["type"] == "Scan"


def test_planner_plain_columns_unaffected():
    """Non-aggregate SELECT list must not produce an Aggregate node."""
    p = plan("SELECT name, salary FROM employees")
    assert p["type"] == "Project"


# ---------------------------------------------------------------------------
# Executor — _aggregate handler
# ---------------------------------------------------------------------------


def test_execute_count_star_all_rows():
    """COUNT(*) returns the total number of rows in the table."""
    p = plan("SELECT COUNT(*) FROM employees")
    rows = execute(p)
    assert rows == [{"COUNT(*)": 5}]


def test_execute_count_star_with_filter():
    """COUNT(*) respects an upstream Filter node."""
    p = plan("SELECT COUNT(*) FROM employees WHERE department = 'Engineering'")
    rows = execute(p)
    assert rows == [{"COUNT(*)": 2}]


def test_execute_multi_aggregate_engineering():
    """MIN/MAX/AVG over filtered Engineering employees."""
    p = plan("SELECT MIN(age), MAX(age), AVG(age) FROM employees WHERE department = 'Engineering'")
    rows = execute(p)
    assert rows == [{"MIN(age)": 28, "MAX(age)": 42, "AVG(age)": 35.0}]


def test_execute_sum_salary():
    p = plan("SELECT SUM(salary) FROM employees")
    rows = execute(p)
    assert rows == [{"SUM(salary)": 95000 + 72000 + 110000 + 65000 + 78000}]


def test_execute_min_salary():
    p = plan("SELECT MIN(salary) FROM employees")
    rows = execute(p)
    assert rows == [{"MIN(salary)": 65000}]


def test_execute_max_salary():
    p = plan("SELECT MAX(salary) FROM employees")
    rows = execute(p)
    assert rows == [{"MAX(salary)": 110000}]


def test_execute_aggregate_returns_single_row():
    """Aggregate always returns exactly one row."""
    p = plan("SELECT COUNT(*) FROM employees")
    rows = execute(p)
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# Edge cases — empty table
# ---------------------------------------------------------------------------


def test_aggregate_count_star_empty_table(tmp_path, monkeypatch):
    """COUNT(*) on an empty table returns 0."""
    (tmp_path / "empty.csv").write_text("id,name\n")
    import engine.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_DATA_DIR", tmp_path)

    p = {"type": "Aggregate", "source": {"type": "Scan", "table": "empty", "columns": "*"},
         "aggregates": [{"function": "count", "column": "*", "alias": "COUNT(*)"}]}
    rows = execute(p)
    assert rows == [{"COUNT(*)": 0}]


def test_aggregate_sum_empty_table_returns_null(tmp_path, monkeypatch):
    """SUM on empty table returns None (SQL NULL)."""
    (tmp_path / "empty.csv").write_text("val\n")
    import engine.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_DATA_DIR", tmp_path)

    p = {"type": "Aggregate", "source": {"type": "Scan", "table": "empty", "columns": "*"},
         "aggregates": [{"function": "sum", "column": "val", "alias": "SUM(val)"}]}
    rows = execute(p)
    assert rows == [{"SUM(val)": None}]


def test_aggregate_avg_empty_table_returns_null(tmp_path, monkeypatch):
    """AVG on empty table returns None."""
    (tmp_path / "empty.csv").write_text("n\n")
    import engine.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_DATA_DIR", tmp_path)

    p = {"type": "Aggregate", "source": {"type": "Scan", "table": "empty", "columns": "*"},
         "aggregates": [{"function": "avg", "column": "n", "alias": "AVG(n)"}]}
    rows = execute(p)
    assert rows == [{"AVG(n)": None}]


def test_aggregate_min_max_empty_table_returns_null(tmp_path, monkeypatch):
    """MIN and MAX on empty table both return None."""
    (tmp_path / "empty.csv").write_text("x\n")
    import engine.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_DATA_DIR", tmp_path)

    p = {"type": "Aggregate", "source": {"type": "Scan", "table": "empty", "columns": "*"},
         "aggregates": [
             {"function": "min", "column": "x", "alias": "MIN(x)"},
             {"function": "max", "column": "x", "alias": "MAX(x)"},
         ]}
    rows = execute(p)
    assert rows == [{"MIN(x)": None, "MAX(x)": None}]


def test_aggregate_count_col_all_nulls(monkeypatch):
    """COUNT(col) on a column of all-None values returns 0."""
    import engine.executor as executor_mod
    monkeypatch.setattr(executor_mod, "load_table", lambda name: [{"val": None}, {"val": None}])

    p = {"type": "Aggregate", "source": {"type": "Scan", "table": "dummy", "columns": "*"},
         "aggregates": [{"function": "count", "column": "val", "alias": "COUNT(val)"}]}
    rows = execute(p)
    assert rows == [{"COUNT(val)": 0}]


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------


def test_execute_unknown_aggregate_function_raises():
    """An unrecognised aggregate function name must raise ValueError."""
    p = {"type": "Aggregate",
         "source": {"type": "Scan", "table": "employees", "columns": "*"},
         "aggregates": [{"function": "median", "column": "age", "alias": "MEDIAN(age)"}]}
    with pytest.raises(ValueError, match="Unknown aggregate function"):
        execute(p)


def test_parser_aggregate_missing_rparen_raises():
    """Missing closing parenthesis must raise ValueError."""
    with pytest.raises(ValueError):
        parse("SELECT COUNT( FROM employees")


def test_parser_aggregate_missing_lparen_raises():
    """Missing opening parenthesis (e.g. bare COUNT without parens) must raise."""
    with pytest.raises(ValueError):
        parse("SELECT COUNT FROM employees")
