"""Tests for GROUP BY and HAVING: lexer, parser, planner, and executor."""
import pytest

from engine.executor import execute
from frontend.lexer import (
    Token,
    TK_GROUP,
    TK_HAVING,
    TK_BY,
    TK_IDENT,
    TK_AS,
    TK_EOF,
    tokenize,
)
from frontend.parser import parse
from frontend.planner import plan


# ---------------------------------------------------------------------------
# Lexer — GROUP and HAVING keywords
# ---------------------------------------------------------------------------


def test_lexer_group_keyword():
    tokens = tokenize("GROUP")
    assert tokens[0] == Token(TK_GROUP, "GROUP")


def test_lexer_having_keyword():
    tokens = tokenize("HAVING")
    assert tokens[0] == Token(TK_HAVING, "HAVING")


def test_lexer_group_case_insensitive():
    tokens = tokenize("group")
    assert tokens[0].type == TK_GROUP


def test_lexer_having_case_insensitive():
    tokens = tokenize("having")
    assert tokens[0].type == TK_HAVING


def test_lexer_group_by_sequence():
    tokens = tokenize("GROUP BY department")
    types = [t.type for t in tokens]
    assert types == [TK_GROUP, TK_BY, TK_IDENT, TK_EOF]


def test_lexer_full_group_by_having_query():
    """Full GROUP BY HAVING query tokenises correctly."""
    sql = "SELECT department, COUNT(*) AS cnt FROM employees GROUP BY department HAVING cnt > 1;"
    tokens = tokenize(sql)
    types = [t.type for t in tokens]
    assert TK_GROUP in types
    assert TK_HAVING in types
    assert TK_AS in types


# ---------------------------------------------------------------------------
# Parser — GROUP BY and HAVING clauses
# ---------------------------------------------------------------------------


def test_parser_no_group_by_yields_empty_list():
    """When GROUP BY is absent, group_by is an empty list."""
    ast = parse("SELECT name FROM employees")
    assert ast["group_by"] == []
    assert ast["having"] is None


def test_parser_group_by_single_column():
    ast = parse("SELECT department, COUNT(*) AS cnt FROM employees GROUP BY department")
    assert ast["group_by"] == ["department"]
    assert ast["having"] is None


def test_parser_group_by_multi_column():
    ast = parse("SELECT dept, team, COUNT(*) AS cnt FROM employees GROUP BY dept, team")
    assert ast["group_by"] == ["dept", "team"]


def test_parser_having_clause():
    ast = parse(
        "SELECT department, COUNT(*) AS cnt FROM employees GROUP BY department HAVING cnt > 1"
    )
    assert ast["having"] is not None
    h = ast["having"]
    assert h["type"] == "binop"
    assert h["op"] == ">"
    assert h["left"] == {"type": "col", "name": "cnt"}
    assert h["right"] == {"type": "lit", "value": 1}


def test_parser_group_by_before_order_by():
    """GROUP BY is parsed before ORDER BY; both appear in the AST."""
    ast = parse(
        "SELECT department, COUNT(*) AS cnt FROM employees "
        "GROUP BY department ORDER BY department ASC"
    )
    assert ast["group_by"] == ["department"]
    assert ast["order_by"] == [{"column": "department", "direction": "asc"}]


def test_parser_where_group_by_having_order_by():
    """All optional clauses together parse correctly."""
    ast = parse(
        "SELECT department, COUNT(*) AS cnt FROM employees "
        "WHERE salary > 50000 GROUP BY department HAVING cnt > 1 ORDER BY department ASC"
    )
    assert ast["where"] is not None
    assert ast["group_by"] == ["department"]
    assert ast["having"] is not None
    assert ast["order_by"] == [{"column": "department", "direction": "asc"}]


def test_parser_aggregate_with_explicit_alias():
    """COUNT(*) AS cnt produces a func dict with an alias key."""
    ast = parse("SELECT COUNT(*) AS cnt FROM employees")
    col = ast["columns"][0]
    assert col["type"] == "func"
    assert col["name"] == "count"
    assert col["alias"] == "cnt"


