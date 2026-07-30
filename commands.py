from pathlib import Path
from workspace import load_workspace, list_workspaces
from gitutils import current_branch
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

            current = current_branch(repo_path)

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

    if not results:
        return

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
