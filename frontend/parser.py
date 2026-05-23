from frontend.lexer import (
    tokenize,
    TK_SELECT,
    TK_FROM,
    TK_WHERE,
    TK_STAR,
    TK_IDENT,
    TK_QUALIFIED_IDENT,
    TK_SEMI,
    TK_COMMA,
    TK_EOF,
    TK_EQ,
    TK_NEQ,
    TK_LT,
    TK_LTE,
    TK_GT,
    TK_GTE,
    TK_STRING_LIT,
    TK_INT_LIT,
    TK_FLOAT_LIT,
    TK_ORDER,
    TK_BY,
    TK_ASC,
    TK_DESC,
    TK_LIMIT,
    TK_COUNT,
    TK_SUM,
    TK_AVG,
    TK_MIN,
    TK_MAX,
    TK_LPAREN,
    TK_RPAREN,
    TK_PLUS,
    TK_MINUS,
    TK_SLASH,
    TK_AS,
    TK_GROUP,
    TK_HAVING,
    TK_JOIN,
    TK_INNER,
    TK_ON,
    TK_DISTINCT,
    TK_IN,
    TK_NOT,
    TK_IS,
    TK_NULL,
    TK_LEFT,
    TK_RIGHT,
    TK_OUTER,
)

_COMP_OPS = {TK_EQ: "=", TK_NEQ: "!=", TK_LT: "<", TK_LTE: "<=", TK_GT: ">", TK_GTE: ">="}

_AGG_KEYWORDS = {TK_COUNT, TK_SUM, TK_AVG, TK_MIN, TK_MAX}


def parse(sql: str) -> dict:
    """Parse a SQL string and return an AST dict.

    Only SELECT statements are supported. Returns:
        {
            "type": "select",
            "columns": ["*"] | list of column descriptors,
            "from": "<table_name>",
            "where": <predicate_expr> | None,
            "group_by": [<col_name>, ...],
            "having": <predicate_expr> | None,
            "order_by": [{"column": "<col>", "direction": "asc"|"desc"}, ...],
            "limit": <int> | None,
        }

    Column descriptors in the SELECT list are one of:
      - a bare string (backward-compatible plain column reference, no alias)
      - {"type":"func","name":<str>,"args":[<expr>]} for aggregate calls (no explicit alias)
      - {"type":"func","name":<str>,"args":[<expr>],"alias":<str>} for aliased aggregate calls
      - {"expr": <expr_node>, "alias": <str>} for arithmetic or aliased plain columns

    Mixing aggregate calls and plain columns is allowed at parse time; the planner
    enforces that GROUP BY must be present when both are used.

    Raises ValueError on syntax errors.
    """
    tokens = tokenize(sql)
    pos = 0

    def peek():
        return tokens[pos]

    def consume(expected_type: str):
        nonlocal pos
        t = tokens[pos]
        if t.type != expected_type:
            raise ValueError(
                f"Expected token {expected_type!r}, got {t.type!r} ({t.value!r})"
            )
        pos += 1
        return t

    consume(TK_SELECT)

    distinct = False
    if peek().type == TK_DISTINCT:
        consume(TK_DISTINCT)
        distinct = True

    t = peek()
    if t.type == TK_STAR:
        consume(TK_STAR)
        columns = ["*"]
    else:
        columns = [_parse_one_select_col(peek, consume)]
        while peek().type == TK_COMMA:
            consume(TK_COMMA)
            columns.append(_parse_one_select_col(peek, consume))

    consume(TK_FROM)
    table_token = consume(TK_IDENT)
    from_alias = None
    if peek().type == TK_AS:
        consume(TK_AS)
        from_alias = consume(TK_IDENT).value

    join_info = None
    if peek().type in (TK_INNER, TK_LEFT, TK_RIGHT):
        join_type = "inner"
        if peek().type == TK_INNER:
            consume(TK_INNER)
        elif peek().type == TK_LEFT:
            consume(TK_LEFT)
            join_type = "left"
            if peek().type == TK_OUTER:
                consume(TK_OUTER)
        elif peek().type == TK_RIGHT:
            consume(TK_RIGHT)
            join_type = "right"
            if peek().type == TK_OUTER:
                consume(TK_OUTER)
        consume(TK_JOIN)
        join_table_token = consume(TK_IDENT)
        join_alias = None
        if peek().type == TK_AS:
            consume(TK_AS)
            join_alias = consume(TK_IDENT).value
        consume(TK_ON)
        join_on = _parse_comparison(peek, consume)
        join_info = {
            "table": join_table_token.value,
            "alias": join_alias,
            "on": join_on,
            "join_type": join_type,
        }

    predicate = None
    if peek().type == TK_WHERE:
        consume(TK_WHERE)
        predicate = _parse_comparison(peek, consume)

    group_by = []
    if peek().type == TK_GROUP:
        consume(TK_GROUP)
        consume(TK_BY)
        group_by.append(consume(TK_IDENT).value)
        while peek().type == TK_COMMA:
            consume(TK_COMMA)
            group_by.append(consume(TK_IDENT).value)

    having = None
    if peek().type == TK_HAVING:
        consume(TK_HAVING)
        having = _parse_comparison(peek, consume)

    order_by = []
    if peek().type == TK_ORDER:
        consume(TK_ORDER)
        consume(TK_BY)
        order_by.append(_parse_order_key(peek, consume))
        while peek().type == TK_COMMA:
            consume(TK_COMMA)
            order_by.append(_parse_order_key(peek, consume))

    limit = None
    if peek().type == TK_LIMIT:
        consume(TK_LIMIT)
        limit_tok = consume(TK_INT_LIT)
        limit = int(limit_tok.value)

    if peek().type == TK_SEMI:
        consume(TK_SEMI)

    if peek().type != TK_EOF:
        t = peek()
        raise ValueError(f"Unexpected token {t.type!r} ({t.value!r}) after statement")

    return {
        "type": "select",
        "distinct": distinct,
        "columns": columns,
        "from": table_token.value,
        "from_alias": from_alias,
        "join": join_info,
        "where": predicate,
        "group_by": group_by,
        "having": having,
        "order_by": order_by,
        "limit": limit,
    }


