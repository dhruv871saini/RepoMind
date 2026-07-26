from fastapi import FastAPI
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app:FastAPI):
    try:
        print("ready to connect db")
    except Exception as e :
        print(f"this is error in db connection {e}")

    yield


app= FastAPI(
    title="GitRepo Chat API",
    description="""
RAG-powered GitHub repository chat.
 
Ingest any GitHub repo, then ask questions like:
- "Why is the auth controller structured this way?"
- "Which services use the email middleware?"
- "How does the payment flow work end to end?"
- "Where is the database connection initialized?"
    """,
    version="1.0.0",
    lifespan=lifespan,

)


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}



