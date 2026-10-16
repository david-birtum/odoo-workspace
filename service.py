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
    is_merged_into,
)
from credentials import GitCredentials, CredentialRequired, run_with_fallback
from state import (
    get_active_workspace,
    set_active_workspace,
    get_remembered,
    remember_branches,
    forget_workspace,
    forget_repo,
)


def status_kind(row: dict) -> str:
    """
    Misma clasificación que ``ows status``: error, wip, mismatch, blocked, ok.
    """

    if row.get("error"):
        return "error"

    if row.get("current") != row.get("expected"):
        return "wip" if row.get("wip") else "mismatch"

    if row.get("dirty") or row.get("ahead"):
        return "blocked"

    return "ok"


def manifest_branches(git_root: Path, version: str) -> dict:
    """
    ``{repo: {ramas}}`` declaradas en cualquier manifest de la versión.
    """

    branches = {}

    for manifest in list_workspaces(git_root, version):
        data = load_workspace(git_root, version, manifest.stem)

        for repo, info in (data.get("repositories") or {}).items():
            branches.setdefault(repo, set()).add(str(info["branch"]).strip())

    return branches


def is_work_branch(
    repo: str,
    branch: str | None,
    expected: str,
    known_branches: dict,
    remembered: dict,
) -> bool:
    """
    Rama de trabajo en curso: distinta a la esperada y, o bien recordada
    para el workspace, o bien no declarada en ningún manifest de la versión.
    """

    if not branch or branch == expected:
        return False

    if remembered.get(repo) == branch:
        return True

    return branch not in known_branches.get(repo, set())


def _merged_into_expected(path: Path, branch: str, expected: str) -> bool:
    return bool(is_merged_into(path, branch, f"origin/{expected}"))


def snapshot_work_branches(
    git_root: Path,
    version: str,
    workspace: str,
    known_branches: dict | None = None,
) -> dict:
    """
    Guarda en el estado local las ramas de trabajo en las que están ahora
    los repos de ``workspace``. Reemplaza lo recordado antes.
    """

    data = load_workspace(git_root, version, workspace)
    known = known_branches if known_branches is not None else manifest_branches(git_root, version)
    remembered = get_remembered(version, workspace)
    branches = {}

    for repo, info in (data.get("repositories") or {}).items():

        expected = str(info["branch"]).strip()
        path = repo_path(git_root, version, repo)

        if not path.exists():
            continue

        current, error = current_branch(path)

        if error or not current:
            continue

        if is_work_branch(repo, current, expected, known, remembered):
            branches[repo] = current

    remember_branches(version, workspace, branches)

    return branches


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
        "wip": False,
        "merged_into": None,
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
    known = manifest_branches(git_root, version)
    remembered = get_remembered(version, workspace)

    repos = []

    for repo, info in repositories.items():
        expected = str(info["branch"]).strip()
        row = collect_repo_status(git_root, version, repo, expected)

        if row["error"] is None and is_work_branch(
            repo, row["current"], expected, known, remembered,
        ):
            row["wip"] = True
            path = repo_path(git_root, version, repo)

            if _merged_into_expected(path, row["current"], expected):
                row["merged_into"] = expected

        repos.append(row)

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
    known = manifest_branches(git_root, version)
    remembered = get_remembered(version, workspace)

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
                if is_work_branch(repo, current, expected, known, remembered):
                    reason = (
                        f"Work in progress on '{current}' "
                        f"(sync only updates '{expected}')"
                    )
                else:
                    reason = f"On branch '{current}', expected '{expected}'"

                result = _action_result(repo, "skipped", reason)
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
    manifest: bool = False,
) -> dict:
    """
    Misma lógica que ``ows switch``. Devuelve resultados por repo.

    Antes de mover nada, guarda las ramas de trabajo del workspace del que
    se sale (el último al que se hizo switch, o el mejor del ranking).
    Por defecto retoma las ramas recordadas de ``workspace``; con
    ``manifest=True`` usa siempre la rama del YAML y olvida lo recordado.
    """

    data = load_workspace(git_root, version, workspace)
    repositories = data.get("repositories", {})
    results = []
    needs_credentials = False
    known = manifest_branches(git_root, version)

    leaving = get_active_workspace(version)

    if leaving is None:
        ranking = collect_current(git_root, version)["results"]
        leaving = ranking[0]["workspace"] if ranking else None

    saved_branches = {}

    if leaving and not (manifest and leaving == workspace):
        try:
            saved_branches = snapshot_work_branches(git_root, version, leaving, known)
        except FileNotFoundError:
            saved_branches = {}

    remembered = {} if manifest else get_remembered(version, workspace)

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

            target = expected
            resumed = False
            notes = []
            wanted = remembered.get(repo)

            if wanted:
                if local_branch_exists(path, wanted):
                    target = wanted
                    resumed = True
                else:
                    forget_repo(version, workspace, repo)
                    notes.append(
                        f"remembered branch '{wanted}' no longer exists locally"
                    )

            if resumed:
                notes.insert(0, "work in progress")

                if _merged_into_expected(path, target, expected):
                    notes.insert(1, f"already merged into {expected}")

            if current == target:
                result = _action_result(
                    repo, "already-on-branch",
                    " · ".join(notes) or None,
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

            if not resumed and not local_branch_exists(path, expected):
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
                f"Checking out {target}",
            )
            _, error = checkout(path, target)

            if error:
                result = _action_result(repo, "failed", error)
                results.append(result)
                _progress_repo_done(progress_callback, result)
                continue

            reason = f"'{current}' → '{target}'"

            if notes:
                reason = f"{reason} ({' · '.join(notes)})"

            result = _action_result(
                repo, "resumed" if resumed else "switched",
                reason,
            )
            results.append(result)
            _progress_repo_done(progress_callback, result)

        if manifest:
            forget_workspace(version, workspace)

        set_active_workspace(version, workspace)
    finally:
        credentials.cleanup()

    return {
        "project": data["project"],
        "version": data["version"],
        "action": "switch",
        "mode": "manifest" if manifest else "resume",
        "left_workspace": leaving,
        "saved_branches": saved_branches,
        "results": results,
        "needs_credentials": needs_credentials,
    }
