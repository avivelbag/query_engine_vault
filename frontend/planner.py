from frontend.parser import parse


def plan(sql: str) -> dict:
    """Convert a SQL string into a canonical plan dict.

    Calls parse() then maps the AST to a plan node conforming to spec/plan.md.
    Evaluation order follows SQL semantics: Scan → Filter → Project → Sort → Limit.
    When the SELECT list contains aggregate function calls, emits Aggregate instead
    of Project (GROUP BY is out of scope; mixing aggregates and plain columns raises).

    - SELECT * FROM t                         → Scan
    - SELECT a, b FROM t                      → Project(Scan)
    - SELECT * FROM t WHERE ...               → Filter(Scan)
    - SELECT a FROM t WHERE ... ORDER BY c    → Sort(Project(Filter(Scan)))
    - SELECT a FROM t ORDER BY c LIMIT n      → Limit(Sort(Project(Scan)))
    - SELECT COUNT(*) FROM t                  → Aggregate(Scan)
    - SELECT MIN(x) FROM t WHERE ...          → Aggregate(Filter(Scan))

    Raises ValueError for unsupported statement types.
    """
    ast = parse(sql)
    if ast["type"] == "select":
        cols = ast["columns"]
        scan = {"type": "Scan", "table": ast["from"], "columns": "*"}
        source = scan

        if ast.get("where") is not None:
            source = {"type": "Filter", "source": source, "predicate": ast["where"]}

        if cols != ["*"] and any(isinstance(c, dict) and c.get("type") == "func" for c in cols):
            aggregates = []
            for func_call in cols:
                fn = func_call["name"]
                col = func_call["args"][0]["name"]
                alias = f"{fn.upper()}({col})"
                aggregates.append({"function": fn, "column": col, "alias": alias})
            return {"type": "Aggregate", "source": source, "aggregates": aggregates}

        if cols != ["*"]:
            source = {"type": "Project", "source": source, "columns": cols}

        if ast.get("order_by"):
            source = {"type": "Sort", "source": source, "keys": ast["order_by"]}

        if ast.get("limit") is not None:
            source = {"type": "Limit", "source": source, "count": ast["limit"]}

        return source
    raise ValueError(f"Unsupported statement type: {ast['type']!r}")
