from typing import Optional

def print_repo_status(
    repo: str,
    current: Optional[str] = None,
    expected: Optional[str] = None,
    error: Optional[str] = None,
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

    print()
    
