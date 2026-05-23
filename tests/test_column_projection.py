"""Tests for column projection: lexer comma support, parser column lists,
planner Project wrapping, and executor Project execution."""
import pytest

from engine.executor import execute
from frontend.lexer import Token, TK_COMMA, TK_IDENT, TK_SELECT, TK_FROM, TK_SEMI, TK_EOF, tokenize
from frontend.parser import parse
from frontend.planner import plan


# ---------------------------------------------------------------------------
# Lexer — comma token
# ---------------------------------------------------------------------------


def test_lexer_comma_token():
    tokens = tokenize("SELECT id, name FROM t;")
    types = [t.type for t in tokens]
    assert TK_COMMA in types


def test_lexer_column_list_tokens():
    tokens = tokenize("SELECT id, name FROM employees;")
    assert tokens == [
        Token(TK_SELECT, "SELECT"),
        Token(TK_IDENT, "id"),
        Token(TK_COMMA, ","),
        Token(TK_IDENT, "name"),
        Token(TK_FROM, "FROM"),
        Token(TK_IDENT, "employees"),
        Token(TK_SEMI, ";"),
        Token(TK_EOF, ""),
    ]


def test_lexer_three_column_list():
    tokens = tokenize("SELECT a, b, c FROM t")
    types = [t.type for t in tokens]
    assert types == [TK_SELECT, TK_IDENT, TK_COMMA, TK_IDENT, TK_COMMA, TK_IDENT, TK_FROM, TK_IDENT, TK_EOF]


# ---------------------------------------------------------------------------
# Parser — column list
# ---------------------------------------------------------------------------


def test_parser_single_column():
    ast = parse("SELECT id FROM employees")
    assert ast == {"type": "select", "distinct": False, "columns": ["id"], "from": "employees", "from_alias": None, "join": None, "where": None, "group_by": [], "having": None, "order_by": [], "limit": None}


def test_parser_two_columns():
    ast = parse("SELECT id, name FROM employees")
    assert ast == {"type": "select", "distinct": False, "columns": ["id", "name"], "from": "employees", "from_alias": None, "join": None, "where": None, "group_by": [], "having": None, "order_by": [], "limit": None}


def test_parser_three_columns():
    ast = parse("SELECT id, name, department FROM employees;")
    assert ast == {"type": "select", "distinct": False, "columns": ["id", "name", "department"], "from": "employees", "from_alias": None, "join": None, "where": None, "group_by": [], "having": None, "order_by": [], "limit": None}


def test_parser_column_list_preserves_order():
    ast = parse("SELECT salary, name, id FROM employees")
    assert ast["columns"] == ["salary", "name", "id"]


def test_parser_star_still_works():
    ast = parse("SELECT * FROM employees")
    assert ast["columns"] == ["*"]


def test_parser_trailing_comma_raises():
    """A trailing comma after the last column is a syntax error (no identifier follows)."""
    with pytest.raises(ValueError):
        parse("SELECT id, FROM employees")


def test_parser_double_comma_raises():
    with pytest.raises(ValueError):
        parse("SELECT id,, name FROM employees")


# ---------------------------------------------------------------------------
# Planner — Project wrapping
# ---------------------------------------------------------------------------


def test_planner_single_column_emits_project():
    p = plan("SELECT id FROM employees")
    assert p["type"] == "Project"
    assert p["columns"] == ["id"]
    assert p["source"] == {"type": "Scan", "table": "employees", "columns": "*"}


def test_planner_two_columns_emits_project():
    p = plan("SELECT id, name FROM employees")
    assert p["type"] == "Project"
    assert p["columns"] == ["id", "name"]


def test_planner_star_emits_bare_scan():
    """SELECT * must NOT wrap in Project — keep the plan minimal."""
    p = plan("SELECT * FROM employees")
    assert p["type"] == "Scan"
    assert "source" not in p


def test_planner_project_source_is_scan():
    p = plan("SELECT id, name FROM employees")
    assert p["source"]["type"] == "Scan"
    assert p["source"]["table"] == "employees"


def test_planner_column_order_preserved():
    p = plan("SELECT salary, name FROM employees")
    assert p["columns"] == ["salary", "name"]


# ---------------------------------------------------------------------------
# Executor — Project node
# ---------------------------------------------------------------------------


def test_execute_project_two_columns():
    p = {
        "type": "Project",
        "source": {"type": "Scan", "table": "employees", "columns": "*"},
        "columns": ["id", "name"],
    }
    rows = execute(p)
    assert rows[0] == {"id": 1, "name": "Alice"}
    assert rows[4] == {"id": 5, "name": "Eve"}


def test_execute_project_column_count():
    p = {
        "type": "Project",
        "source": {"type": "Scan", "table": "employees", "columns": "*"},
        "columns": ["id", "name"],
    }
    rows = execute(p)
    assert all(len(r) == 2 for r in rows)


def test_execute_project_drops_unlisted_columns():
    p = {
        "type": "Project",
        "source": {"type": "Scan", "table": "employees", "columns": "*"},
        "columns": ["id"],
    }
    rows = execute(p)
    assert all(set(r.keys()) == {"id"} for r in rows)


def test_execute_project_declaration_order():
    """Executor must emit columns in declaration order, not CSV order."""
    p = {
        "type": "Project",
        "source": {"type": "Scan", "table": "employees", "columns": "*"},
        "columns": ["name", "id"],
    }
    rows = execute(p)
    assert list(rows[0].keys()) == ["name", "id"]


def test_execute_project_all_rows_present():
    p = {
        "type": "Project",
        "source": {"type": "Scan", "table": "employees", "columns": "*"},
        "columns": ["id", "name"],
    }
    rows = execute(p)
    assert len(rows) == 5


def test_execute_project_empty_source(tmp_path, monkeypatch):
    """Project over an empty table returns an empty list."""
    csv_file = tmp_path / "empty.csv"
    csv_file.write_text("id,name\n")

    import engine.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_DATA_DIR", tmp_path)

    p = {
        "type": "Project",
        "source": {"type": "Scan", "table": "empty", "columns": "*"},
        "columns": ["id", "name"],
    }
    assert execute(p) == []


def test_execute_project_missing_column_raises():
    """Projecting a column that does not exist in the source must raise KeyError."""
    p = {
        "type": "Project",
        "source": {"type": "Scan", "table": "employees", "columns": "*"},
        "columns": ["nonexistent"],
    }
    with pytest.raises(KeyError):
        execute(p)


# ---------------------------------------------------------------------------
# End-to-end: plan → execute
# ---------------------------------------------------------------------------


def test_end_to_end_id_name_projection():
    rows = execute(plan("SELECT id, name FROM employees"))
    assert rows == [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"},
        {"id": 3, "name": "Carol"},
        {"id": 4, "name": "Dave"},
        {"id": 5, "name": "Eve"},
    ]


def test_end_to_end_single_column():
    rows = execute(plan("SELECT department FROM employees"))
    assert rows == [
        {"department": "Engineering"},
        {"department": "Marketing"},
        {"department": "Engineering"},
        {"department": "HR"},
        {"department": "Marketing"},
    ]


def test_end_to_end_reverse_column_order():
    """Column order in result matches declaration, not CSV order."""
    rows = execute(plan("SELECT name, id FROM employees"))
    assert list(rows[0].keys()) == ["name", "id"]
    assert rows[0] == {"name": "Alice", "id": 1}


def test_end_to_end_case_insensitive_keywords():
    rows_upper = execute(plan("SELECT id, name FROM employees"))
    rows_lower = execute(plan("select id, name from employees"))
    assert rows_upper == rows_lower
