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
