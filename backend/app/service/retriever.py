from __future__ import annotations

import time
import uuid
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models import Chunk, FileRelationship, Query, QueryChunk, Repository
from app.service.ask import ask
from app.service.chroma import get_chunks_by_ids, search_chunks
from app.service.embed import embed


def _hit_label(hit: dict) -> str:
    meta = hit.get("metadata") or {}
    path = meta.get("file_path", "?")
    name = meta.get("function_name") or "-"
    score = hit.get("relevance_score")
    src = hit.get("retrieval_source", "?")
    score_s = f"{score}" if score is not None else "n/a"
    return f"[{src}] {path} :: {name}  score={score_s}"


def run_retriever(
    db: Session,
    *,
    repo_id: str,
    question: str,
    k: int = 5,
    history: list[dict] | None = None,
    expand_graph: bool = True,
    max_graph_chunks: int = 20,
) -> dict[str, Any]:
    """
    Full RAG flow:
      validate repo → embed → Chroma search → optional graph expand → ask → persist
    """
    started = time.perf_counter()
    question = (question or "").strip()
    if not question:
        raise ValueError("question is empty")

    print("\n======== RETRIEVER START ========")
    print(f"[input] repo_id={repo_id}")
    print(f"[input] question={question!r}")
    print(f"[input] k={k} expand_graph={expand_graph} max_graph_chunks={max_graph_chunks}")
    print(f"[input] history_turns={len(history or [])}")

    try:
        repo_uuid = uuid.UUID(str(repo_id))
    except ValueError as e:
        raise ValueError("repo_id is invalid") from e

    repo = db.query(Repository).filter(Repository.id == repo_uuid).first()
    if repo is None:
        raise LookupError("repository not found")
    if repo.status != "ready":
        raise RuntimeError(f"repository is not ready (status={repo.status})")

    print(f"[repo] name={repo.repo_name} status={repo.status} chunks={repo.chunk_count}")

    query_row = Query(
        repo_id=repo.id,
        question=question,
        status="pending",
    )
    db.add(query_row)
    db.flush()
    print(f"[db] created Query id={query_row.id} status=pending")

    try:
        print("[embed] embedding question...")
        query_embedding = embed(question)
        print(f"[embed] done  dim={len(query_embedding)}")

        print(f"[chroma] searching top-{max(1, k)}...")
        vector_hits = search_chunks(
            str(repo.id),
            query_embedding,
            n_results=max(1, k),
        )
        for hit in vector_hits:
            hit["retrieval_source"] = "vector"

        print(f"[chroma] got {len(vector_hits)} vector hits:")
        for i, hit in enumerate(vector_hits, start=1):
            print(f"  {i}. {_hit_label(hit)}")

        graph_hits: list[dict] = []
        if expand_graph and vector_hits:
            print("[graph] expanding via FileRelationship...")
            graph_hits = _expand_via_graph(
                db,
                repo_id=repo.id,
                vector_hits=vector_hits,
                max_extra=max_graph_chunks,
            )
            print(f"[graph] got {len(graph_hits)} extra chunks:")
            for i, hit in enumerate(graph_hits, start=1):
                print(f"  {i}. {_hit_label(hit)}")
        elif not expand_graph:
            print("[graph] skipped (expand_graph=false)")
        else:
            print("[graph] skipped (no vector hits)")

        contexts = _merge_contexts(vector_hits, graph_hits)
        print(
            f"[merge] contexts for LLM: {len(contexts)} "
            f"(vector={len(vector_hits)} + graph={len(graph_hits)})"
        )

        print("[ask] sending question + contexts to Ollama...")
        answer = ask(question, contexts=contexts, history=history or [])
        preview = answer if len(answer) <= 300 else answer[:300] + "..."
        print(f"[ask] answer ({len(answer)} chars):\n{preview}")

        _persist_query_chunks(db, query_row, contexts)

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        query_row.answer = answer
        query_row.status = "completed"
        query_row.response_time_ms = elapsed_ms
        query_row.vector_chunks_count = len(vector_hits)
        query_row.graph_chunks_count = len(graph_hits)
        query_row.chunks_used = len(contexts)
        db.commit()
        db.refresh(query_row)

        print(
            f"[done] query_id={query_row.id} status=completed "
            f"time={elapsed_ms}ms chunks_used={query_row.chunks_used}"
        )
        print("======== RETRIEVER END ========\n")

        return {
            "query_id": str(query_row.id),
            "repo_id": str(repo.id),
            "question": question,
            "answer": answer,
            "status": query_row.status,
            "response_time_ms": elapsed_ms,
            "chunks_used": query_row.chunks_used,
            "vector_chunks_count": query_row.vector_chunks_count,
            "graph_chunks_count": query_row.graph_chunks_count,
            "contexts": [
                {
                    "chunk_id": c["id"],
                    "relevance_score": c.get("relevance_score"),
                    "retrieval_source": c.get("retrieval_source", "vector"),
                    "metadata": c.get("metadata") or {},
                }
                for c in contexts
            ],
        }
    except Exception as e:
        query_row.status = "failed"
        query_row.response_time_ms = int((time.perf_counter() - started) * 1000)
        db.commit()
        print(f"[fail] query_id={query_row.id} error={e}")
        print("======== RETRIEVER FAIL ========\n")
        raise


