# Query 07 — COUNT(*)

```sql
SELECT COUNT(*) FROM employees;
```

Counts all rows in the `employees` table. The result is a single row with one
column aliased `COUNT(*)`. The `employees` fixture has 5 rows, so the expected
value is `5`.
