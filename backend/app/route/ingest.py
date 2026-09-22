from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.postgres import get_db
from app.ingestion.pipeline import ingest_repository

router = APIRouter(prefix="/ingest", tags=["Ingest"])


class IngestRequest(BaseModel):
    repo_url: str
    force: bool = False


@router.post("/")
def ingest(request: IngestRequest, db: Session = Depends(get_db)):
    try:
        result = ingest_repository(request.repo_url, db, force=request.force)
    except Exception as e:
        print(f"here is end of ingest !!! fail ")
        raise HTTPException(status_code=500, detail=str(e)) from e

    state = result.get("state", "fresh")
    messages = {
        "fresh": "Ingest complete: cloned, parsed, related, and embedded",
        "up_to_date": "Repo already up to date — nothing to do",
        "changed": "Incremental sync complete: updated changed files",
    }
    return {
        "message": messages.get(state, "Ingest complete"),
        **result,
    }
