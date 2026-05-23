# Query 16 — IS NULL predicate

Demonstrates `IS NULL` in a `WHERE` clause to select rows where a column has no value.

## Query

```sql
SELECT name FROM employees WHERE manager_id IS NULL ORDER BY name ASC;
```

## Feature: `isnull` expression node

`IS NULL` evaluates the left-hand expression and returns `true` when the result
is `None` (SQL NULL), `false` otherwise. `IS NOT NULL` inverts the test.

Unlike `= NULL`, which always returns `false` under SQL three-valued logic,
`IS NULL` is the correct way to test for the absence of a value. This predicate
always returns a Python `bool` — it never propagates NULL.

### Why `= NULL` does not work

In SQL, `NULL = NULL` evaluates to `unknown` (not `true`), so a `WHERE` clause
like `WHERE manager_id = NULL` would exclude every row, including rows where
`manager_id` actually is NULL. `IS NULL` is the dedicated operator for this test.

## Plan

```
Sort(
  Project(
    Filter(
      Scan(employees),
      predicate: {type:"isnull", negated:false,
                  expr:{type:"col","name":"manager_id"}}
    ),
    columns: ["name"]
  ),
  keys: [{column:"name", direction:"asc"}]
)
```

## Expected output

Employees with no manager (top-level employees), sorted alphabetically:

| name  |
|-------|
| Alice |
| Carol |
