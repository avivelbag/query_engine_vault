from engine.storage import load_table


def execute(plan: dict) -> list[dict]:
    """Dispatch a plan node and return the result as a list of dicts.

    Supported node types: Scan, Project.
    Raises ValueError for unknown node types.
    """
    node_type = plan.get("type")
    if node_type == "Scan":
        return _scan(plan)
    if node_type == "Project":
        return _project(plan)
    raise ValueError(f"Unknown plan node type: {node_type!r}")


def _scan(plan: dict) -> list[dict]:
    return load_table(plan["table"])


def _project(plan: dict) -> list[dict]:
    """Execute source node then keep only the declared columns in order."""
    rows = execute(plan["source"])
    cols = plan["columns"]
    return [{c: row[c] for c in cols} for row in rows]
