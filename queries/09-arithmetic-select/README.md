# Query 09 — Arithmetic SELECT with alias

Demonstrates scalar arithmetic in the SELECT list and column aliasing via AS.

## SQL

```sql
SELECT name, salary * 1.1 AS raised_salary FROM employees ORDER BY raised_salary DESC;
```

## Expected behaviour

`salary * 1.1` is evaluated per row, producing a float (int * float → float per Python 3
semantics). The result is aliased to `raised_salary` which is also used as the ORDER BY key.

Float values in `expected.csv` are Python's default `repr` of the computed float — the
shortest decimal string that round-trips back to the same IEEE 754 double.
