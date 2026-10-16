from pathlib import Path
from utils import print_repo_status, print_action_result
from service import collect_status, collect_current, collect_sync, collect_switch


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
            tree_changes=row.get("tree_changes"),
            wip=row.get("wip", False),
            merged_into=row.get("merged_into"),
        )


def _print_action_payload(payload: dict):

    print()
    print(f"Workspace : {payload['project']}")
    print(f"Version   : {payload['version']}")

    if payload.get("mode") == "manifest":
        print("Mode      : manifest (YAML branches, work branches forgotten)")
    elif payload.get("mode") == "resume":
        print("Mode      : resume work branches")

    print()

    saved = payload.get("saved_branches") or {}

    if saved:
        print(f"Saved work branches of {payload['left_workspace']}:")

        for repo, branch in saved.items():
            print(f"    {repo:<30} {branch}")

        print()

    for row in payload["results"]:
        print_action_result(row["repo"], row["status"], row.get("reason"))

    skipped = sum(
        1 for row in payload["results"]
        if row["status"] in ("skipped", "failed")
    )

    if skipped:
        print()
        print(f"⚠️  {skipped} repo(s) skipped/failed — see the reasons above.")

    if payload.get("needs_credentials"):
        print()
        print(
            "Some repos were skipped because Git credentials are required. "
            "Fill username/token in the UI or run from a terminal."
        )

    print()


def sync(git_root: Path, version: str, workspace: str):
    """
    Actualiza automáticamente (git pull --ff-only) los repos del workspace
    que estén en la rama esperada, sin cambios sin commitear y sin commits
    por pushear. El resto se reporta como omitido con el motivo.
    """

    _print_action_payload(collect_sync(git_root, version, workspace))


def switch(git_root: Path, version: str, workspace: str, manifest: bool = False):
    """
    Cambia (git checkout) cada repo del workspace a su rama de trabajo
    recordada o, si no hay, a la del manifest (``manifest=True`` fuerza
    siempre la del manifest). No toca repos con cambios sin commitear ni
    con commits locales sin pushear. No hace pull — eso es ``sync``.
    """

    _print_action_payload(
        collect_switch(git_root, version, workspace, manifest=manifest)
    )


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
