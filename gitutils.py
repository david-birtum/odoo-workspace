import subprocess


def git(repo_path, *args, env=None):

    result = subprocess.run(
        ["git", *args],
        cwd=repo_path,
        capture_output=True,
        text=True,
        env=env,
    )

    if result.returncode != 0:
        return None, result.stderr.strip()

    return result.stdout.strip(), None


def current_branch(repo_path):

    return git(
        repo_path,
        "branch",
        "--show-current",
    )


def is_dirty(repo_path):

    output, error = git(repo_path, "status", "--porcelain")

    if error is not None:
        return None, error

    return bool(output), None


def _porcelain_change_label(index_status: str, worktree_status: str) -> str:
    """
    Etiqueta legible para una línea ``git status --porcelain`` (XY).
    """

    if index_status == "?" and worktree_status == "?":
        return "untracked"

    if index_status == "R" or worktree_status == "R":
        return "renamed"

    if index_status == "C" or worktree_status == "C":
        return "copied"

    if index_status == "D" or worktree_status == "D":
        return "deleted"

    if index_status == "A" or worktree_status == "A":
        return "added"

    if index_status == "M" or worktree_status == "M":
        return "modified"

    if index_status == "U" or worktree_status == "U":
        return "unmerged"

    return "changed"


def parse_porcelain(output: str) -> list[str]:
    """
    Convierte la salida de ``git status --porcelain`` en líneas tipo
    ``modified   path/to/file`` (similar a ``git status -s`` ampliado).
    """

    entries = []

    for line in output.splitlines():
        if not line:
            continue

        if line.startswith("??"):
            path = line[3:].strip()
            if path:
                entries.append(f"untracked  {path}")
            continue

        xy = line[:2]
        rest = line[3:].strip()
        index_status = xy[0] if len(xy) > 0 else " "
        worktree_status = xy[1] if len(xy) > 1 else " "
        label = _porcelain_change_label(index_status, worktree_status)

        if " -> " in rest:
            entries.append(f"{label:<10} {rest}")
        elif rest:
            entries.append(f"{label:<10} {rest}")

    return entries


def working_tree_changes(repo_path):
    """
    :return: ``(dirty, lines, error)`` donde ``lines`` lista cambios
        locales (vacío si el árbol está limpio).
    :rtype: tuple
    """

    output, error = git(repo_path, "status", "--porcelain")

    if error is not None:
        return None, [], error

    if not output:
        return False, [], None

    return True, parse_porcelain(output), None


def ahead_behind(repo_path, fallback_ref=None):
    """
    Cuenta commits locales sin pushear (ahead) y commits remotos sin
    traer (behind), comparando HEAD contra su upstream (@{u}).

    Si la rama actual no tiene upstream configurado, reintenta contra
    ``fallback_ref`` (ej. ``"origin/19.0"``) cuando se provee, en vez de
    fallar directo. No modifica la configuración del repo.

    :param str fallback_ref: ref remoto a usar si ``@{u}`` no existe.
    :return: tupla ``(ahead, behind, error)``. ``error`` no es ``None``
        si tampoco se pudo comparar contra ``fallback_ref`` o git falla.
    :rtype: tuple
    """

    output, error = git(
        repo_path,
        "rev-list",
        "--left-right",
        "--count",
        "@{u}...HEAD",
    )

    if error is not None and fallback_ref:
        output, error = git(
            repo_path,
            "rev-list",
            "--left-right",
            "--count",
            f"{fallback_ref}...HEAD",
        )

    if error is not None:
        return None, None, error

    behind_str, ahead_str = output.split()

    return int(ahead_str), int(behind_str), None


def fetch(repo_path, branch=None, env=None):
    """
    Trae del remoto ``origin``. Si se da ``branch``, fuerza además que
    esa rama se traiga a ``refs/remotes/origin/<branch>`` de forma
    explícita, aunque el ``remote.origin.fetch`` configurado en el repo
    esté restringido a otra rama (repos clonados con fetch de una sola
    rama, donde un `git fetch` normal nunca actualizaría esta rama).

    :param str branch: rama remota a asegurar en las referencias
        locales, además del fetch normal.
    """

    if branch:
        return git(
            repo_path,
            "fetch",
            "origin",
            f"+{branch}:refs/remotes/origin/{branch}",
            env=env,
        )

    return git(repo_path, "fetch", env=env)


def local_branch_exists(repo_path, branch):
    """
    :return: ``True`` si ``refs/heads/<branch>`` existe en el repo.
    :rtype: bool
    """

    _, error = git(
        repo_path,
        "show-ref",
        "--verify",
        "--quiet",
        f"refs/heads/{branch}",
    )

    return error is None


def checkout(repo_path, branch, env=None):
    """
    ``git checkout <branch>``. Si la rama no existe en local pero sí
    como ``origin/<branch>`` (el caller debe haber hecho fetch), git
    crea la rama local con tracking (DWIM de checkout).

    :param str branch: rama a dejar como HEAD.
    """

    return git(repo_path, "checkout", branch, env=env)


def pull_ff_only(repo_path, branch=None, env=None):
    """
    ``git pull --ff-only``. Si se da ``branch``, especifica ``origin``
    y la rama de forma explícita, para que funcione aunque la rama
    actual no tenga upstream configurado (``@{u}``) — de otro modo
    git no sabe de dónde traer y falla con "No hay información de
    rastreo para la rama actual".

    :param str branch: rama remota de la que hacer merge fast-forward.
    """

    if branch:
        return git(repo_path, "pull", "--ff-only", "origin", branch, env=env)

    return git(repo_path, "pull", "--ff-only", env=env)

