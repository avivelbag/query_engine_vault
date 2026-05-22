from engine.storage import load_table


def execute(plan: dict) -> list[dict]:
    """Dispatch a plan node and return the result as a list of dicts.

    Supported node types: Scan.
    Raises ValueError for unknown node types.
    """
    node_type = plan.get("type")
    if node_type == "Scan":
        return _scan(plan)
    raise ValueError(f"Unknown plan node type: {node_type!r}")


def _scan(plan: dict) -> list[dict]:
    rows = load_table(plan["table"])
    if plan["columns"] == "*":
        return rows
    return [{col: row[col] for col in plan["columns"]} for row in rows]
