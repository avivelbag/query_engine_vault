# Supported Features

| Feature              | SQL Syntax                                              | Plan Node | Query Dir                      |
|----------------------|---------------------------------------------------------|-----------|--------------------------------|
| Full table scan      | `SELECT * FROM <table>`                                 | Scan      | queries/01-select-star         |
| Column projection    | `SELECT col1, col2 FROM <table>`                        | Project   | queries/02-column-projection   |
| WHERE filter         | `SELECT ... FROM <table> WHERE <col> <op> <literal>`    | Filter    | queries/03-where-equality      |
| ORDER BY             | `SELECT ... FROM <table> ORDER BY col1 ASC, col2 DESC`  | Sort      | queries/05-order-by            |
| LIMIT                | `SELECT ... FROM <table> ORDER BY ... LIMIT n`          | Limit     | queries/06-order-by-limit      |
| Aggregate functions  | `SELECT COUNT(*)\|SUM(c)\|AVG(c)\|MIN(c)\|MAX(c) FROM …` | Aggregate | queries/07-count-star          |
| Scalar arithmetic    | `SELECT col * lit AS alias … WHERE col op lit`          | Project   | queries/09-arithmetic-select   |
| GROUP BY             | `SELECT col, AGG(*) AS alias … GROUP BY col`            | Aggregate | queries/11-group-by            |
| HAVING               | `SELECT col, AGG(*) AS alias … GROUP BY col HAVING …`   | Aggregate | queries/12-group-by-having     |
| INNER JOIN           | `SELECT t1.col, t2.col FROM t1 INNER JOIN t2 ON t1.k = t2.k` | Join | queries/13-inner-join      |
| SELECT DISTINCT      | `SELECT DISTINCT col1 [, col2] FROM <table>`                  | Distinct | queries/14-distinct    |
| IN / NOT IN          | `SELECT ... FROM <table> WHERE col IN (v1, v2, ...)`          | Filter   | queries/15-in-operator |
| IS NULL / IS NOT NULL | `SELECT ... FROM <table> WHERE col IS NULL / IS NOT NULL`    | Filter   | queries/16-is-null     |
| LEFT JOIN            | `SELECT a.col, b.col FROM t1 AS a LEFT [OUTER] JOIN t2 AS b ON a.k = b.k` | Join | queries/18-left-join |
| RIGHT JOIN           | `SELECT a.col, b.col FROM t1 AS a RIGHT [OUTER] JOIN t2 AS b ON a.k = b.k` | Join | —            |
