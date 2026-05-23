# Query 12 — GROUP BY with HAVING

Exercises HAVING to filter aggregate groups: keeps only departments with more than one employee.

**SQL**
```sql
SELECT department, COUNT(*) AS cnt FROM employees GROUP BY department HAVING cnt > 1 ORDER BY department ASC;
```

**Plan**: Sort(Aggregate(Scan, group_by=[department], having={cnt > 1}))

**Expected output** (2 rows — HR has only 1 employee and is filtered out):

| department  | cnt |
|-------------|-----|
| Engineering | 2   |
| Marketing   | 2   |

The HAVING predicate `cnt > 1` references the aggregate alias. ORDER BY makes the result deterministic.
