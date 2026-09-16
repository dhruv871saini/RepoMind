from pathlib import Path
from git import Repo
import shutil


BASE_DIR = Path("repositories")


def sanitize_repo_name(repo_url: str) -> str:
    name = repo_url.rstrip("/").split("/")[-1]

    if name.endswith(".git"):
        name = name[:-4]

    return name


def clone_repo(repo_url: str, force: bool = False) -> dict | None:
    BASE_DIR.mkdir(exist_ok=True)
    new_files = []
    edited_files = []
    deleted_files = []
    repo_name = sanitize_repo_name(repo_url)
    repo_path = BASE_DIR / repo_name

    if force and repo_path.exists():
        shutil.rmtree(repo_path)
        print(f" force wipe: deleted {repo_path}")

    if not repo_path.exists():
        print(f" cloning {repo_url}...")
        repo =  Repo.clone_from(repo_url, repo_path)
        sha = repo.head.commit.hexsha

        print(f"Fresh clone completed: {sha}")

        return {
            "repo_path": str(repo_path),
            "new_sha": sha,
            "added": [],
            "modified": [],
            "deleted": [],
            "is_fresh_clone": True,
        }

    else:
        print(f" repository already exists: {repo_path}")

    repo = Repo(repo_path)

    print(f" fetching {repo_url}...")
    repo.remotes.origin.fetch()

    old = repo.head.commit.hexsha
    sha = repo.remotes.origin.refs[repo.active_branch.name].commit.hexsha


    if old == sha:
        print("Repo is up to date")
        return {
            "repo_path": str(repo_path),
            "new_sha": sha,
            "added": new_files,
            "modified": edited_files,
            "deleted": deleted_files,   
            "is_fresh_clone": False
        }
    print(f"diff===>>>{repo.git.diff(old, sha)}")
    print(f"\n\n\n\n\n\n diff==>wertyuio{ repo.commit(old).diff(repo.commit(sha))}")
    changes = repo.git.diff(
    "--name-status",
    old,
    sha
    )


    for line in changes.splitlines():
        status, path = line.split("\t", 1)

        if status == "A":
            new_files.append(path)
        elif status == "M":
            edited_files.append(path)
        elif status == "D":
            deleted_files.append(path)

    print("New files:", new_files)
    print("Edited files:", edited_files)
    print("Deleted files:", deleted_files)

    print(changes)
    print(f"Repository ready at: {repo_path}")

    return {
    "repo_path": str(repo_path),
    "new_sha": sha,
    "added": new_files,
    "modified": edited_files,
    "deleted": deleted_files,
    "is_fresh_clone": False
    }
