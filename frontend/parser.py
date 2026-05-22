from frontend.lexer import tokenize, TK_SELECT, TK_FROM, TK_STAR, TK_IDENT, TK_SEMI, TK_COMMA, TK_EOF


def parse(sql: str) -> dict:
    """Parse a SQL string and return an AST dict.

    Only SELECT statements are supported. Returns:
        {"type": "select", "columns": ["*"], "from": "<table_name>"}
      or
        {"type": "select", "columns": ["col1", "col2", ...], "from": "<table_name>"}

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
    elif t.type == TK_IDENT:
        columns = [consume(TK_IDENT).value]
        while peek().type == TK_COMMA:
            consume(TK_COMMA)
            columns.append(consume(TK_IDENT).value)
    else:
        raise ValueError(f"Expected * or column name, got {t.type!r} ({t.value!r})")

    consume(TK_FROM)
    table_token = consume(TK_IDENT)

    if peek().type == TK_SEMI:
        consume(TK_SEMI)

    if peek().type != TK_EOF:
        t = peek()
        raise ValueError(f"Unexpected token {t.type!r} ({t.value!r}) after statement")

    return {"type": "select", "columns": columns, "from": table_token.value}
