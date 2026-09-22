from pathlib import Path
from git import Repo
import shutil


BASE_DIR = Path("repositories")


def sanitize_repo_name(repo_url: str) -> str:
    name = repo_url.rstrip("/").split("/")[-1]

    if name.endswith(".git"):
        name = name[:-4]

    return name


def clone_repo(repo_url: str, force: bool = False) -> dict:
    BASE_DIR.mkdir(exist_ok=True)

    added: list[str] = []
    modified: list[str] = []
    deleted: list[str] = []

    repo_name = sanitize_repo_name(repo_url)
    repo_path = BASE_DIR / repo_name

    if force and repo_path.exists():
        shutil.rmtree(repo_path)
        print(f" force wipe: deleted {repo_path}")

    if not repo_path.exists():
        print(f" cloning {repo_url}...")
        repo = Repo.clone_from(repo_url, repo_path)
        sha = repo.head.commit.hexsha
        print(f" fresh clone completed: {sha[:8]}")
        return {
            "repo_path": str(repo_path),
            "new_sha": sha,
            "added": added,
            "modified": modified,
            "deleted": deleted,
            "state": "fresh",
        }

    print(f" repository already exists: {repo_path}")
    repo = Repo(repo_path)

    print(f" fetching {repo_url}...")
    repo.remotes.origin.fetch()

    old = repo.head.commit.hexsha
    sha = repo.remotes.origin.refs[repo.active_branch.name].commit.hexsha

    if old == sha:
        print(" repo is up to date")
        return {
            "repo_path": str(repo_path),
            "new_sha": sha,
            "added": added,
            "modified": modified,
            "deleted": deleted,
            "state": "up_to_date",
        }
    print(f"diff===>>>{repo.git.diff(old, sha)}")

    changes = repo.git.diff("--name-status", old, sha)
    print(f"changes of file ===>>  {changes}")
    for line in changes.splitlines():
        parts = line.split("\t")
        status = parts[0]
        if status.startswith("R") or status.startswith("C"):
            if len(parts) >= 3:
                deleted.append(parts[1])
                added.append(parts[2])
            continue
        path = parts[1] if len(parts) > 1 else ""
        if not path:
            continue
        if status == "A":
            added.append(path)
        elif status == "M":
            modified.append(path)
        elif status == "D":
            deleted.append(path)

    print(f" added={added}")
    print(f" modified={modified}")
    print(f" deleted={deleted}")

    # Apply remote changes to local disk before incremental sync reads files
    print(f" pulling {repo_url}...")
    repo.remotes.origin.pull()

    return {
        "repo_path": str(repo_path),
        "new_sha": sha,
        "added": added,
        "modified": modified,
        "deleted": deleted,
        "state": "changed",
    }
