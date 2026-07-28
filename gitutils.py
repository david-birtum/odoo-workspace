import subprocess


def git(repo_path, *args):

    result = subprocess.run(
        ["git", *args],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        return None

    return result.stdout.strip()


def current_branch(repo_path):

    return git(
        repo_path,
        "branch",
        "--show-current",
    )

