"""Tests for LEFT JOIN and RIGHT JOIN: lexer, parser, planner, executor, and e2e."""

from engine.executor import execute, _table_name_of
from frontend.lexer import (
    Token,
    TK_LEFT,
    TK_RIGHT,
    TK_OUTER,
    TK_JOIN,
    TK_AS,
    TK_IDENT,
    tokenize,
)
from frontend.parser import parse
from frontend.planner import plan


# ---------------------------------------------------------------------------
# Lexer — new tokens
# ---------------------------------------------------------------------------


def test_lexer_left_keyword():
    tokens = tokenize("LEFT")
    assert tokens[0] == Token(TK_LEFT, "LEFT")


def test_lexer_right_keyword():
    tokens = tokenize("RIGHT")
    assert tokens[0] == Token(TK_RIGHT, "RIGHT")


def test_lexer_outer_keyword():
    tokens = tokenize("OUTER")
    assert tokens[0] == Token(TK_OUTER, "OUTER")


def test_lexer_left_join_tokens():
    tokens = tokenize("LEFT JOIN")
    assert tokens[0].type == TK_LEFT
    assert tokens[1].type == TK_JOIN


def test_lexer_left_outer_join_tokens():
    tokens = tokenize("LEFT OUTER JOIN")
    assert tokens[0].type == TK_LEFT
    assert tokens[1].type == TK_OUTER
    assert tokens[2].type == TK_JOIN


def test_lexer_right_join_case_insensitive():
    tokens = tokenize("right join")
    assert tokens[0].type == TK_RIGHT
    assert tokens[1].type == TK_JOIN


def test_lexer_as_keyword_present():
    """AS was already defined; verify it tokenises alongside table names."""
    tokens = tokenize("employees AS e")
    assert tokens[0].type == TK_IDENT
    assert tokens[1].type == TK_AS
    assert tokens[2] == Token(TK_IDENT, "e")


# ---------------------------------------------------------------------------
# Parser — table aliases
# ---------------------------------------------------------------------------


def test_parser_from_alias_captured():
    ast = parse("SELECT * FROM employees AS e LEFT JOIN departments AS d ON e.department = d.name")
    assert ast["from"] == "employees"
    assert ast["from_alias"] == "e"


def test_parser_no_alias_is_none():
    ast = parse("SELECT * FROM employees INNER JOIN departments ON employees.dept_id = departments.id")
    assert ast["from_alias"] is None
    assert ast["join"]["alias"] is None


def test_parser_join_alias_captured():
    ast = parse("SELECT * FROM employees AS e LEFT JOIN departments AS d ON e.department = d.name")
    assert ast["join"]["alias"] == "d"


# ---------------------------------------------------------------------------
# Parser — LEFT / RIGHT / OUTER JOIN
# ---------------------------------------------------------------------------


def test_parser_left_join_type():
    ast = parse(
        "SELECT * FROM employees AS e LEFT JOIN departments AS d ON e.department = d.name"
    )
    assert ast["join"]["join_type"] == "left"


def test_parser_left_outer_join_type():
    ast = parse(
        "SELECT * FROM employees AS e LEFT OUTER JOIN departments AS d ON e.department = d.name"
    )
    assert ast["join"]["join_type"] == "left"


def test_parser_right_join_type():
    ast = parse(
        "SELECT * FROM departments AS d RIGHT JOIN employees AS e ON e.department = d.name"
    )
    assert ast["join"]["join_type"] == "right"


def test_parser_right_outer_join_type():
    ast = parse(
        "SELECT * FROM departments AS d RIGHT OUTER JOIN employees AS e ON e.department = d.name"
    )
    assert ast["join"]["join_type"] == "right"


def test_parser_inner_join_type_preserved():
    ast = parse(
        "SELECT * FROM employees INNER JOIN departments ON employees.dept_id = departments.id"
    )
    assert ast["join"]["join_type"] == "inner"


# ---------------------------------------------------------------------------
# Planner — join_type and alias propagation
# ---------------------------------------------------------------------------


