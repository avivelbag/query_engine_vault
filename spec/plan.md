# Query Plan Specification

This document is the canonical definition of plan nodes. Both the frontend (planner) and the engine (executor) must conform to these shapes. No plan node type may appear in either layer unless it is defined here.

## Type Coercion

When reading a CSV, each cell value is coerced in order:
1. Attempt `int` parse — if successful, the value is an integer.
2. Attempt `float` parse — if successful, the value is a float.
3. Otherwise, the value remains a string.

This rule is applied by `engine/storage.py` and must be reflected in any test fixture that reconstructs expected output.

## Node Types

### Scan

Reads all rows from a named table stored as a CSV in `data/`.

```json
{
  "type": "Scan",
  "table": "<string: table name>",
  "columns": "*"
}
```

`columns: "*"` returns all columns in CSV order.

### Project

Keeps a strict ordered subset of columns from its source node.

```json
{
  "type": "Project",
  "source": { "type": "Scan", "table": "employees", "columns": "*" },
  "columns": ["id", "name"]
}
```

`columns` is an ordered list of column names; the executor emits rows with only those columns in the listed order. `source` may be any plan node (recursive composition).
