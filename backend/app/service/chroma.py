import re
import chromadb
from chromadb.config import Settings
from app.setting import settings

client = None
_collection = None

algorithm = {"hnsw:space": "cosine"}
collection_name = "repo_mind"


def sanitize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9_-]", "_", name.lower())


def init_chroma():
    global client

    print("Initiating Chroma DB...")


    client = chromadb.HttpClient(
        host=settings.CHROMA_HOST, port=settings.CHROMA_PORT, settings=Settings(anonymized_telemetry=False)
    )
    client.heartbeat()
    
    print("Successfully chroma DB")
    return client

def create_collection(repo_id):

    if client is None:
        raise RuntimeError(
            "client is not get show run the init_chroma() first!"
            )
    global _collection
    safe_repo_id = sanitize_name(repo_id)
    full_collection_name = f"{collection_name}_{safe_repo_id}"

    _collection = client.get_or_create_collection(
        name=full_collection_name, metadata=algorithm
    )
    return _collection



def reset_collection(repo_id: str):
    if client is None:
        raise RuntimeError("client is not get show run the init_chroma() first!")

    global _collection
    safe_repo_id = sanitize_name(repo_id)
    full_collection_name = f"{collection_name}_{safe_repo_id}"
    try:
        client.delete_collection(full_collection_name)
    except Exception:
        pass
    _collection = client.get_or_create_collection(
        name=full_collection_name, metadata=algorithm
    )
    return _collection


def store_chunks(repo_id: str, chunks: list[dict]):

    if not chunks:
        return

    collection = create_collection(repo_id)
    collection.add(
        ids=[c["id"] for c in chunks],
        embeddings=[c["embedding"] for c in chunks],
        documents=[c["content"] for c in chunks],
        metadatas=[c["metadata"] for c in chunks],
    )


def search_chunks(
    repo_id: str,
    query_embedding: list[float],
    n_results: int = 10,
    where: dict | None = None,
) -> list[dict]:
    if not query_embedding:
        return []

    collection = create_collection(repo_id)
    count = collection.count()
    if count == 0:
        return []

    kwargs: dict = {
        "query_embeddings": [query_embedding],
        "n_results": min(n_results, count),
        "include": ["documents", "metadatas", "distances"],
    }
    if where:
        kwargs["where"] = where

    result = collection.query(**kwargs)

    ids = (result.get("ids") or [[]])[0]
    documents = (result.get("documents") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]

    hits: list[dict] = []
    for chunk_id, document, metadata, distance in zip(
        ids, documents, metadatas, distances
    ):
        # hnsw:space=cosine → distance is 1 - cosine_similarity
        similarity = 1.0 - float(distance)
        hits.append(
            {
                "id": chunk_id,
                "content": document,
                "metadata": metadata or {},
                "distance": float(distance),
                "relevance_score": round(max(0.0, min(1.0, similarity)) * 100, 2),
            }
        )
    return hits


def get_chunks_by_ids(repo_id: str, chunk_ids: list[str]) -> list[dict]:
    if not chunk_ids:
        return []

    collection = create_collection(repo_id)
    result = collection.get(
        ids=chunk_ids,
        include=["documents", "metadatas"],
    )

    ids = result.get("ids") or []
    documents = result.get("documents") or []
    metadatas = result.get("metadatas") or []

    return [
        {
            "id": chunk_id,
            "content": document,
            "metadata": metadata or {},
            "relevance_score": None,
        }
        for chunk_id, document, metadata in zip(ids, documents, metadatas)
    ]