def _parse_one_select_col(peek, consume):
    """Parse one item in the SELECT list: aggregate call (with optional AS alias) or expression.

    Aggregate calls may carry an explicit AS alias; the alias is stored under the
    key "alias" in the returned func dict.  When no AS is present the key is absent,
    preserving backward-compatible dict equality for existing tests.
    Plain expressions delegate to _parse_select_col_expr.
    """
    t = peek()
    if t.type in _AGG_KEYWORDS:
        func_tok = consume(t.type)
        agg = _parse_agg_call(peek, consume, func_tok)
        if peek().type == TK_AS:
            consume(TK_AS)
            agg = {**agg, "alias": consume(TK_IDENT).value}
        return agg
    return _parse_select_col_expr(peek, consume)


def _parse_agg_call(peek, consume, func_token) -> dict:
    """Parse the argument list of an aggregate function call.

    Expects the opening parenthesis, then either * or a column identifier, then
    the closing parenthesis.  Returns a FuncCall expression dict as defined in
    spec/plan.md: {"type":"func","name":<str>,"args":[<expr>]}.
    """
    consume(TK_LPAREN)
    t = peek()
    if t.type == TK_STAR:
        consume(TK_STAR)
        arg = {"type": "col", "name": "*"}
    elif t.type == TK_IDENT:
        arg = {"type": "col", "name": consume(TK_IDENT).value}
    else:
        raise ValueError(
            f"Expected * or column name inside aggregate call, got {t.type!r} ({t.value!r})"
        )
    consume(TK_RPAREN)
    return {"type": "func", "name": func_token.value.lower(), "args": [arg]}


def _parse_order_key(peek, consume) -> dict:
    """Parse a single ORDER BY key: <column> [ASC|DESC].

    Accepts both bare identifiers and dot-qualified names (table.column).
    Direction defaults to 'asc' when omitted.
    """
    t = peek()
    if t.type == TK_QUALIFIED_IDENT:
        col = consume(TK_QUALIFIED_IDENT).value
    else:
        col = consume(TK_IDENT).value
    direction = "asc"
    if peek().type == TK_ASC:
        consume(TK_ASC)
    elif peek().type == TK_DESC:
        consume(TK_DESC)
        direction = "desc"
    return {"column": col, "direction": direction}


def _parse_expr_atom(peek, consume) -> dict:
    """Parse an atomic expression: column reference, literal, or parenthesised expr.

    Returns an expression dict (col, lit, or recursive binop via subexpression).
    Raises ValueError if no valid atom is found.
    """
    t = peek()
    if t.type == TK_QUALIFIED_IDENT:
        return {"type": "col", "name": consume(TK_QUALIFIED_IDENT).value}
    if t.type == TK_IDENT:
        return {"type": "col", "name": consume(TK_IDENT).value}
    if t.type == TK_INT_LIT:
        return {"type": "lit", "value": int(consume(TK_INT_LIT).value)}
    if t.type == TK_FLOAT_LIT:
        return {"type": "lit", "value": float(consume(TK_FLOAT_LIT).value)}
    if t.type == TK_STRING_LIT:
        return {"type": "lit", "value": consume(TK_STRING_LIT).value}
    if t.type == TK_LPAREN:
        consume(TK_LPAREN)
        expr = _parse_expr_additive(peek, consume)
        consume(TK_RPAREN)
        return expr
    raise ValueError(f"Expected expression, got {t.type!r} ({t.value!r})")


