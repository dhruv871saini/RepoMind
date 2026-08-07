from __future__ import annotations

import re

from app.files.base import (
    ParseResult,
    empty_result,
    find_matching_brace,
    line_of,
    slice_lines,
)

_IMPORT_RE = re.compile(r"^\s*import\s+([\w.]+)\s*;", re.MULTILINE)
_CLASS_RE = re.compile(
    r"(?:^|\n)\s*(?:public|protected|private|abstract|final|\s)*\s*(?:class|interface|enum)\s+([A-Za-z_][\w]*)",
    re.MULTILINE,
)
_METHOD_RE = re.compile(
    r"(?:^|\n)\s*(?:public|protected|private|static|final|synchronized|abstract|native|default|\s)*"
    r"(?:<[^>]+>\s*)?"
    r"(?:[\w.\[\]]+)\s+([A-Za-z_][\w]*)\s*\([^;]*\)\s*(?:throws\s+[\w.,\s]+)?\s*\{",
    re.MULTILINE,
)


def parse(content: str, file_path: str) -> ParseResult:
    result: ParseResult = empty_result()

    for m in _IMPORT_RE.finditer(content):
        raw = m.group(1)
        result["imports"].append(
            {
                "raw": raw,
                "names": [raw.split(".")[-1]],
                "is_local": not raw.startswith("java.") and not raw.startswith("javax."),
            }
        )

    for m in _CLASS_RE.finditer(content):
        result["exports"].append(m.group(1))

    seen_spans: set[tuple[int, int]] = set()
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
            if method == class_name:
                method = "<init>"
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
