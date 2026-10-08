from functools import partial
from pathlib import Path

from workspace import load_workspace, list_workspaces, repo_path
from gitutils import (
    current_branch,
    is_dirty,
    ahead_behind,
    fetch,
    pull_ff_only,
    local_branch_exists,
    checkout,
    working_tree_changes,
)
from credentials import GitCredentials, CredentialRequired, run_with_fallback


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
        "tree_changes": [],
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

    dirty, tree_changes, dirty_error = working_tree_changes(path)
    row["dirty"] = dirty
    row["tree_changes"] = tree_changes

    if dirty_error and row["error"] is None:
        row["error"] = f"Unable to read working tree: {dirty_error}"

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


def _action_result(repo: str, status: str, reason: str | None = None) -> dict:
    return {
        "repo": repo,
        "status": status,
        "reason": reason,
    }


def _emit_progress(progress_callback, event: dict) -> None:
    if progress_callback is not None:
        progress_callback(event)


def _progress_repo_start(progress_callback, repo: str, index: int, total: int) -> None:
    _emit_progress(progress_callback, {
        "type": "repo_start",
        "repo": repo,
        "index": index,
        "total": total,
        "step": "Starting",
    })


def _progress_repo_step(progress_callback, repo: str, step: str) -> None:
    _emit_progress(progress_callback, {
        "type": "repo_step",
        "repo": repo,
        "step": step,
    })


def _progress_repo_done(progress_callback, result: dict) -> None:
    _emit_progress(progress_callback, {
        "type": "repo_done",
        "repo": result["repo"],
        "result": result,
    })


def collect_sync(
    git_root: Path,
    version: str,
    workspace: str,
    credentials_provider=None,
    progress_callback=None,
) -> dict:
    """
    Misma lógica que ``ows sync``. Devuelve resultados por repo.
    """

    data = load_workspace(git_root, version, workspace)
    repositories = data.get("repositories", {})
    results = []
    needs_credentials = False

    credentials = GitCredentials(provider=credentials_provider)
    total = len(repositories)

    try:
        for index, (repo, info) in enumerate(repositories.items(), start=1):

            _progress_repo_start(progress_callback, repo, index, total)
            expected = str(info["branch"]).strip()
            path = repo_path(git_root, version, repo)

            if not path.exists():
                result = _action_result(repo, "skipped", "Repository not found")
                results.append(result)
                _progress_repo_done(progress_callback, result)
                continue

            _progress_repo_step(progress_callback, repo, "Reading current branch")
            current, error = current_branch(path)

            if error:
                result = _action_result(
                    repo, "skipped",
                    f"Unable to get current branch: {error}",
                )
                results.append(result)
                _progress_repo_done(progress_callback, result)
                continue

            if current != expected:
                result = _action_result(
                    repo, "skipped",
                    f"On branch '{current}', expected '{expected}'",
                )
                results.append(result)
                _progress_repo_done(progress_callback, result)
                continue

            _progress_repo_step(progress_callback, repo, "Checking working tree")
            dirty, error = is_dirty(path)

            if error:
                result = _action_result(
                    repo, "skipped",
                    f"Unable to check working tree: {error}",
                )
                results.append(result)
                _progress_repo_done(progress_callback, result)
                continue

            if dirty:
                result = _action_result(
                    repo, "skipped",
                    "Uncommitted changes in working tree",
                )
                results.append(result)
                _progress_repo_done(progress_callback, result)
                continue

            _progress_repo_step(
                progress_callback, repo,
                f"Fetching origin/{expected}",
            )
            try:
                _, error = run_with_fallback(
                    partial(fetch, branch=expected),
                    path,
                    credentials,
                )
            except CredentialRequired:
                needs_credentials = True
                result = _action_result(
                    repo, "skipped",
                    "Git credentials required (HTTPS)",
                )
                results.append(result)
                _progress_repo_done(progress_callback, result)
                continue

            if error:
                result = _action_result(repo, "skipped", f"Unable to fetch: {error}")
                results.append(result)
                _progress_repo_done(progress_callback, result)
                continue

            _progress_repo_step(progress_callback, repo, "Comparing with remote")
            ahead, behind, error = ahead_behind(
                path,
                fallback_ref=f"origin/{expected}",
            )

            if error:
                result = _action_result(
                    repo, "skipped",
                    f"No upstream configured or unable to compare: {error}",
                )
                results.append(result)
                _progress_repo_done(progress_callback, result)
                continue

            if ahead:
                result = _action_result(
                    repo, "skipped",
                    f"{ahead} unpushed commit(s)",
                )
                results.append(result)
                _progress_repo_done(progress_callback, result)
                continue

            if behind == 0:
                result = _action_result(repo, "up-to-date")
                results.append(result)
                _progress_repo_done(progress_callback, result)
                continue

            _progress_repo_step(
                progress_callback, repo,
                f"Pulling {behind} commit(s) (fast-forward)",
            )
            try:
                _, error = run_with_fallback(
                    partial(pull_ff_only, branch=expected),
                    path,
                    credentials,
                )
            except CredentialRequired:
                needs_credentials = True
                result = _action_result(
                    repo, "skipped",
                    "Git credentials required (HTTPS)",
                )
                results.append(result)
                _progress_repo_done(progress_callback, result)
                continue

            if error:
                result = _action_result(repo, "failed", error)
                results.append(result)
                _progress_repo_done(progress_callback, result)
                continue

            result = _action_result(repo, "updated", f"{behind} commit(s) pulled")
            results.append(result)
            _progress_repo_done(progress_callback, result)
    finally:
        credentials.cleanup()

    return {
        "project": data["project"],
        "version": data["version"],
        "action": "sync",
        "results": results,
        "needs_credentials": needs_credentials,
    }


