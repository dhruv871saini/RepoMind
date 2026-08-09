from __future__ import annotations

import re
from app.files.base import (
    ParseResult, empty_result,
    find_matching_brace, line_of, slice_lines,
)

# ── Import detection ───────────────────────────────────────────────────────────
_IMPORT_RE = re.compile(
    r"""import\s+(?:type\s+)?                  # import / import type
        (?:
            (?P<default>[\w$]+)                # default import name
            (?:\s*,\s*)?                       # optional comma
        )?
        (?:\{(?P<named>[^}]+)\})?              # { named, imports }
        (?:\*\s+as\s+(?P<namespace>[\w$]+))?   # * as namespace
        \s+from\s+['"](?P<path>[^'"]+)['"]     # from 'path'
    """,
    re.VERBOSE | re.MULTILINE,
)

_SIDE_EFFECT_IMPORT_RE = re.compile(
    r"""^\s*import\s+['"]([^'"]+)['"]""",
    re.MULTILINE,
)

# ── Export detection ───────────────────────────────────────────────────────────
_EXPORT_NAME_RE = re.compile(
    r"""export\s+(?:default\s+)?
        (?:async\s+)?
        (?:function\*?|class|const|let|var|enum|type|interface)
        \s+([\w$]+)
    """,
    re.VERBOSE,
)

_EXPORT_BLOCK_RE = re.compile(
    r"""export\s*\{([^}]+)\}""",
    re.MULTILINE,
)

# ── Function/class START detection (Phase 1) ──────────────────────────────────
# IMPORTANT: these patterns only detect the keyword + name.
# They deliberately do NOT try to match parameters — that's what broke before.
# We find the name, then scan forward for the opening { ourselves.

_FUNC_NAME_RE = re.compile(
    r"""(?:^|\n)
        [ \t]*                              # optional indentation
        (?:export\s+)?                      # optional export
        (?:default\s+)?                     # optional default
        (?:async\s+)?                       # optional async
        function\s*\*?\s*                   # function keyword
        ([\w$]+)                            # ← CAPTURE: function name
    """,
    re.VERBOSE | re.MULTILINE,
)

_ARROW_NAME_RE = re.compile(
    r"""(?:^|\n)
        [ \t]*                              # optional indentation
        (?:export\s+)?                      # optional export
        (?:const|let|var)\s+               # declaration keyword
        ([\w$]+)                            # ← CAPTURE: variable name
        \s*=\s*                             # assignment
        (?:async\s+)?                       # optional async
        (?:
            \([^)]*\)\s*=>                  # short param list => (for simple cases)
          | \(                              # or just opening paren (multiline)
        )
    """,
    re.VERBOSE | re.MULTILINE,
)

_CLASS_NAME_RE = re.compile(
    r"""(?:^|\n)
        [ \t]*
        (?:export\s+)?
        (?:abstract\s+)?
        class\s+([\w$]+)                    # ← CAPTURE: class name
    """,
    re.VERBOSE | re.MULTILINE,
)

_METHOD_NAME_RE = re.compile(
    r"""(?:^|\n)
        [ \t]+                              # MUST be indented (inside a class)
        (?:public|private|protected|static|async|get|set|\s)*
        ([\w$]+)                            # ← CAPTURE: method name
        \s*\(                               # opening paren
    """,
    re.VERBOSE | re.MULTILINE,
)

# Keywords that look like methods but aren't
_NOT_A_METHOD = {
    "if", "for", "while", "switch", "catch", "do", "else",
    "return", "throw", "new", "typeof", "instanceof", "void",
    "delete", "await", "yield", "case", "break", "continue",
    "import", "export", "class", "function", "var", "let", "const",
    "try", "finally", "debugger", "with",
}


def _find_opening_brace(content: str, start_idx: int) -> int:
    """
    Scan forward from start_idx to find the first '{' that opens
    a function body. Skips over parameter lists entirely.

    This is the key fix: instead of matching params with regex,
    we just scan forward until we find the opening brace.
    Works for any parameter syntax: multiline, nested objects, generics.
    """
    i = start_idx
    paren_depth = 0
    angle_depth = 0   # for TypeScript generics <T>
    in_str = None
    escape = False

    while i < len(content):
        ch = content[i]

        # Handle string literals — don't misinterpret braces inside strings
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == in_str:
                in_str = None
            i += 1
            continue

        if ch in ('"', "'", "`"):
            in_str = ch
        elif ch == "(":
            paren_depth += 1
        elif ch == ")":
            paren_depth -= 1
        elif ch == "<" and paren_depth == 0:
            angle_depth += 1
        elif ch == ">" and angle_depth > 0:
            angle_depth -= 1
        elif ch == "{" and paren_depth == 0 and angle_depth == 0:
            return i   # ← this is the opening brace of the function body

        i += 1

    return -1   # no opening brace found


