from frontend.lexer import (
    tokenize,
    TK_SELECT,
    TK_FROM,
    TK_WHERE,
    TK_STAR,
    TK_IDENT,
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
)

_COMP_OPS = {TK_EQ: "=", TK_NEQ: "!=", TK_LT: "<", TK_LTE: "<=", TK_GT: ">", TK_GTE: ">="}

_AGG_KEYWORDS = {TK_COUNT, TK_SUM, TK_AVG, TK_MIN, TK_MAX}


def parse(sql: str) -> dict:
    """Parse a SQL string and return an AST dict.

    Only SELECT statements are supported. Returns:
        {
            "type": "select",
            "columns": ["*"] | ["col1", ...],
            "from": "<table_name>",
            "where": <predicate_expr> | None,
            "order_by": [{"column": "<col>", "direction": "asc"|"desc"}, ...],
            "limit": <int> | None,
        }

    A predicate_expr is a BinOp dict from the expression sub-language defined in
    spec/plan.md: {"type":"binop","op":"=","left":<expr>,"right":<expr>}.

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

    t = peek()
    if t.type == TK_STAR:
        consume(TK_STAR)
        columns = ["*"]
    elif t.type in _AGG_KEYWORDS:
        func_tok = consume(t.type)
        columns = [_parse_agg_call(peek, consume, func_tok)]
        while peek().type == TK_COMMA:
            consume(TK_COMMA)
            next_t = peek()
            if next_t.type not in _AGG_KEYWORDS:
                raise ValueError(
                    "Cannot mix aggregate functions and plain columns in SELECT list"
                )
            func_tok2 = consume(next_t.type)
            columns.append(_parse_agg_call(peek, consume, func_tok2))
    elif t.type == TK_IDENT:
        columns = [consume(TK_IDENT).value]
        while peek().type == TK_COMMA:
            consume(TK_COMMA)
            next_t = peek()
            if next_t.type in _AGG_KEYWORDS:
                raise ValueError(
                    "Cannot mix plain columns and aggregate functions in SELECT list"
                )
            columns.append(consume(TK_IDENT).value)
    else:
        raise ValueError(f"Expected *, aggregate function, or column name, got {t.type!r} ({t.value!r})")

    consume(TK_FROM)
    table_token = consume(TK_IDENT)

    predicate = None
    if peek().type == TK_WHERE:
        consume(TK_WHERE)
        predicate = _parse_comparison(peek, consume)

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
        "columns": columns,
        "from": table_token.value,
        "where": predicate,
        "order_by": order_by,
        "limit": limit,
    }


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

    Direction defaults to 'asc' when omitted.
    """
    col = consume(TK_IDENT).value
    direction = "asc"
    if peek().type == TK_ASC:
        consume(TK_ASC)
    elif peek().type == TK_DESC:
        consume(TK_DESC)
        direction = "desc"
    return {"column": col, "direction": direction}


def _parse_comparison(peek, consume) -> dict:
    """Parse a single comparison: <identifier> <comp_op> <literal>.

    Returns a BinOp expression dict as defined in spec/plan.md.
    Only column-op-literal form is supported (compound AND/OR is out of scope).
    """
    col_token = consume(TK_IDENT)
    left = {"type": "col", "name": col_token.value}

    op_token = peek()
    if op_token.type not in _COMP_OPS:
        raise ValueError(
            f"Expected comparison operator, got {op_token.type!r} ({op_token.value!r})"
        )
    consume(op_token.type)
    op = _COMP_OPS[op_token.type]

    lit_token = peek()
    if lit_token.type == TK_STRING_LIT:
        consume(TK_STRING_LIT)
        right = {"type": "lit", "value": lit_token.value}
    elif lit_token.type == TK_INT_LIT:
        consume(TK_INT_LIT)
        right = {"type": "lit", "value": int(lit_token.value)}
    elif lit_token.type == TK_FLOAT_LIT:
        consume(TK_FLOAT_LIT)
        right = {"type": "lit", "value": float(lit_token.value)}
    else:
        raise ValueError(
            f"Expected a literal value, got {lit_token.type!r} ({lit_token.value!r})"
        )

    return {"type": "binop", "op": op, "left": left, "right": right}