def test_planner_left_join_node_join_type():
    p = plan(
        "SELECT e.name FROM employees AS e LEFT JOIN departments AS d ON e.department = d.name"
    )
    join = p["source"]
    assert join["type"] == "Join"
    assert join["join_type"] == "left"


def test_planner_right_join_node_join_type():
    p = plan(
        "SELECT d.name FROM departments AS d RIGHT JOIN employees AS e ON e.department = d.name"
    )
    join = p["source"]
    assert join["join_type"] == "right"


def test_planner_scan_carries_alias():
    p = plan(
        "SELECT e.name FROM employees AS e LEFT JOIN departments AS d ON e.department = d.name"
    )
    join = p["source"]
    assert join["left"]["alias"] == "e"
    assert join["right"]["alias"] == "d"


def test_planner_scan_no_alias_when_not_declared():
    p = plan(
        "SELECT employees.name FROM employees INNER JOIN departments ON employees.dept_id = departments.id"
    )
    join = p["source"]
    assert "alias" not in join["left"]
    assert "alias" not in join["right"]


def test_planner_left_join_sort_wraps_project_wraps_join():
    p = plan(
        "SELECT e.name, d.location FROM employees AS e LEFT JOIN departments AS d ON e.department = d.name ORDER BY e.name ASC"
    )
    assert p["type"] == "Sort"
    assert p["source"]["type"] == "Project"
    assert p["source"]["source"]["type"] == "Join"


# ---------------------------------------------------------------------------
# _table_name_of with alias
# ---------------------------------------------------------------------------


def test_table_name_of_uses_alias_when_present():
    node = {"type": "Scan", "table": "employees", "alias": "e", "columns": "*"}
    assert _table_name_of(node) == "e"


def test_table_name_of_falls_back_to_table_when_no_alias():
    node = {"type": "Scan", "table": "employees", "columns": "*"}
    assert _table_name_of(node) == "employees"


# ---------------------------------------------------------------------------
# Executor — LEFT JOIN
# ---------------------------------------------------------------------------


def _make_left_join_plan(tmp_path, left_csv, right_csv, on_expr):
    """Create two CSV tables in tmp_path and return a LEFT JOIN plan."""
    import engine.storage as storage_mod
    (tmp_path / "left.csv").write_text(left_csv)
    (tmp_path / "right.csv").write_text(right_csv)
    storage_mod._DATA_DIR = tmp_path
    return {
        "type": "Join",
        "join_type": "left",
        "left": {"type": "Scan", "table": "left", "columns": "*"},
        "right": {"type": "Scan", "table": "right", "columns": "*"},
        "on": on_expr,
    }


def test_execute_left_join_all_left_rows_present(tmp_path, monkeypatch):
    """LEFT JOIN: every left row appears even if no right row matches."""
    import engine.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_DATA_DIR", tmp_path)
    (tmp_path / "left.csv").write_text("id,val\n1,a\n2,b\n")
    (tmp_path / "right.csv").write_text("fk,label\n1,x\n")
    p = {
        "type": "Join", "join_type": "left",
        "left": {"type": "Scan", "table": "left", "columns": "*"},
        "right": {"type": "Scan", "table": "right", "columns": "*"},
        "on": {
            "type": "binop", "op": "=",
            "left": {"type": "col", "name": "left.id"},
            "right": {"type": "col", "name": "right.fk"},
        },
    }
    rows = execute(p)
    assert len(rows) == 2
    matched = next(r for r in rows if r["left.id"] == 1)
    assert matched["right.label"] == "x"
    unmatched = next(r for r in rows if r["left.id"] == 2)
    assert unmatched["right.label"] is None
    assert unmatched["right.fk"] is None


