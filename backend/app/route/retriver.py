from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.postgres import get_db
from app.service.retriever import run_retriever

router = APIRouter(prefix="/retriver", tags=["retriver"])


class RetriverRequest(BaseModel):
    repo_id: str
    question: str
    k: int = Field(default=5, ge=1, le=50)
    history: list[dict] = Field(default_factory=list)
    expand_graph: bool = True
    max_graph_chunks: int = Field(default=20, ge=0, le=100)


@router.post("/")
def retriver(request: RetriverRequest, db: Session = Depends(get_db)):
    question = (request.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is invalid or empty")
    if not (request.repo_id or "").strip():
        raise HTTPException(status_code=400, detail="repo_id is required")

    try:
        return run_retriever(
            db,
            repo_id=request.repo_id.strip(),
            question=question,
            k=request.k,
            history=request.history,
            expand_graph=request.expand_graph,
            max_graph_chunks=request.max_graph_chunks,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except Exception as e:
        print(f"error in retriver:\n{e}")
        raise HTTPException(status_code=500, detail="retriver crash") from e
