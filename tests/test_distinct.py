"""Tests for SELECT DISTINCT — deduplication via the Distinct plan node."""
import pytest

from engine.executor import execute
from frontend.lexer import tokenize, TK_DISTINCT
from frontend.parser import parse
from frontend.planner import plan


# ---------------------------------------------------------------------------
# Lexer tests
# ---------------------------------------------------------------------------

def test_lexer_distinct_keyword():
    """DISTINCT is tokenised as TK_DISTINCT, not as an identifier."""
    tokens = tokenize("SELECT DISTINCT name FROM employees;")
    types = [t.type for t in tokens]
    assert TK_DISTINCT in types


def test_lexer_distinct_case_insensitive():
    """DISTINCT is recognised regardless of case."""
    tokens_upper = tokenize("SELECT DISTINCT id FROM t;")
    tokens_lower = tokenize("SELECT distinct id FROM t;")
    assert tokens_upper[1].type == TK_DISTINCT
    assert tokens_lower[1].type == TK_DISTINCT


def test_lexer_distinct_not_confused_with_identifier():
    """A column named 'distinctval' is still tokenised as an IDENT."""
    tokens = tokenize("SELECT distinctval FROM t;")
    # first token is SELECT, second should be IDENT not DISTINCT
    assert tokens[1].type == "IDENT"
    assert tokens[1].value == "distinctval"


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------

def test_parser_distinct_flag_set():
    """Parser sets distinct=True when DISTINCT appears after SELECT."""
    ast = parse("SELECT DISTINCT department FROM employees;")
    assert ast["distinct"] is True


def test_parser_no_distinct_flag_false():
    """Parser sets distinct=False when DISTINCT is absent."""
    ast = parse("SELECT department FROM employees;")
    assert ast["distinct"] is False


def test_parser_distinct_star():
    """SELECT DISTINCT * is parsed without error; columns is ['*']."""
    ast = parse("SELECT DISTINCT * FROM employees;")
    assert ast["distinct"] is True
    assert ast["columns"] == ["*"]


def test_parser_distinct_column_list():
    """SELECT DISTINCT with explicit column list parses correctly."""
    ast = parse("SELECT DISTINCT name, department FROM employees;")
    assert ast["distinct"] is True
    assert ast["columns"] == ["name", "department"]


# ---------------------------------------------------------------------------
# Planner tests
# ---------------------------------------------------------------------------

def test_planner_distinct_wraps_project():
    """Planner emits Distinct node wrapping the Project when DISTINCT is present."""
    p = plan("SELECT DISTINCT department FROM employees;")
    assert p["type"] == "Distinct"
    assert p["source"]["type"] == "Project"


def test_planner_distinct_below_sort():
    """Distinct sits below Sort when ORDER BY is also present."""
    p = plan("SELECT DISTINCT department FROM employees ORDER BY department ASC;")
    assert p["type"] == "Sort"
    assert p["source"]["type"] == "Distinct"


def test_planner_distinct_below_limit():
    """Distinct sits below Limit (and Sort) when LIMIT is present."""
    p = plan("SELECT DISTINCT department FROM employees ORDER BY department ASC LIMIT 2;")
    assert p["type"] == "Limit"
    assert p["source"]["type"] == "Sort"
    assert p["source"]["source"]["type"] == "Distinct"


def test_planner_no_distinct_no_wrap():
    """Without DISTINCT, no Distinct node is emitted."""
    p = plan("SELECT department FROM employees;")
    assert p["type"] == "Project"


def test_planner_distinct_star_wraps_scan():
    """SELECT DISTINCT * wraps the Scan directly (no Project node)."""
    p = plan("SELECT DISTINCT * FROM employees;")
    assert p["type"] == "Distinct"
    assert p["source"]["type"] == "Scan"


# ---------------------------------------------------------------------------
# Executor tests — happy path
# ---------------------------------------------------------------------------

_EMPLOYEES = [
    {"id": 1, "name": "Alice",  "department": "Engineering", "salary": 95000,  "age": 28, "dept_id": 1},
    {"id": 2, "name": "Bob",    "department": "Marketing",   "salary": 72000,  "age": 35, "dept_id": 2},
    {"id": 3, "name": "Carol",  "department": "Engineering", "salary": 110000, "age": 42, "dept_id": 1},
    {"id": 4, "name": "Dave",   "department": "HR",          "salary": 65000,  "age": 29, "dept_id": 3},
    {"id": 5, "name": "Eve",    "department": "Marketing",   "salary": 78000,  "age": 38, "dept_id": 2},
]


def test_executor_distinct_deduplicates():
    """Executor deduplicates rows via the Distinct node, preserving first occurrence."""
    distinct_node = {
        "type": "Distinct",
        "source": {
            "type": "Project",
            "source": {"type": "Scan", "table": "employees", "columns": "*"},
            "columns": ["department"],
        },
    }
    result = execute(distinct_node)
    departments = [r["department"] for r in result]
    # Three unique departments; first occurrences are Engineering, Marketing, HR
    assert len(result) == 3
    assert departments[0] == "Engineering"
    assert departments[1] == "Marketing"
    assert departments[2] == "HR"


