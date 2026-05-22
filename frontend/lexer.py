from dataclasses import dataclass

TK_SELECT = "SELECT"
TK_FROM = "FROM"
TK_STAR = "STAR"
TK_IDENT = "IDENT"
TK_SEMI = "SEMI"
TK_COMMA = "COMMA"
TK_EOF = "EOF"

_KEYWORDS = {"SELECT": TK_SELECT, "FROM": TK_FROM}


@dataclass
class Token:
    type: str
    value: str


def tokenize(sql: str) -> list[Token]:
    """Convert a SQL string into a flat list of tokens.

    Recognised tokens: SELECT, FROM (case-insensitive), *, ;, bare identifiers.
    Whitespace is silently consumed. Unknown characters raise ValueError.
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
