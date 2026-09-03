from typing import Optional

def print_repo_status(
    repo: str,
    current: Optional[str] = None,
    expected: Optional[str] = None,
    error: Optional[str] = None,
    ahead: Optional[int] = None,
    dirty: Optional[bool] = None,
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

    if current == expected:
        print(f"✅ {repo}")
        print(f"    Branch   : {current}")
    else:
        print(f"⚠️  {repo}")
        print(f"    Current  : {current}")
        print(f"    Expected : {expected}")

    if dirty:
        print("    Tree     : Uncommitted changes")

    if ahead:
        print(f"    Unpushed : {ahead} commit(s)")

    print()


def print_sync_result(
    repo: str,
    status: str,
    reason: Optional[str] = None,
) -> None:
    """
    Imprime el resultado de intentar sincronizar (pull) un repositorio.
    """

    icons = {
        "updated": "✅",
        "up-to-date": "✅",
        "skipped": "⏭️ ",
        "failed": "❌",
    }

    icon = icons.get(status, "•")

    print(f"{icon} {repo:<30} {status}", end="")

    if reason:
        print(f" — {reason}", end="")

    print()

