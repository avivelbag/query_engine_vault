# Query 10 — Arithmetic in WHERE clause

Demonstrates arithmetic expressions on the left-hand side of a WHERE predicate.

## SQL

```sql
SELECT name, age FROM employees WHERE age * 2 > 50 ORDER BY name ASC;
```

## Expected behaviour

`age * 2 > 50` is evaluated per row.  All five employees satisfy the condition
(minimum age is 28, and 28 * 2 = 56 > 50), so all rows are returned sorted by name.
