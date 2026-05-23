# Supported Features

| Feature              | SQL Syntax                                              | Plan Node | Query Dir                      |
|----------------------|---------------------------------------------------------|-----------|--------------------------------|
| Full table scan      | `SELECT * FROM <table>`                                 | Scan      | queries/01-select-star         |
| Column projection    | `SELECT col1, col2 FROM <table>`                        | Project   | queries/02-column-projection   |
| WHERE filter         | `SELECT ... FROM <table> WHERE <col> <op> <literal>`    | Filter    | queries/03-where-equality      |
| ORDER BY             | `SELECT ... FROM <table> ORDER BY col1 ASC, col2 DESC`  | Sort      | queries/05-order-by            |
| LIMIT                | `SELECT ... FROM <table> ORDER BY ... LIMIT n`          | Limit     | queries/06-order-by-limit      |
| Aggregate functions  | `SELECT COUNT(*)\|SUM(c)\|AVG(c)\|MIN(c)\|MAX(c) FROM …` | Aggregate | queries/07-count-star          |
