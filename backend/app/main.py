from fastapi import FastAPI
from contextlib import asynccontextmanager
from service.chroma import init_chroma
from db.postgres import base,engine

@asynccontextmanager
async def lifespan(app:FastAPI):
    try:
        print("Connecting to chroma db...")
        init_chroma()

        print("Connecting to PostgreSQL...")
        base.metadata.create_all(bind=engine)

        print("db connection is done ")

    except Exception as e :
        print("error in connectiion time of  db ")
        print(f"this is error in db connection {e}")

    yield


app= FastAPI(
    title="GitRepo Chat API",
    description="RAG-powered GitHub repository chat.",
    version="1.0.0",
    lifespan=lifespan,

)




@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}





