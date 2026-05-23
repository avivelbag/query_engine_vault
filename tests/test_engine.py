"""Unit tests for engine: storage and executor."""
import pytest

from engine.executor import execute
from engine.storage import _coerce, load_table


# ---------------------------------------------------------------------------
# _coerce
# ---------------------------------------------------------------------------


def test_coerce_integer():
    assert _coerce("42") == 42
    assert isinstance(_coerce("42"), int)


def test_coerce_float():
    assert _coerce("3.14") == pytest.approx(3.14)
    assert isinstance(_coerce("3.14"), float)


def test_coerce_string():
    assert _coerce("Alice") == "Alice"
    assert isinstance(_coerce("Alice"), str)


def test_coerce_negative_integer():
    assert _coerce("-7") == -7


def test_coerce_zero():
    assert _coerce("0") == 0
    assert isinstance(_coerce("0"), int)


# ---------------------------------------------------------------------------
# load_table
# ---------------------------------------------------------------------------


def test_load_table_employees():
    rows = load_table("employees")
    assert len(rows) == 5
    assert rows[0] == {"id": 1, "name": "Alice", "department": "Engineering", "salary": 95000, "age": 28, "dept_id": 1}


def test_load_table_returns_list_of_dicts():
    rows = load_table("employees")
    assert all(isinstance(r, dict) for r in rows)


def test_load_table_coerces_types():
    rows = load_table("employees")
    assert isinstance(rows[0]["id"], int)
    assert isinstance(rows[0]["salary"], int)
    assert isinstance(rows[0]["name"], str)


def test_load_table_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_table("nonexistent_table")


def test_load_table_empty_csv(tmp_path, monkeypatch):
    """Empty CSV (headers only) returns an empty list."""
    csv_file = tmp_path / "empty.csv"
    csv_file.write_text("id,name\n")

    import engine.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_DATA_DIR", tmp_path)

    rows = load_table("empty")
    assert rows == []


def test_load_table_single_row_csv(tmp_path, monkeypatch):
    csv_file = tmp_path / "one.csv"
    csv_file.write_text("x,y\n10,hello\n")

    import engine.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_DATA_DIR", tmp_path)

    rows = load_table("one")
    assert rows == [{"x": 10, "y": "hello"}]


# ---------------------------------------------------------------------------
# execute
# ---------------------------------------------------------------------------


def test_execute_scan_all_rows():
    plan = {"type": "Scan", "table": "employees", "columns": "*"}
    rows = execute(plan)
    assert len(rows) == 5


def test_execute_scan_first_row():
    plan = {"type": "Scan", "table": "employees", "columns": "*"}
    rows = execute(plan)
    assert rows[0]["name"] == "Alice"


def test_execute_unknown_node_type_raises():
    with pytest.raises(ValueError, match="Unknown plan node type"):
        execute({"type": "Bogus", "table": "employees", "columns": "*"})


def test_execute_missing_type_raises():
    with pytest.raises(ValueError, match="Unknown plan node type"):
        execute({"table": "employees", "columns": "*"})


def test_execute_scan_empty_table(tmp_path, monkeypatch):
    csv_file = tmp_path / "blank.csv"
    csv_file.write_text("a,b\n")

    import engine.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_DATA_DIR", tmp_path)

    rows = execute({"type": "Scan", "table": "blank", "columns": "*"})
    assert rows == []
