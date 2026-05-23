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

Keeps a strict ordered subset of columns from its source node. Each entry in `columns` is either:

- a bare string (backward-compatible plain column name, equivalent to a ColRef with no alias), or
- a column descriptor object: `{"expr": <expr_node>, "alias": <str|null>}`

When `alias` is non-null the output row uses the alias as the key. When `alias` is null and the expression is a ColRef, the output key is the column name. For any other expression without an alias, the output key is the `repr` of the expression dict.

Bare strings:

```json
{
  "type": "Project",
  "source": { "type": "Scan", "table": "employees", "columns": "*" },
  "columns": ["id", "name"]
}
```

With arithmetic expression and alias:

```json
{
  "type": "Project",
  "source": { "type": "Scan", "table": "employees", "columns": "*" },
  "columns": [
    "name",
    {"expr": {"type": "binop", "op": "*", "left": {"type": "col", "name": "salary"}, "right": {"type": "lit", "value": 1.1}}, "alias": "raised_salary"}
  ]
}
```

`source` may be any plan node (recursive composition).

### Sort

Orders its source rows by one or more keys. Uses Python's stable sort so equal keys preserve relative input order.

```json
{
  "type": "Sort",
  "source": { "type": "Scan", "table": "employees", "columns": "*" },
  "keys": [
    {"column": "department", "direction": "asc"},
    {"column": "name", "direction": "asc"}
  ]
}
```

`keys` is an ordered list of sort keys; the first entry is the primary key. Each key has a `column` (string) and a `direction` of `"asc"` or `"desc"`. An empty `source` returns `[]`.

### Limit

Returns at most `count` rows from its source node, taken from the front of the result.

```json
{
  "type": "Limit",
  "source": { "type": "Sort", "keys": [...] },
  "count": 3
}
```

`count` must be a non-negative integer. A Limit node always sits *above* a Sort node so slicing occurs after ordering. An empty `source` returns `[]`.

### Aggregate

Consumes all rows from its source, partitions them by the optional `group_by` keys, applies one or more aggregate functions per partition, and optionally filters the resulting rows with `having`.

**Whole-table aggregation** (when `group_by` is absent or `[]`): returns exactly one result row.

**GROUP BY** (when `group_by` is non-empty): returns one result row per distinct key tuple. The group columns are included in each output row alongside the aggregate values.

```json
{
  "type": "Aggregate",
  "source": { "type": "Scan", "table": "employees", "columns": "*" },
  "aggregates": [
    {"function": "count", "column": "*",      "alias": "COUNT(*)"},
    {"function": "avg",   "column": "age",    "alias": "AVG(age)"},
    {"function": "max",   "column": "salary", "alias": "MAX(salary)"}
  ],
  "group_by": ["department"],
  "having": {
    "type": "binop", "op": ">",
    "left":  {"type": "col", "name": "cnt"},
    "right": {"type": "lit", "value": 1}
  }
}
```

Each entry in `aggregates` has:
- `function`: one of `"count"`, `"sum"`, `"avg"`, `"min"`, `"max"` (lowercase).
- `column`: a column name string, or `"*"` (only meaningful for `count`).
- `alias`: the output column name for this aggregate in the result row.

`group_by` (optional): an ordered list of column name strings to partition by. Omit or set to `[]` for whole-table aggregation.

`having` (optional): a predicate expression applied to each aggregate output row after aggregation. Uses the same expression grammar as the `predicate` field of a Filter node. The expression may reference aggregate aliases (e.g. `cnt`) or group columns.

**NULL and empty-set semantics:**
- `COUNT(*)` — counts every row in the group, including rows with NULL columns. Returns `0` for an empty source.
- `COUNT(col)` — counts non-NULL values in `col` within the group. Returns `0` for an empty source or all-NULL column.
- `SUM / AVG / MIN / MAX` — ignore NULL values within the group. Return `None` (written as empty string in CSV) when the set of non-NULL values is empty (empty source or all-NULL column).

Mixing aggregate calls and plain column references in the same SELECT list requires `group_by` to be non-empty; this is enforced at plan time.

## Row-Order Guarantee

When a query includes `ORDER BY`, the engine returns rows in exactly the declared order. When no `ORDER BY` is present, **the engine makes no row-order guarantee**. Tests that compare results from unordered queries must normalise both sides (e.g. sort by all columns) before asserting equality.

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

A binary operation. `op` is one of:

- **Comparison** (`=`, `!=`, `<`, `<=`, `>`, `>=`): evaluates to a boolean.
- **Arithmetic** (`+`, `-`, `*`, `/`): evaluates to a numeric scalar.

```json
{"type": "binop", "op": "=", "left": <expr>, "right": <expr>}
```

**Type coercion in comparisons:** if one operand is `int` and the other is `float`, both are promoted to `float`. Otherwise operands are compared as their Python types (string comparisons use Python `str` ordering).

**Arithmetic type semantics:**
- `int op int` → `int` for `+`, `-`, `*`; `float` for `/` (Python 3 division).
- Any `float` operand → `float` result for all arithmetic ops.
- `NULL` operand → `NULL` result (propagate; do not return zero or False).
- Division by zero raises `ZeroDivisionError`; it is not silently coerced to `NULL`.

**Operator precedence (when appearing inside larger expressions):** `*` and `/` bind tighter than `+` and `-`.

#### FuncCall

An aggregate function invocation in the SELECT list. The planner converts FuncCall nodes into Aggregate plan-node descriptors; the executor never sees this expression type directly.

```json
{"type": "func", "name": "count", "args": [{"type": "col", "name": "*"}]}
```

`name` is the lowercase function name (`count`, `sum`, `avg`, `min`, `max`). `args` is a single-element list containing either a ColRef or `{"type":"col","name":"*"}` for `COUNT(*)`.

## NULL Handling

Any comparison involving a NULL value (Python `None`) yields `false`, regardless of the operator. This matches SQL three-valued logic: `NULL = NULL` is `false`, `NULL != NULL` is `false`, etc.
