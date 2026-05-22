from frontend.parser import parse


def plan(sql: str) -> dict:
    """Convert a SQL string into a canonical plan dict.

    Calls parse() then maps the AST to a plan node conforming to spec/plan.md.
    Currently supports SELECT * only, emitting a Scan node:
        {"type": "Scan", "table": "<name>", "columns": "*"}

    Raises ValueError for unsupported statement types.
    """
    ast = parse(sql)
    if ast["type"] == "select":
        return {"type": "Scan", "table": ast["from"], "columns": "*"}
    raise ValueError(f"Unsupported statement type: {ast['type']!r}")
