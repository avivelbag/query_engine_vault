# Query 05 — ORDER BY (multi-column)

Demonstrates multi-column `ORDER BY` without a `LIMIT`.

```sql
SELECT name, department FROM employees ORDER BY department ASC, name ASC;
```

Expected result is sorted first by `department` ascending, then by `name` ascending within each department.
