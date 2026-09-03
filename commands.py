from functools import partial
from pathlib import Path
from workspace import load_workspace, list_workspaces
from gitutils import current_branch, is_dirty, ahead_behind, fetch, pull_ff_only
from utils import print_repo_status, print_sync_result
from credentials import GitCredentials, run_with_fallback


def status(git_root: Path, version: str, workspace: str):

    data = load_workspace(
        git_root,
        version,
        workspace,
    )

    print()
    print(f"Workspace : {data['project']}")
    print(f"Version   : {data['version']}")
    print()

    repositories = data.get("repositories", {})

    for repo, info in repositories.items():

        expected = str(info["branch"]).strip()

        repo_path = (
            git_root
            / version
            / "odoo"
            / repo
        )

        if not repo_path.exists():
            print_repo_status(
                repo=repo,
                expected=expected,
                error="Repository not found",
            )
            continue

        current, error = current_branch(repo_path)

        if error:
            print_repo_status(
                repo=repo,
                expected=expected,
                error=f"Unable to get current branch: {error}",
            )
            continue

        ahead, _behind, ahead_error = ahead_behind(
            repo_path,
            fallback_ref=f"origin/{expected}",
        )

        print_repo_status(
            repo=repo,
            current=current,
            expected=expected,
            ahead=None if ahead_error else ahead,
        )

def sync(git_root: Path, version: str, workspace: str):
    """
    Actualiza automáticamente (git pull --ff-only) los repos del workspace
    que estén en la rama esperada, sin cambios sin commitear y sin commits
    por pushear. El resto se reporta como omitido con el motivo.
    """

    data = load_workspace(
        git_root,
        version,
        workspace,
    )

    print()
    print(f"Workspace : {data['project']}")
    print(f"Version   : {data['version']}")
    print()

    repositories = data.get("repositories", {})
    credentials = GitCredentials()

    try:
        for repo, info in repositories.items():

            expected = str(info["branch"]).strip()

            repo_path = (
                git_root
                / version
                / "odoo"
                / repo
            )

            if not repo_path.exists():
                print_sync_result(repo, "skipped", "Repository not found")
                continue

            current, error = current_branch(repo_path)

            if error:
                print_sync_result(
                    repo, "skipped",
                    f"Unable to get current branch: {error}",
                )
                continue

            if current != expected:
                print_sync_result(
                    repo, "skipped",
                    f"On branch '{current}', expected '{expected}'",
                )
                continue

            dirty, error = is_dirty(repo_path)

            if error:
                print_sync_result(
                    repo, "skipped",
                    f"Unable to check working tree: {error}",
                )
                continue

            if dirty:
                print_sync_result(
                    repo, "skipped",
                    "Uncommitted changes in working tree",
                )
                continue

            _, error = run_with_fallback(
                partial(fetch, branch=expected),
                repo_path,
                credentials,
            )

            if error:
                print_sync_result(repo, "skipped", f"Unable to fetch: {error}")
                continue

            ahead, behind, error = ahead_behind(
                repo_path,
                fallback_ref=f"origin/{expected}",
            )

            if error:
                print_sync_result(
                    repo, "skipped",
                    f"No upstream configured or unable to compare: {error}",
                )
                continue

            if ahead:
                print_sync_result(
                    repo, "skipped",
                    f"{ahead} unpushed commit(s)",
                )
                continue

            if behind == 0:
                print_sync_result(repo, "up-to-date")
                continue

            _, error = run_with_fallback(
                partial(pull_ff_only, branch=expected),
                repo_path,
                credentials,
            )

            if error:
                print_sync_result(repo, "failed", error)
                continue

            print_sync_result(repo, "updated", f"{behind} commit(s) pulled")
    finally:
        credentials.cleanup()

    print()

def current(git_root: Path, version: str):

    results = []

    for manifest in list_workspaces(git_root, version):

        workspace = manifest.stem

        data = load_workspace(
            git_root,
            version,
            workspace,
        )

        repositories = data.get("repositories", {})

        total = len(repositories)
        matches = 0
        differences = []

        for repo, info in repositories.items():

            expected = str(info["branch"]).strip()

            repo_path = (
                git_root
                / version
                / "odoo"
                / repo
            )

            if not repo_path.exists():
                differences.append(
                    (repo, "NOT FOUND", expected)
                )
                continue

            current, error = current_branch(repo_path)

            if error:
                differences.append(
                    (repo, f"ERROR: {error}", expected)
                )
                continue

            if current == expected:
                matches += 1
            else:
                differences.append(
                    (repo, current, expected)
                )

        percentage = 0 if total == 0 else (matches / total) * 100

        results.append({
            "workspace": workspace,
            "matches": matches,
            "total": total,
            "percentage": percentage,
            "differences": differences,
        })

    if not results:
        print()
        print(f"No workspace manifests found for version {version}.")
        print()
        return

    results.sort(
        key=lambda r: (r["percentage"], r["matches"]),
        reverse=True,
    )

    print()
    print("Workspace ranking")
    print("=" * 70)

    medals = ["🥇", "🥈", "🥉"]

    for idx, result in enumerate(results):

        medal = medals[idx] if idx < 3 else " "

        print(
            f"{medal} "
            f"{result['workspace']:<20} "
            f"{result['matches']:>2}/{result['total']:<2} "
            f"({result['percentage']:5.1f}%)"
        )

    print()

    best = results[0]

    print(f"Current workspace: {best['workspace']}")
    print()

    if not best["differences"]:
        print("✅ All repositories match the manifest.")
        return

    print("Repositories with differences:\n")

    for repo, current_branch_name, expected in best["differences"]:

        print(f"⚠ {repo}")
        print(f"    Current  : {current_branch_name}")
        print(f"    Expected : {expected}")
        print()
