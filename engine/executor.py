from engine.storage import load_table


def execute(plan: dict) -> list[dict]:
    """Dispatch a plan node and return the result as a list of dicts.

    Supported node types: Scan, Filter, Project, Sort, Limit.
    Raises ValueError for unknown node types.
    """
    node_type = plan.get("type")
    if node_type == "Scan":
        return _scan(plan)
    if node_type == "Filter":
        return _filter(plan)
    if node_type == "Project":
        return _project(plan)
    if node_type == "Sort":
        return _sort(plan)
    if node_type == "Limit":
        return _limit(plan)
    if node_type == "Aggregate":
        return _aggregate(plan)
    raise ValueError(f"Unknown plan node type: {node_type!r}")


def _scan(plan: dict) -> list[dict]:
    return load_table(plan["table"])


def _filter(plan: dict) -> list[dict]:
    """Execute source node then keep only rows where the predicate is truthy."""
    rows = execute(plan["source"])
    predicate = plan["predicate"]
    return [row for row in rows if eval_expr(predicate, row)]


def _project(plan: dict) -> list[dict]:
    """Execute source node then keep only the declared columns in order."""
    rows = execute(plan["source"])
    cols = plan["columns"]
    return [{c: row[c] for c in cols} for row in rows]


def _sort(plan: dict) -> list[dict]:
    """Execute source node then return rows ordered by the key list.

    Uses Python's stable sort iterated in reverse key order so that the first
    key in the list is the primary sort key (multi-column sort via stable sort).
    An empty source returns [] without error.
    """
    rows = execute(plan["source"])
    for key in reversed(plan["keys"]):
        col = key["column"]
        rows = sorted(rows, key=lambda r: r[col], reverse=(key["direction"] == "desc"))
    return rows


def _limit(plan: dict) -> list[dict]:
    """Execute source node then return only the first count rows.

    An empty source or count larger than available rows returns all rows.
    """
    return execute(plan["source"])[: plan["count"]]


def _aggregate(plan: dict) -> list[dict]:
    """Execute source, compute each aggregate over all rows, return a single-row result.

    NULL semantics (matches spec/plan.md):
    - COUNT(*): counts every row regardless of NULLs.
    - COUNT(col): counts non-NULL values in that column.
    - SUM / AVG / MIN / MAX: ignore NULLs; return None when no non-NULL values exist.
    - AVG on an empty set (or all-NULL column): None.
    """
    rows = execute(plan["source"])
    result = {}
    for agg in plan["aggregates"]:
        fn = agg["function"]
        col = agg["column"]
        alias = agg["alias"]
        if col == "*":
            non_null = None
        else:
            vals = [r[col] for r in rows]
            non_null = [v for v in vals if v is not None]
        if fn == "count":
            result[alias] = len(rows) if col == "*" else len(non_null)
        elif fn == "sum":
            result[alias] = sum(non_null) if non_null else None
        elif fn == "avg":
            result[alias] = sum(non_null) / len(non_null) if non_null else None
        elif fn == "min":
            result[alias] = min(non_null) if non_null else None
        elif fn == "max":
            result[alias] = max(non_null) if non_null else None
        else:
            raise ValueError(f"Unknown aggregate function: {fn!r}")
    return [result]


def eval_expr(expr: dict, row: dict):
    """Evaluate an expression dict against a row, returning a scalar or bool.

    Supports the expression sub-language from spec/plan.md:
    - {"type":"col","name":"<name>"}  → value of that column in row
    - {"type":"lit","value":<scalar>} → the constant scalar
    - {"type":"binop","op":"...","left":<expr>,"right":<expr>}
        Operators: = != < <= > >=
        NULL rule: any operand that is None yields False (SQL three-valued logic).
        Type coercion: int vs float promotes both to float before comparing.
    """
    t = expr["type"]
    if t == "col":
        return row[expr["name"]]
    if t == "lit":
        return expr["value"]
    if t == "binop":
        left = eval_expr(expr["left"], row)
        right = eval_expr(expr["right"], row)
        if left is None or right is None:
            return False
        if isinstance(left, int) and isinstance(right, float):
            left = float(left)
        elif isinstance(left, float) and isinstance(right, int):
            right = float(right)
        op = expr["op"]
        if op == "=":
            return left == right
        if op == "!=":
            return left != right
        if op == "<":
            return left < right
        if op == "<=":
            return left <= right
        if op == ">":
            return left > right
        if op == ">=":
            return left >= right
        raise ValueError(f"Unknown operator: {op!r}")
    raise ValueError(f"Unknown expression type: {t!r}")