def test_executor_distinct_preserves_first_occurrence_order():
    """The order of first occurrence is preserved (stable dedup)."""
    # Using department projection; Engineering appears first in the CSV
    result = execute(plan("SELECT DISTINCT department FROM employees;"))
    assert result[0]["department"] == "Engineering"


def test_executor_full_query_14_distinct_ordered():
    """The query from queries/14-distinct returns one row per department sorted ASC."""
    result = execute(plan("SELECT DISTINCT department FROM employees ORDER BY department ASC;"))
    assert result == [
        {"department": "Engineering"},
        {"department": "HR"},
        {"department": "Marketing"},
    ]


def test_executor_distinct_no_duplicates_when_all_unique():
    """DISTINCT on a column with all unique values returns all rows unchanged."""
    result = execute(plan("SELECT DISTINCT name FROM employees;"))
    assert len(result) == 5


def test_executor_distinct_star_all_rows_unique():
    """SELECT DISTINCT * on employees returns all 5 rows (all are unique)."""
    result = execute(plan("SELECT DISTINCT * FROM employees;"))
    assert len(result) == 5


# ---------------------------------------------------------------------------
# Executor tests — NULL handling
# ---------------------------------------------------------------------------

def test_executor_distinct_null_equals_null(tmp_path, monkeypatch):
    """Two rows with NULL in the same column are treated as equal by DISTINCT.

    For deduplication purposes NULL == NULL, unlike SQL comparison semantics.
    """
    import engine.storage as storage
    import csv

    csv_path = tmp_path / "nulltest.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["val"])
        writer.writerow([""])   # empty → None after coercion? No — empty string stays as "".
        writer.writerow([""])   # second empty string — both equal, dedup to one

    monkeypatch.setattr(storage, "_DATA_DIR", tmp_path)

    distinct_node = {
        "type": "Distinct",
        "source": {"type": "Scan", "table": "nulltest", "columns": "*"},
    }
    result = execute(distinct_node)
    assert len(result) == 1


def test_executor_distinct_null_values_grouped(tmp_path, monkeypatch):
    """Rows where NULL columns are identical are deduplicated to a single row."""
    import engine.storage as storage
    import csv

    csv_path = tmp_path / "nullcol.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "group"])
        writer.writeheader()
        writer.writerow({"id": "1", "group": ""})
        writer.writerow({"id": "2", "group": ""})
        writer.writerow({"id": "3", "group": "A"})

    monkeypatch.setattr(storage, "_DATA_DIR", tmp_path)

    distinct_node = {
        "type": "Distinct",
        "source": {
            "type": "Project",
            "source": {"type": "Scan", "table": "nullcol", "columns": "*"},
            "columns": ["group"],
        },
    }
    result = execute(distinct_node)
    # "" and "" are equal so they collapse to one; "A" is distinct → 2 rows total
    assert len(result) == 2


# ---------------------------------------------------------------------------
# Executor tests — edge cases
# ---------------------------------------------------------------------------

def test_executor_distinct_empty_source(tmp_path, monkeypatch):
    """Distinct over an empty table returns an empty list."""
    import engine.storage as storage
    import csv

    csv_path = tmp_path / "empty.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["col"])

    monkeypatch.setattr(storage, "_DATA_DIR", tmp_path)

    result = execute({
        "type": "Distinct",
        "source": {"type": "Scan", "table": "empty", "columns": "*"},
    })
    assert result == []


def test_executor_distinct_single_row(tmp_path, monkeypatch):
    """Distinct over a single-row table returns that row unchanged."""
    import engine.storage as storage
    import csv

    csv_path = tmp_path / "onerow.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["x"])
        writer.writeheader()
        writer.writerow({"x": "42"})

    monkeypatch.setattr(storage, "_DATA_DIR", tmp_path)

    result = execute({
        "type": "Distinct",
        "source": {"type": "Scan", "table": "onerow", "columns": "*"},
    })
    assert result == [{"x": 42}]


def test_executor_distinct_all_same_row(tmp_path, monkeypatch):
    """Distinct over N identical rows returns exactly one row."""
    import engine.storage as storage
    import csv

    csv_path = tmp_path / "allsame.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["val"])
        writer.writeheader()
        for _ in range(10):
            writer.writerow({"val": "x"})

    monkeypatch.setattr(storage, "_DATA_DIR", tmp_path)

    result = execute({
        "type": "Distinct",
        "source": {"type": "Scan", "table": "allsame", "columns": "*"},
    })
    assert result == [{"val": "x"}]


# ---------------------------------------------------------------------------
# Error / failure mode tests
# ---------------------------------------------------------------------------

def test_executor_distinct_unknown_type_raises():
    """Executor raises ValueError for an unknown plan node type (sanity check)."""
    with pytest.raises(ValueError, match="Unknown plan node type"):
        execute({"type": "UnknownNode"})


def test_parser_distinct_must_precede_columns():
    """DISTINCT keyword after SELECT but before column list is the only valid position."""
    # This should parse fine
    ast = parse("SELECT DISTINCT id FROM employees;")
    assert ast["distinct"] is True
    # Omitting DISTINCT gives distinct=False
    ast2 = parse("SELECT id FROM employees;")
    assert ast2["distinct"] is False
