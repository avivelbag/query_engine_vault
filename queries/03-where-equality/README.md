# Query 03 — WHERE Equality Filter

Exercises the Filter node with an equality predicate on a string column.

```sql
SELECT * FROM employees WHERE department = 'Engineering';
```

Returns all columns for employees whose `department` is `'Engineering'`.
Expected rows: Alice and Carol.
