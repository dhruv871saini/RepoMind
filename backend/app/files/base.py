from __future__ import annotations

from typing import TypedDict


class ImportInfo(TypedDict):
    raw: str
    names: list[str]
    is_local: bool


class FunctionInfo(TypedDict):
    name: str
    start_line: int
    end_line: int
    content: str
    detection_method: str


class ParseResult(TypedDict):
    exports: list[str]
    imports: list[ImportInfo]
    functions: list[FunctionInfo]


def empty_result() -> ParseResult:
    return {"exports": [], "imports": [], "functions": []}


def slice_lines(content: str, start_line: int, end_line: int) -> str:
    lines = content.splitlines()
    return "\n".join(lines[start_line - 1 : end_line])


def find_matching_brace(content: str, open_idx: int) -> int | None:
    """Return index of closing '}' matching '{' at open_idx, or None."""
    if open_idx < 0 or open_idx >= len(content) or content[open_idx] != "{":
        return None

    depth = 0
    in_str = None
    escape = False
    i = open_idx
    while i < len(content):
        ch = content[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == in_str:
                in_str = None
        else:
            if ch in ('"', "'", "`"):
                in_str = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return None


def line_of(content: str, idx: int) -> int:
    return content.count("\n", 0, idx) + 1
