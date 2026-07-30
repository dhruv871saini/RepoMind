from fastapi import APIRouter
from pydantic import BaseModel
from app.service.clone import clone_repo

router = APIRouter(prefix="/clone", tags=["Clone"])


class CloneRequest(BaseModel):
    repo_url: str
    force: bool = False


@router.post("/")
def clone_repository(request: CloneRequest):
    path = clone_repo(request.repo_url, request.force)

    return {
        "message": "Repository cloned successfully",
        "path": path,
    }