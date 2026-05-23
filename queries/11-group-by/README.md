# Query 11 — GROUP BY with COUNT

Exercises per-group aggregation: counts employees in each department.

**SQL**
```sql
SELECT department, COUNT(*) AS cnt FROM employees GROUP BY department ORDER BY department ASC;
```

**Plan**: Sort(Aggregate(Scan, group_by=[department]))

**Expected output** (3 rows, one per department, ordered by department name):

| department  | cnt |
|-------------|-----|
| Engineering | 2   |
| HR          | 1   |
| Marketing   | 2   |

ORDER BY is included so the result is deterministic.
