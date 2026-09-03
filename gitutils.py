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

