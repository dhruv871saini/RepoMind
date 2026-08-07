from __future__ import annotations

from pathlib import Path
from typing import Callable

from app.files import goFile, javaFile, pythonFile, tsFile
from app.files.base import ParseResult, empty_result

ParserFn = Callable[[str, str], ParseResult]

_EXTENSION_MAP: dict[str, tuple[str, ParserFn]] = {
    ".py": ("python", pythonFile.parse),
    ".ts": ("typescript", tsFile.parse),
    ".tsx": ("typescript", tsFile.parse),
    ".js": ("javascript", tsFile.parse),
    ".jsx": ("javascript", tsFile.parse),
    ".mjs": ("javascript", tsFile.parse),
    ".cjs": ("javascript", tsFile.parse),
    ".go": ("go", goFile.parse),
    ".java": ("java", javaFile.parse),
}


def get_parser(file_path: str) -> tuple[str, ParserFn] | None:
    ext = Path(file_path).suffix.lower()
    return _EXTENSION_MAP.get(ext)


def parse_file(content: str, file_path: str) -> tuple[str | None, ParseResult]:
    info = get_parser(file_path)
    if info is None:
        return None, empty_result()
    lang, parser = info
    return lang, parser(content, file_path)
