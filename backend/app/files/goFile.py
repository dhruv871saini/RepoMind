from __future__ import annotations

import re

from app.files.base import (
    ParseResult,
    empty_result,
    find_matching_brace,
    line_of,
    slice_lines,
)

_IMPORT_BLOCK_RE = re.compile(r"import\s*\((.*?)\)", re.DOTALL)
_IMPORT_SINGLE_RE = re.compile(r'import\s+"([^"]+)"')
_FUNC_RE = re.compile(
    r"(?:^|\n)func\s+(?:\([^)]+\)\s+)?([A-Za-z_][\w]*)\s*\([^)]*\)[^{]*\{",
    re.MULTILINE,
)


def parse(content: str, file_path: str) -> ParseResult:
    result: ParseResult = empty_result()

    for m in _IMPORT_BLOCK_RE.finditer(content):
        block = m.group(1)
        for path_m in re.finditer(r'"([^"]+)"', block):
            raw = path_m.group(1)
            result["imports"].append(
                {
                    "raw": raw,
                    "names": ["*"],
                    "is_local": raw.startswith("."),
                }
            )

    for m in _IMPORT_SINGLE_RE.finditer(content):
        raw = m.group(1)
        if any(i["raw"] == raw for i in result["imports"]):
            continue
        result["imports"].append(
            {
                "raw": raw,
                "names": ["*"],
                "is_local": raw.startswith("."),
            }
        )

    seen_spans: set[tuple[int, int]] = set()
    for m in _FUNC_RE.finditer(content):
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
        if name and name[0].isupper():
            result["exports"].append(name)

    seen = set()
    result["exports"] = [e for e in result["exports"] if not (e in seen or seen.add(e))]
    return result