def collect_switch(
    git_root: Path,
    version: str,
    workspace: str,
    credentials_provider=None,
    progress_callback=None,
) -> dict:
    """
    Misma lógica que ``ows switch``. Devuelve resultados por repo.
    """

    data = load_workspace(git_root, version, workspace)
    repositories = data.get("repositories", {})
    results = []
    needs_credentials = False

    credentials = GitCredentials(provider=credentials_provider)
    total = len(repositories)

    try:
        for index, (repo, info) in enumerate(repositories.items(), start=1):

            _progress_repo_start(progress_callback, repo, index, total)
            expected = str(info["branch"]).strip()
            path = repo_path(git_root, version, repo)

            if not path.exists():
                result = _action_result(repo, "skipped", "Repository not found")
                results.append(result)
                _progress_repo_done(progress_callback, result)
                continue

            _progress_repo_step(progress_callback, repo, "Reading current branch")
            current, error = current_branch(path)

            if error:
                result = _action_result(
                    repo, "skipped",
                    f"Unable to get current branch: {error}",
                )
                results.append(result)
                _progress_repo_done(progress_callback, result)
                continue

            if current == expected:
                result = _action_result(repo, "already-on-branch")
                results.append(result)
                _progress_repo_done(progress_callback, result)
                continue

            _progress_repo_step(progress_callback, repo, "Checking working tree")
            dirty, error = is_dirty(path)

            if error:
                result = _action_result(
                    repo, "skipped",
                    f"Unable to check working tree: {error}",
                )
                results.append(result)
                _progress_repo_done(progress_callback, result)
                continue

            if dirty:
                result = _action_result(
                    repo, "skipped",
                    "Uncommitted changes in working tree",
                )
                results.append(result)
                _progress_repo_done(progress_callback, result)
                continue

            _progress_repo_step(progress_callback, repo, "Checking unpushed commits")
            ahead, _behind, ahead_error = ahead_behind(
                path,
                fallback_ref=f"origin/{current}",
            )

            if not ahead_error and ahead:
                result = _action_result(
                    repo, "skipped",
                    f"{ahead} unpushed commit(s) on '{current}'",
                )
                results.append(result)
                _progress_repo_done(progress_callback, result)
                continue

            if not local_branch_exists(path, expected):
                _progress_repo_step(
                    progress_callback, repo,
                    f"Fetching origin/{expected}",
                )
                try:
                    _, error = run_with_fallback(
                        partial(fetch, branch=expected),
                        path,
                        credentials,
                    )
                except CredentialRequired:
                    needs_credentials = True
                    result = _action_result(
                        repo, "skipped",
                        "Git credentials required (HTTPS)",
                    )
                    results.append(result)
                    _progress_repo_done(progress_callback, result)
                    continue

                if error:
                    result = _action_result(
                        repo, "skipped",
                        f"Unable to fetch '{expected}': {error}",
                    )
                    results.append(result)
                    _progress_repo_done(progress_callback, result)
                    continue

            _progress_repo_step(
                progress_callback, repo,
                f"Checking out {expected}",
            )
            _, error = checkout(path, expected)

            if error:
                result = _action_result(repo, "failed", error)
                results.append(result)
                _progress_repo_done(progress_callback, result)
                continue

            result = _action_result(
                repo, "switched",
                f"'{current}' → '{expected}'",
            )
            results.append(result)
            _progress_repo_done(progress_callback, result)
    finally:
        credentials.cleanup()

    return {
        "project": data["project"],
        "version": data["version"],
        "action": "switch",
        "results": results,
        "needs_credentials": needs_credentials,
    }
