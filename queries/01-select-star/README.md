# Query 01: SELECT * FROM employees

This query exercises the minimal end-to-end path: the lexer tokenises `SELECT * FROM employees`, the parser builds an AST, the planner emits a `Scan` node, and the executor reads `data/employees.csv` returning all rows. It is the convergence gate for the Scan node — the simplest possible query that validates the full frontend→engine pipeline without any filtering, projection, or joining.
