# Query 15 — IN Operator

Demonstrates the `IN` membership predicate in a `WHERE` clause.

## Query

```sql
SELECT name, department FROM employees WHERE department IN ('Engineering', 'Marketing') ORDER BY name ASC;
```

## Feature: `in` expression node

The `IN` predicate evaluates the left-hand expression and returns `true` if the
result equals any value in the parenthesised list.  `NOT IN` inverts the test.

### NULL-skip rule

- If the **left-hand expression** evaluates to `NULL`, the predicate returns
  `false` for both `IN` and `NOT IN` — the row is excluded regardless.
- If a **value inside the list** evaluates to `NULL`, that entry is silently
  skipped and never matches.  This follows the most useful interpretation for a
  simple engine and avoids returning `unknown` for otherwise-matchable rows.

## Plan

```
Sort(
  Project(
    Filter(
      Scan(employees),
      predicate: {type:"in", negated:false,
                  expr:{type:"col","name":"department"},
                  values:[{type:"lit","value":"Engineering"},
                          {type:"lit","value":"Marketing"}]}
    ),
    columns: ["name", "department"]
  ),
  keys: [{column:"name", direction:"asc"}]
)
```

## Expected output

Employees in Engineering or Marketing sorted alphabetically by name:

| name  | department  |
|-------|-------------|
| Alice | Engineering |
| Bob   | Marketing   |
| Carol | Engineering |
| Eve   | Marketing   |
