from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy import delete

from app.db.models import Chunk, File, FileRelationship, Repository
from app.files.dispatch import parse_file
from app.files.resolve import resolve_import
from app.service.chroma import reset_collection, store_chunks
from app.service.embed import (
    MAX_EMBED_CHARS,
    OVERLAP_CHARS,
    embed_texts,
    split_for_embed,
)

EMBED_BATCH = 10


def _line_range_for_slice(
    full: str,
    start_char: int,
    end_char: int,
    *,
    base_start_line: int,
) -> tuple[int, int]:
    """Map a char slice inside a function body to absolute file line numbers."""
    start_char = max(0, min(start_char, len(full)))
    end_char = max(start_char, min(end_char, len(full)))
    lines_before = full.count("\n", 0, start_char)
    lines_in_slice = full.count("\n", start_char, end_char)
    start_line = base_start_line + lines_before
    end_line = start_line + lines_in_slice
    return start_line, end_line


class Pass2Scanner:
    """
    Pass 2: parse files → exports/imports/function chunks → relationships → embed.
    """

    def __init__(self, repo_id: str, repo_path: str, db_session):
        self.repo_id = repo_id
        self.repo_path = Path(repo_path)
        self.db = db_session

    def parse_and_chunks(self, file_id_map: dict) -> dict:
        file_id_map = {str(k): v for k, v in file_id_map.items()}

        self._clear_previous()

        failed_files: list[str] = []
        pending_edges: list[dict] = []
        chroma_batch: list[dict] = []
        chunks_created = 0
        chunks_embedded = 0

        files = self.db.query(File).filter(File.repo_id == self.repo_id).all()

        for file_record in files:
            file_path = file_record.file_path
            full_path = self.repo_path / file_path

            content = self._read_file(full_path)
            if content is None:
                failed_files.append(file_path)
                continue

            lang, parsed = parse_file(content, file_path)
            if lang is None:
                continue

            file_record.exports = parsed["exports"] or []

            for fn in parsed["functions"]:
                parts = split_for_embed(fn["content"])
                if len(parts) > 1:
                    print(
                        f"[chunk] split {file_path}::{fn['name']} "
                        f"into {len(parts)} parts ({len(fn['content'])} chars)"
                    )

                # Track char offset so each part gets correct line numbers.
                char_offset = 0
                full = fn["content"] or ""

                for part_idx, part in enumerate(parts):
                    chunk_uuid = str(uuid.uuid4())
                    detection = fn["detection_method"]
                    if len(parts) > 1:
                        detection = f"{detection}:part{part_idx + 1}/{len(parts)}"

                    # Locate this part in the full function (overlap-aware).
                    found_at = full.find(part, max(0, char_offset - OVERLAP_CHARS))
                    if found_at < 0:
                        found_at = char_offset
                    part_start_line, part_end_line = _line_range_for_slice(
                        full,
                        found_at,
                        found_at + len(part),
                        base_start_line=fn["start_line"],
                    )
                    char_offset = found_at + max(1, len(part) - OVERLAP_CHARS)

                    self.db.add(
                        Chunk(
                            repo_id=self.repo_id,
                            file_id=file_record.id,
                            chunk_id=chunk_uuid,
                            function_name=fn["name"],
                            start_line=part_start_line,
                            end_line=part_end_line,
                            chunk_type="function",
                            detection_method=detection,
                        )
                    )
                    chunks_created += 1
                    # Store the same text we embed — every part is embedded, nothing dropped.
                    chroma_batch.append(
                        {
                            "id": chunk_uuid,
                            "content": part,
                            "metadata": {
                                "repo_id": str(self.repo_id),
                                "file_id": str(file_record.id),
                                "file_path": file_path,
                                "function_name": fn["name"],
                                "start_line": part_start_line,
                                "end_line": part_end_line,
                                "chunk_type": "function",
                                "layer": file_record.layer or "unknown",
                                "part_index": part_idx,
                                "part_count": len(parts),
                            },
                        }
                    )

                    if len(chroma_batch) >= EMBED_BATCH:
                        chunks_embedded += self._flush_embeddings(chroma_batch)
                        print(f"chroma batch is here ===>{chunks_embedded}\n\n\n\n\n\n\n")
                        chroma_batch.clear()

            for imp in parsed["imports"]:
                pending_edges.append(
                    {
                        "source_file_id": file_record.id,
                        "source_path": file_path,
                        "raw": imp["raw"],
                        "names": imp["names"],
                        "lang": lang,
                    }
                )

            if chunks_created and chunks_created % 100 == 0:
                self.db.commit()

        if chroma_batch:
            chunks_embedded += self._flush_embeddings(chroma_batch)

        relationships_created = self._write_relationships(pending_edges, file_id_map)
        self.db.commit()

        return {
            "chunks_created": chunks_created,
            "chunks_embedded": chunks_embedded,
            "relationships_created": relationships_created,
            "failed_files": failed_files,
        }

    def _clear_previous(self) -> None:
        self.db.execute(
            delete(FileRelationship).where(FileRelationship.repo_id == self.repo_id)
        )
        self.db.execute(delete(Chunk).where(Chunk.repo_id == self.repo_id))
        self.db.commit()
        try:
            reset_collection(str(self.repo_id))
        except Exception as e:
            print(f"chroma reset skipped/failed: {e}")

    def _read_file(self, full_path: Path) -> str | None:
        if not full_path.is_file():
            return None
        try:
            return full_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                return full_path.read_text(encoding="latin-1")
            except Exception:
                return None
        except Exception:
            return None

    def _flush_embeddings(self, batch: list[dict]) -> int:
        payload: list[dict] = []
        for c in batch:
            try:
                emb = embed_texts([c["content"]])[0]
            except Exception as e:
                # Last resort: hard-truncate and retry once; otherwise skip chunk.
                short = (c["content"] or "")[: max(1000, MAX_EMBED_CHARS // 2)]
                print(
                    f"[embed] failed id={c['id']} chars={len(c.get('content') or '')} "
                    f"err={e}; retrying with {len(short)} chars"
                )
                try:
                    emb = embed_texts([short])[0]
                    c = {**c, "content": short}
                except Exception as e2:
                    print(f"[embed] skip id={c['id']} err={e2}")
                    continue

            payload.append(
                {
                    "id": c["id"],
                    "content": c["content"],
                    "embedding": emb,
                    "metadata": c["metadata"],
                }
            )

        if not payload:
            return 0

        store_chunks(str(self.repo_id), payload)

        repo = self.db.query(Repository).filter(Repository.id == self.repo_id).first()
        if repo is not None:
            repo.done_chunks = (repo.done_chunks or 0) + len(payload)
            self.db.commit()
        return len(payload)

    def _write_relationships(self, pending_edges: list[dict], file_id_map: dict) -> int:
        # key -> (source_id, target_id, names)
        merged: dict[tuple[str, str], tuple[object, object, list[str]]] = {}

        for edge in pending_edges:
            target_path = resolve_import(
                edge["raw"],
                edge["source_path"],
                file_id_map,
                edge["lang"],
            )
            if target_path is None:
                continue

            target_id = file_id_map[target_path]
            if str(target_id) == str(edge["source_file_id"]):
                continue

            key = (str(edge["source_file_id"]), str(target_id))
            if key in merged:
                _, _, names = merged[key]
                for n in edge["names"]:
                    if n not in names:
                        names.append(n)
            else:
                merged[key] = (
                    edge["source_file_id"],
                    target_id,
                    list(edge["names"]),
                )

        created = 0
        for source_id, target_id, names in merged.values():
            self.db.add(
                FileRelationship(
                    repo_id=self.repo_id,
                    source_file_id=source_id,
                    target_file_id=target_id,
                    is_local=True,
                    import_names=names,
                )
            )
            created += 1
        return created
