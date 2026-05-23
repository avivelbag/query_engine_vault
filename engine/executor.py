from engine.storage import load_table


def execute(plan: dict) -> list[dict]:
    """Dispatch a plan node and return the result as a list of dicts.

    Supported node types: Scan, Filter, Project.
    Raises ValueError for unknown node types.
    """
    node_type = plan.get("type")
    if node_type == "Scan":
        return _scan(plan)
    if node_type == "Filter":
        return _filter(plan)
    if node_type == "Project":
        return _project(plan)
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
