import getpass
import os
import stat
import tempfile


ASKPASS_SCRIPT = """#!/bin/sh
case "$1" in
    Username*) printf '%s' "$OWS_GIT_USERNAME" ;;
    *) printf '%s' "$OWS_GIT_TOKEN" ;;
esac
"""


class GitCredentials:
    """
    Captura usuario y token de git una sola vez y los reutiliza para
    todas las llamadas de red (fetch/pull) de una misma corrida de
    ``ows sync``.

    Las credenciales se piden de forma perezosa: solo en el primer
    repositorio que realmente las necesita, no al arrancar el comando.
    Nunca se escriben a disco: viajan en variables de entorno del
    proceso y las lee, en tiempo real, un script auxiliar (GIT_ASKPASS)
    que se borra al terminar la corrida.
    """

    def __init__(self):
        self._env = None
        self._askpass_path = None

    def env(self):
        """
        :return: entorno con ``GIT_ASKPASS`` listo para pasarle a
            ``subprocess.run``. Pide las credenciales por entrada
            estándar la primera vez que se llama; en llamadas
            posteriores reutiliza lo ya capturado.
        :rtype: dict
        """

        if self._env is None:
            self._env = self._prompt_and_build_env()

        return self._env

    def _prompt_and_build_env(self):

        print()
        print("🔐 Git credentials (una sola vez para esta corrida, no se guardan):")
        username = input("    Username : ").strip()
        token = getpass.getpass("    Token    : ")

        fd, path = tempfile.mkstemp(prefix="ows_askpass_")

        with os.fdopen(fd, "w") as f:
            f.write(ASKPASS_SCRIPT)

        os.chmod(path, stat.S_IRWXU)
        self._askpass_path = path

        env = dict(os.environ)
        env["GIT_ASKPASS"] = path
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["OWS_GIT_USERNAME"] = username
        env["OWS_GIT_TOKEN"] = token

        return env

    def cleanup(self):
        """Borra el script temporal de askpass, si se llegó a crear."""

        if self._askpass_path and os.path.exists(self._askpass_path):
            os.remove(self._askpass_path)


AUTH_ERROR_MARKERS = (
    "could not read username",
    "could not read password",
    "terminal prompts disabled",
    "authentication failed",
    "invalid username or token",
)


def needs_credentials(error):
    """
    :param str error: mensaje de stderr de un comando git fallido.
    :return: True si el error sugiere que a git le faltó un usuario o
        password/token (no aplica a fallos de auth por SSH, esos no
        se resuelven con usuario/token).
    :rtype: bool
    """

    lowered = error.lower()

    return any(marker in lowered for marker in AUTH_ERROR_MARKERS)


def silent_env():
    """
    Entorno para el primer intento (sin forzar credenciales) de una
    operación de red: no toca usuario/token, así que una SSH key o un
    credential helper ya configurado en la máquina resuelven la
    autenticación de forma transparente. Sí desactiva el prompt nativo
    de git por terminal (``/dev/tty``), que de otra forma se salta por
    completo nuestro ``GIT_ASKPASS`` y pregunta directo en pantalla en
    cada repo. Si de verdad hacen falta usuario/token, git falla rápido
    en vez de preguntar aquí, para que ``run_with_fallback`` sea quien
    dispare el prompt propio (una sola vez por corrida).

    :rtype: dict
    """

    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"

    return env


def run_with_fallback(operation, repo_path, credentials):
    """
    Corre ``operation(repo_path, env=silent_env())`` primero, sin forzar
    credenciales, para que una SSH key o un credential helper ya
    configurado en la máquina resuelvan la autenticación de forma
    transparente. Solo si el error indica que faltó usuario/token
    (``needs_credentials``), reintenta una vez usando las credenciales
    capturadas por ``credentials`` (pedidas por primera vez aquí si
    esta corrida de ``sync`` aún no las había necesitado).

    :param callable operation: ``fetch``/``pull_ff_only`` u otra función
        con firma ``(repo_path, env=None) -> (output, error)``.
    :param Path repo_path: repositorio sobre el que correr la operación.
    :param GitCredentials credentials: caché de credenciales de la corrida.
    :return: ``(output, error)`` de la operación.
    :rtype: tuple
    """

    output, error = operation(repo_path, env=silent_env())

    if error and needs_credentials(error):
        output, error = operation(repo_path, env=credentials.env())

    return output, error
