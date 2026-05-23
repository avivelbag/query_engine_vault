# Query 17 — IS NOT NULL predicate

Demonstrates `IS NOT NULL` in a `WHERE` clause to select rows where a column has a value.

## Query

```sql
SELECT name FROM employees WHERE manager_id IS NOT NULL ORDER BY name ASC;
```

## Feature: `isnull` expression node (negated)

`IS NOT NULL` evaluates the left-hand expression and returns `true` when the
result is not `None`, `false` when it is `None`. This is the logical complement
of `IS NULL`.

## Plan

```
Sort(
  Project(
    Filter(
      Scan(employees),
      predicate: {type:"isnull", negated:true,
                  expr:{type:"col","name":"manager_id"}}
    ),
    columns: ["name"]
  ),
  keys: [{column:"name", direction:"asc"}]
)
```

## Expected output

Employees who have a manager (non-top-level employees), sorted alphabetically:

| name |
|------|
| Bob  |
| Dave |
| Eve  |
