# Query Engine

A minimal SQL query engine built in two independent layers: a **frontend** that parses SQL into a plan, and an **engine** that executes that plan against CSV files.

## Two-line design

```
SQL string
  → frontend/lexer.py   (tokenise)
  → frontend/parser.py  (build AST)
  → frontend/planner.py (emit plan dict)
  → engine/executor.py  (dispatch on plan["type"])
  → engine/storage.py   (read CSV from data/)
  → list[dict]          (result rows)
```

The frontend never imports the engine; the engine never imports the frontend. The plan dict (a plain JSON-serialisable Python dict) is the only coupling between them. Node types are defined in `spec/plan.md`.

## Running a query

```python
from frontend.planner import plan
from engine.executor import execute

rows = execute(plan("SELECT * FROM employees"))
```

Or from the shell:

```bash
python3 -c "
from frontend.planner import plan
from engine.executor import execute
import json
print(json.dumps(execute(plan('SELECT * FROM employees')), indent=2))
"
```

## Adding a feature

1. Define the new plan node in `spec/plan.md` with a `### NodeType` heading.
2. Add a branch in `frontend/planner.py` that emits the new node.
3. Add a handler in `engine/executor.py` that executes the new node.
4. Add sample data to `data/` if needed.
5. Create `queries/<NN-slug>/query.sql`, `expected.csv`, and `README.md`.
6. Add an entry to `features.json` and `FEATURES.md`.
7. Run `python3 -m pytest tests/ -x --tb=short -q` — all tests must pass.

## Running tests

```bash
python3 -m pytest tests/ -x --tb=short -q
```
