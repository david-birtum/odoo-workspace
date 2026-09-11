from pathlib import Path

from workspace import load_workspace, list_workspaces, repo_path
from gitutils import current_branch, is_dirty, ahead_behind


def status_kind(row: dict) -> str:
    """
    Misma clasificación que ``ows status``: error, mismatch, blocked, ok.
    """

    if row.get("error"):
        return "error"

    if row.get("current") != row.get("expected"):
        return "mismatch"

    if row.get("dirty") or row.get("ahead"):
        return "blocked"

    return "ok"


def collect_repo_status(git_root: Path, version: str, repo: str, expected: str) -> dict:
    """
    Estado de un repo frente a la rama esperada. No imprime ni toca git
    más allá de lecturas (branch, dirty, ahead).
    """

    row = {
        "repo": repo,
        "current": None,
        "expected": expected,
        "ahead": None,
        "dirty": None,
        "error": None,
    }

    path = repo_path(git_root, version, repo)

    if not path.exists():
        row["error"] = "Repository not found"
        return row

    current, error = current_branch(path)

    if error:
        row["error"] = f"Unable to get current branch: {error}"
        return row

    row["current"] = current

    ahead, _behind, ahead_error = ahead_behind(
        path,
        fallback_ref=f"origin/{current}",
    )
    row["ahead"] = None if ahead_error else ahead

    dirty, _dirty_error = is_dirty(path)
    row["dirty"] = dirty

    return row


def collect_status(git_root: Path, version: str, workspace: str) -> dict:

    data = load_workspace(git_root, version, workspace)
    repositories = data.get("repositories", {})

    repos = []

    for repo, info in repositories.items():
        expected = str(info["branch"]).strip()
        repos.append(collect_repo_status(git_root, version, repo, expected))

    return {
        "project": data["project"],
        "version": data["version"],
        "repos": repos,
    }


def collect_current(git_root: Path, version: str) -> dict:

    results = []

    for manifest in list_workspaces(git_root, version):

        workspace = manifest.stem
        data = load_workspace(git_root, version, workspace)
        repositories = data.get("repositories", {})

        total = len(repositories)
        matches = 0
        differences = []

        for repo, info in repositories.items():

            expected = str(info["branch"]).strip()
            path = repo_path(git_root, version, repo)

            if not path.exists():
                differences.append(
                    {
                        "repo": repo,
                        "current": "NOT FOUND",
                        "expected": expected,
                    }
                )
                continue

            current, error = current_branch(path)

            if error:
                differences.append(
                    {
                        "repo": repo,
                        "current": f"ERROR: {error}",
                        "expected": expected,
                    }
                )
                continue

            if current == expected:
                matches += 1
            else:
                differences.append(
                    {
                        "repo": repo,
                        "current": current,
                        "expected": expected,
                    }
                )

        percentage = 0 if total == 0 else (matches / total) * 100

        results.append({
            "workspace": workspace,
            "matches": matches,
            "total": total,
            "percentage": percentage,
            "differences": differences,
        })

    results.sort(
        key=lambda r: (r["percentage"], r["matches"]),
        reverse=True,
    )

    return {
        "version": version,
        "results": results,
    }
