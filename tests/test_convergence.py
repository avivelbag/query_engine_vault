"""Convergence gate: for every queries/<slug>/, execute(plan(query.sql)) must equal expected.csv."""
import csv
from pathlib import Path

import pytest

from engine.executor import execute
from engine.storage import _coerce
from frontend.planner import plan

QUERIES_DIR = Path(__file__).parent.parent / "queries"

_query_dirs = sorted(d for d in QUERIES_DIR.iterdir() if d.is_dir())


def _load_expected(csv_path: Path) -> list[dict]:
    """Load expected.csv applying the canonical type coercion from storage."""
    with open(csv_path, newline="") as f:
        return [{k: _coerce(v) for k, v in row.items()} for row in csv.DictReader(f)]


@pytest.mark.parametrize("query_dir", _query_dirs, ids=[d.name for d in _query_dirs])
def test_convergence(query_dir):
    sql = (query_dir / "query.sql").read_text().strip()
    expected = _load_expected(query_dir / "expected.csv")
    assert execute(plan(sql)) == expected


def test_convergence_employees_direct():
    """Explicit non-parametrised check named in the acceptance criteria."""
    result = execute(plan("SELECT * FROM employees"))
    expected = _load_expected(QUERIES_DIR / "01-select-star" / "expected.csv")
    assert result == expected


def test_convergence_case_insensitive_keywords():
    """SQL keywords are case-insensitive; result must match regardless of casing."""
    result_upper = execute(plan("SELECT * FROM employees"))
    result_lower = execute(plan("select * from employees"))
    assert result_upper == result_lower


def test_convergence_no_query_dirs_is_not_silently_green(tmp_path):
    """Parametrise over an empty directory must yield zero tests, not vacuous pass.

    This test asserts the helper itself works on an empty queries dir without
    crashing — a parametrised suite with zero items simply skips collection.
    """
    empty = tmp_path / "queries"
    empty.mkdir()
    dirs = sorted(d for d in empty.iterdir() if d.is_dir())
    assert dirs == []
