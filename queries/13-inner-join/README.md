# Query 13 — INNER JOIN

Demonstrates an INNER JOIN between `employees` and `departments` using an
equality predicate on `employees.dept_id = departments.id`. All five employees
have a matching department, so all five rows appear in the result.

```sql
SELECT employees.name, departments.name
FROM employees
INNER JOIN departments
ON employees.dept_id = departments.id
ORDER BY employees.name ASC;
```

## Expected output

| employees.name | departments.name |
|----------------|-----------------|
| Alice          | Engineering     |
| Bob            | Marketing       |
| Carol          | Engineering     |
| Dave           | HR              |
| Eve            | Marketing       |
