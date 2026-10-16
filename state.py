import json
import os
import tempfile
from pathlib import Path


def state_path() -> Path:
    """
    Archivo de estado local de ``ows`` (fuera de los repos, sin git).
    ``OWS_STATE_FILE`` lo sobreescribe; si no, ``$XDG_STATE_HOME/ows`` o
    ``~/.local/state/ows``.
    """

    override = os.environ.get("OWS_STATE_FILE")

    if override:
        return Path(override)

    base = os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state"

    return Path(base) / "ows" / "state.json"


def load_state() -> dict:

    path = state_path()

    if not path.exists():
        return {}

    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}

    return data if isinstance(data, dict) else {}


def save_state(data: dict) -> None:

    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(prefix=".state-", dir=path.parent)

    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)

    os.replace(tmp_path, path)


def _version_state(data: dict, version: str) -> dict:
    return data.setdefault("versions", {}).setdefault(str(version), {})


def get_active_workspace(version: str) -> str | None:
    """Último workspace al que se hizo switch en esa versión."""

    return (
        load_state()
        .get("versions", {})
        .get(str(version), {})
        .get("active")
    )


def set_active_workspace(version: str, workspace: str) -> None:

    data = load_state()
    _version_state(data, version)["active"] = workspace
    save_state(data)


def get_remembered(version: str, workspace: str) -> dict:
    """
    Ramas de trabajo recordadas para un workspace: ``{repo: rama}``.
    """

    return dict(
        load_state()
        .get("versions", {})
        .get(str(version), {})
        .get("workspaces", {})
        .get(workspace, {})
    )


def remember_branches(version: str, workspace: str, branches: dict) -> None:
    """Reemplaza las ramas recordadas del workspace (vacío = olvidar)."""

    data = load_state()
    workspaces = _version_state(data, version).setdefault("workspaces", {})

    if branches:
        workspaces[workspace] = dict(branches)
    else:
        workspaces.pop(workspace, None)

    save_state(data)


def forget_workspace(version: str, workspace: str) -> None:
    remember_branches(version, workspace, {})


def forget_repo(version: str, workspace: str, repo: str) -> None:

    branches = get_remembered(version, workspace)

    if branches.pop(repo, None) is not None:
        remember_branches(version, workspace, branches)
