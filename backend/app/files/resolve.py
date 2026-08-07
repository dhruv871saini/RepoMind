from __future__ import annotations

from pathlib import PurePosixPath


def resolve_import(
    raw: str,
    source_file: str,
    file_id_map: dict,
    lang: str,
) -> str | None:
    """Map an import string to a key in file_id_map, or None if unresolved."""
    if lang == "python":
        candidates = _python_candidates(raw, source_file)
    elif lang in {"typescript", "javascript"}:
        candidates = _js_candidates(raw, source_file)
    elif lang == "go":
        candidates = _go_candidates(raw, source_file)
    elif lang == "java":
        candidates = _java_candidates(raw)
    else:
        return None

    normalized_map = {_norm(k): k for k in file_id_map}
    for cand in candidates:
        key = _norm(cand)
        if key in normalized_map:
            return normalized_map[key]

    # Go packages often import a directory; pick any .go file under it
    if lang == "go":
        for cand in candidates:
            prefix = _norm(cand).rstrip("/") + "/"
            for key, original in normalized_map.items():
                if key.startswith(prefix) and key.endswith(".go"):
                    return original

    return None


def _norm(path: str) -> str:
    return str(PurePosixPath(path.replace("\\", "/")))


def _python_candidates(raw: str, source_file: str) -> list[str]:
    src = PurePosixPath(source_file)
    out: list[PurePosixPath] = []

    if raw.startswith("."):
        level = 0
        while level < len(raw) and raw[level] == ".":
            level += 1
        module = raw[level:]
        base = src.parent
        for _ in range(max(level - 1, 0)):
            base = base.parent
        if module:
            target = base / PurePosixPath(*module.split("."))
        else:
            target = base
        out.extend(_py_files(target))
    else:
        parts = PurePosixPath(*raw.split("."))
        out.extend(_py_files(parts))
        if src.parts:
            out.extend(_py_files(PurePosixPath(src.parts[0]) / parts))

    return [str(p) for p in out]


def _py_files(base: PurePosixPath) -> list[PurePosixPath]:
    return [
        PurePosixPath(f"{base}.py"),
        base / "__init__.py",
    ]


def _js_candidates(raw: str, source_file: str) -> list[str]:
    if not (raw.startswith(".") or raw.startswith("/")):
        return []

    src_dir = PurePosixPath(source_file).parent
    joined = (src_dir / raw)
    target = PurePosixPath(_norm(str(joined)))
    exts = [".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"]
    out: list[str] = []

    if target.suffix in exts:
        out.append(str(target))
    else:
        for ext in exts:
            out.append(f"{target}{ext}")
        for ext in exts:
            out.append(str(target / f"index{ext}"))

    return out


def _go_candidates(raw: str, source_file: str) -> list[str]:
    if not raw.startswith("."):
        return []
    src_dir = PurePosixPath(source_file).parent
    target = PurePosixPath(_norm(str(src_dir / raw)))
    return [f"{target}.go", str(target)]


def _java_candidates(raw: str) -> list[str]:
    path = PurePosixPath(*raw.split("."))
    return [
        f"{path}.java",
        f"src/main/java/{path}.java",
    ]
