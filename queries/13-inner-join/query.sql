SELECT employees.name, departments.name FROM employees INNER JOIN departments ON employees.dept_id = departments.id ORDER BY employees.name ASC;
