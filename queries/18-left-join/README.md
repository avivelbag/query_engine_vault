# Query 18 — LEFT JOIN

## SQL

```sql
SELECT e.name, d.location
FROM employees AS e
LEFT JOIN departments AS d ON e.department = d.name
ORDER BY e.name ASC;
```

## Purpose

Demonstrates LEFT OUTER JOIN semantics. Every row from the **left** table
(`employees`) appears in the result exactly once.  For a left row that finds no
matching right row, every right-side column is set to SQL NULL (an empty cell
in the CSV).

## NULL-padding rule

When a left row's join key does not equal the join key of **any** right row, the
engine emits the left row paired with `None` for each right-side column.  In
this query, Dave's `employees.department` value is `"HR"`, which has no
corresponding `departments.name` entry (the department was renamed to
`"Human Resources"`), so `d.location` is NULL for Dave.

## Expected output (ordered by employee name)

| e.name | d.location  |
|--------|-------------|
| Alice  | New York    |
| Bob    | London      |
| Carol  | New York    |
| Dave   | *(NULL)*    |
| Eve    | London      |

The deliberate name mismatch between `employees.department = "HR"` and the
department table row `name = "Human Resources"` guarantees the NULL-padding path
is exercised.
