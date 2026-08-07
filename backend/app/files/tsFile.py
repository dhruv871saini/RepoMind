from __future__ import annotations

import re

from app.files.base import (
    ParseResult,
    empty_result,
    find_matching_brace,
    line_of,
    slice_lines,
)

_NAMED_IMPORT_RE = re.compile(
    r"""import\s+(?:type\s+)?(?:(\w+)(?:\s*,\s*)?)?(?:\{([^}]+)\})?\s+from\s+['"]([^'"]+)['"]"""
)

_FUNC_RE = re.compile(
    r"""(?:^|\n)\s*(?:export\s+)?(?:async\s+)?function\s*\*?\s+([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{""",
    re.MULTILINE,
)

_ARROW_RE = re.compile(
    r"""(?:^|\n)\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>\s*\{""",
    re.MULTILINE,
)

_METHOD_RE = re.compile(
    r"""(?:^|\n)\s*(?:public|private|protected|static|async|get|set|\s)*\s*([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{""",
    re.MULTILINE,
)

_CLASS_RE = re.compile(
    r"""(?:^|\n)\s*(?:export\s+)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)""",
    re.MULTILINE,
)

_EXPORT_NAME_RE = re.compile(
    r"""export\s+(?:default\s+)?(?:async\s+)?(?:function\*?|class|const|let|var|enum|type|interface)\s+([A-Za-z_$][\w$]*)"""
)


def parse(content: str, file_path: str) -> ParseResult:
    result: ParseResult = empty_result()

    for m in _NAMED_IMPORT_RE.finditer(content):
        default_name, named, raw = m.group(1), m.group(2), m.group(3)
        names: list[str] = []
        if default_name:
            names.append(default_name)
        if named:
            for part in named.split(","):
                part = part.strip()
                if not part:
                    continue
                if " as " in part:
                    part = part.split(" as ")[-1].strip()
                names.append(part)
        if not names:
            names = ["*"]
        result["imports"].append(
            {
                "raw": raw,
                "names": names,
                "is_local": raw.startswith(".") or raw.startswith("/"),
            }
        )

    # side-effect imports: import './x'
    for m in re.finditer(r"""^\s*import\s+['"]([^'"]+)['"]""", content, re.MULTILINE):
        raw = m.group(1)
        if any(i["raw"] == raw for i in result["imports"]):
            continue
        result["imports"].append(
            {
                "raw": raw,
                "names": ["*"],
                "is_local": raw.startswith(".") or raw.startswith("/"),
            }
        )

    for m in _EXPORT_NAME_RE.finditer(content):
        result["exports"].append(m.group(1))

    for m in _CLASS_RE.finditer(content):
        name = m.group(1)
        if name not in result["exports"]:
            result["exports"].append(name)

    seen_spans: set[tuple[int, int]] = set()

    for pattern in (_FUNC_RE, _ARROW_RE):
        for m in pattern.finditer(content):
            name = m.group(1)
            brace_idx = content.find("{", m.end() - 1)
            end_idx = find_matching_brace(content, brace_idx)
            if end_idx is None:
                continue
            start_line = line_of(content, m.start())
            end_line = line_of(content, end_idx)
            span = (start_line, end_line)
            if span in seen_spans:
                continue
            seen_spans.add(span)
            result["functions"].append(
                {
                    "name": name,
                    "start_line": start_line,
                    "end_line": end_line,
                    "content": slice_lines(content, start_line, end_line),
                    "detection_method": "brace_count",
                }
            )
            if name not in result["exports"] and "export" in m.group(0):
                result["exports"].append(name)

    # class methods (skip constructor-only noise by including all)
    for cm in _CLASS_RE.finditer(content):
        class_name = cm.group(1)
        brace_idx = content.find("{", cm.end())
        class_end = find_matching_brace(content, brace_idx)
        if class_end is None:
            continue
        body = content[brace_idx : class_end + 1]
        offset = brace_idx
        for mm in _METHOD_RE.finditer(body):
            method = mm.group(1)
            if method in {"if", "for", "while", "switch", "catch", "function"}:
                continue
            local_brace = body.find("{", mm.end() - 1)
            if local_brace < 0:
                continue
            abs_brace = offset + local_brace
            end_idx = find_matching_brace(content, abs_brace)
            if end_idx is None:
                continue
            start_line = line_of(content, offset + mm.start())
            end_line = line_of(content, end_idx)
            span = (start_line, end_line)
            if span in seen_spans:
                continue
            seen_spans.add(span)
            result["functions"].append(
                {
                    "name": f"{class_name}.{method}",
                    "start_line": start_line,
                    "end_line": end_line,
                    "content": slice_lines(content, start_line, end_line),
                    "detection_method": "brace_count",
                }
            )

    seen = set()
    result["exports"] = [e for e in result["exports"] if not (e in seen or seen.add(e))]
    return result
