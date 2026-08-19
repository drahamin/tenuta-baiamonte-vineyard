from __future__ import annotations


def split_sql_statements(source: str) -> list[str]:
    """Split migration SQL without breaking quoted text or SQL comments."""
    statements: list[str] = []
    buffer: list[str] = []
    quote: str | None = None
    line_comment = False
    block_comment = False
    index = 0

    while index < len(source):
        char = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""

        if line_comment:
            buffer.append(char)
            if char == "\n":
                line_comment = False
            index += 1
            continue

        if block_comment:
            buffer.append(char)
            if char == "*" and following == "/":
                buffer.append(following)
                block_comment = False
                index += 2
            else:
                index += 1
            continue

        if quote:
            buffer.append(char)
            if char == "\\" and following:
                buffer.append(following)
                index += 2
                continue
            if char == quote:
                if following == quote:
                    buffer.append(following)
                    index += 2
                    continue
                quote = None
            index += 1
            continue

        if char in {"'", '"', "`"}:
            quote = char
            buffer.append(char)
            index += 1
            continue
        if char == "-" and following == "-":
            line_comment = True
            buffer.extend((char, following))
            index += 2
            continue
        if char == "/" and following == "*":
            block_comment = True
            buffer.extend((char, following))
            index += 2
            continue
        if char == ";":
            statement = "".join(buffer).strip()
            if statement:
                statements.append(statement)
            buffer.clear()
            index += 1
            continue

        buffer.append(char)
        index += 1

    statement = "".join(buffer).strip()
    if statement:
        statements.append(statement)
    return statements
