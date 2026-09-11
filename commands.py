from functools import partial
from pathlib import Path
from workspace import load_workspace
from gitutils import (
    current_branch,
    is_dirty,
    ahead_behind,
    fetch,
    pull_ff_only,
    local_branch_exists,
    checkout,
)
from utils import print_repo_status, print_action_result
from credentials import GitCredentials, run_with_fallback
from service import collect_status, collect_current


def status(git_root: Path, version: str, workspace: str):

    payload = collect_status(git_root, version, workspace)

    print()
    print(f"Workspace : {payload['project']}")
    print(f"Version   : {payload['version']}")
    print()

    for row in payload["repos"]:
        print_repo_status(
            repo=row["repo"],
            current=row["current"],
            expected=row["expected"],
            error=row["error"],
            ahead=row["ahead"],
            dirty=row["dirty"],
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
                print_action_result(repo, "skipped", "Repository not found")
                continue

            current, error = current_branch(repo_path)

            if error:
                print_action_result(
                    repo, "skipped",
                    f"Unable to get current branch: {error}",
                )
                continue

            if current != expected:
                print_action_result(
                    repo, "skipped",
                    f"On branch '{current}', expected '{expected}'",
                )
                continue

            dirty, error = is_dirty(repo_path)

            if error:
                print_action_result(
                    repo, "skipped",
                    f"Unable to check working tree: {error}",
                )
                continue

            if dirty:
                print_action_result(
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
                print_action_result(repo, "skipped", f"Unable to fetch: {error}")
                continue

            ahead, behind, error = ahead_behind(
                repo_path,
                fallback_ref=f"origin/{expected}",
            )

            if error:
                print_action_result(
                    repo, "skipped",
                    f"No upstream configured or unable to compare: {error}",
                )
                continue

            if ahead:
                print_action_result(
                    repo, "skipped",
                    f"{ahead} unpushed commit(s)",
                )
                continue

            if behind == 0:
                print_action_result(repo, "up-to-date")
                continue

            _, error = run_with_fallback(
                partial(pull_ff_only, branch=expected),
                repo_path,
                credentials,
            )

            if error:
                print_action_result(repo, "failed", error)
                continue

            print_action_result(repo, "updated", f"{behind} commit(s) pulled")
    finally:
        credentials.cleanup()

    print()


def switch(git_root: Path, version: str, workspace: str):
    """
    Cambia (git checkout) cada repo del workspace a la rama esperada
    por el manifest. No toca repos con cambios sin commitear ni con
    commits locales sin pushear. No hace pull — eso es ``sync``.
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
                print_action_result(repo, "skipped", "Repository not found")
                continue

            current, error = current_branch(repo_path)

            if error:
                print_action_result(
                    repo, "skipped",
                    f"Unable to get current branch: {error}",
                )
                continue

            if current == expected:
                print_action_result(repo, "already-on-branch")
                continue

            dirty, error = is_dirty(repo_path)

            if error:
                print_action_result(
                    repo, "skipped",
                    f"Unable to check working tree: {error}",
                )
                continue

            if dirty:
                print_action_result(
                    repo, "skipped",
                    "Uncommitted changes in working tree",
                )
                continue

            ahead, _behind, ahead_error = ahead_behind(
                repo_path,
                fallback_ref=f"origin/{current}",
            )

            if not ahead_error and ahead:
                print_action_result(
                    repo, "skipped",
                    f"{ahead} unpushed commit(s) on '{current}'",
                )
                continue

            if not local_branch_exists(repo_path, expected):
                _, error = run_with_fallback(
                    partial(fetch, branch=expected),
                    repo_path,
                    credentials,
                )

                if error:
                    print_action_result(
                        repo, "skipped",
                        f"Unable to fetch '{expected}': {error}",
                    )
                    continue

            _, error = checkout(repo_path, expected)

            if error:
                print_action_result(repo, "failed", error)
                continue

            print_action_result(
                repo, "switched",
                f"'{current}' → '{expected}'",
            )
    finally:
        credentials.cleanup()

    print()


def current(git_root: Path, version: str):

    payload = collect_current(git_root, version)
    results = payload["results"]

    if not results:
        print()
        print(f"No workspace manifests found for version {version}.")
        print()
        return

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

    for diff in best["differences"]:

        print(f"⚠ {diff['repo']}")
        print(f"    Current  : {diff['current']}")
        print(f"    Expected : {diff['expected']}")
        print()
