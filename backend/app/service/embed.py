import ollama as ol

EMBED_MODEL = "nomic-embed-text"


def embed(text: str) -> list[float]:
    response = ol.embeddings(
        model=EMBED_MODEL,
        prompt=text,
    )
    return response["embedding"]


def embed_texts(texts: list[str]) -> list[list[float]]:
    return [embed(text) for text in texts]