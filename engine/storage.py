import csv
from pathlib import Path

_DATA_DIR = Path(__file__).parent.parent / "data"


def _coerce(value: str):
    if value == "":
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def load_table(name: str) -> list[dict]:
    """Load a table from data/<name>.csv and return all rows as list-of-dicts.

    Each cell value is coerced: int first, then float, then left as string.
    Raises FileNotFoundError if the CSV does not exist.
    """
    path = _DATA_DIR / f"{name}.csv"
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        return [{k: _coerce(v) for k, v in row.items()} for row in reader]
