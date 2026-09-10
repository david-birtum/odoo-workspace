# Changelog

Todos los cambios notables de `ows` se documentan en este archivo.
Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
Este proyecto aún no usa versionado semántico formal (es una herramienta
interna, no un paquete publicado); las entradas se agrupan por fecha.

## [Unreleased]

## [2026-09-10] — status: ícono amarillo para "rama correcta pero no listo para sync"

### Changed
- `ows status` ya no marca ✅ a un repo con la rama correcta si tiene
  cambios sin commitear o commits sin pushear — ahora usa 🟡 para
  distinguir "rama correcta pero bloqueado para `sync`" de "listo de
  verdad" (✅). ⚠️ se queda exclusivo para rama distinta a la esperada.

## [2026-09-03] — status: fix falso "Unpushed" en ramas distintas a la esperada

### Fixed
- `ows status` reportaba commits "sin pushear" que en realidad sí estaban
  en el remoto: cuando la rama actual no coincide con la esperada por el
  manifest y no tiene upstream configurado, el fallback comparaba contra
  `origin/<rama esperada>` en vez de `origin/<rama actual>` — cualquier
  feature branch basada en la esperada (ej. `19.0`) se veía "adelantada"
  por sus propios commits, aunque ya estuvieran pusheados a su propia
  rama remota. Ahora el fallback siempre compara contra el remoto de la
  rama en la que realmente estás.

## [2026-09-03] — status: muestra señales de sync

### Added
- `ows status` ahora muestra también si el repo tiene cambios sin
  commitear (`Tree : Uncommitted changes`), la misma señal que usa
  `ows sync` para decidir si puede actualizarlo solo — junto con el
  conteo de commits sin pushear que ya mostraba, deja ver de un vistazo
  si un repo calificaría para `sync` sin tener que correrlo.

## [2026-09-03] — `17a6afe`

### Added
- `ows sync <version> <workspace>`: actualiza automáticamente
  (`git pull --ff-only`) los repos que están en la rama esperada, sin
  cambios sin commitear y sin commits por pushear; el resto se reporta
  como omitido con el motivo.
- `ows status` ahora muestra, por repo, si hay commits locales sin pushear
  (`Unpushed : N commit(s)`).
- Captura de credenciales (usuario/token) una sola vez por corrida de
  `sync`, vía un script `GIT_ASKPASS` temporal — nunca se escriben a disco,
  solo viven en memoria del proceso mientras dura la corrida.
- Fallback transparente de credenciales: `sync` intenta primero cada
  operación de red sin forzar usuario/token (para que una SSH key o un
  credential helper ya configurado resuelvan solos); solo pide credenciales
  si git de verdad las necesita.
- `README.md` con documentación de uso real de la herramienta.

### Changed
- `gitutils.git()` ahora devuelve `(valor, error)` en vez de descartar el
  `stderr` de git cuando un comando falla — los mensajes de error reales de
  git llegan hasta la salida de `status`/`current`/`sync` en vez de un
  genérico "Unable to get current branch".
- `ows current` imprime un mensaje explícito ("No workspace manifests
  found for version X") en vez de un ranking vacío cuando la versión no
  tiene ningún manifest.
- `ahead_behind()` acepta un `fallback_ref` (ej. `origin/<rama>`) para
  comparar contra el remoto cuando la rama actual no tiene upstream
  (`@{u}`) configurado, en vez de fallar directo.

### Fixed
- `sync` fallaba con "No hay información de rastreo" al hacer
  `git pull --ff-only` en repos cuya rama actual no tiene upstream
  configurado (ej. `BESTWAY`) — ahora `fetch`/`pull` reciben la rama
  esperada de forma explícita (`git fetch origin +<rama>:refs/remotes/
  origin/<rama>`, `git pull --ff-only origin <rama>`), así funcionan sin
  depender de `@{u}` ni del `remote.origin.fetch` configurado en el repo
  (que en varios repos del workspace apunta a una rama distinta de la que
  realmente se usa).
- El primer intento de `fetch`/`pull` sin credenciales forzadas dejaba que
  git preguntara usuario/contraseña directo por terminal (`/dev/tty`) en
  cada repo, en vez de fallar rápido y disparar el prompt propio de `ows`
  una sola vez — se corrigió desactivando el prompt nativo de git
  (`GIT_TERMINAL_PROMPT=0`) en ese primer intento.

## [2026-07-29] — `b0e63d2`

### Added
- `ows current <version>`: ranking de todos los workspaces de una versión
  según qué tan bien coincide cada uno con las ramas que hay actualmente en
  disco, con detalle de diferencias del workspace mejor rankeado.

## [2026-07-28] — `9a34649`, `e0e9224`

### Added
- Estructura inicial del proyecto: entrypoint `ows`, `commands.py`,
  `gitutils.py`, `utils.py`, `workspace.py`.
- `ows status <version> <workspace>`: compara la rama actual de cada repo
  del manifest contra la rama esperada.
