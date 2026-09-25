import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import Repository
from app.db.postgres import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/repo", tags=["repo"])


@router.get("/")
def get_repositories(db: Session = Depends(get_db)):
    try:
        data = db.query(Repository).all()
        return {"data": data}
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Failed to fetch repositories")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch repositories",
        ) from exc


@router.delete("/{repo_id}")
def delete_repository(repo_id: UUID, db: Session = Depends(get_db)):
    try:
        result = db.execute(
            delete(Repository).where(Repository.id == repo_id)
        )

        if result.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Repository not found",
            )

        db.commit()
        return {
            "message": "Repository deleted successfully",
            "id": str(repo_id),
        }
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Failed to delete repository %s", repo_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete repository",
        ) from exc