def test_execute_left_join_unmatched_right_cols_are_none(tmp_path, monkeypatch):
    """Unmatched LEFT JOIN row sets ALL right columns to None."""
    import engine.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_DATA_DIR", tmp_path)
    (tmp_path / "left.csv").write_text("id\n1\n2\n")
    (tmp_path / "right.csv").write_text("fk,a,b\n1,x,y\n")
    p = {
        "type": "Join", "join_type": "left",
        "left": {"type": "Scan", "table": "left", "columns": "*"},
        "right": {"type": "Scan", "table": "right", "columns": "*"},
        "on": {
            "type": "binop", "op": "=",
            "left": {"type": "col", "name": "left.id"},
            "right": {"type": "col", "name": "right.fk"},
        },
    }
    rows = execute(p)
    unmatched = next(r for r in rows if r["left.id"] == 2)
    assert unmatched["right.fk"] is None
    assert unmatched["right.a"] is None
    assert unmatched["right.b"] is None


def test_execute_left_join_empty_right_table(tmp_path, monkeypatch):
    """LEFT JOIN with empty right table: all left rows appear with all right cols None."""
    import engine.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_DATA_DIR", tmp_path)
    (tmp_path / "left.csv").write_text("id\n1\n2\n")
    (tmp_path / "right.csv").write_text("fk\n")
    p = {
        "type": "Join", "join_type": "left",
        "left": {"type": "Scan", "table": "left", "columns": "*"},
        "right": {"type": "Scan", "table": "right", "columns": "*"},
        "on": {
            "type": "binop", "op": "=",
            "left": {"type": "col", "name": "left.id"},
            "right": {"type": "col", "name": "right.fk"},
        },
    }
    rows = execute(p)
    assert len(rows) == 2
    for r in rows:
        assert "left.id" in r


def test_execute_left_join_empty_left_table(tmp_path, monkeypatch):
    """LEFT JOIN with empty left table: no output rows at all."""
    import engine.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_DATA_DIR", tmp_path)
    (tmp_path / "left.csv").write_text("id\n")
    (tmp_path / "right.csv").write_text("fk\n1\n")
    p = {
        "type": "Join", "join_type": "left",
        "left": {"type": "Scan", "table": "left", "columns": "*"},
        "right": {"type": "Scan", "table": "right", "columns": "*"},
        "on": {
            "type": "binop", "op": "=",
            "left": {"type": "col", "name": "left.id"},
            "right": {"type": "col", "name": "right.fk"},
        },
    }
    assert execute(p) == []


def test_execute_left_join_multiple_matches(tmp_path, monkeypatch):
    """LEFT JOIN: a left row that matches multiple right rows produces multiple output rows."""
    import engine.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_DATA_DIR", tmp_path)
    (tmp_path / "left.csv").write_text("id\n1\n")
    (tmp_path / "right.csv").write_text("fk,val\n1,a\n1,b\n")
    p = {
        "type": "Join", "join_type": "left",
        "left": {"type": "Scan", "table": "left", "columns": "*"},
        "right": {"type": "Scan", "table": "right", "columns": "*"},
        "on": {
            "type": "binop", "op": "=",
            "left": {"type": "col", "name": "left.id"},
            "right": {"type": "col", "name": "right.fk"},
        },
    }
    rows = execute(p)
    assert len(rows) == 2
    vals = {r["right.val"] for r in rows}
    assert vals == {"a", "b"}


# ---------------------------------------------------------------------------
# Executor — RIGHT JOIN
# ---------------------------------------------------------------------------


def test_execute_right_join_all_right_rows_present(tmp_path, monkeypatch):
    """RIGHT JOIN: every right row appears even if no left row matches."""
    import engine.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_DATA_DIR", tmp_path)
    (tmp_path / "left.csv").write_text("id,val\n1,a\n")
    (tmp_path / "right.csv").write_text("fk,label\n1,x\n2,y\n")
    p = {
        "type": "Join", "join_type": "right",
        "left": {"type": "Scan", "table": "left", "columns": "*"},
        "right": {"type": "Scan", "table": "right", "columns": "*"},
        "on": {
            "type": "binop", "op": "=",
            "left": {"type": "col", "name": "left.id"},
            "right": {"type": "col", "name": "right.fk"},
        },
    }
    rows = execute(p)
    assert len(rows) == 2
    matched = next(r for r in rows if r["right.fk"] == 1)
    assert matched["left.val"] == "a"
    unmatched = next(r for r in rows if r["right.fk"] == 2)
    assert unmatched["left.id"] is None
    assert unmatched["left.val"] is None


