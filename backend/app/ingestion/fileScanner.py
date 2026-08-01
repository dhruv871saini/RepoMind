from pathlib import Path
import os
class FileScanner:

    SKIP_DIRS = {
        'node_modules', '.git', 'dist', 'build', 'target',
        'venv', 'env', '.venv', '__pycache__', '.idea', '.vscode',
        'coverage', '.next', 'out', 'bin', 'obj', 'vendor'
    }
    
    SKIP_FILES = {
        'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml',
        'poetry.lock', 'Gemfile.lock', 'Cargo.lock',
        '.gitignore', '.dockerignore', '.env', '.env.example'
    }
    
    SUPPORTED_EXTENSIONS = {
        '.js', '.jsx', '.ts', '.tsx',
        '.py', '.go', '.java', '.rb', '.php',
        '.rs', '.c', '.cpp', '.h', '.hpp',
        '.cs', '.swift', '.kt', '.scala',
        '.lua', '.r', '.dart'
    }

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)
        self.files = []
    
    def scan(self,)-> list[Path]:
        self.files=[]

        for root, dirs, files in os.walk (self.repo_path):
            dirs[:] = [d for d in  dirs if d not in self.SKIP_DIRS]
            for file in files:
                if file  in self.SKIP_FILES:
                    continue
                file_path = Path(root) / file
                extension = file_path.suffix
                
                if extension in self.SUPPORTED_EXTENSIONS:
                    rel_path = file_path.relative_to(self.repo_path)
                    print(f"rel_path is here {rel_path}")
                    self.files.append(rel_path)
        print(f"all file path  {self.files}")
        return self.files
    
    def get_file_stats(self) -> dict:
        stats = {'total_files': len(self.files), 'by_extension': {}, 'by_layer': {}}
        
        for file_path in self.files:
            ext = file_path.suffix
            stats['by_extension'][ext] = stats['by_extension'].get(ext, 0) + 1
            
            layer = self._detect_layer(str(file_path))
            stats['by_layer'][layer] = stats['by_layer'].get(layer, 0) + 1
        
        return stats
    
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


