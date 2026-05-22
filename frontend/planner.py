from frontend.parser import parse


def plan(sql: str) -> dict:
    """Convert a SQL string into a canonical plan dict.

    Calls parse() then maps the AST to a plan node conforming to spec/plan.md.
    SELECT * emits a bare Scan node. SELECT col1, col2 wraps a Scan in a
    Project node that restricts output to the named columns in declaration order.

    Raises ValueError for unsupported statement types.
    """
    ast = parse(sql)
    if ast["type"] == "select":
        cols = ast["columns"]
        scan = {"type": "Scan", "table": ast["from"], "columns": "*"}
        if cols == ["*"]:
            return scan
        return {"type": "Project", "source": scan, "columns": cols}
    raise ValueError(f"Unsupported statement type: {ast['type']!r}")
