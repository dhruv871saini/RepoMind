import ollama as ol

from app.setting import settings

CHAT_MODEL = settings.OLLAMA_CHAT_MODEL


def _format_context(contexts: list[dict]) -> str:
    if not contexts:
        return "(no code context found)"

    parts: list[str] = []
    for i, ctx in enumerate(contexts, start=1):
        meta = ctx.get("metadata") or {}
        path = meta.get("file_path", "unknown")
        name = meta.get("function_name", "")
        start = meta.get("start_line", "?")
        end = meta.get("end_line", "?")
        score = ctx.get("relevance_score")
        header = f"[{i}] {path}"
        if name:
            header += f" :: {name}"
        header += f" (L{start}-{end})"
        if score is not None:
            header += f" score={score}"
        body = (ctx.get("content") or "").strip()
        parts.append(f"{header}\n{body}")
    return "\n\n".join(parts)


def ask(
    question: str,
    contexts: list[dict] | None = None,
    history: list[dict] | None = None,
    model: str | None = None,
) -> str:
    """
    Ask Ollama a question grounded in retrieved code chunks.

    contexts: hits from search_chunks (id, content, metadata, relevance_score)
    history:  optional prior chat turns [{"role": "user"|"assistant", "content": "..."}]
    """
    question = (question or "").strip()
    if not question:
        raise ValueError("question is empty")

    context_block = _format_context(contexts or [])
    system = (
        "You are RepoMind, a code assistant for a specific repository. "
        "Answer using the provided code context. "
        "Cite file paths and function names when relevant. "
        "If the context is insufficient, say what is missing instead of inventing code."
    )
    user_prompt = (
        f"Code context:\n{context_block}\n\n"
        f"Question: {question}\n\n"
        "Answer:"
    )

    messages: list[dict] = [{"role": "system", "content": system}]
    for turn in history or []:
        role = turn.get("role")
        content = (turn.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_prompt})

    model_name = model or CHAT_MODEL
    print(f"[ask] model={model_name} contexts={len(contexts or [])} history={len(history or [])}")
    print(f"[ask] context chars={len(context_block)} prompt chars={len(user_prompt)}")

    response = ol.chat(
        model=model_name,
        messages=messages,
    )
    answer = (response.get("message") or {}).get("content", "").strip()
    print(f"[ask] ollama returned {len(answer)} chars")
    return answer
