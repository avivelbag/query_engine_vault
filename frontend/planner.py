from frontend.parser import parse


def plan(sql: str) -> dict:
    """Convert a SQL string into a canonical plan dict.

    Calls parse() then maps the AST to a plan node conforming to spec/plan.md.
    Evaluation order follows SQL semantics: Scan → Filter → Aggregate/Project → Sort → Limit.

    - SELECT * FROM t                                         → Scan
    - SELECT a, b FROM t                                      → Project(Scan)
    - SELECT * FROM t WHERE ...                               → Filter(Scan)
    - SELECT a FROM t WHERE ... ORDER BY c                    → Sort(Project(Filter(Scan)))
    - SELECT a FROM t ORDER BY c LIMIT n                      → Limit(Sort(Project(Scan)))
    - SELECT COUNT(*) FROM t                                  → Aggregate(Scan)
    - SELECT MIN(x) FROM t WHERE ...                          → Aggregate(Filter(Scan))
    - SELECT dept, COUNT(*) AS cnt FROM t GROUP BY dept       → Aggregate(Scan, group_by=[dept])
    - SELECT dept, COUNT(*) AS cnt FROM t GROUP BY dept
        HAVING cnt > 1 ORDER BY dept                          → Sort(Aggregate(..., having=...))

    Raises ValueError for unsupported statement types or invalid combinations
    (e.g. mixing aggregates with plain columns without GROUP BY).
    """
    ast = parse(sql)
    if ast["type"] != "select":
        raise ValueError(f"Unsupported statement type: {ast['type']!r}")

    cols = ast["columns"]
    scan = {"type": "Scan", "table": ast["from"], "columns": "*"}
    source = scan

    if ast.get("where") is not None:
        source = {"type": "Filter", "source": source, "predicate": ast["where"]}

    has_aggregates = any(isinstance(c, dict) and c.get("type") == "func" for c in cols)

    if has_aggregates:
        group_cols = ast.get("group_by") or []
        has_plain = any(not (isinstance(c, dict) and c.get("type") == "func") for c in cols)
        if has_plain and not group_cols:
            raise ValueError(
                "Cannot mix aggregate functions and plain columns in SELECT list without GROUP BY"
            )

        aggregates = []
        for col_desc in cols:
            if isinstance(col_desc, dict) and col_desc.get("type") == "func":
                fn = col_desc["name"]
                col_name = col_desc["args"][0]["name"]
                alias = col_desc.get("alias") or f"{fn.upper()}({col_name})"
                aggregates.append({"function": fn, "column": col_name, "alias": alias})

        agg_node: dict = {"type": "Aggregate", "source": source, "aggregates": aggregates}
        if group_cols:
            agg_node["group_by"] = group_cols
        having = ast.get("having")
        if having is not None:
            agg_node["having"] = having
        source = agg_node
    elif cols != ["*"]:
        source = {"type": "Project", "source": source, "columns": cols}

    if ast.get("order_by"):
        source = {"type": "Sort", "source": source, "keys": ast["order_by"]}

    if ast.get("limit") is not None:
        source = {"type": "Limit", "source": source, "count": ast["limit"]}

    return source
