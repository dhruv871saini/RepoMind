from pathlib import Path
from git import Repo
import shutil


BASE_DIR = Path("repositories")


def sanitize_repo_name(repo_url: str) -> str:
    
    name = repo_url.rstrip("/").split("/")[-1]

    if name.endswith(".git"):
        name = name[:-4]

    return name


def clone_repo(repo_url: str, force: bool = False) -> str:

    BASE_DIR.mkdir(exist_ok=True)

    repo_name = sanitize_repo_name(repo_url)
    repo_path = BASE_DIR / repo_name

    if repo_path.exists():
        if force:
            shutil.rmtree(repo_path)
        else:
            print(f"Repository already exists: {repo_path}")
            return str(repo_path)

    print(f"Cloning {repo_url}...")
    Repo.clone_from(repo_url, repo_path)

    print(f"Repository cloned to: {repo_path}")

    return str(repo_path)

