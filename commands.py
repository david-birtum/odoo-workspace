from pathlib import Path

from gitutils import current_branch
from workspace import load_workspace
from utils import print_repo_status


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

        current = current_branch(repo_path)

        if current is None:
            print_repo_status(
                repo=repo,
                expected=expected,
                error="Unable to get current branch",
            )
            continue

        print_repo_status(
            repo=repo,
            current=current,
            expected=expected,
        )
