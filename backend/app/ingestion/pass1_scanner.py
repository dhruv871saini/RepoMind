from pathlib import Path
from typing import Dict
from app.ingestion.fileScanner import FileScanner
from app.db.models import File


class Pass1Scanner:
    
    def __init__(self, repo_id: str, repo_path: str, db_session):
        self.repo_id = repo_id
        self.repo_path = Path(repo_path)
        self.db = db_session
        print("==== pass1scanner is start =====")
    
    def scan_and_create_files(self) -> dict:
        
        scanner = FileScanner(str(self.repo_path))
        files = scanner.scan()
        
        print(f"Found {len(files)} code files")
        
        created_count = 0
        file_id_map = {}
        
        for file_path in files:
            existing = self.db.query(File).filter(
                File.repo_id == self.repo_id,
                File.file_path == str(file_path)
            ).first()
            
            if existing:
                file_id_map[str(file_path)] = existing.id
                continue
            
            file_record = File(
                repo_id=self.repo_id,
                file_path=str(file_path),
                layer=self._detect_layer(str(file_path))
            )
            self.db.add(file_record)
            self.db.flush()
            
            file_id_map[str(file_path)] = file_record.id
            created_count += 1
            
            if created_count % 100 == 0:
                self.db.commit()
                print(f"Created {created_count} file records...")
        
        self.db.commit()
        print(f"Created {created_count} new file records")
        
        return {
            'total_files': len(files),
            'created_count': created_count,
            'file_id_map': file_id_map
        }
    
    def _detect_layer(self, file_path: str) -> str:
        path_lower = file_path.lower()
        
        if 'controller' in path_lower or 'handlers' in path_lower:
            return 'controller'
        elif 'service' in path_lower:
            return 'service'
        elif 'model' in path_lower or 'schema' in path_lower:
            return 'model'
        elif 'route' in path_lower or 'router' in path_lower:
            return 'route'
        elif 'middleware' in path_lower:
            return 'middleware'
        elif 'util' in path_lower or 'helper' in path_lower:
            return 'utils'
        elif 'config' in path_lower or 'setting' in path_lower:
            return 'config'
        elif 'test' in path_lower or '__tests__' in path_lower:
            return 'test'
        else:
            return 'unknown'