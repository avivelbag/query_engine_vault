# Sample Data

## employees.csv

A small employee table used to drive the first query (`SELECT * FROM employees`).

| Column     | Type             | Description                                      |
|------------|------------------|--------------------------------------------------|
| id         | integer          | Unique employee identifier                       |
| name       | string           | Employee full name                               |
| department | string           | Department name (denormalised, for legacy queries) |
| salary     | integer          | Annual salary in USD                             |
| age        | integer          | Employee age                                     |
| dept_id    | integer          | Foreign key into `departments.id`                |
| manager_id | integer or NULL  | id of the employee's direct manager; empty (NULL) for top-level employees |

5 rows, mixed int/string types, covering Engineering, Marketing, and HR departments.
Alice and Carol have no manager (`manager_id` is NULL); Bob, Dave, and Eve each
report to another employee. An empty CSV cell is stored as `None` (SQL NULL) by
the storage layer.

## departments.csv

A department reference table added to support INNER JOIN queries and extended for
LEFT/RIGHT JOIN tests.

| Column   | Type    | Description                            |
|----------|---------|----------------------------------------|
| id       | integer | Unique department identifier           |
| name     | string  | Department name                        |
| location | string  | City where the department is located   |
| budget   | integer | Annual departmental budget in USD      |

3 rows: Engineering (id=1, New York), Marketing (id=2, London),
Human Resources (id=3, Berlin).

All employees have a valid `dept_id`, so `INNER JOIN … ON dept_id = id` returns
all 5 employee rows. However, the `employees.department` string for Dave is
`"HR"`, which intentionally does not match the `departments.name` value
`"Human Resources"`. This deliberate mismatch ensures that a `LEFT JOIN … ON
e.department = d.name` emits Dave with a NULL `location`, exercising the
NULL-padding path of the outer-join executor.
