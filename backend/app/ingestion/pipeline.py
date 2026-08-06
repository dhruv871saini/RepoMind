from datetime import datetime, timezone

from app.db.models import Repository
from app.ingestion.pass1_scanner import Pass1Scanner
from app.ingestion.pass2_scanner import Pass2Scanner
from app.service.clone import clone_repo, sanitize_repo_name


def ingest_repository(repo_url: str, db, force: bool = False) -> dict:
    repo = db.query(Repository).filter(Repository.repo_url == repo_url).first()
    stage = "cloning"

    if repo is None:
        repo = Repository(
            repo_url=repo_url,
            repo_name=sanitize_repo_name(repo_url),
            repo_path="",
            status="cloning",
        )
        db.add(repo)
        db.commit()
        db.refresh(repo)
    else:
        repo.status = "cloning"
        repo.error_message = None
        repo.failed_stage = None
        repo.done_chunks = 0
        repo.total_chunks = 0
        repo.chunk_count = 0
        db.commit()

    try:
        repo_path = clone_repo(repo_url, force=force)
        repo.repo_path = repo_path
        repo.repo_name = sanitize_repo_name(repo_url)

        stage = "walking"
        repo.status = "walking"
        db.commit()

        result = Pass1Scanner(
            repo_id=str(repo.id),
            repo_path=repo_path,
            db_session=db,
        ).scan_and_create_files()

        repo.file_count = result["total_files"]
        repo.progress = 25
        db.commit()

        stage = "chunking"
        repo.status = "chunking"
        db.commit()

        stage = "embedding"
        repo.status = "embedding"
        db.commit()

        pass2 = Pass2Scanner(
            repo_id=str(repo.id),
            repo_path=repo_path,
            db_session=db,
        ).parse_and_chunks(result["file_id_map"])

        repo.chunk_count = pass2["chunks_created"]
        repo.total_chunks = pass2["chunks_created"]
        repo.done_chunks = pass2["chunks_embedded"]
        repo.progress = 100
        repo.status = "ready"
        repo.last_ingested_at = datetime.now(timezone.utc)
        db.commit()

        return {
            "repo_id": str(repo.id),
            "repo_name": repo.repo_name,
            "repo_path": repo_path,
            "status": repo.status,
            "progress": repo.progress,
            "total_files": result["total_files"],
            "created_count": result["created_count"],
            "chunks_created": pass2["chunks_created"],
            "chunks_embedded": pass2["chunks_embedded"],
            "relationships_created": pass2["relationships_created"],
            "failed_files": pass2["failed_files"],
        }
    except Exception as e:
        repo.status = "failed"
        repo.failed_stage = stage
        repo.error_message = str(e)
        db.commit()
        raise
