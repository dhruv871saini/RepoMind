from app.db.models import File,Chunk,FileRelationship

class Pass2Scanner:
    def __init__(self,repo_id:str, repo_path:str, db_session):
        self.repo_id= repo_id
        self.repo_path=repo_path
        self.db=db_session

    def parse_and_chunks(self,file_id_map):
        print(f"repo path is {self.repo_path}")
        files=self.db.query(File).filter(File.repo_id==self.repo_id)
        for file_record in files:
            try:
                file_path = file_record.file_path
                full_path = self.repo_path / file_path
                print(f"full path is {full_path}")
                try:
                    with open(full_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                except UnicodeDecodeError:
                    try:
                        with open(full_path, 'r', encoding='latin-1') as f:
                            content = f.read()
                    except:
                        failed_files.append(file_path)
                        continue
                print(f"content is {content}")

                
