# 02 — Column Projection

Exercises the `Project` plan node, which restricts a `Scan`'s output to a
declared subset of columns in declaration order.

`SELECT id, name FROM employees` wraps a full `Scan` of the employees table
in a `Project` node that keeps only `id` and `name`, discarding `department`
and `salary`. The executor emits rows in the order the columns are listed in
the SQL, not the order they appear in the CSV.
