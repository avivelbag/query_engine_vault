SELECT department, COUNT(*) AS cnt FROM employees GROUP BY department HAVING cnt > 1 ORDER BY department ASC;