def parse(content: str, file_path: str) -> ParseResult:
    result: ParseResult = empty_result()

    # ── 1. Imports ─────────────────────────────────────────────────────────
    seen_paths: set[str] = set()

    for m in _IMPORT_RE.finditer(content):
        path = m.group("path")
        if path in seen_paths:
            continue
        seen_paths.add(path)

        names: list[str] = []
        if m.group("default"):
            names.append(m.group("default"))
        if m.group("namespace"):
            names.append(m.group("namespace"))
        if m.group("named"):
            for part in m.group("named").split(","):
                part = part.strip()
                if not part:
                    continue
                # handle: { original as alias } → keep alias
                if " as " in part:
                    part = part.split(" as ")[-1].strip()
                if part:
                    names.append(part)

        result["imports"].append({
            "raw":      path,
            "names":    names or ["*"],
            "is_local": path.startswith(".") or path.startswith("/"),
        })

    # Side-effect imports: import './polyfill'
    for m in _SIDE_EFFECT_IMPORT_RE.finditer(content):
        path = m.group(1)
        if path not in seen_paths:
            seen_paths.add(path)
            result["imports"].append({
                "raw":      path,
                "names":    ["*"],
                "is_local": path.startswith("."),
            })

    # ── 2. Exports ─────────────────────────────────────────────────────────
    seen_exports: set[str] = set()

    for m in _EXPORT_NAME_RE.finditer(content):
        name = m.group(1)
        if name and name not in seen_exports:
            seen_exports.add(name)
            result["exports"].append(name)

    for m in _EXPORT_BLOCK_RE.finditer(content):
        for part in m.group(1).split(","):
            part = part.strip()
            if not part:
                continue
            # export { foo as bar } → export bar
            name = part.split(" as ")[-1].strip()
            if name and name not in seen_exports:
                seen_exports.add(name)
                result["exports"].append(name)

    # ── 3. Functions (two-phase detection) ─────────────────────────────────
    seen_spans: set[tuple[int, int]] = set()

    def _extract(name: str, search_from: int, detection_method: str) -> bool:
        """
        Phase 2: given we found function name at search_from,
        scan forward to find { then use find_matching_brace for }.
        Returns True if chunk was successfully extracted.
        """
        brace_open = _find_opening_brace(content, search_from)
        if brace_open < 0:
            return False

        brace_close = find_matching_brace(content, brace_open)
        if brace_close is None:
            return False

        start_line = line_of(content, search_from)
        end_line   = line_of(content, brace_close)
        span = (start_line, end_line)

        if span in seen_spans:
            return False
        seen_spans.add(span)

        result["functions"].append({
            "name":             name,
            "start_line":       start_line,
            "end_line":         end_line,
            "content":          slice_lines(content, start_line, end_line),
            "detection_method": detection_method,
        })
        return True

    # Named functions: function foo(...) { }
    for m in _FUNC_NAME_RE.finditer(content):
        name = m.group(1)
        if name in _NOT_A_METHOD:
            continue
        _extract(name, m.end(), "brace_count")

        # Track exports from inline export function
        if "export" in m.group(0) and name not in seen_exports:
            seen_exports.add(name)
            result["exports"].append(name)

    # Arrow functions: const foo = async (...) => { }
    for m in _ARROW_NAME_RE.finditer(content):
        name = m.group(1)
        if name in _NOT_A_METHOD:
            continue
        # Search for => then { after it
        arrow_idx = content.find("=>", m.end())
        if arrow_idx < 0:
            # Might be multiline arrow — scan forward for {
            _extract(name, m.end(), "brace_count")
        else:
            _extract(name, arrow_idx + 2, "brace_count")

    # ── 4. Classes and their methods ───────────────────────────────────────
    for cm in _CLASS_NAME_RE.finditer(content):
        class_name = cm.group(1)

        # Find the class body
        class_brace_open = _find_opening_brace(content, cm.end())
        if class_brace_open < 0:
            continue

        class_brace_close = find_matching_brace(content, class_brace_open)
        if class_brace_close is None:
            continue

        # Track class as export
        if class_name not in seen_exports:
            seen_exports.add(class_name)
            result["exports"].append(class_name)

        # Extract methods from inside the class body only
        class_body = content[class_brace_open : class_brace_close + 1]
        body_offset = class_brace_open

        for mm in _METHOD_NAME_RE.finditer(class_body):
            method_name = mm.group(1)

            # Skip keywords, constructors named after class, and private (__)
            if method_name in _NOT_A_METHOD:
                continue
            if method_name.startswith("__"):
                continue

            # Phase 2: find method body brace
            abs_search_start = body_offset + mm.end()
            method_brace_open = _find_opening_brace(content, abs_search_start)
            if method_brace_open < 0:
                continue

            # Make sure method brace is still inside class body
            if method_brace_open > class_brace_close:
                continue

            method_brace_close = find_matching_brace(content, method_brace_open)
            if method_brace_close is None:
                continue

            start_line = line_of(content, body_offset + mm.start())
            end_line   = line_of(content, method_brace_close)
            span = (start_line, end_line)

            if span in seen_spans:
                continue
            seen_spans.add(span)

            result["functions"].append({
                "name":             f"{class_name}.{method_name}",
                "start_line":       start_line,
                "end_line":         end_line,
                "content":          slice_lines(content, start_line, end_line),
                "detection_method": "brace_count",
            })

    # De-duplicate exports preserving order
    seen = set()
    result["exports"] = [e for e in result["exports"]
                         if not (e in seen or seen.add(e))]

    return result