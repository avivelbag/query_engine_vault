"""Tests for ORDER BY (Sort node) and LIMIT (Limit node) support."""

from engine.executor import execute
from frontend.lexer import (
    tokenize,
    TK_ORDER,
    TK_BY,
    TK_ASC,
    TK_DESC,
    TK_LIMIT,
)
from frontend.parser import parse
from frontend.planner import plan


# ---------------------------------------------------------------------------
# Lexer: new keywords
# ---------------------------------------------------------------------------


def test_lexer_order_by_keywords():
    tokens = tokenize("SELECT * FROM t ORDER BY col ASC;")
    types = [tok.type for tok in tokens]
    assert TK_ORDER in types
    assert TK_BY in types
    assert TK_ASC in types


def test_lexer_desc_keyword():
    tokens = tokenize("SELECT * FROM t ORDER BY col DESC;")
    types = [tok.type for tok in tokens]
    assert TK_DESC in types


def test_lexer_limit_keyword():
    tokens = tokenize("SELECT * FROM t LIMIT 5;")
    types = [tok.type for tok in tokens]
    assert TK_LIMIT in types


def test_lexer_order_by_case_insensitive():
    tokens_upper = tokenize("SELECT * FROM t ORDER BY col ASC")
    tokens_lower = tokenize("select * from t order by col asc")
    assert [tok.type for tok in tokens_upper] == [tok.type for tok in tokens_lower]


# ---------------------------------------------------------------------------
# Parser: ORDER BY and LIMIT AST
# ---------------------------------------------------------------------------


def test_parser_order_by_single_asc():
    ast = parse("SELECT * FROM employees ORDER BY name ASC")
    assert ast["order_by"] == [{"column": "name", "direction": "asc"}]
    assert ast["limit"] is None


def test_parser_order_by_single_desc():
    ast = parse("SELECT * FROM employees ORDER BY age DESC")
    assert ast["order_by"] == [{"column": "age", "direction": "desc"}]


def test_parser_order_by_direction_default_asc():
    """Omitting ASC/DESC defaults to asc."""
    ast = parse("SELECT * FROM employees ORDER BY name")
    assert ast["order_by"] == [{"column": "name", "direction": "asc"}]


def test_parser_order_by_multi_column():
    ast = parse("SELECT * FROM employees ORDER BY department ASC, name ASC")
    assert ast["order_by"] == [
        {"column": "department", "direction": "asc"},
        {"column": "name", "direction": "asc"},
    ]


def test_parser_limit_only():
    ast = parse("SELECT * FROM employees LIMIT 3")
    assert ast["limit"] == 3
    assert ast["order_by"] == []


def test_parser_order_by_and_limit():
    ast = parse("SELECT * FROM employees ORDER BY age DESC LIMIT 3")
    assert ast["order_by"] == [{"column": "age", "direction": "desc"}]
    assert ast["limit"] == 3


def test_parser_no_order_by_no_limit():
    ast = parse("SELECT * FROM employees")
    assert ast["order_by"] == []
    assert ast["limit"] is None


def test_parser_order_by_with_where():
    ast = parse("SELECT * FROM employees WHERE age > 30 ORDER BY name ASC")
    assert ast["where"] is not None
    assert ast["order_by"] == [{"column": "name", "direction": "asc"}]


# ---------------------------------------------------------------------------
# Planner: Sort and Limit plan nodes
# ---------------------------------------------------------------------------


def test_planner_order_by_wraps_in_sort():
    p = plan("SELECT * FROM employees ORDER BY name ASC")
    assert p["type"] == "Sort"
    assert p["keys"] == [{"column": "name", "direction": "asc"}]
    assert p["source"]["type"] == "Scan"


def test_planner_limit_wraps_in_limit():
    p = plan("SELECT * FROM employees LIMIT 5")
    assert p["type"] == "Limit"
    assert p["count"] == 5


def test_planner_order_by_then_limit_nesting():
    """Sort must sit below Limit so slicing happens after ordering."""
    p = plan("SELECT * FROM employees ORDER BY age DESC LIMIT 3")
    assert p["type"] == "Limit"
    assert p["source"]["type"] == "Sort"
    assert p["source"]["source"]["type"] == "Scan"


def test_planner_project_below_sort():
    """Column projection sits below Sort in the plan tree."""
    p = plan("SELECT name, age FROM employees ORDER BY age DESC")
    assert p["type"] == "Sort"
    assert p["source"]["type"] == "Project"


def test_planner_full_pipeline():
    """WHERE → Project → Sort → Limit stack is correctly nested."""
    p = plan("SELECT name FROM employees WHERE age > 30 ORDER BY name ASC LIMIT 2")
    assert p["type"] == "Limit"
    assert p["count"] == 2
    sort = p["source"]
    assert sort["type"] == "Sort"
    proj = sort["source"]
    assert proj["type"] == "Project"
    filt = proj["source"]
    assert filt["type"] == "Filter"
    assert filt["source"]["type"] == "Scan"


# ---------------------------------------------------------------------------
# Executor: Sort node
# ---------------------------------------------------------------------------


def _employees_fixture():
    """Return five employee dicts matching data/employees.csv."""
    return [
        {"id": 1, "name": "Alice", "department": "Engineering", "salary": 95000, "age": 28},
        {"id": 2, "name": "Bob", "department": "Marketing", "salary": 72000, "age": 35},
        {"id": 3, "name": "Carol", "department": "Engineering", "salary": 110000, "age": 42},
        {"id": 4, "name": "Dave", "department": "HR", "salary": 65000, "age": 29},
        {"id": 5, "name": "Eve", "department": "Marketing", "salary": 78000, "age": 38},
    ]


