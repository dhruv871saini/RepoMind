from __future__ import annotations

import ast
from pathlib import Path

from app.files.base import ParseResult, empty_result, slice_lines


def parse(content: str, file_path: str) -> ParseResult:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return empty_result()

    result: ParseResult = empty_result()
    all_names: list[str] | None = None

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result["exports"].append(node.name)
            result["functions"].append(_fn(content, node.name, node))
        elif isinstance(node, ast.ClassDef):
            result["exports"].append(node.name)
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    result["functions"].append(
                        _fn(content, f"{node.name}.{item.name}", item)
                    )
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    if isinstance(node.value, (ast.List, ast.Tuple)):
                        all_names = [
                            elt.value
                            for elt in node.value.elts
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                        ]
        elif isinstance(node, ast.Import):
            for alias in node.names:
                result["imports"].append(
                    {
                        "raw": alias.name,
                        "names": [alias.asname or alias.name.split(".")[-1]],
                        "is_local": _looks_local(alias.name, file_path),
                    }
                )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            prefix = "." * node.level
            raw = f"{prefix}{module}" if module or node.level else ""
            names = []
            for alias in node.names:
                if alias.name == "*":
                    names.append("*")
                else:
                    names.append(alias.asname or alias.name)
            if raw:
                result["imports"].append(
                    {
                        "raw": raw,
                        "names": names,
                        "is_local": node.level > 0 or _looks_local(module, file_path),
                    }
                )

    if all_names is not None:
        result["exports"] = all_names

    # de-dupe exports preserving order
    seen = set()
    result["exports"] = [e for e in result["exports"] if not (e in seen or seen.add(e))]
    return result


def _fn(content: str, name: str, node: ast.AST) -> dict:
    start = getattr(node, "lineno", 1)
    end = getattr(node, "end_lineno", start) or start
    return {
        "name": name,
        "start_line": start,
        "end_line": end,
        "content": slice_lines(content, start, end),
        "detection_method": "ast",
    }


def _looks_local(module: str, file_path: str) -> bool:
    if not module:
        return False
    top = module.split(".")[0]
    # treat first path segment as possible package root
    root = Path(file_path).parts[0] if Path(file_path).parts else ""
    return top == root or top in {"app", "src", "lib", "backend", "frontend"}
