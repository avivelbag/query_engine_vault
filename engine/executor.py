from engine.storage import load_table


def execute(plan: dict) -> list[dict]:
    """Dispatch a plan node and return the result as a list of dicts.

    Supported node types: Scan, Filter, Project, Sort, Limit, Aggregate, Join.
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
    if node_type == "Join":
        return _join(plan)
    if node_type == "Distinct":
        return _distinct(plan)
    raise ValueError(f"Unknown plan node type: {node_type!r}")


def _scan(plan: dict) -> list[dict]:
    return load_table(plan["table"])


def _filter(plan: dict) -> list[dict]:
    """Execute source node then keep only rows where the predicate is truthy."""
    rows = execute(plan["source"])
    predicate = plan["predicate"]
    return [row for row in rows if eval_expr(predicate, row)]


def _normalise_col_desc(c) -> dict:
    """Coerce a bare string or col-descriptor dict to canonical {expr, alias} form.

    Bare strings are backward-compatible column names; they become a ColRef with
    no alias so the rest of _project sees a uniform shape.
    """
    if isinstance(c, str):
        return {"expr": {"type": "col", "name": c}, "alias": None}
    return c


def _project(plan: dict) -> list[dict]:
    """Execute source then emit rows containing only the declared column descriptors.

    Each descriptor is normalised to {expr, alias} via _normalise_col_desc.  The
    output key is the alias when present; for a bare ColRef it is the column name;
    for any other expression it is the repr of the expr dict.
    """
    rows = execute(plan["source"])
    out = []
    for row in rows:
        new_row = {}
        for c in plan["columns"]:
            desc = _normalise_col_desc(c)
            val = eval_expr(desc["expr"], row)
            if desc["alias"] is not None:
                key = desc["alias"]
            elif desc["expr"]["type"] == "col":
                key = desc["expr"]["name"]
            else:
                key = str(desc["expr"])
            new_row[key] = val
        out.append(new_row)
    return out


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
    """Execute source, partition by group_by keys, compute aggregates per group, apply HAVING.

    When group_by is absent or empty the node behaves as a whole-table aggregate and
    returns exactly one result row (backward-compatible with existing queries 07–08).

    When group_by is non-empty, one output row is produced per distinct key tuple.
    The HAVING predicate (same expression grammar as Filter) is evaluated against
    each aggregate output row and can reference aggregate aliases (e.g. cnt > 1).

    NULL semantics (matches spec/plan.md):
    - COUNT(*): counts every row in the group regardless of NULLs.
    - COUNT(col): counts non-NULL values in that column within the group.
    - SUM / AVG / MIN / MAX: ignore NULLs; return None when no non-NULL values exist.
    """
    rows = execute(plan["source"])
    group_keys = plan.get("group_by") or []

    if not group_keys:
        groups: dict = {"": rows}
    else:
        groups = {}
        for row in rows:
            key = tuple(row[k] for k in group_keys)
            groups.setdefault(key, []).append(row)

    result = []
    for key, group_rows in groups.items():
        out: dict = {}
        if group_keys:
            for col, val in zip(group_keys, key):
                out[col] = val
        for agg in plan["aggregates"]:
            fn = agg["function"]
            col = agg["column"]
            alias = agg["alias"]
            if col == "*":
                non_null = None
            else:
                vals = [r[col] for r in group_rows]
                non_null = [v for v in vals if v is not None]
            if fn == "count":
                out[alias] = len(group_rows) if col == "*" else len(non_null)
            elif fn == "sum":
                out[alias] = sum(non_null) if non_null else None
            elif fn == "avg":
                out[alias] = sum(non_null) / len(non_null) if non_null else None
            elif fn == "min":
                out[alias] = min(non_null) if non_null else None
            elif fn == "max":
                out[alias] = max(non_null) if non_null else None
            else:
                raise ValueError(f"Unknown aggregate function: {fn!r}")
        result.append(out)

    having = plan.get("having")
    if having:
        result = [r for r in result if eval_expr(having, r)]

    return result


def _distinct(plan: dict) -> list[dict]:
    """Execute source node then emit only the first occurrence of each unique row.

    Rows are keyed by a tuple of all column values in emission order. Two NULL
    values in the same column position are treated as equal for deduplication
    (NULL == NULL for DISTINCT — unlike SQL comparisons where NULL = NULL is
    unknown). Row order is the order of first occurrence (stable dedup).

    A list is used for `seen` rather than a set because future value types may be
    unhashable. This is O(n²) in the number of distinct rows; acceptable for the
    small tables this engine targets.
    """
    seen: list = []
    result: list[dict] = []
    for row in execute(plan["source"]):
        key = tuple(row[k] for k in row)
        if key not in seen:
            seen.append(key)
            result.append(row)
    return result


def _table_name_of(plan: dict) -> str:
    """Walk a plan subtree to find the root Scan's qualifier (alias if set, else table name).

    Used by _join to determine the prefix for each side's columns.
    Traverses through Filter, Project, Sort, Limit, and Aggregate nodes
    (all of which have a single 'source' child) until it reaches a Scan.
    Raises ValueError for node types that cannot be resolved to a table name.
    """
    if plan["type"] == "Scan":
        return plan.get("alias") or plan["table"]
    if "source" in plan:
        return _table_name_of(plan["source"])
    raise ValueError(f"Cannot derive table name from plan type {plan['type']!r}")


def _join(plan: dict) -> list[dict]:
    """Execute a nested-loop join supporting INNER, LEFT OUTER, and RIGHT OUTER semantics.

    Every column in the result is qualified as 'qualifier.column' where the qualifier
    is the table alias when present, otherwise the table name. NULL join keys never
    match (eval_expr returns False for NULL comparisons).

    LEFT JOIN: unmatched left rows are emitted with None for every right-side column.
    RIGHT JOIN: unmatched right rows are emitted with None for every left-side column.
    INNER JOIN: only matched rows are emitted (existing behaviour, unchanged).
    """
    join_type = plan.get("join_type", "inner")
    left_rows = execute(plan["left"])
    right_rows = execute(plan["right"])
    left_table = _table_name_of(plan["left"])
    right_table = _table_name_of(plan["right"])

    right_cols = {f"{right_table}.{k}" for row in right_rows for k in row} if right_rows else set()
    left_cols = {f"{left_table}.{k}" for row in left_rows for k in row} if left_rows else set()

    matched_right: set[int] = set()
    result = []
    for left_row in left_rows:
        merged_left = {f"{left_table}.{k}": v for k, v in left_row.items()}
        left_matched = False
        for ri, right_row in enumerate(right_rows):
            merged = {**merged_left, **{f"{right_table}.{k}": v for k, v in right_row.items()}}
            if eval_expr(plan["on"], merged):
                result.append(merged)
                left_matched = True
                matched_right.add(ri)
        if not left_matched and join_type == "left":
            result.append({**merged_left, **{k: None for k in right_cols}})

    if join_type == "right":
        for ri, right_row in enumerate(right_rows):
            if ri not in matched_right:
                merged_right = {f"{right_table}.{k}": v for k, v in right_row.items()}
                result.append({**{k: None for k in left_cols}, **merged_right})

    return result


def eval_expr(expr: dict, row: dict):
    """Evaluate an expression dict against a row, returning a scalar or bool.

    Supports the expression sub-language from spec/plan.md:
    - {"type":"col","name":"<name>"}  → value of that column in row
    - {"type":"lit","value":<scalar>} → the constant scalar
    - {"type":"binop","op":"...","left":<expr>,"right":<expr>}
        Arithmetic ops (+, -, *, /):
          NULL operand → None (propagate).
          Division by zero raises ZeroDivisionError.
          int / int → float (Python 3 semantics).
        Comparison ops (= != < <= > >=):
          NULL operand → False (SQL three-valued logic).
          int vs float promotes both to float before comparing.
    """
    t = expr["type"]
    if t == "col":
        return row[expr["name"]]
    if t == "lit":
        return expr["value"]
    if t == "binop":
        op = expr["op"]
        left = eval_expr(expr["left"], row)
        right = eval_expr(expr["right"], row)
        if op in ("+", "-", "*", "/"):
            if left is None or right is None:
                return None
            if op == "+":
                return left + right
            if op == "-":
                return left - right
            if op == "*":
                return left * right
            if op == "/":
                return left / right  # ZeroDivisionError propagates to caller
        if left is None or right is None:
            return False
        if isinstance(left, int) and isinstance(right, float):
            left = float(left)
        elif isinstance(left, float) and isinstance(right, int):
            right = float(right)
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
    if t == "in":
        lhs = eval_expr(expr["expr"], row)
        if lhs is None:
            return False
        matched = any(
            lhs == eval_expr(v, row)
            for v in expr["values"]
            if eval_expr(v, row) is not None
        )
        return matched if not expr["negated"] else not matched
    if t == "isnull":
        val = eval_expr(expr["expr"], row)
        result = val is None
        return result if not expr["negated"] else not result
    raise ValueError(f"Unknown expression type: {t!r}")
