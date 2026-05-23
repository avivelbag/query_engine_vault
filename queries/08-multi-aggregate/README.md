# Query 08 — Multi-aggregate with WHERE

```sql
SELECT MIN(age), MAX(age), AVG(age) FROM employees WHERE department = 'Engineering';
```

Filters to Engineering employees (Alice age=28, Carol age=42) then computes three
aggregates in a single pass.  The result is one row with columns `MIN(age)`,
`MAX(age)`, and `AVG(age)`.

Expected values:
- `MIN(age)` = 28 (integer)
- `MAX(age)` = 42 (integer)
- `AVG(age)` = 35.0 (float — Python's default `sum/len` division result)

The `AVG` value in `expected.csv` is written as Python's default `float` repr
(`35.0`) so that the comparison in `test_convergence` is exact after CSV
coercion via `_coerce`.