def test_parser_aggregate_without_alias_has_no_alias_key():
    """COUNT(*) without AS produces a func dict without alias key (backward-compatible)."""
    ast = parse("SELECT COUNT(*) FROM employees")
    col = ast["columns"][0]
    assert col == {"type": "func", "name": "count", "args": [{"type": "col", "name": "*"}]}
    assert "alias" not in col


def test_parser_mixed_plain_and_aggregate_allowed_with_group_by():
    """Parser accepts mixed plain+aggregate SELECT list (validation is at plan time)."""
    ast = parse(
        "SELECT department, COUNT(*) AS cnt FROM employees GROUP BY department"
    )
    cols = ast["columns"]
    assert cols[0] == "department"
    assert cols[1]["type"] == "func"
    assert cols[1]["alias"] == "cnt"


# ---------------------------------------------------------------------------
# Planner — GROUP BY and HAVING on Aggregate node
# ---------------------------------------------------------------------------


def test_planner_group_by_emits_group_by_field():
    p = plan("SELECT department, COUNT(*) AS cnt FROM employees GROUP BY department")
    assert p["type"] == "Aggregate"
    assert p["group_by"] == ["department"]


def test_planner_having_emits_having_field():
    p = plan(
        "SELECT department, COUNT(*) AS cnt FROM employees "
        "GROUP BY department HAVING cnt > 1"
    )
    assert p["type"] == "Aggregate"
    assert p["having"] is not None
    assert p["having"]["op"] == ">"


def test_planner_no_group_by_omits_group_by_field():
    """Whole-table aggregate must not include group_by key to stay backward-compatible."""
    p = plan("SELECT COUNT(*) FROM employees")
    assert p["type"] == "Aggregate"
    assert "group_by" not in p


def test_planner_no_having_omits_having_field():
    """GROUP BY without HAVING must not include having key."""
    p = plan("SELECT department, COUNT(*) AS cnt FROM employees GROUP BY department")
    assert "having" not in p


def test_planner_group_by_with_order_by_wraps_in_sort():
    """ORDER BY on a GROUP BY query produces Sort(Aggregate(...))."""
    p = plan(
        "SELECT department, COUNT(*) AS cnt FROM employees "
        "GROUP BY department ORDER BY department ASC"
    )
    assert p["type"] == "Sort"
    assert p["source"]["type"] == "Aggregate"
    assert p["source"]["group_by"] == ["department"]


def test_planner_explicit_alias_used_in_aggregate_descriptor():
    """COUNT(*) AS cnt → alias field in aggregates list is 'cnt', not auto-generated."""
    p = plan("SELECT department, COUNT(*) AS cnt FROM employees GROUP BY department")
    aggs = p["aggregates"]
    assert len(aggs) == 1
    assert aggs[0] == {"function": "count", "column": "*", "alias": "cnt"}


def test_planner_auto_alias_without_as():
    """COUNT(*) without AS → alias auto-generated as 'COUNT(*)'."""
    p = plan("SELECT COUNT(*) FROM employees")
    assert p["aggregates"][0]["alias"] == "COUNT(*)"


def test_planner_mixed_without_group_by_raises():
    """Mixing aggregates and plain columns without GROUP BY raises at plan time."""
    with pytest.raises(ValueError, match="mix"):
        plan("SELECT department, COUNT(*) FROM employees")


def test_planner_group_by_source_is_filter_when_where_present():
    """WHERE + GROUP BY: Aggregate wraps Filter."""
    p = plan(
        "SELECT department, COUNT(*) AS cnt FROM employees "
        "WHERE salary > 60000 GROUP BY department"
    )
    assert p["type"] == "Aggregate"
    assert p["source"]["type"] == "Filter"
    assert p["source"]["source"]["type"] == "Scan"


# ---------------------------------------------------------------------------
# Executor — GROUP BY grouping and HAVING filter
# ---------------------------------------------------------------------------


def test_execute_group_by_count_produces_multiple_rows():
    """GROUP BY returns one row per distinct department."""
    p = plan("SELECT department, COUNT(*) AS cnt FROM employees GROUP BY department")
    rows = execute(p)
    assert len(rows) == 3
    depts = {r["department"] for r in rows}
    assert depts == {"Engineering", "HR", "Marketing"}


