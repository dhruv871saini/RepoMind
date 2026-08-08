from __future__ import annotations

import httpx

from app.setting import settings


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed texts via local Ollama (/api/embed)."""
    if not texts:
        return []

    url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/embed"
    payload = {
        "model": settings.OLLAMA_EMBED_MODEL,
        "input": texts,
    }

    with httpx.Client(timeout=120.0) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()

    embeddings = data.get("embeddings")
    if not embeddings or len(embeddings) != len(texts):
        raise RuntimeError(
            f"Ollama embed returned unexpected payload for {len(texts)} texts: "
            f"{list(data.keys())}"
        )
    return embeddings
