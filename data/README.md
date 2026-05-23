# Sample Data

## employees.csv

A small employee table used to drive the first query (`SELECT * FROM employees`).

| Column     | Type    | Description                                      |
|------------|---------|--------------------------------------------------|
| id         | integer | Unique employee identifier                       |
| name       | string  | Employee full name                               |
| department | string  | Department name (denormalised, for legacy queries) |
| salary     | integer | Annual salary in USD                             |
| age        | integer | Employee age                                     |
| dept_id    | integer | Foreign key into `departments.id`                |

5 rows, mixed int/string types, covering Engineering, Marketing, and HR departments.

## departments.csv

A department reference table added to support INNER JOIN queries.

| Column | Type    | Description                            |
|--------|---------|----------------------------------------|
| id     | integer | Unique department identifier           |
| name   | string  | Department name                        |
| budget | integer | Annual departmental budget in USD      |

3 rows: Engineering (id=1), Marketing (id=2), HR (id=3). All employees have a
matching `dept_id`, so an INNER JOIN over `employees.dept_id = departments.id`
returns all 5 employee rows.