def _parse_expr_multiplicative(peek, consume) -> dict:
    """Parse multiplicative expressions: * and / (higher precedence), left-associative.

    Calls _parse_expr_atom for each operand so that * and / bind tighter than + and -.
    """
    left = _parse_expr_atom(peek, consume)
    while peek().type in (TK_STAR, TK_SLASH):
        op_tok = peek()
        consume(op_tok.type)
        right = _parse_expr_atom(peek, consume)
        op = "*" if op_tok.type == TK_STAR else "/"
        left = {"type": "binop", "op": op, "left": left, "right": right}
    return left


def _parse_expr_additive(peek, consume) -> dict:
    """Parse additive expressions: + and - (lower precedence), left-associative.

    Calls _parse_expr_multiplicative for each operand so that + and - bind looser.
    """
    left = _parse_expr_multiplicative(peek, consume)
    while peek().type in (TK_PLUS, TK_MINUS):
        op_tok = peek()
        consume(op_tok.type)
        right = _parse_expr_multiplicative(peek, consume)
        op = "+" if op_tok.type == TK_PLUS else "-"
        left = {"type": "binop", "op": op, "left": left, "right": right}
    return left


def _parse_select_col_expr(peek, consume):
    """Parse one SELECT column: an arithmetic expression with an optional AS alias.

    Returns a bare string for a plain column reference with no alias (backward-compatible).
    Returns {"expr": <expr_node>, "alias": <str>} when an alias is present or when the
    expression is not a simple column reference (arithmetic, literal, etc.).
    """
    expr = _parse_expr_additive(peek, consume)
    alias = None
    if peek().type == TK_AS:
        consume(TK_AS)
        alias = consume(TK_IDENT).value
    if alias is None and expr["type"] == "col":
        return expr["name"]
    return {"expr": expr, "alias": alias}


def _parse_comparison(peek, consume) -> dict:
    """Parse a WHERE predicate: binary comparison or IN / NOT IN membership test.

    Both sides of a binary comparison are full arithmetic expressions, so
    `age * 2 > 50` is supported.  After parsing the left-hand side the parser
    checks for `IN` or `NOT IN`; if found it consumes the parenthesised value
    list and returns an `in` node.  Otherwise it falls through to the standard
    comparison operator path.

    NOT is consumed optimistically when seen after an expression: in this grammar
    the only valid continuation after NOT is IN, so the parser raises ValueError
    if IN does not follow.

    Only a single predicate is supported (no AND/OR).
    Returns an expression dict as defined in spec/plan.md.
    """
    left = _parse_expr_additive(peek, consume)

    if peek().type == TK_IS:
        consume(TK_IS)
        negated = False
        if peek().type == TK_NOT:
            consume(TK_NOT)
            negated = True
        consume(TK_NULL)
        return {"type": "isnull", "negated": negated, "expr": left}

    if peek().type == TK_NOT:
        consume(TK_NOT)
        if peek().type != TK_IN:
            t = peek()
            raise ValueError(
                f"Expected IN after NOT in predicate, got {t.type!r} ({t.value!r})"
            )
        consume(TK_IN)
        return _parse_in_list(peek, consume, left, negated=True)

    if peek().type == TK_IN:
        consume(TK_IN)
        return _parse_in_list(peek, consume, left, negated=False)

    op_token = peek()
    if op_token.type not in _COMP_OPS:
        raise ValueError(
            f"Expected comparison operator, got {op_token.type!r} ({op_token.value!r})"
        )
    consume(op_token.type)
    op = _COMP_OPS[op_token.type]

    right = _parse_expr_additive(peek, consume)

    return {"type": "binop", "op": op, "left": left, "right": right}


def _parse_in_list(peek, consume, lhs: dict, negated: bool) -> dict:
    """Parse the parenthesised value list of an IN / NOT IN predicate.

    Expects the token stream to be positioned just after the IN keyword.
    Returns an `in` expression node as defined in spec/plan.md:
        {"type": "in", "negated": <bool>, "expr": <lhs>, "values": [<expr>, ...]}
    Values may be any primary expression (literals, column references, arithmetic).
    An empty value list raises ValueError.
    """
    consume(TK_LPAREN)
    values = [_parse_expr_additive(peek, consume)]
    while peek().type == TK_COMMA:
        consume(TK_COMMA)
        values.append(_parse_expr_additive(peek, consume))
    consume(TK_RPAREN)
    return {"type": "in", "negated": negated, "expr": lhs, "values": values}