def test_execute_group_by_count_correct_values():
    """COUNT(*) per group matches the actual employee distribution."""
    p = plan(
        "SELECT department, COUNT(*) AS cnt FROM employees "
        "GROUP BY department ORDER BY department ASC"
    )
    rows = execute(p)
    assert rows == [
        {"department": "Engineering", "cnt": 2},
        {"department": "HR", "cnt": 1},
        {"department": "Marketing", "cnt": 2},
    ]


def test_execute_having_filters_groups():
    """HAVING cnt > 1 removes HR (cnt=1) and keeps Engineering and Marketing."""
    p = plan(
        "SELECT department, COUNT(*) AS cnt FROM employees "
        "GROUP BY department HAVING cnt > 1 ORDER BY department ASC"
    )
    rows = execute(p)
    assert rows == [
        {"department": "Engineering", "cnt": 2},
        {"department": "Marketing", "cnt": 2},
    ]


def test_execute_having_all_filtered_returns_empty():
    """HAVING that excludes every group returns an empty result."""
    p = plan(
        "SELECT department, COUNT(*) AS cnt FROM employees "
        "GROUP BY department HAVING cnt > 100"
    )
    rows = execute(p)
    assert rows == []


def test_execute_group_by_backwards_compat_whole_table():
    """Whole-table aggregate (no group_by) still returns exactly one row."""
    p = plan("SELECT COUNT(*) FROM employees")
    rows = execute(p)
    assert len(rows) == 1
    assert rows[0]["COUNT(*)"] == 5


def test_execute_group_by_empty_source(tmp_path, monkeypatch):
    """GROUP BY on an empty table returns an empty result."""
    (tmp_path / "empty.csv").write_text("id,department\n")
    import engine.storage as storage_mod

    monkeypatch.setattr(storage_mod, "_DATA_DIR", tmp_path)

    p = {
        "type": "Aggregate",
        "source": {"type": "Scan", "table": "empty", "columns": "*"},
        "aggregates": [{"function": "count", "column": "*", "alias": "cnt"}],
        "group_by": ["department"],
    }
    rows = execute(p)
    assert rows == []


def test_execute_group_by_sum():
    """SUM aggregate per group produces correct per-group totals."""
    p = plan("SELECT department, SUM(salary) AS total FROM employees GROUP BY department")
    rows = execute(p)
    by_dept = {r["department"]: r["total"] for r in rows}
    assert by_dept["Engineering"] == 95000 + 110000
    assert by_dept["Marketing"] == 72000 + 78000
    assert by_dept["HR"] == 65000


def test_execute_group_by_having_equal():
    """HAVING cnt = 1 keeps only the single-employee department (HR)."""
    p = plan(
        "SELECT department, COUNT(*) AS cnt FROM employees "
        "GROUP BY department HAVING cnt = 1"
    )
    rows = execute(p)
    assert len(rows) == 1
    assert rows[0]["department"] == "HR"
    assert rows[0]["cnt"] == 1


# ---------------------------------------------------------------------------
# End-to-end convergence: queries 11 and 12
# ---------------------------------------------------------------------------


def test_convergence_query_11_group_by():
    """Query 11 result matches expected.csv exactly (ORDER BY makes it deterministic)."""
    from pathlib import Path
    import csv
    from engine.storage import _coerce

    query_dir = Path(__file__).parent.parent / "queries" / "11-group-by"
    sql = (query_dir / "query.sql").read_text().strip()

    with open(query_dir / "expected.csv", newline="") as f:
        expected = [{k: _coerce(v) for k, v in row.items()} for row in csv.DictReader(f)]

    result = execute(plan(sql))
    assert result == expected


def test_convergence_query_12_group_by_having():
    """Query 12 result matches expected.csv exactly (ORDER BY makes it deterministic)."""
    from pathlib import Path
    import csv
    from engine.storage import _coerce

    query_dir = Path(__file__).parent.parent / "queries" / "12-group-by-having"
    sql = (query_dir / "query.sql").read_text().strip()

    with open(query_dir / "expected.csv", newline="") as f:
        expected = [{k: _coerce(v) for k, v in row.items()} for row in csv.DictReader(f)]

    result = execute(plan(sql))
    assert result == expected
