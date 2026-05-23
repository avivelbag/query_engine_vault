# Query 14 — SELECT DISTINCT

Demonstrates `SELECT DISTINCT`, which deduplicates result rows before returning them.

## SQL

```sql
SELECT DISTINCT department FROM employees ORDER BY department ASC;
```

## Feature

The `DISTINCT` keyword after `SELECT` causes the engine to deduplicate output rows
by full-row equality before applying `ORDER BY`. In this example the `employees`
table contains five rows across three departments; after deduplication only one row
per department survives.

## Plan

```
Sort
  └── Distinct
        └── Project(department)
              └── Scan(employees)
```

## NULL-equality rule

For deduplication purposes, two `NULL` values in the same column position are
treated as equal (`NULL == NULL` is `true`). This is the one place in the engine
where this holds — it matches standard SQL DISTINCT behaviour, which groups all
NULL values together rather than treating each NULL as distinct from the others.
