from __future__ import annotations

from chromadb.utils import embedding_functions

_embedding_fn = None


def get_embedding_fn():
    global _embedding_fn
    if _embedding_fn is None:
        _embedding_fn = embedding_functions.DefaultEmbeddingFunction()
    return _embedding_fn


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    return get_embedding_fn()(texts)
