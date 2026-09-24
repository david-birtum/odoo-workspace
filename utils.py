from typing import Optional, Sequence

def print_repo_status(
    repo: str,
    current: Optional[str] = None,
    expected: Optional[str] = None,
    error: Optional[str] = None,
    ahead: Optional[int] = None,
    dirty: Optional[bool] = None,
    tree_changes: Optional[Sequence[str]] = None,
) -> None:
    """
    Imprime el estado de un repositorio del workspace.
    """

    if error:
        print(f"❌ {repo}")
        print(f"    Error    : {error}")

        if expected:
            print(f"    Expected : {expected}")

        print()
        return

    if current != expected:
        print(f"⚠️  {repo}")
        print(f"    Current  : {current}")
        print(f"    Expected : {expected}")
    elif dirty or ahead:
        print(f"🟡 {repo}")
        print(f"    Branch   : {current}")
    else:
        print(f"✅ {repo}")
        print(f"    Branch   : {current}")

    if dirty:
        print("    Tree     : Uncommitted changes")
        for line in tree_changes or []:
            print(f"             {line}")

    if ahead:
        print(f"    Unpushed : {ahead} commit(s)")

    print()


def print_action_result(
    repo: str,
    status: str,
    reason: Optional[str] = None,
) -> None:
    """
    Imprime el resultado de una acción por repositorio (sync, switch).
    """

    icons = {
        "updated": "✅",
        "up-to-date": "✅",
        "switched": "✅",
        "already-on-branch": "✅",
        "skipped": "⏭️ ",
        "failed": "❌",
    }

    icon = icons.get(status, "•")

    print(f"{icon} {repo:<30} {status}", end="")

    if reason:
        print(f" — {reason}", end="")

    print()

