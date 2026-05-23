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
    TK_PLUS,
    TK_MINUS,
    TK_SLASH,
    TK_AS,
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
            "order_by": [{"column": "<col>", "direction": "asc"|"desc"}, ...],
            "limit": <int> | None,
        }

    Column descriptors in the SELECT list are one of:
      - a bare string (backward-compatible plain column reference, no alias)
      - {"expr": <expr_node>, "alias": <str>} for arithmetic or aliased columns

    A predicate_expr is a BinOp dict: {"type":"binop","op":"...","left":<expr>,"right":<expr>}.
    Arithmetic BinOps use ops "+", "-", "*", "/" and may appear in WHERE and SELECT.

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
    else:
        columns = [_parse_select_col_expr(peek, consume)]
        while peek().type == TK_COMMA:
            consume(TK_COMMA)
            next_t = peek()
            if next_t.type in _AGG_KEYWORDS:
                raise ValueError(
                    "Cannot mix plain columns and aggregate functions in SELECT list"
                )
            columns.append(_parse_select_col_expr(peek, consume))

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


def _parse_expr_atom(peek, consume) -> dict:
    """Parse an atomic expression: column reference, literal, or parenthesised expr.

    Returns an expression dict (col, lit, or recursive binop via subexpression).
    Raises ValueError if no valid atom is found.
    """
    t = peek()
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
    """Parse a WHERE predicate: <expr> <comp_op> <expr>.

    Both sides are full arithmetic expressions, so `age * 2 > 50` is supported.
    Only a single comparison is supported (no AND/OR).
    Returns a BinOp expression dict as defined in spec/plan.md.
    """
    left = _parse_expr_additive(peek, consume)

    op_token = peek()
    if op_token.type not in _COMP_OPS:
        raise ValueError(
            f"Expected comparison operator, got {op_token.type!r} ({op_token.value!r})"
        )
    consume(op_token.type)
    op = _COMP_OPS[op_token.type]

    right = _parse_expr_additive(peek, consume)

    return {"type": "binop", "op": op, "left": left, "right": right}