def _expand_via_graph(
    db: Session,
    *,
    repo_id,
    vector_hits: list[dict],
    max_extra: int,
) -> list[dict]:
    """Pull chunks from files connected via FileRelationship to vector-hit files."""
    chroma_ids = [h["id"] for h in vector_hits]
    seed_chunks = (
        db.query(Chunk)
        .filter(Chunk.repo_id == repo_id, Chunk.chunk_id.in_(chroma_ids))
        .all()
    )
    if not seed_chunks:
        print("[graph] no postgres Chunk rows for vector hits")
        return []

    seed_file_ids = {c.file_id for c in seed_chunks}
    seed_chroma_ids = {c.chunk_id for c in seed_chunks}
    print(f"[graph] seed files={len(seed_file_ids)} seed chunks={len(seed_chunks)}")

    rels = (
        db.query(FileRelationship)
        .filter(
            FileRelationship.repo_id == repo_id,
            or_(
                FileRelationship.source_file_id.in_(seed_file_ids),
                FileRelationship.target_file_id.in_(seed_file_ids),
            ),
        )
        .all()
    )
    if not rels:
        print("[graph] no FileRelationship edges from seed files")
        return []

    related_file_ids: set = set()
    for rel in rels:
        related_file_ids.add(rel.source_file_id)
        related_file_ids.add(rel.target_file_id)
    related_file_ids -= seed_file_ids
    print(f"[graph] relationships={len(rels)} related_files={len(related_file_ids)}")
    if not related_file_ids:
        return []

    related_chunks = (
        db.query(Chunk)
        .filter(
            Chunk.repo_id == repo_id,
            Chunk.file_id.in_(related_file_ids),
            ~Chunk.chunk_id.in_(seed_chroma_ids),
        )
        .limit(max_extra)
        .all()
    )
    if not related_chunks:
        print("[graph] related files have no extra chunks")
        return []

    print(f"[graph] fetching {len(related_chunks)} chunk bodies from Chroma")
    fetched = get_chunks_by_ids(str(repo_id), [c.chunk_id for c in related_chunks])
    for hit in fetched:
        hit["retrieval_source"] = "graph"
        hit.setdefault("relevance_score", None)
    return fetched


def _merge_contexts(vector_hits: list[dict], graph_hits: list[dict]) -> list[dict]:
    merged: list[dict] = []
    seen: set[str] = set()
    for hit in [*vector_hits, *graph_hits]:
        chunk_id = hit.get("id")
        if not chunk_id or chunk_id in seen:
            continue
        seen.add(chunk_id)
        merged.append(hit)
    return merged


def _persist_query_chunks(db: Session, query_row: Query, contexts: list[dict]) -> None:
    if not contexts:
        print("[db] no QueryChunk rows to save")
        return

    chroma_ids = [c["id"] for c in contexts]
    rows = (
        db.query(Chunk)
        .filter(Chunk.repo_id == query_row.repo_id, Chunk.chunk_id.in_(chroma_ids))
        .all()
    )
    by_chroma = {row.chunk_id: row for row in rows}

    saved = 0
    missing = 0
    for ctx in contexts:
        pg_chunk = by_chroma.get(ctx["id"])
        if pg_chunk is None:
            missing += 1
            continue
        db.add(
            QueryChunk(
                query_id=query_row.id,
                chunk_id=pg_chunk.id,
                relevance_score=ctx.get("relevance_score"),
                retrieval_source=ctx.get("retrieval_source") or "vector",
            )
        )
        saved += 1

    print(f"[db] saved QueryChunk rows={saved} missing_in_postgres={missing}")
