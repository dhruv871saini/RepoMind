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
        raise HTTPException(status_code=500, detail=str(e)) from e

    return {
        "message": "Pass 1 complete: repository cloned and files recorded",
        **result,
    }
