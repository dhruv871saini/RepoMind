import ollama as ol

from app.setting import settings

EMBED_MODEL = settings.OLLAMA_EMBED_MODEL
MAX_EMBED_CHARS = settings.MAX_EMBED_CHARS
OVERLAP_CHARS = min(2_000, max(200, MAX_EMBED_CHARS // 8))

_client = ol.Client(host=settings.OLLAMA_BASE_URL)


def split_for_embed(text: str) -> list[str]:
    """
    Split long text into overlapping winadditionalProp1dows that fit the embed model.

    Every character of `text` appears in at least one part (with overlap).
    Prefers splitting on newlines so windows don't cut mid-line when possible.
    """
    text = text or ""
    if not text:
        return []
    if len(text) <= MAX_EMBED_CHARS:
        return [text]

    parts: list[str] = []
    start = 0
    n = len(text)
    step = max(1, MAX_EMBED_CHARS - OVERLAP_CHARS)

    while start < n:
        end = min(start + MAX_EMBED_CHARS, n)

        if end < n:
            window = text[start:end]
            nl = window.rfind("\n")
            if nl >= MAX_EMBED_CHARS // 2:
                end = start + nl + 1

        parts.append(text[start:end])
        if end >= n:
            break

        next_start = end - OVERLAP_CHARS
        if next_start <= start:
            next_start = start + step
        start = next_start

    return parts


def embed(text: str) -> list[float]:
    prompt = text or ""
    if len(prompt) > MAX_EMBED_CHARS:
        print(f"[embed] truncating {len(prompt)} -> {MAX_EMBED_CHARS} chars (split preferred)")
        prompt = prompt[:MAX_EMBED_CHARS]

    print(f"[embed] model={EMBED_MODEL} chars={len(prompt)}")
    response = _client.embeddings(
        model=EMBED_MODEL,
        prompt=prompt,
    )
    return response["embedding"]


def embed_texts(texts: list[str]) -> list[list[float]]:
    return [embed(text) for text in texts]