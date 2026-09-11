from pathlib import Path
import yaml


def repo_path(git_root: Path, version: str, repo: str) -> Path:
    return git_root / version / "odoo" / repo


def list_versions(git_root: Path):
    """
    Versiones de Odoo bajo ``git_root`` que tienen al menos un
    manifest ``workspace/*.yaml``.
    """

    versions = []

    if not git_root.is_dir():
        return versions

    for path in sorted(git_root.iterdir()):
        if not path.is_dir():
            continue

        workspace_dir = path / "workspace"

        if workspace_dir.is_dir() and any(workspace_dir.glob("*.yaml")):
            versions.append(path.name)

    return versions


def load_workspace(git_root: Path, version: str, workspace: str):

    manifest = (
        git_root
        / version
        / "workspace"
        / f"{workspace}.yaml"
    )

    if not manifest.exists():
        raise FileNotFoundError(manifest)

    with open(manifest) as f:
        return yaml.safe_load(f)

def list_workspaces(git_root: Path, version: str):

    workspace_dir = (
        git_root
        / version
        / "workspace"
    )

    if not workspace_dir.is_dir():
        return []

    return sorted(workspace_dir.glob("*.yaml"))


def list_workspace_names(git_root: Path, version: str):
    return [path.stem for path in list_workspaces(git_root, version)]
