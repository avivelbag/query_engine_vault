# Query 04 — WHERE Range Comparison

Exercises the Filter node with a greater-than predicate on an integer column.

```sql
SELECT * FROM employees WHERE age > 30;
```

The `employees` table includes an `age` integer column. This query returns all
columns for employees older than 30.
Expected rows: Bob (35), Carol (42), Eve (38).