def test_execute_right_join_unmatched_left_cols_are_none(tmp_path, monkeypatch):
    """Unmatched RIGHT JOIN row sets ALL left columns to None."""
    import engine.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_DATA_DIR", tmp_path)
    (tmp_path / "left.csv").write_text("id,a,b\n1,x,y\n")
    (tmp_path / "right.csv").write_text("fk\n1\n2\n")
    p = {
        "type": "Join", "join_type": "right",
        "left": {"type": "Scan", "table": "left", "columns": "*"},
        "right": {"type": "Scan", "table": "right", "columns": "*"},
        "on": {
            "type": "binop", "op": "=",
            "left": {"type": "col", "name": "left.id"},
            "right": {"type": "col", "name": "right.fk"},
        },
    }
    rows = execute(p)
    unmatched = next(r for r in rows if r["right.fk"] == 2)
    assert unmatched["left.id"] is None
    assert unmatched["left.a"] is None
    assert unmatched["left.b"] is None


def test_execute_right_join_empty_left_table(tmp_path, monkeypatch):
    """RIGHT JOIN with empty left table: all right rows appear with all left cols None."""
    import engine.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_DATA_DIR", tmp_path)
    (tmp_path / "left.csv").write_text("id\n")
    (tmp_path / "right.csv").write_text("fk\n1\n2\n")
    p = {
        "type": "Join", "join_type": "right",
        "left": {"type": "Scan", "table": "left", "columns": "*"},
        "right": {"type": "Scan", "table": "right", "columns": "*"},
        "on": {
            "type": "binop", "op": "=",
            "left": {"type": "col", "name": "left.id"},
            "right": {"type": "col", "name": "right.fk"},
        },
    }
    rows = execute(p)
    assert len(rows) == 2
    for r in rows:
        assert "right.fk" in r


def test_execute_right_join_empty_right_table(tmp_path, monkeypatch):
    """RIGHT JOIN with empty right table: no output rows."""
    import engine.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_DATA_DIR", tmp_path)
    (tmp_path / "left.csv").write_text("id\n1\n")
    (tmp_path / "right.csv").write_text("fk\n")
    p = {
        "type": "Join", "join_type": "right",
        "left": {"type": "Scan", "table": "left", "columns": "*"},
        "right": {"type": "Scan", "table": "right", "columns": "*"},
        "on": {
            "type": "binop", "op": "=",
            "left": {"type": "col", "name": "left.id"},
            "right": {"type": "col", "name": "right.fk"},
        },
    }
    assert execute(p) == []


# ---------------------------------------------------------------------------
# Executor — alias-based column qualification
# ---------------------------------------------------------------------------


def test_execute_join_alias_qualifies_columns(tmp_path, monkeypatch):
    """When Scan nodes carry aliases, output columns use alias.column naming."""
    import engine.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_DATA_DIR", tmp_path)
    (tmp_path / "employees.csv").write_text("id,name\n1,Alice\n")
    (tmp_path / "departments.csv").write_text("id,name\n1,Engineering\n")
    p = {
        "type": "Join", "join_type": "inner",
        "left": {"type": "Scan", "table": "employees", "alias": "e", "columns": "*"},
        "right": {"type": "Scan", "table": "departments", "alias": "d", "columns": "*"},
        "on": {
            "type": "binop", "op": "=",
            "left": {"type": "col", "name": "e.id"},
            "right": {"type": "col", "name": "d.id"},
        },
    }
    rows = execute(p)
    assert len(rows) == 1
    assert "e.id" in rows[0]
    assert "e.name" in rows[0]
    assert "d.id" in rows[0]
    assert "d.name" in rows[0]
    assert "employees.name" not in rows[0]


