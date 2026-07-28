from pathlib import Path
import yaml


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

