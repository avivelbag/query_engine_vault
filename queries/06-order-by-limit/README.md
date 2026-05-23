# Query 06 — ORDER BY + LIMIT

Demonstrates `ORDER BY` combined with `LIMIT` to return the top-N rows.

```sql
SELECT name, age FROM employees ORDER BY age DESC LIMIT 3;
```

Returns the three oldest employees, ordered from oldest to youngest.
