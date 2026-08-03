from app.db.models import Repository
from app.ingestion.pass1_scanner import Pass1Scanner
from app.service.clone import clone_repo, sanitize_repo_name
from app.ingestion.pass2_scanner import Pass2Scanner

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

        result2=Pass2Scanner(repo_id=repo.id,repo_path=repo.repo_path,db_session=db)
        result2.parse_and_chunks(result['file_id_map'])
        print(f"result2==={result2}")

        return {
            "repo_id": str(repo.id),
            "repo_name": repo.repo_name,
            "repo_path": repo_path,
            "status": repo.status,
            "progress": repo.progress,
            "total_files": result["total_files"],
            "created_count": result["created_count"],
        }
    except Exception as e:
        repo.status = "failed"
        repo.failed_stage = stage
        repo.error_message = str(e)
        db.commit()
        raise
