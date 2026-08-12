# Challenges, Debugging & Fixes

This document records **real problems** we hit while building RepoMind’s RAG backend, how we **debugged** them, and what we **changed**.

Audience: developers and recruiters who want to see practical engineering judgment—not just a happy-path demo.

---

## Challenge map (overview)

```text
Failures we hit
│
├── 1. Embedding context overflow on ingest
│   └── huge function bodies > embed model limit
│
├── 2. “We changed the model” but behavior didn’t change
│   └── embed.py hardcoded model; .env overrode settings.py
│
├── 3. Truncation “fixed” crash but lost code
│   └── leftover text never embedded
│
├── 4. Split parts stored only a slice
│   └── retrieval looked like “code is missing”
│
└── 5. Chat / ask can also overflow context
    └── too many retrieved chunks packed into one prompt
```

```text
500: input length exceeds the context length
                │
                ▼
         Where did it come from?
          /          \
         /            \
   /ingest             /retriver
   (detail = Ollama    (often "retriver crash"
    error string)       — check server logs)
         │                    │
         ▼                    ▼
   Embedding path        Ask / chat path
         │                    │
         ├── chunk too large  └── too much retrieved context
         ├── wrong / ignored model settings
         └── char budget still too high
```

---

## Challenge 1 — Ingest dies: context length exceeded

### Symptom

```json
{ "detail": "the input length exceeds the context length (status code: 500)" }
```

- Returned from **`POST /ingest/`** (that route forwards `str(e)`).
- Repo status often ended as `failed` with `failed_stage` around **embedding**.

### Why it happened

During Pass 2 we embed **entire function bodies**.  
Embedding models (e.g. `nomic-embed-text`) have a max context (~8k tokens).  
Dense code ≈ **few characters per token**, so a large function easily overflows.

Also: embeddings ran in **batches**. One oversized item could fail the batch / stage.

```text
Parser finds function
        │
        ▼
  fn["content"]  ──►  ollama.embeddings()  ──►  BOOM if too long
```

### How we debugged

1. Matched error shape to **Ollama client** (`… (status code: 500)`).
2. Compared routes:
   - `/ingest` → `detail=str(e)` ← matched the response we saw
   - `/retriver` → would say `"retriver crash"`
3. Traced ingest → `Pass2Scanner._flush_embeddings` → `embed_texts` → `ol.embeddings`.
4. Confirmed **no max length** on chunk text before embed.
5. Logged stage (`embedding`) and chunk sizes.

### How we solved it

| Step | Change |
|---|---|
| 1 | Added `split_for_embed()` — overlapping windows under a char budget |
| 2 | Large function → **many chunks**; small function → **one chunk** |
| 3 | Lowered budget to a safer default (`MAX_EMBED_CHARS=8000`) |
| 4 | Per-chunk embed with **retry shorter / skip** so one bad chunk doesn’t kill the whole repo |

```text
Before:
  1 function → 1 huge prompt → fail

After:
  1 function
  ├── window 1 → embed OK
  ├── window 2 → embed OK
  └── window 3 → embed OK
```

**Key files:** `app/service/embed.py`, `app/ingestion/pass2_scanner.py`

---

## Challenge 2 — “Higher model” still failed / didn’t apply

### Symptom

Settings / comments said we switched to a larger embedding or chat model, but:

- Errors still looked like **nomic / small-context** failures, or
- Behavior didn’t match the model named in `settings.py`.

### Why it happened

Two config traps:

1. **`embed.py` hardcoded** `EMBED_MODEL = "nomic-embed-text"`  
   → ignored `settings.OLLAMA_EMBED_MODEL`.
2. **`.env` overrides** pydantic settings  
   → e.g. `.env` still had `OLLAMA_EMBED_MODEL=nomic-embed-text` even if `settings.py` default was changed.

```text
settings.py  (default qwen…)
      │
      ▼
   .env wins  ──► nomic-embed-text
      │
      ▼
   embed.py hardcoded nomic  ──► settings never used anyway
```

### How we debugged

1. Printed effective settings at runtime (`settings.OLLAMA_EMBED_MODEL`).
2. Grepped for `EMBED_MODEL` / `nomic` / `ollama`.
3. Compared `.env` vs `settings.py` vs `embed.py`.

### How we solved it

- Wire `embed.py` (and `ask.py`) to **`settings`** + `ollama.Client(host=OLLAMA_BASE_URL)`.
- Make limits configurable: `MAX_EMBED_CHARS`, `MAX_ASK_CONTEXT_CHARS`.
- Document that **`.env` is source of truth** for local runs; restart API after changes.
- Log `[embed] model=… chars=…` so the active model is visible in server logs.

**Key files:** `app/service/embed.py`, `app/setting.py`, `.env`

---

## Challenge 3 — Truncation stops the crash but “leaves text behind”

### Symptom

After adding a simple truncate-before-embed:

