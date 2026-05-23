SELECT e.name, d.location FROM employees AS e LEFT JOIN departments AS d ON e.department = d.name ORDER BY e.name ASC;
