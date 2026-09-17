from sqlalchemy import delete 
from app.db.models import Chunk, File, FileRelationship
from app.service.chroma import delete_chunks_by_ids
from app.ingestion.pass2_scanner import Pass2Scanner
from app.ingestion.pass1_scanner import Pass1Scanner

def run_incremental_sync(repo, repo_path, added, modified, deleted, new_sha, db):
    repo_id = str(repo.id)

    for file_path in deleted:
        file_record = db.query(File).filter(
            File.repo_id == repo.id,
            File.file_path == file_path
        ).first()

        if file_record is None:
            continue

        chunk_ids = [
            c.chunk_id
            for c in db.query(Chunk).filter(Chunk.file_id == file_record.id).all()
        ]

        delete_chunks_by_ids(repo_id, chunk_ids)

        db.execute(delete(Chunk).where(Chunk.file_id == file_record.id))

        db.execute(
            delete(FileRelationship).where(
                (FileRelationship.source_file_id == file_record.id) |
                (FileRelationship.target_file_id == file_record.id)
            )
        )

        db.delete(file_record)
        db.commit()
        print(f"[sync] deleted: {file_path}")

    for file_path in modified:
        file_record = db.query(File).filter(
            File.repo_id == repo.id,
            File.file_path == file_path
        ).first()

        if file_record is None:
            added.append(file_path)
            continue

        chunk_ids = [
            c.chunk_id
            for c in db.query(Chunk).filter(Chunk.file_id == file_record.id).all()
        ]

        delete_chunks_by_ids(repo_id, chunk_ids)

        db.execute(delete(Chunk).where(Chunk.file_id == file_record.id))

        db.execute(
            delete(FileRelationship).where(
                FileRelationship.source_file_id == file_record.id
            )
        )

        db.commit()
        print(f"[sync] cleared old chunks for modified: {file_path}")



    all_files = db.query(File).filter(File.repo_id == repo.id).all()
    file_id_map = {f.file_path: f.id for f in all_files}

    for file_path in added:
        file_record = File(
            repo_id=repo.id,
            file_path=file_path,
            layer=Pass1Scanner.detect_layer(file_path)  
        )
        db.add(file_record)
        db.flush()
        file_id_map[file_path] = file_record.id
        print(f"[sync] added file record: {file_path}")

    db.commit()

    files_to_reprocess = set(modified) | set(added)

    scanner = Pass2Scanner(repo_id=repo_id, repo_path=repo_path, db_session=db)
    scanner.reprocess_files(files_to_reprocess, file_id_map)
    repo.last_commit_sha = new_sha
    repo.status = "ready"
    db.commit()
    print(f"[sync] complete. SHA updated to {new_sha[:8]}")