- Ingest stopped crashing.
- Concern: **remaining text after the cut is never embedded** → retrieval can’t find that logic.

### Why it happened

```text
function[0 : 24000]  → embedded
function[24000 : ]   → discarded for search
```

Truncate is a **safety valve**, not a complete index of the function.

### How we debugged / reasoned

- Product requirement: searchable coverage of the whole function when possible.
- Truncation alone fails that requirement for huge methods.

### How we solved it

Replaced “truncate only” with **split + embed every window**:

```text
split_for_embed(text)
├── prefers newline boundaries
├── overlapping windows (no uncovered gap)
└── each part → its own Chunk row + Chroma vector
```

Keep truncate only as a **last-resort safety net** inside `embed()`.

**Key files:** `app/service/embed.py`, `app/ingestion/pass2_scanner.py`

---

## Challenge 4 — “Code is missing” after split

### Symptom (two related meanings we hit)

1. **Retrieval display:** stored only the window → answer context looked incomplete vs the full function.  
2. **Embedding coverage:** worry that split didn’t embed the remainder (see Challenge 3).

### How we debugged

- Inspected what Pass 2 puts in Chroma `documents` vs what `embed()` receives.
- Walked `/retriver` → `ask._format_context` which prints `ctx["content"]`.
- Verified split coverage with length tests (all characters appear in ≥1 window).

### How we solved it

Final consistent rule:

```text
Store what you embed.
Each part.content == the window that was embedded.
Collectively, parts cover the full function (with overlap).
Metadata includes part_index / part_count and per-part line ranges.
```

Also improved flush:

- Embed **one chunk at a time** in the batch flusher.
- On failure: retry with a shorter string; if still failing → **skip + log**, continue ingest.

**Key files:** `app/ingestion/pass2_scanner.py`, `app/service/embed.py`

---

## Challenge 5 — Ask path can overflow too

### Symptom

Even with ingest fixed, asking questions can fail when:

- `k` is high, and/or
- `expand_graph` pulls many related chunks, and/or
- history is long,

so the **chat** model prompt exceeds its context (different limit than the embed model).

### How we debugged

1. Noted `/retriver` merges vector + graph contexts then calls `ask()`.
2. Logged `context chars` / `prompt chars` in `ask`.
3. Distinguished embed overflow (ingest) vs chat overflow (retriever).

### How we solved it

- Cap assembled code context with `MAX_ASK_CONTEXT_CHARS` (keep top-ranked chunks first).
- Keep graph expansion configurable (`expand_graph`, `max_graph_chunks`).
- Use settings-driven chat model via the same Ollama client host.

**Key files:** `app/service/ask.py`, `app/service/retriever.py`, `app/setting.py`

---

## Debugging playbook (reuse next time)

```text
Got a 500 from RepoMind?
│
├── Read `detail`
│   ├── exact Ollama message? → likely embed or chat context
│   └── "retriver crash"? → check server logs for real exception
│
├── Check Repository row
│   ├── status / failed_stage / error_message
│   └── done_chunks vs total_chunks
│
├── Confirm effective config (not just settings.py)
│   ├── .env values
│   ├── restart uvicorn after .env change
│   └── log lines: [embed] model=… / [ask] model=…
│
├── Measure sizes
│   ├── chunk char lengths at flush
│   └── ask context char length
│
└── Isolate
    ├── re-ingest one small repo first
    ├── force: true to rebuild Chroma + chunks
    └── try expand_graph=false to test ask without graph bulk
```

### Useful log markers

| Log prefix | Meaning |
|---|---|
| `[chunk] split … into N parts` | Oversized function was windowed |
| `[embed] model=… chars=…` | Actual embed model + size |
| `[embed] failed … retrying` | Chunk overflowed; shorter retry |
| `[embed] skip …` | Chunk abandoned so ingest can finish |
| `[ask] context truncated…` | Chat prompt budget hit |
| `======== RETRIEVER START/FAIL` | Full ask pipeline trace |

---

## Before / after (engineering summary)

| Area | Before | After |
|---|---|---|
| Large functions | Single embed → crash | Split windows → multiple embeddings |
| Model selection | Hardcoded / easy to misconfigure | Settings + `.env` + runtime logs |
| Bad chunk | Failed whole ingest | Retry shorter / skip chunk |
| Ask prompt | Unbounded context | Cap with `MAX_ASK_CONTEXT_CHARS` |
| Observability | Opaque 500 | Stage status + targeted prints |

---

## What this shows (for recruiters)

- We treat RAG as a **pipeline with measurable failure points**, not a single LLM call.
- We separate **embed context limits** from **chat context limits**.
- We prefer **coverage-preserving splits** over silent truncation when indexing code.
- We debug with **route behavior, config precedence, and size metrics**—not guesswork.

For the happy-path architecture and diagrams, see **[README.md](./README.md)**.
