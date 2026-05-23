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

### Filter

Keeps only rows from its source node for which the predicate expression evaluates to true.

```json
{
  "type": "Filter",
  "source": { "type": "Scan", "table": "employees", "columns": "*" },
  "predicate": {
    "type": "binop",
    "op": "=",
    "left": {"type": "col", "name": "department"},
    "right": {"type": "lit", "value": "Engineering"}
  }
}
```

`source` may be any plan node. `predicate` must be an expression (see Expression Sub-language below).

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

## Expression Sub-language

Expressions are used in predicate positions (e.g. the `predicate` field of a Filter node). They are not plan nodes and must not appear as top-level plan nodes.

#### ColRef

References a column in the current row by name.

```json
{"type": "col", "name": "<column_name>"}
```

#### Literal

A constant scalar value.

```json
{"type": "lit", "value": <int|float|str>}
```

#### BinOp

A binary comparison. `op` must be one of `=`, `!=`, `<`, `<=`, `>`, `>=`.

```json
{"type": "binop", "op": "=", "left": <expr>, "right": <expr>}
```

Type coercion in comparisons: if one operand is `int` and the other is `float`, both are promoted to `float`. Otherwise operands are compared as their Python types (string comparisons use Python `str` ordering).

## NULL Handling

Any comparison involving a NULL value (Python `None`) yields `false`, regardless of the operator. This matches SQL three-valued logic: `NULL = NULL` is `false`, `NULL != NULL` is `false`, etc.
