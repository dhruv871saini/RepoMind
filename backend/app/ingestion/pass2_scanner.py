from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy import delete

from app.db.models import Chunk, File, FileRelationship, Repository
from app.files.dispatch import parse_file
from app.files.resolve import resolve_import
from app.service.chroma import reset_collection, store_chunks
from app.service.embed import embed_texts

EMBED_BATCH = 32


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
                chunk_uuid = str(uuid.uuid4())
                self.db.add(
                    Chunk(
                        repo_id=self.repo_id,
                        file_id=file_record.id,
                        chunk_id=chunk_uuid,
                        function_name=fn["name"],
                        start_line=fn["start_line"],
                        end_line=fn["end_line"],
                        chunk_type="function",
                        detection_method=fn["detection_method"],
                    )
                )
                chunks_created += 1
                chroma_batch.append(
                    {
                        "id": chunk_uuid,
                        "content": fn["content"],
                        "metadata": {
                            "repo_id": str(self.repo_id),
                            "file_id": str(file_record.id),
                            "file_path": file_path,
                            "function_name": fn["name"],
                            "start_line": fn["start_line"],
                            "end_line": fn["end_line"],
                            "chunk_type": "function",
                            "layer": file_record.layer or "unknown",
                        },
                    }
                )

                if len(chroma_batch) >= EMBED_BATCH:
                    chunks_embedded += self._flush_embeddings(chroma_batch)
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
        texts = [c["content"] for c in batch]
        embeddings = embed_texts(texts)
        payload = [
            {
                "id": c["id"],
                "content": c["content"],
                "embedding": emb,
                "metadata": c["metadata"],
            }
            for c, emb in zip(batch, embeddings)
        ]
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
