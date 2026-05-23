from dataclasses import dataclass

TK_SELECT = "SELECT"
TK_FROM = "FROM"
TK_WHERE = "WHERE"
TK_STAR = "STAR"
TK_IDENT = "IDENT"
TK_SEMI = "SEMI"
TK_COMMA = "COMMA"
TK_EOF = "EOF"

TK_EQ = "EQ"
TK_NEQ = "NEQ"
TK_LT = "LT"
TK_LTE = "LTE"
TK_GT = "GT"
TK_GTE = "GTE"

TK_STRING_LIT = "STRING_LIT"
TK_INT_LIT = "INT_LIT"
TK_FLOAT_LIT = "FLOAT_LIT"

_KEYWORDS = {"SELECT": TK_SELECT, "FROM": TK_FROM, "WHERE": TK_WHERE}


@dataclass
class Token:
    type: str
    value: str


def tokenize(sql: str) -> list[Token]:
    """Convert a SQL string into a flat list of tokens.

    Recognised tokens: SELECT, FROM, WHERE (case-insensitive), *, ;, ,, bare
    identifiers, comparison operators (= != < <= > >=), single-quoted string
    literals, and integer/float numeric literals. Whitespace is silently
    consumed. Unknown characters raise ValueError.
    """
    tokens: list[Token] = []
    i = 0
    while i < len(sql):
        c = sql[i]
        if c.isspace():
            i += 1
        elif c == "*":
            tokens.append(Token(TK_STAR, "*"))
            i += 1
        elif c == ";":
            tokens.append(Token(TK_SEMI, ";"))
            i += 1
        elif c == ",":
            tokens.append(Token(TK_COMMA, ","))
            i += 1
        elif c == "=":
            tokens.append(Token(TK_EQ, "="))
            i += 1
        elif c == "!":
            if i + 1 < len(sql) and sql[i + 1] == "=":
                tokens.append(Token(TK_NEQ, "!="))
                i += 2
            else:
                raise ValueError(f"Unexpected character {c!r} at position {i}")
        elif c == "<":
            if i + 1 < len(sql) and sql[i + 1] == "=":
                tokens.append(Token(TK_LTE, "<="))
                i += 2
            else:
                tokens.append(Token(TK_LT, "<"))
                i += 1
        elif c == ">":
            if i + 1 < len(sql) and sql[i + 1] == "=":
                tokens.append(Token(TK_GTE, ">="))
                i += 2
            else:
                tokens.append(Token(TK_GT, ">"))
                i += 1
        elif c == "'":
            j = i + 1
            while j < len(sql) and sql[j] != "'":
                j += 1
            if j >= len(sql):
                raise ValueError(f"Unterminated string literal starting at position {i}")
            tokens.append(Token(TK_STRING_LIT, sql[i + 1 : j]))
            i = j + 1
        elif c.isdigit() or (c == "-" and i + 1 < len(sql) and sql[i + 1].isdigit()):
            j = i
            if sql[j] == "-":
                j += 1
            while j < len(sql) and sql[j].isdigit():
                j += 1
            if j < len(sql) and sql[j] == "." and j + 1 < len(sql) and sql[j + 1].isdigit():
                j += 1
                while j < len(sql) and sql[j].isdigit():
                    j += 1
                tokens.append(Token(TK_FLOAT_LIT, sql[i:j]))
            else:
                tokens.append(Token(TK_INT_LIT, sql[i:j]))
            i = j
        elif c.isalpha() or c == "_":
            j = i
            while j < len(sql) and (sql[j].isalnum() or sql[j] == "_"):
                j += 1
            word = sql[i:j]
            tok_type = _KEYWORDS.get(word.upper(), TK_IDENT)
            tokens.append(Token(tok_type, word))
            i = j
        else:
            raise ValueError(f"Unexpected character {c!r} at position {i}")
    tokens.append(Token(TK_EOF, ""))
    return tokens
