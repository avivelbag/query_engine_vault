from frontend.parser import parse


def plan(sql: str) -> dict:
    """Convert a SQL string into a canonical plan dict.

    Calls parse() then maps the AST to a plan node conforming to spec/plan.md.
    Evaluation order follows SQL semantics: Scan → Filter → Project.

    - SELECT * FROM t            → Scan
    - SELECT a, b FROM t         → Project(Scan)
    - SELECT * FROM t WHERE ...  → Filter(Scan)
    - SELECT a FROM t WHERE ...  → Project(Filter(Scan))

    Raises ValueError for unsupported statement types.
    """
    ast = parse(sql)
    if ast["type"] == "select":
        cols = ast["columns"]
        scan = {"type": "Scan", "table": ast["from"], "columns": "*"}
        source = scan

        if ast.get("where") is not None:
            source = {"type": "Filter", "source": source, "predicate": ast["where"]}

        if cols != ["*"]:
            source = {"type": "Project", "source": source, "columns": cols}

        return source
    raise ValueError(f"Unsupported statement type: {ast['type']!r}")