def test_execute_left_join_null_key_never_matches(tmp_path, monkeypatch):
    """NULL join key on the left side is treated as unmatched (LEFT JOIN emits null row)."""
    import engine.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_DATA_DIR", tmp_path)
    (tmp_path / "left.csv").write_text("id,fk\n1,1\n2,\n")
    (tmp_path / "right.csv").write_text("id\n1\n")
    p = {
        "type": "Join", "join_type": "left",
        "left": {"type": "Scan", "table": "left", "columns": "*"},
        "right": {"type": "Scan", "table": "right", "columns": "*"},
        "on": {
            "type": "binop", "op": "=",
            "left": {"type": "col", "name": "left.fk"},
            "right": {"type": "col", "name": "right.id"},
        },
    }
    rows = execute(p)
    assert len(rows) == 2
    matched = next(r for r in rows if r["left.id"] == 1)
    assert matched["right.id"] == 1
    unmatched = next(r for r in rows if r["left.id"] == 2)
    assert unmatched["right.id"] is None


# ---------------------------------------------------------------------------
# End-to-end: plan → execute using real employees/departments tables
# ---------------------------------------------------------------------------


def test_e2e_left_join_returns_all_employees():
    """LEFT JOIN returns all 5 employees even when Dave has no matching department."""
    rows = execute(plan(
        "SELECT e.name, d.location FROM employees AS e LEFT JOIN departments AS d "
        "ON e.department = d.name ORDER BY e.name ASC"
    ))
    assert len(rows) == 5
    names = [r["e.name"] for r in rows]
    assert names == ["Alice", "Bob", "Carol", "Dave", "Eve"]


def test_e2e_left_join_matched_rows_have_location():
    """Employees with matching departments get a non-NULL location."""
    rows = execute(plan(
        "SELECT e.name, d.location FROM employees AS e LEFT JOIN departments AS d "
        "ON e.department = d.name ORDER BY e.name ASC"
    ))
    by_name = {r["e.name"]: r["d.location"] for r in rows}
    assert by_name["Alice"] == "New York"
    assert by_name["Bob"] == "London"
    assert by_name["Carol"] == "New York"
    assert by_name["Eve"] == "London"


def test_e2e_left_join_dave_location_is_null():
    """Dave's department 'HR' has no match in departments.name; location must be None."""
    rows = execute(plan(
        "SELECT e.name, d.location FROM employees AS e LEFT JOIN departments AS d "
        "ON e.department = d.name ORDER BY e.name ASC"
    ))
    by_name = {r["e.name"]: r["d.location"] for r in rows}
    assert by_name["Dave"] is None


def test_e2e_left_join_order_by_name_asc():
    """ORDER BY e.name ASC must produce alphabetical order across all 5 rows."""
    rows = execute(plan(
        "SELECT e.name, d.location FROM employees AS e LEFT JOIN departments AS d "
        "ON e.department = d.name ORDER BY e.name ASC"
    ))
    names = [r["e.name"] for r in rows]
    assert names == sorted(names)


def test_e2e_right_join_via_planner(tmp_path, monkeypatch):
    """RIGHT JOIN plan through the full planner → executor stack."""
    import engine.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_DATA_DIR", tmp_path)
    (tmp_path / "emp.csv").write_text("id,name,dept\n1,Alice,Eng\n")
    (tmp_path / "dept.csv").write_text("name,loc\nEng,NY\nHR,Berlin\n")
    rows = execute(plan(
        "SELECT e.name, d.loc FROM emp AS e RIGHT JOIN dept AS d ON e.dept = d.name ORDER BY d.loc ASC"
    ))
    assert len(rows) == 2
    berlin_row = next(r for r in rows if r["d.loc"] == "Berlin")
    assert berlin_row["e.name"] is None


def test_e2e_inner_join_unaffected_by_outer_join_code():
    """Existing INNER JOIN query (query 13) still returns correct 5-row result."""
    rows = execute(plan(
        "SELECT employees.name, departments.name FROM employees "
        "INNER JOIN departments ON employees.dept_id = departments.id "
        "ORDER BY employees.name ASC"
    ))
    assert len(rows) == 5
    by_name = {r["employees.name"]: r["departments.name"] for r in rows}
    assert by_name["Dave"] == "Human Resources"
    assert by_name["Alice"] == "Engineering"
