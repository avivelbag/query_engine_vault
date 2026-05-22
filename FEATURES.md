# Supported Features

| Feature              | SQL Syntax                           | Plan Node | Query Dir                      |
|----------------------|--------------------------------------|-----------|--------------------------------|
| Full table scan      | `SELECT * FROM <table>`              | Scan      | queries/01-select-star         |
| Column projection    | `SELECT col1, col2 FROM <table>`     | Project   | queries/02-column-projection   |
