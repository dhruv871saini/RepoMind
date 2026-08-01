from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db.models import Base
from app.db.postgres import engine
from app.route import ingest
from app.service.chroma import init_chroma


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        print("Connecting to chroma db...")
        init_chroma()

        print("Connecting to PostgreSQL...")
        Base.metadata.create_all(bind=engine)

        print("db connection is done ")
    except Exception as e:
        print("error in connectiion time of  db ")
        print(f"this is error in db connection {e}")

    yield


app = FastAPI(
    title="GitRepo Chat API",
    description="RAG-powered GitHub repository chat.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(ingest.router)


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}