def _make_scan():
    return {"type": "Scan", "table": "employees", "columns": "*"}


def test_execute_sort_single_key_asc():
    sort_plan = {
        "type": "Sort",
        "source": _make_scan(),
        "keys": [{"column": "name", "direction": "asc"}],
    }
    rows = execute(sort_plan)
    names = [r["name"] for r in rows]
    assert names == sorted(names)


def test_execute_sort_single_key_desc():
    sort_plan = {
        "type": "Sort",
        "source": _make_scan(),
        "keys": [{"column": "age", "direction": "desc"}],
    }
    rows = execute(sort_plan)
    ages = [r["age"] for r in rows]
    assert ages == sorted(ages, reverse=True)


def test_execute_sort_multi_column():
    """department ASC, name ASC must yield the canonical ordering."""
    sort_plan = {
        "type": "Sort",
        "source": _make_scan(),
        "keys": [
            {"column": "department", "direction": "asc"},
            {"column": "name", "direction": "asc"},
        ],
    }
    rows = execute(sort_plan)
    names = [r["name"] for r in rows]
    assert names == ["Alice", "Carol", "Dave", "Bob", "Eve"]


def test_execute_sort_empty_source(tmp_path, monkeypatch):
    """Sort over an empty table returns [] without error."""
    csv_file = tmp_path / "empty.csv"
    csv_file.write_text("name,age\n")

    import engine.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_DATA_DIR", tmp_path)

    sort_plan = {
        "type": "Sort",
        "source": {"type": "Scan", "table": "empty", "columns": "*"},
        "keys": [{"column": "age", "direction": "asc"}],
    }
    assert execute(sort_plan) == []


def test_execute_sort_preserves_all_columns():
    sort_plan = {
        "type": "Sort",
        "source": _make_scan(),
        "keys": [{"column": "name", "direction": "asc"}],
    }
    rows = execute(sort_plan)
    assert all("salary" in r and "department" in r for r in rows)


# ---------------------------------------------------------------------------
# Executor: Limit node
# ---------------------------------------------------------------------------


def test_execute_limit_first_three():
    limit_plan = {
        "type": "Limit",
        "source": {
            "type": "Sort",
            "source": _make_scan(),
            "keys": [{"column": "age", "direction": "desc"}],
        },
        "count": 3,
    }
    rows = execute(limit_plan)
    assert len(rows) == 3
    assert rows[0]["name"] == "Carol"
    assert rows[1]["name"] == "Eve"
    assert rows[2]["name"] == "Bob"


def test_execute_limit_larger_than_source():
    """Limit count > row count returns all rows without error."""
    limit_plan = {"type": "Limit", "source": _make_scan(), "count": 100}
    rows = execute(limit_plan)
    assert len(rows) == 5


def test_execute_limit_zero():
    """LIMIT 0 returns an empty list."""
    limit_plan = {"type": "Limit", "source": _make_scan(), "count": 0}
    assert execute(limit_plan) == []


def test_execute_limit_empty_source(tmp_path, monkeypatch):
    """Limit over an empty table returns [] without error."""
    csv_file = tmp_path / "empty.csv"
    csv_file.write_text("name,age\n")

    import engine.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_DATA_DIR", tmp_path)

    limit_plan = {
        "type": "Limit",
        "source": {"type": "Scan", "table": "empty", "columns": "*"},
        "count": 5,
    }
    assert execute(limit_plan) == []


# ---------------------------------------------------------------------------
# End-to-end: plan() → execute() for new query files
# ---------------------------------------------------------------------------


def test_e2e_order_by_multi_column():
    """Query 05: SELECT name, department ORDER BY department ASC, name ASC."""
    result = execute(plan("SELECT name, department FROM employees ORDER BY department ASC, name ASC"))
    expected = [
        {"name": "Alice", "department": "Engineering"},
        {"name": "Carol", "department": "Engineering"},
        {"name": "Dave", "department": "HR"},
        {"name": "Bob", "department": "Marketing"},
        {"name": "Eve", "department": "Marketing"},
    ]
    assert result == expected


def test_e2e_order_by_limit():
    """Query 06: SELECT name, age ORDER BY age DESC LIMIT 3."""
    result = execute(plan("SELECT name, age FROM employees ORDER BY age DESC LIMIT 3"))
    expected = [
        {"name": "Carol", "age": 42},
        {"name": "Eve", "age": 38},
        {"name": "Bob", "age": 35},
    ]
    assert result == expected


def test_e2e_order_by_with_where():
    """Combining WHERE and ORDER BY returns filtered rows in declared order."""
    result = execute(plan("SELECT name, age FROM employees WHERE age > 30 ORDER BY age ASC"))
    names = [r["name"] for r in result]
    assert names == ["Bob", "Eve", "Carol"]


def test_e2e_order_by_desc_single_key():
    result = execute(plan("SELECT name, salary FROM employees ORDER BY salary DESC"))
    salaries = [r["salary"] for r in result]
    assert salaries == sorted(salaries, reverse=True)


def test_e2e_limit_one():
    result = execute(plan("SELECT name FROM employees ORDER BY name ASC LIMIT 1"))
    assert result == [{"name": "Alice"}]
